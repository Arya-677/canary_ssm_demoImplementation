"""
Comprehensive External Benchmarking and Confirmatory Validation Runner (Gate G6).
Evaluates 9 methods head-to-head across 12 Null and 14 Harmful scenarios:
1. hier_ssm (Hierarchical SSM)
2. indep_ssm (Independent SSM)
3. no_inertia_ssm (No-Inertia SSM ablation)
4. kayenta_judge (Kayenta rolling Mann-Whitney U judge)
5. argo_policy (Argo Rollouts AR-3 analysis policy)
6. flagger_policy (Flagger metric analysis policy)
7. slo_threshold (Contrast delta comparator)
8. adj_cusum (Workload-adjusted CUSUM)
9. glr_window (Generalized Likelihood Ratio window)

Includes:
- B=1,000 null calibration with exact order-statistic thresholds
- Gate G2 Beta-Binomial validity audit
- Paired sign-flip permutation tests (5,000 permutations)
- Holm multiplicity adjustment
- Bootstrap 95% confidence intervals
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import binom

from canary_ssm.baselines import adjusted_cusum
from canary_ssm.baselines_extra import glr_window
from canary_ssm.comparators import (
    KayentaJudge, KayentaConfig,
    SLOThresholdComparator, SLOConfig,
    ArgoRolloutsPolicy, ArgoPolicyConfig,
    FlaggerPolicy, FlaggerPolicyConfig,
    NoInertiaSSM
)
from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.preprocess import fit_nuisance, Nuisance
from canary_ssm.simulate import SimConfig, simulate

ARTIFACTS_DIR = Path("external_validation_v1/artifacts")
RESULTS_DIR = Path("external_validation_v1/results")
PER_ROLLOUT_DIR = Path("external_validation_v1/results/per_rollout")
for p in [ARTIFACTS_DIR, RESULTS_DIR, PER_ROLLOUT_DIR]:
    p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------
def get_scenarios() -> dict[str, dict]:
    scenarios = {}

    # 12 NULL Scenarios
    scenarios["NULL-01_stationary"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60)}
    scenarios["NULL-02_step"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, workload_step=0.3365)}
    scenarios["NULL-03_diurnal"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, workload_amp=0.2, workload_period=60)}
    scenarios["NULL-04_spike"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, spike_n=2, spike_len=5, spike_mag=0.15)}
    scenarios["NULL-05_heavy_tail"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, heavy_tail_df=3)}
    scenarios["NULL-06_hetero_noise"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, host_mu_sd=0.25)}
    scenarios["NULL-07_missing_mcar"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, missing_rate=0.10)}
    scenarios["NULL-08_burst_missing"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, missing_rate=0.10, burst_len=5)}
    scenarios["NULL-09_contam_ctrl"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, contam_frac=0.10)}
    scenarios["NULL-10_label_error"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, label_error=0.30)}
    scenarios["NULL-11_late_arrival"] = {"type": "null", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, late_frac=0.20, late_delay=3)}
    scenarios["NULL-12_cluster_scale"] = {"type": "null", "cfg": SimConfig(n_hosts=50, n_canary=5, t_pre=60, t_post=60)}

    # 14 HARM Scenarios
    scenarios["HARM-01_sparse"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.0, duration=45)}
    scenarios["HARM-02_class_wide"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, affected_mode="class0", effect_pct=3.0, duration=45)}
    scenarios["HARM-03_broad"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=4, effect_pct=3.0, duration=45)}
    scenarios["HARM-04_weak_sparse"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=2.0, duration=45)}
    scenarios["HARM-05_single_canary"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=1, effect_pct=5.0, duration=45)}
    scenarios["HARM-06_ramp_onset"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, shape="ramp", ramp_len=15, effect_pct=4.0, duration=45)}
    scenarios["HARM-07_transient_decay"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.5, duration=20, decay_len=15)}
    scenarios["HARM-08_sparse_step"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.0, duration=45, workload_step=0.3365)}
    scenarios["HARM-09_class_step"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, affected_mode="class0", effect_pct=3.0, duration=45, workload_step=0.3365)}
    scenarios["HARM-10_heavy_tail"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.5, duration=45, heavy_tail_df=3)}
    scenarios["HARM-11_missingness"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.5, duration=45, missing_rate=0.20)}
    scenarios["HARM-12_contam"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.5, duration=45, contam_frac=0.10)}
    scenarios["HARM-13_label_error"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, affected_mode="class0", effect_pct=3.5, duration=45, label_error=0.30)}
    scenarios["HARM-14_delayed_onset"] = {"type": "harm", "cfg": SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60, n_affected=2, effect_pct=3.5, duration=45, onset_delay=10)}

    return scenarios


# ---------------------------------------------------------------------------
# Detector Evaluator
# ---------------------------------------------------------------------------
def evaluate_rollout(r, nuis: Nuisance, thresholds: dict[str, float]) -> dict[str, dict]:
    adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
    t0 = r.t0
    T = r.T

    methods = {
        "hier_ssm": lambda a: EffectDetector(nuis, EffectParams(kind="hier")).run(a),
        "indep_ssm": lambda a: EffectDetector(nuis, EffectParams(kind="indep")).run(a),
        "no_inertia_ssm": lambda a: NoInertiaSSM(nuis).run(a),
        "kayenta_judge": lambda a: KayentaJudge().run(a),
        "argo_policy": lambda a: ArgoRolloutsPolicy().run(a),
        "flagger_policy": lambda a: FlaggerPolicy().run(a),
        "slo_threshold": lambda a: SLOThresholdComparator().run(a),
        "adj_cusum": lambda a: adjusted_cusum(a, k=0.25),
        "glr_window": lambda a: glr_window(a, W=15),
    }

    results = {}
    for name, fn in methods.items():
        out = fn(adj)
        score_post = out.score[t0:]
        max_score = float(np.nanmax(score_post)) if len(score_post) > 0 and np.isfinite(score_post).any() else -np.inf
        tau = thresholds.get(name, 0.0)

        # Alarm condition
        alarm = bool(max_score >= tau)
        if alarm:
            # First crossing index relative to t0
            crossing_indices = np.flatnonzero(score_post >= tau)
            alarm_rel = int(crossing_indices[0])
            alarm_time = t0 + alarm_rel
            delay = float(alarm_rel)
        else:
            alarm_time = -1
            delay = np.nan

        # Premature alarm check
        score_pre = out.score[:t0]
        premature = bool(np.isfinite(score_pre).any() and (np.nanmax(score_pre) >= tau))

        results[name] = {
            "alarm": alarm,
            "alarm_time": alarm_time,
            "delay": delay,
            "premature": premature,
            "max_score": max_score,
            "runtime_ms": out.runtime_ms
        }
    return results


# ---------------------------------------------------------------------------
# Calibration Routine
# ---------------------------------------------------------------------------
def calibrate_thresholds(nuis: Nuisance, B: int = 1000, alpha: float = 0.05) -> dict[str, float]:
    print(f"Calibrating {B} null rollouts at alpha={alpha}...")
    cfg = SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60)
    methods = [
        "hier_ssm", "indep_ssm", "no_inertia_ssm",
        "kayenta_judge", "argo_policy", "flagger_policy",
        "slo_threshold", "adj_cusum", "glr_window"
    ]
    max_scores = {m: [] for m in methods}

    for b in range(B):
        seed = 100000 + b
        r, _ = simulate(cfg, seed=seed, harm=False)
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
        t0 = r.t0

        out_hier = EffectDetector(nuis, EffectParams(kind="hier")).run(adj)
        out_indep = EffectDetector(nuis, EffectParams(kind="indep")).run(adj)
        out_no_inertia = NoInertiaSSM(nuis).run(adj)
        out_kay = KayentaJudge().run(adj)
        out_argo = ArgoRolloutsPolicy().run(adj)
        out_flag = FlaggerPolicy().run(adj)
        out_slo = SLOThresholdComparator().run(adj)
        out_cusum = adjusted_cusum(adj, k=0.25)
        out_glr = glr_window(adj, W=15)

        max_scores["hier_ssm"].append(np.nanmax(out_hier.score[t0:]))
        max_scores["indep_ssm"].append(np.nanmax(out_indep.score[t0:]))
        max_scores["no_inertia_ssm"].append(np.nanmax(out_no_inertia.score[t0:]))
        max_scores["kayenta_judge"].append(np.nanmax(out_kay.score[t0:]))
        max_scores["argo_policy"].append(np.nanmax(out_argo.score[t0:]))
        max_scores["flagger_policy"].append(np.nanmax(out_flag.score[t0:]))
        max_scores["slo_threshold"].append(np.nanmax(out_slo.score[t0:]))
        max_scores["adj_cusum"].append(np.nanmax(out_cusum.score[t0:]))
        max_scores["glr_window"].append(np.nanmax(out_glr.score[t0:]))

    k = int(np.ceil((B + 1) * (1.0 - alpha))) - 1  # 0-indexed order statistic
    k = min(k, B - 1)

    thresholds = {}
    for m in methods:
        arr = np.sort(np.array(max_scores[m]))
        tau = float(arr[k])
        thresholds[m] = tau
        print(f"  {m:16s} -> threshold tau = {tau:.5f}")

    with open(ARTIFACTS_DIR / "calibrated_thresholds.json", "w") as f:
        json.dump(thresholds, f, indent=2)

    return thresholds


# ---------------------------------------------------------------------------
# Validation Gate Audit
# ---------------------------------------------------------------------------
def audit_gate_g2(nuis: Nuisance, thresholds: dict[str, float], n_val: int = 500, alpha: float = 0.05) -> pd.DataFrame:
    print(f"Auditing Gate G2 validity on {n_val} independent null rollouts...")
    cfg = SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60)
    methods = list(thresholds.keys())
    alarms = {m: 0 for m in methods}

    for b in range(n_val):
        seed = 101000 + b
        r, _ = simulate(cfg, seed=seed, harm=False)
        res = evaluate_rollout(r, nuis, thresholds)
        for m in methods:
            if res[m]["alarm"]:
                alarms[m] += 1

    records = []
    for m in methods:
        k_alarms = alarms[m]
        far = k_alarms / n_val
        # Exact one-sided binomial test against upper bound
        p_val = float(binom.sf(k_alarms - 1, n_val, alpha))
        passed = (far <= 0.075) and (p_val >= 0.01)
        records.append({
            "method": m,
            "threshold": thresholds[m],
            "n_val": n_val,
            "alarms": k_alarms,
            "achieved_far": far,
            "binom_pval": p_val,
            "gate_g2_pass": passed
        })

    df = pd.DataFrame(records)
    df.to_csv(RESULTS_DIR / "gate_g2_audit.csv", index=False)
    print("Gate G2 Audit Results:")
    print(df.to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# Confirmatory Benchmark Evaluation
# ---------------------------------------------------------------------------
def run_benchmark(nuis: Nuisance, thresholds: dict[str, float], pairs_per_scen: int = 50) -> pd.DataFrame:
    scenarios = get_scenarios()
    methods = list(thresholds.keys())
    per_rollout_records = []

    print(f"Running confirmatory benchmark across {len(scenarios)} scenarios ({pairs_per_scen} paired rollouts each)...")
    seed_base = 102000

    for s_idx, (scen_name, scen_info) in enumerate(scenarios.items()):
        cfg = scen_info["cfg"]
        is_null_scen = scen_info["type"] == "null"
        t_start = time.perf_counter()

        for p in range(pairs_per_scen):
            pair_seed = seed_base + s_idx * 1000 + p

            # Paired simulation
            r_harm, _ = simulate(cfg, seed=pair_seed, harm=True, pair_id=p)
            r_null, _ = simulate(cfg, seed=pair_seed, harm=False, pair_id=p)

            res_harm = evaluate_rollout(r_harm, nuis, thresholds)
            res_null = evaluate_rollout(r_null, nuis, thresholds)

            for m in methods:
                # Record harm rollout
                per_rollout_records.append({
                    "rollout_id": f"{scen_name}_p{p}_harm",
                    "scenario": scen_name,
                    "scen_type": scen_info["type"],
                    "pair_id": p,
                    "method": m,
                    "harm": True,
                    "alarm": res_harm[m]["alarm"],
                    "alarm_time": res_harm[m]["alarm_time"],
                    "delay": res_harm[m]["delay"],
                    "premature": res_harm[m]["premature"],
                    "max_score": res_harm[m]["max_score"],
                    "runtime_ms": res_harm[m]["runtime_ms"]
                })
                # Record null rollout
                per_rollout_records.append({
                    "rollout_id": f"{scen_name}_p{p}_null",
                    "scenario": scen_name,
                    "scen_type": scen_info["type"],
                    "pair_id": p,
                    "method": m,
                    "harm": False,
                    "alarm": res_null[m]["alarm"],
                    "alarm_time": res_null[m]["alarm_time"],
                    "delay": res_null[m]["delay"],
                    "premature": res_null[m]["premature"],
                    "max_score": res_null[m]["max_score"],
                    "runtime_ms": res_null[m]["runtime_ms"]
                })

        elapsed = time.perf_counter() - t_start
        print(f"  [{s_idx+1:02d}/{len(scenarios):02d}] {scen_name:24s} completed in {elapsed:.2f}s")

    df_per = pd.DataFrame(per_rollout_records)
    df_per.to_csv(PER_ROLLOUT_DIR / "external_benchmark_per_rollout.csv", index=False)
    print("Saved per-rollout evaluation to:", PER_ROLLOUT_DIR / "external_benchmark_per_rollout.csv")

    # -----------------------------------------------------------------------
    # Summary Metrics and Statistical Hypothesis Tests
    # -----------------------------------------------------------------------
    summary_records = []
    # Evaluate across all harmful scenarios combined and per scenario
    harm_df = df_per[df_per["harm"] == True]
    null_df = df_per[df_per["harm"] == False]

    for scen_name in ["OVERALL_HARMFUL"] + list(scenarios.keys()):
        if scen_name == "OVERALL_HARMFUL":
            sub_harm = harm_df[harm_df["scen_type"] == "harm"]
            sub_null = null_df[null_df["scen_type"] == "null"]
        else:
            sub_harm = harm_df[harm_df["scenario"] == scen_name]
            sub_null = null_df[null_df["scenario"] == scen_name]

        # Extract hierarchical delays as reference for paired differences
        hier_delays = sub_harm[sub_harm["method"] == "hier_ssm"].set_index(["scenario", "pair_id"])["delay"]

        for m in methods:
            m_sub_harm = sub_harm[sub_harm["method"] == m]
            m_sub_null = sub_null[sub_null["method"] == m]

            power = float(np.mean(m_sub_harm["alarm"])) if len(m_sub_harm) > 0 else 0.0
            far = float(np.mean(m_sub_null["alarm"])) if len(m_sub_null) > 0 else 0.0
            premature_rate = float(np.mean(m_sub_harm["premature"])) if len(m_sub_harm) > 0 else 0.0

            # Conditional delay (on alarmed rollouts)
            valid_delays = m_sub_harm["delay"].dropna()
            mean_delay = float(np.mean(valid_delays)) if len(valid_delays) > 0 else np.nan
            median_delay = float(np.median(valid_delays)) if len(valid_delays) > 0 else np.nan

            # Capped time-to-success (15 min qualifying event, capped at 45)
            capped_delay = np.where(m_sub_harm["alarm"], np.nan_to_num(m_sub_harm["delay"], nan=45.0), 45.0)
            mean_capped_t2s = float(np.mean(capped_delay))

            # Paired difference against hier_ssm
            m_delays = m_sub_harm.set_index(["scenario", "pair_id"])["delay"]
            common_pairs = hier_delays.dropna().index.intersection(m_delays.dropna().index)
            if len(common_pairs) > 5 and m != "hier_ssm":
                d_diff = m_delays.loc[common_pairs].values - hier_delays.loc[common_pairs].values
                mean_diff = float(np.mean(d_diff))

                # Sign-flip permutation test (5,000 permutations)
                rng = np.random.default_rng(42)
                flips = rng.choice([-1.0, 1.0], size=(5000, len(d_diff)))
                perm_means = np.mean(flips * d_diff[None, :], axis=1)
                pval_signflip = float(np.mean(np.abs(perm_means) >= np.abs(mean_diff)))

                # 95% bootstrap CI
                boot_idx = rng.integers(0, len(d_diff), size=(2000, len(d_diff)))
                boot_means = np.mean(d_diff[boot_idx], axis=1)
                ci_lo = float(np.percentile(boot_means, 2.5))
                ci_hi = float(np.percentile(boot_means, 97.5))
            else:
                mean_diff = 0.0 if m == "hier_ssm" else np.nan
                pval_signflip = 1.0
                ci_lo = np.nan
                ci_hi = np.nan

            summary_records.append({
                "scenario": scen_name,
                "method": m,
                "n_eval": len(m_sub_harm),
                "power": power,
                "far": far,
                "premature_rate": premature_rate,
                "mean_delay": mean_delay,
                "median_delay": median_delay,
                "mean_capped_t2s": mean_capped_t2s,
                "delta_delay_vs_hier": mean_diff,
                "pval_signflip": pval_signflip,
                "ci_95_lo": ci_lo,
                "ci_95_hi": ci_hi
            })

    df_summary = pd.DataFrame(summary_records)

    # Apply Holm step-down correction to overall harmful p-values
    sub_overall = df_summary[df_summary["scenario"] == "OVERALL_HARMFUL"].copy()
    valid_pvals = sub_overall[sub_overall["method"] != "hier_ssm"]["pval_signflip"].values
    methods_pvals = sub_overall[sub_overall["method"] != "hier_ssm"]["method"].values

    sort_idx = np.argsort(valid_pvals)
    m_tests = len(valid_pvals)
    holm_pvals = np.zeros(m_tests)
    cum_max = 0.0
    for rank, idx in enumerate(sort_idx):
        p_adj = min(1.0, valid_pvals[idx] * (m_tests - rank))
        cum_max = max(cum_max, p_adj)
        holm_pvals[idx] = cum_max

    holm_map = dict(zip(methods_pvals, holm_pvals))
    df_summary["pval_holm"] = df_summary["method"].map(holm_map)

    df_summary.to_csv(RESULTS_DIR / "external_benchmark_summary.csv", index=False)
    print("Saved summary metrics to:", RESULTS_DIR / "external_benchmark_summary.csv")

    print("\nOVERALL HARMFUL SUMMARY BENCHMARK:")
    print(df_summary[df_summary["scenario"] == "OVERALL_HARMFUL"][[
        "method", "power", "far", "mean_delay", "mean_capped_t2s", "delta_delay_vs_hier", "pval_signflip"
    ]].to_string(index=False))

    return df_summary


if __name__ == "__main__":
    print("Initializing External Benchmark Suite (Gate G6)...")
    # Calibrate nuisance on baseline data
    r_dev, _ = simulate(SimConfig(n_hosts=12, n_canary=4, t_pre=60, t_post=60), seed=99999, harm=False)
    nuis = fit_nuisance([r_dev])

    # Step 1: Calibration (B=1000 nulls)
    thresholds = calibrate_thresholds(nuis, B=1000, alpha=0.05)

    # Step 2: Gate G2 validity audit (N=500 nulls)
    audit_gate_g2(nuis, thresholds, n_val=500, alpha=0.05)

    # Step 3: Confirmatory Benchmark Execution (26 scenarios x 50 pairs = 1,300 rollouts)
    run_benchmark(nuis, thresholds, pairs_per_scen=50)

    print("\nExternal Benchmarking and Confirmatory Testing Complete!")
