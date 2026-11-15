"""Declarative data models for versioned evaluation scenarios.

Each scenario specifies topology, seed, warmup, deployment, workload, and injection
completely independently of detector parameters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class TopologyConfig:
    """Datacenter physical topology configuration."""
    n_racks: int = 4
    servers_per_rack: int = 6
    n_classes: int = 2
    canary_ids: list[str] = field(default_factory=lambda: [
        "srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"
    ])

    @property
    def total_servers(self) -> int:
        return self.n_racks * self.servers_per_rack


@dataclass(frozen=True)
class DeploymentConfig:
    """Software release deployment configuration."""
    version: str = "v1.2.0"
    release_id: str = "rel-v1.2.0"
    profile_type: str = "CLEAN"             # CLEAN | MEMORY_LEAK | CPU_REGRESSION | ERROR_REGRESSION | LATENCY_REGRESSION
    deploy_tick: int = 30
    canary_ids: list[str] = field(default_factory=lambda: [
        "srv-r0-s0", "srv-r1-s0", "srv-r2-s0", "srv-r3-s0"
    ])
    affected_canary_ids: list[str] = field(default_factory=list)
    description: str = "Standard release artifact"


@dataclass(frozen=True)
class WorkloadConfig:
    """Fleet-wide workload and memory dynamics configuration."""
    base_request_rate: float = 100.0
    elasticity_mean: float = 0.50
    has_gc_cycles: bool = False
    gc_period_ticks: int = 15
    gc_amplitude_mb: float = 300.0
    warmup_ticks: int = 15
    warmup_amplitude_mb: float = 400.0


@dataclass(frozen=True)
class FaultInjectionConfig:
    """Injected infrastructure or release fault configuration."""
    fault_type: str | None = None          # None | RACK_NETWORK_LATENCY | FLEET_DEMAND_SPIKE | CPU_SATURATION | PROCESS_MEMORY_LEAK | ERROR_REGRESSION | SERVER_OUTAGE
    target_scope: str | None = None        # rack-0 | fleet | srv-r0-s0 | etc.
    start_tick: int = 30
    stop_tick: int | None = None
    severity: float = 0.0
    missingness_rate: float = 0.0          # Drop rate for observations (0.0 to 1.0)
    drop_same_rack_controls: bool = False  # Suppress baseline controls in rack-0


@dataclass(frozen=True)
class ScenarioDefinition:
    """Self-contained declarative specification of an operational scenario.

    Guarantees:
    - Topology, seed, warmup, deployment, workload, and injection are specified
      strictly independently of detector parameters and decision policies.
    """
    name: str
    description: str
    seed: int
    warmup_ticks: int = 30
    horizon_ticks: int = 75
    topology: TopologyConfig = field(default_factory=TopologyConfig)
    deployment: DeploymentConfig = field(default_factory=DeploymentConfig)
    workload: WorkloadConfig = field(default_factory=WorkloadConfig)
    injection: FaultInjectionConfig = field(default_factory=FaultInjectionConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "seed": self.seed,
            "warmup_ticks": self.warmup_ticks,
            "horizon_ticks": self.horizon_ticks,
            "topology": asdict(self.topology),
            "deployment": asdict(self.deployment),
            "workload": asdict(self.workload),
            "injection": asdict(self.injection),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioDefinition:
        return cls(
            name=data["name"],
            description=data["description"],
            seed=int(data["seed"]),
            warmup_ticks=int(data.get("warmup_ticks", 30)),
            horizon_ticks=int(data.get("horizon_ticks", 75)),
            topology=TopologyConfig(**data.get("topology", {})),
            deployment=DeploymentConfig(**data.get("deployment", {})),
            workload=WorkloadConfig(**data.get("workload", {})),
            injection=FaultInjectionConfig(**data.get("injection", {})),
        )
