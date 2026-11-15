"""Replay and verification workflow for versioned scenarios.

Ensures the exit gate requirement:
A fresh local run reproduces telemetry and detector outputs under the same recorded config and environment.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from canary_ssm.detector_service import FrozenPolicy
from canary_ssm.telemetry.records import TelemetryRecord

from .models import ScenarioDefinition
from .runner import run_scenario


def verify_scenario_reproducibility(
    scenario_dir: str | Path,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """Verify that a fresh local execution identically reproduces persisted telemetry and detector outputs."""
    p = Path(scenario_dir)
    manifest_path = p / "manifest.json"
    telem_path = p / "telemetry.csv"
    recom_path = p / "recommendations.csv"
    model_policy_path = p / "model_policy.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest.json in {p}")
    if not telem_path.exists():
        raise FileNotFoundError(f"Missing telemetry.csv in {p}")
    if not recom_path.exists():
        raise FileNotFoundError(f"Missing recommendations.csv in {p}")

    # Load recorded artifacts
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenario = ScenarioDefinition.from_dict(manifest_data)

    policy = None
    if model_policy_path.exists():
        mp_data = json.loads(model_policy_path.read_text(encoding="utf-8"))
        policy = FrozenPolicy(
            policy_id=mp_data.get("policy_id", "POLICY-SIDAK-0.05"),
            model_id=mp_data.get("model_id", "MODEL-HSSM-V1"),
            alpha=float(mp_data.get("alpha", 0.05)),
            threshold_lat=float(mp_data.get("threshold_latency", -0.693147)),
            threshold_mem=float(mp_data.get("threshold_memory", -0.693147)),
            persistence_window=int(mp_data.get("persistence_window_ticks", 10)),
            kappa_lat=float(mp_data.get("kappa_latency_boundary", 0.0198026)),
            kappa_mem=float(mp_data.get("kappa_memory_mb_per_min", 0.50)),
        )

    # Execute a fresh run under recorded configuration
    fresh_result = run_scenario(scenario, output_dir=None, policy=policy)

    # 1. Compare Telemetry
    with open(telem_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        recorded_telem = list(reader)

    if len(fresh_result.telemetry) != len(recorded_telem):
        return {
            "reproduced": False,
            "error": f"Telemetry row count mismatch: {len(fresh_result.telemetry)} vs recorded {len(recorded_telem)}",
        }

    max_latency_diff = 0.0
    max_memory_diff = 0.0
    max_cpu_diff = 0.0

    for i, fresh_rec in enumerate(fresh_result.telemetry):
        rec_dict = recorded_telem[i]
        assert fresh_rec.server_id == rec_dict["server_id"]
        assert fresh_rec.tick == int(rec_dict["tick"])
        assert fresh_rec.exposure == (rec_dict["exposure"].lower() == "true")

        # Check exact rounded CSV precision matching
        lat_diff = abs(round(fresh_rec.latency_ms, 4) - float(rec_dict["latency_ms"]))
        mem_diff = abs(round(fresh_rec.memory_mb, 2) - float(rec_dict["memory_mb"]))
        cpu_diff = abs(round(fresh_rec.cpu_fraction, 4) - float(rec_dict["cpu_fraction"]))

        max_latency_diff = max(max_latency_diff, lat_diff)
        max_memory_diff = max(max_memory_diff, mem_diff)
        max_cpu_diff = max(max_cpu_diff, cpu_diff)

    telemetry_matches = (
        max_latency_diff <= tolerance and
        max_memory_diff <= tolerance and
        max_cpu_diff <= tolerance
    )

    # 2. Compare Recommendations
    with open(recom_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        recorded_recoms = list(reader)

    if len(fresh_result.recommendations) != len(recorded_recoms):
        return {
            "reproduced": False,
            "error": f"Recommendations row count mismatch: {len(fresh_result.recommendations)} vs recorded {len(recorded_recoms)}",
        }

    advisories_match = True
    for i, fresh_rec in enumerate(fresh_result.recommendations):
        rec_row = recorded_recoms[i]
        assert fresh_rec["tick"] == int(rec_row["tick"])
        if fresh_rec["infrastructure_advisory"] != rec_row["infrastructure_advisory"]:
            advisories_match = False
            break
        if fresh_rec["canary_release_advisory"] != rec_row["canary_release_advisory"]:
            advisories_match = False
            break
        if fresh_rec["inferred_attribution"] != rec_row["inferred_attribution"]:
            advisories_match = False
            break

    is_reproduced = bool(telemetry_matches and advisories_match)

    return {
        "reproduced": is_reproduced,
        "scenario_name": scenario.name,
        "telemetry_rows_compared": len(fresh_result.telemetry),
        "recommendation_rows_compared": len(fresh_result.recommendations),
        "max_latency_diff": max_latency_diff,
        "max_memory_diff": max_memory_diff,
        "max_cpu_diff": max_cpu_diff,
        "telemetry_matches": telemetry_matches,
        "advisories_match": advisories_match,
    }
