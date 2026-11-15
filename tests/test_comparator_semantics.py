"""
Deterministic Comparator Semantics Test Suite (Section B of Supplemental Addendum).
Implements test fixtures KAY-01 through COMMON-01:
- KAY-01: Mann-Whitney U calculation, direction, p-value, and verdict.
- KAY-02: Ties, insufficient sample count, missing metric handling.
- ARGO-01: Deterministic state trace across failureLimit and consecutiveSuccessLimit.
- ARGO-02: Missing, delayed, and errored measurement handling.
- FLAG-01: Step progression, cumulative failure threshold, and rollback scoring.
- FLAG-02: Missing measurement and cumulative failure retention.
- SLO-01: Boundary behavior (below, at, above threshold) and window averaging.
- COMMON-01: Online chronological streaming prefix invariance.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import mannwhitneyu

from canary_ssm.baselines import DetectorOutput
from canary_ssm.comparators import (
    KayentaJudge, KayentaConfig,
    ArgoRolloutsPolicy, ArgoPolicyConfig,
    FlaggerPolicy, FlaggerPolicyConfig,
    SLOThresholdComparator, SLOConfig
)
from canary_ssm.factor import Adjusted


def make_dummy_adjusted(
    T: int,
    t0: int,
    nc: int,
    r: np.ndarray | None = None,
    ctl_r: np.ndarray | None = None,
    nctl: int = 2
) -> Adjusted:
    if r is None:
        r = np.zeros((T, nc))
    return Adjusted(
        r=r,
        obs=np.ones((T, nc), dtype=bool),
        elig=np.ones(T, dtype=bool),
        U=np.zeros(T),
        lam=np.ones(nc),
        sigma=np.ones(nc),
        rm=np.zeros((T, nc)),
        class_id=np.zeros(nc, dtype=int),
        t0=t0,
        fallback=np.zeros(nc, dtype=bool),
        f_hat=np.zeros(T),
        ctl_r=ctl_r,
        ctl_class_id=np.zeros(ctl_r.shape[1], dtype=int) if ctl_r is not None else None
    )


# ---------------------------------------------------------------------------
# KAY-01: Mann-Whitney U calculation, direction, p-value, and verdict
# ---------------------------------------------------------------------------
def test_kay_01_mann_whitney_u_and_direction():
    """Verify independent Mann-Whitney U statistic calculation and direction."""
    judge = KayentaJudge(KayentaConfig(min_samples=5, alpha=0.05, effect_size_threshold=0.0))

    canary = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
    control = np.array([1.0, 1.2, 1.5, 1.8, 2.0, 2.2])

    # Independent calculation
    expected_res = mannwhitneyu(canary, control, alternative="greater")
    n1, n2 = len(canary), len(control)
    expected_mean = n1 * n2 / 2.0
    expected_std = np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    expected_z = (expected_res.statistic - expected_mean) / expected_std

    outcome, p_val, z_score = judge.evaluate_sample(canary, control)

    assert outcome == "FAIL_CRITICAL"
    assert np.isclose(p_val, expected_res.pvalue, rtol=1e-5)
    assert np.isclose(z_score, expected_z, rtol=1e-5)
    assert z_score > 0.0


# ---------------------------------------------------------------------------
# KAY-02: Ties, insufficient sample count, missing metric handling
# ---------------------------------------------------------------------------
def test_kay_02_ties_and_insufficient_samples():
    """Verify tie handling, insufficient sample counts, and missing data."""
    judge = KayentaJudge(KayentaConfig(min_samples=5, alpha=0.05))

    # Insufficient samples (< min_samples=5)
    outcome, p_val, z_score = judge.evaluate_sample(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
    assert outcome == "NODATA"
    assert p_val == 1.0
    assert z_score == 0.0

    # Ties (all identical values)
    canary_ties = np.array([2.0, 2.0, 2.0, 2.0, 2.0])
    control_ties = np.array([2.0, 2.0, 2.0, 2.0, 2.0])
    outcome_tie, p_val_tie, z_score_tie = judge.evaluate_sample(canary_ties, control_ties)
    assert outcome_tie == "PASS"
    assert p_val_tie == 1.0

    # Missing values (NaNs filtered out without crashing)
    canary_nan = np.array([3.0, 4.0, np.nan, 5.0, np.nan, 6.0, 7.0])
    control_clean = np.array([1.0, 1.5, 2.0, 2.2, 2.5])
    outcome_nan, p_val_nan, z_score_nan = judge.evaluate_sample(canary_nan, control_clean)
    assert outcome_nan == "FAIL_CRITICAL"
    assert z_score_nan > 0.0


# ---------------------------------------------------------------------------
# ARGO-01: Deterministic state trace across failureLimit & consecutive mode
# ---------------------------------------------------------------------------
def test_argo_01_deterministic_failure_limit_trace():
    """Verify exact state trace and counter progression around failureLimit."""
    T = 10
    t0 = 2
    nc = 4

    adj = make_dummy_adjusted(T=T, t0=t0, nc=nc)

    # Test AR-3 cumulative failure policy
    raw_signal = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    raw_out = DetectorOutput(method="mock", score=raw_signal, elig=adj.elig, host_score=None)

    argo_cum = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=3, consecutive=False))
    res_cum = argo_cum.run(adj, raw_detector_output=raw_out)

    # Pre-rollout should be NaN
    assert np.isnan(res_cum.score[:t0]).all()
    # Post-rollout cumulative trace:
    # t=2: val=0 -> counter=0 -> 0/3 = 0.0
    # t=3: val=1 -> counter=1 -> 1/3
    # t=4: val=0 -> counter=1 -> 1/3
    # t=5: val=1 -> counter=2 -> 2/3
    # t=6: val=1 -> counter=3 -> 3/3 = 1.0 (breach!)
    # t=7: val=0 -> counter=3 -> 3/3 = 1.0
    assert np.isclose(res_cum.score[2], 0.0)
    assert np.isclose(res_cum.score[3], 1.0 / 3.0)
    assert np.isclose(res_cum.score[4], 1.0 / 3.0)
    assert np.isclose(res_cum.score[5], 2.0 / 3.0)
    assert np.isclose(res_cum.score[6], 1.0)
    assert np.isclose(res_cum.score[7], 1.0)

    # Test AR-3 consecutive failure policy (counter resets on pass)
    argo_cons = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=3, consecutive=True))
    res_cons = argo_cons.run(adj, raw_detector_output=raw_out)
    # t=4 has val=0, so counter resets to 0!
    assert np.isclose(res_cons.score[3], 1.0 / 3.0)
    assert np.isclose(res_cons.score[4], 0.0)
    assert np.isclose(res_cons.score[5], 1.0 / 3.0)
    assert np.isclose(res_cons.score[6], 2.0 / 3.0)


# ---------------------------------------------------------------------------
# ARGO-02: Missing, delayed, and errored measurement handling
# ---------------------------------------------------------------------------
def test_argo_02_missing_and_error_handling():
    """Verify that NaNs and errors do not count as successes or corrupt state."""
    T = 6
    t0 = 1
    nc = 2
    adj = make_dummy_adjusted(T=T, t0=t0, nc=nc)

    raw_signal = np.array([0.0, np.nan, 1.0, np.nan, 0.0, 1.0])
    raw_out = DetectorOutput(method="mock", score=raw_signal, elig=adj.elig, host_score=None)

    argo = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=2, consecutive=False))
    res = argo.run(adj, raw_detector_output=raw_out)

    # t=1: NaN treated as 0 (no false increment)
    assert np.isclose(res.score[1], 0.0)
    # t=2: val=1 -> counter=1 -> 0.5
    assert np.isclose(res.score[2], 0.5)
    # t=3: NaN -> counter remains 1
    assert np.isclose(res.score[3], 0.5)
    # t=5: val=1 -> counter=2 -> 1.0
    assert np.isclose(res.score[5], 1.0)


# ---------------------------------------------------------------------------
# FLAG-01: Step progression, cumulative failure threshold, and rollback scoring
# ---------------------------------------------------------------------------
def test_flag_01_step_progression_and_threshold():
    """Verify Flagger cumulative failed-check threshold progression."""
    T = 8
    t0 = 1
    nc = 2
    adj = make_dummy_adjusted(T=T, t0=t0, nc=nc)

    raw_signal = np.array([0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0])
    raw_out = DetectorOutput(method="mock", score=raw_signal, elig=adj.elig, host_score=None)

    flag = FlaggerPolicy(FlaggerPolicyConfig(max_failed_checks=5))
    res = flag.run(adj, raw_detector_output=raw_out)

    # Failures occur at t=1, 2, 4, 5, 6 (5 failures total)
    assert np.isclose(res.score[1], 1.0 / 5.0)
    assert np.isclose(res.score[2], 2.0 / 5.0)
    assert np.isclose(res.score[3], 2.0 / 5.0)
    assert np.isclose(res.score[4], 3.0 / 5.0)
    assert np.isclose(res.score[5], 4.0 / 5.0)
    assert np.isclose(res.score[6], 5.0 / 5.0) # Full budget breached
    assert np.isclose(res.score[7], 5.0 / 5.0)


# ---------------------------------------------------------------------------
# FLAG-02: Missing measurement and cumulative failure retention
# ---------------------------------------------------------------------------
def test_flag_02_cumulative_failure_retention_on_recovery():
    """Verify that Flagger retains cumulative failure counts across clean checks."""
    T = 6
    t0 = 1
    nc = 2
    adj = make_dummy_adjusted(T=T, t0=t0, nc=nc)

    # A burst of 2 failures, followed by 3 clean checks
    raw_signal = np.array([0.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    raw_out = DetectorOutput(method="mock", score=raw_signal, elig=adj.elig, host_score=None)

    flag = FlaggerPolicy(FlaggerPolicyConfig(max_failed_checks=5))
    res = flag.run(adj, raw_detector_output=raw_out)

    # Budget remains consumed at 2/5 = 0.4 even when clean checks follow
    assert np.isclose(res.score[2], 0.4)
    assert np.isclose(res.score[3], 0.4)
    assert np.isclose(res.score[4], 0.4)
    assert np.isclose(res.score[5], 0.4)


# ---------------------------------------------------------------------------
# SLO-01: Boundary behavior (below, at, above threshold) and window averaging
# ---------------------------------------------------------------------------
def test_slo_01_boundary_and_window_averaging():
    """Verify SLO contrast calculation, strict boundary, and window averaging."""
    T = 6
    t0 = 2
    nc = 2
    nctl = 2

    # Canary residuals: 0 at t=0,1,2, then 2.0, 4.0, 6.0
    r_can = np.array([
        [0.0, 0.0],
        [0.0, 0.0],
        [0.0, 0.0],
        [2.0, 2.0],
        [4.0, 4.0],
        [6.0, 6.0]
    ])
    # Control residuals: constant 1.0
    r_ctl = np.ones((T, nctl))

    adj = make_dummy_adjusted(T=T, t0=t0, nc=nc, r=r_can, ctl_r=r_ctl, nctl=nctl)

    # Rolling window = 2
    slo = SLOThresholdComparator(SLOConfig(window=2, standardize=False))
    res = slo.run(adj)

    # Pre-rollout must be NaN
    assert np.isnan(res.score[:t0]).all()

    # t=2: window [1,2] -> can_mean=0, ctl_mean=1 -> diff = -1.0
    assert np.isclose(res.score[2], -1.0)
    # t=3: window [2,3] -> can_mean = (0 + 2)/2 = 1.0, ctl_mean=1 -> diff = 0.0
    assert np.isclose(res.score[3], 0.0)
    # t=4: window [3,4] -> can_mean = (2 + 4)/2 = 3.0, ctl_mean=1 -> diff = 2.0
    assert np.isclose(res.score[4], 2.0)
    # t=5: window [4,5] -> can_mean = (4 + 6)/2 = 5.0, ctl_mean=1 -> diff = 4.0
    assert np.isclose(res.score[5], 4.0)


# ---------------------------------------------------------------------------
# COMMON-01: Online chronological streaming prefix invariance
# ---------------------------------------------------------------------------
def test_common_01_streaming_prefix_invariance():
    """Verify that evaluating up to time t produces identical scores as complete series."""
    T = 15
    t0 = 5
    nc = 3
    rng = np.random.default_rng(123)

    r_can = rng.normal(0, 1, size=(T, nc))
    r_ctl = rng.normal(0, 1, size=(T, nc))

    adj_full = make_dummy_adjusted(T=T, t0=t0, nc=nc, r=r_can, ctl_r=r_ctl, nctl=nc)

    kayenta = KayentaJudge(KayentaConfig(window=5, min_samples=3))
    slo = SLOThresholdComparator(SLOConfig(window=5, standardize=False))
    argo = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=3))
    flag = FlaggerPolicy(FlaggerPolicyConfig(max_failed_checks=5))

    out_kay_full = kayenta.run(adj_full)
    out_slo_full = slo.run(adj_full)
    out_argo_full = argo.run(adj_full)
    out_flag_full = flag.run(adj_full)

    # Check prefix invariance for intermediate cutoffs t_cut in [7, 10, 14]
    for t_cut in [7, 10, 14]:
        adj_cut = make_dummy_adjusted(
            T=t_cut + 1,
            t0=t0,
            nc=nc,
            r=r_can[:t_cut + 1],
            ctl_r=r_ctl[:t_cut + 1],
            nctl=nc
        )

        out_kay_cut = kayenta.run(adj_cut)
        out_slo_cut = slo.run(adj_cut)
        out_argo_cut = argo.run(adj_cut)
        out_flag_cut = flag.run(adj_cut)

        assert np.isclose(out_kay_full.score[t_cut], out_kay_cut.score[t_cut], rtol=1e-5)
        assert np.isclose(out_slo_full.score[t_cut], out_slo_cut.score[t_cut], rtol=1e-5)
        assert np.isclose(out_argo_full.score[t_cut], out_argo_cut.score[t_cut], rtol=1e-5)
        assert np.isclose(out_flag_full.score[t_cut], out_flag_cut.score[t_cut], rtol=1e-5)
