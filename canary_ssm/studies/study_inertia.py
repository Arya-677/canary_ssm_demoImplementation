"""V3 study: does hierarchical inertia add value beyond ordinary persistence and decision hysteresis?

Addendum B1-B3 / J1. Three mechanisms are kept SEPARATE and crossed in one design:

  M1 latent persistence           : indep_ssm / hier_ssm (equal-rho AR effect states, already tuned in model_v2)
  M2 cross-level (two-scale) inertia: hier_ts (group and local levels get different rho, innovation and prior scales)
  M3 decision-level inertia       : pause only after m consecutive eligible minutes above threshold, m in persist_m
                                    (calibrated EXACTLY via the running-minimum score, decision.persist_score)

Classical comparators (adj_cusum, glr_window) get the same m grid and the same calibration. Every (method, m, regime)
cell has its OWN order-statistic threshold from `n_null` calibration nulls (seed block study_inertia_cal) and is audited
on separate validation nulls (study_inertia_val) with the exact Beta-Binomial test. Scenarios are evaluated on
study_inertia_eval seeds. No detector code sees truth; truth is used only here (evaluator side).

Outputs (all CSV/JSON; report.md is generated from them):
  hier_ts_selection.csv, hier_ts_params.json   development-set tuning of hier_ts (if tuned here)
  table_calibration_validity.csv               per regime x method x m: threshold, FAR on validation nulls, bb_p
  per_rollout_policy.csv                       one row per rollout x method x m (the audit trail)
  table_scenario_summary.csv                   power / misses / premature / capped time / stability per scenario
  table_paired_contrasts.csv                   paired capped-time differences with sign-flip p and Holm adjustment
  table_runtime.csv                            mean per-update milliseconds per method
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .. import decision as dec
from .. import experiments as E
from .. import manifest as man_mod
from .. import metrics as M
from .. import parallel, seeds
from ..inertia import load_inertia_grid, ts_candidates
from ..simulate import SimConfig, simulate
from . import require_tuned, write_summary_md

REPO = Path(__file__).resolve().parents[2]
DEFAULT_METHODS = ["indep_ssm", "hier_ssm", "hier_ts", "adj_cusum", "glr_window"]
DEFAULT_M = (1, 3, 5, 10, 15)
REGIME_CFG = {"plain": REPO / "configs" / "plain_main.yaml", "step": REPO / "configs" / "step_regime.yaml"}
DEFAULT_SCENARIOS = REPO / "configs" / "inertia_scenarios.yaml"
NORMAL = dec.NORMAL


# ----------------------------------------------------------------------------------------- helpers
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False)
    except ImportError:                                   # tabulate is an optional extra
        return df.to_string(index=False)


def _chunks(items: list, workers: int) -> list[list]:
    size = max(10, len(items) // max(1, workers))
    return [items[i:i + size] for i in range(0, len(items), size)]


def _slim_event(ev: dict) -> dict:
    return {"has_event": bool(ev["has_event"]), "onset": ev["onset"], "transient": bool(ev["transient"]),
            "intervals": [(int(h), int(s), int(e)) for h, s, e in ev["intervals"]]}


def holm_adjust(p: np.ndarray) -> np.ndarray:
    """Holm step-down adjusted p-values (monotone, capped at 1)."""
    p = np.asarray(p, float); n = len(p); order = np.argsort(p); adj = np.empty(n); run = 0.0
    for rank, idx in enumerate(order):
        run = max(run, (n - rank) * p[idx]); adj[idx] = min(1.0, run)
    return adj


def sign_flip_pvalue(d: np.ndarray, n_perm: int = 5000, seed: int = 0) -> float:
    """Two-sided paired sign-flip permutation p-value for H0: mean difference = 0 (resampling over ROLLOUTS)."""
    d = np.asarray(d, float); d = d[np.isfinite(d)]
    if d.size == 0 or np.allclose(d, 0):
        return 1.0
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1.0, 1.0], size=(n_perm, d.size))
    stat = np.abs((flips * d).mean(1))
    return float((1 + np.sum(stat >= abs(d.mean()) - 1e-15)) / (n_perm + 1))


# ----------------------------------------------------------------------------------------- scoring worker
def _score_chunk(task: dict) -> list[dict]:
    models, _, _ = E.load_models(Path(task["model_dir"]))
    methods, params = task["methods"], task["params"]
    recs = []
    for it in task["items"]:
        sc = SimConfig.from_dict(it["sim_cfg"])
        roll, truth = simulate(sc, int(it["seed"]), bool(it["harm"]), it["rollout_id"], pair_id=int(it["pair_id"]))
        cache: dict = {}; fails: list = []; outs = {}; rt = {}
        for m in methods:
            o = E._safe_run(models, roll, m, params[m], cache, fails)
            outs[m] = (o.score, o.elig); rt[m] = float(o.runtime_ms)
        rec = {"role": it["role"], "scenario": it["scenario"], "regime": it["regime"], "rollout_id": roll.rollout_id,
               "pair_id": int(it["pair_id"]), "harm": bool(it["harm"]), "t0": int(roll.t0), "T": int(roll.T),
               "outs": outs, "runtime_ms": rt, "n_fail": len(fails)}
        rec["ev"] = _slim_event(M.event_truth(truth, len(roll.canary_idx))) if it["harm"] else \
            {"has_event": False, "onset": None, "transient": False, "intervals": []}
        recs.append(rec)
    return recs


def _score(model_dir: Path, items: list[dict], methods: list[str], params: dict, workers: int | None, desc: str) -> list[dict]:
    w = parallel.resolve_workers(workers, len(items))
    tasks = [{"model_dir": str(model_dir), "methods": methods, "params": params, "items": ch} for ch in _chunks(items, w)]
    out = parallel.pmap(_score_chunk, tasks, workers=w, desc=desc)
    return [r for ch in out for r in ch]


# ----------------------------------------------------------------------------------------- hier_ts tuning (DEV ONLY)
def tune_hier_ts(model_dir: Path, dev_dir: Path, out_dir: Path, workers: int | None = 1, k_folds: int = 5,
                 min_dev_nulls: int = 200, grid_path: Path | None = None, cache_dir: Path | None = None,
                 log=print) -> dict:
    """Select hier_ts hyperparameters by the SAME 5-fold CV + 1-SE protocol used for every other method, on the SAME
    development role (nuisance parameters come from the shipped model; nothing is read from calibration/validation/test)."""
    model_dir, dev_dir, out_dir = Path(model_dir), Path(dev_dir), Path(out_dir)
    if not (dev_dir / "manifest.json").exists():
        raise FileNotFoundError(
            f"dev data not found at {dev_dir}. Generate it first: python -m canary_ssm.cli simulate "
            f"--config configs/plain_main.yaml --role dev --out {dev_dir}")
    models, mcfg, _ = E.load_models(model_dir, cache_dir=cache_dir)
    grids = load_inertia_grid(grid_path)
    cands = ts_candidates(grids)
    hier_budget = len(E.candidate_grid("hier_ssm", E.load_grids()))
    if len(cands) > hier_budget:
        raise ValueError(f"budget parity violated: hier_ts has {len(cands)} candidates > hier_ssm {hier_budget}")
    dev = E.load_role(dev_dir)
    failures: list = []
    best, rows = E.select_on_dev(models, dev, "hier_ts", cands, failures, log, workers=workers, dev_dir=dev_dir,
                                 cache_dir=cache_dir, k_folds=k_folds, min_dev_nulls=min_dev_nulls)
    argmin = min(rows, key=lambda r: r["dev_capped_time"])
    axes = {k: sorted({float(c[k]) for c in cands}) for k in ("rho_g", "rho_h", "sd_g", "sd_h_ratio", "prior_h_ratio")}
    edges = {k: bool(len(v) > 1 and (float(best[k]) in (v[0], v[-1]))) for k, v in axes.items()}
    res = {"grid_version": grids.get("version"), "n_candidates": len(cands), "hier_ssm_budget": hier_budget,
           "selected": best, "argmin": json.loads(argmin["params"]), "dev_capped_time_selected":
           float(next(r["dev_capped_time"] for r in rows if r.get("is_selected"))), "edge_flags": edges,
           "n_fit_failures": len(failures), "dev_dir": str(dev_dir)}
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_dir / "hier_ts_selection.csv", index=False)
    (out_dir / "hier_ts_params.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


# ----------------------------------------------------------------------------------------- main study
def _load_scenarios(path: Path | None, only: list[str] | None) -> tuple[dict, list[dict]]:
    y = yaml.safe_load(Path(path or DEFAULT_SCENARIOS).read_text(encoding="utf-8-sig"))
    scen = y["scenarios"]
    if only:
        scen = [s for s in scen if s["name"] in set(only)]
        if not scen:
            raise ValueError(f"no scenario matches {only}")
    return y, scen


def run(
    model_dir: Path | str = Path("artifacts/model_v2"),
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/study_inertia"),
    n_null: int = 2000,
    n_harm: int = 300,
    seed_purpose: str | None = None,
    allow_frozen: bool = False,
    legacy_seeds: bool = False,
    workers: int | None = 1,
    methods: list[str] | None = None,
    persist_m: tuple[int, ...] | list[int] = DEFAULT_M,
    dev_dir: Path | str = Path("data/plain/dev"),
    tune: bool = True,
    ts_params: dict | str | Path | None = None,
    scenario_file: Path | str | None = None,
    only_scenarios: list[str] | None = None,
    n_val: int | None = None,
    alpha: float = 0.05,
    n_clear: int = 5,
    hyst_frac: float = 0.5,
    emergency_offset: float | None = None,
    k_folds: int = 5,
    min_dev_nulls: int = 200,
    cache_dir: Path | str | None = None,
    **kwargs,
) -> dict[str, Any]:
    t_wall = time.time()
    model_dir, out_dir = Path(model_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _, mcfg, mh = E.load_models(model_dir)
    require_tuned(mcfg, allow_frozen=allow_frozen)
    meths = list(methods or DEFAULT_METHODS)
    ms = sorted({int(m) for m in persist_m} | {1})
    n_val = int(n_val if n_val is not None else n_null)
    n_eval = int(n_harm)
    ycfg, scenarios = _load_scenarios(scenario_file, only_scenarios)
    base = ycfg.get("base", {})
    regimes = sorted({s["regime"] for s in scenarios})

    # ---- method parameters: tuned (dev) values from the model; hier_ts from its own dev tuning ----
    params: dict[str, dict] = {}
    for m in meths:
        if m == "hier_ts":
            continue
        if m not in mcfg["selected"]:
            raise KeyError(f"method {m!r} has no tuned parameters in {model_dir / 'model_config.json'}")
        params[m] = mcfg["selected"][m]["params"]
    ts_info: dict = {}
    if "hier_ts" in meths:
        if ts_params is not None:
            ts_info = json.loads(Path(ts_params).read_text()) if isinstance(ts_params, (str, Path)) else dict(ts_params)
            ts_info = ts_info.get("selected", ts_info)
            params["hier_ts"] = ts_info
        elif tune:
            ts_res = tune_hier_ts(model_dir, Path(dev_dir), out_dir, workers=workers, k_folds=k_folds,
                                  min_dev_nulls=min_dev_nulls, cache_dir=cache_dir)
            params["hier_ts"] = ts_res["selected"]; ts_info = ts_res
        else:
            raise ValueError("hier_ts requested but neither ts_params nor tune=True was provided")

    # ---- calibration + validation nulls from each regime's own mixture ----
    cal_items, val_items = [], []
    for ri, reg in enumerate(regimes):
        cfg = E.load_config(REGIME_CFG[reg])
        for i in range(n_null):
            for role, bucket, purpose, n in (("cal", cal_items, "study_inertia_cal", n_null),
                                             ("val", val_items, "study_inertia_val", n_val)):
                if i >= n:
                    continue
                seed = seeds.seed_for(purpose, i, ri)
                fam = E._family_for(cfg, seed)
                bucket.append({"role": role, "scenario": f"mixture_{reg}", "regime": reg, "seed": int(seed), "harm": False,
                               "pair_id": int(i), "rollout_id": f"{role}_{reg}_{seed}",
                               "sim_cfg": asdict(E.make_sim_cfg(cfg, fam))})
    cal = _score(model_dir, cal_items, meths, params, workers, "inertia:cal")
    val = _score(model_dir, val_items, meths, params, workers, "inertia:val")

    # ---- per (regime, method, m) policies: exact order-statistic calibration of the persistence score ----
    policies: dict[tuple, dict] = {}
    for reg in regimes:
        recs = [r for r in cal if r["regime"] == reg]
        t0 = recs[0]["t0"]
        for m in meths:
            for mm in ms:
                policies[(reg, m, mm)] = dec.calibrate_persistence(
                    [r["outs"][m][0] for r in recs], [r["outs"][m][1] for r in recs], t0, mm, alpha, n_clear,
                    hyst_frac, emergency_offset)

    vrows = []
    for (reg, m, mm), pol in policies.items():
        recs = [r for r in val if r["regime"] == reg]
        k = 0
        for r in recs:
            s, v = dec.persist_score(r["outs"][m][0], r["outs"][m][1], r["t0"], mm, emergency_offset)
            k += int(dec.first_alarm(s, v, pol["h_on"], r["t0"]) is not None)
        n = len(recs); lo, hi = M.clopper_pearson(k, n)
        row = {"regime": reg, "method": m, "m_on": mm, "B": pol["base"]["B"], "k_order": pol["base"]["k"],
               "h_on": pol["h_on"], "h_off": pol["h_off"], "alerts": k, "n_val": n, "far": k / n, "ci_lo": lo, "ci_hi": hi}
        if np.isfinite(pol["h_on"]):
            bb = M.betabinom_validity(k, n, pol["base"]["B"], pol["base"]["k"])
            row.update(expected_alerts=bb["expected_alerts"], bb_pvalue_two_sided=bb["bb_pvalue_two_sided"])
        row["gate_evaluable"] = bool(n >= 2000)
        vrows.append(row)
    df_val = pd.DataFrame(vrows)
    df_val.to_csv(out_dir / "table_calibration_validity.csv", index=False)

    # ---- scenario evaluation (paired null + harm rollouts, same seeds) ----
    eval_items = []
    for si, sc in enumerate(scenarios):
        d = {**base, **sc["overrides"], "family": sc["name"]}
        for i in range(n_eval):
            seed = seeds.seed_for("study_inertia_eval", i, si)
            for harm in (False, True):
                eval_items.append({"role": "eval", "scenario": sc["name"], "regime": sc["regime"], "seed": int(seed),
                                   "harm": harm, "pair_id": int(i), "rollout_id": f"ev{si}_{seed}_{'h' if harm else 'n'}",
                                   "sim_cfg": asdict(SimConfig.from_dict(d))})
    ev_recs = _score(model_dir, eval_items, meths, params, workers, "inertia:eval")

    rows = []
    for r in ev_recs:
        ev, t0, T = r["ev"], r["t0"], r["T"]
        t_rec = max((e for _, _, e in ev["intervals"]), default=None) if ev["has_event"] else None
        for m in meths:
            sc_arr, el = r["outs"][m]
            for mm in ms:
                pol = policies[(r["regime"], m, mm)]
                s, v = dec.persist_score(sc_arr, el, t0, mm, emergency_offset)
                t_alarm = dec.first_alarm(s, v, pol["h_on"], t0)
                cl = M.classify(t_alarm, ev, T)
                rp = dec.replay_policy(sc_arr, el, t0, pol["h_on"], pol["h_off"], mm, n_clear, emergency_offset)
                rec_delay = np.nan
                if t_rec is not None and t_rec < T and rp["states"][t_rec] == dec.PAUSE:
                    back = np.flatnonzero(rp["states"][t_rec:] == NORMAL)
                    rec_delay = float(back[0]) if back.size else float(T - t_rec)
                rows.append({"scenario": r["scenario"], "regime": r["regime"], "rollout_id": r["rollout_id"],
                             "pair_id": r["pair_id"], "is_harm_rollout": r["harm"], "has_event": ev["has_event"],
                             "kind": cl["kind"], "method": m, "m_on": mm, "status": cl["status"], "alarm": t_alarm is not None,
                             "delay": cl["delay"], "capped": cl["capped"], "first_pause": rp["first_pause"],
                             "reversals": rp["reversals"], "time_paused": rp["time_paused"],
                             "pause_episodes": rp["pause_episodes"], "recovery_delay": rec_delay})
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "per_rollout_policy.csv", index=False)

    # ---- summaries ----
    srows = []
    for (scn, m, mm), g in df.groupby(["scenario", "method", "m_on"]):
        nul = g[~g["is_harm_rollout"]]; har = g[g["is_harm_rollout"]]; evt = har[har["has_event"]]
        row = {"scenario": scn, "method": m, "m_on": mm, "n_pairs": int(len(nul)),
               "null_alert_rate": float(nul["alarm"].mean()),
               "harm_rollout_noevent_alert_rate": float(har[~har["has_event"]]["alarm"].mean()) if (~har["has_event"]).any() else np.nan,
               "n_event": int(len(evt))}
        if len(evt):
            row.update(power=float((evt["status"] == "success").mean()), miss=float((evt["status"] == "miss").mean()),
                       premature=float((evt["status"] == "premature").mean()), mean_capped=float(evt["capped"].mean()),
                       median_delay_success=float(evt.loc[evt["status"] == "success", "delay"].median()),
                       mean_reversals=float(evt["reversals"].mean()), mean_time_paused=float(evt["time_paused"].mean()),
                       mean_recovery_delay=float(evt["recovery_delay"].mean()))
        row.update(null_mean_reversals=float(nul["reversals"].mean()), null_mean_time_paused=float(nul["time_paused"].mean()))
        srows.append(row)
    df_s = pd.DataFrame(srows); df_s.to_csv(out_dir / "table_scenario_summary.csv", index=False)

    # ---- paired contrasts (negative mean diff = first config faster) ----
    contrasts: list[tuple[str, tuple, tuple]] = []
    have = set(meths)
    for mm in ms:
        if "hier_ts" in have and "hier_ssm" in have:
            contrasts.append((f"C1_asymmetry:hier_ts-vs-hier_ssm@m{mm}", ("hier_ts", mm), ("hier_ssm", mm)))
        if "hier_ssm" in have and "indep_ssm" in have:
            contrasts.append((f"C2_pooling:hier_ssm-vs-indep_ssm@m{mm}", ("hier_ssm", mm), ("indep_ssm", mm)))
        for ref in ("adj_cusum", "glr_window"):
            for sm in ("hier_ts", "hier_ssm"):
                if sm in have and ref in have:
                    contrasts.append((f"C4_classical:{sm}-vs-{ref}@m{mm}", (sm, mm), (ref, mm)))
        if mm > 1:
            for m in meths:
                contrasts.append((f"C3_hysteresis:{m}@m{mm}-vs-m1", (m, mm), (m, 1)))
    ev_only = df[df["is_harm_rollout"] & df["has_event"]]
    crow = []
    for scn, g in ev_only.groupby("scenario"):
        piv = g.pivot_table(index="rollout_id", columns=["method", "m_on"], values="capped", aggfunc="first")
        for name, a, b in contrasts:
            if a in piv.columns and b in piv.columns:
                d = (piv[a] - piv[b]).to_numpy()
                mean, lo, hi = M.paired_bootstrap(d)
                crow.append({"scenario": scn, "contrast": name, "n": int(np.isfinite(d).sum()), "mean_capped_diff": mean,
                             "ci_lo": lo, "ci_hi": hi, "p_signflip": sign_flip_pvalue(d)})
    df_c = pd.DataFrame(crow)
    if not df_c.empty:
        df_c["p_holm"] = holm_adjust(df_c["p_signflip"].to_numpy())
    df_c.to_csv(out_dir / "table_paired_contrasts.csv", index=False)

    rt = pd.DataFrame([{"method": m, "mean_update_ms": float(np.mean([r["runtime_ms"][m] for r in ev_recs]))} for m in meths])
    rt.to_csv(out_dir / "table_runtime.csv", index=False)

    sections = [("Calibration validity (validation nulls, exact Beta-Binomial)", _md(df_val.round(4))),
                ("Scenario summary", _md(df_s.round(4)))]
    if not df_c.empty:
        sections.append(("Paired contrasts (negative = first config faster; Holm over all rows)", _md(df_c.round(4))))
    sections.append(("Runtime", _md(rt.round(4))))
    write_summary_md(out_dir / "report.md", "Study: inertia vs persistence vs hysteresis", sections)

    manifest = man_mod.build_manifest(
        out_dir=out_dir, study="inertia", model_dir=str(model_dir), model_hash=mh, allow_frozen=bool(allow_frozen),
        n_null=int(n_null), n_val=int(n_val), n_eval=int(n_eval), persist_m=ms, methods=meths, alpha=float(alpha),
        n_clear=int(n_clear), hyst_frac=float(hyst_frac), emergency_offset=emergency_offset,
        scenarios=[s["name"] for s in scenarios], hier_ts=ts_info,
        n_score_failures=int(sum(r["n_fail"] for r in cal + val + ev_recs)),
        wall_times={"study_inertia_s": round(time.time() - t_wall, 3)})
    (out_dir / "experiment_manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return manifest
