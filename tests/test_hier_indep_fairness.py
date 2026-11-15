"""Tests for Hierarchical vs Independent fairness (Task 1).

Covers:
a) Opt-in prior_mode: "legacy" (default, bit-identical) vs "ratio_scaled" (P0_b = (prior_sd * sd_h_ratio)^2).
b) Opt-in variance-matched hierarchical config: scale sd_g and sd_h so that diag(Cov(a))
   (prior and process) equals the independent model's, leaving only the correlation structure different.
   Verified with implied_host_covariance and the filter's actual P0/Q against an independent reference.
c) Grids v3: candidate grid with declared sd_h_ratio <= 24 candidates per family after long_run_sd constraint.
d) Deterministic streaming parity under new modes.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from canary_ssm.detector_service import OnlineHierarchicalLatencyFilter
from canary_ssm.factor import Adjusted
from canary_ssm.hierarchy import (
    EffectDetector,
    EffectParams,
    build_model,
    class_structure,
    effect_prior_variance,
    implied_host_covariance,
    long_run_sd,
    pooling_correlation,
)
from canary_ssm.preprocess import Nuisance
from canary_ssm.schema import KAPPA


def _make_dummy_adjusted(n_canaries: int = 4, T: int = 30, t0: int = 10, seed: int = 42) -> Adjusted:
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, 0.02, size=(T, n_canaries))
    obs = np.ones((T, n_canaries), dtype=bool)
    elig = np.ones(T, dtype=bool)
    class_id = np.array([0, 0, 1, 1], dtype=int)
    sigma = np.full(n_canaries, 0.02)
    lam = np.full(n_canaries, 1.0)
    U = np.zeros(T)
    rm = r.copy()
    fallback = np.zeros(n_canaries, dtype=bool)
    f_hat = np.zeros(T)
    return Adjusted(
        r=r, obs=obs, elig=elig, t0=t0, sigma=sigma, lam=lam, U=U, class_id=class_id,
        rm=rm, fallback=fallback, f_hat=f_hat,
    )


def _make_nuisance(n_classes: int = 2) -> Nuisance:
    return Nuisance(
        x_center=0.0,
        class_lambda=[1.0] * n_classes,
        phi_e=[0.85] * n_classes,
        q_e=[0.015] * n_classes,
        v=[0.005] * n_classes,
    )


def test_prior_mode_legacy_bit_identical():
    """Verify legacy prior mode produces bit-identical output to omitting prior_mode."""
    adj = _make_dummy_adjusted()
    nuis = _make_nuisance()

    p_default = EffectParams(kind="hier", sd_g=0.005, sd_h_ratio=0.5, prior_sd=0.03)
    p_legacy = EffectParams(kind="hier", sd_g=0.005, sd_h_ratio=0.5, prior_sd=0.03, prior_mode="legacy")

    out_def = EffectDetector(nuis, p_default).run(adj)
    out_leg = EffectDetector(nuis, p_legacy).run(adj)

    np.testing.assert_array_equal(out_def.score, out_leg.score)
    np.testing.assert_array_equal(out_def.host_score, out_leg.host_score)
    np.testing.assert_array_equal(out_def.host_prob, out_leg.host_prob)
    np.testing.assert_array_equal(out_def.effect_cov, out_leg.effect_cov)


def test_prior_mode_ratio_scaled():
    """Verify prior_mode='ratio_scaled' sets P0_b = (prior_sd * sd_h_ratio)^2 while P0_theta = prior_sd^2."""
    class_id = np.array([0, 0, 1, 1], dtype=int)
    prior_sd = 0.03
    sd_h_ratio = 0.5

    p_scaled = EffectParams(kind="hier", prior_sd=prior_sd, sd_h_ratio=sd_h_ratio, prior_mode="ratio_scaled")
    p0_eff = effect_prior_variance(p_scaled, class_id)

    C, B = class_structure(class_id)
    n_theta = C.shape[1]  # 2 classes
    n_b = B.shape[1]      # 2 deviation states

    # Theta states must have prior variance prior_sd^2
    np.testing.assert_allclose(p0_eff[:n_theta], prior_sd ** 2)
    # b states must have prior variance (prior_sd * sd_h_ratio)^2
    np.testing.assert_allclose(p0_eff[n_theta:], (prior_sd * sd_h_ratio) ** 2)

    # Legacy mode must have prior_sd^2 for ALL states
    p_leg = EffectParams(kind="hier", prior_sd=prior_sd, sd_h_ratio=sd_h_ratio, prior_mode="legacy")
    p0_leg = effect_prior_variance(p_leg, class_id)
    np.testing.assert_allclose(p0_leg, prior_sd ** 2)


def test_variance_matched_implied_host_covariance():
    """Verify that variance_matched mode matches independent model's diag(Cov(a)).

    Under variance-matched mode:
    diag(Cov(a)) must strictly equal sd_g^2 (innovation) or sd_g^2 / (1 - rho_g^2) (stationary)
    for every host, regardless of class size m_g or sd_h_ratio.
    """
    class_id = np.array([0, 0, 0, 1, 1], dtype=int)  # Class 0: m=3, Class 1: m=2
    sd_g = 0.005
    sd_h_ratio = 0.75
    rho_g = 0.95
    rho_h = 0.95

    p_vm = EffectParams(
        kind="hier",
        sd_g=sd_g,
        sd_h_ratio=sd_h_ratio,
        rho_g=rho_g,
        rho_h=rho_h,
        variance_mode="variance_matched",
    )
    p_indep = EffectParams(
        kind="indep",
        sd_g=sd_g,
        rho_g=rho_g,
    )

    # 1. Non-stationary innovation covariance
    cov_vm, corr_vm = implied_host_covariance(p_vm, class_id, stationary=False)
    cov_indep, _ = implied_host_covariance(p_indep, class_id, stationary=False)

    # Marginal host variances must equal independent model's
    np.testing.assert_allclose(np.diag(cov_vm), np.diag(cov_indep))
    np.testing.assert_allclose(np.diag(cov_vm), sd_g ** 2)

    # Within-class correlations must match analytical pooling correlation
    tau = sd_h_ratio
    # Class 0: m=3
    expected_corr_c0 = pooling_correlation(tau, 3)
    for i in range(3):
        for j in range(3):
            if i != j:
                assert np.isclose(corr_vm[i, j], expected_corr_c0)

    # Class 1: m=2
    expected_corr_c1 = pooling_correlation(tau, 2)
    assert np.isclose(corr_vm[3, 4], expected_corr_c1)

    # Cross-class covariance must be zero
    for i in range(3):
        for j in (3, 4):
            assert np.isclose(cov_vm[i, j], 0.0)

    # 2. Stationary covariance
    cov_vm_stat, corr_vm_stat = implied_host_covariance(p_vm, class_id, stationary=True)
    cov_indep_stat, _ = implied_host_covariance(p_indep, class_id, stationary=True)
    np.testing.assert_allclose(np.diag(cov_vm_stat), np.diag(cov_indep_stat))
    np.testing.assert_allclose(np.diag(cov_vm_stat), sd_g ** 2 / (1.0 - rho_g ** 2))


def test_variance_matched_filter_p0_and_q():
    """Verify that filter's actual P0 and Q have host effect marginal variances matching indep."""
    class_id = np.array([0, 0, 1, 1, 1], dtype=int)  # unbalanced classes
    n = len(class_id)
    sd_g = 0.004
    sd_h_ratio = 0.8
    prior_sd = 0.025

    p_vm = EffectParams(
        kind="hier",
        sd_g=sd_g,
        sd_h_ratio=sd_h_ratio,
        prior_sd=prior_sd,
        variance_mode="variance_matched",
    )

    L, rho, sd = build_model(p_vm, class_id)
    p0_eff = effect_prior_variance(p_vm, class_id)

    # Host effect prior covariance: L @ P0_eff @ L.T
    cov_a_prior = L @ np.diag(p0_eff) @ L.T
    np.testing.assert_allclose(np.diag(cov_a_prior), prior_sd ** 2)

    # Host effect innovation covariance: L @ Q_eff @ L.T
    cov_a_proc = L @ np.diag(sd ** 2) @ L.T
    np.testing.assert_allclose(np.diag(cov_a_proc), sd_g ** 2)


def test_streaming_and_batch_parity_under_new_modes():
    """Verify OnlineHierarchicalLatencyFilter matches EffectDetector under variance_matched and ratio_scaled."""
    adj = _make_dummy_adjusted()
    nuis = _make_nuisance()

    p_vm = EffectParams(
        kind="hier",
        sd_g=0.005,
        sd_h_ratio=0.6,
        prior_sd=0.03,
        prior_mode="ratio_scaled",
        variance_mode="variance_matched",
    )

    # Batch run
    batch_out = EffectDetector(nuis, p_vm).run(adj)

    # Streaming run
    flt = OnlineHierarchicalLatencyFilter(
        canary_classes=adj.class_id,
        params=p_vm,
        phi_e=nuis.phi_e,
        q_e=nuis.q_e,
        v_meas=nuis.v,
        kappa=KAPPA,
    )

    for t in range(adj.t0):
        flt.step_preperiod(adj.r[t], adj.obs[t])

    scores = []
    means = []
    for t in range(adj.t0, adj.r.shape[0]):
        am, a_se, c_th, c_th_se, score = flt.step(adj.r[t], adj.obs[t])
        scores.append(score)
        means.append(am)

    streaming_scores = np.array(scores)
    streaming_means = np.array(means)

    np.testing.assert_allclose(streaming_scores, batch_out.score[adj.t0:], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(streaming_means, batch_out.host_score[adj.t0:], rtol=1e-12, atol=1e-12)


def test_grids_v3_budget_parity():
    """Verify configs/grids_v3.yaml enforces <= 24 candidates per family and leaves v2 untouched."""
    from canary_ssm.experiments import load_grids, candidate_grid, DEFAULT_GRID_PATH

    v2_path = DEFAULT_GRID_PATH
    v3_path = v2_path.parent / "grids_v3.yaml"
    assert v3_path.exists(), "configs/grids_v3.yaml must exist"

    g2 = load_grids(v2_path)
    assert g2.get("version") == "v2.0"

    g3 = load_grids(v3_path)
    assert g3.get("version") == "v3.0"

    # Verify sd_h_ratio is varied in ssm
    assert len(g3["ssm"]["sd_h_ratio"]) > 1

    methods_to_check = [
        "hier_ssm", "indep_ssm", "pooled_ssm",
        "adj_cusum", "adj_ewma", "topk_cusum", "matched_contrast",
        "wmean", "ar_cusum", "glr_window", "sparse_mix_glr",
        "bocpd", "msprt", "mw_judge", "hier_no_persist", "hier_rw",
    ]

    for m in methods_to_check:
        cands = candidate_grid(m, g3)
        assert len(cands) <= 24, f"Method {m} has {len(cands)} candidates in grids_v3, expected <= 24"
        assert len(cands) > 0, f"Method {m} has 0 candidates in grids_v3"
