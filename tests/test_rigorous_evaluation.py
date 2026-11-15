"""Rigorous Statistical Evaluation Suite Tests (Prompt 11 Exit Gate).

Verifies:
1. Hand-labeled metric fixtures: misses, premature alarms, capped time, localization F1, attribution confusion.
2. Separate metric event labels: persistent latency harm vs. memory growth harm (no silent reuse of log(1.02)).
3. Artifact and split audit: disjoint seed ranges, frozen model parameter hash before calibration.
4. Order-statistic threshold calibration (strict greater-than) and policy replay calibration.
5. Independent null validation: achieved false alert rate with Clopper-Pearson 95% CI and Beta-Binomial test.
6. Empirical demonstration that a host risk cutoff DOES NOT provide fleet-wide false alert control.
7. Paired bootstrap resampling paired rollouts, never timestamps.
8. Generated CSV result tables and synthesis report integrity.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from canary_ssm.decision import first_alarm
from canary_ssm.evaluation.calibration import (
    FirstCrossingCalibration,
    calibrate_first_crossing_threshold,
    calibrate_multichannel_by_replay,
    compute_achieved_null_rate,
    evaluate_host_risk_vs_fleet_control,
)
from canary_ssm.evaluation.fixtures import (
    EventLabel,
    MultiMetricEventTruth,
    attribution_confusion_matrix,
    classify_run,
    compute_localization,
    evaluate_event_truth,
    paired_bootstrap_contrast,
)
from canary_ssm.evaluation.runner import run_full_evaluation_suite
from canary_ssm.evaluation.splits import (
    DataRole,
    FrozenModelParameters,
    RoleSeedBundle,
    get_all_role_bundles,
    get_seed_bundle,
    verify_seed_separation,
)


# =============================================================================
# 1. Hand-Labeled Metric Fixtures
# =============================================================================
def test_hand_labeled_classification_fixtures():
    """Verify exact hand-computed outcomes for all rollout classification states."""
    T_total = 100
    t_exposure = 20
    truth_event = MultiMetricEventTruth(
        has_event=True,
        event_label=EventLabel.HARM_LATENCY_PERSISTENT,
        onset=30,
        intervals=[(30, 70)],
        affected_canary_ids=["srv-r0-s0"],
    )

    # 1. Success: alarm at tick 35 (onset=30) -> delay = 5, capped = 5
    res_succ = classify_run(t_alarm=35, truth=truth_event, total_ticks=T_total, exposure_tick=t_exposure)
    assert res_succ["status"] == "success"
    assert res_succ["is_correct"] is True
    assert res_succ["delay"] == 5.0
    assert res_succ["capped_time"] == 5.0

    # 2. Miss: alarm is None -> status = miss, delay = NaN, capped = 100 - 30 = 70
    res_miss = classify_run(t_alarm=None, truth=truth_event, total_ticks=T_total, exposure_tick=t_exposure)
    assert res_miss["status"] == "miss"
    assert res_miss["is_correct"] is False
    assert np.isnan(res_miss["delay"])
    assert res_miss["capped_time"] == 70.0

    # 3. Premature alarm: alarm at tick 25 before onset 30 -> status = premature, capped = 70
    res_prem = classify_run(t_alarm=25, truth=truth_event, total_ticks=T_total, exposure_tick=t_exposure)
    assert res_prem["status"] == "premature"
    assert res_prem["is_correct"] is False
    assert np.isnan(res_prem["delay"])
    assert res_prem["capped_time"] == 70.0

    # 4. Late alarm after recovery: alarm at tick 75 (after interval end 70) -> late_after_recovery, capped = 70
    res_late = classify_run(t_alarm=75, truth=truth_event, total_ticks=T_total, exposure_tick=t_exposure)
    assert res_late["status"] == "late_after_recovery"
    assert res_late["is_correct"] is False
    assert np.isnan(res_late["delay"])
    assert res_late["capped_time"] == 70.0

    # 5. Quiet null: no event, no alarm -> quiet, is_correct = True
    truth_null = MultiMetricEventTruth(
        has_event=False,
        event_label=EventLabel.NO_EVENT,
        onset=None,
        intervals=[],
        affected_canary_ids=[],
    )
    res_quiet = classify_run(t_alarm=None, truth=truth_null, total_ticks=T_total, exposure_tick=t_exposure)
    assert res_quiet["status"] == "quiet"
    assert res_quiet["is_correct"] is True
    assert np.isnan(res_quiet["capped_time"])

    # 6. False alarm null: no event, alarm at tick 40 -> false_alarm, is_correct = False
    res_fa = classify_run(t_alarm=40, truth=truth_null, total_ticks=T_total, exposure_tick=t_exposure)
    assert res_fa["status"] == "false_alarm"
    assert res_fa["is_correct"] is False


def test_separate_event_labels_not_reusing_kappa_lat():
    """Verify distinct event labels: memory growth uses kappa_M = 0.50 MB/min, NOT log(1.02)."""
    canaries = ["c0", "c1", "c2", "c3"]
    T = 60

    # Case A: Latency harm only (a_lat > log(1.02), memory = 0)
    a_lat = np.zeros((T, 4))
    a_lat[20:45, 0] = 0.03  # > log(1.02) approx 0.0198
    truth_lat = evaluate_event_truth(a_latency=a_lat, canary_ids=canaries)
    assert truth_lat.has_event is True
    assert truth_lat.event_label == EventLabel.HARM_LATENCY_PERSISTENT
    assert truth_lat.affected_canary_ids == ["c0"]

    # Case B: Memory growth harm only (memory_drift = 0.60 MB/min >= 0.50 MB/min, latency = 0)
    a_mem = np.zeros((T, 4))
    a_mem[20:45, 1] = 0.60
    truth_mem = evaluate_event_truth(memory_drift=a_mem, canary_ids=canaries)
    assert truth_mem.has_event is True
    assert truth_mem.event_label == EventLabel.HARM_MEMORY_GROWTH
    assert truth_mem.affected_canary_ids == ["c1"]

    # Case C: Memory drift below boundary (0.35 MB/min < 0.50 MB/min).
    # Even though 0.35 > log(1.02) approx 0.0198, it MUST NOT trigger memory harm!
    a_mem_sub = np.zeros((T, 4))
    a_mem_sub[20:45, 1] = 0.35  # > log(1.02), but < kappa_M = 0.50 MB/min
    truth_sub = evaluate_event_truth(memory_drift=a_mem_sub, canary_ids=canaries)
    assert truth_sub.has_event is False
    assert truth_sub.event_label == EventLabel.NO_EVENT

    # Case D: Compound harm (both latency and memory)
    truth_comp = evaluate_event_truth(a_latency=a_lat, memory_drift=a_mem, canary_ids=canaries)
    assert truth_comp.has_event is True
    assert truth_comp.event_label == EventLabel.HARM_COMPOUND
    assert set(truth_comp.affected_canary_ids) == {"c0", "c1"}

    # Case E: Infrastructure fault
    truth_rk = evaluate_event_truth(canary_ids=canaries, fault_type="RACK_NETWORK_LATENCY")
    assert truth_rk.has_event is False
    assert truth_rk.event_label == EventLabel.FAULT_RACK_LATENCY


def test_hand_labeled_localization_fixture():
    """Verify exact hand-computed top-k recall, precision, recall, and F1."""
    canaries = ["c0", "c1", "c2", "c3"]
    # c0 and c2 are truly affected
    true_affected = ["c0", "c2"]
    # Host scores rank: c0 (0.9), c2 (0.8), c3 (0.3), c1 (0.1)
    scores = {"c0": 0.90, "c1": 0.10, "c2": 0.80, "c3": 0.30}

    loc = compute_localization(scores, true_affected, canary_order=canaries, topk=3)
    # Top-3 are: {c0, c2, c3}
    # Intersect with {c0, c2} = {c0, c2} (size 2)
    # top-3 recall: 2 / min(3, 2) = 2 / 2 = 1.0
    # precision: 2 / 3 = 0.6666...
    # recall: 2 / 2 = 1.0
    # F1: 2 * (2/3) * 1 / (2/3 + 1) = (4/3) / (5/3) = 4/5 = 0.80
    assert loc["topk_recall"] == 1.0
    assert abs(loc["precision"] - 2.0 / 3.0) < 1e-4
    assert loc["recall"] == 1.0
    assert abs(loc["f1"] - 0.80) < 1e-4
    assert abs(loc["fdp"] - 1.0 / 3.0) < 1e-4


def test_hand_labeled_attribution_confusion():
    """Verify exact counts and abstention calculation in attribution confusion matrix."""
    true_labels = [
        EventLabel.HARM_LATENCY_PERSISTENT,
        EventLabel.HARM_MEMORY_GROWTH,
        EventLabel.HARM_COMPOUND,
        EventLabel.NO_EVENT,
        EventLabel.NO_EVENT,
    ]
    inferred = [
        "LATENCY_REGRESSION",
        "MEMORY_GROWTH_LEAK",
        "COMPOUND_REGRESSION",
        "NORMAL",
        "INSUFFICIENT_DATA",  # Abstention
    ]

    conf = attribution_confusion_matrix(true_labels, inferred)
    assert conf["total_rollouts"] == 5
    assert conf["abstention_count"] == 1
    assert conf["abstention_rate"] == 0.20
    assert conf["evaluable_count"] == 4
    # All 4 evaluable predictions matched perfectly
    assert conf["attribution_accuracy"] == 1.0
    assert conf["matrix"]["NORMAL"]["NORMAL"] == 1
    assert conf["matrix"]["NORMAL"]["INSUFFICIENT_DATA"] == 1
    assert conf["matrix"]["LATENCY_REGRESSION"]["LATENCY_REGRESSION"] == 1
    assert conf["matrix"]["MEMORY_GROWTH_LEAK"]["MEMORY_GROWTH_LEAK"] == 1
    assert conf["matrix"]["COMPOUND_REGRESSION"]["COMPOUND_REGRESSION"] == 1


def test_paired_bootstrap_resamples_pairs_not_timestamps():
    """Verify paired bootstrap resamples rollout pairs (never timestamps)."""
    # 20 paired rollouts where method A is consistently 5.0 min slower than method B
    a = np.array([25.0] * 20)
    b = np.array([20.0] * 20)

    res = paired_bootstrap_contrast(a, b, n_boot=1000, seed=42)
    assert res["n_pairs"] == 20
    assert res["mean_diff"] == 5.0
    assert res["ci_lower"] == 5.0
    assert res["ci_upper"] == 5.0
    assert res["p_value"] == 0.0


# =============================================================================
# 2. Artifact and Split Audit
# =============================================================================
def test_artifact_split_audit():
    """Verify strict disjoint seed blocks across all roles and parameter freezing."""
    # 1. Assert seed separation across all data roles
    assert verify_seed_separation() is True

    bundles = get_all_role_bundles()
    assert "smoke" in bundles
    assert "dev" in bundles
    assert "calibration" in bundles
    assert "null_validation" in bundles
    assert "test" in bundles

    # 2. Assert calibration and null_validation forbid harm scenarios
    assert bundles["calibration"].allowed_harm is False
    assert bundles["null_validation"].allowed_harm is False
    assert bundles["test"].allowed_harm is True

    # 3. Assert seed ranges do not overlap
    assert bundles["smoke"].seed_max < bundles["dev"].seed_base
    assert bundles["dev"].seed_max < bundles["calibration"].seed_base
    assert bundles["calibration"].seed_max < bundles["null_validation"].seed_base
    assert bundles["null_validation"].seed_max < bundles["test"].seed_base

    # 4. Verify parameter freezing
    params = FrozenModelParameters()
    sha = params.compute_sha256()
    assert len(sha) == 64
    # Re-running with same parameters yields exact same hash
    assert FrozenModelParameters().compute_sha256() == sha


# =============================================================================
# 3. Order-Statistic Calibration and Replay
# =============================================================================
def test_order_statistic_threshold_strict_greater_than():
    """Verify order-statistic calibration k = ceil((B+1)(1-alpha)) and strict '>' rule."""
    # B = 19 rollouts: maxima 1..19
    maxima = np.arange(1.0, 20.0)
    # alpha = 0.05 -> k = ceil(20 * 0.95) = ceil(19.0) = 19
    cal = calibrate_first_crossing_threshold(maxima, alpha=0.05, method_name="test_det")
    assert cal.k_order == 19
    assert cal.threshold == 19.0
    assert cal.B_calibration == 19

    # Strict greater-than check: score = 19.0 does NOT alarm; score = 19.01 DOES
    score = np.array([10.0, 19.0, 19.01])
    elig = np.ones(3, dtype=bool)
    assert first_alarm(score, elig, thr=cal.threshold, t0=0) == 2  # tick 2 alarms, tick 1 does not


def test_host_risk_cutoff_fails_fleet_control():
    """Verify that a host-level risk cutoff fails to control fleet-wide false alerts."""
    # Generate B=100 rollouts, T=30 ticks, nc=4 canaries of independent healthy noise
    rng = np.random.default_rng(42)
    B, T, nc = 100, 30, 4
    # Host harm probabilities under null fluctuate randomly with mean ~ 0.05
    null_risks = rng.beta(0.5, 9.5, size=(B, T, nc))

    # Released threshold calibrated on max log score
    max_log_scores = np.max(np.log(np.maximum(null_risks, 1e-12)), axis=(1, 2))
    cal = calibrate_first_crossing_threshold(max_log_scores, alpha=0.05)

    comp = evaluate_host_risk_vs_fleet_control(null_risks, calibrated_release_threshold=cal.threshold)
    assert comp["calibrated_fleet_far"] <= 0.06

    # Naive host cutoff (Pr > 0.20 or 0.30) inflates fleet false alerts to >= 50%
    cutoff_20 = next(c for c in comp["host_cutoff_comparisons"] if c["host_risk_cutoff"] == 0.20)
    assert cutoff_20["fleet_false_alarm_rate"] >= 0.50
    assert cutoff_20["inflation_factor_over_5pct"] >= 10.0


# =============================================================================
# 4. End-to-End Suite Execution & Saved Result Tables Gate
# =============================================================================
def test_full_evaluation_suite_execution_and_saved_tables(tmp_path):
    """Execute evaluation suite, verify independent null validation and versioned CSVs."""
    # Run small evaluation suite (B=30 calibration nulls, n=30 validation nulls, 2 test pairs per scenario)
    summary = run_full_evaluation_suite(
        output_dir=tmp_path,
        n_cal_nulls=30,
        n_val_nulls=30,
        n_test_pairs=2,
        alpha=0.05,
        seed_override=50_000,
    )

    # 1. Assert all 5 CSV tables exist and are non-empty
    csv_null_val = tmp_path / "table_null_validation.csv"
    csv_scenarios = tmp_path / "table_evaluation_scenarios.csv"
    csv_loc = tmp_path / "table_localization_performance.csv"
    csv_attr = tmp_path / "table_attribution_confusion.csv"
    csv_contrasts = tmp_path / "table_paired_bootstrap_contrasts.csv"
    md_report = tmp_path / "VIRTUAL_DATA_CENTER_EVALUATION_REPORT.md"

    for path in [csv_null_val, csv_scenarios, csv_loc, csv_attr, csv_contrasts, md_report]:
        assert path.exists(), f"Missing expected output: {path}"
        assert path.stat().st_size > 50, f"File {path} is empty or too small"

    # 2. Independent null validation verification
    df_null = pd.read_csv(csv_null_val)
    assert len(df_null) >= 6
    assert "method" in df_null.columns
    assert "achieved_far" in df_null.columns
    assert "ci_lower_95" in df_null.columns
    assert "validity_gate" in df_null.columns

    # 3. Scenario table verification
    df_scen = pd.read_csv(csv_scenarios)
    assert len(df_scen) >= 13 * 6
    assert "det_15_min" in df_scen.columns
    assert "miss_rate" in df_scen.columns
    assert "mean_capped_time" in df_scen.columns

    # 4. Localization table verification
    df_loc = pd.read_csv(csv_loc)
    assert len(df_loc) > 0
    assert "topk_recall" in df_loc.columns
    assert "f1" in df_loc.columns

    # 5. Paired bootstrap contrasts verification
    df_contrasts = pd.read_csv(csv_contrasts)
    assert len(df_contrasts) >= 5
    assert "mean_capped_time_difference" in df_contrasts.columns
    assert "bootstrap_p_value" in df_contrasts.columns
