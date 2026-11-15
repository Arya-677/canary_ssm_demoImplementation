"""Typed TelemetryRecord data contract for the Virtual Data Center.

Strict Anti-Leakage Firewall:
TelemetryRecord contains only observable telemetry and deployment metadata.
It must NEVER contain fault_type, injected_severity, or any ground-truth indicators.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class TelemetryRecord:
    """Standardized multi-metric telemetry observation for a single host at one discrete tick.

    Latency Statistic Declaration:
        The `latency_ms` field represents the estimated geometric mean response time in
        milliseconds over the discrete 1-minute aggregation window, derived from
        exp(mean log-latency). It reflects the central latency response of requests
        served during the window. It is NOT an empirical request-level p95, p99, or
        maximum tail latency measurement.

    Units:
        - latency_ms: milliseconds (ms), strictly > 0.
        - memory_mb: Megabytes (MB), process resident set size, bounded by server capacity.
        - cpu_fraction: dimensionless fraction in [0.0, 1.0], representing CPU utilization.
        - request_count: discrete integer count of requests served during the 1-minute window.
        - error_count: discrete integer count of failed/error requests, strictly in [0, request_count].
    """
    run_id: str
    tick: int
    event_time: int
    arrival_time: int
    server_id: str
    rack_id: str
    class_id: int
    version: str
    exposure: bool
    request_count: int
    latency_ms: float
    memory_mb: float
    cpu_fraction: float
    error_count: int
    observed: bool = True
    source: str = "SIMULATED"

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id cannot be empty")
        if self.tick < 0:
            raise ValueError(f"tick cannot be negative, got {self.tick}")
        if self.event_time < 0:
            raise ValueError(f"event_time cannot be negative, got {self.event_time}")
        if self.arrival_time < self.event_time:
            raise ValueError(
                f"arrival_time ({self.arrival_time}) cannot be earlier than event_time ({self.event_time})"
            )
        if not self.server_id:
            raise ValueError("server_id cannot be empty")
        if not self.rack_id:
            raise ValueError("rack_id cannot be empty")
        if self.class_id < 0:
            raise ValueError(f"class_id must be non-negative, got {self.class_id}")
        if self.request_count < 0:
            raise ValueError(f"request_count cannot be negative, got {self.request_count}")
        if self.latency_ms <= 0.0:
            raise ValueError(f"latency_ms must be strictly positive, got {self.latency_ms}")
        if self.memory_mb < 0.0:
            raise ValueError(f"memory_mb cannot be negative, got {self.memory_mb}")
        if not (0.0 <= self.cpu_fraction <= 1.0):
            raise ValueError(f"cpu_fraction must be in [0.0, 1.0], got {self.cpu_fraction}")
        if not (0 <= self.error_count <= self.request_count):
            raise ValueError(
                f"error_count ({self.error_count}) must be between 0 and request_count ({self.request_count})"
            )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "run_id": self.run_id,
            "tick": self.tick,
            "event_time": self.event_time,
            "arrival_time": self.arrival_time,
            "server_id": self.server_id,
            "rack_id": self.rack_id,
            "class_id": self.class_id,
            "version": self.version,
            "exposure": self.exposure,
            "request_count": self.request_count,
            "latency_ms": round(float(self.latency_ms), 4),
            "memory_mb": round(float(self.memory_mb), 2),
            "cpu_fraction": round(float(self.cpu_fraction), 4),
            "error_count": int(self.error_count),
            "observed": bool(self.observed),
        }
        if self.source != "SIMULATED":
            d["source"] = str(self.source)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TelemetryRecord":
        return cls(
            run_id=str(d["run_id"]),
            tick=int(d["tick"]),
            event_time=int(d["event_time"]),
            arrival_time=int(d["arrival_time"]),
            server_id=str(d["server_id"]),
            rack_id=str(d["rack_id"]),
            class_id=int(d["class_id"]),
            version=str(d["version"]),
            exposure=bool(d["exposure"]),
            request_count=int(d["request_count"]),
            latency_ms=float(d["latency_ms"]),
            memory_mb=float(d["memory_mb"]),
            cpu_fraction=float(d["cpu_fraction"]),
            error_count=int(d["error_count"]),
            observed=bool(d.get("observed", True)),
            source=str(d.get("source", "SIMULATED")),
        )
