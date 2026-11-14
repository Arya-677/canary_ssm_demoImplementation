"""
Robustness, Out-of-Distribution, Negative Controls, and Scaling Experiments Runner (Gate G7).
Evaluates:
1. Missingness mechanisms (MCAR 0-40%, burst dropouts).
2. Control contamination (0%, 1%, 5%, 10%, 25%).
3. Five negative controls (NC-01 to NC-05).
4. OOD calibration transfer (TRANSFER-A vs TRANSFER-B).
5. Computational runtime scaling (N=10 to 500 hosts).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import numpy as np
import pandas as pd

from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.preprocess import fit_nuisance, Nuisance
from canary_ssm.simulate import SimConfig, simulate
from canary_ssm.comparators import KayentaJudge, SLOThresholdComparator, NoInertiaSSM

OUT_DIR = Path("external_validation_v1/results/robustness")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Missingness Robustness Sweep
# ---------------------------------------------------------------------------
def run_missingness_sweep(nuis: Nuisance, tau: float, n_reps: int = 30) -> pd.DataFrame:
    print("Running Missingness Robustness Sweep...")
    missing_rates = [0.0, 0.05, 0.10, 0.20, 0.40]
    records = []

    for rate in missing_rates:
        delays = []
        alarms = 0
        abstentions = 0

        for rep in range(n_reps):
            seed = 110000 + int(rate * 1000) + rep
            cfg = SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60,
                            n_affected=2, effect_pct=3.5, duration=45,
                            missing_rate=rate)
            r, _ = simulate(cfg, seed=seed, harm=True)
            adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))

            # Detector run
            det = EffectDetector(nuis, EffectParams(kind="hier"))
            out = det.run(adj)
            score_post = out.score[r.t0:]

            # Abstention check: if > 50% of canary observations are missing
            can_obs = r.observed[r.t0:, r.canary_idx]
            if np.mean(can_obs) < 0.5:
                abstentions += 1

            if len(score_post) > 0 and np.nanmax(score_post) >= tau:
                alarms += 1
                alarm_rel = int(np.flatnonzero(score_post >= tau)[0])
                delays.append(float(alarm_rel))

        records.append({
            "missing_mechanism": "MCAR",
            "missing_rate": rate,
            "burst_len": 0,
            "power": alarms / n_reps,
            "mean_delay": float(np.mean(delays)) if delays else np.nan,
            "median_delay": float(np.median(delays)) if delays else np.nan,
            "abstention_rate": abstentions / n_reps
        })

    # Burst missingness test
    burst_delays = []
    burst_alarms = 0
    burst_abst = 0
    for rep in range(n_reps):
        seed = 111000 + rep
        cfg = SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60,
                        n_affected=2, effect_pct=3.5, duration=45,
                        missing_rate=0.15, burst_len=5)
        r, _ = simulate(cfg, seed=seed, harm=True)
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
        det = EffectDetector(nuis, EffectParams(kind="hier"))
        out = det.run(adj)
        score_post = out.score[r.t0:]

        can_obs = r.observed[r.t0:, r.canary_idx]
        if np.mean(can_obs) < 0.5:
            burst_abst += 1

        if len(score_post) > 0 and np.nanmax(score_post) >= tau:
            burst_alarms += 1
            alarm_rel = int(np.flatnonzero(score_post >= tau)[0])
            burst_delays.append(float(alarm_rel))

    records.append({
        "missing_mechanism": "BURST",
        "missing_rate": 0.15,
        "burst_len": 5,
        "power": burst_alarms / n_reps,
        "mean_delay": float(np.mean(burst_delays)) if burst_delays else np.nan,
        "median_delay": float(np.median(burst_delays)) if burst_delays else np.nan,
        "abstention_rate": burst_abst / n_reps
    })

    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "missingness_sweep.csv", index=False)
    print("Missingness Sweep Results:")
    print(df.to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# 2. Control Contamination Sweep
# ---------------------------------------------------------------------------
def run_contamination_sweep(nuis: Nuisance, tau: float, n_reps: int = 30) -> pd.DataFrame:
    print("Running Control Contamination Sweep...")
    contam_fracs = [0.0, 0.01, 0.05, 0.10, 0.25]
    records = []

    for frac in contam_fracs:
        delays = []
        alarms = 0

        for rep in range(n_reps):
            seed = 112000 + int(frac * 1000) + rep
            cfg = SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60,
                            n_affected=2, effect_pct=3.5, duration=45,
                            contam_frac=frac, contam_scale=0.5)
            r, _ = simulate(cfg, seed=seed, harm=True)
            adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
            det = EffectDetector(nuis, EffectParams(kind="hier"))
            out = det.run(adj)
            score_post = out.score[r.t0:]

            if len(score_post) > 0 and np.nanmax(score_post) >= tau:
                alarms += 1
                alarm_rel = int(np.flatnonzero(score_post >= tau)[0])
                delays.append(float(alarm_rel))

        records.append({
            "contam_frac": frac,
            "power": alarms / n_reps,
            "mean_delay": float(np.mean(delays)) if delays else np.nan,
            "power_retention": (alarms / n_reps) / max(1e-6, records[0]["power"] if records else 1.0)
        })

    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "contamination_sweep.csv", index=False)
    print("Contamination Sweep Results:")
    print(df.to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# 3. Five Negative Controls (NC-01 to NC-05)
# ---------------------------------------------------------------------------
def run_negative_controls(nuis: Nuisance, tau: float, n_reps: int = 50) -> pd.DataFrame:
    print("Running Negative Controls Battery (NC-01 to NC-05)...")
    controls = {
        "NC-01_traffic_surge": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, workload_step=0.405), # +50% surge
        "NC-02_db_slowdown": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, spike_n=1, spike_len=15, spike_mag=0.20),
        "NC-03_permuted_canaries": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60), # canary indices permuted with controls
        "NC-04_upstream_throttling": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, contam_frac=0.50, contam_scale=1.0), # uniform 50%
        "NC-05_variance_doubling": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, host_mu_sd=0.20),
    }

    records = []
    for nc_name, cfg in controls.items():
        alarms = 0
        max_scores = []

        for rep in range(n_reps):
            seed = 113000 + rep
            r, _ = simulate(cfg, seed=seed, harm=False)

            if nc_name == "NC-03_permuted_canaries":
                # Permute canary flags among control hosts
                rng = np.random.default_rng(seed)
                perm = rng.permutation(r.N)
                r.exposed = np.zeros(r.N, bool)
                r.exposed[perm[:r.N // 3]] = True

            adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
            det = EffectDetector(nuis, EffectParams(kind="hier"))
            out = det.run(adj)
            score_post = out.score[r.t0:]

            m_score = float(np.nanmax(score_post)) if len(score_post) > 0 else -np.inf
            max_scores.append(m_score)
            if m_score >= tau:
                alarms += 1

        far = alarms / n_reps
        records.append({
            "control_id": nc_name,
            "n_reps": n_reps,
            "alarms": alarms,
            "achieved_far": far,
            "mean_max_score": float(np.mean(max_scores)),
            "safety_gate_passed": far <= 0.08
        })

    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "negative_controls.csv", index=False)
    print("Negative Controls Summary:")
    print(df.to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# 4. Out-of-Distribution Calibration Transfer
# ---------------------------------------------------------------------------
def run_ood_transfer(nuis: Nuisance, tau_source: float, n_reps: int = 50) -> pd.DataFrame:
    print("Running Out-of-Distribution Generalization (TRANSFER-A vs TRANSFER-B)...")
    # Step regime nulls
    cfg_step = SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, workload_step=0.3365)

    # TRANSFER-A: Evaluate source threshold on target step regime
    alarms_a = 0
    scores_step_nulls = []
    for rep in range(n_reps):
        seed = 114000 + rep
        r, _ = simulate(cfg_step, seed=seed, harm=False)
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
        det = EffectDetector(nuis, EffectParams(kind="hier"))
        out = det.run(adj)
        m_sc = float(np.nanmax(out.score[r.t0:]))
        scores_step_nulls.append(m_sc)
        if m_sc >= tau_source:
            alarms_a += 1

    far_a = alarms_a / n_reps

    # TRANSFER-B: Recalibrated threshold in step regime
    k = int(np.ceil((len(scores_step_nulls) + 1) * 0.95)) - 1
    k = min(k, len(scores_step_nulls) - 1)
    tau_recal = float(np.sort(scores_step_nulls)[k])

    # Evaluate on fresh step nulls
    alarms_b = 0
    for rep in range(n_reps):
        seed = 115000 + rep
        r, _ = simulate(cfg_step, seed=seed, harm=False)
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
        det = EffectDetector(nuis, EffectParams(kind="hier"))
        out = det.run(adj)
        m_sc = float(np.nanmax(out.score[r.t0:]))
        if m_sc >= tau_recal:
            alarms_b += 1

    far_b = alarms_b / n_reps

    records = [
        {
            "transfer_mode": "TRANSFER-A (Source Threshold Frozen)",
            "source_threshold": tau_source,
            "target_regime": "step (+33.65%)",
            "achieved_far": far_a,
            "far_inflation": far_a - 0.05
        },
        {
            "transfer_mode": "TRANSFER-B (Recalibrated on Step)",
            "source_threshold": tau_recal,
            "target_regime": "step (+33.65%)",
            "achieved_far": far_b,
            "far_inflation": far_b - 0.05
        }
    ]
    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "ood_transfer.csv", index=False)
    print("OOD Transfer Results:")
    print(df.to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# 5. Computational Scaling Benchmark
# ---------------------------------------------------------------------------
def run_runtime_scaling(nuis: Nuisance) -> pd.DataFrame:
    print("Running Runtime Scaling Benchmark (N=10 to 500 hosts)...")
    cluster_sizes = [10, 25, 50, 100, 250, 500]
    records = []

    for N in cluster_sizes:
        nc = max(2, int(N * 0.10))
        cfg = SimConfig(n_hosts=N, n_canary=nc, t_pre=30, t_post=30)
        r, _ = simulate(cfg, seed=116000, harm=False)
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))

        det = EffectDetector(nuis, EffectParams(kind="hier"))

        # Measure 10 full runs
        latencies = []
        for _ in range(10):
            t_start = time.perf_counter()
            out = det.run(adj)
            latencies.append((time.perf_counter() - t_start) * 1000.0) # total ms

        per_step_ms = np.array(latencies) / (r.T - r.t0)
        records.append({
            "cluster_size_N": N,
            "canary_hosts_nc": nc,
            "p50_step_ms": float(np.percentile(per_step_ms, 50)),
            "p95_step_ms": float(np.percentile(per_step_ms, 95)),
            "p99_step_ms": float(np.percentile(per_step_ms, 99)),
            "total_runtime_ms": float(np.median(latencies))
        })

    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "runtime_scaling.csv", index=False)
    print("Runtime Scaling Results:")
    print(df.to_string(index=False))
    return df


if __name__ == "__main__":
    print("Starting Robustness & Scaling Battery (Gate G7)...")
    # Load calibrated threshold from Gate G6
    thresh_path = Path("external_validation_v1/artifacts/calibrated_thresholds.json")
    if thresh_path.exists():
        with open(thresh_path) as f:
            thresholds = json.load(f)
        tau_hier = thresholds.get("hier_ssm", 0.0)
    else:
        tau_hier = 0.0

    r_dev, _ = simulate(SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60), seed=99999, harm=False)
    nuis = fit_nuisance([r_dev])

    run_missingness_sweep(nuis, tau_hier, n_reps=25)
    run_contamination_sweep(nuis, tau_hier, n_reps=25)
    run_negative_controls(nuis, tau_hier, n_reps=40)
    run_ood_transfer(nuis, tau_hier, n_reps=40)
    run_runtime_scaling(nuis)
    print("Gate G7 Robustness Battery Complete!")
