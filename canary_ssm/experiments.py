"""Experiment orchestration (handbook Sections 9-13, 16).

Artifact chain (every step consumes explicit, hash-checked artifacts):
  simulate -> data/<role>/ (+ data/<role>_truth/ evaluator-only)
  fit      -> artifacts/model/{nuisance_*.json, model_config.json, dev_selection.csv, fit_failures.csv}
  calibrate-> artifacts/policy/policy.json            (needs model hash)
  validate -> artifacts/policy/null_validation.json   (frozen policy, independent nulls)
  evaluate -> results/final/*                         (needs matching model+policy hashes)
"""
from __future__ import annotations

import itertools
import json
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import decision as dec
from . import metrics as M
from .baselines import DetectorOutput, config_grid, run_baseline
from .hierarchy import EffectDetector, EffectParams, long_run_sd
from .preprocess import Nuisance, fit_nuisance, adjust_roll
from .schema import Rollout, dict_hash, dir_hash, file_hash, KAPPA
from .simulate import SimConfig, Truth, simulate

SEED_BASE = {"smoke": 10_000, "dev": 1_000_000, "calibration": 2_000_000,
             "null_validation": 3_000_000, "test": 4_000_000}
BASELINES = ["matched_contrast", "adj_ewma", "adj_cusum", "topk_cusum"]
SSMS = ["pooled_ssm", "indep_ssm", "hier_ssm"]
ABLATIONS = ["hier_no_persist", "hier_rank0", "hier_arwhite", "hier_white", "hier_huber", "hier_degraded"]
REUSED = ("hier_rank0", "hier_arwhite", "hier_white", "hier_huber", "hier_degraded")   # reuse hier effect params
COMBOS = {"combo_hier_topk": ("hier_ssm", "topk_cusum"), "combo_hier_m0": ("hier_ssm", "matched_contrast"),
          "combo_m0_topk": ("matched_contrast", "topk_cusum")}
FROZEN = {"matched_contrast": {}, "adj_ewma": {"alpha": 0.2}, "adj_cusum": {"k": 0.25}, "topk_cusum": {"K": 3, "k": 0.25},
          **{f"{m}_ssm": {"kind": k, "rho_g": 0.95, "rho_h": 0.95, "sd_g": 0.001, "sd_h_ratio": 1.0, "prior_sd": 0.01, "huber_c": 0.0}
             for m, k in (("pooled", "pooled"), ("indep", "indep"), ("hier", "hier"))}}   # AUDIT USE ONLY, not tuned
ALPHA = 0.05


# ===================================================================== config + data
def load_config(path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    cross = cfg.get("cross")
    if cross:                                              # e.g. {sd_host: [0.01, 0.02, 0.04]}
        keys = list(cross); fams = []
        for f in cfg["families"]:
            for vals in itertools.product(*[cross[k] for k in keys]):
                ov = {**f.get("overrides", {}), **dict(zip(keys, vals))}
                fams.append({"name": f["name"] + "@" + ",".join(f"{k}={v}" for k, v in zip(keys, vals)),
                             "weight": f.get("weight", 1.0) / np.prod([len(cross[k]) for k in keys]), "overrides": ov})
        cfg["families"] = fams
    return cfg


def _family_for(cfg: dict, seed: int) -> dict:
    fams = cfg["families"]; w = np.array([f.get("weight", 1.0) for f in fams], float)
    return fams[int(np.random.default_rng(seed + 99).choice(len(fams), p=w / w.sum()))]


def make_sim_cfg(cfg: dict, family: dict) -> SimConfig:
    d = {**cfg.get("sim", {}), **family.get("overrides", {}), "family": family["name"]}
    return SimConfig.from_dict(d)


def generate_role(cfg: dict, role: str, out_dir: Path, csv: bool = False) -> dict:
    """role sizes: dev/test -> `pairs` paired null+harm; calibration/null_validation -> `pairs` nulls."""
    out_dir = Path(out_dir); truth_dir = out_dir.parent / (out_dir.name + "_truth")
    n = cfg["roles"][role]["pairs"]; base = cfg["roles"][role].get("seed_base", SEED_BASE[role])
    paired = role in ("smoke", "dev", "test")
    for i in range(n):
        seed = base + i
        sc = make_sim_cfg(cfg, _family_for(cfg, seed))
        for harm in ([False, True] if paired else [False]):
            rid = f"r{seed}_{'h' if harm else 'n'}"
            roll, truth = simulate(sc, seed, harm, rid, pair_id=i)
            roll.meta["pair_id"] = i; roll.meta["role"] = role
            roll.save_npz(out_dir / f"{rid}.npz"); truth.save(truth_dir / f"{rid}.npz")
            if csv and i < 3:
                d = out_dir / "csv" / rid; d.mkdir(parents=True, exist_ok=True)
                roll.to_telemetry().to_csv(d / "telemetry.csv", index=False)
                (d / "metadata.json").write_text(json.dumps(roll.metadata(), indent=1))
    man = {"role": role, "n_pairs": n, "paired": paired, "seed_base": base,
           "config_hash": dict_hash(cfg), "n_rollouts": n * (2 if paired else 1)}
    (out_dir / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def load_role(data_dir: Path, truth: bool = True) -> list[tuple[Rollout, Truth | None]]:
    data_dir = Path(data_dir); truth_dir = data_dir.parent / (data_dir.name + "_truth")
    out = []
    for p in sorted(data_dir.glob("r*.npz")):
        out.append((Rollout.load_npz(p), Truth.load(truth_dir / p.name) if truth else None))
    if not out:
        raise FileNotFoundError(f"no rollouts in {data_dir}")
    return out


# ===================================================================== model registry
def ssm_grid(kind: str, persistence: bool = True, constrain: bool = True) -> list[EffectParams]:
    """Declared effect grid. constrain=True drops candidates whose effect-state long-run SD exceeds kappa
    (handoff audit: those cross risk 0.5 on healthy data regardless of the prior)."""
    rhos = (0.0, 0.8, 0.95, 0.99) if persistence else (0.0,)
    g = [EffectParams(kind=kind, rho_g=r, rho_h=r, sd_g=sd, prior_sd=ps)
         for r in rhos for sd in (0.001, 0.005, 0.01) for ps in (0.01, 0.03)]
    return [p for p in g if long_run_sd(p) <= KAPPA] if constrain else g


def candidate_grid(method: str) -> list[dict]:
    """Predeclared candidate configs (<=24 per family)."""
    if method in BASELINES:
        return [p for n, p in config_grid() if n == method]
    kind = {"pooled_ssm": "pooled", "indep_ssm": "indep", "hier_ssm": "hier", "hier_no_persist": "hier"}[method]
    return [asdict(p) for p in ssm_grid(kind, persistence=(method != "hier_no_persist"))]


class Models:
    """Binds nuisance variants + selected hyperparameters; runs any method on a Rollout."""

    def __init__(self, nuis: dict[str, Nuisance], selected: dict | None = None, misclass: float = 0.2):
        self.nuis, self.selected, self.misclass = nuis, selected or {}, misclass

    def adjusted(self, roll: Rollout, key: str, cache: dict):
        if key not in cache:
            cache[key] = adjust_roll(roll, self.nuis["rank0" if key == "rank0" else "main"])
        return cache[key]

    def run(self, roll: Rollout, method: str, params: dict | None = None, cache: dict | None = None) -> DetectorOutput:
        cache = {} if cache is None else cache
        params = params if params is not None else self.selected[method]["params"]
        if method in BASELINES:
            return run_baseline(method, self.adjusted(roll, "main", cache), **params)
        key, nk, override = "main", "main", None
        if method == "hier_rank0":
            key, nk = "rank0", "rank0"
        elif method == "hier_arwhite":
            nk = "arwhite"
        elif method == "hier_white":
            nk = "white"
        elif method == "hier_huber":
            params = {**params, "huber_c": 3.0}
        elif method == "hier_degraded":
            nc = len(roll.canary_idx); cls = roll.class_id[roll.canary_idx].copy()
            rng = np.random.default_rng(int(roll.meta.get("seed", 0)) + 7)
            flip = rng.choice(nc, size=int(round(self.misclass * nc)), replace=False)
            cls[flip] = 1 - cls[flip]; override = cls
        adj = self.adjusted(roll, key, cache)
        return EffectDetector(self.nuis[nk], EffectParams(**params), name=method, class_override=override).run(adj)


def _safe_run(models: Models, roll, method, params, cache, failures: list):
    try:
        return models.run(roll, method, params, cache)
    except (FloatingPointError, np.linalg.LinAlgError, ValueError) as e:      # failed fits are RETAINED
        failures.append({"rollout_id": roll.rollout_id, "method": method, "params": json.dumps(params),
                         "error": f"{type(e).__name__}: {e}"})
        T = roll.T
        return DetectorOutput(method, np.full(T, np.nan), np.zeros(T, bool), None)


# ===================================================================== FIT (development only)
def _alarm_outcome(out: DetectorOutput, thr: float, t0: int, ev: dict) -> dict:
    return M.classify(dec.first_alarm(out.score, out.elig, thr, t0), ev, len(out.score))


def select_on_dev(models: Models, dev, method: str, grid: list[dict], failures: list, log=print) -> tuple[dict, list]:
    """Two-fold (by pair id) internal validation: threshold from nulls of one fold, capped time-to-success
    (misses count as remaining horizon) on harmed rollouts of the other fold. Common objective for all families."""
    nulls = [(r, t) for r, t in dev if not t.harm]; harms = [(r, t) for r, t in dev if t.harm]
    nc = len(nulls[0][0].canary_idx)
    per_fold = len(nulls) // 2
    if per_fold < int(np.ceil(1 / ALPHA)):       # k=ceil((B+1)(1-alpha)) > B  =>  infinite threshold, no alarms
        raise ValueError(f"dev fold has only {per_fold} nulls; need >= {int(np.ceil(1 / ALPHA))} for alpha={ALPHA}. "
                         "Use more dev pairs (>= 40 pairs; the full config uses 300).")
    evs = {r.rollout_id: M.event_truth(t, nc) for r, t in harms}
    rows = []
    for ci, params in enumerate(grid):
        t_start = time.time()
        Mx, fold_n, out_h, fold_h = [], [], [], []
        for r, t in nulls:
            o = _safe_run(models, r, method, params, {}, failures)
            Mx.append(dec.release_max(o.score, o.elig, r.t0)); fold_n.append(t.pair_id % 2)
        for r, t in harms:
            o = _safe_run(models, r, method, params, {}, failures)
            out_h.append((o.score, o.elig, r.t0, evs[r.rollout_id])); fold_h.append(t.pair_id % 2)
        Mx, fold_n, fold_h = np.array(Mx), np.array(fold_n), np.array(fold_h)
        obj = []
        for f in (0, 1):
            thr = dec.calibrate_threshold(Mx[fold_n == f], ALPHA)["threshold"]
            for (s, e, t0, ev), fh in zip(out_h, fold_h):
                if fh != 1 - f or not ev["has_event"]:
                    continue
                obj.append(M.classify(dec.first_alarm(s, e, thr, t0), ev, len(s))["capped"])
        score = float(np.mean(obj)) if obj else np.inf
        rows.append({"method": method, "cand": ci, "params": json.dumps(params), "dev_capped_time": score,
                     "seconds": round(time.time() - t_start, 1)})
        log(f"  [{method}] cand {ci + 1}/{len(grid)} capped={score:.2f}")
    best = min(rows, key=lambda r: r["dev_capped_time"])
    return json.loads(best["params"]), rows


def fit(dev_dir: Path, out_dir: Path, methods: list[str], log=print, max_dev_pairs: int | None = None,
        grid_stride: int = 1, beta_mode: str = "pre", frozen: bool = False) -> dict:
    """frozen=True skips hyperparameter selection and uses FROZEN declared values (calibration AUDITS only)."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    dev = load_role(dev_dir)
    if max_dev_pairs:
        dev = [(r, t) for r, t in dev if t.pair_id < max_dev_pairs]
    healthy = [r for r, t in dev if not t.harm]
    log(f"fit: {len(healthy)} healthy dev rollouts for nuisance (beta_mode={beta_mode}, frozen={frozen})")
    nuis = {"main": fit_nuisance(healthy, 1, "ar_only", beta_mode)}
    if "hier_rank0" in methods:
        nuis["rank0"] = fit_nuisance(healthy, 0, "ar_only", beta_mode)
    if "hier_arwhite" in methods:
        nuis["arwhite"] = fit_nuisance(healthy, 1, "ar_white", beta_mode)
    if "hier_white" in methods:
        nuis["white"] = fit_nuisance(healthy, 1, "white", beta_mode)
    for k, n in nuis.items():
        n.save(out_dir / f"nuisance_{k}.json")
    models = Models(nuis)
    failures, rows, selected = [], [], {}
    for m in methods:
        if frozen:
            base = "hier_ssm" if m in REUSED + ("hier_no_persist",) else m
            selected[m] = {"params": FROZEN[base], "frozen_for_audit": True, "loc_cutoff": 3}
            continue
        if m in REUSED:
            selected[m] = {"params": selected["hier_ssm"]["params"], "reused_from": "hier_ssm"}
            continue
        best, r = select_on_dev(models, dev, m, candidate_grid(m)[::grid_stride], failures, log)  # stride>1: smoke only
        selected[m] = {"params": best}; rows += r
    models.selected = selected
    if not frozen:                      # localization cutoff chosen on development (max mean F1 at onset+30)
        harms = [(r, t) for r, t in dev if t.harm]; nc = len(harms[0][0].canary_idx)
        for m in methods:
            f1 = {c: [] for c in range(1, 6)}
            for r, t in harms[:100]:
                ev = M.event_truth(t, nc)
                if not ev["has_event"]:
                    continue
                o = _safe_run(models, r, m, None, {}, failures)
                for c in f1:
                    loc = M.localization(o, ev, cutoff=c)
                    if loc:
                        p_, rc = loc["cut_precision"], loc["cut_recall"]
                        f1[c].append(0 if p_ + rc == 0 else 2 * p_ * rc / (p_ + rc))
            selected[m]["loc_cutoff"] = int(max(f1, key=lambda c: np.mean(f1[c]) if f1[c] else -1))
    cfg = {"selected": selected, "kappa": KAPPA, "alpha": ALPHA, "methods": methods, "frozen": frozen,
           "beta_mode": beta_mode, "dev_rollouts": len(dev), "misclass": 0.2,
           "nuisance_files": sorted(f"nuisance_{k}.json" for k in nuis)}
    (out_dir / "model_config.json").write_text(json.dumps(cfg, indent=1))
    pd.DataFrame(rows).to_csv(out_dir / "dev_selection.csv", index=False)
    pd.DataFrame(failures, columns=["rollout_id", "method", "params", "error"]).to_csv(out_dir / "fit_failures.csv", index=False)
    return cfg


def load_models(model_dir: Path) -> tuple[Models, dict, str]:
    model_dir = Path(model_dir)
    for need in ("model_config.json", "nuisance_main.json"):
        if not (model_dir / need).exists():
            raise FileNotFoundError(f"missing model artifact {need} in {model_dir}")
    cfg = json.loads((model_dir / "model_config.json").read_text())
    nuis = {p.stem.replace("nuisance_", ""): Nuisance.load(p) for p in model_dir.glob("nuisance_*.json")}
    h = dir_hash([model_dir / "model_config.json", *model_dir.glob("nuisance_*.json")])
    return Models(nuis, cfg["selected"], cfg.get("misclass", 0.2)), cfg, h


# ===================================================================== CALIBRATE / VALIDATE
# ---------------------------------------------------------------- joint calibration of combined detectors
def combine_outputs(name: str, comps: list[DetectorOutput], ecdfs: list[np.ndarray]) -> DetectorOutput:
    """Union detector with ONE false-alert budget: map each component score to the fraction of calibration-null
    rollout maxima it exceeds, take the max over components, then calibrate that combined score like any other."""
    import functools
    sc = [np.where(np.isfinite(o.score), np.searchsorted(e, o.score, side="right") / len(e), np.nan)
          for o, e in zip(comps, ecdfs)]
    elig = np.logical_and.reduce([o.elig for o in comps])
    return DetectorOutput(name, functools.reduce(np.fmax, sc), elig, None, None, float(sum(o.runtime_ms for o in comps)))


def combos_for(methods: list[str]) -> list[str]:
    return [c for c, comp in COMBOS.items() if all(x in methods for x in comp)]


def run_methods(models: Models, roll: Rollout, methods: list[str], failures: list, pol: dict | None = None) -> dict:
    cache = {}
    outs = {m: _safe_run(models, roll, m, None, cache, failures) for m in methods}
    if pol and pol.get("ecdf"):
        for c in pol.get("combos", []):
            outs[c] = combine_outputs(c, [outs[x] for x in COMBOS[c]], [np.array(pol["ecdf"][x]) for x in COMBOS[c]])
    return outs


def _null_scores(models: Models, rolls, methods, failures, pol=None):
    res = {}
    for r, _ in rolls:
        for m, o in run_methods(models, r, methods, failures, pol).items():
            res.setdefault(m, []).append(o)
    return res


def calibrate(cal_dir: Path, model_dir: Path, out_dir: Path, log=print) -> dict:
    models, cfg, mh = load_models(model_dir)
    rolls = load_role(cal_dir, truth=False); failures = []
    outs = _null_scores(models, rolls, cfg["methods"], failures)
    t0 = rolls[0][0].t0
    pol = {"model_hash": mh, "calib_hash": dict_hash({"ids": [r.rollout_id for r, _ in rolls]}),
           "alpha": cfg["alpha"], "n_calibration": len(rolls), "thresholds": {}, "advisory": {}, "ecdf": {}, "combos": []}

    def one(m, olist):
        mx = np.array([dec.release_max(o.score, o.elig, r.t0) for o, (r, _) in zip(olist, rolls)])
        c = dec.calibrate_threshold(mx, cfg["alpha"]); c["insample_alert_rate"] = float(np.mean(mx > c["threshold"]))
        pol["thresholds"][m] = c
        pol["advisory"][m] = dec.calibrate_advisory([o.score for o in olist], [o.elig for o in olist], t0, cfg["alpha"])
        log(f"  {m:18s} thr={c['threshold']:.4g} (k={c['k']}/{c['B']})")
        return mx

    for m in cfg["methods"]:
        mx = one(m, outs[m])
        pol["ecdf"][m] = sorted(float(v) if np.isfinite(v) else -1e18 for v in mx)
    for c in combos_for(cfg["methods"]):
        comb = [combine_outputs(c, [outs[x][i] for x in COMBOS[c]], [np.array(pol["ecdf"][x]) for x in COMBOS[c]])
                for i in range(len(rolls))]
        one(c, comb); pol["combos"].append(c)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "policy.json").write_text(json.dumps(pol, indent=1))   # json keeps Infinity round-trip safe
    return pol


def load_policy(policy_dir: Path, model_hash: str) -> dict:
    p = Path(policy_dir) / "policy.json"
    if not p.exists():
        raise FileNotFoundError(f"missing policy artifact {p}")
    pol = json.loads(p.read_text())
    if pol["model_hash"] != model_hash:
        raise ValueError("policy was calibrated for a different model artifact (hash mismatch)")
    return pol


def _alert_table(outs: dict, rolls, pol, fam) -> dict:
    rep = {}
    for m, olist in outs.items():
        thr = pol["thresholds"][m]["threshold"]
        al = np.array([dec.first_alarm(o.score, o.elig, thr, r.t0) is not None for o, (r, _) in zip(olist, rolls)])
        k, n = int(al.sum()), len(al); lo, hi = M.clopper_pearson(k, n)
        rep[m] = {"alerts": k, "n": n, "rate": k / n, "ci95": [lo, hi], "target": pol["alpha"],
                  "pass_contains_5pct": bool(lo <= pol["alpha"] <= hi), "pass_upper_le_8pct": bool(hi <= 0.08),
                  "by_family": {f: float(al[[x == f for x in fam]].mean()) for f in sorted(set(fam))}}
    return rep


def validate_null(val_dir: Path, model_dir: Path, policy_dir: Path, log=print) -> dict:
    models, cfg, mh = load_models(model_dir); pol = load_policy(policy_dir, mh)
    rolls = load_role(val_dir, truth=False); failures = []
    outs = _null_scores(models, rolls, cfg["methods"], failures, pol)
    rep = _alert_table(outs, rolls, pol, [r.meta.get("family") for r, _ in rolls])
    for m, v in rep.items():
        log(f"  {m:18s} {v['alerts']}/{v['n']} = {v['rate']:.3f}  CI [{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]  "
            f"contains5%={v['pass_contains_5pct']} upper<=8%={v['pass_upper_le_8pct']}")
    Path(policy_dir, "null_validation.json").write_text(json.dumps(rep, indent=1))
    return rep


def audit_null(cfg_path: Path, model_dir: Path, policy_dir: Path, n: int = 500, out_dir: Path = Path("results/audit"),
               methods: list[str] | None = None, seed_base: int = 6_000_000, log=print) -> pd.DataFrame:
    """Fresh NULL rollouts for every family in cfg (step-only, phi_e misspecification, heavy tails, ...) scored with the
    FROZEN model + policy. Pass labels are computed from numbers: 95% CI contains 5% OR upper bound <= 8%."""
    cfg = load_config(cfg_path); models, mcfg, mh = load_models(model_dir); pol = load_policy(policy_dir, mh)
    meths = [m for m in (methods or mcfg["methods"]) if m in mcfg["methods"]]
    rows = []
    for fi, fam in enumerate(cfg["families"]):
        sc = make_sim_cfg(cfg, fam); failures = []; outs = {}
        for i in range(n):
            seed = seed_base + fi * 100_000 + i
            roll, _ = simulate(sc, seed, False, f"a{seed}", pair_id=i)
            for m, o in run_methods(models, roll, meths, failures, pol).items():
                outs.setdefault(m, []).append(o)
        t0 = sc.t_pre
        for m, olist in outs.items():
            thr = pol["thresholds"][m]["threshold"]
            k = sum(dec.first_alarm(o.score, o.elig, thr, t0) is not None for o in olist)
            lo, hi = M.clopper_pearson(k, n)
            rows.append({"family": fam["name"], "method": m, "alerts": k, "n": n, "rate": k / n, "ci_lo": lo, "ci_hi": hi,
                         "pass_contains_5pct": bool(lo <= pol["alpha"] <= hi), "pass_upper_le_8pct": bool(hi <= 0.08),
                         "above_target": bool(lo > pol["alpha"]), "gate_evaluable": bool(n >= 400),
                         "abstain_frac": float(np.mean([1 - o.elig[t0:].mean() for o in olist])), "fit_failures": len(failures)})
        log(f"  family {fam['name']}: done")
    df = pd.DataFrame(rows); Path(out_dir).mkdir(parents=True, exist_ok=True)
    df.to_csv(Path(out_dir) / "table_audit_null.csv", index=False)
    return df


# ===================================================================== EVALUATE
def evaluate(test_dir: Path, model_dir: Path, policy_dir: Path, out_dir: Path, log=print) -> Path:
    models, cfg, mh = load_models(model_dir); pol = load_policy(policy_dir, mh)
    test = load_role(test_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    nc = len(test[0][0].canary_idx); failures = []
    rows, hostrows, flick, rt, calib = [], [], [], [], []
    for i, (r, t) in enumerate(test):
        ev = M.event_truth(t, nc)
        for m, o in run_methods(models, r, cfg["methods"], failures, pol).items():
            thr = pol["thresholds"][m]["threshold"]
            ta = dec.first_alarm(o.score, o.elig, thr, r.t0)
            c = M.classify(ta, ev, r.T)
            rows.append({"rollout_id": r.rollout_id, "pair_id": t.pair_id, "family": t.family, "harm": t.harm,
                         "method": m, "kind": c["kind"], "status": c["status"], "alarm_time": ta, "onset": ev["onset"],
                         "delay": c["delay"], "capped": c["capped"], "followup": c.get("followup", np.nan),
                         "brier": M.brier(o, ev, r.t0), "elig_frac": float(o.elig[r.t0:].mean())})
            loc = M.localization(o, ev, cutoff=cfg["selected"].get(m, {}).get("loc_cutoff", 3))
            if loc:
                hostrows.append({"rollout_id": r.rollout_id, "method": m, "family": t.family, **loc,
                                 "detected": c["status"] == "success"})
            a = pol["advisory"][m]; ad = dec.advisory_replay(o.score, o.elig, r.t0, a["h_on"], a["h_off"], a["n_clear"])
            flick.append({"rollout_id": r.rollout_id, "method": m, "harm": t.harm, "reversals": ad["reversals"],
                          "time_paused": ad["time_paused"], "first_pause": ad["first_pause"]})
            rt.append({"rollout_id": r.rollout_id, "method": m, "runtime_ms_per_update": o.runtime_ms})
            if o.host_prob is not None:
                P = o.host_prob[r.t0:][o.elig[r.t0:]]; J = ev["J"][r.t0:][o.elig[r.t0:]]
                b = np.minimum((P * 10).astype(int), 9)
                for k in range(10):
                    calib.append({"method": m, "bin": k, "n": int((b == k).sum()), "sum_p": float(P[b == k].sum()),
                                  "sum_j": float(J[b == k].sum())})
        if (i + 1) % 50 == 0:
            log(f"  evaluated {i + 1}/{len(test)}")
    pd.DataFrame(rows).to_csv(out_dir / "per_rollout_metrics.csv", index=False)
    pd.DataFrame(hostrows).to_csv(out_dir / "host_metrics.csv", index=False)
    pd.DataFrame(flick).to_csv(out_dir / "flicker.csv", index=False)
    pd.DataFrame(rt).to_csv(out_dir / "runtime.csv", index=False)
    pd.DataFrame(calib).groupby(["method", "bin"]).sum().reset_index().to_csv(out_dir / "calibration_bins.csv", index=False)
    pd.DataFrame(failures, columns=["rollout_id", "method", "params", "error"]).to_csv(out_dir / "fit_failures.csv", index=False)
    write_manifest(out_dir, model_dir, policy_dir, test_dir, cfg, pol, len(failures))
    return out_dir


def write_manifest(out_dir, model_dir, policy_dir, test_dir, cfg, pol, n_fail):
    def git():
        try:
            return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return None
    man = {"commit": git(), "python": sys.version, "machine": {"platform": platform.platform(),
           "processor": platform.processor(), "cpu_count": __import__("os").cpu_count()},
           "model_hash": pol["model_hash"], "calib_hash": pol["calib_hash"], "alpha": pol["alpha"],
           "thresholds": {m: c["threshold"] for m, c in pol["thresholds"].items()},
           "selected": cfg["selected"], "fit_failures_test": n_fail,
           "test_manifest": json.loads((Path(test_dir) / "manifest.json").read_text()),
           "lockfile_hash": file_hash(Path("requirements.lock")) if Path("requirements.lock").exists() else None,
           "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (Path(out_dir) / "experiment_manifest.json").write_text(json.dumps(man, indent=1, default=str))


# ===================================================================== runtime benchmark
def benchmark(nuis_dir: Path | None, sizes=(10, 50, 100), reps: int = 3, out: Path = Path("results/runtime_scaling.csv")):
    rows = []
    for nc in sizes:
        cfg = SimConfig(n_canary=nc, n_hosts=nc + 90, n_affected=min(3, nc))
        healthy = [simulate(cfg, 50_000 + s, False)[0] for s in range(12)]
        nuis = fit_nuisance(healthy)
        for kind in ("hier", "indep"):
            ts = []
            for s in range(reps):
                roll, _ = simulate(cfg, 60_000 + s, True)
                a = adjust_roll(roll, nuis)
                ts.append(EffectDetector(nuis, EffectParams(kind=kind)).run(a).update_times_ms)
            ts = np.concatenate(ts)
            rows.append({"n_canaries": nc, "model": kind, "median_ms": np.median(ts), "p95_ms": np.quantile(ts, .95),
                         "p99_ms": np.quantile(ts, .99), "machine": platform.processor() or platform.machine()})
    df = pd.DataFrame(rows); Path(out).parent.mkdir(parents=True, exist_ok=True); df.to_csv(out, index=False)
    return df
