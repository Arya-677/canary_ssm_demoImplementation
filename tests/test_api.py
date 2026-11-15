"""Unit tests for FastAPI REST API endpoints and Web Dashboard serving."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from canary_ssm.api.app import create_app
from canary_ssm.api.service import SimulatorService


@pytest.fixture
def client():
    svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=42, ssm_connected=True)
    app = create_app(service=svc)
    return TestClient(app)


def test_serve_dashboard_static_files(client: TestClient):
    """Dashboard HTML, CSS, and JS must be served with HTTP 200."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Virtual Data Center" in res_index.text
    assert "<nav class=\"nav-tabs\">" in res_index.text

    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200
    assert ":root" in res_css.text

    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "setupNavigation" in res_js.text


def test_world_status_and_control(client: TestClient):
    """World status endpoint and stepping/pause controls."""
    res = client.get("/api/world/status")
    assert res.status_code == 200
    data = res.json()
    assert data["tick"] >= 30  # Initial warm-up ticks
    assert data["infrastructure_advisory"] == "NORMAL"
    assert data["canary_release_advisory"] == "RUNNING"
    assert data["fleet_summary"]["total_servers"] == 24

    # Step simulation by 5 ticks
    start_tick = data["tick"]
    res_step = client.post("/api/world/control", json={"action": "step", "ticks": 5})
    assert res_step.status_code == 200
    assert res_step.json()["tick"] == start_tick + 5

    # Change speed
    res_speed = client.post("/api/world/control", json={"action": "speed", "speed_seconds": 0.5})
    assert res_speed.status_code == 200
    assert res_speed.json()["tick_speed_seconds"] == 0.5


def test_servers_and_racks_topology(client: TestClient):
    """Inspect servers and racks topology."""
    res_servers = client.get("/api/world/servers")
    assert res_servers.status_code == 200
    servers = res_servers.json()
    assert len(servers) == 24

    res_racks = client.get("/api/world/racks")
    assert res_racks.status_code == 200
    racks = res_racks.json()
    assert len(racks) == 4
    assert racks[0]["rack_id"] == "rack-0"
    assert len(racks[0]["servers"]) == 6


def test_releases_and_allocation_validation(client: TestClient):
    """Release creation, allocation validation, and identifiability guards."""
    # List releases (contains baseline)
    res_list = client.get("/api/releases")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # Create new memory leak release
    leak_payload = {
        "release_id": "rel-test-leak",
        "version_tag": "v1.2.0-test",
        "behavior_profile": {
            "profile_type": "MEMORY_LEAK",
            "severity": 45.0,
            "duration": 60,
        },
        "artifact_filename": "cache_service.py",
        "artifact_content": "# Unexecuted cache code\n",
    }
    res_create = client.post("/api/releases", json=leak_payload)
    assert res_create.status_code == 200
    data = res_create.json()
    assert data["release_id"] == "rel-test-leak"
    assert data["artifact"]["is_executed"] is False

    # Get default balanced allocation
    res_def_alloc = client.get("/api/releases/default-allocation")
    assert res_def_alloc.status_code == 200
    canaries = res_def_alloc.json()["recommended_canaries"]
    assert len(canaries) == 4

    # Validate default allocation (must pass)
    res_val_ok = client.post("/api/releases/validate", json={"canary_server_ids": canaries})
    assert res_val_ok.status_code == 200
    assert res_val_ok.json()["is_valid"] is True

    # Validate confounded allocation (pure canary rack) -> MUST FAIL
    pure_rack_canaries = ["srv-r0-s0", "srv-r0-s1", "srv-r0-s2", "srv-r0-s3", "srv-r0-s4", "srv-r0-s5"]
    res_val_confounded = client.post("/api/releases/validate", json={"canary_server_ids": pure_rack_canaries})
    assert res_val_confounded.status_code == 200
    assert res_val_confounded.json()["is_valid"] is False
    assert any("CONFUSED_RACK_CONFOUNDING" in iss for iss in res_val_confounded.json()["issues"])


def test_deployment_and_rollback_flow(client: TestClient):
    """Deploy release, step simulation, observe canary memory leak, then rollback."""
    # Register release
    client.post("/api/releases", json={
        "release_id": "rel-flow-leak",
        "version_tag": "v1.2.0-flow",
        "behavior_profile": {"profile_type": "MEMORY_LEAK", "severity": 40.0, "duration": 60},
        "artifact_filename": "worker.py",
        "artifact_content": "# code\n",
    })

    canaries = ["srv-r0-s0", "srv-r1-s3", "srv-r2-s0", "srv-r3-s3"]
    res_deploy = client.post("/api/releases/deploy", json={
        "release_id": "rel-flow-leak",
        "canary_server_ids": canaries,
    })
    assert res_deploy.status_code == 200
    assert res_deploy.json()["status"] == "DEPLOYED"

    # Step simulation by 15 ticks
    client.post("/api/world/control", json={"action": "step", "ticks": 15})

    # Check advisory: canary memory leak should be detected!
    res_adv = client.get("/api/monitoring/advisory")
    assert res_adv.status_code == 200
    adv = res_adv.json()
    assert adv["canary_release_advisory"] == "PAUSE RECOMMENDED"
    assert "Canary process memory elevated" in adv["advisory_reason"]

    # Rollback release with process restart
    res_rb = client.post("/api/releases/rollback", json={
        "release_id": "rel-flow-leak",
        "restart_process": True,
    })
    assert res_rb.status_code == 200
    assert res_rb.json()["status"] == "ROLLED_BACK"
    assert res_rb.json()["memory_cleared"] is True

    # Status should show ROLLED BACK
    res_status = client.get("/api/world/status")
    assert res_status.json()["canary_release_advisory"] == "ROLLED BACK"


def test_fault_injection_and_truth_store(client: TestClient):
    """Manual fault injection in developer view updates truth store."""
    res_fault = client.post("/api/faults/inject", json={
        "fault_type": "RACK_NETWORK_LATENCY",
        "scope": "RACK",
        "target_id": "rack-2",
        "severity": 0.30,
        "duration": 40,
    })
    assert res_fault.status_code == 200
    assert res_fault.json()["scope"] == "rack"

    # Step 5 ticks
    client.post("/api/world/control", json={"action": "step", "ticks": 5})

    # Inspect ground truth
    res_truth = client.get("/api/faults/truth")
    assert res_truth.status_code == 200
    truth = res_truth.json()
    assert len(truth["registered_faults"]) >= 1
    assert any(f["target_id"] == "rack-2" for f in truth["registered_faults"])

    # Check advisory: Infrastructure Advisory should detect RACK_DEGRADED on rack-2!
    res_adv = client.get("/api/monitoring/advisory")
    assert res_adv.status_code == 200
    adv = res_adv.json()
    assert "rack-2" in adv["infrastructure_advisory"]


def test_evaluation_summary(client: TestClient):
    """Evaluation summary endpoint compares ground truth vs detector decision."""
    res_eval = client.get("/api/evaluation/summary")
    assert res_eval.status_code == 200
    data = res_eval.json()
    assert "has_true_release_fault" in data
    assert "detector_recommends_pause" in data
    assert "infrastructure_advisory" in data
    assert "canary_release_advisory" in data


def test_detector_not_connected_default_and_toggle():
    """Default service state without SSM must honestly report DETECTOR NOT CONNECTED."""
    unconnected_svc = SimulatorService(n_racks=4, servers_per_rack=6, seed=42, ssm_connected=False)
    app = create_app(service=unconnected_svc)
    c = TestClient(app)

    # Deploy a canary release
    c.post("/api/releases", json={
        "release_id": "rel-unconn",
        "version_tag": "v1.9.0",
        "behavior_profile": {"profile_type": "CLEAN"},
    })
    c.post("/api/releases/deploy", json={"release_id": "rel-unconn"})

    res_adv = c.get("/api/monitoring/advisory")
    assert res_adv.status_code == 200
    assert res_adv.json()["canary_release_advisory"] == "DETECTOR NOT CONNECTED"
    assert "DETECTOR NOT CONNECTED" in res_adv.json()["advisory_reason"]

    # Toggle detector ON
    res_toggle = c.post("/api/detector/toggle", json={"connected": True})
    assert res_toggle.status_code == 200
    assert res_toggle.json()["ssm_connected"] is True

    # Now detector reports statistical status
    res_adv_on = c.get("/api/monitoring/advisory")
    assert res_adv_on.json()["canary_release_advisory"] == "RUNNING"


def test_hazards_configuration(client: TestClient):
    """Configuring stochastic hazards in Fault Lab."""
    res = client.post("/api/faults/hazards", json={
        "enable_stochastic": True,
        "server_outage_hazard_per_min": 0.005,
        "rack_latency_hazard_per_min": 0.010,
        "seed": 999,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["enable_stochastic"] is True
    assert data["server_outage_hazard_per_min"] == 0.005


def test_command_history(client: TestClient):
    """Command history tracks executed deployments and actions."""
    res = client.get("/api/commands/history")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_run_export_import(client: TestClient):
    """Exporting a saved run and importing it for replay."""
    res_export = client.get("/api/runs/export")
    assert res_export.status_code == 200
    bundle = res_export.json()
    assert "telemetry_history" in bundle
    assert "fleet_summary" in bundle

    res_import = client.post("/api/runs/import", json={"bundle": bundle})
    assert res_import.status_code == 200
    assert res_import.json()["status"] == "LOADED"


def test_detector_endpoints_status_evidence_timeline(client: TestClient):
    """Test dedicated detector endpoints: /status, /evidence, /timeline, /auto-rollback."""
    # Status endpoint
    res_status = client.get("/api/detector/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["model_id"] == "MODEL-HSSM-V1"
    assert data_status["policy_id"] == "POLICY-SIDAK-0.05"
    assert data_status["infrastructure_advisory"] == "NORMAL"
    assert "data_eligibility" in data_status
    assert "epistemic_disclaimer" in data_status

    # Evidence endpoint
    res_evidence = client.get("/api/detector/evidence")
    assert res_evidence.status_code == 200
    data_evidence = res_evidence.json()
    assert "servers" in data_evidence
    assert len(data_evidence["servers"]) == 24

    # Timeline endpoint
    res_timeline = client.get("/api/detector/timeline?limit=50")
    assert res_timeline.status_code == 200
    data_timeline = res_timeline.json()
    assert isinstance(data_timeline, list)
    assert len(data_timeline) > 0
    assert "canary_effect_ci_lower" in data_timeline[-1]

    # Auto-rollback toggle
    res_ar = client.post("/api/detector/auto-rollback", json={"enabled": True})
    assert res_ar.status_code == 200
    assert res_ar.json()["auto_rollback_enabled"] is True


def test_auto_rollback_intervention_censoring(client: TestClient):
    """Test opt-in automated simulated rollback intervention and censoring."""
    # Enable auto-rollback
    client.post("/api/detector/auto-rollback", json={"enabled": True})

    # Create severe regression release
    client.post("/api/releases", json={
        "release_id": "rel-auto-rb-test",
        "version_tag": "v1.9.9",
        "behavior_profile": {"profile_type": "LATENCY_REGRESSION", "severity": 0.35, "duration": 60},
        "artifact_filename": "server.py",
        "artifact_content": "# code\n",
    })

    canaries = ["srv-r0-s0", "srv-r1-s3", "srv-r2-s0", "srv-r3-s3"]
    client.post("/api/releases/deploy", json={
        "release_id": "rel-auto-rb-test",
        "canary_server_ids": canaries,
    })

    # Step simulation until auto-rollback triggers
    for _ in range(8):
        client.post("/api/world/control", json={"action": "step", "ticks": 1})
        status = client.get("/api/world/status").json()
        if status.get("auto_rollback_triggered"):
            break

    # After trigger, canary release advisory transitions to ROLLED BACK
    status_final = client.get("/api/world/status").json()
    assert status_final["auto_rollback_triggered"] is True
    assert status_final["intervention_tick"] is not None
    assert status_final["canary_release_advisory"] == "ROLLED BACK"

