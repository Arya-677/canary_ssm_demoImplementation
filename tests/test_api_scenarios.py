"""Test FastAPI endpoints for scenario catalog, 1-click loading, and pooling comparisons."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from canary_ssm.api.app import create_app
from canary_ssm.api.routes import set_service
from canary_ssm.api.service import SimulatorService


@pytest.fixture
def client():
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=42, ssm_connected=True)
    set_service(svc)
    app = create_app(svc)
    return TestClient(app)


def test_list_scenarios_endpoint(client):
    """GET /api/scenarios returns the canonical scenarios."""
    res = client.get("/api/scenarios")
    assert res.status_code == 200
    scenarios = res.json()
    assert len(scenarios) >= 8
    names = [s["name"] for s in scenarios]
    assert "clean_release" in names
    assert "release_leak_two_canaries" in names
    assert "rack_slowdown" in names


def test_load_scenario_endpoint(client):
    """POST /api/scenarios/load resets world and deploys scenario preset in 1 click."""
    res = client.post("/api/scenarios/load", json={"name": "release_leak_two_canaries"})
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == "release_leak_two_canaries"
    assert data["deployment"]["release_id"] == "rel-leak-v1"
    assert len(data["deployment"]["canary_servers"]) == 4

    # Status reflects deployed canary
    status = data["status"]
    assert status["active_release_id"] == "rel-leak-v1"
    assert len(status["canary_servers"]) == 4


def test_load_scenario_with_browser_payload(client):
    """POST /api/scenarios/load with exact browser payload {scenario_name: ...} returns 200."""
    res = client.post("/api/scenarios/load", json={"scenario_name": "clean_release"})
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == "clean_release"
    assert data["deployment"]["release_id"] == "rel-clean-v1"


def test_compare_methods_endpoint(client):
    """GET /api/detector/compare-methods returns comparison between Hierarchical, Independent, and Pooled SSM."""
    # First load a scenario so canaries are active
    client.post("/api/scenarios/load", json={"name": "clean_release"})

    # Step a few ticks
    client.post("/world/control", json={"action": "step", "ticks": 3})

    res = client.get("/api/detector/compare-methods")
    assert res.status_code == 200
    data = res.json()
    assert data["active"] is True
    methods = data["methods"]
    assert "hierarchical" in methods
    assert "independent" in methods
    assert "pooled" in methods
    assert methods["hierarchical"]["kind"] == "hier"
    assert methods["independent"]["kind"] == "indep"
    assert methods["pooled"]["kind"] == "pooled"
