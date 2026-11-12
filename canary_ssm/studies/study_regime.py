"""Causal Workload Regime Rule study (ported from Experiment 7; WP-A5, WP-A6)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import decision as dec
from .. import manifest as man_mod
from .. import metrics as M
from .. import parallel, seeds
from ..experiments import load_models, run_methods
from ..simulate import SimConfig, simulate
from . import require_tuned, write_summary_md


METHODS_DEFAULT = ["matched_contrast", "adj_cusum", "topk_cusum", "hier_ssm"]


def causal_regime_selector(x: np.ndarray, t0: int, thr: float = 0.17) -> str:
    """Selects regime causally from measured workload covariate x only (no truth, no latency)."""
    pre = float(np.mean(x[max(0, t0 - 5):t0]))
    post = float(np.mean(x[t0:min(len(x), t0 + 5)]))
    return "step" if (post - pre) > thr else "plain"


def _score_regime_chunk(task: dict) -> list[dict]:
    models, _, _ = load_models(Path(task["model_dir"]))
    methods = task["methods"]
    recs = []
    for item in task["items"]:
        sc = SimConfig.from_dict(item["sim_cfg"])
        roll, truth = simulate(sc, int(item["seed"]), bool(item["harm"]), item["rollout_id"], pair_id=int(item["pair_id"]))
        outs = run_methods(models, roll, methods, [])
        pred_reg = causal_regime_selector(roll.x, roll.t0)
        entry: dict[str, Any] = {
            "rollout_id": roll.rollout_id,
            "pair_id": int(item["pair_id"]),
            "t0": int(roll.t0),
            "T": int(roll.T),
            "pred_regime": pred_reg,
            "maxima": {m: dec.release_max(outs[m].score, outs[m].elig, roll.t0) for m in methods},
        }
        if item["store_scores"]:
            entry["outs"] = {m: (outs[m].score, outs[m].elig) for m in methods}
        if item["harm"]:
            entry["ev"] = M.event_truth(truth, len(roll.canary_idx))
        recs.append(entry)
    return recs


def _run_batch(
    model_dir: Path,
    sc: SimConfig,
    base_seed: int | None,
    seed_purpose: str,
    family_idx: int,
    n: int,
    harm: bool,
    methods: list[str],
    workers: int | None,
    store_scores: bool = True,
    desc: str = "study_regime",
) -> list[dict]:
    sc_dict = asdict(sc)
    items = []
    for i in range(n):
        seed = (base_seed + i) if base_seed is not None else seeds.seed_for(seed_purpose, i, family_idx)
        items.append({
            "rollout_id": f"sr_{family_idx}_{seed}_{'h' if harm else 'n'}",
            "seed": int(seed),
            "pair_id": int(i),
            "harm": bool(harm),
            "sim_cfg": sc_dict,
            "store_scores": bool(store_scores),
        })
    w = parallel.resolve_workers(workers, len(items))
    chunks = [items[i:i + max(10, len(items) // max(1, w))] for i in range(0, len(items), max(10, len(items) // max(1, w)))]
    tasks = [{"model_dir": str(model_dir), "methods": methods, "items": ch} for ch in chunks]
    out_chunks = parallel.pmap(_score_regime_chunk, tasks, workers=w, desc=desc)
    flat = [r for ch in out_chunks for r in ch]
    flat.sort(key=lambda r: r["pair_id"])
    return flat


def run(
    model_dir: Path | str = Path("artifacts/model"),
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/study_regime"),
    n_null: int = 500,
    n_harm: int = 200,
    seed_purpose: str = "study_regime",
    allow_frozen: bool = False,
    legacy_seeds: bool = False,
    workers: int | None = 1,
    methods: list[str] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Run the dual-regime calibration & power study using DetectorOutput.elig everywhere."""
    t0_wall = time.time()
    model_dir = Path(model_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _, mcfg, mh = load_models(model_dir)
    require_tuned(mcfg, allow_frozen=allow_frozen)
    meths = list(methods or [m for m in METHODS_DEFAULT if m in mcfg["methods"]])

    cfg_plain = SimConfig(sd_host=0.02, workload_step=0.0)
    cfg_step = SimConfig(sd_host=0.02, workload_step=0.3365)
    cfg_s1_plain = SimConfig(sd_host=0.02, n_affected=3, effect_pct=3.0, duration=45, workload_step=0.0)
    cfg_s1_step = SimConfig(sd_host=0.02, n_affected=3, effect_pct=3.0, duration=45, workload_step=0.3365)

    leg = seeds.LEGACY["v1_experiment_7"] if legacy_seeds else [None] * 6

    cal_plain = _run_batch(model_dir, cfg_plain, leg[0], seed_purpose, 0, n_null, False, meths, workers, store_scores=False, desc="cal_plain")
    cal_step = _run_batch(model_dir, cfg_step, leg[1], seed_purpose, 1, n_null, False, meths, workers, store_scores=False, desc="cal_step")

    plain_maxima = {m: np.array([r["maxima"][m] for r in cal_plain], float) for m in meths}
    step_maxima = {m: np.array([r["maxima"][m] for r in cal_step], float) for m in meths}

    cal_plain_info = {m: dec.calibrate_threshold(plain_maxima[m], 0.05) for m in meths}
    cal_step_info = {m: dec.calibrate_threshold(step_maxima[m], 0.05) for m in meths}
    thr_plain = {m: cal_plain_info[m]["threshold"] for m in meths}
    thr_step = {m: cal_step_info[m]["threshold"] for m in meths}

    n_p_mix = int(0.85 * n_null)
    n_s_mix = int(0.15 * n_null)
    mix_maxima = {
        m: np.concatenate([
            np.random.default_rng(42).choice(plain_maxima[m], size=n_p_mix, replace=False),
            np.random.default_rng(43).choice(step_maxima[m], size=n_s_mix, replace=False),
        ])
        for m in meths
    }
    cal_mix_info = {m: dec.calibrate_threshold(mix_maxima[m], 0.05) for m in meths}
    thr_single = {m: cal_mix_info[m]["threshold"] for m in meths}

    null_eval_rows = []
    conf_rows = []
    for r_idx, (reg_name, sc, base_s) in enumerate([("plain", cfg_plain, leg[2]), ("step", cfg_step, leg[3])]):
        val_recs = _run_batch(model_dir, sc, base_s, seed_purpose, 2 + r_idx, n_null, False, meths, workers, store_scores=True, desc=f"val_{reg_name}")
        preds = [r["pred_regime"] for r in val_recs]
        for pred_name in ("plain", "step"):
            cnt = int(sum(p == pred_name for p in preds))
            conf_rows.append({"true_regime": reg_name, "selected_regime": pred_name, "count": cnt, "rate": cnt / len(preds)})
        for m in meths:
            kd = 0
            ks = 0
            for rec in val_recs:
                sc_arr, elig = rec["outs"][m]
                t_used = thr_step[m] if rec["pred_regime"] == "step" else thr_plain[m]
                if dec.first_alarm(sc_arr, elig, t_used, rec["t0"]) is not None:
                    kd += 1
                if dec.first_alarm(sc_arr, elig, thr_single[m], rec["t0"]) is not None:
                    ks += 1
            lod, hid = M.clopper_pearson(kd, len(val_recs))
            los, his = M.clopper_pearson(ks, len(val_recs))
            c_ref = cal_step_info[m] if reg_name == "step" else cal_plain_info[m]
            bbd = M.betabinom_validity(kd, len(val_recs), c_ref["B"], c_ref["k"])
            bbs = M.betabinom_validity(ks, len(val_recs), cal_mix_info[m]["B"], cal_mix_info[m]["k"])
            null_eval_rows.append({
                "true_regime": reg_name, "method": m, "policy": "causal_dual_regime",
                "alerts": kd, "n": len(val_recs), "rate": kd / len(val_recs), "ci_lo": lod, "ci_hi": hid,
                "expected_alerts": bbd["expected_alerts"], "bb_sd": bbd["bb_sd"],
                "bb_pvalue_two_sided": bbd["bb_pvalue_two_sided"],
                "pass_upper_le_8pct": bool(hid <= 0.08), "pass_contains_5pct": bool(lod <= 0.05 <= hid),
            })
            null_eval_rows.append({
                "true_regime": reg_name, "method": m, "policy": "single_threshold",
                "alerts": ks, "n": len(val_recs), "rate": ks / len(val_recs), "ci_lo": los, "ci_hi": his,
                "expected_alerts": bbs["expected_alerts"], "bb_sd": bbs["bb_sd"],
                "bb_pvalue_two_sided": bbs["bb_pvalue_two_sided"],
                "pass_upper_le_8pct": bool(his <= 0.08), "pass_contains_5pct": bool(los <= 0.05 <= his),
            })

    df_null = pd.DataFrame(null_eval_rows)
    df_conf = pd.DataFrame(conf_rows)
    df_null.to_csv(out_dir / "table_regime_null_rates.csv", index=False)
    df_conf.to_csv(out_dir / "table_regime_confusion.csv", index=False)

    power_rows = []
    if n_harm > 0:
        for h_idx, (scen_name, sc, base_s) in enumerate([("S1_plain", cfg_s1_plain, leg[4]), ("S1_step", cfg_s1_step, leg[5])]):
            harm_recs = _run_batch(model_dir, sc, base_s, seed_purpose, 4 + h_idx, n_harm, True, meths, workers, store_scores=True, desc=scen_name)
            for rec in harm_recs:
                ev = rec["ev"]
                if not ev["has_event"]:
                    continue
                for m in meths:
                    sc_arr, elig = rec["outs"][m]
                    t_used = thr_step[m] if rec["pred_regime"] == "step" else thr_plain[m]
                    c_dual = M.classify(dec.first_alarm(sc_arr, elig, t_used, rec["t0"]), ev, rec["T"])
                    c_sing = M.classify(dec.first_alarm(sc_arr, elig, thr_single[m], rec["t0"]), ev, rec["T"])
                    power_rows.append({
                        "scenario": scen_name, "rollout_id": rec["rollout_id"], "method": m,
                        "pred_regime": rec["pred_regime"],
                        "success_dual": c_dual["status"] == "success", "capped_dual": c_dual["capped"], "delay_dual": c_dual["delay"],
                        "success_single": c_sing["status"] == "success", "capped_single": c_sing["capped"], "delay_single": c_sing["delay"],
                    })

    df_power = pd.DataFrame(power_rows)
    df_power.to_csv(out_dir / "table_power_rollouts.csv", index=False)

    summary_rows = []
    if not df_power.empty:
        for (scen, m), g in df_power.groupby(["scenario", "method"]):
            diff = g["capped_dual"] - g["capped_single"]
            m_diff, lo_diff, hi_diff = M.paired_bootstrap(diff.to_numpy())
            summary_rows.append({
                "scenario": scen, "method": m, "n": len(g),
                "detection_rate_dual": float(g["success_dual"].mean()),
                "mean_capped_dual": float(g["capped_dual"].mean()),
                "detection_rate_single": float(g["success_single"].mean()),
                "mean_capped_single": float(g["capped_single"].mean()),
                "mean_capped_diff_dual_minus_single": m_diff,
                "ci_lo": lo_diff, "ci_hi": hi_diff,
            })
    df_summary = pd.DataFrame(summary_rows)
    df_summary.to_csv(out_dir / "table_power_summary.csv", index=False)

    sections = [
        ("Regime Selector Confusion Matrix", df_conf.round(4).to_markdown(index=False)),
        ("Null False-Alert Rates", df_null.round(4).to_markdown(index=False)),
    ]
    if not df_summary.empty:
        sections.append(("Power & Capped-Time Comparison", df_summary.round(4).to_markdown(index=False)))
    write_summary_md(out_dir / "report.md", "Study: Causal Workload Regime Rule", sections)

    manifest = man_mod.build_manifest(
        out_dir=out_dir,
        study="regime",
        model_dir=str(model_dir),
        model_hash=mh,
        allow_frozen=bool(allow_frozen),
        legacy_seeds=bool(legacy_seeds),
        seed_purpose=seed_purpose,
        n_null=int(n_null),
        n_harm=int(n_harm),
        wall_times={"study_regime_s": round(time.time() - t0_wall, 3)},
    )
    (out_dir / "experiment_manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return manifest
