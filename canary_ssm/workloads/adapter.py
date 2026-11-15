"""Physical Telemetry Adapter.

Drives HTTP traffic against isolated worker processes and collects actual
operating system process metrics (RSS memory via psutil, measured round-trip
latency via high-resolution timers, CPU utilization, and HTTP error counts).

Emits standardized TelemetryRecord objects labeled with source='MEASURED'.
"""
from __future__ import annotations

import math
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import numpy as np

from canary_ssm.telemetry.records import TelemetryRecord
from .harness import IsolatedWorkerHarness


class PhysicalTelemetryAdapter:
    """Measures physical execution of an isolated worker and converts it into TelemetryRecords."""

    def __init__(self, default_timeout_per_req: float = 2.0) -> None:
        self.default_timeout_per_req = default_timeout_per_req

    def dispatch_tick(
        self,
        harness: IsolatedWorkerHarness,
        tick: int,
        request_count: int = 10,
        endpoint: str = "/work",
        params: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[TelemetryRecord, list[dict[str, Any]]]:
        """Dispatch a discrete batch of HTTP requests to the worker and collect physical metrics.

        Parameters
        ----------
        harness:
            The running IsolatedWorkerHarness instance.
        tick:
            Discrete simulation tick index.
        request_count:
            Number of requests to dispatch within this tick window.
        endpoint:
            HTTP path (e.g. '/work', '/error').
        params:
            Query string parameters passed to the endpoint.
        metadata:
            Optional server metadata (server_id, rack_id, class_id, version, exposure, run_id).

        Returns
        -------
        record:
            TelemetryRecord populated with physical measurements and source='MEASURED'.
        request_logs:
            List of individual request outcomes with latencies and status codes.
        """
        if not harness.is_alive() or harness.port is None:
            raise RuntimeError(f"Worker {harness.server_id} is not running or has no port assigned.")

        meta = metadata or {}
        run_id = str(meta.get("run_id", "measured-run-01"))
        server_id = str(meta.get("server_id", harness.server_id))
        rack_id = str(meta.get("rack_id", "rack-0"))
        class_id = int(meta.get("class_id", 0))
        version = str(meta.get("version", "v1.0.0"))
        exposure = bool(meta.get("exposure", False))

        latencies_ms: list[float] = []
        error_count = 0
        request_logs: list[dict[str, Any]] = []

        query_str = f"?{urlencode(params)}" if params else ""
        url = f"http://127.0.0.1:{harness.port}{endpoint}{query_str}"

        for req_idx in range(request_count):
            if not harness.is_alive():
                # Worker died during traffic burst
                error_count += (request_count - req_idx)
                break

            t0 = time.perf_counter()
            status_code = 0
            err_msg: str | None = None

            try:
                req = Request(url, method="GET")
                with urlopen(req, timeout=self.default_timeout_per_req) as resp:
                    status_code = resp.status
                    _ = resp.read()
            except HTTPError as http_err:
                status_code = http_err.code
                err_msg = f"HTTP {http_err.code}"
            except (URLError, TimeoutError, OSError) as net_err:
                status_code = 599  # Custom harness connection failure indicator
                err_msg = str(net_err)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if 200 <= status_code < 400:
                latencies_ms.append(max(elapsed_ms, 0.01))
            else:
                error_count += 1

            request_logs.append({
                "req_idx": req_idx,
                "status_code": status_code,
                "latency_ms": elapsed_ms,
                "error": err_msg,
            })

        # Sample process resident memory and CPU fraction
        metrics = harness.get_current_metrics()
        current_memory_mb = float(metrics.get("memory_mb", 0.0))
        current_cpu = float(metrics.get("cpu_fraction", 0.0))

        # Geometric mean latency across successful responses (as defined in TelemetryRecord contract)
        if latencies_ms:
            log_latencies = np.log(latencies_ms)
            geo_mean_latency = float(np.exp(np.mean(log_latencies)))
        else:
            # Fallback when all requests failed: penalize with timeout latency
            geo_mean_latency = float(self.default_timeout_per_req * 1000.0)

        record = TelemetryRecord(
            run_id=run_id,
            tick=tick,
            event_time=tick,
            arrival_time=tick,
            server_id=server_id,
            rack_id=rack_id,
            class_id=class_id,
            version=version,
            exposure=exposure,
            request_count=request_count,
            latency_ms=round(geo_mean_latency, 4),
            memory_mb=round(current_memory_mb, 2),
            cpu_fraction=round(min(max(current_cpu, 0.0), 1.0), 4),
            error_count=error_count,
            observed=True,
            source="MEASURED",
        )

        return record, request_logs
