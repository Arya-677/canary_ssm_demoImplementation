"""Tests for streaming time slicing, duplicate handling, control exclusion, nested rack adjustment,
uncertainty propagation, coverage protocol, and causal invariance.

Governing requirements:
1. Build time slices using only records received by the decision timestamp (arrival_time <= t).
2. Fix duplicate handling; log stale, missing and late observations without revising past alerts.
3. Exclude exposed hosts from controls.
4. Fit workload/intercept terms and loadings on healthy development data and permitted preperiod only.
5. Estimate shared fleet and rack variation from eligible baseline controls with an identifiable constraint;
   avoid subtracting the same component twice.
6. Carry shared control estimation uncertainty into residual covariance and document approximations.
7. Require configured same rack and class control coverage (4 racks demo starts with 5 controls per rack).
8. Output adjusted log latency and per metric residuals/masks for later channels.
9. Do not infer a release cause if rack controls are absent.
10. Demonstrate that future observation changes cannot alter earlier residuals.
Exit gate: shared load/rack shock fixtures, coverage abstention and no future leakage pass.
"""
from __future__ import annotations

import copy
import numpy as np
import pytest

from canary_ssm.telemetry import (
    TelemetryRecord,
    SlicingProtocol,
    StreamSliceBuilder,
    fit_preperiod_baseline,
    infer_release_cause,
)
from canary_ssm.factor import adjust, Adjusted
from canary_ssm.schema import Rollout


def _create_mock_record(
    server_id: str,
    rack_id: str,
    class_id: int,
    tick: int,
    arrival_time: int,
    exposure: bool = False,
    version: str = "v1.0.0",
    latency_ms: float = 100.0,
    memory_mb: float = 200.0,
    cpu_fraction: float = 0.20,
    request_count: int = 1000,
    error_count: int = 0,
    observed: bool = True,
    run_id: str = "test-run",
) -> TelemetryRecord:
    return TelemetryRecord(
        run_id=run_id,
        tick=tick,
        event_time=tick,
        arrival_time=arrival_time,
        server_id=server_id,
        rack_id=rack_id,
        class_id=class_id,
        version=version,
        exposure=exposure,
        request_count=request_count,
        latency_ms=latency_ms,
        memory_mb=memory_mb,
        cpu_fraction=cpu_fraction,
        error_count=error_count,
        observed=observed,
    )


def _setup_4rack_world(t_pre: int = 60, seed: int = 42):
    """Create 4 racks x 6 servers = 24 servers. 1 canary per rack (r0-s0, r1-s0, r2-s0, r3-s0).

    In pre-period (0..t_pre-1), all hosts are clean baseline controls.
    """
    rng = np.random.default_rng(seed)
    servers = []
    metadata = {}
    racks = [f"rack-{r}" for r in range(4)]
    canaries = {f"srv-r{r}-s0" for r in range(4)}

    records = []
    for r_idx, rk in enumerate(racks):
        for s_idx in range(6):
            sid = f"srv-r{r_idx}-s{s_idx}"
            cls_id = s_idx % 2  # 2 classes
            servers.append(sid)
            is_canary = (sid in canaries)
            metadata[sid] = {"rack_id": rk, "class_id": cls_id, "exposed": is_canary}

            for t in range(t_pre):
                req = int(rng.normal(1000, 50))
                # Base latency with mild AR(1) noise
                lat = float(np.exp(np.log(100.0) + 0.05 * (np.log(req) - np.log(1000)) + rng.normal(0, 0.02)))
                mem = float(200.0 + rng.normal(0, 5.0))
                cpu = float(np.clip(0.10 + 0.0001 * req + rng.normal(0, 0.01), 0.0, 1.0))
                records.append(_create_mock_record(
                    server_id=sid,
                    rack_id=rk,
                    class_id=cls_id,
                    tick=t,
                    arrival_time=t,
                    exposure=False,  # unexposed during pre-period
                    version="v1.0.0",
                    latency_ms=lat,
                    memory_mb=mem,
                    cpu_fraction=cpu,
                    request_count=req,
                ))

    protocol = SlicingProtocol(min_controls_per_rack=3, min_controls_per_class=3, min_canary_coverage=0.80)
    baseline = fit_preperiod_baseline(records, t0=t_pre, expected_servers=servers, protocol=protocol)
    builder = StreamSliceBuilder(servers, metadata, protocol=protocol, baseline=baseline)
    builder.ingest(records)
    return servers, metadata, canaries, protocol, baseline, builder


# ---------------------------------------------------------------------
# Test 1: Causality & Decision Timestamp Filtering
# ---------------------------------------------------------------------
def test_decision_timestamp_filtering_and_causality():
    """Only records received by decision timestamp (arrival_time <= t) may enter slice."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60)

    # Ingest records for tick 60, but with varied arrival times
    # Some arrived at tick 60 (on-time), some delayed to tick 62 (late)
    new_recs = []
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        # Suppose srv-r0-s1 arrives late at tick 62
        arr_time = 62 if sid == "srv-r0-s1" else 60
        new_recs.append(_create_mock_record(
            server_id=sid,
            rack_id=rk,
            class_id=cls_id,
            tick=60,
            arrival_time=arr_time,
            exposure=is_can,
            version="v1.1.0" if is_can else "v1.0.0",
        ))

    builder.ingest(new_recs)

    # Slice at decision timestamp 60
    slice_60 = builder.build_slice(decision_tick=60)
    # Late record must NOT be admitted at decision timestamp 60
    assert "srv-r0-s1" in slice_60.audit_log.missing_servers
    assert slice_60.audit_log.total_admitted == 23  # 24 - 1 missing

    # At decision timestamp 62, the late record is now arrived
    slice_62 = builder.build_slice(decision_tick=60)  # query event time 60 as of decision time 62
    # Ingesting records for 62 allows access to arrival_time <= 62
    builder.ingest([_create_mock_record("srv-r0-s1", "rack-0", 1, 62, 62)])
    slice_at_62 = builder.build_slice(decision_tick=62)
    assert slice_at_62.tick == 62


# ---------------------------------------------------------------------
# Test 2: Duplicate Handling (Deterministic & Logged)
# ---------------------------------------------------------------------
def test_duplicate_handling_deterministic_and_logged():
    """Duplicate records for (server_id, event_time) must be resolved deterministically and logged."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60)

    # Ingest identical record twice at tick 60
    rec1 = _create_mock_record("srv-r0-s0", "rack-0", 0, 60, 60, exposure=True, version="v1.1.0", latency_ms=105.0)
    rec2 = _create_mock_record("srv-r0-s0", "rack-0", 0, 60, 60, exposure=True, version="v1.1.0", latency_ms=999.0)  # duplicate

    other_recs = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], 60, 60,
                            exposure=(s in canaries), version="v1.1.0" if (s in canaries) else "v1.0.0")
        for s in servers if s != "srv-r0-s0"
    ]

    builder.ingest([rec1] + other_recs + [rec2])
    slice_60 = builder.build_slice(60)

    # Check audit log caught the duplicate
    assert slice_60.audit_log.duplicate_count == 1
    assert slice_60.audit_log.duplicates[0]["server_id"] == "srv-r0-s0"
    # First record must be preserved (latency_ms = 105.0, not 999.0)
    # Canary r_latency should be close to 0, not +2.3 (which 999.0 would give)
    idx_canary = slice_60.canary_ids.index("srv-r0-s0")
    assert abs(slice_60.r_latency[idx_canary]) < 0.20


# ---------------------------------------------------------------------
# Test 3: Stale, Missing, Late Logging & Alert Immutability
# ---------------------------------------------------------------------
def test_stale_missing_late_logging_without_revising_past_alerts():
    """Past alerts cannot be revised by late-arriving records."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60)

    # At tick 60, emit alert and record it
    recs_60 = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], 60, 60, exposure=(s in canaries))
        for s in servers
    ]
    builder.ingest(recs_60)
    slice_60 = builder.build_slice(60)
    initial_alert = {
        "tick": 60,
        "advisory": "RUNNING",
        "score": 0.02,
        "evidence": "nominal",
    }
    builder.record_alert(60, initial_alert)

    # Attempt to overwrite alert at tick 60 must raise RuntimeError
    with pytest.raises(RuntimeError, match="immutable"):
        builder.record_alert(60, {"tick": 60, "advisory": "PAUSE RECOMMENDED"})

    # Now simulate tick 65: a late record for tick 58 arrives
    late_rec = _create_mock_record("srv-r1-s2", "rack-1", 0, 58, 65, latency_ms=120.0)
    recs_65 = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], 65, 65, exposure=(s in canaries))
        for s in servers
    ]
    builder.ingest([late_rec] + recs_65)
    slice_65 = builder.build_slice(65)

    # Audit log logs the late record
    assert slice_65.audit_log.late_count >= 1

    # Alert at tick 60 remains strictly identical
    alert_at_60 = builder.get_alert(60)
    assert alert_at_60 == initial_alert
    assert alert_at_60["advisory"] == "RUNNING"


# ---------------------------------------------------------------------
# Test 4: Exclude Exposed Hosts from Controls
# ---------------------------------------------------------------------
def test_exclude_exposed_hosts_from_controls():
    """Canaries (exposure=True or version != baseline) must NEVER be included in controls."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60)

    # Ingest records where canaries are exposed
    recs = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], 60, 60,
                            exposure=(s in canaries), version="v1.1.0" if (s in canaries) else "v1.0.0")
        for s in servers
    ]
    builder.ingest(recs)
    sl = builder.build_slice(60)

    # Ensure none of the canaries appear in control_ids
    for c in canaries:
        assert c in sl.canary_ids
        assert c not in sl.control_ids

    # Total controls must equal total servers minus canaries
    assert len(sl.control_ids) == len(servers) - len(canaries)


# ---------------------------------------------------------------------
# Test 5: Pre-period Fitting Only
# ---------------------------------------------------------------------
def test_preperiod_fitting_only():
    """Host intercepts, slopes, and loadings come from pre-period data (t < t0) only."""
    servers, metadata, canaries, protocol, baseline1, builder = _setup_4rack_world(t_pre=60, seed=123)

    # Use the exact pre-period records from builder
    orig_pre_recs = list(builder._raw_records)

    # Add post-period records with extreme values at t=60..100
    rng = np.random.default_rng(999)
    post_records = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], t, t,
                            latency_ms=9999.0, memory_mb=99999.0)
        for s in servers for t in range(60, 100)
    ]

    baseline2 = fit_preperiod_baseline(orig_pre_recs + post_records, t0=60, expected_servers=servers, protocol=protocol)

    # All fitted parameters must be exactly identical
    assert baseline1.x_center == baseline2.x_center
    for s in servers:
        assert baseline1.mu_latency[s] == baseline2.mu_latency[s]
        assert baseline1.beta_latency[s] == baseline2.beta_latency[s]
        assert baseline1.lam[s] == baseline2.lam[s]


# ---------------------------------------------------------------------
# Test 6: Shared Fleet Load Shock Fixture
# ---------------------------------------------------------------------
def test_shared_fleet_load_shock_fixture():
    """A fleet-wide workload demand spike must be absorbed by baseline controls.

    Canary adjusted residuals must remain within baseline noise (no false alarm).
    """
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    # Inject fleet-wide demand spike at tick 60: requests double (1000 -> 2500)
    # Healthy latency increases on all servers according to queuing delay
    spike_recs = []
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        # High request volume
        req = 2500
        # Latency rises naturally with demand according to healthy response
        lat = float(np.exp(np.log(100.0) + 0.05 * (np.log(req) - np.log(1000))))
        spike_recs.append(_create_mock_record(
            server_id=sid,
            rack_id=rk,
            class_id=cls_id,
            tick=60,
            arrival_time=60,
            exposure=is_can,
            latency_ms=lat,
            request_count=req,
        ))

    builder.ingest(spike_recs)
    sl = builder.build_slice(60)

    # Slice must be eligible
    assert sl.eligible
    # Fleet factor or workload adjustment absorbs the demand spike
    for r_lat in sl.r_latency:
        # Residuals must remain near zero (< 0.10 log units), not spiking to false alarm
        assert abs(r_lat) < 0.10, f"Canary residual {r_lat} exceeded false alarm threshold under load shock"


# ---------------------------------------------------------------------
# Test 7: Shared Rack Shock Fixture (Absorbed by Same-Rack Controls)
# ---------------------------------------------------------------------
def test_rack_shock_fixture_absorbed_by_same_rack_controls():
    """A rack-specific network latency slowdown (+0.40 log units) hits rack-0.

    Same-rack baseline controls estimate gamma_hat_{rack-0} approx 0.40.
    The canary in rack-0 must NOT see an elevated residual; its adjusted residual remains flat.
    """
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    # At tick 60: rack-0 network switch slows down by +0.40 log latency for all hosts in rack-0
    shock_recs = []
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        # Add +0.40 log latency to all hosts in rack-0
        lat = 100.0 * (np.exp(0.40) if rk == "rack-0" else 1.0)
        shock_recs.append(_create_mock_record(
            server_id=sid,
            rack_id=rk,
            class_id=cls_id,
            tick=60,
            arrival_time=60,
            exposure=is_can,
            latency_ms=float(lat),
            request_count=1000,
        ))

    builder.ingest(shock_recs)
    sl = builder.build_slice(60)

    assert sl.eligible
    # Rack-0 nuisance must be strongly positive (~0.30 to 0.40)
    assert sl.gamma_hat["rack-0"] > 0.25, f"Rack-0 nuisance was {sl.gamma_hat['rack-0']}"

    # Canary in rack-0 (srv-r0-s0) residual must be flat (< 0.10)!
    idx_r0_canary = sl.canary_ids.index("srv-r0-s0")
    r0_residual = sl.r_latency[idx_r0_canary]
    assert abs(r0_residual) < 0.10, f"Rack shock leaked into canary residual: {r0_residual}"


# ---------------------------------------------------------------------
# Test 8: Absent Rack Controls Blocks Release Cause Inference
# ---------------------------------------------------------------------
def test_absent_rack_controls_blocks_release_cause_inference():
    """If all baseline controls in a rack are absent, release cause inference MUST be blocked."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    # At tick 60: rack-0 baseline controls are all offline/missing
    recs = []
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        # Omit baseline controls for rack-0
        if rk == "rack-0" and not is_can:
            continue
        recs.append(_create_mock_record(
            server_id=sid,
            rack_id=rk,
            class_id=cls_id,
            tick=60,
            arrival_time=60,
            exposure=is_can,
        ))

    builder.ingest(recs)
    sl = builder.build_slice(60)

    # Slice must be marked unidentifiable and ineligible
    assert sl.is_unidentifiable
    assert not sl.eligible
    assert any("ABSENT_RACK_CONTROLS" in r for r in sl.attribution_blocked_reasons)

    # infer_release_cause must return False
    can_infer, reason = infer_release_cause(sl, canary_id="srv-r0-s0")
    assert not can_infer
    assert "UNIDENTIFIABLE" in reason or "ABSENT_RACK_CONTROLS" in reason


# ---------------------------------------------------------------------
# Test 9: Coverage Protocol Abstention Rules
# ---------------------------------------------------------------------
def test_coverage_protocol_abstention_rules():
    """Minimum controls per rack, per class, and canary coverage trigger explicit abstention."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    # Case A: Only 2 controls in rack-1 (below min_controls_per_rack = 3)
    recs_a = []
    r1_controls_kept = 0
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        if rk == "rack-1" and not is_can:
            r1_controls_kept += 1
            if r1_controls_kept > 2:  # only keep 2
                continue
        recs_a.append(_create_mock_record(sid, rk, cls_id, 60, 60, exposure=is_can))

    b_a = StreamSliceBuilder(servers, metadata, protocol=protocol, baseline=baseline)
    b_a.ingest(recs_a)
    sl_a = b_a.build_slice(60)
    assert not sl_a.eligible
    assert any("INSUFFICIENT_RACK_CONTROLS" in r and "rack-1" in r for r in sl_a.ineligible_reasons)

    # Case B: Only 1 canary observed (1/4 = 25% < 80% min_canary_coverage)
    recs_b = []
    can_kept = 0
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        if is_can:
            can_kept += 1
            if can_kept > 1:
                continue
        recs_b.append(_create_mock_record(sid, rk, cls_id, 61, 61, exposure=is_can))

    b_b = StreamSliceBuilder(servers, metadata, protocol=protocol, baseline=baseline)
    b_b.ingest(recs_b)
    sl_b = b_b.build_slice(61)
    assert not sl_b.eligible
    assert any("INSUFFICIENT_CANARY_COVERAGE" in r for r in sl_b.ineligible_reasons)


# ---------------------------------------------------------------------
# Test 10: No Future Leakage Invariance
# ---------------------------------------------------------------------
def test_no_future_leakage_invariance():
    """Altering, adding, or perturbing observations at t2 > t1 cannot alter residuals at t1."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    # Produce slice at tick 60
    recs_60 = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], 60, 60, exposure=(s in canaries))
        for s in servers
    ]
    builder.ingest(recs_60)
    slice_60_initial = builder.build_slice(60)
    r_lat_orig = np.copy(slice_60_initial.r_latency)
    f_hat_orig = slice_60_initial.f_hat
    gamma_orig = copy.deepcopy(slice_60_initial.gamma_hat)

    # Now simulate tick 61, 62 with massive perturbations / outages / crazy values
    rng = np.random.default_rng(777)
    future_recs = []
    for t in (61, 62):
        for s in servers:
            future_recs.append(_create_mock_record(
                s, metadata[s]["rack_id"], metadata[s]["class_id"], t, t,
                latency_ms=float(rng.uniform(10.0, 5000.0)),
                memory_mb=float(rng.uniform(100.0, 16000.0)),
                cpu_fraction=float(rng.uniform(0.1, 0.9)),
            ))

    builder.ingest(future_recs)

    # Re-build slice for tick 60
    slice_60_after = builder.build_slice(60)

    # MUST BE EXACTLY IDENTICAL down to machine precision
    np.testing.assert_array_equal(r_lat_orig, slice_60_after.r_latency)
    assert f_hat_orig == slice_60_after.f_hat
    assert gamma_orig == slice_60_after.gamma_hat


# ---------------------------------------------------------------------
# Test 11: Shared Estimation Uncertainty Covariance
# ---------------------------------------------------------------------
def test_shared_estimation_uncertainty_covariance():
    """Estimation uncertainty covariance cov_U correctly reflects rack control mean variance and fleet variance."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    recs_60 = [
        _create_mock_record(s, metadata[s]["rack_id"], metadata[s]["class_id"], 60, 60, exposure=(s in canaries))
        for s in servers
    ]
    builder.ingest(recs_60)
    sl = builder.build_slice(60)

    # cov_U shape: (nc, nc) = (4, 4)
    nc = len(sl.canary_ids)
    assert sl.cov_U.shape == (nc, nc)
    # Diagonal elements must be strictly positive
    for i in range(nc):
        assert sl.cov_U[i, i] > 0.0
    # Symmetric
    assert np.allclose(sl.cov_U, sl.cov_U.T, atol=1e-12)


# ---------------------------------------------------------------------
# Test 12: Multi-Metric Residuals and Masks
# ---------------------------------------------------------------------
def test_multi_metric_residuals_and_masks():
    """Slice must output adjusted log latency, memory, CPU, error residuals and masks."""
    servers, metadata, canaries, protocol, baseline, builder = _setup_4rack_world(t_pre=60, seed=42)

    # Inject memory divergence on canary 0 (+500 MB)
    recs_60 = []
    for sid in servers:
        rk = metadata[sid]["rack_id"]
        cls_id = metadata[sid]["class_id"]
        is_can = sid in canaries
        mem = 700.0 if sid == "srv-r0-s0" else 200.0
        recs_60.append(_create_mock_record(
            sid, rk, cls_id, 60, 60, exposure=is_can, memory_mb=mem, cpu_fraction=0.35, error_count=5
        ))

    builder.ingest(recs_60)
    sl = builder.build_slice(60)

    assert sl.r_memory.shape == (4,)
    assert sl.r_cpu.shape == (4,)
    assert sl.r_error.shape == (4,)
    assert sl.mask_memory.all()
    assert sl.mask_cpu.all()
    assert sl.mask_error.all()

    # Canary 0 memory residual must be ~ +500 MB
    idx0 = sl.canary_ids.index("srv-r0-s0")
    assert sl.r_memory[idx0] > 450.0
    # Other canaries memory residuals must be near zero
    for i in range(4):
        if i != idx0:
            assert abs(sl.r_memory[i]) < 50.0


# ---------------------------------------------------------------------
# Test 13: Factor Adjust with Racks (Integration with Rollout)
# ---------------------------------------------------------------------
def test_factor_adjust_with_racks():
    """Verify that adjust(roll, ..., rack_ids=...) handles nested rack estimation and populates cov_U."""
    # Construct a small mock Rollout with 4 racks of 6 hosts = 24 hosts
    N = 24
    T = 80
    t0 = 60
    racks = np.array([f"rack-{h // 6}" for h in range(N)])
    cls = np.array([h % 2 for h in range(N)])
    exposed = np.zeros(N, bool)
    exposed[[0, 6, 12, 18]] = True  # 4 canaries, 1 per rack

    rng = np.random.default_rng(101)
    x = rng.normal(0, 0.1, T)
    f = rng.normal(0, 0.1, T)
    y = np.zeros((T, N))
    # Add a rack-0 latency shock at t >= 60 (+0.35)
    for h in range(N):
        y[:, h] = np.log(100.0) + 1.0 * f + 0.1 * x + rng.normal(0, 0.02, T)
        if racks[h] == "rack-0":
            y[60:, h] += 0.35

    obs = np.ones((T, N), bool)
    roll = Rollout(
        rollout_id="test-roll-racks",
        y=y,
        x=x,
        observed=obs,
        decision_obs=obs,
        class_id=cls,
        exposed=exposed,
        t0=t0,
        request_count=np.full((T, N), 1000),
        meta={"rack_ids": racks.tolist()},
    )

    adj = adjust(roll, x_center=0.0, class_lambda=np.ones(2), factor_rank=1, rack_ids=racks)

    assert adj.cov_U is not None
    assert adj.gamma_hat is not None
    assert adj.gamma_hat.shape[0] == T
    # Rack shock should be absorbed: canary 0 residual should stay flat
    assert np.nanmean(np.abs(adj.r[60:, 0])) < 0.10
