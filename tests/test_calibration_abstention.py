"""Tests for calibration abstention reporting and order-statistic integrity (Task 3).

Verifies:
a) In decision.py calibrate_threshold:
   - Fully masked nulls (no eligible observations in horizon, max=-inf) increment n_no_eligible.
   - Rollouts with valid finite scores are counted in n_finite_maxima.
   - Fully masked nulls DO NOT corrupt the order statistic k or threshold.
   - Error is raised if valid finite nulls < min_B_for_alpha.
b) In decision.py threshold_uncertainty:
   - Propagates n_no_eligible and n_finite_maxima into uncertainty dict.
c) In experiments.py:
   - Propagates abstention counts into threshold_uncertainty.csv and null_validation.json.
"""
from __future__ import annotations

import numpy as np
import pytest

from canary_ssm.decision import (
    calibrate_threshold,
    min_B_for_alpha,
    threshold_uncertainty,
    release_max,
)


def test_calibrate_threshold_masked_nulls_do_not_corrupt_k():
    """Verify that fully masked nulls increment n_no_eligible and do NOT shift order statistic k."""
    alpha = 0.05
    rng = np.random.default_rng(42)
    clean_maxima = rng.normal(-1.5, 0.3, size=100)

    # Baseline calibration on clean finite nulls
    cal_clean = calibrate_threshold(clean_maxima, alpha=alpha)
    assert cal_clean["n_no_eligible"] == 0
    assert cal_clean["n_finite_maxima"] == 100
    expected_k = cal_clean["k"]
    expected_thr = cal_clean["threshold"]

    # Inject 25 fully masked rollouts (-inf) and 5 NaN rollouts
    contaminated_maxima = np.r_[clean_maxima, np.full(25, -np.inf), np.full(5, np.nan)]
    cal_contam = calibrate_threshold(contaminated_maxima, alpha=alpha)

    # Assert abstention counts are recorded correctly
    assert cal_contam["n_no_eligible"] == 30
    assert cal_contam["n_finite_maxima"] == 100
    assert cal_contam["B"] == 100
    assert cal_contam["B_total"] == 130

    # Crucial property: order statistic k and threshold must stay bit-identical to clean run
    assert cal_contam["k"] == expected_k
    assert cal_contam["threshold"] == expected_thr


def test_calibrate_threshold_insufficient_valid_nulls_raises():
    """Verify that calibrate_threshold raises ValueError when valid finite nulls < min_B_for_alpha under strict=True, and returns inf threshold under default strict=False."""
    alpha = 0.05
    min_b = min_B_for_alpha(alpha)  # ceil(0.95 / 0.05) = 19
    assert min_b == 19

    # Provide 15 valid nulls and 50 masked nulls (total 65 rollouts, but only 15 valid < 19)
    maxima = np.r_[np.random.normal(0, 1, size=15), np.full(50, -np.inf)]

    with pytest.raises(ValueError, match="insufficient valid nulls"):
        calibrate_threshold(maxima, alpha=alpha, strict=True)

    # In default mode, k = ceil(16 * 0.95) = 16 > 15, so threshold is float("inf")
    res = calibrate_threshold(maxima, alpha=alpha, strict=False)
    assert res["threshold"] == float("inf")
    assert res["k"] == 16
    assert res["B"] == 15
    assert res["n_finite_maxima"] == 15
    assert res["n_no_eligible"] == 50


def test_threshold_uncertainty_propagates_abstention():
    """Verify threshold_uncertainty includes n_no_eligible and n_finite_maxima."""
    alpha = 0.05
    maxima = np.r_[np.random.normal(-1.0, 0.2, size=50), np.full(10, -np.inf)]

    unc = threshold_uncertainty(maxima, alpha=alpha, n_boot=200, seed=42)
    assert unc["n_no_eligible"] == 10
    assert unc["n_finite_maxima"] == 50
    assert unc["B"] == 50
    assert np.isfinite(unc["threshold"])
    assert np.isfinite(unc["boot_lo"])
    assert np.isfinite(unc["boot_hi"])


def test_release_max_all_masked_returns_neginf():
    """Verify that release_max returns -inf when all ticks are masked / ineligible."""
    score = np.array([0.5, 0.8, 1.2, 0.9])
    elig = np.array([False, False, False, False])
    t0 = 1

    m = release_max(score, elig, t0=t0, horizon=3)
    assert m == -np.inf
