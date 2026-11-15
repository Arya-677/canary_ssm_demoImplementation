"""Workload Execution Sandbox & Physical Telemetry Adapter.

Provides disposable, isolated worker execution with hard memory/CPU limits,
process group containment, ephemeral filesystems, reliable lifecycle cleanup,
physical telemetry observation, and strict anti-leakage isolation from truth.
"""

from .models import (
    WorkerLimits,
    HarnessFailureType,
    ApplicationFaultType,
    WorkerExecutionResult,
)
from .harness import IsolatedWorkerHarness
from .adapter import PhysicalTelemetryAdapter
from .runner import WorkloadRunner
from .comparison import (
    compare_physical_vs_simulated,
    recalibrate_empirical_threshold,
)

__all__ = [
    "WorkerLimits",
    "HarnessFailureType",
    "ApplicationFaultType",
    "WorkerExecutionResult",
    "IsolatedWorkerHarness",
    "PhysicalTelemetryAdapter",
    "WorkloadRunner",
    "compare_physical_vs_simulated",
    "recalibrate_empirical_threshold",
]
