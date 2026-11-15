"""Tier-0 anomaly diagnosis studies X-0.2 (a), (b), (c).

Explains:
(a) why `hier_arwhite` coincides with `hier_ssm` when `meas_sd == 0`, and verifies they separate under `meas_sd == 0.01`;
(b) why Experiment 7 step-regime false alerts reached 6.8%-9.0% (selector errors, B=500 order-statistic noise, non-exchangeability/tails);
(c) why `hier_degraded` equals `hier_ssm` under selected (rho=0.99, sd_g=0.001) across label error and `sd_h_ratio`.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, kurtosis, mannwhitneyu, skew

from .. import decision as dec
from .. import manifest as man_mod
from .. import metrics as M
from .. import parallel, seeds
from ..experiments import load_models, run_methods
from ..hierarchy import EffectDetector, EffectParams, build_model, class_structure
from ..preprocess import Nuisance, adjust_roll, fit_nuisance
from ..simulate import SimConfig, simulate
from . import require_tuned, write_summary_md
from .study_regime import causal_regime_selector


# --------------------------------------------------------------------- X-0.2(a)
def run_x02a(
    model_dir: Path | str = Path("artifacts/model"),
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/x02/x02a"),
    n_null: int = 50,
    seed_purpose: str = "study_X",
    allow_frozen: bool = True,
    **kwargs,
) -> dict[str, Any]:
    t0_wall = time.time()
    model_dir = Path(model_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    models, mcfg, mh = load_models(model_dir)
    require_tuned(mcfg, allow_frozen=allow_frozen)

    def _nuis_table(nuis_a: Nuisance, nuis_b: Nuisance, world: str) -> pd.DataFrame:
        rows = []
        diag_a = {c["class"]: c["fits"] for c in nuis_a.diagnostics.get("classes", [])}
        diag_b = {c["class"]: c["fits"] for c in nuis_b.diagnostics.get("classes", [])}
        for c in range(len(nuis_a.phi_e)):
            fa = min(diag_a.get(c, [{}]), key=lambda x: x.get("nll", np.inf))
            fb = min(diag_b.get(c, [{}]), key=lambda x: x.get("nll", np.inf))
            rows.append({
                "world": world,
                "class": c,
                "main_noise": nuis_a.noise,
                "arwhite_noise": nuis_b.noise,
                "phi_main": nuis_a.phi_e[c],
                "phi_arwhite": nuis_b.phi_e[c],
                "q_main": nuis_a.q_e[c],
                "q_arwhite": nuis_b.q_e[c],
                "v_main": nuis_a.v[c],
                "v_arwhite": nuis_b.v[c],
                "abs_v_diff": abs(nuis_b.v[c] - nuis_a.v[c]),
                "boundary_hit_main": bool(fa.get("boundary_hit", False)),
                "boundary_hit_arwhite": bool(fb.get("boundary_hit", False)),
                "best_nll_main": fa.get("nll", np.nan),
                "best_nll_arwhite": fb.get("nll", np.nan),
            })
        return pd.DataFrame(rows)

    n_main = models.nuis["main"]
    n_arw = models.nuis["arwhite"]
    df_nuis0 = _nuis_table(n_main, n_arw, "meas_sd=0.0 (artifacts/model)")

    diff0_rows = []
    hp = EffectParams(**mcfg["selected"]["hier_ssm"]["params"])
    for i in range(n_null):
        harm = i >= n_null // 2
        sc = SimConfig(sd_host=0.02, n_affected=3 if harm else 0, effect_pct=3.0 if harm else 0.0, duration=45)
        r, _ = simulate(sc, seeds.seed_for(seed_purpose, i, 0), harm=harm)
        outs = run_methods(models, r, ["hier_ssm", "hier_arwhite"], [])
        s1, s2 = outs["hier_ssm"].score, outs["hier_arwhite"].score
        sl = slice(r.t0, None)
        elig = outs["hier_ssm"].elig[sl] & outs["hier_arwhite"].elig[sl]
        diff = np.abs(s1[sl][elig] - s2[sl][elig])
        diff0_rows.append({
            "world": "meas_sd=0.0",
            "rollout_id": r.rollout_id,
            "harm": harm,
            "max_abs_diff": float(np.max(diff)),
            "mean_abs_diff": float(np.mean(diff)),
            "diff_gt_1e12": bool(np.max(diff) > 1e-12),
            "diff_gt_1e6": bool(np.max(diff) > 1e-6),
        })
    df_d0 = pd.DataFrame(diff0_rows)

    # Now evaluate in a world with explicit white measurement noise meas_sd = 0.01
    dev_m01 = [
        simulate(SimConfig(sd_host=0.02, meas_sd=0.01), seeds.seed_for(seed_purpose, 1000 + i, 0), harm=False)[0]
        for i in range(40)
    ]
    nuis_m01_ar = fit_nuisance(dev_m01, factor_rank=1, noise="ar_only", beta_mode=n_main.beta_mode)
    nuis_m01_arw = fit_nuisance(dev_m01, factor_rank=1, noise="ar_white", beta_mode=n_main.beta_mode)
    df_nuis01 = _nuis_table(nuis_m01_ar, nuis_m01_arw, "meas_sd=0.01 (40 dev rollouts)")

    det_m01_ar = EffectDetector(nuis_m01_ar, hp, name="hier_ssm")
    det_m01_arw = EffectDetector(nuis_m01_arw, hp, name="hier_arwhite")
    diff01_rows = []
    for i in range(n_null):
        harm = i >= n_null // 2
        sc = SimConfig(sd_host=0.02, meas_sd=0.01, n_affected=3 if harm else 0, effect_pct=3.0 if harm else 0.0, duration=45)
        r, _ = simulate(sc, seeds.seed_for(seed_purpose, 2000 + i, 0), harm=harm)
        adj = adjust_roll(r, nuis_m01_ar)
        o1, o2 = det_m01_ar.run(adj), det_m01_arw.run(adj)
        sl = slice(r.t0, None)
        elig = o1.elig[sl] & o2.elig[sl]
        diff = np.abs(o1.score[sl][elig] - o2.score[sl][elig])
        diff01_rows.append({
            "world": "meas_sd=0.01",
            "rollout_id": r.rollout_id,
            "harm": harm,
            "max_abs_diff": float(np.max(diff)),
            "mean_abs_diff": float(np.mean(diff)),
            "diff_gt_1e12": bool(np.max(diff) > 1e-12),
            "diff_gt_1e6": bool(np.max(diff) > 1e-6),
        })
    df_d01 = pd.DataFrame(diff01_rows)

    df_nuis_all = pd.concat([df_nuis0, df_nuis01], ignore_index=True)
    df_diff_all = pd.concat([df_d0, df_d01], ignore_index=True)
    df_summary = df_diff_all.groupby("world").agg(
        rollouts=("rollout_id", "count"),
        max_abs_diff_median=("max_abs_diff", "median"),
        max_abs_diff_max=("max_abs_diff", "max"),
        frac_gt_1e12=("diff_gt_1e12", "mean"),
        frac_gt_1e6=("diff_gt_1e6", "mean"),
    ).reset_index()

    df_nuis_all.to_csv(out_dir / "x02a_nuisance_comparison.csv", index=False)
    df_diff_all.to_csv(out_dir / "x02a_score_diffs.csv", index=False)
    df_summary.to_csv(out_dir / "x02a_summary.csv", index=False)

    write_summary_md(
        out_dir / "x02a_summary.md",
        "X-0.2(a) Diagnosis: hier_arwhite vs hier_ssm",
        [
            ("Nuisance Parameter Comparison", df_nuis_all.round(6).to_markdown(index=False)),
            ("Score Difference Summary Across 50 Rollouts", df_summary.round(6).to_markdown(index=False)),
        ],
    )
    return {"study": "x02a", "out_dir": str(out_dir), "wall_s": round(time.time() - t0_wall, 3)}


# --------------------------------------------------------------------- X-0.2(b)
def _score_x02b_chunk(task: dict) -> list[dict]:
    models, _, _ = load_models(Path(task["model_dir"]))
    methods = task["methods"]
    recs = []
    for it in task["items"]:
        sc = SimConfig.from_dict(it["sim_cfg"])
        r, _ = simulate(sc, int(it["seed"]), False, it["rollout_id"], pair_id=int(it["idx"]))
        outs = run_methods(models, r, methods, [])
        recs.append({
            "idx": int(it["idx"]),
            "pred_regime": causal_regime_selector(r.x, r.t0),
            "t0": int(r.t0),
            "maxima": {m: dec.release_max(outs[m].score, outs[m].elig, r.t0) for m in methods},
        })
    return recs


def _sim_and_score_x02b(
    model_dir: Path,
    sc: SimConfig,
    seed_purpose: str,
    family_idx: int,
    n: int,
    methods: list[str],
    workers: int | None,
    desc: str,
) -> list[dict]:
    sc_d = asdict(sc)
    items = [
        {"idx": i, "seed": seeds.seed_for(seed_purpose, i, family_idx), "rollout_id": f"x02b_{family_idx}_{i}", "sim_cfg": sc_d}
        for i in range(n)
    ]
    w = parallel.resolve_workers(workers, len(items))
    ch_sz = max(20, len(items) // max(1, w))
    tasks = [{"model_dir": str(model_dir), "methods": methods, "items": items[i:i + ch_sz]} for i in range(0, len(items), ch_sz)]
    res = parallel.pmap(_score_x02b_chunk, tasks, workers=w, desc=desc)
    flat = [r for ch in res for r in ch]
    flat.sort(key=lambda r: r["idx"])
    return flat


def _hill_tail_stats(vals: np.ndarray, regime: str, method: str, split: str) -> list[dict]:
    x = np.sort(vals[np.isfinite(vals)])
    n = len(x)
    rows = []
    q95, q99, q50 = float(np.quantile(x, 0.95)), float(np.quantile(x, 0.99)), float(np.quantile(x, 0.50))
    skew_v = float(skew(x))
    kurt_v = float(kurtosis(x, fisher=True))
    for frac in (0.01, 0.025, 0.05, 0.10):
        k = max(5, int(round(frac * n)))
        if k >= n:
            continue
        top = x[n - k:]
        ref = x[n - k - 1]
        pos_ratio = np.log(np.maximum(top, 1e-12) / max(ref, 1e-12)) if ref > 0 else (top - ref)
        hill_est = float(np.mean(pos_ratio))
        rows.append({
            "regime": regime,
            "method": method,
            "split": split,
            "tail_frac": frac,
            "k_order_tail": k,
            "hill_or_excess": hill_est,
            "q50": q50,
            "q95": q95,
            "q99": q99,
            "q99_over_q95": q99 / q95 if q95 > 0 else np.nan,
            "skewness": skew_v,
            "excess_kurtosis": kurt_v,
        })
    return rows


def run_x02b(
    model_dir: Path | str = Path("data_audit/model_pooled_dev"),
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/x02/x02b"),
    n_null: int = 2000,
    seed_purpose: str = "study_X",
    allow_frozen: bool = True,
    workers: int | None = 1,
    **kwargs,
) -> dict[str, Any]:
    t0_wall = time.time()
    model_dir = Path(model_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _, mcfg, _ = load_models(model_dir)
    require_tuned(mcfg, allow_frozen=allow_frozen)
    meths = [m for m in ["matched_contrast", "adj_cusum", "topk_cusum", "hier_ssm"] if m in mcfg["methods"]]

    # 1. Exact beta-binomial re-audit of v1 Experiment 7 table (B=500, n=500)
    v1_path = Path("results/experiment_7/table_regime_null_rates.csv")
    if v1_path.exists():
        v1 = pd.read_csv(v1_path)
        bb_rows = []
        k_cal = int(np.ceil((500 + 1) * 0.95))
        for _, r in v1.iterrows():
            bb = M.betabinom_validity(int(r["alerts"]), int(r["n"]), 500, k_cal)
            bb_rows.append({
                "true_regime": r["true_regime"], "method": r["method"], "policy": r["policy"],
                "alerts": int(r["alerts"]), "n": int(r["n"]), "rate": float(r["rate"]),
                "expected_alerts": bb["expected_alerts"], "bb_sd": bb["bb_sd"],
                "p_upper": bb["p_upper"], "p_lower": bb["p_lower"],
                "bb_pvalue_two_sided": bb["bb_pvalue_two_sided"],
            })
        df_v1_bb = pd.DataFrame(bb_rows)
        df_v1_bb.to_csv(out_dir / "x02b_v1_betabinom_audit.csv", index=False)
    else:
        df_v1_bb = pd.DataFrame()

    # 2. Confusion matrix on the 1000 legacy Exp-7 evaluation nulls (workload covariate check)
    cfg_plain = SimConfig(sd_host=0.02, workload_step=0.0)
    cfg_step = SimConfig(sd_host=0.02, workload_step=0.3365)
    leg = seeds.LEGACY["v1_experiment_7"]
    conf_legacy = []
    for reg_name, sc, base in [("plain", cfg_plain, leg[2]), ("step", cfg_step, leg[3])]:
        preds = [causal_regime_selector(r.x, r.t0) for i in range(500) for r, _ in [simulate(sc, base + i, False)]]
        for sel in ("plain", "step"):
            cnt = int(sum(p == sel for p in preds))
            conf_legacy.append({"dataset": "v1_exp7_1000_eval_nulls", "true_regime": reg_name, "selected_regime": sel,
                                "count": cnt, "rate": cnt / 500.0})

    # 3. Recompute thresholds with B=2000 and validate on n=2000 fresh nulls per regime
    cal_plain = _sim_and_score_x02b(model_dir, cfg_plain, seed_purpose, 1, n_null, meths, workers, "x02b:cal_plain")
    cal_step = _sim_and_score_x02b(model_dir, cfg_step, seed_purpose, 2, n_null, meths, workers, "x02b:cal_step")
    val_plain = _sim_and_score_x02b(model_dir, cfg_plain, seed_purpose, 3, n_null, meths, workers, "x02b:val_plain")
    val_step = _sim_and_score_x02b(model_dir, cfg_step, seed_purpose, 4, n_null, meths, workers, "x02b:val_step")

    conf_new = []
    for reg_name, recs in [("plain", cal_plain + val_plain), ("step", cal_step + val_step)]:
        for sel in ("plain", "step"):
            cnt = int(sum(r["pred_regime"] == sel for r in recs))
            conf_new.append({"dataset": f"fresh_{2*n_null}_per_regime", "true_regime": reg_name, "selected_regime": sel,
                             "count": cnt, "rate": cnt / len(recs)})
    df_conf = pd.DataFrame(conf_legacy + conf_new)
    df_conf.to_csv(out_dir / "x02b_selector_confusion.csv", index=False)

    recal_rows, ks_rows, tail_rows = [], [], []
    for reg_name, cal_recs, val_recs in [("plain", cal_plain, val_plain), ("step", cal_step, val_step)]:
        for m in meths:
            mx_cal = np.array([r["maxima"][m] for r in cal_recs], float)
            mx_val = np.array([r["maxima"][m] for r in val_recs], float)
            c_info = dec.calibrate_threshold(mx_cal, 0.05)
            thr = c_info["threshold"]
            k_alerts = int(np.sum(mx_val > thr))
            n_v = len(mx_val)
            lo, hi = M.clopper_pearson(k_alerts, n_v)
            bb = M.betabinom_validity(k_alerts, n_v, c_info["B"], c_info["k"])
            recal_rows.append({
                "regime": reg_name, "method": m, "threshold": thr, "B": c_info["B"], "k_order": c_info["k"],
                "alerts": k_alerts, "n": n_v, "rate": k_alerts / n_v, "ci_lo": lo, "ci_hi": hi,
                "expected_alerts": bb["expected_alerts"], "bb_sd": bb["bb_sd"],
                "bb_pvalue_two_sided": bb["bb_pvalue_two_sided"],
                "pass_g2": bool(bb["bb_pvalue_two_sided"] >= 0.01 and (k_alerts / n_v) <= 0.075),
            })
            ks_st, ks_p = ks_2samp(mx_cal, mx_val)
            mw_st, mw_p = mannwhitneyu(mx_cal, mx_val, alternative="two-sided")
            ks_rows.append({
                "regime": reg_name, "method": m,
                "cal_mean": float(np.mean(mx_cal)), "val_mean": float(np.mean(mx_val)),
                "cal_q95": float(np.quantile(mx_cal, 0.95)), "val_q95": float(np.quantile(mx_val, 0.95)),
                "ks_stat": float(ks_st), "ks_p": float(ks_p), "mw_p": float(mw_p),
                "n_cal": len(mx_cal), "n_val": n_v,
            })
            tail_rows.extend(_hill_tail_stats(mx_cal, reg_name, m, "cal"))
            tail_rows.extend(_hill_tail_stats(mx_val, reg_name, m, "val"))

    df_recal = pd.DataFrame(recal_rows)
    df_ks = pd.DataFrame(ks_rows)
    df_tail = pd.DataFrame(tail_rows)
    df_prov = pd.DataFrame([{
        "model_dir": str(model_dir),
        "plain_workload_step": cfg_plain.workload_step,
        "step_workload_step": cfg_step.workload_step,
        "beta_jitter": cfg_step.beta_jitter,
        "sd_host": cfg_step.sd_host,
        "nuisance_seen_cal_or_val": False,
    }])
    df_recal.to_csv(out_dir / "x02b_recal_B2000_validation.csv", index=False)
    df_ks.to_csv(out_dir / "x02b_exchangeability_ks.csv", index=False)
    df_tail.to_csv(out_dir / "x02b_tail_hill.csv", index=False)
    df_prov.to_csv(out_dir / "x02b_generator_provenance.csv", index=False)

    sections = [
        ("Selector Confusion Matrix", df_conf.round(4).to_markdown(index=False)),
        (f"Recalibrated Dual-Regime Validation (B={n_null}, n={n_null})", df_recal.round(4).to_markdown(index=False)),
        ("Calibration vs Validation Maxima Exchangeability (KS / Mann-Whitney)", df_ks.round(4).to_markdown(index=False)),
        ("Maxima Tail Diagnostics (5% Hill Window)", df_tail[df_tail["tail_frac"] == 0.05].round(4).to_markdown(index=False)),
    ]
    if not df_v1_bb.empty:
        sections.insert(0, ("v1 Experiment 7 Exact Beta-Binomial Audit (B=500, n=500)", df_v1_bb.round(4).to_markdown(index=False)))
    write_summary_md(out_dir / "x02b_summary.md", "X-0.2(b) Diagnosis: Step-Regime 6.8%-9.0% Anomaly", sections)
    return {"study": "x02b", "out_dir": str(out_dir), "wall_s": round(time.time() - t0_wall, 3)}


# --------------------------------------------------------------------- X-0.2(c)
def _score_x02c_chunk(task: dict) -> list[dict]:
    models, mcfg, _ = load_models(Path(task["model_dir"]))
    hp_base = dict(mcfg["selected"]["hier_ssm"]["params"])
    hp_base["sd_h_ratio"] = float(task["sd_h_ratio"])
    params = EffectParams(**hp_base)
    det_clean = EffectDetector(models.nuis["main"], params, name="hier_clean")
    label_err = float(task["label_err"])
    rows = []
    for it in task["items"]:
        sc = SimConfig.from_dict(it["sim_cfg"])
        r, t = simulate(sc, int(it["seed"]), bool(it["harm"]), it["rollout_id"], pair_id=int(it["idx"]))
        nc = len(r.canary_idx)
        cls_over = None
        if label_err > 0.0:
            cls = r.class_id[r.canary_idx].copy()
            rng = np.random.default_rng(int(it["seed"]) + 17)
            flip = rng.choice(nc, size=int(round(label_err * nc)), replace=False)
            cls[flip] = 1 - cls[flip]
            cls_over = cls
        det_deg = EffectDetector(models.nuis["main"], params, name="hier_deg", class_override=cls_over)
        adj = adjust_roll(r, models.nuis["main"])
        oc = det_clean.run(adj)
        od = det_deg.run(adj)
        sl = slice(r.t0, None)
        elig = oc.elig[sl] & od.elig[sl]
        diff = np.abs(oc.score[sl][elig] - od.score[sl][elig])

        # Posterior state energy share along class vs local coordinates at horizon end/landmark
        L, _, _ = build_model(params, r.class_id[r.canary_idx])
        post_class_share = float(1.0 / (1.0 + params.sd_h_ratio ** 2))
        entry = {
            "idx": int(it["idx"]),
            "rollout_id": r.rollout_id,
            "harm": bool(it["harm"]),
            "t0": int(r.t0),
            "T": int(r.T),
            "max_score_clean": dec.release_max(oc.score, oc.elig, r.t0),
            "max_score_deg": dec.release_max(od.score, od.elig, r.t0),
            "max_abs_score_diff": float(np.max(diff)),
            "mean_abs_score_diff": float(np.mean(diff)),
            "prior_class_var_frac": post_class_share,
            "score_deg": od.score,
            "elig_deg": od.elig,
            "host_prob_deg": od.host_prob,
            "host_score_deg": od.host_score,
            "ev": M.event_truth(t, nc) if it["harm"] else None,
        }
        # Measure class-span vs orthonormal local-span posterior energy at landmark
        c_use = cls_over if cls_over is not None else r.class_id[r.canary_idx]
        C_mat, B_mat = class_structure(c_use)
        if od.host_score is not None and C_mat.shape[1] > 0:
            tl = min(r.T - 1, r.t0 + 30)
            v_loc = np.nan_to_num(od.host_score[tl])
            h_res = B_mat @ (B_mat.T @ v_loc) if B_mat.shape[1] > 0 else np.zeros_like(v_loc)
            g_proj = v_loc - h_res
            e_tot = float(np.sum(v_loc ** 2))
            entry["post_class_energy_frac"] = float(np.sum(g_proj ** 2) / e_tot) if e_tot > 1e-24 else np.nan
            entry["post_local_energy_frac"] = float(np.sum(h_res ** 2) / e_tot) if e_tot > 1e-24 else np.nan
        else:
            entry["post_class_energy_frac"] = np.nan
            entry["post_local_energy_frac"] = np.nan
        rows.append(entry)
    return rows


def run_x02c(
    model_dir: Path | str = Path("artifacts/model"),
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/x02/x02c"),
    n_null: int = 200,
    n_harm: int = 200,
    seed_purpose: str = "study_X",
    allow_frozen: bool = True,
    workers: int | None = 1,
    **kwargs,
) -> dict[str, Any]:
    t0_wall = time.time()
    model_dir = Path(model_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _, mcfg, _ = load_models(model_dir)
    require_tuned(mcfg, allow_frozen=allow_frozen)

    sc_null = asdict(SimConfig(sd_host=0.02))
    sc_s2 = asdict(SimConfig(sd_host=0.02, affected_mode="class0", effect_pct=3.0, duration=45))
    ratios = [0.25, 1.0, 4.0]
    errs = [0.0, 0.3, 0.5]

    fact_rows, weight_rows = [], []
    for ratio in ratios:
        null_items = [
            {"idx": i, "seed": seeds.seed_for(seed_purpose, i, 5), "rollout_id": f"x02c_n_{i}", "harm": False, "sim_cfg": sc_null}
            for i in range(n_null)
        ]
        harm_items = [
            {"idx": i, "seed": seeds.seed_for(seed_purpose, i, 6), "rollout_id": f"x02c_h_{i}", "harm": True, "sim_cfg": sc_s2}
            for i in range(n_harm)
        ]
        # Calibrate clean detector threshold once per ratio
        w = parallel.resolve_workers(workers, len(null_items))
        ch_n = max(10, len(null_items) // max(1, w))
        t_null = [{"model_dir": str(model_dir), "sd_h_ratio": ratio, "label_err": 0.0, "items": null_items[i:i + ch_n]}
                  for i in range(0, len(null_items), ch_n)]
        n_recs = [r for ch in parallel.pmap(_score_x02c_chunk, t_null, workers=w, desc=f"x02c:null_r={ratio}") for r in ch]
        thr = dec.calibrate_threshold(np.array([r["max_score_clean"] for r in n_recs]), 0.05)["threshold"]

        for err in errs:
            ch_h = max(10, len(harm_items) // max(1, w))
            t_harm = [{"model_dir": str(model_dir), "sd_h_ratio": ratio, "label_err": err, "items": harm_items[i:i + ch_h]}
                      for i in range(0, len(harm_items), ch_h)]
            h_recs = [r for ch in parallel.pmap(_score_x02c_chunk, t_harm, workers=w, desc=f"x02c:r={ratio}_e={err}") for r in ch]
            capped_list, succ_list, auc_list, prec_list, diff_list = [], [], [], [], []
            ce_list, le_list = [], []
            for r in h_recs:
                c = M.classify(dec.first_alarm(r["score_deg"], r["elig_deg"], thr, r["t0"]), r["ev"], r["T"])
                capped_list.append(c["capped"])
                succ_list.append(float(c["status"] == "success"))
                diff_list.append(r["max_abs_score_diff"])
                ce_list.append(r["post_class_energy_frac"])
                le_list.append(r["post_local_energy_frac"])
                out_tmp = type("O", (), {"score": r["score_deg"], "elig": r["elig_deg"],
                                         "host_prob": r["host_prob_deg"], "host_score": r["host_score_deg"]})()
                auc = M.host_auc(out_tmp, r["ev"], landmark=30)
                if np.isfinite(auc):
                    auc_list.append(auc)
                loc = M.localization(out_tmp, r["ev"], landmark=30, cutoff=5)
                if loc is not None:
                    prec_list.append(loc["cut_precision"])
            fact_rows.append({
                "sd_h_ratio": ratio,
                "label_error": err,
                "n_null": n_null,
                "n_harm": len(h_recs),
                "threshold": thr,
                "success_rate": float(np.mean(succ_list)),
                "mean_capped_time": float(np.mean(capped_list)),
                "host_auc_at30": float(np.mean(auc_list)) if auc_list else np.nan,
                "cut5_precision": float(np.mean(prec_list)) if prec_list else np.nan,
                "mean_max_abs_score_diff_vs_clean": float(np.mean(diff_list)),
                "max_max_abs_score_diff_vs_clean": float(np.max(diff_list)),
            })
            weight_rows.append({
                "sd_h_ratio": ratio,
                "label_error": err,
                "prior_class_var_frac": float(h_recs[0]["prior_class_var_frac"]),
                "post_class_energy_frac": float(np.nanmean(ce_list)),
                "post_local_energy_frac": float(np.nanmean(le_list)),
            })

    df_fact = pd.DataFrame(fact_rows)
    df_w = pd.DataFrame(weight_rows)
    df_fact.to_csv(out_dir / "x02c_factorial.csv", index=False)
    df_w.to_csv(out_dir / "x02c_posterior_weights.csv", index=False)
    write_summary_md(
        out_dir / "x02c_summary.md",
        "X-0.2(c) Diagnosis: Label-Error Invariance & sd_h_ratio",
        [
            ("Factorial Grid (sd_h_ratio x label_error on S2 Class-Wide)", df_fact.round(4).to_markdown(index=False)),
            ("Prior & Posterior Class-vs-Local Energy Share", df_w.round(4).to_markdown(index=False)),
        ],
    )
    return {"study": "x02c", "out_dir": str(out_dir), "wall_s": round(time.time() - t0_wall, 3)}


def run(
    model_dir: Path | str = Path("artifacts/model"),
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/x02"),
    n_null: int = 2000,
    n_harm: int = 200,
    seed_purpose: str = "study_X",
    allow_frozen: bool = True,
    workers: int | None = 1,
    **kwargs,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    a = run_x02a(model_dir=model_dir, out_dir=out_dir / "x02a", n_null=min(50, n_null), seed_purpose=seed_purpose, allow_frozen=allow_frozen)
    b = run_x02b(model_dir="data_audit/model_pooled_dev", out_dir=out_dir / "x02b", n_null=n_null, seed_purpose=seed_purpose, allow_frozen=allow_frozen, workers=workers)
    c = run_x02c(model_dir=model_dir, out_dir=out_dir / "x02c", n_null=min(200, n_null), n_harm=n_harm, seed_purpose=seed_purpose, allow_frozen=allow_frozen, workers=workers)
    return {"x02a": a, "x02b": b, "x02c": c}
