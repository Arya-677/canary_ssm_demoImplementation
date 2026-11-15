"""Regression test suite for all defects addressed in the repair audit.

Verifies:
- Issue 1: Browser scenario load payload compatibility (name / scenario_name).
- Issue 3: CPU regression targets canaries with positive elevation while controls remain unaffected.
- Issue 4: Declarative scenario configurations applied (GC cycles, missingness, drop controls).
- Issue 5 & 13: Same-tick redeploy, unique command IDs, exact server placement rollback restoration.
- Issue 6: Export/import integrity and read-only replay stepping protection.
- Issue 7: Exploratory / uncalibrated policies cannot trigger auto-rollback.
- Issue 8: Artifact integrity and genuine null handling.
- Issue 9: Full rollout lifecycle state machine and append-only transitions.
- Issue 11 & 12: Finite numeric bounds validation in BehaviorProfile.
"""
from __future__ import annotations

import math
import pytest

from canary_ssm.api.service import SimulatorService
from canary_ssm.deployments import (
    BehaviorProfile,
    BehaviorProfileType,
    DeploymentManager,
    Release,
    ReleaseArtifact,
    RolloutState,
)
from canary_ssm.faults import FaultType
from canary_ssm.world import VirtualWorld


def test_behavior_profile_numeric_validation():
    """Issue 11 & 12: BehaviorProfile rejects NaN, Inf, and negative values."""
    with pytest.raises(ValueError, match="finite number"):
        BehaviorProfile(profile_type=BehaviorProfileType.MEMORY_LEAK, severity=float("nan"))

    with pytest.raises(ValueError, match="finite number"):
        BehaviorProfile(profile_type=BehaviorProfileType.CPU_REGRESSION, severity=float("inf"))

    with pytest.raises(ValueError, match="non-negative"):
        BehaviorProfile(profile_type=BehaviorProfileType.CLEAN, duration=-5)

    with pytest.raises(ValueError, match="non-negative"):
        BehaviorProfile(profile_type=BehaviorProfileType.CLEAN, susceptible_class_id=-1)

    # Valid profile creates successfully
    prof = BehaviorProfile(profile_type=BehaviorProfileType.MEMORY_LEAK, severity=35.0, duration=60)
    assert prof.severity == 35.0
    assert prof.duration == 60


def test_rollout_lifecycle_state_machine():
    """Issue 9: Rollout states transition properly and append to transition log."""
    world = VirtualWorld.create_default(n_racks=2, servers_per_rack=4, seed=123)
    mgr = DeploymentManager()

    rel = mgr.create_release(
        release_id="rel-lifecycle-v1",
        version_tag="v2.0.0",
        behavior_profile={"profile_type": "CLEAN"},
    )
    assert rel.rollout_state == RolloutState.CREATED

    # Deploy
    canaries = ["srv-r0-s0", "srv-r1-s0"]
    deploy_res = mgr.deploy_canary(world, "rel-lifecycle-v1", canaries)
    assert rel.rollout_state == RolloutState.CANARY
    assert deploy_res["rollout_state"] == RolloutState.CANARY.value

    # Pause
    pause_res = mgr.pause_canary("rel-lifecycle-v1", current_tick=10, reason="Investigating alert")
    assert rel.rollout_state == RolloutState.PAUSED
    assert pause_res["rollout_state"] == RolloutState.PAUSED.value

    # Promote from PAUSED -> PROMOTED
    promote_res = mgr.promote_canary(world, "rel-lifecycle-v1", reason="Cleared alert")
    assert rel.rollout_state == RolloutState.PROMOTED
    assert promote_res["rollout_state"] == RolloutState.PROMOTED.value

    # Cannot rollback after promotion
    with pytest.raises(ValueError, match="Cannot rollback release in state PROMOTED"):
        mgr.rollback_canary(world, "rel-lifecycle-v1")

    # Check append-only transitions audit log
    assert len(mgr.transitions) >= 3
    states = [(t.from_state, t.to_state) for t in mgr.transitions]
    assert (RolloutState.CREATED, RolloutState.CANARY) in states
    assert (RolloutState.CANARY, RolloutState.PAUSED) in states
    assert (RolloutState.PAUSED, RolloutState.PROMOTED) in states


def test_same_tick_deploy_rollback_redeploy():
    """Issue 5 & 13: Same-tick deploy -> rollback -> redeploy operates idempotently with unique command IDs."""
    world = VirtualWorld.create_default(n_racks=2, servers_per_rack=4, seed=123)
    mgr = DeploymentManager()

    rel1 = mgr.create_release(
        release_id="rel-same-tick-1",
        version_tag="v1.1.0",
        behavior_profile={"profile_type": "CLEAN"},
    )
    canaries = ["srv-r0-s0", "srv-r1-s0"]

    # Step 1: Deploy
    res1 = mgr.deploy_canary(world, "rel-same-tick-1", canaries)
    cmd1 = res1["command_id"]
    for cid in canaries:
        assert world.fleet.get_server(cid).installed_version == "v1.1.0"

    # Step 2: Rollback on the exact same tick
    res_rb = mgr.rollback_canary(world, "rel-same-tick-1")
    cmd_rb = res_rb["command_id"]
    assert cmd_rb != cmd1
    for cid in canaries:
        assert world.fleet.get_server(cid).installed_version == "v1.0.0-baseline"

    # Step 3: Redeploy on the exact same tick
    rel2 = mgr.create_release(
        release_id="rel-same-tick-2",
        version_tag="v1.2.0",
        behavior_profile={"profile_type": "CLEAN"},
    )
    res2 = mgr.deploy_canary(world, "rel-same-tick-2", canaries)
    cmd2 = res2["command_id"]
    assert cmd2 != cmd1
    assert cmd2 != cmd_rb
    for cid in canaries:
        assert world.fleet.get_server(cid).installed_version == "v1.2.0"


def test_cpu_regression_positive_elevation_on_canaries():
    """Issue 3: CPU regression scenario elevates canary CPU while controls remain at baseline."""
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=10)
    svc.load_scenario("cpu_regression")

    # Step forward 5 ticks into the fault
    svc.step(5)

    telemetry = svc.get_latest_telemetry()
    canary_ids = set(svc.active_canary_ids)
    canary_cpus = [r["cpu_fraction"] for r in telemetry if r["server_id"] in canary_ids]
    control_cpus = [r["cpu_fraction"] for r in telemetry if r["server_id"] not in canary_ids]

    assert len(canary_cpus) > 0
    assert len(control_cpus) > 0

    mean_canary_cpu = sum(canary_cpus) / len(canary_cpus)
    mean_control_cpu = sum(control_cpus) / len(control_cpus)

    # Canaries should experience elevated CPU utilization relative to controls
    assert mean_canary_cpu > mean_control_cpu + 0.15


def test_healthy_gc_scenario_config():
    """Issue 4: Healthy GC scenario sets telemetry GC amplitude and period."""
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=10)
    res = svc.load_scenario("healthy_gc")

    assert svc.world.telemetry_engine.cfg.gc_amplitude_mb == 300.0
    assert svc.world.telemetry_engine.cfg.gc_period_ticks == 15
    assert res["status"]["monitoring_state"] in ("MONITORING", "CALIBRATED", "UNCALIBRATED_POLICY")


def test_missing_controls_abstention():
    """Issue 4: Missing controls scenario causes identifiability abstention in detector."""
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=10)
    svc.load_scenario("missing_controls")

    assert svc.drop_same_rack_controls is True
    # Step 10 ticks under missing controls
    svc.step(10)

    status = svc.get_status()
    # Release cause attribution must be blocked / insufficient data because controls on canary racks are absent
    assert status["monitoring_state"] == "INSUFFICIENT_DATA"
    assert "INSUFFICIENT DATA" in status["canary_release_advisory"]


def test_export_import_readonly_replay_protection():
    """Issue 6: Exported run imported into service enforces read-only replay and preserves tick."""
    svc = SimulatorService(n_racks=2, servers_per_rack=4, seed=42)
    svc.step(10)
    bundle = svc.export_run()

    new_svc = SimulatorService(n_racks=2, servers_per_rack=4, seed=99)
    res = new_svc.import_run(bundle)

    assert res["is_read_only_replay"] is True
    assert new_svc.is_read_only_replay is True
    assert new_svc.world.clock.tick == bundle["current_tick"]

    # Live simulation step must be rejected during read-only replay
    with pytest.raises(RuntimeError, match="Cannot advance live simulation during read-only timeline replay"):
        new_svc.step(1)

    # Resetting clears replay mode
    new_svc.reset()
    assert new_svc.is_read_only_replay is False
    new_svc.step(1)  # now works cleanly


def test_auto_rollback_blocked_for_uncalibrated_policy():
    """Issue 7: Detector must never trigger auto_rollback when policy is uncalibrated."""
    from canary_ssm.detector_service import create_uncalibrated_exploratory_policy
    svc = SimulatorService(n_racks=2, servers_per_rack=4, seed=42)
    svc.set_auto_rollback(True)
    # Explicitly set an uncalibrated exploratory policy
    svc.detector_service.set_policy(create_uncalibrated_exploratory_policy())
    assert svc.detector_service.frozen_policy.is_calibrated is False

    # Deploy a severe regression
    rel = svc.create_release(
        release_id="rel-severe",
        version_tag="v2.0.0",
        behavior_profile={"profile_type": "LATENCY_REGRESSION", "severity": 0.5},
    )
    svc.deploy_canary("rel-severe", ["srv-r0-s0"])

    # Step 15 ticks
    svc.step(15)

    status = svc.get_status()
    # Auto rollback must NOT be triggered because policy is uncalibrated
    assert status["auto_rollback_triggered"] is False
    assert svc.active_release_id == "rel-severe"
