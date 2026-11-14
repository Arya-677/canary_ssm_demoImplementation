"""Experiment 7: Causal Workload Regime Rule for Calibration Under Shared Steps.

Evaluates:
1. False-alert rate on plain nulls (n=500).
2. False-alert rate on step nulls (n=500).
3. Calibration gate status (95% Clopper-Pearson upper bound <= 0.08).
4. Statistical power & time-to-success on harmed rollouts (plain S1 vs step S1)
   comparing causal dual-regime policy vs single pooled threshold policy.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from canary_ssm.simulate import SimConfig, simulate
from canary_ssm.experiments import load_models, run_methods, load_config
from canary_ssm import decision as dec
from canary_ssm import metrics as M

def causal_regime_selector(x: np.ndarray, t0: int, thr: float = 0.17) -> str:
    """Selects regime from measured workload covariate x only (no truth, no latency)."""
    pre = np.mean(x[max(0, t0 - 5):t0])
    # Causal check using first post-rollout observations:
    post = np.mean(x[t0:min(len(x), t0 + 5)])
    return "step" if (post - pre) > thr else "plain"

def run_experiment_7(n_null: int = 500, n_harm: int = 200, beta_mode: str = "pooled_dev",
                     out_dir: Path = Path("results/experiment_7")):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    models, mcfg, mh = load_models(f"data_audit/model_{beta_mode}")
    methods = ["matched_contrast", "adj_cusum", "topk_cusum", "hier_ssm"]
    
    # 1. Simulate calibration sets for both regimes:
    # 500 plain nulls, 500 step nulls
    cfg_plain = SimConfig(sd_host=0.02, workload_step=0.0)
    cfg_step = SimConfig(sd_host=0.02, workload_step=0.3365)
    
    print(f"--- Calibrating Dual Regimes (n={n_null} nulls per regime, beta_mode={beta_mode}) ---")
    plain_maxima = {m: [] for m in methods}
    step_maxima = {m: [] for m in methods}
    
    for i in range(n_null):
        # Plain null
        rp, _ = simulate(cfg_plain, 2_100_000 + i, harm=False)
        op = run_methods(models, rp, methods, [])
        for m in methods:
            plain_maxima[m].append(dec.release_max(op[m].score, op[m].elig, rp.t0))
            
        # Step null
        rs, _ = simulate(cfg_step, 2_600_000 + i, harm=False)
        os = run_methods(models, rs, methods, [])
        for m in methods:
            step_maxima[m].append(dec.release_max(os[m].score, os[m].elig, rs.t0))
            
    # Compute thresholds
    thr_plain = {m: dec.calibrate_threshold(np.array(plain_maxima[m]), 0.05)["threshold"] for m in methods}
    thr_step = {m: dec.calibrate_threshold(np.array(step_maxima[m]), 0.05)["threshold"] for m in methods}
    
    # Single threshold from combined mixture (85% plain, 15% step):
    mix_maxima = {m: np.concatenate([np.random.default_rng(42).choice(plain_maxima[m], size=int(0.85*n_null), replace=False),
                                     np.random.default_rng(43).choice(step_maxima[m], size=int(0.15*n_null), replace=False)])
                  for m in methods}
    thr_single = {m: dec.calibrate_threshold(mix_maxima[m], 0.05)["threshold"] for m in methods}
    
    print("\nCalibrated Thresholds:")
    for m in methods:
        print(f"  {m:18s} | Plain: {thr_plain[m]:.4g} | Step: {thr_step[m]:.4g} | Single Mixture: {thr_single[m]:.4g}")
        
    # 2. Evaluate False-Alert Rates on Fresh Independent Nulls (n=n_null per cell)
    print(f"\n--- Evaluating False-Alert Rates on Fresh Nulls (n={n_null} per cell) ---")
    null_eval_rows = []
    
    for regime_name, sc in [("plain", cfg_plain), ("step", cfg_step)]:
        alarms_dual = {m: 0 for m in methods}
        alarms_single = {m: 0 for m in methods}
        regime_preds = []
        
        for i in range(n_null):
            seed = 7_500_000 + (0 if regime_name == "plain" else 500_000) + i
            roll, _ = simulate(sc, seed, harm=False)
            pred_regime = causal_regime_selector(roll.x, roll.t0)
            regime_preds.append(pred_regime)
            
            outs = run_methods(models, roll, methods, [])
            for m in methods:
                o = outs[m]
                # Dual causal rule:
                t_used = thr_step[m] if pred_regime == "step" else thr_plain[m]
                if dec.first_alarm(o.score, o.elig, t_used, roll.t0) is not None:
                    alarms_dual[m] += 1
                # Single threshold:
                if dec.first_alarm(o.score, o.elig, thr_single[m], roll.t0) is not None:
                    alarms_single[m] += 1
                    
        regime_acc = np.mean([p == regime_name for p in regime_preds])
        print(f"  True {regime_name:5s} nulls: regime selector accuracy = {100*regime_acc:.1f}%")
        
        for m in methods:
            kd, n = alarms_dual[m], n_null
            lod, hid = M.clopper_pearson(kd, n)
            ks = alarms_single[m]
            los, his = M.clopper_pearson(ks, n)
            
            null_eval_rows.append({
                "true_regime": regime_name,
                "method": m,
                "policy": "causal_dual_regime",
                "alerts": kd, "n": n, "rate": kd / n, "ci_lo": lod, "ci_hi": hid,
                "pass_upper_le_8pct": bool(hid <= 0.08),
                "pass_contains_5pct": bool(lod <= 0.05 <= hid)
            })
            null_eval_rows.append({
                "true_regime": regime_name,
                "method": m,
                "policy": "single_threshold",
                "alerts": ks, "n": n, "rate": ks / n, "ci_lo": los, "ci_hi": his,
                "pass_upper_le_8pct": bool(his <= 0.08),
                "pass_contains_5pct": bool(los <= 0.05 <= his)
            })
            
    df_null = pd.DataFrame(null_eval_rows)
    df_null.to_csv(out_dir / "table_regime_null_rates.csv", index=False)
    
    # 3. Evaluate Power and Time-to-Success on Harmed Rollouts (n=n_harm per scenario)
    print(f"\n--- Evaluating Statistical Power on Harmed Rollouts (n={n_harm} per scenario) ---")
    cfg_s1_plain = SimConfig(sd_host=0.02, n_affected=3, effect_pct=3.0, duration=45, workload_step=0.0)
    cfg_s1_step  = SimConfig(sd_host=0.02, n_affected=3, effect_pct=3.0, duration=45, workload_step=0.3365)
    
    power_rows = []
    for scen_name, sc in [("S1_plain", cfg_s1_plain), ("S1_step", cfg_s1_step)]:
        for i in range(n_harm):
            seed = 8_200_000 + (0 if "plain" in scen_name else 300_000) + i
            roll, truth = simulate(sc, seed, harm=True)
            ev = M.event_truth(truth, len(roll.canary_idx))
            if not ev["has_event"]:
                continue
            pred_regime = causal_regime_selector(roll.x, roll.t0)
            outs = run_methods(models, roll, methods, [])
            
            for m in methods:
                o = outs[m]
                # Dual causal
                t_used = thr_step[m] if pred_regime == "step" else thr_plain[m]
                ta_dual = dec.first_alarm(o.score, o.elig, t_used, roll.t0)
                c_dual = M.classify(ta_dual, ev, roll.T)
                
                # Single
                ta_sing = dec.first_alarm(o.score, o.elig, thr_single[m], roll.t0)
                c_sing = M.classify(ta_sing, ev, roll.T)
                
                power_rows.append({
                    "scenario": scen_name, "rollout_id": roll.rollout_id, "method": m,
                    "pred_regime": pred_regime,
                    "success_dual": c_dual["status"] == "success",
                    "capped_dual": c_dual["capped"],
                    "delay_dual": c_dual["delay"],
                    "success_single": c_sing["status"] == "success",
                    "capped_single": c_sing["capped"],
                    "delay_single": c_sing["delay"],
                })
                
    df_power = pd.DataFrame(power_rows)
    df_power.to_csv(out_dir / "table_power_rollouts.csv", index=False)
    
    # Summary of power comparison
    summary_rows = []
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
            "power_gain_reading": "negative favours dual causal rule (faster / more detections)"
        })
    df_summary = pd.DataFrame(summary_rows)
    df_summary.to_csv(out_dir / "table_power_summary.csv", index=False)
    print("\nPower Summary:")
    print(df_summary[["scenario", "method", "detection_rate_dual", "detection_rate_single",
                      "mean_capped_dual", "mean_capped_single", "mean_capped_diff_dual_minus_single"]].to_string(index=False))
    
    # Write report
    report = [
        "# Experiment 7: Causal Workload Regime Rule Evaluation\n",
        f"**Null rollouts per cell:** {n_null} | **Harmed rollouts per scenario:** {n_harm}\n",
        "## 1. Null False-Alert Rates (Target: 5.0%)\n",
        df_null.to_markdown(index=False),
        "\n## 2. Statistical Power & Horizon-Capped Time Comparison\n",
        df_summary.to_markdown(index=False),
    ]
    (out_dir / "report.md").write_text("\n".join(report))
    print(f"\nExperiment 7 complete! Artifacts written to {out_dir}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-null", type=int, default=500)
    ap.add_argument("--n-harm", type=int, default=200)
    ap.add_argument("--beta-mode", default="pooled_dev")
    a = ap.parse_args()
    run_experiment_7(a.n_null, a.n_harm, a.beta_mode)
