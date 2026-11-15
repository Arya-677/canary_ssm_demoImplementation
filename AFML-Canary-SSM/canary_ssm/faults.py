"""Typed platform fault contracts; truth records belong to developer/evaluator paths."""
from dataclasses import dataclass, replace
from enum import Enum
import math


class FaultKind(str, Enum):
    CPU = "cpu_throttle"
    MEMORY = "memory_pressure"
    CRASH = "service_crash"
    NETWORK = "network_degradation"
    DEMAND = "demand_surge"


class FaultScope(str, Enum):
    HOST = "host"
    RACK = "rack"
    WORLD = "world"


class Recovery(str, Enum):
    RESTORE = "restore"
    RESTART = "restart"


@dataclass(frozen=True)
class FaultEvent:
    fault_id: str
    kind: FaultKind
    scope: FaultScope
    target: str
    start_tick: int
    duration: int
    severity: float
    seed: int
    recovery: Recovery = Recovery.RESTORE
    host_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name, enum in (("kind", FaultKind), ("scope", FaultScope), ("recovery", Recovery)):
            try:
                object.__setattr__(self, name, enum(getattr(self, name)))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid fault {name}") from exc
        for name in ("fault_id", "target"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 128:
                raise ValueError(f"{name} must be a nonempty identifier of at most 128 characters")
        if type(self.start_tick) is not int or self.start_tick < 1:
            raise ValueError("start_tick must be a positive integer")
        if type(self.duration) is not int or not 1 <= self.duration <= 1000:
            raise ValueError("duration must be integer ticks in [1, 1000]")
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2^32)")
        if type(self.severity) not in (int, float) or not math.isfinite(self.severity) or not 0.1 <= self.severity <= 0.95:
            raise ValueError("severity must be finite in [0.1, 0.95]")
        if self.kind == FaultKind.DEMAND and (self.scope != FaultScope.WORLD or self.target != "world"):
            raise ValueError("Demand surge requires world scope/target")
        if self.kind == FaultKind.NETWORK and self.scope != FaultScope.RACK:
            raise ValueError("Network degradation requires rack scope")
        if self.kind in (FaultKind.CPU, FaultKind.MEMORY, FaultKind.CRASH) and self.scope not in (FaultScope.HOST, FaultScope.RACK):
            raise ValueError("CPU/memory/crash faults require host or rack scope")
        expected = Recovery.RESTART if self.kind == FaultKind.CRASH else Recovery.RESTORE
        if self.recovery != expected:
            raise ValueError(f"{self.kind.value} requires recovery={expected.value}")
        object.__setattr__(self, "host_ids", tuple(self.host_ids))

    @property
    def end_tick(self):
        return self.start_tick + self.duration

    def active(self, tick):
        return self.start_tick <= tick < self.end_tick

    def resolve(self, world):
        if self.scope == FaultScope.HOST:
            hosts = [h.host_id for h in world.hosts if h.host_id == self.target]
        elif self.scope == FaultScope.RACK:
            hosts = [h.host_id for h in world.hosts if h.rack_id == self.target]
        else:
            hosts = [h.host_id for h in world.hosts]
        if not hosts:
            raise ValueError("Unknown or empty fault target")
        return replace(self, host_ids=tuple(sorted(hosts)))

    def to_dict(self):
        return {"fault_id": self.fault_id, "kind": self.kind.value, "scope": self.scope.value,
                "target": self.target, "start_tick": self.start_tick, "duration": self.duration,
                "end_tick": self.end_tick, "severity": self.severity, "seed": self.seed,
                "recovery": self.recovery.value, "host_ids": list(self.host_ids), "origin": "platform"}
