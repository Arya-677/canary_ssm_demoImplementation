"""Tests for Virtual Data Center Fault Engine: Scopes, Resource Pressure, OOM, and Pairing (Prompt 3)."""
from __future__ import annotations

import math
import numpy as np
import pytest

from canary_ssm.telemetry import TelemetryRecord
from canary_ssm.faults import (
    FaultCategory,
    FaultDefinition,
    FaultScope,
    FaultType,
    EvaluatorFaultTruthStore,
)
from canary_ssm.world import (
    VirtualWorld,
    create_default_fleet,
)


# =====================================================================
# 1. Fault Definitions & Validation
# =====================================================================
def test_fault_definitions_and_categories():
    """Faults must distinguish infrastructure from release categories and enforce validation."""
    assert FaultType.SERVER_OUTAGE.category == FaultCategory.INFRASTRUCTURE
    assert FaultType.RACK_NETWORK_LATENCY.category == FaultCategory.INFRASTRUCTURE
    assert FaultType.PROCESS_MEMORY_LEAK.category == FaultCategory.RELEASE
    assert FaultType.RELEASE_LATENCY_REGRESSION.category == FaultCategory.RELEASE

    # Valid infrastructure fault
    f1 = FaultDefinition(
        fault_id="f1",
        fault_type=FaultType.RACK_NETWORK_LATENCY,
        scope=FaultScope.RACK,
        target_id="rack-1",
        onset_tick=10,
        duration=20,
        severity=0.20,
    )
    assert f1.expiry_tick == 30
    assert f1.is_active_at(10) is True
    assert f1.is_active_at(25) is True
    assert f1.is_active_at(30) is False

    # Release fault requires target_version
    with pytest.raises(ValueError, match="requires target_version"):
        FaultDefinition(
            fault_id="f2",
            fault_type=FaultType.PROCESS_MEMORY_LEAK,
            scope=FaultScope.SERVER,
            target_id="srv-0",
            onset_tick=10,
            duration=20,
            severity=15.0,
            target_version=None,
        )

    # Negative duration rejected
    with pytest.raises(ValueError, match="duration"):
        FaultDefinition(
            fault_id="f3",
            fault_type=FaultType.SERVER_OUTAGE,
            scope=FaultScope.SERVER,
            target_id="srv-0",
            onset_tick=10,
            duration=-5,
            severity=1.0,
        )


# =====================================================================
# 2. Scope Verification: Rack Fault vs Release Fault
# =====================================================================
def test_rack_fault_affects_all_servers_in_rack():
    """A rack fault must affect ALL servers in that rack (both baseline and canary), leaving other racks intact."""
    world = VirtualWorld(seed=100)
    # Mark srv-r1-s0 as a canary
    world.set_server_version("srv-r1-s0", "v1.1.0-canary")

    # Inject rack network latency on rack-1 from tick 10 to 25
    fault = FaultDefinition(
        fault_id="rack1-slowdown",
        fault_type=FaultType.RACK_NETWORK_LATENCY,
        scope=FaultScope.RACK,
        target_id="rack-1",
        onset_tick=10,
        duration=15,
        severity=0.30,  # ~+35% latency
    )
    world.inject_fault(fault)

    # Step to tick 15 (fault is active)
    res = world.step(15)
    t15_recs = {r.server_id: r for r in res.telemetry if r.tick == 15}

    # All 6 servers in rack-1 must have elevated latency
    rack1_recs = [r for r in t15_recs.values() if r.rack_id == "rack-1"]
    other_recs = [r for r in t15_recs.values() if r.rack_id != "rack-1"]

    assert len(rack1_recs) == 6
    mean_rack1_lat = float(np.mean([r.latency_ms for r in rack1_recs]))
    mean_other_lat = float(np.mean([r.latency_ms for r in other_recs]))

    assert mean_rack1_lat > mean_other_lat * 1.25, f"Expected rack 1 elevation, got {mean_rack1_lat} vs {mean_other_lat}"

    # Verify both canary and controls in rack-1 are affected
    canary_rec = t15_recs["srv-r1-s0"]
    control_rec = t15_recs["srv-r1-s1"]
    assert canary_rec.exposure is True
    assert control_rec.exposure is False
    assert canary_rec.latency_ms > mean_other_lat * 1.20
    assert control_rec.latency_ms > mean_other_lat * 1.20

    # Truth store check
    truth = world.truth_store.get_tick_truth(15)
    assert truth is not None
    assert "rack1-slowdown" in truth.active_fault_ids
    for sid in [f"srv-r1-s{i}" for i in range(6)]:
        assert sid in truth.affected_server_ids


def test_release_fault_scope_and_no_pre_exposure():
    """A release fault must ONLY affect exposed canary servers, and never before exposure."""
    world = VirtualWorld(seed=200)

    # Release fault targeting version "v1.1.0-canary", onset tick 5, duration 20
    rel_fault = FaultDefinition(
        fault_id="rel-bug",
        fault_type=FaultType.RELEASE_LATENCY_REGRESSION,
        scope=FaultScope.SERVER,
        target_id="fleet",
        onset_tick=5,
        duration=20,
        severity=0.25,  # +28% latency
        target_version="v1.1.0-canary",
    )
    world.inject_fault(rel_fault)

    # Step to tick 8 BEFORE any server is exposed to v1.1.0-canary
    res1 = world.step(8)
    t8_recs = {r.server_id: r for r in res1.telemetry if r.tick == 8}

    # Invariant: NO server is exposed yet, so NO server must be affected!
    for sid, r in t8_recs.items():
        assert r.exposure is False
        assert r.version == "v1.0.0-baseline"

    truth_t8 = world.truth_store.get_tick_truth(8)
    assert truth_t8 is not None
    # No exposed servers -> affected list must be empty!
    assert len(truth_t8.affected_server_ids) == 0

    # Deploy release to srv-r0-s0 and srv-r2-s0 at tick 8
    world.set_server_version("srv-r0-s0", "v1.1.0-canary")
    world.set_server_version("srv-r2-s0", "v1.1.0-canary")

    # Step to tick 15 (now exposed and fault is active)
    res2 = world.step(7)
    t15_recs = {r.server_id: r for r in res2.telemetry if r.tick == 15}

    canary1 = t15_recs["srv-r0-s0"]
    canary2 = t15_recs["srv-r2-s0"]
    control_same_rack = t15_recs["srv-r0-s1"]

    assert canary1.exposure is True
    assert canary2.exposure is True
    assert control_same_rack.exposure is False

    # Canaries must have elevated latency due to release regression
    assert canary1.latency_ms > control_same_rack.latency_ms * 1.15
    assert canary2.latency_ms > control_same_rack.latency_ms * 1.15

    # Truth store check
    truth_t15 = world.truth_store.get_tick_truth(15)
    assert truth_t15 is not None
    assert set(truth_t15.affected_server_ids) == {"srv-r0-s0", "srv-r2-s0"}


# =====================================================================
# 3. Memory Leak, Resource Pressure Coupling, and Simulated OOM
# =====================================================================
def test_memory_leak_pressure_and_simulated_oom():
    """A memory leak must increase modeled memory, trigger pressure/thrashing, and crash at OOM."""
    world = VirtualWorld(seed=300)

    # Expose srv-r0-s0 to candidate release
    world.set_server_version("srv-r0-s0", "v1.1.0-canary")
    srv = world.fleet.get_server("srv-r0-s0")
    # Base memory = 2048 MB, Capacity = 16384 MB
    assert srv.base_memory_mb == 2048.0
    assert srv.memory_capacity_mb == 16384.0

    # Fast leak: 800 MB per minute
    # At tick 0: ~2048 MB
    # At tick 12: ~11,648 MB (> 70% = 11,468 MB -> Zone 2: Pressure)
    # At tick 16: ~14,848 MB (> 90% = 14,745 MB -> Zone 3: Thrashing)
    # At tick 18: ~16,448 MB (>= 16,384 MB -> Zone 4: OOM Crash!)
    leak_fault = FaultDefinition(
        fault_id="fast-leak",
        fault_type=FaultType.PROCESS_MEMORY_LEAK,
        scope=FaultScope.SERVER,
        target_id="srv-r0-s0",
        onset_tick=1,
        duration=30,
        severity=800.0,  # 800 MB/min
        target_version="v1.1.0-canary",
        restart_duration=2,
    )
    world.inject_fault(leak_fault)

    # 1. Step to tick 5 (Normal zone: <70% capacity)
    res_normal = world.step(5)
    t5_rec = [r for r in res_normal.telemetry if r.tick == 5 and r.server_id == "srv-r0-s0"][0]
    assert t5_rec.memory_mb > 5000.0
    assert t5_rec.memory_mb < 0.70 * srv.memory_capacity_mb
    assert t5_rec.observed is True

    # 2. Step to tick 13 (Pressure zone: 70% - 90%)
    res_pressure = world.step(8)
    t13_rec = [r for r in res_pressure.telemetry if r.tick == 13 and r.server_id == "srv-r0-s0"][0]
    assert t13_rec.memory_mb >= 0.70 * srv.memory_capacity_mb
    assert t13_rec.memory_mb < 0.90 * srv.memory_capacity_mb
    # Pressure elevates CPU utilization
    ctrl_rec = [r for r in res_pressure.telemetry if r.tick == 13 and r.server_id == "srv-r0-s1"][0]
    assert t13_rec.cpu_fraction > ctrl_rec.cpu_fraction

    # 3. Step to tick 17 (Thrashing zone: >90%)
    res_thrash = world.step(4)
    t17_rec = [r for r in res_thrash.telemetry if r.tick == 17 and r.server_id == "srv-r0-s0"][0]
    assert t17_rec.memory_mb >= 0.90 * srv.memory_capacity_mb
    # Severe latency rise and error spike under thrashing
    ctrl_t17 = [r for r in res_thrash.telemetry if r.tick == 17 and r.server_id == "srv-r0-s1"][0]
    assert t17_rec.latency_ms > ctrl_t17.latency_ms * 1.20
    assert t17_rec.error_count > ctrl_t17.error_count * 5

    # 4. Step to tick 19 (OOM crash and restart gap!)
    res_oom = world.step(2)
    t19_rec = [r for r in res_oom.telemetry if r.tick == 19 and r.server_id == "srv-r0-s0"][0]
    # Server crashed! Offline and unobserved
    assert t19_rec.observed is False
    assert t19_rec.request_count == 0

    # Verify crash is recorded in truth store
    assert len(world.truth_store.oom_crash_events) >= 1
    crash_event = world.truth_store.oom_crash_events[0]
    assert crash_event["server_id"] == "srv-r0-s0"
    assert crash_event["crash_tick"] in (18, 19)

    # 5. Step to tick 22 (Recovered after restart!)
    res_restart = world.step(3)
    t22_rec = [r for r in res_restart.telemetry if r.tick == 22 and r.server_id == "srv-r0-s0"][0]
    # Server restarted: online, memory reset to near baseline!
    assert t22_rec.observed is True
    assert t22_rec.memory_mb < 5000.0  # Freshly restarted memory


# =====================================================================
# 4. Overlap & Recovery Semantics
# =====================================================================
def test_overlapping_faults_and_recovery():
    """Overlapping rack and release faults must compose, and system recovers when faults expire."""
    world = VirtualWorld(seed=400)
    world.set_server_version("srv-r0-s0", "v1.1.0-canary")

    # Fault 1: Rack network latency on rack-0 (ticks 10 to 20)
    f_rack = FaultDefinition(
        fault_id="f-rack",
        fault_type=FaultType.RACK_NETWORK_LATENCY,
        scope=FaultScope.RACK,
        target_id="rack-0",
        onset_tick=10,
        duration=10,
        severity=0.20,
    )
    # Fault 2: Release latency regression on v1.1.0-canary (ticks 15 to 25)
    f_rel = FaultDefinition(
        fault_id="f-rel",
        fault_type=FaultType.RELEASE_LATENCY_REGRESSION,
        scope=FaultScope.SERVER,
        target_id="fleet",
        onset_tick=15,
        duration=10,
        severity=0.20,
        target_version="v1.1.0-canary",
    )
    world.inject_fault(f_rack)
    world.inject_fault(f_rel)

    # Advance to tick 18 where BOTH faults overlap on srv-r0-s0
    res = world.step(18)
    t18 = {r.server_id: r for r in res.telemetry if r.tick == 18}

    canary = t18["srv-r0-s0"]           # Has BOTH rack fault AND release fault
    rack_ctrl = t18["srv-r0-s1"]        # Has ONLY rack fault
    other_ctrl = t18["srv-r1-s1"]       # Has NEITHER fault

    assert rack_ctrl.latency_ms > other_ctrl.latency_ms * 1.15
    # Overlapping composition: canary experiences combined elevation!
    assert canary.latency_ms > rack_ctrl.latency_ms * 1.15

    # Advance to tick 30 (BOTH faults have expired -> full recovery!)
    res_rec = world.step(12)
    t30 = {r.server_id: r for r in res_rec.telemetry if r.tick == 30}
    canary_t30 = t30["srv-r0-s0"]
    rack_ctrl_t30 = t30["srv-r0-s1"]
    other_ctrl_t30 = t30["srv-r1-s1"]

    # Difference between canary and controls in same class must return to normal baseline jitter (<10%)
    diff = abs(canary_t30.latency_ms - rack_ctrl_t30.latency_ms) / rack_ctrl_t30.latency_ms
    assert diff < 0.10, f"System failed to recover after faults expired: diff={diff}"


# =====================================================================
# 5. Paired Null/Harm Exogenous Stream Sharing
# =====================================================================
def test_paired_null_harm_share_exogenous_streams():
    """Paired null and harm runs must share bitwise identical exogenous workload and noise streams."""
    base_seed = 54321

    # World Null: No faults
    world_null = VirtualWorld(seed=base_seed)
    res_null = world_null.step(20)

    # World Harm: Injected release regression + extra stochastic evaluations
    world_harm = VirtualWorld(seed=base_seed)
    world_harm.set_server_version("srv-r0-s0", "v1.1.0-canary")
    f_harm = FaultDefinition(
        fault_id="harm-reg",
        fault_type=FaultType.RELEASE_LATENCY_REGRESSION,
        scope=FaultScope.SERVER,
        target_id="srv-r0-s0",
        onset_tick=10,
        duration=10,
        severity=0.15,
        target_version="v1.1.0-canary",
    )
    world_harm.inject_fault(f_harm)
    res_harm = world_harm.step(20)

    # Controls in unexposed racks (e.g. rack-2, server 3) must be BITWISE IDENTICAL
    # because exogenous workload, factor, and noise streams are shared!
    null_srv2 = [r for r in res_null.telemetry if r.server_id == "srv-r2-s3"]
    harm_srv2 = [r for r in res_harm.telemetry if r.server_id == "srv-r2-s3"]

    assert len(null_srv2) == len(harm_srv2)
    for rn, rh in zip(null_srv2, harm_srv2):
        assert rn.to_dict() == rh.to_dict()
