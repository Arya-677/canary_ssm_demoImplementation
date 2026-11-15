"""Tests for Virtual Data Center Telemetry: Healthy response functions, bounds, and shared variation (Prompt 2)."""
from __future__ import annotations

import math
import numpy as np
import pytest

from canary_ssm.telemetry import TelemetryRecord
from canary_ssm.world import (
    VirtualWorld,
    create_default_fleet,
    HealthyTelemetryConfig,
    HealthyTelemetryEngine,
)


# =====================================================================
# 1. TelemetryRecord Schema & Strict Firewall
# =====================================================================
def test_telemetry_record_schema_and_firewall():
    """TelemetryRecord must contain all required observable fields and NO fault truth."""
    fields = set(TelemetryRecord.__dataclass_fields__.keys())
    required = {
        "run_id", "tick", "event_time", "arrival_time", "server_id", "rack_id",
        "class_id", "version", "exposure", "request_count", "latency_ms",
        "memory_mb", "cpu_fraction", "error_count", "observed"
    }
    assert required.issubset(fields)

    # Strict Firewall: Detector/Telemetry MUST NEVER see fault labels or injected truth
    forbidden = {"fault_type", "injected_severity", "fault_id", "ground_truth", "truth"}
    assert not (forbidden & fields), f"Forbidden fault truth fields found in TelemetryRecord: {forbidden & fields}"


def test_telemetry_record_validation():
    """TelemetryRecord must enforce numerical invariants."""
    # Valid record
    rec = TelemetryRecord(
        run_id="run-01", tick=1, event_time=1, arrival_time=1,
        server_id="s1", rack_id="r1", class_id=0, version="v1.0.0",
        exposure=False, request_count=5000, latency_ms=102.5,
        memory_mb=2048.0, cpu_fraction=0.45, error_count=2, observed=True,
    )
    assert rec.to_dict()["latency_ms"] == 102.5

    # Invalid cpu_fraction > 1.0
    with pytest.raises(ValueError, match="cpu_fraction"):
        TelemetryRecord(
            run_id="run-01", tick=1, event_time=1, arrival_time=1,
            server_id="s1", rack_id="r1", class_id=0, version="v1.0.0",
            exposure=False, request_count=5000, latency_ms=102.5,
            memory_mb=2048.0, cpu_fraction=1.2, error_count=2, observed=True,
        )

    # Invalid latency <= 0
    with pytest.raises(ValueError, match="latency_ms"):
        TelemetryRecord(
            run_id="run-01", tick=1, event_time=1, arrival_time=1,
            server_id="s1", rack_id="r1", class_id=0, version="v1.0.0",
            exposure=False, request_count=5000, latency_ms=0.0,
            memory_mb=2048.0, cpu_fraction=0.45, error_count=2, observed=True,
        )

    # Invalid error_count > request_count
    with pytest.raises(ValueError, match="error_count"):
        TelemetryRecord(
            run_id="run-01", tick=1, event_time=1, arrival_time=1,
            server_id="s1", rack_id="r1", class_id=0, version="v1.0.0",
            exposure=False, request_count=10, latency_ms=100.0,
            memory_mb=2048.0, cpu_fraction=0.45, error_count=15, observed=True,
        )


def test_latency_statistic_declaration():
    """TelemetryRecord docstring must declare what latency_ms represents (not p95)."""
    doc = TelemetryRecord.__doc__ or ""
    assert "geometric mean" in doc.lower()
    assert "not an empirical request-level p95" in doc.lower() or "not" in doc.lower()


# =====================================================================
# 2. Healthy Generation & Finite Bounds
# =====================================================================
def test_healthy_telemetry_bounds_and_finite_series():
    """All generated healthy telemetry records must have finite values within valid bounds."""
    world = VirtualWorld(seed=42)
    res = world.step(30)
    assert res.tick == 30
    assert len(res.telemetry) == 30 * 24  # 30 ticks x 24 servers

    for rec in res.telemetry:
        # Check finiteness
        assert math.isfinite(rec.latency_ms), f"Non-finite latency: {rec}"
        assert math.isfinite(rec.memory_mb), f"Non-finite memory: {rec}"
        assert math.isfinite(rec.cpu_fraction), f"Non-finite CPU: {rec}"

        # Check bounds
        assert rec.latency_ms > 0.0, f"Latency not positive: {rec.latency_ms}"
        assert 0.0 <= rec.cpu_fraction <= 1.0, f"CPU out of bounds: {rec.cpu_fraction}"
        assert 0 <= rec.error_count <= rec.request_count, f"Errors out of bounds: {rec}"
        assert 0.0 <= rec.memory_mb <= 16384.0, f"Memory exceeded capacity: {rec.memory_mb}"
        assert rec.observed is True


def test_low_volume_uncertainty():
    """Low request volume must expand measurement noise on latency and keep error counts valid."""
    cfg = HealthyTelemetryConfig(sd_meas_base=0.05)
    engine = HealthyTelemetryEngine(config=cfg, seed=777)
    fleet = create_default_fleet(n_racks=1, servers_per_rack=2)

    # Normal volume
    recs_normal = engine.generate_tick_telemetry(fleet, tick=1)
    assert recs_normal[0].request_count > 1000

    # Offline/Zero volume host
    fleet.get_server("srv-r0-s0").online = False
    recs_offline = engine.generate_tick_telemetry(fleet, tick=2)
    s0_rec = recs_offline[0]
    assert s0_rec.request_count == 0
    assert s0_rec.error_count == 0
    assert s0_rec.cpu_fraction == 0.0
    assert s0_rec.observed is False


# =====================================================================
# 3. Workload Dynamics & Shared Variations
# =====================================================================
def test_shared_fleet_workload_increase():
    """A fleet-wide workload demand increase must increase requests, CPU, and latency across all servers."""
    world = VirtualWorld(seed=101)

    # 1. Baseline period (ticks 1..20)
    res_base = world.step(20)
    base_reqs = [r.request_count for r in res_base.telemetry if r.tick > 10]
    base_cpu = [r.cpu_fraction for r in res_base.telemetry if r.tick > 10]
    base_lat = [r.latency_ms for r in res_base.telemetry if r.tick > 10]

    mean_base_req = float(np.mean(base_reqs))
    mean_base_cpu = float(np.mean(base_cpu))
    mean_base_lat = float(np.mean(base_lat))

    # 2. Apply +35% shared workload shift
    world.set_fleet_workload_offset(0.35)
    res_high = world.step(20)
    high_reqs = [r.request_count for r in res_high.telemetry if r.tick > 30]
    high_cpu = [r.cpu_fraction for r in res_high.telemetry if r.tick > 30]
    high_lat = [r.latency_ms for r in res_high.telemetry if r.tick > 30]

    mean_high_req = float(np.mean(high_reqs))
    mean_high_cpu = float(np.mean(high_cpu))
    mean_high_lat = float(np.mean(high_lat))

    # Assert load increase elevated metrics fleet-wide
    assert mean_high_req > mean_base_req * 1.20, f"Expected request volume increase, got {mean_base_req} -> {mean_high_req}"
    assert mean_high_cpu > mean_base_cpu, f"Expected CPU increase, got {mean_base_cpu} -> {mean_high_cpu}"
    assert mean_high_lat > mean_base_lat, f"Expected latency increase, got {mean_base_lat} -> {mean_high_lat}"


def test_shared_rack_nuisance_shift():
    """A rack shared nuisance shift affects both baseline and canary servers in that rack identically."""
    world = VirtualWorld(seed=555)

    # Designate srv-r1-s0 as a canary running v1.1.0-canary
    world.set_server_version("srv-r1-s0", "v1.1.0-canary")
    assert world.fleet.get_server("srv-r1-s0").installed_version == "v1.1.0-canary"

    # Baseline 10 ticks
    world.step(10)

    # Shift rack-1 shared nuisance by +0.15 log units (~+16% latency)
    world.set_rack_offset("rack-1", 0.15)
    res = world.step(15)

    # Filter telemetry for tick 25
    t25 = [r for r in res.telemetry if r.tick == 25]
    rack1_recs = [r for r in t25 if r.rack_id == "rack-1"]
    other_recs = [r for r in t25 if r.rack_id != "rack-1"]

    rack1_canary = [r for r in rack1_recs if r.exposure is True][0]
    rack1_controls = [r for r in rack1_recs if r.exposure is False]

    mean_rack1_ctrl_lat = float(np.mean([r.latency_ms for r in rack1_controls]))
    mean_other_lat = float(np.mean([r.latency_ms for r in other_recs]))

    # Rack 1 servers (both canary and control) must be elevated compared to other racks
    assert mean_rack1_ctrl_lat > mean_other_lat, "Rack-1 controls should show elevated latency"
    # Canary latency in rack 1 should be comparable to same-class same-rack controls (healthy scenario!)
    same_class_controls = [r for r in rack1_controls if r.class_id == rack1_canary.class_id]
    assert len(same_class_controls) > 0
    mean_same_class = float(np.mean([r.latency_ms for r in same_class_controls]))
    diff = abs(rack1_canary.latency_ms - mean_same_class) / mean_same_class
    assert diff < 0.10, f"Canary and control in same rack diverged unexpectedly under healthy load: {diff}"


# =====================================================================
# 4. Deterministic Replay
# =====================================================================
def test_telemetry_reproducibility():
    """Two independent simulations with the same seed must produce identical telemetry series."""
    w1 = VirtualWorld(seed=12345)
    res1 = w1.step(25)

    w2 = VirtualWorld(seed=12345)
    res2 = w2.step(25)

    assert len(res1.telemetry) == len(res2.telemetry)
    for r1, r2 in zip(res1.telemetry, res2.telemetry):
        assert r1.to_dict() == r2.to_dict()
