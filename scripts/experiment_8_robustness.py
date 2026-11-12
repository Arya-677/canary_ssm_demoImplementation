"""Experiment 8: Robustness Under Slope Heterogeneity, Heavy Tails, and Persistent Noise.

Evaluates:
1. Slope estimation error (beta_hat - beta_true) and per-rollout residual shift SD/RMS
   for matched_contrast, pooled_dev beta, and per-host pre beta under heterogeneous slopes.
2. Heavy-tail misspecification (Student-t(3)): hier_ssm vs hier_huber (c=3.0) on false alerts & power.
3. Persistent noise misspecification (phi_e=0.8): standard hier_ssm vs conservative phi_e=0.8 on false alerts & power.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from canary_ssm.simulate import SimConfig, simulate, _streams
from canary_ssm.factor import host_slopes, adjust
from canary_ssm.preprocess import fit_nuisance, adjust_roll, Nuisance
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.baselines import run_baseline
from canary_ssm import decision as dec
from canary_ssm import metrics as M

def extract_true_beta(cfg: SimConfig, seed: int, nc: int) -> np.ndarray:
    rs = _streams(seed)
    m = rs["meta"]
    _ = m.normal(0, cfg.host_mu_sd, cfg.n_hosts)
    return (cfg.beta + m.normal(0, cfg.beta_jitter, cfg.n_hosts))[:nc]

def run_experiment_8(n_null: int = 400, n_harm: int = 150, out_dir: Path = Path("results/experiment_8")):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # Part 1: Heterogeneous Slopes & Residual Spread Diagnostic
    # =========================================================================
    print("--- Part 1: Slope Heterogeneity & Residual Spread Diagnostic ---")
    cfg_hetero = SimConfig(sd_host=0.02, workload_step=0.3365, beta_jitter=0.08)
    
    # Fit pooled beta from dev healthy rollouts (nominal beta=0.15)
    dev_rolls = [simulate(SimConfig(sd_host=0.02), 1_000_000 + i, harm=False)[0] for i in range(30)]
    nuis_pre = fit_nuisance(dev_rolls, beta_mode="pre")
    nuis_pooled = fit_nuisance(dev_rolls, beta_mode="pooled_dev")
    bp = nuis_pooled.beta_pooled
    print(f"Pooled dev beta = {bp:.4f}")
    
    beta_err_rows = []
    res_spread_rows = []
    
    for i in range(n_null):
        seed = 4_100_000 + i
        roll, truth = simulate(cfg_hetero, seed, harm=False)
        nc = len(roll.canary_idx)
        t0 = roll.t0
        
        # True canary betas from Truth simulation config:
        # In simulate.py: beta = cfg.beta + m.normal(0, cfg.beta_jitter, N)
        # We can extract true beta from truth.config or by replicating the stream,
        # but truth object has the exact metadata
        true_beta = extract_true_beta(cfg_hetero, seed, nc)
        
        # Variant 1: Per-host pre-period beta
        b_pre = host_slopes(roll, nuis_pre.x_center)[:nc]
        # Variant 2: Pooled dev beta
        b_pool = np.full(nc, bp)
        
        # Residuals under each variant:
        # 1. Per-host pre
        adj_pre = adjust(roll, nuis_pre.x_center, np.array(nuis_pre.class_lambda), 1, None)
        # 2. Pooled dev
        adj_pool = adjust(roll, nuis_pooled.x_center, np.array(nuis_pooled.class_lambda), 1, bp)
        # 3. Matched contrast residual
        r_mc = adj_pool.rm
        
        # Residual shift: post-mean minus pre-mean per canary host
        shift_pre = np.nanmean(adj_pre.r[t0:], axis=0) - np.nanmean(adj_pre.r[:t0], axis=0)
        shift_pool = np.nanmean(adj_pool.r[t0:], axis=0) - np.nanmean(adj_pool.r[:t0], axis=0)
        shift_mc = np.nanmean(r_mc[t0:], axis=0) - np.nanmean(r_mc[:t0], axis=0)
        
        for name, errs in [("per_host_pre", b_pre - true_beta), ("pooled_dev", b_pool - true_beta)]:
            beta_err_rows.append({
                "variant": name, "rollout_id": roll.rollout_id,
                "mean_error": float(np.mean(errs)),
                "sd_error": float(np.std(errs, ddof=1)),
                "rms_error": float(np.sqrt(np.mean(errs ** 2))),
                "max_abs_error": float(np.max(np.abs(errs)))
            })
            
        for name, shifts in [("per_host_pre", shift_pre), ("pooled_dev", shift_pool), ("matched_contrast", shift_mc)]:
            res_spread_rows.append({
                "variant": name, "rollout_id": roll.rollout_id,
                "signed_mean_shift": float(np.mean(shifts)),
                "sd_residual_shift": float(np.std(shifts, ddof=1)),
                "rms_residual_shift": float(np.sqrt(np.mean(shifts ** 2))),
                "max_abs_shift": float(np.max(np.abs(shifts)))
            })
            
    df_beta_err = pd.DataFrame(beta_err_rows)
    df_res_spread = pd.DataFrame(res_spread_rows)
    
    summary_beta = df_beta_err.groupby("variant")[["mean_error", "sd_error", "rms_error", "max_abs_error"]].mean().reset_index()
    summary_res = df_res_spread.groupby("variant")[["signed_mean_shift", "sd_residual_shift", "rms_residual_shift", "max_abs_shift"]].mean().reset_index()
    
    summary_beta.to_csv(out_dir / "table_beta_error.csv", index=False)
    summary_res.to_csv(out_dir / "table_residual_spread.csv", index=False)
    
    print("\nBeta Estimation Errors (Spread of beta_hat about true beta):")
    print(summary_beta.to_string(index=False))
    print("\nPer-Rollout Residual Shift Diagnostic (SD and RMS vs Signed Mean):")
    print(summary_res.to_string(index=False))
    
    # =========================================================================
    # Part 2: Heavy Tails (student_t3) & hier_huber Evaluation
    # =========================================================================
    print("\n--- Part 2: Heavy Tails (Student-t(3)): hier_ssm vs hier_huber ---")
    cfg_t3_null = SimConfig(sd_host=0.02, heavy_tail_df=3.0)
    cfg_t3_harm = SimConfig(sd_host=0.02, heavy_tail_df=3.0, n_affected=3, effect_pct=3.0, duration=45)
    
    # Calibrate on healthy baseline nulls (plain)
    cal_rolls = [simulate(SimConfig(sd_host=0.02), 2_000_000 + i, harm=False)[0] for i in range(400)]
    p_std = EffectParams(kind="hier", rho_g=0.95, sd_g=0.001, prior_sd=0.01, huber_c=0.0)
    p_hub = EffectParams(kind="hier", rho_g=0.95, sd_g=0.001, prior_sd=0.01, huber_c=3.0)
    
    det_std = EffectDetector(nuis_pooled, p_std, name="hier_ssm")
    det_hub = EffectDetector(nuis_pooled, p_hub, name="hier_huber")
    
    mx_std_cal = [dec.release_max(det_std.run(adjust_roll(r, nuis_pooled)).score, r.decision_obs.all(axis=1), r.t0) for r in cal_rolls]
    mx_hub_cal = [dec.release_max(det_hub.run(adjust_roll(r, nuis_pooled)).score, r.decision_obs.all(axis=1), r.t0) for r in cal_rolls]
    
    thr_std = dec.calibrate_threshold(np.array(mx_std_cal), 0.05)["threshold"]
    thr_hub = dec.calibrate_threshold(np.array(mx_hub_cal), 0.05)["threshold"]
    
    # Evaluate false alerts on t(3) nulls
    alerts_std, alerts_hub = 0, 0
    for i in range(n_null):
        r, _ = simulate(cfg_t3_null, 6_300_000 + i, harm=False)
        a = adjust_roll(r, nuis_pooled)
        o_std = det_std.run(a)
        o_hub = det_hub.run(a)
        if dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0) is not None: alerts_std += 1
        if dec.first_alarm(o_hub.score, o_hub.elig, thr_hub, r.t0) is not None: alerts_hub += 1
        
    rate_std = alerts_std / n_null; lo_std, hi_std = M.clopper_pearson(alerts_std, n_null)
    rate_hub = alerts_hub / n_null; lo_hub, hi_hub = M.clopper_pearson(alerts_hub, n_null)
    
    # Evaluate power on t(3) harmed rollouts
    pow_std, pow_hub = [], []
    for i in range(n_harm):
        r, truth = simulate(cfg_t3_harm, 7_300_000 + i, harm=True)
        ev = M.event_truth(truth, len(r.canary_idx))
        a = adjust_roll(r, nuis_pooled)
        o_std = det_std.run(a)
        o_hub = det_hub.run(a)
        c_std = M.classify(dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0), ev, r.T)
        c_hub = M.classify(dec.first_alarm(o_hub.score, o_hub.elig, thr_hub, r.t0), ev, r.T)
        pow_std.append({"success": c_std["status"] == "success", "capped": c_std["capped"]})
        pow_hub.append({"success": c_hub["status"] == "success", "capped": c_hub["capped"]})
        
    df_t3 = pd.DataFrame([
        {"detector": "hier_ssm (standard)", "null_rate": rate_std, "ci_lo": lo_std, "ci_hi": hi_std,
         "detection_rate": float(np.mean([p["success"] for p in pow_std])),
         "mean_capped_time": float(np.mean([p["capped"] for p in pow_std]))},
        {"detector": "hier_huber (c=3.0)", "null_rate": rate_hub, "ci_lo": lo_hub, "ci_hi": hi_hub,
         "detection_rate": float(np.mean([p["success"] for p in pow_hub])),
         "mean_capped_time": float(np.mean([p["capped"] for p in pow_hub]))}
    ])
    df_t3.to_csv(out_dir / "table_heavy_tails_huber.csv", index=False)
    print("\nHeavy Tails (Student-t(3)) Robustness:")
    print(df_t3.to_string(index=False))
    
    # =========================================================================
    # Part 3: Persistent Noise (phi_e=0.8) & Conservative Filter Evaluation
    # =========================================================================
    print("\n--- Part 3: Persistent Noise (phi_e=0.8): Standard vs Conservative ---")
    cfg_phi_null = SimConfig(sd_host=0.02, phi_e=0.8)
    cfg_phi_harm = SimConfig(sd_host=0.02, phi_e=0.8, n_affected=3, effect_pct=3.0, duration=45)
    
    # Conservative nuisance with phi_e pinned at 0.8:
    nuis_cons = Nuisance(
        x_center=nuis_pooled.x_center, class_lambda=nuis_pooled.class_lambda,
        phi_e=[0.8, 0.8], q_e=nuis_pooled.q_e, v=nuis_pooled.v,
        factor_rank=1, noise="ar_only", beta_mode="pooled_dev", beta_pooled=bp
    )
    det_cons = EffectDetector(nuis_cons, p_std, name="hier_conservative_phi")
    
    mx_cons_cal = [dec.release_max(det_cons.run(adjust_roll(r, nuis_cons)).score, r.decision_obs.all(axis=1), r.t0) for r in cal_rolls]
    thr_cons = dec.calibrate_threshold(np.array(mx_cons_cal), 0.05)["threshold"]
    
    alerts_std_phi, alerts_cons = 0, 0
    for i in range(n_null):
        r, _ = simulate(cfg_phi_null, 6_400_000 + i, harm=False)
        a_std = adjust_roll(r, nuis_pooled)
        a_cons = adjust_roll(r, nuis_cons)
        o_std = det_std.run(a_std)
        o_cons = det_cons.run(a_cons)
        if dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0) is not None: alerts_std_phi += 1
        if dec.first_alarm(o_cons.score, o_cons.elig, thr_cons, r.t0) is not None: alerts_cons += 1
        
    rate_std_p = alerts_std_phi / n_null; lo_std_p, hi_std_p = M.clopper_pearson(alerts_std_phi, n_null)
    rate_cons = alerts_cons / n_null; lo_cons, hi_cons = M.clopper_pearson(alerts_cons, n_null)
    
    pow_std_p, pow_cons = [], []
    for i in range(n_harm):
        r, truth = simulate(cfg_phi_harm, 7_400_000 + i, harm=True)
        ev = M.event_truth(truth, len(r.canary_idx))
        a_std = adjust_roll(r, nuis_pooled)
        a_cons = adjust_roll(r, nuis_cons)
        o_std = det_std.run(a_std)
        o_cons = det_cons.run(a_cons)
        c_std = M.classify(dec.first_alarm(o_std.score, o_std.elig, thr_std, r.t0), ev, r.T)
        c_cons = M.classify(dec.first_alarm(o_cons.score, o_cons.elig, thr_cons, r.t0), ev, r.T)
        pow_std_p.append({"success": c_std["status"] == "success", "capped": c_std["capped"]})
        pow_cons.append({"success": c_cons["status"] == "success", "capped": c_cons["capped"]})
        
    df_phi = pd.DataFrame([
        {"detector": "hier_ssm (nominal phi=0.6)", "null_rate": rate_std_p, "ci_lo": lo_std_p, "ci_hi": hi_std_p,
         "detection_rate": float(np.mean([p["success"] for p in pow_std_p])),
         "mean_capped_time": float(np.mean([p["capped"] for p in pow_std_p]))},
        {"detector": "hier_ssm (conservative phi=0.8)", "null_rate": rate_cons, "ci_lo": lo_cons, "ci_hi": hi_cons,
         "detection_rate": float(np.mean([p["success"] for p in pow_cons])),
         "mean_capped_time": float(np.mean([p["capped"] for p in pow_cons]))}
    ])
    df_phi.to_csv(out_dir / "table_persistent_noise.csv", index=False)
    print("\nPersistent Noise (phi_e=0.8) Robustness:")
    print(df_phi.to_string(index=False))
    
    # Combined report
    rep = [
        "# Experiment 8: Robustness Evaluation\n",
        "## 1. Beta Spread & Residual Shift Diagnostic Under Slope Heterogeneity\n",
        summary_beta.to_markdown(index=False),
        "\n",
        summary_res.to_markdown(index=False),
        "\n## 2. Heavy Tails (Student-t(3)) Robustness\n",
        df_t3.to_markdown(index=False),
        "\n## 3. Persistent Noise (phi_e=0.8) Robustness\n",
        df_phi.to_markdown(index=False),
    ]
    (out_dir / "report.md").write_text("\n".join(rep))
    print(f"\nExperiment 8 complete! Artifacts written to {out_dir}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-null", type=int, default=400)
    ap.add_argument("--n-harm", type=int, default=150)
    a = ap.parse_args()
    run_experiment_8(a.n_null, a.n_harm)
