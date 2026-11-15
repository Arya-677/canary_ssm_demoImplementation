"""Acceptance Scenarios for Virtual Data Center & Hierarchical Detection.

Implements the 4 benchmark demo scenarios:
1. Scenario 1 (Clean Baseline): 180 pre-ticks + 120 exposure ticks with clean release.
2. Scenario 2 (Canary Memory Leak): Memory leak on 2 canaries (+35MB/min) causing resource pressure.
3. Scenario 3 (Rack Network Slowdown): Shared rack latency affecting both controls and canaries in rack-0.
4. Scenario 4 (Compound Faults & Identifiability Guard):
   - 4A: Combined rack slowdown and canary memory leak.
   - 4B: Pure-canary rack confounding (0 controls) -> UNCERTAIN / INSUFFICIENT DATA.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from canary_ssm.api.service import SimulatorService
from canary_ssm.deployments import BehaviorProfile, BehaviorProfileType
from canary_ssm.faults.models import FaultDefinition, FaultScope, FaultType


@dataclass
class ScenarioResult:
    """Outcome and recorded timeline of an acceptance scenario run."""
    scenario_name: str
    pre_exposure_ticks: int
    exposure_ticks: int
    total_ticks: int
    final_infrastructure_advisory: str
    final_canary_release_advisory: str
    final_release_score: float
    advisory_reason: str
    timeline_summary: list[dict[str, Any]]
    is_correct_classification: bool
    evaluation_details: dict[str, Any]


def run_clean_baseline_scenario(seed: int = 42) -> ScenarioResult:
    """Scenario 1: Clean Baseline Rollout.

    - 180 pre-exposure ticks.
    - Deploy clean release to 4 canaries (1 per rack).
    - 120 exposure ticks.
    - Expected: Infrastructure NORMAL, Canary RUNNING, Score < threshold.
    """
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=seed, ssm_connected=True)
    svc.reset(seed=seed)

    # Pre-period: 180 ticks
    svc.step(180)

    # Deploy Clean Release
    svc.create_release(
        release_id="rel-scen-clean",
        version_tag="v1.1.0-clean",
        behavior_profile={"profile_type": "CLEAN"},
    )
    alloc = svc.get_default_allocation()["recommended_canaries"]
    svc.deploy_canary("rel-scen-clean", canary_server_ids=alloc)

    # Post-period: 120 ticks
    svc.step(120)

    adv = svc.evaluate_advisories()
    is_correct = (
        adv["infrastructure_advisory"] == "NORMAL"
        and adv["canary_release_advisory"] == "RUNNING"
    )

    return ScenarioResult(
        scenario_name="Scenario 1: Clean Baseline Rollout",
        pre_exposure_ticks=180,
        exposure_ticks=120,
        total_ticks=svc.world.clock.tick,
        final_infrastructure_advisory=adv["infrastructure_advisory"],
        final_canary_release_advisory=adv["canary_release_advisory"],
        final_release_score=adv["release_score"],
        advisory_reason=adv["advisory_reason"],
        timeline_summary=svc.get_metrics_timeline(limit=120),
        is_correct_classification=is_correct,
        evaluation_details={
            "channel_evidence": adv.get("channel_evidence", {}),
            "canary_count": len(svc.active_canary_ids),
        },
    )


def run_memory_leak_scenario(seed: int = 42) -> ScenarioResult:
    """Scenario 2: Canary Memory Leak on 2 canaries.

    - 180 pre-exposure ticks.
    - Deploy release with configured memory leak (+35 MB/min) on 2 canaries (Class 0 canaries).
    - 120 exposure ticks.
    - Expected: Infrastructure NORMAL, Canary PAUSE RECOMMENDED.
    """
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=seed, ssm_connected=True)
    svc.reset(seed=seed)

    svc.step(180)

    # Deploy leak release restricted to Class 0 (affects 2 of the 4 canaries)
    svc.create_release(
        release_id="rel-scen-leak",
        version_tag="v1.2.0-leak",
        behavior_profile={
            "profile_type": "MEMORY_LEAK",
            "severity": 35.0,  # 35 MB / min
            "duration": 120,
            "susceptible_class_id": 0,
        },
    )
    alloc = svc.get_default_allocation()["recommended_canaries"]
    svc.deploy_canary("rel-scen-leak", canary_server_ids=alloc)

    svc.step(120)

    adv = svc.evaluate_advisories()
    is_correct = (
        adv["infrastructure_advisory"] == "NORMAL"
        and adv["canary_release_advisory"] == "PAUSE RECOMMENDED"
    )

    return ScenarioResult(
        scenario_name="Scenario 2: Canary Memory Leak (2 Canaries)",
        pre_exposure_ticks=180,
        exposure_ticks=120,
        total_ticks=svc.world.clock.tick,
        final_infrastructure_advisory=adv["infrastructure_advisory"],
        final_canary_release_advisory=adv["canary_release_advisory"],
        final_release_score=adv["release_score"],
        advisory_reason=adv["advisory_reason"],
        timeline_summary=svc.get_metrics_timeline(limit=120),
        is_correct_classification=is_correct,
        evaluation_details={
            "channel_evidence": adv.get("channel_evidence", {}),
            "memory_growth_detected": adv.get("channel_evidence", {}).get("memory_growth_delta_mb", 0) > 300.0,
        },
    )


def run_rack_slowdown_scenario(seed: int = 42) -> ScenarioResult:
    """Scenario 3: Shared Rack Network Slowdown.

    - 180 pre-exposure ticks.
    - Clean release running on 4 canaries.
    - Injected rack network latency on rack-0 (+0.30 log latency) affecting ALL 6 servers in rack-0.
    - Expected:
        * Infrastructure Advisory: RACK_DEGRADED: rack-0.
        * Canary Release Advisory: RUNNING (Controls absorb rack nuisance; no release-specific harm).
    """
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=seed, ssm_connected=True)
    svc.reset(seed=seed)

    svc.step(180)

    svc.create_release(
        release_id="rel-scen-rack-clean",
        version_tag="v1.1.0-clean",
        behavior_profile={"profile_type": "CLEAN"},
    )
    alloc = svc.get_default_allocation()["recommended_canaries"]
    svc.deploy_canary("rel-scen-rack-clean", canary_server_ids=alloc)

    # Inject rack network slowdown on rack-0 at onset tick with duration covering exposure
    svc.inject_fault(
        fault_type="RACK_NETWORK_LATENCY",
        scope="RACK",
        target_id="rack-0",
        severity=0.30,  # +35% latency
        duration=180,
    )

    svc.step(120)

    adv = svc.evaluate_advisories()
    is_correct = (
        "rack-0" in adv["infrastructure_advisory"]
        and adv["canary_release_advisory"] == "RUNNING"
    )

    return ScenarioResult(
        scenario_name="Scenario 3: Rack Network Slowdown (Shared Infrastructure Fault)",
        pre_exposure_ticks=180,
        exposure_ticks=120,
        total_ticks=svc.world.clock.tick,
        final_infrastructure_advisory=adv["infrastructure_advisory"],
        final_canary_release_advisory=adv["canary_release_advisory"],
        final_release_score=adv["release_score"],
        advisory_reason=adv["advisory_reason"],
        timeline_summary=svc.get_metrics_timeline(limit=120),
        is_correct_classification=is_correct,
        evaluation_details={
            "rack_nuisance_detected": "rack-0" in adv["infrastructure_advisory"],
            "canary_isolated_from_rack_fault": adv["canary_release_advisory"] == "RUNNING",
        },
    )


def run_compound_faults_scenario(seed: int = 42) -> ScenarioResult:
    """Scenario 4A: Compound Faults (Rack Slowdown + Canary Memory Leak).

    - 180 pre-exposure ticks.
    - Both rack network latency on rack-0 AND canary memory leak on canaries.
    - Expected:
        * Infrastructure Advisory: RACK_DEGRADED: rack-0.
        * Canary Release Advisory: PAUSE RECOMMENDED.
    """
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=seed, ssm_connected=True)
    svc.reset(seed=seed)

    svc.step(180)

    svc.create_release(
        release_id="rel-scen-compound",
        version_tag="v1.2.0-leak",
        behavior_profile={"profile_type": "MEMORY_LEAK", "severity": 35.0, "duration": 180},
    )
    alloc = svc.get_default_allocation()["recommended_canaries"]
    svc.deploy_canary("rel-scen-compound", canary_server_ids=alloc)

    # Inject rack network latency on rack-0
    svc.inject_fault(
        fault_type="RACK_NETWORK_LATENCY",
        scope="RACK",
        target_id="rack-0",
        severity=0.30,
        duration=180,
    )

    svc.step(120)

    adv = svc.evaluate_advisories()
    is_correct = (
        "rack-0" in adv["infrastructure_advisory"]
        and adv["canary_release_advisory"] == "PAUSE RECOMMENDED"
    )

    return ScenarioResult(
        scenario_name="Scenario 4A: Compound Faults (Rack Slowdown + Memory Leak)",
        pre_exposure_ticks=180,
        exposure_ticks=120,
        total_ticks=svc.world.clock.tick,
        final_infrastructure_advisory=adv["infrastructure_advisory"],
        final_canary_release_advisory=adv["canary_release_advisory"],
        final_release_score=adv["release_score"],
        advisory_reason=adv["advisory_reason"],
        timeline_summary=svc.get_metrics_timeline(limit=120),
        is_correct_classification=is_correct,
        evaluation_details={
            "rack_degraded": "rack-0" in adv["infrastructure_advisory"],
            "canary_pause_recommended": adv["canary_release_advisory"] == "PAUSE RECOMMENDED",
        },
    )


def run_confounded_pure_rack_scenario(seed: int = 42) -> ScenarioResult:
    """Scenario 4B: Confounded Allocation (Pure-Canary Rack with 0 Controls).

    - Entire rack-0 allocated as canaries (6 canaries, 0 controls in rack-0).
    - Allocation validator flags CONFUSED_RACK_CONFOUNDING.
    - Expected:
        * Canary Release Advisory: INSUFFICIENT DATA / CONFLICT.
        * Demonstrates identifiability guard when controls cannot separate cause.
    """
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=seed, ssm_connected=True)
    svc.reset(seed=seed)

    svc.step(180)

    svc.create_release(
        release_id="rel-scen-confounded",
        version_tag="v1.2.0-confounded",
        behavior_profile={"profile_type": "CLEAN"},
    )
    # Pure canary rack: all 6 servers in rack-0
    pure_rack_canaries = [f"srv-r0-s{s}" for s in range(6)]

    # Validate allocation
    val = svc.validate_allocation(pure_rack_canaries)
    assert not val["is_valid"], "Pure-canary rack MUST be rejected by allocation validator"

    # Forcing deployment in service to evaluate detector behavior
    svc.active_release_id = "rel-scen-confounded"
    svc.active_canary_ids = list(pure_rack_canaries)
    for sid in pure_rack_canaries:
        svc.world.set_server_version(sid, "v1.2.0-confounded")

    # Inject rack fault on rack-0
    svc.inject_fault(
        fault_type="RACK_NETWORK_LATENCY",
        scope="RACK",
        target_id="rack-0",
        severity=0.30,
        duration=120,
    )

    svc.step(30)

    adv = svc.evaluate_advisories()
    is_correct = (adv["canary_release_advisory"] == "INSUFFICIENT DATA / CONFLICT")

    return ScenarioResult(
        scenario_name="Scenario 4B: Confounded Allocation (Pure-Canary Rack, 0 Controls)",
        pre_exposure_ticks=180,
        exposure_ticks=30,
        total_ticks=svc.world.clock.tick,
        final_infrastructure_advisory=adv["infrastructure_advisory"],
        final_canary_release_advisory=adv["canary_release_advisory"],
        final_release_score=adv["release_score"],
        advisory_reason=adv["advisory_reason"],
        timeline_summary=svc.get_metrics_timeline(limit=30),
        is_correct_classification=is_correct,
        evaluation_details={
            "allocation_rejected": not val["is_valid"],
            "confounding_issue": val["issues"][0] if val["issues"] else "",
        },
    )
