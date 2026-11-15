"""Unit and integration tests for versioned scenarios and reproducibility exit gate.

Exit Gate Requirement:
A fresh local run reproduces telemetry and detector outputs under the same recorded config and environment.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from canary_ssm.evaluation.benchmarking import get_hardware_info, run_fleet_scaling_benchmark
from canary_ssm.evaluation.plotting import generate_all_plots
from canary_ssm.scenarios import (
    create_scenario_catalog,
    run_scenario,
    save_declarative_configs,
    verify_scenario_reproducibility,
)


def test_scenario_catalog_and_declarative_configs(tmp_path: Path) -> None:
    """Verify that all 8 versioned scenarios are defined and can be serialized to disk."""
    catalog = create_scenario_catalog()
    assert len(catalog) == 8

    expected_scenarios = {
        "clean_release",
        "release_leak_two_canaries",
        "rack_slowdown",
        "fleet_demand_spike",
        "cpu_regression",
        "healthy_gc",
        "combined_rack_fault_release_leak",
        "missing_controls",
    }
    assert set(catalog.keys()) == expected_scenarios

    # Save declarative configs to tmp_path
    saved = save_declarative_configs(out_dir=tmp_path)
    assert len(saved) == 8

    for p in saved:
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "name" in data
        assert "topology" in data
        assert "deployment" in data
        assert "workload" in data
        assert "injection" in data


def test_scenario_execution_and_separate_persistence(tmp_path: Path) -> None:
    """Verify that running a scenario persists all 5 separate artifacts."""
    catalog = create_scenario_catalog()
    scen = catalog["release_leak_two_canaries"]

    out_dir = tmp_path / "release_leak_two_canaries"
    result = run_scenario(scen, output_dir=out_dir)

    assert result.scenario_name == "release_leak_two_canaries"
    assert len(result.telemetry) == 75 * 24  # 75 ticks * 24 servers = 1800 records
    assert len(result.recommendations) == 75

    # Check that all 5 separate artifacts exist
    manifest_file = out_dir / "manifest.json"
    telem_file = out_dir / "telemetry.csv"
    model_policy_file = out_dir / "model_policy.json"
    recom_file = out_dir / "recommendations.csv"
    eval_file = out_dir / "evaluator_results.json"

    assert manifest_file.exists()
    assert telem_file.exists()
    assert model_policy_file.exists()
    assert recom_file.exists()
    assert eval_file.exists()

    # Evaluator truth verdict
    ev = result.evaluator_results
    assert ev["detection_status"] == "success"
    assert ev["final_canary_release_advisory"] == "PAUSE RECOMMENDED"
    assert ev["final_attribution"] == "MEMORY_GROWTH_LEAK"
    assert ev["alarm_tick"] is not None


def test_clean_release_and_rack_slowdown(tmp_path: Path) -> None:
    """Verify clean release remains quiet and rack slowdown absorbs infrastructure nuisance."""
    catalog = create_scenario_catalog()

    # Clean Release
    res_clean = run_scenario(catalog["clean_release"], output_dir=tmp_path / "clean")
    assert res_clean.evaluator_results["detection_status"] == "quiet"
    assert res_clean.evaluator_results["alarm_tick"] is None
    assert res_clean.evaluator_results["final_canary_release_advisory"] == "RUNNING"
    assert res_clean.evaluator_results["final_infrastructure_advisory"] == "NORMAL"

    # Rack Slowdown
    res_rack = run_scenario(catalog["rack_slowdown"], output_dir=tmp_path / "rack")
    assert res_rack.evaluator_results["detection_status"] == "quiet"
    assert res_rack.evaluator_results["alarm_tick"] is None
    assert res_rack.evaluator_results["final_canary_release_advisory"] == "RUNNING"
    assert res_rack.evaluator_results["final_infrastructure_advisory"] == "RACK_DEGRADED: rack-0"


def test_missing_controls_identifiability_abstention(tmp_path: Path) -> None:
    """Verify that missing rack controls enforces identifiability guard and blocks release attribution."""
    catalog = create_scenario_catalog()
    res_miss = run_scenario(catalog["missing_controls"], output_dir=tmp_path / "missing")

    assert res_miss.evaluator_results["final_canary_release_advisory"] == "INSUFFICIENT DATA / CONFLICT"
    assert res_miss.evaluator_results["final_attribution"] == "INSUFFICIENT_DATA"


def test_exit_gate_reproducibility() -> None:
    """Exit Gate Verification: fresh local runs reproduce saved telemetry and recommendations exactly."""
    scenarios_dir = Path("results/scenarios")
    assert scenarios_dir.exists()

    for p in scenarios_dir.iterdir():
        if p.is_dir() and (p / "manifest.json").exists():
            rep = verify_scenario_reproducibility(p)
            assert rep["reproduced"] is True, f"Failed reproduction for scenario {p.name}: {rep}"
            assert rep["telemetry_matches"] is True
            assert rep["advisories_match"] is True


def test_hardware_profiling_and_fleet_scaling(tmp_path: Path) -> None:
    """Verify hardware profile extraction and scaling benchmark runner."""
    hw = get_hardware_info()
    assert "machine" in hw
    assert "total_ram_gb" in hw
    assert hw["total_ram_gb"] > 0
    assert "physical_cores" in hw
    assert hw["physical_cores"] > 0

    # Small scaling run: 12 and 24 servers, 10 ticks
    out_csv = tmp_path / "scaling.csv"
    df = run_fleet_scaling_benchmark(fleet_sizes=(12, 24), n_ticks=10, out_csv=out_csv)
    assert len(df) == 2
    assert out_csv.exists()
    assert "median_ms_per_tick" in df.columns
    assert "peak_ram_mb" in df.columns
    assert "machine" in df.columns


def test_plot_generation(tmp_path: Path) -> None:
    """Verify plot generation strictly from saved results tables."""
    plots = generate_all_plots(out_dir=tmp_path)
    assert len(plots) >= 3
    for p in plots:
        assert p.exists()
        assert p.stat().st_size > 1000  # Non-trivial image file
