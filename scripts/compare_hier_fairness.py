"""Development-only comparison script for Hierarchical vs Independent fairness (Task 1d).

Compares:
1. hier(legacy): Hierarchical SSM with legacy prior and unscaled variance.
2. hier(variance-matched): Hierarchical SSM with variance-matched prior and process noise.
3. indep: Independent SSM (no pooling).
4. pooled: Complete-pooling SSM (single shared effect).

Protocol adherence:
- Data-role separation:
  * dev: used strictly to fit nuisance parameters (pre-period baseline).
  * calibration: used strictly to calibrate order-statistic threshold at alpha=0.05.
  * validation: audit role to measure empirical false-alert rate and detection power / delay.
- Equal false-alert budget: all methods are evaluated at their calibrated alpha=0.05 threshold.
- Full performance reporting: empirical FAR, power (success rate), premature alarms,
  misses, mean delay, and capped time-to-success.
- Outputs saved to `results/table_hier_fairness_comparison.csv`.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canary_ssm.decision import calibrate_threshold, first_alarm, release_max
from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.metrics import classify, event_truth
from canary_ssm.preprocess import fit_nuisance
from canary_ssm.schema import KAPPA
from canary_ssm.seeds import seed_for
from canary_ssm.simulate import SimConfig, simulate


def run_comparison(
    n_dev: int = 40,
    n_cal: int = 100,
    n_val_null: int = 100,
    n_val_harm: int = 100,
    alpha: float = 0.05,
    out_csv: Path | str = "results/table_hier_fairness_comparison.csv",
) -> pd.DataFrame:
    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("Hierarchical vs Independent Fairness Benchmark (Task 1d)")
    print(f"Roles: dev={n_dev}, cal={n_cal}, val_null={n_val_null}, val_harm={n_val_harm}, alpha={alpha}")
    print("=" * 80)

    # 1. SimConfig: 4 canaries across 2 classes (2 canaries per class), 20 controls
    cfg_base = SimConfig(sd_host=0.02, n_canary=4, n_hosts=24, t_pre=30, t_post=60, duration=45)
    cfg_harm = SimConfig(sd_host=0.02, n_canary=4, n_hosts=24, t_pre=30, t_post=60, duration=45, effect_pct=3.0, n_affected=2)

    # 2. DEV ROLE: Fit Nuisance
    print(f"\n[1/4] Generating {n_dev} dev rollouts to fit nuisance baseline...")
    t0_fit = time.time()
    dev_rolls = [
        simulate(cfg_base, seed=seed_for("dev", i, 0), harm=False)[0]
        for i in range(n_dev)
    ]
    nuis = fit_nuisance(dev_rolls, factor_rank=1, noise="ar_only")
    print(f"      Fitted nuisance in {time.time() - t0_fit:.2f}s (x_center={nuis.x_center:.4f})")

    # 3. Define the 4 detector configurations
    configs = {
        "hier(legacy)": EffectParams(
            kind="hier",
            rho_g=0.95,
            rho_h=0.95,
            sd_g=0.005,
            sd_h_ratio=1.0,
            prior_sd=0.03,
            prior_mode="legacy",
            variance_mode="legacy",
        ),
        "hier(variance-matched)": EffectParams(
            kind="hier",
            rho_g=0.95,
            rho_h=0.95,
            sd_g=0.005,
            sd_h_ratio=1.0,
            prior_sd=0.03,
            prior_mode="ratio_scaled",
            variance_mode="variance_matched",
        ),
        "indep": EffectParams(
            kind="indep",
            rho_g=0.95,
            sd_g=0.005,
            prior_sd=0.03,
        ),
        "pooled": EffectParams(
            kind="pooled",
            rho_g=0.95,
            sd_g=0.005,
            prior_sd=0.03,
        ),
    }

    # 4. CALIBRATION ROLE: Calibrate threshold for each detector
    print(f"\n[2/4] Generating {n_cal} calibration null rollouts and calibrating thresholds...")
    t0_cal = time.time()
    cal_adjs = []
    for i in range(n_cal):
        roll, _ = simulate(cfg_base, seed=seed_for("calibration", i, 0), harm=False)
        cal_adjs.append(adjust(roll, nuis.x_center, np.array(nuis.class_lambda)))

    thresholds = {}
    for name, params in configs.items():
        det = EffectDetector(nuis, params, name=name)
        maxima = []
        for adj in cal_adjs:
            out = det.run(adj)
            s_max = release_max(out.score, adj.elig, adj.t0, horizon=cfg_base.t_post)
            maxima.append(s_max)
        cal_res = calibrate_threshold(np.array(maxima), alpha=alpha)
        thresholds[name] = cal_res["threshold"]
        print(f"      {name:24s}: threshold = {cal_res['threshold']:8.4f} (order stat k={cal_res['k']}/{n_cal})")
    print(f"      Calibration complete in {time.time() - t0_cal:.2f}s")

    # 5. VALIDATION NULLS: Empirical False Alert Rate (FAR)
    print(f"\n[3/4] Evaluating {n_val_null} validation null rollouts for empirical FAR...")
    val_null_adjs = []
    for i in range(n_val_null):
        roll, _ = simulate(cfg_base, seed=seed_for("null_validation", i, 0), harm=False)
        val_null_adjs.append(adjust(roll, nuis.x_center, np.array(nuis.class_lambda)))

    far_results = {}
    for name, params in configs.items():
        thr = thresholds[name]
        det = EffectDetector(nuis, params, name=name)
        alarms = 0
        for adj in val_null_adjs:
            out = det.run(adj)
            t_al = first_alarm(out.score, adj.elig, thr, adj.t0)
            if t_al is not None:
                alarms += 1
        far = alarms / n_val_null
        far_results[name] = {"n_null": n_val_null, "n_false_alerts": alarms, "empirical_far": far}
        print(f"      {name:24s}: FAR = {far:.3f} ({alarms}/{n_val_null}) [target <= {alpha:.3f}]")

    # 6. VALIDATION HARMS: Detection Power, Delays, and Capped Times
    print(f"\n[4/4] Evaluating {n_val_harm} validation harm rollouts for detection performance...")
    val_harm_pairs = []
    for i in range(n_val_harm):
        roll, truth = simulate(cfg_harm, seed=seed_for("null_validation", i, 1), harm=True)
        adj = adjust(roll, nuis.x_center, np.array(nuis.class_lambda))
        val_harm_pairs.append((adj, truth))

    perf_results = []
    nc = cfg_harm.n_canary

    for name, params in configs.items():
        thr = thresholds[name]
        det = EffectDetector(nuis, params, name=name)

        successes = 0
        prematures = 0
        misses = 0
        late = 0
        delays = []
        capped_times = []

        for adj, truth in val_harm_pairs:
            ev = event_truth(truth, nc, kappa=KAPPA)
            out = det.run(adj)
            t_al = first_alarm(out.score, adj.elig, thr, adj.t0)
            res = classify(t_al, ev, adj.r.shape[0])

            status = res["status"]
            if status == "success":
                successes += 1
                delays.append(res["delay"])
            elif status == "premature":
                prematures += 1
            elif status == "miss":
                misses += 1
            elif status == "late_after_recovery":
                late += 1

            capped_times.append(res["capped"])

        power = successes / n_val_harm
        premature_rate = prematures / n_val_harm
        miss_rate = misses / n_val_harm
        mean_delay = float(np.mean(delays)) if delays else np.nan
        mean_capped = float(np.mean(capped_times))

        far_info = far_results[name]
        row = {
            "method": name,
            "threshold": thresholds[name],
            "calibrated_alpha": alpha,
            "empirical_far": far_info["empirical_far"],
            "power": power,
            "premature_rate": premature_rate,
            "miss_rate": miss_rate,
            "mean_delay_success": mean_delay,
            "mean_capped_time": mean_capped,
        }
        perf_results.append(row)

    df = pd.DataFrame(perf_results)
    df.to_csv(out_path, index=False)
    print("\n" + "=" * 80)
    print("Final Summary Table (Equal False-Alert Budget):")
    print(df.to_string(index=False))
    print("=" * 80)
    print(f"Saved results to {out_path}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hier vs Indep fairness evaluation at calibrated FAR budget.")
    parser.add_argument("--dev", type=int, default=40, help="Number of dev rollouts for nuisance fit")
    parser.add_argument("--cal", type=int, default=100, help="Number of calibration null rollouts")
    parser.add_argument("--val-null", type=int, default=100, help="Number of validation null rollouts")
    parser.add_argument("--val-harm", type=int, default=100, help="Number of validation harm rollouts")
    parser.add_argument("--alpha", type=float, default=0.05, help="Calibrated false-alert budget")
    parser.add_argument("--out", type=str, default="results/table_hier_fairness_comparison.csv", help="Output CSV path")
    args = parser.parse_args()

    run_comparison(
        n_dev=args.dev,
        n_cal=args.cal,
        n_val_null=args.val_null,
        n_val_harm=args.val_harm,
        alpha=args.alpha,
        out_csv=args.out,
    )
