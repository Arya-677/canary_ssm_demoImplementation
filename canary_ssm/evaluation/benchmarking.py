"""Benchmark runtime and memory scaling across increasing fleet sizes.

Measures:
- Total wall-clock time (seconds)
- Latency per tick (median ms, p95 ms, p99 ms)
- Process resident set size memory (RAM MB)
- Hardware environment metadata (CPU model, core counts, RAM, OS, Python version)
"""
from __future__ import annotations

import gc
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

from canary_ssm.detector_service import DetectorService, FrozenPolicy
from canary_ssm.world import create_default_fleet
from canary_ssm.world.telemetry import HealthyTelemetryConfig, HealthyTelemetryEngine


def get_hardware_info() -> dict[str, Any]:
    """Capture detailed machine hardware and environment profile."""
    proc = platform.processor() or platform.machine()
    logical_cpus = psutil.cpu_count(logical=True) or os.cpu_count() or 1
    physical_cpus = psutil.cpu_count(logical=False) or logical_cpus
    total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
    python_ver = sys.version.split()[0]

    return {
        "machine": proc,
        "physical_cores": physical_cpus,
        "logical_cpus": logical_cpus,
        "total_ram_gb": total_ram_gb,
        "os": os_name,
        "python_version": python_ver,
    }


def run_fleet_scaling_benchmark(
    fleet_sizes: tuple[int, ...] = (12, 24, 48, 96, 192, 384),
    n_ticks: int = 60,
    out_csv: str | Path = "results/runtime_scaling.csv",
    seed: int = 42,
) -> pd.DataFrame:
    """Benchmark simulation and hierarchical detector scaling across increasing fleet sizes."""
    hw = get_hardware_info()
    process = psutil.Process()
    rows: list[dict[str, Any]] = []

    for total_servers in fleet_sizes:
        servers_per_rack = 6
        n_racks = max(2, total_servers // servers_per_rack)
        actual_total = n_racks * servers_per_rack

        gc.collect()
        ram_before_mb = process.memory_info().rss / (1024 * 1024)

        # 1. Initialize Fleet & Metadata
        fleet = create_default_fleet(
            n_racks=n_racks,
            servers_per_rack=servers_per_rack,
            n_classes=2,
        )
        all_server_ids = [s.server_id for s in fleet.list_servers()]
        server_meta = {
            s.server_id: {
                "server_id": s.server_id,
                "rack_id": s.rack_id,
                "class_id": s.class_id,
                "memory_capacity_mb": s.memory_capacity_mb,
                "base_latency_ms": s.base_latency_ms,
            }
            for s in fleet.list_servers()
        }

        # 1 canary per rack
        canary_ids = [f"srv-r{r}-s0" for r in range(n_racks)]
        t_cfg = HealthyTelemetryConfig()
        telem_engine = HealthyTelemetryEngine(config=t_cfg, seed=seed)

        # Initialize detector service
        det_service = DetectorService(
            expected_servers=all_server_ids,
            server_metadata=server_meta,
            frozen_policy=FrozenPolicy(),
            ssm_connected=True,
        )

        # Deployment at tick 15
        t0 = 15
        deployed = False
        tick_times_ms: list[float] = []

        t_start_total = time.perf_counter()

        for t in range(n_ticks):
            t_tick_start = time.perf_counter()

            if t == t0 and not deployed:
                deployed = True
                for cid in canary_ids:
                    s = fleet.get_server(cid)
                    if s:
                        s.installed_version = "v1.2.0-bench"
                det_service.set_deployment("rel-bench", canary_ids=canary_ids, t0=t0)

            # Generate and ingest
            recs = telem_engine.generate_tick_telemetry(fleet, t, run_id="bench-scaling")
            det_service.ingest(recs)
            det_service.step(t)

            t_tick_end = time.perf_counter()
            tick_times_ms.append((t_tick_end - t_tick_start) * 1000.0)

        t_end_total = time.perf_counter()
        total_time_sec = t_end_total - t_start_total

        ram_after_mb = process.memory_info().rss / (1024 * 1024)
        peak_ram_mb = max(ram_before_mb, ram_after_mb)

        tick_arr = np.array(tick_times_ms)
        median_ms = float(np.median(tick_arr))
        p95_ms = float(np.quantile(tick_arr, 0.95))
        p99_ms = float(np.quantile(tick_arr, 0.99))
        throughput_ticks_per_sec = float(n_ticks / total_time_sec) if total_time_sec > 0 else 0.0

        rows.append({
            "fleet_size": actual_total,
            "n_racks": n_racks,
            "servers_per_rack": servers_per_rack,
            "n_canaries": len(canary_ids),
            "n_ticks": n_ticks,
            "total_time_sec": round(total_time_sec, 3),
            "throughput_ticks_per_sec": round(throughput_ticks_per_sec, 1),
            "median_ms_per_tick": round(median_ms, 3),
            "p95_ms_per_tick": round(p95_ms, 3),
            "p99_ms_per_tick": round(p99_ms, 3),
            "peak_ram_mb": round(peak_ram_mb, 2),
            "machine": hw["machine"],
            "physical_cores": hw["physical_cores"],
            "logical_cpus": hw["logical_cpus"],
            "total_ram_gb": hw["total_ram_gb"],
            "os": hw["os"],
            "python_version": hw["python_version"],
        })

    df = pd.DataFrame(rows)
    out_p = Path(out_csv)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_p, index=False)

    return df
