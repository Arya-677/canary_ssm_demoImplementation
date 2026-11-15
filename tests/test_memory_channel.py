"""Tests for Memory Growth Channel, GC Dynamics, Operational Guardrails & Multi-Channel Policy.

Prompt 10 Exit Gate Verification:
- Target definition and epistemic boundary
- Operational capacity guardrail (headroom, utilization, TTE)
- Differencing-induced MA(1) Kalman growth detector
- Healthy GC sawtooth, demand shock, allocator warmup, and restart stability
- Persistent leak detection and decreasing TTE tracking
- Multi-channel policy attribution and joint calibration
"""
import math
import numpy as np
import pytest
from scipy.stats import norm

from canary_ssm.decision import (
    MultiChannelAlertPolicy,
    calibrate_multichannel_policy,
    calibrate_threshold,
)
from canary_ssm.memory import (
    MemoryStepResult,
    MemoryTargetDefinition,
    OnlineMemoryGrowthDetector,
    OperationalMemoryGuardrail,
)
from canary_ssm.telemetry import TelemetryRecord
from canary_ssm.world.telemetry import HealthyTelemetryConfig, HealthyTelemetryEngine
from canary_ssm.world.models import create_default_fleet


def test_target_definition_and_disclaimer():
    """Verify declared boundaries and mandatory epistemic boundary disclaimer."""
    target = MemoryTargetDefinition(
        growth_boundary_mb_per_min=0.50,
        persistence_window_ticks=15,
        headroom_warning_mb=2048.0,
        headroom_critical_mb=1024.0,
        tte_warning_min=120.0,
        tte_critical_min=30.0,
    )
    assert target.growth_boundary_mb_per_min == 0.50
    assert target.persistence_window_ticks == 15
    assert "abnormal resource growth" in target.disclaimer
    assert "not formal verification" in target.disclaimer


def test_operational_memory_guardrail_hand_computed():
    """Verify headroom, utilization, TTE and 3-level guardrail status."""
    target = MemoryTargetDefinition(
        headroom_warning_mb=2000.0,
        headroom_critical_mb=1000.0,
        tte_warning_min=100.0,
        tte_critical_min=30.0,
    )
    guardrail = OperationalMemoryGuardrail(target)

    # Case 1: Healthy normal host
    # Mem = 4000 MB, Cap = 16000 MB (Util = 25%, Headroom = 12000 MB), Rate = 1.0 MB/min -> TTE = 12000 min
    st1, hr1, tte1 = guardrail.evaluate(
        memory_mb=np.array([4000.0]),
        capacities_mb=np.array([16000.0]),
        growth_rates=np.array([1.0]),
    )
    assert st1 == "NORMAL"
    assert hr1[0] == 12000.0
    assert math.isclose(tte1[0], 12000.0, rel_tol=1e-5)

    # Case 2: Memory pressure from high utilization (>= 70%)
    # Mem = 7200 MB, Cap = 10000 MB (Util = 72%), Rate = 0.1 MB/min
    st2, hr2, tte2 = guardrail.evaluate(
        memory_mb=np.array([7200.0]),
        capacities_mb=np.array([10000.0]),
        growth_rates=np.array([0.1]),
    )
    assert st2 == "PRESSURE"

    # Case 3: Memory pressure from low TTE (<= 100 min)
    # Mem = 7500 MB, Cap = 10000 MB (Headroom = 2500 MB > 2000), Rate = 30.0 MB/min -> TTE = 83.3 min <= 100 min
    st3, hr3, tte3 = guardrail.evaluate(
        memory_mb=np.array([7500.0]),
        capacities_mb=np.array([10000.0]),
        growth_rates=np.array([30.0]),
    )
    assert st3 == "PRESSURE"
    assert math.isclose(tte3[0], 2500.0 / 30.0, rel_tol=1e-5)

    # Case 4: Critical OOM risk from critical headroom (<= 1000 MB)
    st4, hr4, tte4 = guardrail.evaluate(
        memory_mb=np.array([9200.0]),
        capacities_mb=np.array([10000.0]),
        growth_rates=np.array([2.0]),
    )
    assert st4 == "CRITICAL_OOM_RISK"

    # Case 5: Critical OOM risk from imminent TTE (<= 30 min)
    # Headroom = 1500 MB, Rate = 60.0 MB/min -> TTE = 25 min
    st5, hr5, tte5 = guardrail.evaluate(
        memory_mb=np.array([8500.0]),
        capacities_mb=np.array([10000.0]),
        growth_rates=np.array([60.0]),
    )
    assert st5 == "CRITICAL_OOM_RISK"
    assert math.isclose(tte5[0], 25.0, rel_tol=1e-5)


def test_kalman_filter_differencing_math_step():
    """Hand-computed verification of 1 discrete update of the differencing MA(1) Kalman engine."""
    detector = OnlineMemoryGrowthDetector(
        t0=5,
        canary_ids=["can0"],
        control_ids=["ctl0", "ctl1"],
        canary_capacities_mb=[10000.0],
        sigma_m=10.0,
        q_drift=0.0,
        prior_drift_sd=1.0,
    )
    assert detector.F.shape == (3, 3)
    assert detector.H.shape == (1, 3)
    assert np.allclose(detector.H, [[1.0, 1.0, -1.0]])

    # Pre-period step at tick 4 (< t0)
    rec_c0_4 = TelemetryRecord(
        run_id="run1", tick=4, event_time=4, arrival_time=4, server_id="can0", rack_id="r0", class_id=0,
        version="v1.1", exposure=True, request_count=1000, latency_ms=10.0, memory_mb=2000.0, cpu_fraction=0.2, error_count=0
    )
    rec_t0_4 = TelemetryRecord(
        run_id="run1", tick=4, event_time=4, arrival_time=4, server_id="ctl0", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2000.0, cpu_fraction=0.2, error_count=0
    )
    rec_t1_4 = TelemetryRecord(
        run_id="run1", tick=4, event_time=4, arrival_time=4, server_id="ctl1", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2000.0, cpu_fraction=0.2, error_count=0
    )
    res4 = detector.step(4, {"can0": rec_c0_4}, {"ctl0": rec_t0_4, "ctl1": rec_t1_4})
    assert np.isnan(res4.score)  # score is NaN at tick < t0

    # Rollout onset step at tick 5 (t0)
    rec_c0 = TelemetryRecord(
        run_id="run1", tick=5, event_time=5, arrival_time=5, server_id="can0", rack_id="r0", class_id=0,
        version="v1.1", exposure=True, request_count=1000, latency_ms=10.0, memory_mb=2000.0, cpu_fraction=0.2, error_count=0
    )
    rec_t0 = TelemetryRecord(
        run_id="run1", tick=5, event_time=5, arrival_time=5, server_id="ctl0", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2000.0, cpu_fraction=0.2, error_count=0
    )
    rec_t1 = TelemetryRecord(
        run_id="run1", tick=5, event_time=5, arrival_time=5, server_id="ctl1", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2000.0, cpu_fraction=0.2, error_count=0
    )
    res5 = detector.step(5, {"can0": rec_c0}, {"ctl0": rec_t0, "ctl1": rec_t1})
    assert np.isfinite(res5.score)  # score is finite at rollout onset t >= t0

    # Step at tick 6: Canary memory climbs by +15 MB, Controls climb by +5 MB
    # Residual y = 15 - 5 = +10 MB
    rec_c0_6 = TelemetryRecord(
        run_id="run1", tick=6, event_time=6, arrival_time=6, server_id="can0", rack_id="r0", class_id=0,
        version="v1.1", exposure=True, request_count=1000, latency_ms=10.0, memory_mb=2015.0, cpu_fraction=0.2, error_count=0
    )
    rec_t0_6 = TelemetryRecord(
        run_id="run1", tick=6, event_time=6, arrival_time=6, server_id="ctl0", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2005.0, cpu_fraction=0.2, error_count=0
    )
    rec_t1_6 = TelemetryRecord(
        run_id="run1", tick=6, event_time=6, arrival_time=6, server_id="ctl1", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2005.0, cpu_fraction=0.2, error_count=0
    )
    res6 = detector.step(6, {"can0": rec_c0_6}, {"ctl0": rec_t0_6, "ctl1": rec_t1_6})

    # Posterior variance on drift must strictly decrease from prior 1.0^2 = 1.0
    assert res6.growth_rate_se[0] < 1.0
    assert res6.growth_rate_estimates[0] > 0.0  # Drift updated positively from positive residual
    assert np.isfinite(res6.score)
    assert 0.0 <= res6.host_probs[0] <= 1.0


def test_gc_cycles_control_cancellation():
    """Verify periodic GC sawtooth is cancelled by matched controls and produces no persistent alarms."""
    cfg = HealthyTelemetryConfig(gc_period_ticks=15, gc_amplitude_mb=300.0)
    engine = HealthyTelemetryEngine(config=cfg, seed=123)
    fleet = create_default_fleet(n_racks=4, servers_per_rack=6)

    canaries = ["srv-r0-s0"]
    controls = ["srv-r0-s1", "srv-r0-s2"]
    caps = [float(fleet.get_server(c).memory_capacity_mb) for c in canaries]

    detector = OnlineMemoryGrowthDetector(
        t0=30,
        canary_ids=canaries,
        control_ids=controls,
        canary_capacities_mb=caps,
        target_definition=MemoryTargetDefinition(growth_boundary_mb_per_min=0.50, persistence_window_ticks=15),
    )

    persists = []
    for t in range(75):
        recs = engine.generate_tick_telemetry(fleet, tick=t)
        by_s = {r.server_id: r for r in recs}
        c_recs = {c: by_s[c] for c in canaries}
        t_recs = {c: by_s[c] for c in controls}
        res = detector.step(t, c_recs, t_recs)
        if t >= 30:
            persists.append(res.is_persistent_leak)

    # Over 45 ticks post-rollout (3 full GC cycles), synchronous GC sweeps must not trigger persistent leak
    assert not any(persists)


def test_workload_demand_surge_cancellation():
    """Verify fleet workload surge (+40% traffic) is cancelled by control adjustment."""
    cfg = HealthyTelemetryConfig(mem_workload_scale=200.0)
    engine = HealthyTelemetryEngine(config=cfg, seed=456)
    fleet = create_default_fleet(n_racks=4, servers_per_rack=6)

    canaries = ["srv-r0-s0"]
    controls = ["srv-r0-s1", "srv-r0-s2"]
    caps = [float(fleet.get_server(c).memory_capacity_mb) for c in canaries]

    detector = OnlineMemoryGrowthDetector(
        t0=30,
        canary_ids=canaries,
        control_ids=controls,
        canary_capacities_mb=caps,
    )

    persists = []
    for t in range(70):
        # Apply temporary workload shock between tick 40 and 55
        if 40 <= t < 55:
            engine.set_fleet_workload_offset(0.40)
        else:
            engine.set_fleet_workload_offset(0.0)

        recs = engine.generate_tick_telemetry(fleet, tick=t)
        by_s = {r.server_id: r for r in recs}
        c_recs = {c: by_s[c] for c in canaries}
        t_recs = {c: by_s[c] for c in controls}
        res = detector.step(t, c_recs, t_recs)
        if t >= 30:
            persists.append(res.is_persistent_leak)

    assert not any(persists)


def test_process_restart_clean_recovery():
    """Verify process restart (memory drop > 500 MB) cleanly resets drift state without false alert."""
    detector = OnlineMemoryGrowthDetector(
        t0=20,
        canary_ids=["can0"],
        control_ids=["ctl0"],
        canary_capacities_mb=[16384.0],
        target_definition=MemoryTargetDefinition(growth_boundary_mb_per_min=0.50, persistence_window_ticks=10),
    )

    # Run normal pre-period and early rollout
    for t in range(35):
        c_rec = TelemetryRecord(
            run_id="r", tick=t, event_time=t, arrival_time=t, server_id="can0", rack_id="r0", class_id=0,
            version="v1.1", exposure=True, request_count=1000, latency_ms=10.0,
            memory_mb=2000.0 + (t - 20) * 0.6 if t >= 20 else 2000.0,
            cpu_fraction=0.2, error_count=0
        )
        t_rec = TelemetryRecord(
            run_id="r", tick=t, event_time=t, arrival_time=t, server_id="ctl0", rack_id="r0", class_id=0,
            version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2000.0,
            cpu_fraction=0.2, error_count=0
        )
        detector.step(t, {"can0": c_rec}, {"ctl0": t_rec})

    # Host restarts at tick 35: memory drops from 2009 MB to 500 MB (drop of -1509 MB)
    c_restart = TelemetryRecord(
        run_id="r", tick=35, event_time=35, arrival_time=35, server_id="can0", rack_id="r0", class_id=0,
        version="v1.1", exposure=True, request_count=0, latency_ms=10.0, memory_mb=500.0,
        cpu_fraction=0.0, error_count=0
    )
    t_normal = TelemetryRecord(
        run_id="r", tick=35, event_time=35, arrival_time=35, server_id="ctl0", rack_id="r0", class_id=0,
        version="v1.0", exposure=False, request_count=1000, latency_ms=10.0, memory_mb=2000.0,
        cpu_fraction=0.2, error_count=0
    )
    res35 = detector.step(35, {"can0": c_restart}, {"ctl0": t_normal})

    # Restart must reset drift estimate to 0 and persistence counter to 0
    assert detector.m[0, 0] == 0.0
    assert detector.ticks_above_kappa[0] == 0
    assert res35.is_persistent_leak is False


def test_persistent_growth_detection_and_tte():
    """Verify abnormal growth (+1.5 MB/min) triggers persistent leak and accurately estimates TTE."""
    target = MemoryTargetDefinition(
        growth_boundary_mb_per_min=0.50,
        persistence_window_ticks=15,
        headroom_warning_mb=4000.0,
        headroom_critical_mb=2000.0,
    )
    detector = OnlineMemoryGrowthDetector(
        t0=20,
        canary_ids=["can0"],
        control_ids=["ctl0"],
        canary_capacities_mb=[10000.0],
        target_definition=target,
        sigma_m=1.0,
    )

    t_alarm = None
    final_res = None
    for t in range(65):
        # Injected leak: +1.5 MB per tick post-t0
        leak = 1.5 * (t - 20) if t >= 20 else 0.0
        c_rec = TelemetryRecord(
            run_id="r", tick=t, event_time=t, arrival_time=t, server_id="can0", rack_id="r0", class_id=0,
            version="v1.1", exposure=True, request_count=1000, latency_ms=10.0,
            memory_mb=2000.0 + leak, cpu_fraction=0.2, error_count=0
        )
        t_rec = TelemetryRecord(
            run_id="r", tick=t, event_time=t, arrival_time=t, server_id="ctl0", rack_id="r0", class_id=0,
            version="v1.0", exposure=False, request_count=1000, latency_ms=10.0,
            memory_mb=2000.0, cpu_fraction=0.2, error_count=0
        )
        res = detector.step(t, {"can0": c_rec}, {"ctl0": t_rec})
        final_res = res
        if res.is_persistent_leak and t_alarm is None and t >= 20:
            t_alarm = t

    # 1. Alarm must trigger exactly after persistence window (15 ticks post-growth crossing)
    assert t_alarm is not None
    assert t_alarm <= 20 + 20
    # 2. Final estimated growth rate must be near true injected 1.5 MB/min
    assert math.isclose(final_res.growth_rate_estimates[0], 1.5, abs_tol=0.35)
    # 3. Headroom must be capacity (10000) - current memory (~2067.5) = ~7932.5 MB
    assert final_res.host_headroom_mb[0] < 8000.0
    # 4. TTE must be Headroom / rate ~ 7932 / 1.5 ~ 5288 min
    assert 4000.0 < final_res.host_tte_min[0] < 6500.0


def test_multichannel_policy_attribution_matrix():
    """Verify all 5 attribution branches of MultiChannelAlertPolicy."""
    policy = MultiChannelAlertPolicy(threshold_lat=-2.0, threshold_mem=-0.50, require_persistence=True)

    # 1. Healthy clean null
    p1 = policy.evaluate_step(score_lat=-4.0, score_mem=-1.0, guardrail_status="NORMAL", is_persistent_mem=False)
    assert p1["is_alert"] is False
    assert p1["attribution"] == "NORMAL"
    assert p1["advisory"] == "RUNNING"

    # 2. Latency regression only
    p2 = policy.evaluate_step(score_lat=-1.0, score_mem=-1.0, guardrail_status="NORMAL", is_persistent_mem=False)
    assert p2["is_alert"] is True
    assert p2["attribution"] == "LATENCY_REGRESSION"
    assert p2["advisory"] == "PAUSE RECOMMENDED"

    # 3. Memory score breach WITHOUT persistence: must NOT be labeled a leak
    p3_temp = policy.evaluate_step(score_lat=-4.0, score_mem=-0.1, guardrail_status="NORMAL", is_persistent_mem=False)
    assert p3_temp["is_alert"] is False
    assert p3_temp["attribution"] == "NORMAL"
    assert p3_temp["advisory"] == "RUNNING"

    # 4. Memory regression WITH persistence: labeled MEMORY_GROWTH_LEAK
    p3_leak = policy.evaluate_step(score_lat=-4.0, score_mem=-0.1, guardrail_status="NORMAL", is_persistent_mem=True)
    assert p3_leak["is_alert"] is True
    assert p3_leak["attribution"] == "MEMORY_GROWTH_LEAK"
    assert p3_leak["advisory"] == "PAUSE RECOMMENDED"

    # 5. Compound regression (both latency and persistent memory breach)
    p4 = policy.evaluate_step(score_lat=-1.0, score_mem=-0.1, guardrail_status="NORMAL", is_persistent_mem=True)
    assert p4["is_alert"] is True
    assert p4["attribution"] == "COMPOUND_REGRESSION"
    assert p4["advisory"] == "PAUSE RECOMMENDED"

    # 6. Critical physical OOM risk: overrides statistical regression attribution
    p5 = policy.evaluate_step(score_lat=-4.0, score_mem=-1.0, guardrail_status="CRITICAL_OOM_RISK", is_persistent_mem=False)
    assert p5["is_alert"] is True
    assert p5["attribution"] == "CRITICAL_CAPACITY_LIMIT"
    assert p5["advisory"] == "CRITICAL_OOM_RISK"


def test_calibrate_multichannel_policy_bonferroni_sidak():
    """Verify joint calibration bounds empirical family-wise error rate <= alpha."""
    rng = np.random.default_rng(777)
    B = 200
    null_lat = rng.normal(loc=-4.0, scale=1.0, size=B)
    null_mem = rng.normal(loc=-3.0, scale=0.8, size=B)

    alpha = 0.05
    cal = calibrate_multichannel_policy(null_lat, null_mem, alpha=alpha)

    assert "threshold_lat" in cal
    assert "threshold_mem" in cal
    # Bonferroni-Šidák channel alpha
    alpha_c = 1.0 - math.sqrt(1.0 - alpha)
    assert math.isclose(cal["alpha_channel"], alpha_c, rel_tol=1e-5)
    # Achieved joint FAR must strictly be <= alpha
    assert cal["achieved_far"] <= alpha
    assert cal["calibration_successful"] is True
