"""Data models for isolated workload execution, resource limits, and failure taxonomy.

Strict separation of:
- Harness Failures: Environment and sandbox boundary violations (OOM kills, timeouts, crashes).
- Application Faults: Service-level logic anomalies (memory leaks, HTTP errors, SLA breaches).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from canary_ssm.telemetry.records import TelemetryRecord


@dataclass(frozen=True)
class WorkerLimits:
    """Resource and execution boundaries enforced on disposable isolated workers."""
    max_memory_mb: float = 128.0
    timeout_seconds: float = 30.0
    startup_timeout_seconds: float = 5.0
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        if self.max_memory_mb <= 0:
            raise ValueError(f"max_memory_mb must be positive, got {self.max_memory_mb}")
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {self.timeout_seconds}")
        if self.startup_timeout_seconds <= 0:
            raise ValueError(f"startup_timeout_seconds must be positive, got {self.startup_timeout_seconds}")
        if self.poll_interval_seconds <= 0:
            raise ValueError(f"poll_interval_seconds must be positive, got {self.poll_interval_seconds}")


class HarnessFailureType(str, Enum):
    """Failures occurring at the harness or isolation boundary level."""
    HARNESS_OOM_KILLED = "HARNESS_OOM_KILLED"
    HARNESS_TIMEOUT = "HARNESS_TIMEOUT"
    HARNESS_STARTUP_FAILURE = "HARNESS_STARTUP_FAILURE"
    HARNESS_CRASH = "HARNESS_CRASH"


class ApplicationFaultType(str, Enum):
    """Anomalies or behaviors originating from application service code."""
    APPLICATION_HEALTHY = "APPLICATION_HEALTHY"
    APPLICATION_MEMORY_LEAK = "APPLICATION_MEMORY_LEAK"
    APPLICATION_HTTP_ERROR = "APPLICATION_HTTP_ERROR"
    APPLICATION_LATENCY_SPIKE = "APPLICATION_LATENCY_SPIKE"
    APPLICATION_EXCEPTION = "APPLICATION_EXCEPTION"


@dataclass
class WorkerExecutionResult:
    """Structured outcome of executing an isolated worker service."""
    server_id: str
    service_name: str
    port: int
    exit_code: int | None
    harness_failure: HarnessFailureType | None
    application_fault: ApplicationFaultType | None
    peak_memory_mb: float
    wall_time_seconds: float
    total_requests: int
    successful_requests: int
    error_requests: int
    mean_latency_ms: float
    telemetry_records: list[TelemetryRecord] = field(default_factory=list)
    error_details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "service_name": self.service_name,
            "port": self.port,
            "exit_code": self.exit_code,
            "harness_failure": self.harness_failure.value if self.harness_failure else None,
            "application_fault": self.application_fault.value if self.application_fault else None,
            "peak_memory_mb": round(float(self.peak_memory_mb), 2),
            "wall_time_seconds": round(float(self.wall_time_seconds), 3),
            "total_requests": int(self.total_requests),
            "successful_requests": int(self.successful_requests),
            "error_requests": int(self.error_requests),
            "mean_latency_ms": round(float(self.mean_latency_ms), 4),
            "telemetry_count": len(self.telemetry_records),
            "error_details": self.error_details,
        }
