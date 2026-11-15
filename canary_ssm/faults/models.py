"""Explicit fault definitions and scopes for the Virtual Data Center.

Distinguishes:
- Infrastructure faults: Affect physical infrastructure (Server, Rack, Fleet) regardless of software version.
- Release faults: Affect only exposed instances running a specific candidate release and optional susceptible class.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FaultScope(str, Enum):
    """Scope of entity targeted by a fault."""
    FLEET = "fleet"
    RACK = "rack"
    SERVER = "server"


class FaultCategory(str, Enum):
    """Broad category separating infrastructure from release faults."""
    INFRASTRUCTURE = "infrastructure"
    RELEASE = "release"


class FaultType(str, Enum):
    """Specific typed fault modes."""
    # Infrastructure faults
    SERVER_OUTAGE = "server_outage"
    RACK_NETWORK_LATENCY = "rack_network_latency"
    FLEET_DEMAND_SPIKE = "fleet_demand_spike"
    CPU_SATURATION = "cpu_saturation"

    # Release faults
    PROCESS_MEMORY_LEAK = "process_memory_leak"
    ERROR_REGRESSION = "error_regression"
    RELEASE_LATENCY_REGRESSION = "release_latency_regression"

    @property
    def category(self) -> FaultCategory:
        if self in {
            FaultType.SERVER_OUTAGE,
            FaultType.RACK_NETWORK_LATENCY,
            FaultType.FLEET_DEMAND_SPIKE,
            FaultType.CPU_SATURATION,
        }:
            return FaultCategory.INFRASTRUCTURE
        return FaultCategory.RELEASE


@dataclass(frozen=True)
class FaultDefinition:
    """Explicit definition of an injected or scheduled fault.

    Attributes:
        fault_id: Unique stable identifier for this fault instance.
        fault_type: Typed fault mode.
        scope: Target scope (FLEET, RACK, or SERVER).
        target_id: Target identifier (e.g. "rack-1", "srv-r0-s1", or "fleet").
        onset_tick: Discrete simulation tick when the fault activates.
        duration: Active duration in discrete simulation ticks (> 0).
        severity: Numerical magnitude of the fault effect:
            - SERVER_OUTAGE: 1.0 (binary outage)
            - RACK_NETWORK_LATENCY: positive log-latency shift in log units (e.g. 0.20 for ~+22% latency)
            - FLEET_DEMAND_SPIKE: workload shift delta in log units (e.g. 0.35)
            - CPU_SATURATION: CPU fraction addition (e.g. 0.40)
            - PROCESS_MEMORY_LEAK: memory leak rate in MB/minute (e.g. 25.0 MB/min)
            - ERROR_REGRESSION: error rate increase delta in [0.0, 1.0] (e.g. 0.03 for +3% errors)
            - RELEASE_LATENCY_REGRESSION: release-specific log-latency regression (e.g. 0.05 for +5%)
        target_version: For release faults, target release version string (e.g. "v1.1.0-canary").
        susceptible_class_id: Optional compatibility group filter (e.g. class 0 only).
        restart_duration: Ticks a server remains offline during an OOM restart (default 2 ticks).
        parameters: Optional extra parameters.
    """
    fault_id: str
    fault_type: FaultType
    scope: FaultScope
    target_id: str
    onset_tick: int
    duration: int
    severity: float
    target_version: str | None = None
    susceptible_class_id: int | None = None
    restart_duration: int = 2
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fault_id:
            raise ValueError("fault_id cannot be empty")
        if self.onset_tick < 0:
            raise ValueError(f"onset_tick cannot be negative, got {self.onset_tick}")
        if self.duration <= 0:
            raise ValueError(f"duration must be strictly positive, got {self.duration}")
        if self.severity < 0.0 and self.fault_type != FaultType.FLEET_DEMAND_SPIKE:
            raise ValueError(f"severity cannot be negative for fault type {self.fault_type}, got {self.severity}")
        if self.fault_type.category == FaultCategory.RELEASE and not self.target_version:
            raise ValueError(f"Release fault {self.fault_type} requires target_version")

    @property
    def expiry_tick(self) -> int:
        return self.onset_tick + self.duration

    def is_active_at(self, tick: int) -> bool:
        return self.onset_tick <= tick < self.expiry_tick

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault_id": self.fault_id,
            "fault_type": self.fault_type.value,
            "category": self.fault_type.category.value,
            "scope": self.scope.value,
            "target_id": self.target_id,
            "onset_tick": self.onset_tick,
            "duration": self.duration,
            "expiry_tick": self.expiry_tick,
            "severity": float(self.severity),
            "target_version": self.target_version,
            "susceptible_class_id": self.susceptible_class_id,
            "restart_duration": self.restart_duration,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FaultDefinition":
        return cls(
            fault_id=str(d["fault_id"]),
            fault_type=FaultType(d["fault_type"]),
            scope=FaultScope(d["scope"]),
            target_id=str(d["target_id"]),
            onset_tick=int(d["onset_tick"]),
            duration=int(d["duration"]),
            severity=float(d["severity"]),
            target_version=str(d["target_version"]) if d.get("target_version") else None,
            susceptible_class_id=int(d["susceptible_class_id"]) if d.get("susceptible_class_id") is not None else None,
            restart_duration=int(d.get("restart_duration", 2)),
            parameters=dict(d.get("parameters", {})),
        )
