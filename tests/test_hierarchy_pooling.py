"""Comprehensive tests for Hierarchical State-Space Model, Helmert basis, implied host covariance,
and diagnostic pooling studies (Prompt 8).

Requirements:
1. Construct class incidence C (n x G) and deterministic within-class orthonormal sum-zero basis B (n x (n-G)).
2. Verify C^T B = 0 and B^T B = I, including singleton classes.
3. Define effect a = C theta + B b; state s = [theta, b, e];
   transition F = blockdiag(rho_g I, rho_h I, Phi_e);
   observation H = [C, B, I]; effect extraction L = [C, B, 0].
4. Output class effects, host deviations, effect means, effect covariance, and Pr(host log latency effect > log(1.02)).
5. Release score is max host risk and must not be called a joint probability.
6. Implied host covariance and sensitivity to pooling strength.
7. Demonstrate class-wide harm, sparse harm (reporting negative transfer if present), rack shock, and recovery.
8. Saved diagnostic traces showing actual pooling behavior.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from scipy.stats import norm

from canary_ssm.detectors import (
    OnlineHierarchicalSSM,
    OnlineIndependentSSM,
    OnlinePooledSSM,
)
from canary_ssm.factor import Adjusted
from canary_ssm.hierarchy import (
    EffectDetector,
    EffectParams,
    class_structure,
    deterministic_helmert_basis,
    implied_host_covariance,
    pooling_correlation,
)
from canary_ssm.preprocess import Nuisance
from canary_ssm.schema import KAPPA
from canary_ssm.studies.study_hierarchical_pooling import (
    run,
    run_scenario_class_wide_harm,
    run_scenario_sparse_harm,
    run_scenario_rack_shock,
    run_scenario_recovery,
)


# =====================================================================
# 1. Deterministic Helmert Basis & Singleton Tests
# =====================================================================
def test_helmert_basis_mathematical_properties():
    """Verify sum-zero (1^T B = 0), orthonormality (B^T B = I), and determinism."""
    for m in [1, 2, 3, 5, 8, 12]:
        B = deterministic_helmert_basis(m)
        if m == 1:
            assert B.shape == (1, 0)
        else:
            assert B.shape == (m, m - 1)
            # Column sums must be exactly zero (sum-zero contrast)
            col_sums = np.sum(B, axis=0)
            np.testing.assert_allclose(col_sums, 0.0, atol=1e-14)
            # Orthonormality B^T B = I_{m-1}
            gram = B.T @ B
            np.testing.assert_allclose(gram, np.eye(m - 1), atol=1e-14)

            # Determinism: repeat call yields identical floats
            B_repeat = deterministic_helmert_basis(m)
            assert np.array_equal(B, B_repeat)


def test_class_structure_various_configurations():
    """Verify C^T B = 0 and B^T B = I across diverse class structures, including singletons."""
    test_cases = [
        # (name, class_id, expected_G, expected_d_b)
        ("all_singletons", np.array([0, 1, 2, 3]), 4, 0),
        ("single_homogeneous_class", np.array([0, 0, 0, 0, 0]), 1, 4),
        ("balanced_two_classes", np.array([0, 0, 1, 1]), 2, 2),
        ("mixed_with_singletons", np.array([0, 0, 1, 2, 2, 2, 3]), 4, 3),  # classes 1 and 3 are singletons
        ("unsorted_class_labels", np.array([10, 2, 10, 5, 2, 10]), 3, 3),
    ]

    for name, cls, exp_G, exp_db in test_cases:
        n = len(cls)
        C, B = class_structure(cls)
        assert C.shape == (n, exp_G), f"{name}: C shape mismatch"
        assert B.shape == (n, exp_db), f"{name}: B shape mismatch"

        # C^T B = 0 (orthogonality between class incidence and within-class deviations)
        if exp_db > 0:
            ct_b = C.T @ B
            np.testing.assert_allclose(ct_b, 0.0, atol=1e-14, err_msg=f"{name}: C^T B != 0")
            # B^T B = I
            bt_b = B.T @ B
            np.testing.assert_allclose(bt_b, np.eye(exp_db), atol=1e-14, err_msg=f"{name}: B^T B != I")

        # Full rank identifiability: [C B] must have rank n
        L = np.hstack([C, B])
        assert np.linalg.matrix_rank(L) == n, f"{name}: [C B] is not full rank"


# =====================================================================
# 2. Implied Host Covariance & Pooling Sensitivity
# =====================================================================
def test_implied_host_covariance_closed_form():
    """Verify implied host covariance matches exact theoretical closed form.

    Within class g of size m:
      Var(a_i) = sigma_g^2 + sigma_h^2 * (m-1)/m
      Cov(a_i, a_j) = sigma_g^2 - sigma_h^2 / m
    Across different classes:
      Cov(a_i, a_j) = 0
    """
    class_id = np.array([0, 0, 0, 1, 1])  # Class 0: m=3, Class 1: m=2
    params = EffectParams(sd_g=0.008, sd_h_ratio=0.75, rho_g=0.90, rho_h=0.85)
    cov_a, corr_a = implied_host_covariance(params, class_id, stationary=False)

    sd_g = params.sd_g
    sd_h = params.sd_g * params.sd_h_ratio

    # Class 0 (hosts 0, 1, 2, m=3)
    var_c0 = sd_g ** 2 + sd_h ** 2 * (2.0 / 3.0)
    cov_c0 = sd_g ** 2 - sd_h ** 2 / 3.0
    for i in range(3):
        assert np.isclose(cov_a[i, i], var_c0)
        for j in range(3):
            if i != j:
                assert np.isclose(cov_a[i, j], cov_c0)

    # Class 1 (hosts 3, 4, m=2)
    var_c1 = sd_g ** 2 + sd_h ** 2 * (1.0 / 2.0)
    cov_c1 = sd_g ** 2 - sd_h ** 2 / 2.0
    assert np.isclose(cov_a[3, 3], var_c1)
    assert np.isclose(cov_a[4, 4], var_c1)
    assert np.isclose(cov_a[3, 4], cov_c1)

    # Cross-class covariance must be 0
    for i in range(3):
        for j in (3, 4):
            assert np.isclose(cov_a[i, j], 0.0)


def test_implied_host_covariance_sensitivity():
    """Verify sensitivity to pooling parameter tau = sd_h_ratio.

    tau -> 0: corr -> 1 (complete pooling)
    tau = 1: corr = (m-1)/(2m-1) > 0
    tau = sqrt(m): corr = 0
    tau -> infty: corr -> -1/(m-1)
    """
    m = 3
    # Complete pooling limit
    assert np.isclose(pooling_correlation(0.0001, m), 1.0, atol=1e-3)

    # Unit ratio
    assert np.isclose(pooling_correlation(1.0, m), (m - 1.0) / (2.0 * m - 1.0))  # 2/5 = 0.40

    # Zero correlation point: tau = sqrt(m)
    assert np.isclose(pooling_correlation(np.sqrt(m), m), 0.0, atol=1e-12)

    # Large local variance limit: tau -> inf
    assert np.isclose(pooling_correlation(100.0, m), -1.0 / (m - 1.0), atol=1e-3)  # -0.50


# =====================================================================
# 3. Diagnostic Outputs & Max-Host Risk Semantics
# =====================================================================
def test_diagnostic_outputs_and_host_deviation_zero_sum():
    """Verify class_effects, host_deviations, effect_cov, and host deviations zero-sum property."""
    class_id = np.array([0, 0, 1, 1, 1])
    n = len(class_id)
    T = 80
    t0 = 40
    r = np.random.default_rng(123).normal(0.0, 0.01, size=(T, n))
    r[t0:, 0:2] += 0.05

    adj = Adjusted(
        r=r,
        obs=np.ones((T, n), dtype=bool),
        elig=np.ones(T, dtype=bool),
        U=np.zeros(T),
        lam=np.ones(n),
        sigma=np.full(n, 0.01),
        rm=r.copy(),
        class_id=class_id,
        t0=t0,
        fallback=np.zeros(n, dtype=bool),
        f_hat=np.zeros(T),
        cov_U=np.zeros((T, n, n)),
    )
    nuis = Nuisance(x_center=0.0, class_lambda=[1.0, 1.0], phi_e=[0.4, 0.4], q_e=[0.01, 0.01], v=[0.005, 0.005])
    det = EffectDetector(nuis, EffectParams(kind="hier"))
    out = det.run(adj)

    assert out.class_effects is not None and out.class_effects.shape == (T, 2)
    assert out.host_deviations is not None and out.host_deviations.shape == (T, n)
    assert out.effect_cov is not None and out.effect_cov.shape == (T, n, n)

    C, B = class_structure(class_id)

    for t in range(t0, T):
        # 1. Host deviations must sum to zero within each class
        # Class 0: hosts 0, 1
        assert np.isclose(np.sum(out.host_deviations[t, 0:2]), 0.0, atol=1e-12)
        # Class 1: hosts 2, 3, 4
        assert np.isclose(np.sum(out.host_deviations[t, 2:5]), 0.0, atol=1e-12)

        # 2. Effect means must match C theta + B b
        expected_am = C @ out.class_effects[t] + out.host_deviations[t]
        np.testing.assert_allclose(out.host_score[t], expected_am, atol=1e-12)

        # 3. Effect covariance must be positive-definite
        eigvals = np.linalg.eigvalsh(out.effect_cov[t])
        assert np.all(eigvals > 0.0)

        # 4. Release score is max-host risk: score = max_i log(prob_i)
        expected_score = np.nanmax(np.log(out.host_prob[t]))
        assert np.isclose(out.score[t], expected_score)


# =====================================================================
# 4. Four Demonstration Scenarios
# =====================================================================
def test_scenario_1_class_wide_harm():
    """Scenario 1: Hierarchical SSM detects Class 0 harm faster with reduced posterior variance."""
    res = run_scenario_class_wide_harm(seed=42)
    m = res.metrics

    # Variance on Class 0 is reduced in Hierarchical SSM compared to Independent SSM
    assert m["variance_reduction_pct"] > 0.0

    # Class 1 canaries are clean: Hierarchical SSM does not falsely flag them (< 0.10)
    assert m["prob_hier_c1"] < 0.10

    # In contrast, Complete Pooling SSM falsely pulls Class 1 into harm (> 0.50)
    assert m["prob_pooled_c1"] > 0.50


def test_scenario_2_sparse_harm_and_negative_transfer():
    """Scenario 2: Complete Pooling dilutes harm and suffers negative transfer; Hierarchical isolates deviation."""
    res = run_scenario_sparse_harm(seed=42)
    m = res.metrics

    # Harm dilution: Complete pooling dilutes harm by > 2.5x
    assert m["dilution_ratio"] >= 2.5

    # Negative transfer: Clean canaries suffer inflated risk under Complete Pooling vs Hierarchical
    assert m["negative_transfer"] > 0.30

    # Hierarchical detects harmed canary 0
    assert m["harm_detected_hier"] is True

    # Complete pooling misses harmed canary 0 due to dilution
    assert m["harm_detected_pooled"] is False


def test_scenario_3_rack_shock_distinguishability():
    """Scenario 3: Physical rack adjustment absorbs network latency shock; no false release alarms."""
    res = run_scenario_rack_shock(seed=42)
    m = res.metrics

    # Rack adjustment gamma_hat absorbs approximately 0.15 shock
    assert np.isclose(m["shock_absorbed_gamma_hat_mean"], 0.15, atol=0.03)

    # Post-adjustment residual on Canary 0 remains near zero
    assert np.isclose(m["post_adj_residual_canary0_mean"], 0.0, atol=0.01)

    # Clean absorption: none of the detectors alarm
    assert m["absorbed_cleanly"] is True
    assert m["false_alarm_hier"] is False
    assert m["false_alarm_indep"] is False
    assert m["false_alarm_pooled"] is False


def test_scenario_4_recovery_smooth_decay():
    """Scenario 4: Harm onset followed by rollback decays smoothly to zero without hysteresis."""
    res = run_scenario_recovery(seed=42)
    m = res.metrics

    # High probability during harm phase
    assert m["peak_prob_hier"] > 0.95

    # Successful recovery post-rollback
    assert m["decay_successful"] is True
    assert m["recovered_prob_hier"] < 0.10
    assert m["recovered_effect_mean"] < 0.015


def test_diagnostic_traces_csv_artifact(tmp_path):
    """Verify study driver generates valid table_pooling_diagnostic_traces.csv."""
    summary = run(seed=42, output_dir=tmp_path)
    trace_path = Path(summary["trace_file"])
    assert trace_path.exists()
    assert trace_path.stat().st_size > 1000

    import pandas as pd
    df = pd.read_csv(trace_path)
    expected_cols = {
        "scenario", "tick", "t_rollout", "canary_id", "class_id",
        "detector", "raw_obs", "effect_mean", "effect_sd",
        "class_effect", "host_deviation", "risk_prob", "release_score",
        "is_harm_active",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) > 1000
    assert not df["effect_mean"].isna().all()
    assert not df["risk_prob"].isna().all()
