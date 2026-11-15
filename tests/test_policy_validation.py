"""Tests for policy artifact compatibility, scale constraints, and calibration validation.

Verifies:
- Rejection of positive thresholds on LOG_POSTERIOR_RISK scale (log p <= 0).
- Rejection of uncalibrated policies when require_calibrated=True.
- Model ID, alpha, and horizon validation.
- Validated factory functions create_calibrated_hier_policy and create_uncalibrated_exploratory_policy.
"""
from __future__ import annotations

import math
import pytest

from canary_ssm.detector_service import (
    FrozenPolicy,
    create_calibrated_hier_policy,
    create_uncalibrated_exploratory_policy,
    validate_policy_compatibility,
)


def test_positive_threshold_rejected_on_log_scale():
    """Thresholds on LOG_POSTERIOR_RISK scale must be <= 0.0 (log of probability)."""
    # Positive threshold is invalid because log(p) <= 0 for all p in [0, 1]
    bad_policy = FrozenPolicy(
        policy_id="BAD-SCALE",
        model_id="MODEL-HSSM-V1",
        threshold_lat=0.50,  # Invalid: positive on log scale!
        threshold_mem=-0.693,
        threshold_scale="LOG_POSTERIOR_RISK",
    )
    is_valid, reasons = validate_policy_compatibility(bad_policy)
    assert not is_valid
    assert any("threshold_lat" in r and "LOG_POSTERIOR_RISK" in r for r in reasons)


def test_uncalibrated_policy_rejected_when_calibrated_required():
    """Exploratory policies must be rejected when calibrated status is required for deployment."""
    exploratory = create_uncalibrated_exploratory_policy()
    assert not exploratory.is_calibrated
    assert exploratory.calibration_status == "UNVALIDATED_EXPLORATORY"

    is_valid, reasons = validate_policy_compatibility(exploratory, require_calibrated=True)
    assert not is_valid
    assert any("UNVALIDATED_EXPLORATORY" in r for r in reasons)


def test_calibrated_policy_passes_validation():
    """Calibrated policy from table_null_validation passes compatibility checks."""
    calibrated = create_calibrated_hier_policy(
        threshold_lat=-1.14122,
        threshold_mem=-0.67302,
        evaluation_horizon=75,
    )
    assert calibrated.is_calibrated
    assert calibrated.calibration_status == "CALIBRATED"
    assert calibrated.achieved_far == 0.01

    is_valid, reasons = validate_policy_compatibility(calibrated, require_calibrated=True, horizon=75)
    assert is_valid
    assert len(reasons) == 0


def test_model_id_and_horizon_mismatch():
    """Incompatible model or shorter calibrated horizon must be rejected."""
    policy = create_calibrated_hier_policy(evaluation_horizon=50)

    # Model ID mismatch
    is_valid, reasons = validate_policy_compatibility(policy, expected_model_id="MODEL-NEURAL-V2")
    assert not is_valid
    assert any("model_id" in r for r in reasons)

    # Horizon exceeds calibrated horizon
    is_valid, reasons = validate_policy_compatibility(policy, horizon=100)
    assert not is_valid
    assert any("horizon" in r for r in reasons)


def test_alpha_bounds():
    """Alpha outside (0, 1] must be rejected."""
    bad_alpha = FrozenPolicy(alpha=0.0)
    is_valid, reasons = validate_policy_compatibility(bad_alpha)
    assert not is_valid
    assert any("alpha" in r for r in reasons)
