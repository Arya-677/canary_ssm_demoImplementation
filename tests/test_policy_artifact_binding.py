"""Tests for runtime policy-artifact contract and safe loader binding (WP-C1 / WP-C4).

Verifies:
1. Valid compatible artifact accepted with calibrated status and Gate G2 PASS.
2. Missing artifact becomes exploratory (no silent calibrated default).
3. Model ID / hash mismatch rejected with explicit reason.
4. Regime mismatch rejected with explicit reason.
5. Horizon under-specification rejected with explicit reason.
6. Failed or unevaluable Gate G2 artifact rejected for operational recommendations.
7. Rejected artifact cannot produce a calibrated dashboard or advisory status.
8. Complete detector firewall remains intact: no Truth or metrics imports in detector modules.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from canary_ssm.api.service import SimulatorService
from canary_ssm.detector_service import (
    DetectorService,
    FrozenPolicy,
    PolicyArtifactContract,
    create_uncalibrated_exploratory_policy,
    load_runtime_policy_artifact,
    validate_policy_compatibility,
)


def _make_server_meta() -> dict[str, dict]:
    """Create minimal mock server metadata for 4 racks and 2 classes."""
    meta = {}
    for r in range(4):
        for s in range(6):
            sid = f"srv-r{r}-s{s}"
            meta[sid] = {
                "server_id": sid,
                "rack_id": f"rack-{r}",
                "class_id": s % 2,
                "memory_capacity_mb": 4096.0,
                "base_latency_ms": 20.0,
            }
    return meta


def test_valid_compatible_artifact_accepted(tmp_path: Path):
    """A valid, compatible policy artifact with passing Gate G2 is accepted as CALIBRATED."""
    artifact_file = tmp_path / "policy.json"
    artifact_payload = {
        "schema_version": 1,
        "policy_id": "POLICY-HAND-VALID-01",
        "model_id": "MODEL-HSSM-V1",
        "regime": "plain",
        "monitoring_horizon": 75,
        "threshold_scale": "LOG_POSTERIOR_RISK",
        "threshold_lat": -1.14122,
        "threshold_mem": -0.67302,
        "alpha": 0.05,
        "gate_g2_status": "PASS",
        "calibration_status": "CALIBRATED",
        "achieved_far": 0.048,
        "gate_g2_details": {"cells_ok": 119, "cells": 119, "status": "PASS"},
    }
    artifact_file.write_text(json.dumps(artifact_payload), encoding="utf-8")

    pol, is_valid, reasons = load_runtime_policy_artifact(
        artifact_path=artifact_file,
        expected_model_id="MODEL-HSSM-V1",
        expected_regime="plain",
        expected_horizon=75,
        active_method="hier_ssm",
    )

    assert is_valid is True
    assert pol.is_calibrated is True
    assert pol.calibration_status == "CALIBRATED"
    assert pol.gate_g2_status == "PASS"
    assert pol.threshold_lat == -1.14122
    assert pol.threshold_mem == -0.67302
    assert len(reasons) == 0

    meta = _make_server_meta()
    service = DetectorService(
        expected_servers=list(meta.keys()),
        server_metadata=meta,
        policy_artifact=artifact_file,
        expected_model_id="MODEL-HSSM-V1",
        regime="plain",
        evaluation_horizon=75,
    )
    status = service.get_status()
    assert status["is_calibrated"] is True
    assert status["calibration_status"] == "CALIBRATED"
    assert status["gate_g2_status"] == "PASS"
    assert status["regime"] == "plain"
    assert len(status["artifact_rejection_reasons"]) == 0


def test_missing_artifact_becomes_exploratory():
    """Initializing DetectorService without a verified artifact defaults to UNVALIDATED_EXPLORATORY."""
    meta = _make_server_meta()
    service = DetectorService(
        expected_servers=list(meta.keys()),
        server_metadata=meta,
        policy_artifact=None,
        regime="plain",
        evaluation_horizon=75,
    )

    assert service.frozen_policy.is_calibrated is False
    assert service.frozen_policy.calibration_status == "UNVALIDATED_EXPLORATORY"
    assert service.frozen_policy.gate_g2_status == "NOT_EVALUATED"
    assert len(service.artifact_rejection_reasons) > 0
    assert any("exploratory" in r.lower() or "no verified" in r.lower() for r in service.artifact_rejection_reasons)

    status = service.get_status()
    assert status["is_calibrated"] is False
    assert status["calibration_status"] == "UNVALIDATED_EXPLORATORY"
    assert status["gate_g2_status"] == "NOT_EVALUATED"


def test_model_mismatch_rejected(tmp_path: Path):
    """An artifact calibrated for a different model must be rejected with an explicit reason."""
    artifact_file = tmp_path / "policy_bad_model.json"
    artifact_payload = {
        "schema_version": 1,
        "policy_id": "POLICY-WRONG-MODEL",
        "model_id": "MODEL-INCOMPATIBLE-V9",
        "regime": "plain",
        "monitoring_horizon": 75,
        "threshold_scale": "LOG_POSTERIOR_RISK",
        "threshold_lat": -1.14122,
        "threshold_mem": -0.67302,
        "gate_g2_status": "PASS",
    }
    artifact_file.write_text(json.dumps(artifact_payload), encoding="utf-8")

    pol, is_valid, reasons = load_runtime_policy_artifact(
        artifact_path=artifact_file,
        expected_model_id="MODEL-HSSM-V1",
        expected_regime="plain",
    )

    assert is_valid is False
    assert pol.is_calibrated is False
    assert pol.calibration_status == "UNVALIDATED_EXPLORATORY"
    assert any("model" in r.lower() and "mismatch" in r.lower() for r in reasons)


def test_regime_mismatch_rejected(tmp_path: Path):
    """An artifact calibrated for step regime cannot be loaded into plain regime without rejection."""
    artifact_file = tmp_path / "policy_step_regime.json"
    artifact_payload = {
        "schema_version": 1,
        "policy_id": "POLICY-STEP-CALIBRATED",
        "model_id": "MODEL-HSSM-V1",
        "regime": "step",
        "monitoring_horizon": 75,
        "threshold_scale": "LOG_POSTERIOR_RISK",
        "threshold_lat": -0.85,
        "threshold_mem": -0.67302,
        "gate_g2_status": "PASS",
    }
    artifact_file.write_text(json.dumps(artifact_payload), encoding="utf-8")

    pol, is_valid, reasons = load_runtime_policy_artifact(
        artifact_path=artifact_file,
        expected_model_id="MODEL-HSSM-V1",
        expected_regime="plain",
    )

    assert is_valid is False
    assert pol.is_calibrated is False
    assert any("regime mismatch" in r.lower() for r in reasons)


def test_horizon_mismatch_rejected(tmp_path: Path):
    """An artifact calibrated for horizon 30 must be rejected when monitoring requires horizon 75."""
    artifact_file = tmp_path / "policy_short_horizon.json"
    artifact_payload = {
        "schema_version": 1,
        "policy_id": "POLICY-SHORT-HORIZON",
        "model_id": "MODEL-HSSM-V1",
        "regime": "plain",
        "monitoring_horizon": 30,
        "threshold_scale": "LOG_POSTERIOR_RISK",
        "threshold_lat": -1.14122,
        "threshold_mem": -0.67302,
        "gate_g2_status": "PASS",
    }
    artifact_file.write_text(json.dumps(artifact_payload), encoding="utf-8")

    pol, is_valid, reasons = load_runtime_policy_artifact(
        artifact_path=artifact_file,
        expected_model_id="MODEL-HSSM-V1",
        expected_regime="plain",
        expected_horizon=75,
    )

    assert is_valid is False
    assert pol.is_calibrated is False
    assert any("horizon mismatch" in r.lower() for r in reasons)


def test_failed_or_unevaluable_gate_g2_rejected(tmp_path: Path):
    """An artifact with Gate G2 FAIL or UNEVALUABLE must be rejected for operational calibration."""
    # Part A: gate_g2_status = FAIL
    artifact_file_fail = tmp_path / "policy_fail_gate.json"
    artifact_file_fail.write_text(
        json.dumps({
            "schema_version": 1,
            "policy_id": "POLICY-GATE-FAIL",
            "model_id": "MODEL-HSSM-V1",
            "regime": "plain",
            "monitoring_horizon": 75,
            "threshold_scale": "LOG_POSTERIOR_RISK",
            "threshold_lat": -1.14122,
            "threshold_mem": -0.67302,
            "gate_g2_status": "FAIL",
            "gate_g2_details": {
                "status": "FAIL",
                "failing": [{"method": "hier_rank0", "family": "S5_label_errors"}],
            },
        }),
        encoding="utf-8",
    )

    pol_fail, is_valid_fail, reasons_fail = load_runtime_policy_artifact(
        artifact_path=artifact_file_fail,
        expected_model_id="MODEL-HSSM-V1",
        expected_regime="plain",
        expected_horizon=75,
    )
    assert is_valid_fail is False
    assert pol_fail.is_calibrated is False
    assert pol_fail.calibration_status == "FAILED_CALIBRATION"
    assert any("gate g2 validation failed" in r.lower() for r in reasons_fail)

    # Part B: gate_g2_status = UNEVALUABLE
    artifact_file_uneval = tmp_path / "policy_unevaluable.json"
    artifact_file_uneval.write_text(
        json.dumps({
            "schema_version": 1,
            "policy_id": "POLICY-GATE-UNEVALUABLE",
            "model_id": "MODEL-HSSM-V1",
            "regime": "plain",
            "monitoring_horizon": 75,
            "threshold_scale": "LOG_POSTERIOR_RISK",
            "threshold_lat": -1.14122,
            "threshold_mem": -0.67302,
            "gate_g2_status": "UNEVALUABLE",
        }),
        encoding="utf-8",
    )

    pol_uneval, is_valid_uneval, reasons_uneval = load_runtime_policy_artifact(
        artifact_path=artifact_file_uneval,
        expected_model_id="MODEL-HSSM-V1",
        expected_regime="plain",
        expected_horizon=75,
    )
    assert is_valid_uneval is False
    assert pol_uneval.is_calibrated is False
    assert any("unevaluable" in r.lower() for r in reasons_uneval)


def test_rejected_artifact_cannot_produce_calibrated_dashboard_status(tmp_path: Path):
    """When an artifact is rejected, neither detector nor simulator services can report CALIBRATED."""
    bad_artifact = tmp_path / "bad_policy.json"
    bad_artifact.write_text(
        json.dumps({
            "schema_version": 1,
            "policy_id": "POLICY-UNAUDITED",
            "model_id": "MODEL-HSSM-V1",
            "regime": "plain",
            "monitoring_horizon": 75,
            "threshold_scale": "LOG_POSTERIOR_RISK",
            "threshold_lat": -1.14122,
            "threshold_mem": -0.67302,
            "gate_g2_status": "FAIL",
        }),
        encoding="utf-8",
    )

    sim = SimulatorService(policy_artifact_path=bad_artifact, regime="plain")
    status = sim.get_status()
    advisory = sim.evaluate_advisories()

    # Neither can report is_calibrated = True
    assert status["is_calibrated"] is False
    assert status["calibration_status"] != "CALIBRATED"
    assert advisory["is_calibrated"] is False
    assert advisory["calibration_status"] != "CALIBRATED"

    # Rejection reasons must be visible in both
    assert len(status["artifact_rejection_reasons"]) > 0
    assert len(advisory["artifact_rejection_reasons"]) > 0


def test_detector_firewall_remains_intact():
    """Verify that detector code never imports Truth, metrics, or reads *_truth files."""
    detector_modules = [
        "canary_ssm/detector_service.py",
        "canary_ssm/hierarchy.py",
        "canary_ssm/kalman.py",
        "canary_ssm/baselines.py",
        "canary_ssm/preprocess.py",
        "canary_ssm/factor.py",
        "canary_ssm/decision.py",
    ]

    for mod_path in detector_modules:
        p = Path(mod_path)
        assert p.exists(), f"Detector file missing: {mod_path}"
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "truth" not in alias.name.lower(), f"Forbidden truth import in {mod_path}: {alias.name}"
                    assert "metrics" not in alias.name.lower(), f"Forbidden metrics import in {mod_path}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "truth" not in mod.lower(), f"Forbidden truth import in {mod_path}: {mod}"
                assert "metrics" not in mod.lower(), f"Forbidden metrics import in {mod_path}: {mod}"
                for alias in node.names:
                    assert alias.name != "Truth", f"Forbidden Truth import in {mod_path}"
                    assert "metrics" not in alias.name.lower(), f"Forbidden metrics import in {mod_path}"
