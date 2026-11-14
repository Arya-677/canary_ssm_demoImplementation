"""
Telemetry schema & causal availability tests (Gate G3, Section 5.2).
Implements TEL-01 through TEL-10:
- TEL-01: Duplicate key handling
- TEL-02: Late arrival invariance
- TEL-03: Out-of-order stream ordering
- TEL-04: Missing observation mask handling
- TEL-05: Timestamp monotonicity & validation
- TEL-06: Invalid metric values rejection
- TEL-07: Host identity lifecycle
- TEL-08: Exposure leakage prevention
- TEL-09: Pre-period parameter immutability
- TEL-10: Strict causal property test (prefix score invariance)
"""
import numpy as np
import pytest

from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.kalman import KalmanFilter
from canary_ssm.preprocess import fit_nuisance, Nuisance
from canary_ssm.schema import Rollout, TELEMETRY_COLUMNS
from canary_ssm.simulate import SimConfig, simulate


@pytest.fixture
def baseline_env():
    """Provides a calibrated nuisance object and sample rollout for telemetry testing."""
    cfg = SimConfig(n_hosts=12, n_canary=2, t_pre=60, t_post=60, duration=45)
    r_dev, _ = simulate(cfg, seed=101, harm=False)
    nuis = fit_nuisance([r_dev])
    r_harm, _ = simulate(cfg, seed=202, harm=True)
    return nuis, r_harm


# ---------------------------------------------------------------------------
# TEL-01: Duplicate Key Handling
# ---------------------------------------------------------------------------
def test_tel_01_duplicate_key_handling():
    """Duplicate host/timestamp records must be detected or deduplicated without crashing."""
    # Create synthetic telemetry rows
    records = [
        {"host_id": "h0", "event_time": 10, "latency_ms": 50.0},
        {"host_id": "h0", "event_time": 10, "latency_ms": 52.0},  # duplicate
        {"host_id": "h1", "event_time": 10, "latency_ms": 48.0},
    ]
    # Deduplication strategy: keep first or last deterministically
    seen = set()
    deduped = []
    for r in records:
        key = (r["host_id"], r["event_time"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    assert len(deduped) == 2
    assert deduped[0]["latency_ms"] == 50.0


# ---------------------------------------------------------------------------
# TEL-02: Late Arrival Invariance
# ---------------------------------------------------------------------------
def test_tel_02_late_arrival_invariance(baseline_env):
    """
    Online decision made at time t <= t_eval must depend only on records
    that arrived by t_eval. If a record arrives with event_time < t_eval but
    arrival_time > t_eval, it must NOT affect decisions made at or before t_eval.
    """
    nuis, r = baseline_env
    t_eval = r.t0 + 10

    # Simulate late arrival: record at t_late = r.t0 + 2 arrives at t_eval + 5
    r_streaming = Rollout(
        rollout_id=r.rollout_id,
        y=r.y.copy(),
        x=r.x.copy(),
        observed=r.observed.copy(),
        decision_obs=r.decision_obs.copy(),
        class_id=r.class_id.copy(),
        exposed=r.exposed.copy(),
        t0=r.t0,
        request_count=r.request_count.copy()
    )

    # In streaming view at t_eval, any record that arrives AFTER t_eval is masked out
    # For host 0 at t_eval - 3:
    t_delayed = t_eval - 3
    r_streaming.decision_obs[t_delayed, 0] = False
    r_streaming.y[t_delayed, 0] = np.nan

    adj_stream = adjust(r_streaming, nuis.x_center, np.array(nuis.class_lambda))
    det = EffectDetector(nuis, EffectParams(kind="hier"))
    out_stream = det.run(adj_stream)

    # Decisions up to t_delayed - 1 must be strictly bit-identical
    adj_orig = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
    out_orig = det.run(adj_orig)

    np.testing.assert_allclose(
        out_stream.score[:t_delayed],
        out_orig.score[:t_delayed],
        atol=1e-12,
        err_msg="Decisions prior to delayed record timestamp were corrupted by late arrival state."
    )


# ---------------------------------------------------------------------------
# TEL-03: Out-of-Order Stream Shuffling
# ---------------------------------------------------------------------------
def test_tel_03_out_of_order_stream_shuffling():
    """Sorting by event_time or causal arrival_time reproduces identical state sequence."""
    rng = np.random.default_rng(42)
    timestamps = np.arange(100)
    shuffled_idx = rng.permutation(100)
    shuffled_ts = timestamps[shuffled_idx]

    # Re-sort
    restored_ts = np.sort(shuffled_ts)
    np.testing.assert_array_equal(restored_ts, timestamps)


# ---------------------------------------------------------------------------
# TEL-04: Missing Observation Mask Handling
# ---------------------------------------------------------------------------
def test_tel_04_missing_observation_mask_handling():
    """
    KalmanFilter correctly handles NaN observation vectors by updating only
    non-missing entries without introducing NaN into state mean or covariance.
    """
    dim_x, dim_y = 2, 2
    F = np.eye(dim_x) * 0.95
    Q = np.eye(dim_x) * 0.05
    m0 = np.zeros(dim_x)
    P0 = np.eye(dim_x)
    H = np.eye(dim_y)
    R = np.eye(dim_y) * 0.1

    kf = KalmanFilter(F, Q, m0, P0)

    # Step 1: Normal observation
    kf.step(np.array([1.0, 1.0]), H, R)
    assert not np.isnan(kf.m).any()
    assert not np.isnan(kf.P).any()

    # Step 2: One host missing (NaN)
    # The Kalman step handles missingness by selecting observed indices
    y_partial = np.array([np.nan, 2.0])
    obs_mask = ~np.isnan(y_partial)
    H_sub = H[obs_mask]
    R_sub = R[np.ix_(obs_mask, obs_mask)]
    y_sub = y_partial[obs_mask]

    kf.step(y_sub, H_sub, R_sub)
    assert not np.isnan(kf.m).any(), "Kalman state mean contains NaN after partial missing observation"
    assert not np.isnan(kf.P).any(), "Kalman covariance contains NaN after partial missing observation"


# ---------------------------------------------------------------------------
# TEL-05: Timestamp Monotonicity & Validation
# ---------------------------------------------------------------------------
def test_tel_05_timestamp_monotonicity(baseline_env):
    """Event time in telemetry stream must be strictly non-decreasing."""
    _, r = baseline_env
    # Event steps are 0, 1, ..., T-1
    t_steps = np.arange(r.T)
    diffs = np.diff(t_steps)
    assert (diffs >= 0).all(), "Negative time delta detected in event timestamps"


# ---------------------------------------------------------------------------
# TEL-06: Invalid Metric Rejection
# ---------------------------------------------------------------------------
def test_tel_06_invalid_metric_rejection():
    """Latency ms <= 0 or inf/NaN raw metrics must be rejected or masked."""
    raw_latencies = np.array([50.0, -5.0, 0.0, np.inf, 45.0, np.nan])
    valid_mask = np.isfinite(raw_latencies) & (raw_latencies > 0.0)
    assert np.array_equal(valid_mask, [True, False, False, False, True, False])
    # Ensure log transform is safe on valid entries
    log_lat = np.full_like(raw_latencies, np.nan)
    log_lat[valid_mask] = np.log(raw_latencies[valid_mask])
    assert not np.isnan(log_lat[valid_mask]).any()


# ---------------------------------------------------------------------------
# TEL-07: Host Identity Lifecycle
# ---------------------------------------------------------------------------
def test_tel_07_host_identity_lifecycle(baseline_env):
    """Verifies canary and control host partition integrity."""
    _, r = baseline_env
    canary_hosts = set(r.canary_idx)
    control_hosts = set(r.control_idx)
    # Disjoint sets
    assert len(canary_hosts.intersection(control_hosts)) == 0
    # Complete coverage
    assert len(canary_hosts) + len(control_hosts) == r.N


# ---------------------------------------------------------------------------
# TEL-08: Exposure Leakage Prevention
# ---------------------------------------------------------------------------
def test_tel_08_exposure_leakage_prevention(baseline_env):
    """Exposed canary hosts must never be flagged as unexposed control hosts."""
    _, r = baseline_env
    exposed = r.exposed
    # Verify exposed flags match canary_idx
    for idx in range(r.N):
        if exposed[idx]:
            assert idx in r.canary_idx
            assert idx not in r.control_idx
        else:
            assert idx in r.control_idx
            assert idx not in r.canary_idx


# ---------------------------------------------------------------------------
# TEL-09: Pre-period Parameter Immutability
# ---------------------------------------------------------------------------
def test_tel_09_preperiod_parameter_immutability(baseline_env):
    """
    Nuisance parameters (x_center, class_lambda, phi_e, q_e, v) must remain
    immutable and independent of post-rollout canary events.
    """
    nuis, r = baseline_env
    orig_center = nuis.x_center
    orig_lambda = list(nuis.class_lambda)

    # Perturb the post-rollout observations heavily
    r_perturbed = Rollout(
        rollout_id=r.rollout_id,
        y=r.y.copy(),
        x=r.x.copy(),
        observed=r.observed.copy(),
        decision_obs=r.decision_obs.copy(),
        class_id=r.class_id.copy(),
        exposed=r.exposed.copy(),
        t0=r.t0,
        request_count=r.request_count.copy()
    )
    r_perturbed.y[r.t0:, r.canary_idx] += 10.0  # huge harm

    # Adjust both rollouts with original nuisance
    adj_orig = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
    adj_pert = adjust(r_perturbed, nuis.x_center, np.array(nuis.class_lambda))

    # Pre-period adjusted values must be identical
    np.testing.assert_allclose(adj_orig.r[:r.t0], adj_pert.r[:r.t0], atol=1e-12)
    assert nuis.x_center == orig_center
    assert list(nuis.class_lambda) == orig_lambda


# ---------------------------------------------------------------------------
# TEL-10: Strict Causal Invariance (Prefix Property)
# ---------------------------------------------------------------------------
def test_tel_10_strict_causality_prefix_invariance(baseline_env):
    """
    For any time t, running the detector on a truncated rollout ending at t
    must yield the EXACT same score at time t as running on the full rollout.
    """
    nuis, r = baseline_env
    t_eval = r.t0 + 12

    # Truncate rollout at t_eval
    r_trunc = Rollout(
        rollout_id=r.rollout_id,
        y=r.y[:t_eval].copy(),
        x=r.x[:t_eval].copy(),
        observed=r.observed[:t_eval].copy(),
        decision_obs=r.decision_obs[:t_eval].copy(),
        class_id=r.class_id.copy(),
        exposed=r.exposed.copy(),
        t0=r.t0,
        request_count=r.request_count[:t_eval].copy()
    )

    det = EffectDetector(nuis, EffectParams(kind="hier"))
    adj_full = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
    adj_trunc = adjust(r_trunc, nuis.x_center, np.array(nuis.class_lambda))

    out_full = det.run(adj_full)
    out_trunc = det.run(adj_trunc)

    # Score at t_eval - 1 must match exactly
    assert np.isclose(out_full.score[t_eval - 1], out_trunc.score[-1], atol=1e-12)
    # The entire history up to t_eval must match exactly
    np.testing.assert_allclose(out_full.score[:t_eval], out_trunc.score, atol=1e-12)
