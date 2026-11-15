"""Physical Telemetry vs Numerical Simulator Comparison & Recalibration Module.

Contrasts physical measured telemetry against idealized numerical simulations.
Demonstrates why simulator-calibrated thresholds cannot be blindly transferred
to physical workloads without empirical validation and recalibration.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from canary_ssm.telemetry.records import TelemetryRecord


def compare_physical_vs_simulated(
    physical_records: list[TelemetryRecord],
    simulated_records: list[TelemetryRecord],
) -> dict[str, Any]:
    """Compare empirical properties of physical measured telemetry against numerical simulation.

    Parameters
    ----------
    physical_records:
        Telemetry records emitted by isolated physical worker execution (source='MEASURED').
    simulated_records:
        Telemetry records emitted by numerical simulator (source='SIMULATED').

    Returns
    -------
    dict:
        Statistical comparison summary contrasting noise structures, baseline footprints,
        and operational distributional divergence.
    """
    if not physical_records or not simulated_records:
        raise ValueError("Both physical_records and simulated_records must be non-empty")

    phys_lats = np.array([r.latency_ms for r in physical_records])
    sim_lats = np.array([r.latency_ms for r in simulated_records])

    phys_mems = np.array([r.memory_mb for r in physical_records])
    sim_mems = np.array([r.memory_mb for r in simulated_records])

    phys_lat_stats = {
        "mean_ms": round(float(np.mean(phys_lats)), 3),
        "std_ms": round(float(np.std(phys_lats)), 3),
        "cv": round(float(np.std(phys_lats) / max(np.mean(phys_lats), 1e-6)), 3),
        "min_ms": round(float(np.min(phys_lats)), 3),
        "max_ms": round(float(np.max(phys_lats)), 3),
    }

    sim_lat_stats = {
        "mean_ms": round(float(np.mean(sim_lats)), 3),
        "std_ms": round(float(np.std(sim_lats)), 3),
        "cv": round(float(np.std(sim_lats) / max(np.mean(sim_lats), 1e-6)), 3),
        "min_ms": round(float(np.min(sim_lats)), 3),
        "max_ms": round(float(np.max(sim_lats)), 3),
    }

    phys_mem_stats = {
        "initial_mb": round(float(phys_mems[0]), 2),
        "final_mb": round(float(phys_mems[-1]), 2),
        "delta_mb": round(float(phys_mems[-1] - phys_mems[0]), 2),
        "std_mb": round(float(np.std(phys_mems)), 2),
    }

    sim_mem_stats = {
        "initial_mb": round(float(sim_mems[0]), 2),
        "final_mb": round(float(sim_mems[-1]), 2),
        "delta_mb": round(float(sim_mems[-1] - sim_mems[0]), 2),
        "std_mb": round(float(np.std(sim_mems)), 2),
    }

    comparison = {
        "physical_latency": phys_lat_stats,
        "simulated_latency": sim_lat_stats,
        "physical_memory": phys_mem_stats,
        "simulated_memory": sim_mem_stats,
        "distributional_divergence": {
            "memory_footprint": (
                "Physical process exhibits runtime base footprint (Python interpreter RSS ~20-30MB) "
                "and discrete OS page allocations, whereas numerical simulation initiates from "
                "synthetically configured host capacity baselines."
            ),
            "latency_jitter": (
                "Physical HTTP requests reflect real socket handshakes, kernel context switching, "
                "and garbage collection pauses, producing empirical tails absent in stationary AR(1) models."
            ),
            "transferability_warning": (
                "Simulator-calibrated thresholds CANNOT be blindly transferred to physical workloads. "
                "Empirical noise variance sigma^2 and autoregressive parameter rho must be re-estimated "
                "on physical baseline runs to maintain declared false alert budgets."
            ),
        },
    }

    return comparison


def recalibrate_empirical_threshold(
    baseline_runs: list[list[TelemetryRecord]],
    target_fpr: float = 0.05,
) -> dict[str, Any]:
    """Fit empirical noise characteristics and calculate a recalibrated empirical threshold.

    Parameters
    ----------
    baseline_runs:
        Collection of clean physical workload runs under healthy baseline operation.
    target_fpr:
        Target false positive rate budget alpha (default: 0.05).

    Returns
    -------
    dict:
        Empirical noise estimates and calibrated decision threshold.
    """
    if not baseline_runs:
        raise ValueError("baseline_runs cannot be empty")

    run_max_residuals: list[float] = []

    for run in baseline_runs:
        if len(run) < 2:
            continue
        mems = np.array([r.memory_mb for r in run])
        # Simple first-difference growth residual
        diffs = np.diff(mems)
        run_max_residuals.append(float(np.max(diffs)))

    if not run_max_residuals:
        raise ValueError("Insufficient baseline run data for calibration")

    arr = np.array(run_max_residuals)
    quantile_level = 1.0 - target_fpr
    calibrated_threshold = float(np.quantile(arr, quantile_level))

    return {
        "target_fpr": target_fpr,
        "sample_runs": len(baseline_runs),
        "empirical_mean_diff": round(float(np.mean(arr)), 3),
        "empirical_std_diff": round(float(np.std(arr)), 3),
        "calibrated_threshold": round(calibrated_threshold, 3),
        "calibration_status": "CALIBRATED_ON_PHYSICAL_BASELINE",
    }
