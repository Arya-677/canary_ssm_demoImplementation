"""Experiment orchestration (handbook Sections 9-13, 16; Change Plan WP-A3, A4, I2, I6).

Artifact chain (every step consumes explicit, hash-checked artifacts):
  simulate -> data/<role>/ (+ data/<role>_truth/ evaluator-only)
  fit      -> artifacts/model/{nuisance_*.json, model_config.json, dev_selection.csv, fit_failures.csv}
  calibrate-> artifacts/policy/policy.json            (needs model hash)
  validate -> artifacts/policy/null_validation.json   (frozen policy, independent nulls)
  evaluate -> results/final/*                         (needs matching model+policy hashes)
"""
from __future__ import annotations

import functools
import itertools
import json
import os
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import decision as dec
from . import manifest as man_mod
from . import metrics as M
from . import parallel, seeds
from .baselines import DetectorOutput, config_grid, run_baseline
from .factor import Adjusted
from .hierarchy import EffectDetector, EffectParams, long_run_sd
from .preprocess import Nuisance, adjust_roll, fit_nuisance
from .schema import KAPPA, Rollout, dict_hash, dir_hash
from .simulate import SimConfig, Truth, simulate

SEED_BASE = seeds.RANGES
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
ALPHA_LIST = [0.01, 0.02, 0.05, 0.10]
GRID_VERSION = "v1"


def code_version_tag() -> str:
    """Short hash of core detector/preprocess source files for safe cache invalidation."""
    pkg = Path(__file__).resolve().parent
    parts = [pkg / n for n in ("schema.py", "factor.py", "preprocess.py", "hierarchy.py", "baselines.py", "decision.py")]
    return dir_hash([p for p in parts if p.exists()])[:16]


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


def _role_seed_purpose(cfg: dict, role: str) -> str:
    return cfg.get("roles", {}).get(role, {}).get("seed_purpose", role)


def _build_role_specs(cfg: dict, role: str) -> list[dict]:
    """Deterministic ordered rollout specifications for a role manifest."""
    role_cfg = cfg["roles"][role]
    n = int(role_cfg["pairs"])
    purpose = _role_seed_purpose(cfg, role)
    use_explicit_base = "seed_base" in role_cfg
    base = int(role_cfg["seed_base"]) if use_explicit_base else seeds.RANGES[purpose]
    paired = role in ("smoke", "dev", "test")
    specs = []
    for i in range(n):
        seed = base + i if use_explicit_base else seeds.seed_for(purpose, i, 0)
        fam = _family_for(cfg, seed)
        sc = make_sim_cfg(cfg, fam)
        for harm in ([False, True] if paired else [False]):
            rid = f"r{seed}_{'h' if harm else 'n'}"
            specs.append({
                "rollout_id": rid,
                "seed": int(seed),
                "harm": bool(harm),
                "pair_id": int(i),
                "role": role,
                "family": fam["name"],
                "sim_cfg": asdict(sc),
            })
    specs.sort(key=lambda s: s["rollout_id"])
    return specs


def generate_role(
    cfg: dict,
    role: str,
    out_dir: Path,
    csv: bool = False,
    manifest_only: bool = False,
    compact: bool = False,
    config_path: str | None = None,
) -> dict:
    """role sizes: dev/test -> `pairs` paired null+harm; calibration/null_validation -> `pairs` nulls."""
    out_dir = Path(out_dir); truth_dir = out_dir.parent / (out_dir.name + "_truth")
    role_cfg = cfg["roles"][role]
    n = int(role_cfg["pairs"])
    purpose = _role_seed_purpose(cfg, role)
    use_explicit_base = "seed_base" in role_cfg
    base = int(role_cfg["seed_base"]) if use_explicit_base else seeds.RANGES[purpose]
    paired = role in ("smoke", "dev", "test")
    specs = _build_role_specs(cfg, role)
    n_rollouts = len(specs)
    disk_info = parallel.check_disk_budget(out_dir, n_rollouts_to_store=0 if manifest_only else n_rollouts)

    if not manifest_only:
        out_dir.mkdir(parents=True, exist_ok=True)
        for sp in specs:
            sc = SimConfig.from_dict(sp["sim_cfg"])
            roll, truth = simulate(sc, sp["seed"], sp["harm"], sp["rollout_id"], pair_id=sp["pair_id"])
            roll.meta["pair_id"] = sp["pair_id"]; roll.meta["role"] = role
            roll.save_npz(out_dir / f"{sp['rollout_id']}.npz", compact=compact)
            truth.save(truth_dir / f"{sp['rollout_id']}.npz", compact=compact)
            if csv and sp["pair_id"] < 3:
                d = out_dir / "csv" / sp["rollout_id"]; d.mkdir(parents=True, exist_ok=True)
                roll.to_telemetry().to_csv(d / "telemetry.csv", index=False)
                (d / "metadata.json").write_text(json.dumps(roll.metadata(), indent=1), encoding="utf-8")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    sr = (
        {"purpose": f"explicit:{purpose}", "count": n, "min_seed": base, "max_seed": base + max(n - 1, 0)}
        if use_explicit_base else seeds.range_summary(purpose, n, 0)
    )
    man = {
        "role": role,
        "regime": cfg.get("regime"),
        "n_pairs": n,
        "paired": paired,
        "seed_purpose": purpose,
        "seed_base": base,
        "seed_ranges": [sr],
        "config_hash": dict_hash(cfg),
        "config": cfg,
        "config_path": config_path,
        "n_rollouts": n_rollouts,
        "manifest_only": bool(manifest_only),
        "compact": bool(compact),
        "disk_free_bytes": disk_info["disk_free_bytes"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return man


def load_role(data_dir: Path, truth: bool = True) -> list[tuple[Rollout, Truth | None]]:
    data_dir = Path(data_dir); truth_dir = data_dir.parent / (data_dir.name + "_truth")
    out = []
    for p in sorted(data_dir.glob("r*.npz")):
        out.append((Rollout.load_npz(p), Truth.load(truth_dir / p.name) if truth else None))
    if not out:
        raise FileNotFoundError(f"no rollouts in {data_dir}")
    return out


def _rollout_specs_from_dir(data_dir: Path, truth: bool = False) -> list[dict]:
    """Reconstruct exact simulation specs from `data/<role>/manifest.json` for `--generate-on-the-fly`."""
    data_dir = Path(data_dir)
    mp = data_dir / "manifest.json"
    if not mp.exists():
        raise FileNotFoundError(f"missing manifest.json in {data_dir} required for --generate-on-the-fly")
    man = json.loads(mp.read_text(encoding="utf-8"))
    if "config" not in man:
        raise ValueError(f"{mp} lacks embedded 'config'; re-simulate manifest or run from disk")
    specs = _build_role_specs(man["config"], man["role"])
    for sp in specs:
        sp["need_truth"] = bool(truth)
    return specs


# ===================================================================== cache helpers
def _nuisance_hash_map(nuis: dict[str, Nuisance]) -> str:
    return dict_hash({k: v.to_dict() for k, v in sorted(nuis.items())})[:16]


def _save_adj_cache(path: Path, adj: Adjusted) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(
        tmp,
        r=adj.r,
        obs=adj.obs,
        elig=adj.elig,
        U=adj.U,
        lam=adj.lam,
        sigma=adj.sigma,
        rm=adj.rm,
        class_id=adj.class_id,
        t0=adj.t0,
        fallback=adj.fallback,
        f_hat=adj.f_hat,
    )
    os.replace(tmp, path)


def _load_adj_cache(path: Path) -> Adjusted:
    z = np.load(path, allow_pickle=False)
    return Adjusted(
        r=z["r"],
        obs=z["obs"],
        elig=z["elig"],
        U=z["U"],
        lam=z["lam"],
        sigma=z["sigma"],
        rm=z["rm"],
        class_id=z["class_id"],
        t0=int(z["t0"]),
        fallback=z["fallback"],
        f_hat=z["f_hat"],
    )


def _save_sel_cache(path: Path, out: DetectorOutput) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, score=out.score, elig=out.elig, runtime_ms=np.array([out.runtime_ms]))
    os.replace(tmp, path)


def _load_sel_cache(path: Path, method: str, params: dict) -> DetectorOutput:
    z = np.load(path, allow_pickle=False)
    return DetectorOutput(
        method=method,
        score=z["score"],
        elig=z["elig"],
        host_score=None,
        runtime_ms=float(z["runtime_ms"][0]),
        params=params,
    )


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

    def __init__(
        self,
        nuis: dict[str, Nuisance],
        selected: dict | None = None,
        misclass: float = 0.2,
        cache_dir: Path | None = None,
        nuis_hash: str | None = None,
        code_ver: str | None = None,
    ):
        self.nuis = nuis
        self.selected = selected or {}
        self.misclass = misclass
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.nuis_hash = nuis_hash or _nuisance_hash_map(nuis)
        self.code_ver = code_ver or code_version_tag()

    def adjusted(self, roll: Rollout, key: str, cache: dict) -> Adjusted:
        if key not in cache:
            n_obj = self.nuis["rank0" if key == "rank0" else "main"]
            if self.cache_dir is not None:
                nh = dict_hash(n_obj.to_dict())[:16]
                cpath = self.cache_dir / "adj" / f"{nh}_{self.code_ver}" / key / f"{roll.rollout_id}.npz"
                if cpath.exists():
                    cache[key] = _load_adj_cache(cpath)
                else:
                    adj = adjust_roll(roll, n_obj)
                    _save_adj_cache(cpath, adj)
                    cache[key] = adj
            else:
                cache[key] = adjust_roll(roll, n_obj)
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


def _eval_candidate_core(
    models: Models,
    dev: list[tuple[Rollout, Truth | None]],
    method: str,
    params: dict,
    ci: int,
    evs: dict[str, dict],
    cache_dir: Path | None,
    code_ver: str,
    mem_adj_caches: dict[str, dict] | None = None,
) -> tuple[dict, list[dict]]:
    t_start = time.time()
    failures: list[dict] = []
    cand_hash = dict_hash(params)[:16]
    nh = models.nuis_hash
    Mx, fold_n, out_h, fold_h = [], [], [], []
    for r, t in dev:
        sel_path = (
            Path(cache_dir) / "sel" / method / f"{nh}_{code_ver}_{cand_hash}" / f"{r.rollout_id}.npz"
            if cache_dir is not None else None
        )
        if sel_path is not None and sel_path.exists():
            o = _load_sel_cache(sel_path, method, params)
        else:
            rc = mem_adj_caches.setdefault(r.rollout_id, {}) if mem_adj_caches is not None else {}
            o = _safe_run(models, r, method, params, rc, failures)
            if sel_path is not None and len(failures) == 0:
                _save_sel_cache(sel_path, o)
        if not t.harm:
            Mx.append(dec.release_max(o.score, o.elig, r.t0))
            fold_n.append(t.pair_id % 2)
        else:
            out_h.append((o.score, o.elig, r.t0, evs[r.rollout_id]))
            fold_h.append(t.pair_id % 2)
    Mx_a, fold_n_a, fold_h_a = np.array(Mx), np.array(fold_n), np.array(fold_h)
    obj = []
    for f in (0, 1):
        thr = dec.calibrate_threshold(Mx_a[fold_n_a == f], ALPHA)["threshold"]
        for (s, e, t0, ev), fh in zip(out_h, fold_h_a):
            if fh != 1 - f or not ev["has_event"]:
                continue
            obj.append(M.classify(dec.first_alarm(s, e, thr, t0), ev, len(s))["capped"])
    score = float(np.mean(obj)) if obj else np.inf
    row = {
        "method": method,
        "cand": ci,
        "params": json.dumps(params),
        "dev_capped_time": score,
        "seconds": round(time.time() - t_start, 2),
    }
    return row, failures


def _eval_candidate_worker(task: dict) -> tuple[dict, list[dict]]:
    """Top-level picklable worker evaluating one candidate across all dev rollouts."""
    nuis = {k: Nuisance.from_dict(v) for k, v in task["nuis"].items()}
    models = Models(
        nuis,
        misclass=task["misclass"],
        cache_dir=Path(task["cache_dir"]) if task["cache_dir"] else None,
        code_ver=task["code_ver"],
    )
    if task["dev_dir"] is not None:
        dev = load_role(Path(task["dev_dir"]), truth=True)
        if task["max_dev_pairs"] is not None:
            dev = [(r, t) for r, t in dev if t.pair_id < task["max_dev_pairs"]]
    else:
        dev = task["dev"]
    return _eval_candidate_core(
        models,
        dev,
        task["method"],
        task["params"],
        task["cand"],
        task["evs"],
        Path(task["cache_dir"]) if task["cache_dir"] else None,
        task["code_ver"],
        mem_adj_caches={},
    )


def select_on_dev(
    models: Models,
    dev,
    method: str,
    grid: list[dict],
    failures: list,
    log=print,
    workers: int | None = 1,
    dev_dir: Path | None = None,
    max_dev_pairs: int | None = None,
    cache_dir: Path | None = None,
) -> tuple[dict, list]:
    """Two-fold (by pair id) internal validation: threshold from nulls of one fold, capped time-to-success
    (misses count as remaining horizon) on harmed rollouts of the other fold. Common objective for all families."""
    nulls = [(r, t) for r, t in dev if not t.harm]; harms = [(r, t) for r, t in dev if t.harm]
    nc = len(nulls[0][0].canary_idx)
    per_fold = len(nulls) // 2
    if per_fold < int(np.ceil(1 / ALPHA)):       # k=ceil((B+1)(1-alpha)) > B  =>  infinite threshold, no alarms
        raise ValueError(f"dev fold has only {per_fold} nulls; need >= {int(np.ceil(1 / ALPHA))} for alpha={ALPHA}. "
                         "Use more dev pairs (>= 40 pairs; the full config uses 300).")
    evs = {r.rollout_id: M.event_truth(t, nc) for r, t in harms}
    use_cache = cache_dir if cache_dir is not None else models.cache_dir
    code_ver = models.code_ver
    w = parallel.resolve_workers(workers, len(grid))

    if w > 1:
        nuis_dicts = {k: v.to_dict() for k, v in models.nuis.items()}
        tasks = [{
            "nuis": nuis_dicts,
            "misclass": models.misclass,
            "dev_dir": str(dev_dir) if dev_dir is not None else None,
            "max_dev_pairs": max_dev_pairs,
            "dev": None if dev_dir is not None else dev,
            "method": method,
            "params": params,
            "cand": ci,
            "evs": evs,
            "cache_dir": str(use_cache) if use_cache is not None else None,
            "code_ver": code_ver,
        } for ci, params in enumerate(grid)]
        res = parallel.pmap(_eval_candidate_worker, tasks, workers=w, desc=f"select:{method}", log=log)
        rows = []
        for row, cand_fail in res:
            rows.append(row)
            failures.extend(cand_fail)
            log(f"  [{method}] cand {row['cand'] + 1}/{len(grid)} capped={row['dev_capped_time']:.2f}")
    else:
        rows = []
        mem_adj: dict[str, dict] = {}
        for ci, params in enumerate(grid):
            row, cand_fail = _eval_candidate_core(
                models, dev, method, params, ci, evs, use_cache, code_ver, mem_adj_caches=mem_adj
            )
            rows.append(row)
            failures.extend(cand_fail)
            log(f"  [{method}] cand {ci + 1}/{len(grid)} capped={row['dev_capped_time']:.2f}")

    best = min(rows, key=lambda r: r["dev_capped_time"])
    return json.loads(best["params"]), rows


def fit(
    dev_dir: Path,
    out_dir: Path,
    methods: list[str],
    log=print,
    max_dev_pairs: int | None = None,
    grid_stride: int = 1,
    beta_mode: str = "pre",
    frozen: bool = False,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    noise_mode: str = "ar_only",
    factor_rank: int = 1,
) -> dict:
    """frozen=True skips hyperparameter selection and uses FROZEN declared values (calibration AUDITS only)."""
    t0_wall = time.time()
    dev_dir = Path(dev_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    dev_man = json.loads((dev_dir / "manifest.json").read_text(encoding="utf-8")) if (dev_dir / "manifest.json").exists() else {}
    dev = load_role(dev_dir)
    if max_dev_pairs:
        dev = [(r, t) for r, t in dev if t.pair_id < max_dev_pairs]
    healthy = [r for r, t in dev if not t.harm]
    log(f"fit: {len(healthy)} healthy dev rollouts for nuisance (beta_mode={beta_mode}, frozen={frozen})")
    nuis = {"main": fit_nuisance(healthy, factor_rank, noise_mode, beta_mode)}
    if "hier_rank0" in methods:
        nuis["rank0"] = fit_nuisance(healthy, 0, noise_mode, beta_mode)
    if "hier_arwhite" in methods:
        nuis["arwhite"] = fit_nuisance(healthy, factor_rank, "ar_white", beta_mode)
    if "hier_white" in methods:
        nuis["white"] = fit_nuisance(healthy, factor_rank, "white", beta_mode)
    for k, n in nuis.items():
        n.save(out_dir / f"nuisance_{k}.json")
    models = Models(nuis, cache_dir=cache_dir)
    failures, rows, selected = [], [], {}
    for m in methods:
        if frozen:
            base = "hier_ssm" if m in REUSED + ("hier_no_persist",) else m
            selected[m] = {"params": FROZEN[base], "frozen_for_audit": True, "loc_cutoff": 3}
            continue
        if m in REUSED:
            selected[m] = {"params": selected["hier_ssm"]["params"], "reused_from": "hier_ssm"}
            continue
        best, r = select_on_dev(
            models, dev, m, candidate_grid(m)[::grid_stride], failures, log,
            workers=workers, dev_dir=dev_dir, max_dev_pairs=max_dev_pairs, cache_dir=cache_dir,
        )
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

    sel_df = pd.DataFrame(rows)
    sel_csv = out_dir / "dev_selection.csv"
    sel_df.to_csv(sel_csv, index=False)
    pd.DataFrame(failures, columns=["rollout_id", "method", "params", "error"]).to_csv(out_dir / "fit_failures.csv", index=False)

    wall_s = round(time.time() - t0_wall, 3)
    cfg = man_mod.build_manifest(
        out_dir=out_dir,
        selected=selected,
        kappa=KAPPA,
        alpha=ALPHA,
        methods=methods,
        frozen=frozen,
        kind="frozen" if frozen else "tuned",
        beta_mode=beta_mode,
        noise_mode=noise_mode,
        factor_rank=factor_rank,
        grid_version=GRID_VERSION,
        grid_hash=dict_hash({m: candidate_grid(m) for m in methods if m not in REUSED}),
        candidate_table_hash=man_mod.sha256_file(sel_csv),
        config=dev_man.get("config"),
        config_hash=dev_man.get("config_hash"),
        regime=dev_man.get("regime"),
        seed_ranges=dev_man.get("seed_ranges"),
        dev_rollouts=len(dev),
        misclass=0.2,
        fit_failures=len(failures),
        wall_times={"fit_s": wall_s},
        nuisance_files=sorted(f"nuisance_{k}.json" for k in nuis),
    )
    (out_dir / "model_config.json").write_text(json.dumps(cfg, indent=1, default=str), encoding="utf-8")
    return cfg


def load_models(
    model_dir: Path,
    cache_dir: Path | None = None,
) -> tuple[Models, dict, str]:
    model_dir = Path(model_dir)
    for need in ("model_config.json", "nuisance_main.json"):
        if not (model_dir / need).exists():
            raise FileNotFoundError(f"missing model artifact {need} in {model_dir}")
    cfg = json.loads((model_dir / "model_config.json").read_text(encoding="utf-8"))
    nuis = {p.stem.replace("nuisance_", ""): Nuisance.load(p) for p in model_dir.glob("nuisance_*.json")}
    h = dir_hash([model_dir / "model_config.json", *model_dir.glob("nuisance_*.json")])
    return Models(nuis, cfg["selected"], cfg.get("misclass", 0.2), cache_dir=cache_dir), cfg, h


# ===================================================================== CALIBRATE / VALIDATE
def combine_outputs(name: str, comps: list[DetectorOutput], ecdfs: list[np.ndarray]) -> DetectorOutput:
    """Union detector with ONE false-alert budget: map each component score to the fraction of calibration-null
    rollout maxima it exceeds, take the max over components, then calibrate that combined score like any other."""
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


def _chunked(seq: list, chunk_size: int) -> list[list]:
    return [seq[i:i + chunk_size] for i in range(0, len(seq), max(1, chunk_size))]


def _load_or_sim_rollout(item: tuple[str | None, dict | None], truth_dir: Path | None) -> tuple[Rollout, Truth | None]:
    path_str, spec = item
    if spec is not None:
        sc = SimConfig.from_dict(spec["sim_cfg"])
        roll, truth = simulate(sc, spec["seed"], spec["harm"], spec["rollout_id"], pair_id=spec["pair_id"])
        roll.meta["pair_id"] = spec["pair_id"]
        roll.meta["role"] = spec["role"]
        return roll, (truth if spec.get("need_truth") else None)
    p = Path(path_str)
    roll = Rollout.load_npz(p)
    tr = Truth.load(truth_dir / p.name) if truth_dir is not None else None
    return roll, tr


def _score_rollouts_chunk(task: dict) -> dict:
    """Top-level worker scoring a chunk of disk paths or on-the-fly specs."""
    model_dir = Path(task["model_dir"])
    cache_dir = Path(task["cache_dir"]) if task.get("cache_dir") else None
    models, cfg, _ = load_models(model_dir, cache_dir=cache_dir)
    pol = task.get("pol")
    methods = task["methods"]
    truth_dir = Path(task["truth_dir"]) if task.get("truth_dir") else None
    mode = task["mode"]
    failures: list[dict] = []

    if mode == "null_scores":
        res: list[dict] = []
        for item in task["items"]:
            r, _ = _load_or_sim_rollout(item, None)
            outs = run_methods(models, r, methods, failures, pol)
            rec = {
                "rollout_id": r.rollout_id,
                "t0": r.t0,
                "family": r.meta.get("family"),
                "outs": {m: (o.score, o.elig, float(o.runtime_ms)) for m, o in outs.items()},
            }
            res.append(rec)
        return {"chunk_idx": task["chunk_idx"], "items": res, "failures": failures}

    if mode == "evaluate":
        rows, hostrows, flick, rt, calib_rows = [], [], [], [], []
        for item in task["items"]:
            r, t = _load_or_sim_rollout(item, truth_dir)
            nc = len(r.canary_idx)
            ev = M.event_truth(t, nc)
            for m, o in run_methods(models, r, methods, failures, pol).items():
                thr = pol["thresholds"][m]["threshold"]
                ta = dec.first_alarm(o.score, o.elig, thr, r.t0)
                c = M.classify(ta, ev, r.T)
                rows.append({
                    "rollout_id": r.rollout_id, "pair_id": t.pair_id, "family": t.family, "harm": t.harm,
                    "method": m, "kind": c["kind"], "status": c["status"], "alarm_time": ta, "onset": ev["onset"],
                    "delay": c["delay"], "capped": c["capped"], "followup": c.get("followup", np.nan),
                    "brier": M.brier(o, ev, r.t0), "elig_frac": float(o.elig[r.t0:].mean()),
                })
                loc = M.localization(o, ev, cutoff=cfg["selected"].get(m, {}).get("loc_cutoff", 3))
                if loc:
                    hostrows.append({"rollout_id": r.rollout_id, "method": m, "family": t.family, **loc,
                                     "detected": c["status"] == "success"})
                a = pol["advisory"][m]
                ad = dec.advisory_replay(o.score, o.elig, r.t0, a["h_on"], a["h_off"], a["n_clear"])
                flick.append({"rollout_id": r.rollout_id, "method": m, "harm": t.harm, "reversals": ad["reversals"],
                              "time_paused": ad["time_paused"], "first_pause": ad["first_pause"]})
                rt.append({"rollout_id": r.rollout_id, "method": m, "runtime_ms_per_update": o.runtime_ms})
                if o.host_prob is not None:
                    P = o.host_prob[r.t0:][o.elig[r.t0:]]; J = ev["J"][r.t0:][o.elig[r.t0:]]
                    b = np.minimum((P * 10).astype(int), 9)
                    for k in range(10):
                        cnt = int((b == k).sum())
                        sp = float(P[b == k].sum())
                        sj = float(J[b == k].sum())
                        calib_rows.append({"rollout_id": r.rollout_id, "method": m, "bin": k,
                                           "n": cnt, "sum_p": sp, "sum_j": sj})
        return {
            "chunk_idx": task["chunk_idx"],
            "rows": rows,
            "hostrows": hostrows,
            "flick": flick,
            "rt": rt,
            "calib": calib_rows,
            "failures": failures,
        }
    raise ValueError(f"unknown chunk mode {mode!r}")


def _run_chunked_with_resume(
    tasks: list[dict],
    workers: int | None,
    resume_dir: Path | None,
    journal_name: str,
    desc: str,
    log=print,
) -> list[dict]:
    """Execute `_score_rollouts_chunk` across chunks with deterministic order and optional JSONL resume."""
    import pickle
    if resume_dir is None:
        return parallel.pmap(_score_rollouts_chunk, tasks, workers=workers, desc=desc, log=log)

    resume_dir = Path(resume_dir)
    ckpt_dir = resume_dir / f".resume_{journal_name}"
    journal = parallel.ProgressJournal(resume_dir / f"journal_{journal_name}.jsonl")
    done_keys = journal.completed_keys("chunk_idx")
    cached: dict[int, dict] = {}
    todo: list[dict] = []
    for t in tasks:
        ci = int(t["chunk_idx"])
        cp = ckpt_dir / f"chunk_{ci:05d}.pkl"
        if str(ci) in done_keys and cp.exists():
            with cp.open("rb") as f:
                cached[ci] = pickle.load(f)
        else:
            todo.append(t)

    if todo:
        res_new = parallel.pmap(_score_rollouts_chunk, todo, workers=workers, desc=desc, log=log)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        for out in res_new:
            ci = int(out["chunk_idx"])
            tmp = ckpt_dir / f"chunk_{ci:05d}.tmp.pkl"
            cp = ckpt_dir / f"chunk_{ci:05d}.pkl"
            with tmp.open("wb") as f:
                pickle.dump(out, f)
            os.replace(tmp, cp)
            journal.append({"chunk_idx": ci, "failures": len(out["failures"]), "ts": time.time()})
            cached[ci] = out
    return [cached[int(t["chunk_idx"])] for t in tasks]


def _prepare_rollout_items(data_dir: Path, truth: bool, generate_on_the_fly: bool) -> tuple[list[tuple[str | None, dict | None]], list[str]]:
    data_dir = Path(data_dir)
    if generate_on_the_fly:
        specs = _rollout_specs_from_dir(data_dir, truth=truth)
        items = [(None, sp) for sp in specs]
        ids = [sp["rollout_id"] for sp in specs]
        return items, ids
    paths = sorted(data_dir.glob("r*.npz"))
    if not paths:
        raise FileNotFoundError(f"no rollouts in {data_dir}")
    return [(str(p), None) for p in paths], [p.stem for p in paths]


def _null_scores(
    models: Models,
    rolls,
    methods: list[str],
    failures: list,
    pol: dict | None = None,
) -> dict[str, list[DetectorOutput]]:
    res: dict[str, list[DetectorOutput]] = {}
    for r, _ in rolls:
        for m, o in run_methods(models, r, methods, failures, pol).items():
            res.setdefault(m, []).append(o)
    return res


def calibrate(
    cal_dir: Path,
    model_dir: Path,
    out_dir: Path,
    log=print,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    resume: bool = False,
    generate_on_the_fly: bool = False,
) -> dict:
    t0_wall = time.time()
    cal_dir = Path(cal_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    models, cfg, mh = load_models(model_dir, cache_dir=cache_dir)
    cal_man = json.loads((cal_dir / "manifest.json").read_text(encoding="utf-8")) if (cal_dir / "manifest.json").exists() else {}
    items, rids = _prepare_rollout_items(cal_dir, truth=False, generate_on_the_fly=generate_on_the_fly)
    failures: list[dict] = []

    w = parallel.resolve_workers(workers, len(items))
    if w > 1 or resume or generate_on_the_fly:
        chunks = _chunked(items, max(10, min(100, len(items) // max(1, w) or 1)))
        tasks = [{
            "mode": "null_scores",
            "chunk_idx": ci,
            "items": ch,
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir) if cache_dir is not None else None,
            "methods": cfg["methods"],
            "pol": None,
            "truth_dir": None,
        } for ci, ch in enumerate(chunks)]
        chunk_outs = _run_chunked_with_resume(
            tasks, workers=w, resume_dir=out_dir if resume else None, journal_name="calibrate", desc="calibrate", log=log
        )
        scored_recs = []
        for co in chunk_outs:
            scored_recs.extend(co["items"])
            failures.extend(co["failures"])
        scored_recs.sort(key=lambda d: d["rollout_id"])
        t0 = scored_recs[0]["t0"]
        t0s = [rec["t0"] for rec in scored_recs]
        outs = {
            m: [
                DetectorOutput(m, rec["outs"][m][0], rec["outs"][m][1], None, runtime_ms=rec["outs"][m][2])
                for rec in scored_recs
            ]
            for m in cfg["methods"]
        }
    else:
        rolls = load_role(cal_dir, truth=False)
        outs = _null_scores(models, rolls, cfg["methods"], failures)
        t0 = rolls[0][0].t0
        t0s = [r.t0 for r, _ in rolls]

    pol = {
        "schema_version": 2,
        "model_hash": mh,
        "calib_hash": dict_hash({"ids": rids}),
        "alpha": cfg["alpha"],
        "alpha_list": ALPHA_LIST,
        "B": len(rids),
        "n_calibration": len(rids),
        "regime": cal_man.get("regime"),
        "seed_ranges": cal_man.get("seed_ranges"),
        "thresholds": {},
        "advisory": {},
        "ecdf": {},
        "combos": [],
        "fit_failures_calibration": len(failures),
        "wall_time_s": 0.0,
    }

    def one(m, olist):
        mx = np.array([dec.release_max(o.score, o.elig, rt0) for o, rt0 in zip(olist, t0s)])
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
                for i in range(len(rids))]
        one(c, comb); pol["combos"].append(c)
        # Keep sorted maxima for combos cleanly inside ecdf as well
        pol["ecdf"][c] = sorted(
            float(v) if np.isfinite(v) else -1e18
            for v in (dec.release_max(o.score, o.elig, rt0) for o, rt0 in zip(comb, t0s))
        )
    pol["wall_time_s"] = round(time.time() - t0_wall, 3)
    (out_dir / "policy.json").write_text(json.dumps(pol, indent=1), encoding="utf-8")   # json keeps Infinity round-trip safe
    return pol


def load_policy(policy_dir: Path, model_hash: str) -> dict:
    p = Path(policy_dir) / "policy.json"
    if not p.exists():
        raise FileNotFoundError(f"missing policy artifact {p}")
    pol = json.loads(p.read_text(encoding="utf-8"))
    if pol["model_hash"] != model_hash:
        raise ValueError("policy was calibrated for a different model artifact (hash mismatch)")
    return pol


def _alert_table_from_recs(recs: list[dict], methods_all: list[str], pol: dict) -> dict:
    rep = {}
    fam = [rec["family"] for rec in recs]
    for m in methods_all:
        thr = pol["thresholds"][m]["threshold"]
        al = np.array([
            dec.first_alarm(rec["outs"][m][0], rec["outs"][m][1], thr, rec["t0"]) is not None
            for rec in recs
        ])
        k, n = int(al.sum()), len(al); lo, hi = M.clopper_pearson(k, n)
        rep[m] = {
            "alerts": k, "n": n, "rate": k / n, "ci95": [lo, hi], "target": pol["alpha"],
            "pass_contains_5pct": bool(lo <= pol["alpha"] <= hi), "pass_upper_le_8pct": bool(hi <= 0.08),
            "by_family": {f: float(al[[x == f for x in fam]].mean()) for f in sorted(set(fam))},
        }
    return rep


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


def validate_null(
    val_dir: Path,
    model_dir: Path,
    policy_dir: Path,
    log=print,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    resume: bool = False,
    generate_on_the_fly: bool = False,
) -> dict:
    val_dir = Path(val_dir); policy_dir = Path(policy_dir)
    models, cfg, mh = load_models(model_dir, cache_dir=cache_dir)
    pol = load_policy(policy_dir, mh)
    items, _ = _prepare_rollout_items(val_dir, truth=False, generate_on_the_fly=generate_on_the_fly)
    failures: list[dict] = []

    w = parallel.resolve_workers(workers, len(items))
    if w > 1 or resume or generate_on_the_fly:
        chunks = _chunked(items, max(10, min(100, len(items) // max(1, w) or 1)))
        tasks = [{
            "mode": "null_scores",
            "chunk_idx": ci,
            "items": ch,
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir) if cache_dir is not None else None,
            "methods": cfg["methods"],
            "pol": pol,
            "truth_dir": None,
        } for ci, ch in enumerate(chunks)]
        chunk_outs = _run_chunked_with_resume(
            tasks, workers=w, resume_dir=policy_dir if resume else None, journal_name="validate_null", desc="validate-null", log=log
        )
        scored_recs = []
        for co in chunk_outs:
            scored_recs.extend(co["items"])
            failures.extend(co["failures"])
        scored_recs.sort(key=lambda d: d["rollout_id"])
        methods_all = list(cfg["methods"]) + list(pol.get("combos", []))
        rep = _alert_table_from_recs(scored_recs, methods_all, pol)
    else:
        rolls = load_role(val_dir, truth=False)
        outs = _null_scores(models, rolls, cfg["methods"], failures, pol)
        rep = _alert_table(outs, rolls, pol, [r.meta.get("family") for r, _ in rolls])

    for m, v in rep.items():
        log(f"  {m:18s} {v['alerts']}/{v['n']} = {v['rate']:.3f}  CI [{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]  "
            f"contains5%={v['pass_contains_5pct']} upper<=8%={v['pass_upper_le_8pct']}")
    (policy_dir / "null_validation.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def audit_null(
    cfg_path: Path,
    model_dir: Path,
    policy_dir: Path,
    n: int = 500,
    out_dir: Path = Path("results/audit"),
    methods: list[str] | None = None,
    seed_base: int | None = None,
    seed_purpose: str = "audit",
    workers: int | None = 1,
    cache_dir: Path | None = None,
    log=print,
) -> pd.DataFrame:
    """Fresh NULL rollouts for every family in cfg scored with the FROZEN model + policy."""
    cfg = load_config(cfg_path); _, mcfg, mh = load_models(model_dir); pol = load_policy(policy_dir, mh)
    meths = [m for m in (methods or mcfg["methods"]) if m in mcfg["methods"]]
    rows = []
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    for fi, fam in enumerate(cfg["families"]):
        sc = make_sim_cfg(cfg, fam)
        sc_dict = asdict(sc)
        items: list[tuple[str | None, dict | None]] = []
        for i in range(n):
            seed = (seed_base + fi * 100_000 + i) if seed_base is not None else seeds.seed_for(seed_purpose, i, fi)
            items.append((None, {
                "rollout_id": f"a{seed}",
                "seed": int(seed),
                "harm": False,
                "pair_id": int(i),
                "role": seed_purpose,
                "family": fam["name"],
                "sim_cfg": sc_dict,
                "need_truth": False,
            }))
        w = parallel.resolve_workers(workers, len(items))
        chunks = _chunked(items, max(10, min(100, len(items) // max(1, w) or 1)))
        tasks = [{
            "mode": "null_scores",
            "chunk_idx": ci,
            "items": ch,
            "model_dir": str(model_dir),
            "cache_dir": str(cache_dir) if cache_dir is not None else None,
            "methods": meths,
            "pol": pol,
            "truth_dir": None,
        } for ci, ch in enumerate(chunks)]
        chunk_outs = _run_chunked_with_resume(tasks, workers=w, resume_dir=None, journal_name="audit", desc=f"audit:{fam['name']}", log=log)
        recs, failures = [], []
        for co in chunk_outs:
            recs.extend(co["items"])
            failures.extend(co["failures"])
        recs.sort(key=lambda d: d["rollout_id"])
        t0 = sc.t_pre
        methods_out = list(recs[0]["outs"].keys()) if recs else meths
        for m in methods_out:
            thr = pol["thresholds"][m]["threshold"]
            k = sum(dec.first_alarm(rec["outs"][m][0], rec["outs"][m][1], thr, t0) is not None for rec in recs)
            lo, hi = M.clopper_pearson(k, n)
            rows.append({
                "family": fam["name"], "method": m, "alerts": k, "n": n, "rate": k / n, "ci_lo": lo, "ci_hi": hi,
                "pass_contains_5pct": bool(lo <= pol["alpha"] <= hi), "pass_upper_le_8pct": bool(hi <= 0.08),
                "above_target": bool(lo > pol["alpha"]), "gate_evaluable": bool(n >= 400),
                "abstain_frac": float(np.mean([1 - rec["outs"][m][1][t0:].mean() for rec in recs])),
                "fit_failures": len(failures),
            })
        log(f"  family {fam['name']}: done")
    df = pd.DataFrame(rows).sort_values(["family", "method"]).reset_index(drop=True)
    df.to_csv(out_dir / "table_audit_null.csv", index=False)
    return df


# ===================================================================== EVALUATE
def evaluate(
    test_dir: Path,
    model_dir: Path,
    policy_dir: Path,
    out_dir: Path,
    log=print,
    workers: int | None = 1,
    cache_dir: Path | None = None,
    resume: bool = False,
    generate_on_the_fly: bool = False,
) -> Path:
    t0_wall = time.time()
    test_dir = Path(test_dir); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    _, cfg, mh = load_models(model_dir, cache_dir=cache_dir)
    pol = load_policy(policy_dir, mh)
    items, _ = _prepare_rollout_items(test_dir, truth=True, generate_on_the_fly=generate_on_the_fly)
    truth_dir = None if generate_on_the_fly else (test_dir.parent / (test_dir.name + "_truth"))

    w = parallel.resolve_workers(workers, len(items))
    chunk_sz = max(5, min(100, len(items) // max(1, w) or 1)) if w > 1 else len(items)
    chunks = _chunked(items, chunk_sz)
    tasks = [{
        "mode": "evaluate",
        "chunk_idx": ci,
        "items": ch,
        "model_dir": str(model_dir),
        "cache_dir": str(cache_dir) if cache_dir is not None else None,
        "methods": cfg["methods"],
        "pol": pol,
        "truth_dir": str(truth_dir) if truth_dir is not None else None,
    } for ci, ch in enumerate(chunks)]
    chunk_outs = _run_chunked_with_resume(
        tasks, workers=w, resume_dir=out_dir if resume else None, journal_name="evaluate", desc="evaluate", log=log
    )

    rows, hostrows, flick, rt, calib, failures = [], [], [], [], [], []
    for co in chunk_outs:
        rows.extend(co["rows"]); hostrows.extend(co["hostrows"]); flick.extend(co["flick"])
        rt.extend(co["rt"]); calib.extend(co["calib"]); failures.extend(co["failures"])

    rows_df = pd.DataFrame(rows)
    if not rows_df.empty:
        rows_df = rows_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    rows_df.to_csv(out_dir / "per_rollout_metrics.csv", index=False)

    host_df = pd.DataFrame(hostrows)
    if not host_df.empty:
        host_df = host_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    host_df.to_csv(out_dir / "host_metrics.csv", index=False)

    flick_df = pd.DataFrame(flick)
    if not flick_df.empty:
        flick_df = flick_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    flick_df.to_csv(out_dir / "flicker.csv", index=False)

    rt_df = pd.DataFrame(rt)
    if not rt_df.empty:
        rt_df = rt_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    rt_df.to_csv(out_dir / "runtime.csv", index=False)

    calib_raw = pd.DataFrame(calib, columns=["rollout_id", "method", "bin", "n", "sum_p", "sum_j"])
    if not calib_raw.empty:
        import math
        calib_raw = calib_raw.sort_values(["method", "bin", "rollout_id"])
        agg = []
        for (m, b), grp in calib_raw.groupby(["method", "bin"], sort=True):
            agg.append({
                "method": m,
                "bin": int(b),
                "n": int(grp["n"].sum()),
                "sum_p": math.fsum(grp["sum_p"].tolist()),
                "sum_j": math.fsum(grp["sum_j"].tolist()),
            })
        calib_df = pd.DataFrame(agg).sort_values(["method", "bin"]).reset_index(drop=True)
    else:
        calib_df = pd.DataFrame(columns=["method", "bin", "n", "sum_p", "sum_j"])
    calib_df.to_csv(out_dir / "calibration_bins.csv", index=False)

    fail_df = pd.DataFrame(failures, columns=["rollout_id", "method", "params", "error"])
    if not fail_df.empty:
        fail_df = fail_df.sort_values(["rollout_id", "method"]).reset_index(drop=True)
    fail_df.to_csv(out_dir / "fit_failures.csv", index=False)

    wall_s = round(time.time() - t0_wall, 3)
    write_manifest(out_dir, model_dir, policy_dir, test_dir, cfg, pol, len(failures), wall_s=wall_s)
    return out_dir


def write_manifest(out_dir, model_dir, policy_dir, test_dir, cfg, pol, n_fail, wall_s: float | None = None):
    test_man = json.loads((Path(test_dir) / "manifest.json").read_text(encoding="utf-8"))
    wall_times = dict(cfg.get("wall_times", {}))
    if pol.get("wall_time_s") is not None:
        wall_times["calibrate_s"] = pol["wall_time_s"]
    if wall_s is not None:
        wall_times["evaluate_s"] = wall_s
    man = man_mod.build_manifest(
        out_dir=out_dir,
        config=test_man.get("config") or cfg.get("config"),
        config_hash=test_man.get("config_hash") or cfg.get("config_hash"),
        regime=pol.get("regime") or test_man.get("regime") or cfg.get("regime"),
        beta_mode=cfg.get("beta_mode"),
        noise_mode=cfg.get("noise_mode", "ar_only"),
        factor_rank=cfg.get("factor_rank", 1),
        grid_file=cfg.get("grid_file"),
        grid_hash=cfg.get("grid_hash"),
        candidate_table_hash=cfg.get("candidate_table_hash"),
        selected=cfg.get("selected"),
        edge_flags=cfg.get("edge_flags"),
        seed_ranges={
            "dev": cfg.get("seed_ranges"),
            "calibration": pol.get("seed_ranges"),
            "test": test_man.get("seed_ranges"),
        },
        wall_times=wall_times,
        fit_failures=n_fail,
        fit_failures_test=n_fail,
        model_hash=pol["model_hash"],
        policy_hash=pol["calib_hash"],
        calib_hash=pol["calib_hash"],
        alpha=pol["alpha"],
        thresholds={m: c["threshold"] for m, c in pol["thresholds"].items()},
        test_manifest=test_man,
        model_dir=str(model_dir),
        policy_dir=str(policy_dir),
    )
    (Path(out_dir) / "experiment_manifest.json").write_text(json.dumps(man, indent=1, default=str), encoding="utf-8")


# ===================================================================== runtime benchmark
def benchmark(nuis_dir: Path | None, sizes=(10, 50, 100), reps: int = 3, out: Path = Path("results/runtime_scaling.csv")):
    rows = []
    for nc in sizes:
        cfg = SimConfig(n_canary=nc, n_hosts=nc + 90, n_affected=min(3, nc))
        healthy = [simulate(cfg, seeds.seed_for("study_X", s, 0), False)[0] for s in range(12)]
        nuis = fit_nuisance(healthy)
        for kind in ("hier", "indep"):
            ts = []
            for s in range(reps):
                roll, _ = simulate(cfg, seeds.seed_for("study_X", s, 1), True)
                a = adjust_roll(roll, nuis)
                ts.append(EffectDetector(nuis, EffectParams(kind=kind)).run(a).update_times_ms)
            ts = np.concatenate(ts)
            rows.append({"n_canaries": nc, "model": kind, "median_ms": np.median(ts), "p95_ms": np.quantile(ts, .95),
                         "p99_ms": np.quantile(ts, .99), "machine": platform.processor() or platform.machine()})
    df = pd.DataFrame(rows); Path(out).parent.mkdir(parents=True, exist_ok=True); df.to_csv(out, index=False)
    return df
