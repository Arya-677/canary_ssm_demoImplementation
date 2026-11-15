"""Catalog of versioned evaluation scenarios.

Provides the 8 canonical benchmark and demonstration scenarios:
1. clean_release: Normal clean deployment on balanced canaries.
2. release_leak_two_canaries: Process memory leak on exactly two canaries.
3. rack_slowdown: Common rack network latency affecting all servers in rack-0.
4. fleet_demand_spike: Macro fleet-wide demand surge affecting all servers.
5. cpu_regression: Elevated CPU saturation on canary instances.
6. healthy_gc: Normal load-dependent garbage collection sawtooth cycles across all servers.
7. combined_rack_fault_release_leak: Rack network fault plus simultaneous canary memory leak.
8. missing_controls: Missing observation records on baseline controls (tests identifiability abstention).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .models import (
    DeploymentConfig,
    FaultInjectionConfig,
    ScenarioDefinition,
    TopologyConfig,
    WorkloadConfig,
)


def get_default_topology() -> TopologyConfig:
    return TopologyConfig(
        n_racks=4,
        servers_per_rack=6,
        n_classes=2,
        canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
    )


def create_scenario_catalog() -> dict[str, ScenarioDefinition]:
    """Construct the registry of 8 canonical versioned scenarios."""
    scenarios: dict[str, ScenarioDefinition] = {}

    # 1. Clean Release
    scenarios["clean_release"] = ScenarioDefinition(
        name="clean_release",
        description="Clean baseline rollout on 4 balanced canaries with zero regressions.",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-clean",
            release_id="rel-clean-v1",
            profile_type="CLEAN",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=[],
            description="Verified bug-free canary release",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(fault_type=None),
    )

    # 2. Release Leak on Two Canaries
    scenarios["release_leak_two_canaries"] = ScenarioDefinition(
        name="release_leak_two_canaries",
        description="Process memory leak regression affecting exactly two canaries (srv-r0-s0, srv-r1-s0).",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-leak",
            release_id="rel-leak-v1",
            profile_type="MEMORY_LEAK",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=["srv-r0-s0", "srv-r1-s0"],
            description="Release with uncollected allocations on class-0 instances",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(
            fault_type="PROCESS_MEMORY_LEAK",
            target_scope="srv-r0-s0,srv-r1-s0",
            start_tick=30,
            stop_tick=None,
            severity=35.0,  # +35 MB/min leak rate
        ),
    )

    # 3. Rack Slowdown
    scenarios["rack_slowdown"] = ScenarioDefinition(
        name="rack_slowdown",
        description="Infrastructure network latency fault affecting all 6 servers in rack-0.",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-clean",
            release_id="rel-clean-v2",
            profile_type="CLEAN",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=[],
            description="Clean release deployed amidst rack infrastructure degradation",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(
            fault_type="RACK_NETWORK_LATENCY",
            target_scope="rack-0",
            start_tick=30,
            stop_tick=75,
            severity=0.30,  # +0.30 log latency shift
        ),
    )

    # 4. Fleet Demand Spike
    scenarios["fleet_demand_spike"] = ScenarioDefinition(
        name="fleet_demand_spike",
        description="Fleet-wide request rate surge (+28%) affecting baseline and canary instances equally.",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-clean",
            release_id="rel-clean-v3",
            profile_type="CLEAN",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=[],
            description="Clean release during macro traffic surge",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(
            fault_type="FLEET_DEMAND_SPIKE",
            target_scope="fleet",
            start_tick=30,
            stop_tick=75,
            severity=0.25,  # +0.25 log demand shift
        ),
    )

    # 5. CPU Regression
    scenarios["cpu_regression"] = ScenarioDefinition(
        name="cpu_regression",
        description="CPU saturation regression on canary instances causing resource exhaustion.",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-cpureg",
            release_id="rel-cpureg-v1",
            profile_type="CPU_REGRESSION",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            description="Release with busy-wait spinning loop",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(
            fault_type="CPU_SATURATION",
            target_scope="canaries",
            start_tick=30,
            stop_tick=None,
            severity=0.40,  # +0.40 CPU fraction
        ),
    )

    # 6. Healthy GC Dynamics
    scenarios["healthy_gc"] = ScenarioDefinition(
        name="healthy_gc",
        description="Normal garbage collection sawtooth sweeps (+300 MB every 15 ticks) across all servers.",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-clean",
            release_id="rel-clean-v4",
            profile_type="CLEAN",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=[],
            description="Clean release with healthy cyclic JVM allocation sweeps",
        ),
        workload=WorkloadConfig(
            base_request_rate=100.0,
            elasticity_mean=0.50,
            has_gc_cycles=True,
            gc_period_ticks=15,
            gc_amplitude_mb=300.0,
        ),
        injection=FaultInjectionConfig(fault_type=None),
    )

    # 7. Combined Rack Fault Plus Release Leak
    scenarios["combined_rack_fault_release_leak"] = ScenarioDefinition(
        name="combined_rack_fault_release_leak",
        description="Simultaneous infrastructure rack latency on rack-0 AND release memory leak on canaries.",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-compound",
            release_id="rel-compound-v1",
            profile_type="MEMORY_LEAK",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=["srv-r0-s0", "srv-r1-s0"],
            description="Canary leak running concurrently with network degradation",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(
            fault_type="RACK_NETWORK_LATENCY",
            target_scope="rack-0",
            start_tick=30,
            stop_tick=75,
            severity=0.30,  # Also pairs with leak in deployment profile
        ),
    )

    # 8. Missing Controls
    scenarios["missing_controls"] = ScenarioDefinition(
        name="missing_controls",
        description="Missing observation records on same-rack baseline controls (evaluates identifiability abstention).",
        seed=10,
        warmup_ticks=30,
        horizon_ticks=75,
        topology=get_default_topology(),
        deployment=DeploymentConfig(
            version="v1.2.0-clean",
            release_id="rel-clean-v5",
            profile_type="CLEAN",
            deploy_tick=30,
            canary_ids=["srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"],
            affected_canary_ids=[],
            description="Clean release with impaired control coverage",
        ),
        workload=WorkloadConfig(base_request_rate=100.0, elasticity_mean=0.50),
        injection=FaultInjectionConfig(
            fault_type=None,
            missingness_rate=0.25,
            drop_same_rack_controls=True,
        ),
    )

    return scenarios


def save_declarative_configs(out_dir: str | Path = "configs/scenarios") -> list[Path]:
    """Persist all 8 scenarios as individual JSON/YAML manifests."""
    catalog = create_scenario_catalog()
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for name, scen in catalog.items():
        file_path = out_path / f"{name}.json"
        file_path.write_text(json.dumps(scen.to_dict(), indent=2) + "\n", encoding="utf-8")
        saved_paths.append(file_path)

    return saved_paths
