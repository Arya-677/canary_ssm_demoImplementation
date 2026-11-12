"""Robustness diagnostic study (ported from Experiment 8; WP-A5, WP-A6)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import decision as dec
from .. import manifest as man_mod
from .. import metrics as M
from .. import seeds
from ..experiments import load_models
from ..factor import adjust, host_slopes
from ..hierarchy import EffectDetector, EffectParams
from ..preprocess import Nuisance, adjust_roll, fit_nuisance
from ..simulate import SimConfig, _streams, simulate
from . import require_tuned, write_summary_md


def _extract_true_beta(cfg: SimConfig, seed: int, nc: int) -> np.ndarray:
    rs = _streams(seed)
    m = rs["meta"]
    _ = m.normal(0, cfg.host_mu_sd, cfg.n_hosts)
    return (cfg.beta + m.normal(0, cfg.beta_jitter, cfg.n_hosts))[:nc]


def run(
    model_dir: Path | str | None = None,
    policy_dir: Path | str | None = None,
    out_dir: Path | str = Path("results/study_robust"),
    n_null: int = 400,
    n_harm: int = 150,
    seed_purpose: str = "study_robust",
    allow_frozen: bool = False,
    legacy_seeds: bool = False,
    **kwargs,
) -> dict[str, Any]:
    """Run slope heterogeneity, heavy-tail (t3), and persistent-noise (phi_e=0.8) robustness checks."""
    t0_wall = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mh = None
    if model_dir is not None:
        _, mcfg, mh = load_models(Path(model_dir))
        require_tuned(mcfg, allow_frozen=allow_frozen)

    leg = seeds.LEGACY["v1_experiment_8"] if legacy_seeds else [None] * 7

    # Part 1: Heterogeneous Slopes & Residual Spread Diagnostic
    cfg_hetero = SimConfig(sd_host=0.02, workload_step=0.3365, beta_jitter=0.08)
    dev_rolls = [
        simulate(SimConfig(sd_host=0.02), (leg[0] + i) if leg[0] is not None else seeds.seed_for(seed_purpose, i, 0), harm=False)[0]
        for i in range(30)
    ]
    nuis_pre = fit_nuisance(dev_rolls, beta_mode="pre")
    nuis_pooled = fit_nuisance(dev_rolls, beta_mode="pooled_dev")
    bp = nuis_pooled.beta_pooled

    beta_err_rows, res_spread_rows = [], []
    for i in range(n_null):
        seed = (leg[2] + i) if leg[2] is not None else seeds.seed_for(seed_purpose, i, 2)
        roll, _ = simulate(cfg_hetero, seed, harm=False)
        nc = len(roll.canary_idx)
        t0 = roll.t0
        true_beta = _extract_true_beta(cfg_hetero, seed, nc)
        b_pre = host_slopes(roll, nuis_pre.x_center)[:nc]
        b_pool = np.full(nc, bp)
        adj_pre = adjust(roll, nuis_pre.x_center, np.array(nuis_pre.class_lambda), 1, None)
        adj_pool = adjust(roll, nuis_pooled.x_center, np.array(nuis_pooled.class_lambda), 1, bp)
        r_mc = adj_pool.rm

        shift_pre = np.nanmean(adj_pre.r[t0:], axis=0) - np.nanmean(adj_pre.r[:t0], axis=0)
        shift_pool = np.nanmean(adj_pool.r[t0:], axis=0) - np.nanmean(adj_pool.r[:t0], axis=0)
        shift_mc = np.nanmean(r_mc[t0:], axis=0) - np.nanmean(r_mc[:t0], axis=0)

        for name, errs in [("per_host_pre", b_pre - true_beta), ("pooled_dev", b_pool - true_beta)]:
            beta_err_rows.append({
                "variant": name, "rollout_id": roll.rollout_id,
                "mean_error": float(np.mean(errs)), "sd_error": float(np.std(errs, ddof=1)),
                "rms_error": float(np.sqrt(np.mean(errs ** 2))), "max_abs_error": float(np.max(np.abs(errs))),
            })
        for name, shifts in [("per_host_pre", shift_pre), ("pooled_dev", shift_pool), ("matched_contrast", shift_mc)]:
            res_spread_rows.append({
                "variant": name, "rollout_id": roll.rollout_id,
                "signed_mean_shift": float(np.mean(shifts)),
                "sd_residual_shift": float(np.std(shifts, ddof=1)),
                "rms_residual_shift": float(np.sqrt(np.mean(shifts ** 2))),
                "max_abs_shift": float(np.max(np.abs(shifts))),
            })

    summary_beta = pd.DataFrame(beta_err_rows).groupby("variant")[["mean_error", "sd_error", "rms_error", "max_abs_error"]].mean().reset_index()
    summary_res = pd.DataFrame(res_spread_rows).groupby("variant")[["signed_mean_shift", "sd_residual_shift", "rms_residual_shift", "max_abs_shift"]].mean().reset_index()
    summary_beta.to_csv(out_dir / "table_beta_error.csv", index=False)
    summary_res.to_csv(out_dir / "table_residual_spread.csv", index=False)

    # Part 2: Heavy Tails (Student-t(3)) & hier_huber using DetectorOutput.elig (WP-A5)
    cal_rolls = [
        simulate(SimConfig(sd_host=0.02), (leg[1] + i) if leg[1] is not None else seeds.seed_for(seed_purpose, i, 1), harm=False)[0]
        for i in range(400)
    ]
    p_std = EffectParams(kind="hier", rho_g=0.95, sd_g=0.001, prior_sd=0.01, huber_c=0.0)
    p_hub = EffectParams(kind="hier", rho_g=0.95, sd_g=0.001, prior_sd=0.01, huber_c=3.0)
    det_std = EffectDetector(nuis_pooled, p_std, name="hier_ssm")
    det_hub = EffectDetector(nuis_pooled, p_hub, name="hier_huber")

    cal_adj = [adjust_roll(r, nuis_pooled) for r in cal_rolls]
    mx_std_cal = [dec.release_max(o.score, o.elig, r.t0) for r, o in ((r, det_std.run(a)) for r, a in zip(cal_rolls, cal_adj))]
    mx_hub_cal = [dec.release_max(o.score, o.elig, r.t0) for r, o in ((r, det_hub.run(a)) for r, a in zip(cal_rolls, cal_adj))]
    c_std_cal = dec.calibrate_threshold(np.array(mx_std_cal), 0.05)
    c_hub_cal = dec.calibrate_threshold(np.array(mx_hub_cal), 0.05)
    thr_std, thr_hub = c_std_cal["threshold"], c_hub_cal["threshold"]

    cfg_t3_null = SimConfig(sd_host=0.02, heavy_tail_df=3.0)
    cfg_t3_harm = SimConfig(sd_host=0.02, heavy_tail_df=3.0, n_affected=3, effect_pct=3.0, duration=45)
    alerts_std, alerts_hub = 0, 0
    for i in range(n_null):
        r, _ = simulate(cfg_t3_null, (leg[3] + i) if leg[3] is not None else seeds.seed_for(seed_purpose, i, 3), harm=False)
        a = adjust_roll(r, nuis_pooled)
        o_std, o_hub = det_std.run(a), det_hub.run(a)
        if dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0) is not None:
            alerts_std += 1
        if dec.first_alarm(o_hub.score, o_hub.elig, thr_hub, r.t0) is not None:
            alerts_hub += 1

    pow_std, pow_hub = [], []
    for i in range(n_harm):
        r, truth = simulate(cfg_t3_harm, (leg[5] + i) if leg[5] is not None else seeds.seed_for(seed_purpose, i, 5), harm=True)
        ev = M.event_truth(truth, len(r.canary_idx))
        a = adjust_roll(r, nuis_pooled)
        o_std, o_hub = det_std.run(a), det_hub.run(a)
        c1 = M.classify(dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0), ev, r.T)
        c2 = M.classify(dec.first_alarm(o_hub.score, o_hub.elig, thr_hub, r.t0), ev, r.T)
        pow_std.append({"success": c1["status"] == "success", "capped": c1["capped"]})
        pow_hub.append({"success": c2["status"] == "success", "capped": c2["capped"]})

    lo_std, hi_std = M.clopper_pearson(alerts_std, n_null)
    lo_hub, hi_hub = M.clopper_pearson(alerts_hub, n_null)
    bb_std_t3 = M.betabinom_validity(alerts_std, n_null, c_std_cal["B"], c_std_cal["k"])
    bb_hub_t3 = M.betabinom_validity(alerts_hub, n_null, c_hub_cal["B"], c_hub_cal["k"])
    df_t3 = pd.DataFrame([
        {
            "detector": "hier_ssm (standard)", "alerts": alerts_std, "n_null": n_null,
            "null_rate": alerts_std / n_null, "ci_lo": lo_std, "ci_hi": hi_std,
            "bb_pvalue_two_sided": bb_std_t3["bb_pvalue_two_sided"],
            "detection_rate": float(np.mean([p["success"] for p in pow_std])),
            "mean_capped_time": float(np.mean([p["capped"] for p in pow_std])),
        },
        {
            "detector": "hier_huber (c=3.0)", "alerts": alerts_hub, "n_null": n_null,
            "null_rate": alerts_hub / n_null, "ci_lo": lo_hub, "ci_hi": hi_hub,
            "bb_pvalue_two_sided": bb_hub_t3["bb_pvalue_two_sided"],
            "detection_rate": float(np.mean([p["success"] for p in pow_hub])),
            "mean_capped_time": float(np.mean([p["capped"] for p in pow_hub])),
        },
    ])
    df_t3.to_csv(out_dir / "table_heavy_tails_huber.csv", index=False)

    # Part 3: Persistent Noise (phi_e=0.8) & Conservative Filter
    cfg_phi_null = SimConfig(sd_host=0.02, phi_e=0.8)
    cfg_phi_harm = SimConfig(sd_host=0.02, phi_e=0.8, n_affected=3, effect_pct=3.0, duration=45)
    nuis_cons = Nuisance(
        x_center=nuis_pooled.x_center, class_lambda=nuis_pooled.class_lambda,
        phi_e=[0.8, 0.8], q_e=nuis_pooled.q_e, v=nuis_pooled.v,
        factor_rank=1, noise="ar_only", beta_mode="pooled_dev", beta_pooled=bp,
    )
    det_cons = EffectDetector(nuis_cons, p_std, name="hier_conservative_phi")
    mx_cons_cal = [dec.release_max(o.score, o.elig, r.t0) for r in cal_rolls for o in [det_cons.run(adjust_roll(r, nuis_cons))]]
    c_cons_cal = dec.calibrate_threshold(np.array(mx_cons_cal), 0.05)
    thr_cons = c_cons_cal["threshold"]

    alerts_std_phi, alerts_cons = 0, 0
    for i in range(n_null):
        r, _ = simulate(cfg_phi_null, (leg[4] + i) if leg[4] is not None else seeds.seed_for(seed_purpose, i, 4), harm=False)
        o_std = det_std.run(adjust_roll(r, nuis_pooled))
        o_cons = det_cons.run(adjust_roll(r, nuis_cons))
        if dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0) is not None:
            alerts_std_phi += 1
        if dec.first_alarm(o_cons.score, o_cons.elig, thr_cons, r.t0) is not None:
            alerts_cons += 1

    pow_std_p, pow_cons = [], []
    for i in range(n_harm):
        r, truth = simulate(cfg_phi_harm, (leg[6] + i) if leg[6] is not None else seeds.seed_for(seed_purpose, i, 6), harm=True)
        ev = M.event_truth(truth, len(r.canary_idx))
        o_std = det_std.run(adjust_roll(r, nuis_pooled))
        o_cons = det_cons.run(adjust_roll(r, nuis_cons))
        c1 = M.classify(dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0), ev, r.T)
        c2 = M.classify(dec.first_alarm(o_cons.score, o_cons.elig, thr_cons, r.t0), ev, r.T)
        pow_std_p.append({"success": c1["status"] == "success", "capped": c1["capped"]})
        pow_cons.append({"success": c2["status"] == "success", "capped": c2["capped"]})

    lo_sp, hi_sp = M.clopper_pearson(alerts_std_phi, n_null)
    lo_co, hi_co = M.clopper_pearson(alerts_cons, n_null)
    bb_sp = M.betabinom_validity(alerts_std_phi, n_null, c_std_cal["B"], c_std_cal["k"])
    bb_co = M.betabinom_validity(alerts_cons, n_null, c_cons_cal["B"], c_cons_cal["k"])
    df_phi = pd.DataFrame([
        {
            "detector": "hier_ssm (nominal phi=0.6)", "alerts": alerts_std_phi, "n_null": n_null,
            "null_rate": alerts_std_phi / n_null, "ci_lo": lo_sp, "ci_hi": hi_sp,
            "bb_pvalue_two_sided": bb_sp["bb_pvalue_two_sided"],
            "detection_rate": float(np.mean([p["success"] for p in pow_std_p])),
            "mean_capped_time": float(np.mean([p["capped"] for p in pow_std_p])),
        },
        {
            "detector": "hier_ssm (conservative phi=0.8)", "alerts": alerts_cons, "n_null": n_null,
            "null_rate": alerts_cons / n_null, "ci_lo": lo_co, "ci_hi": hi_co,
            "bb_pvalue_two_sided": bb_co["bb_pvalue_two_sided"],
            "detection_rate": float(np.mean([p["success"] for p in pow_cons])),
            "mean_capped_time": float(np.mean([p["capped"] for p in pow_cons])),
        },
    ])
    df_phi.to_csv(out_dir / "table_persistent_noise.csv", index=False)

    write_summary_md(
        out_dir / "report.md",
        "Study: Robustness Under Misspecification",
        [
            ("Slope Estimation Error", summary_beta.round(4).to_markdown(index=False)),
            ("Residual Shift Spread", summary_res.round(4).to_markdown(index=False)),
            ("Heavy Tails (Student-t(3))", df_t3.round(4).to_markdown(index=False)),
            ("Persistent Noise (phi_e=0.8)", df_phi.round(4).to_markdown(index=False)),
        ],
    )
    manifest = man_mod.build_manifest(
        out_dir=out_dir,
        study="robust",
        model_dir=str(model_dir) if model_dir is not None else None,
        model_hash=mh,
        allow_frozen=bool(allow_frozen),
        legacy_seeds=bool(legacy_seeds),
        seed_purpose=seed_purpose,
        n_null=int(n_null),
        n_harm=int(n_harm),
        wall_times={"study_robust_s": round(time.time() - t0_wall, 3)},
    )
    (out_dir / "experiment_manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return manifest
