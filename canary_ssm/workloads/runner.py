"""Workload Runner.

Executes reviewed sample services inside isolated worker harnesses, orchestrating
discrete traffic intervals, collecting physical telemetry, and classifying results
into distinct harness failures and application faults.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from canary_ssm.telemetry.records import TelemetryRecord
from .adapter import PhysicalTelemetryAdapter
from .harness import IsolatedWorkerHarness
from .models import (
    ApplicationFaultType,
    HarnessFailureType,
    WorkerExecutionResult,
    WorkerLimits,
)
from .samples import CLEAN_SERVICE_SCRIPT, LEAKING_SERVICE_SCRIPT


class WorkloadRunner:
    """Orchestrates single-host or multi-host real workload execution."""

    def __init__(self, limits: WorkerLimits | None = None) -> None:
        self.limits = limits or WorkerLimits()
        self.adapter = PhysicalTelemetryAdapter()

    def run_workload(
        self,
        script_path: Path | str,
        ticks: int = 5,
        requests_per_tick: int = 5,
        params_per_tick: dict[str, Any] | None = None,
        endpoint: str = "/work",
        server_id: str = "srv-0",
        service_name: str = "sample_service",
        metadata: dict[str, Any] | None = None,
    ) -> WorkerExecutionResult:
        """Execute a single worker across discrete ticks and collect physical telemetry.

        Parameters
        ----------
        script_path:
            Path to reviewed service script.
        ticks:
            Number of discrete aggregation intervals.
        requests_per_tick:
            Traffic intensity per tick.
        params_per_tick:
            Query parameters passed to the service endpoint.
        endpoint:
            Target HTTP endpoint.
        server_id:
            Host identifier.
        service_name:
            Descriptive service name.
        metadata:
            Optional metadata fields (rack_id, class_id, version, exposure).

        Returns
        -------
        WorkerExecutionResult:
            Structured execution results, physical telemetry records, and failure classification.
        """
        records: list[TelemetryRecord] = []
        total_requests = 0
        total_errors = 0
        all_latencies: list[float] = []
        app_fault: ApplicationFaultType | None = None
        t0 = time.perf_counter()

        with IsolatedWorkerHarness(
            script_path=script_path,
            limits=self.limits,
            server_id=server_id,
            service_name=service_name,
        ) as harness:
            for tick in range(ticks):
                if not harness.is_alive() or harness.harness_failure is not None:
                    break

                try:
                    rec, logs = self.adapter.dispatch_tick(
                        harness=harness,
                        tick=tick,
                        request_count=requests_per_tick,
                        endpoint=endpoint,
                        params=params_per_tick,
                        metadata=metadata,
                    )
                    records.append(rec)
                    total_requests += rec.request_count
                    total_errors += rec.error_count
                    all_latencies.append(rec.latency_ms)
                except Exception as exc:
                    # In case of communication failure or worker death
                    total_errors += requests_per_tick
                    break

            peak_mem = harness.peak_memory_mb
            harness_fail = harness.harness_failure
            exit_code = harness.exit_code
            err_details = harness.error_details

        wall_time = time.perf_counter() - t0
        successful = total_requests - total_errors
        mean_lat = float(sum(all_latencies) / len(all_latencies)) if all_latencies else 0.0

        # Application fault classification (only when harness did not fail or crash)
        if harness_fail is None:
            if total_errors > 0:
                app_fault = ApplicationFaultType.APPLICATION_HTTP_ERROR
            elif len(records) >= 3 and (records[-1].memory_mb - records[0].memory_mb) > 5.0:
                # Noticeable sustained physical memory accumulation
                app_fault = ApplicationFaultType.APPLICATION_MEMORY_LEAK
            else:
                app_fault = ApplicationFaultType.APPLICATION_HEALTHY

        return WorkerExecutionResult(
            server_id=server_id,
            service_name=service_name,
            port=harness.port or 0,
            exit_code=exit_code,
            harness_failure=harness_fail,
            application_fault=app_fault,
            peak_memory_mb=peak_mem,
            wall_time_seconds=wall_time,
            total_requests=total_requests,
            successful_requests=successful,
            error_requests=total_errors,
            mean_latency_ms=mean_lat,
            telemetry_records=records,
            error_details=err_details,
        )
