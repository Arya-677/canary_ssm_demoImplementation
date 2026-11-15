"""Acceptance Scenario Unit Tests for Virtual Data Center.

Verifies the 4 primary acceptance demo scenarios:
1. Scenario 1: Clean Baseline Rollout (Infrastructure: NORMAL, Canary: RUNNING).
2. Scenario 2: Canary Memory Leak (Infrastructure: NORMAL, Canary: PAUSE RECOMMENDED).
3. Scenario 3: Rack Network Slowdown (Infrastructure: RACK_DEGRADED: rack-0, Canary: RUNNING).
4. Scenario 4A: Compound Faults (Infrastructure: RACK_DEGRADED: rack-0, Canary: PAUSE RECOMMENDED).
5. Scenario 4B: Pure-Canary Rack Confounding (Canary: INSUFFICIENT DATA / CONFLICT).
"""
from __future__ import annotations

import pytest

from canary_ssm.studies.acceptance_scenarios import (
    run_clean_baseline_scenario,
    run_compound_faults_scenario,
    run_confounded_pure_rack_scenario,
    run_memory_leak_scenario,
    run_rack_slowdown_scenario,
)


def test_scenario_1_clean_baseline():
    """Scenario 1: Clean release maintains NORMAL infrastructure and RUNNING canary."""
    res = run_clean_baseline_scenario(seed=42)
    assert res.is_correct_classification is True
    assert res.final_infrastructure_advisory == "NORMAL"
    assert res.final_canary_release_advisory == "RUNNING"
    assert res.final_release_score < 0.40
    assert len(res.timeline_summary) >= 1


def test_scenario_2_canary_memory_leak():
    """Scenario 2: Canary memory leak correctly triggers PAUSE RECOMMENDED with NORMAL infrastructure."""
    res = run_memory_leak_scenario(seed=42)
    assert res.is_correct_classification is True
    assert res.final_infrastructure_advisory == "NORMAL"
    assert res.final_canary_release_advisory == "PAUSE RECOMMENDED"
    assert "Canary process memory elevated" in res.advisory_reason
    assert res.evaluation_details["memory_growth_detected"] is True


def test_scenario_3_rack_network_slowdown():
    """Scenario 3: Rack network slowdown degrades infrastructure but keeps canary RUNNING."""
    res = run_rack_slowdown_scenario(seed=42)
    assert res.is_correct_classification is True
    assert "rack-0" in res.final_infrastructure_advisory
    assert res.final_canary_release_advisory == "RUNNING"
    assert res.evaluation_details["canary_isolated_from_rack_fault"] is True


def test_scenario_4a_compound_faults():
    """Scenario 4A: Compound faults show RACK_DEGRADED infrastructure AND PAUSE RECOMMENDED canary."""
    res = run_compound_faults_scenario(seed=42)
    assert res.is_correct_classification is True
    assert "rack-0" in res.final_infrastructure_advisory
    assert res.final_canary_release_advisory == "PAUSE RECOMMENDED"


def test_scenario_4b_confounded_pure_rack():
    """Scenario 4B: Pure-canary rack triggers INSUFFICIENT DATA / CONFLICT identifiability guard."""
    res = run_confounded_pure_rack_scenario(seed=42)
    assert res.is_correct_classification is True
    assert res.final_canary_release_advisory == "INSUFFICIENT DATA / CONFLICT"
    assert "Confounded allocation" in res.advisory_reason
    assert res.evaluation_details["allocation_rejected"] is True
