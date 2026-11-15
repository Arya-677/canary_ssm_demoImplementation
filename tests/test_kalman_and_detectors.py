"""Tests for generic Kalman engine, multivariate reference agreement, AR noise fitting,
proper effect prior carryover, and unified streaming detector interface with causal parity.

Governing requirements:
1. Cholesky solves, Joseph covariance updates, correlated observation noise, subset observations, exact grid gaps.
2. Match scalar fixture m0=0, P0=1, rho=1, q=0.1, R=0.5:
   y1=1 -> m=0.6875, P=0.34375; y2=1 -> m=126/151, P=71/302.
3. Verify tiny multivariate case against independent direct matrix reference.
4. Fit parsimonious no-effect AR noise on healthy development data; separate AR process noise from measurement uncertainty.
5. Carry preperiod noise state to rollout; initialize proper nonzero effect priors at exposure.
6. Add EWMA, CUSUM, top K CUSUM, independent host SSM and complete pooling SSM behind one update interface.
7. Use consistent adjusted observations and masks; propagate pooled covariance correctly.
8. Keep raw scores separate from thresholds and do not tune on final scenarios.
Exit gate: independent reference agreement, stable covariance, causal streaming parity and hand computed baseline updates.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.linalg import block_diag
from scipy.stats import norm

from canary_ssm.kalman import KalmanFilter, symmetrize
from canary_ssm.detectors import (
    OnlineEWMA,
    OnlineCUSUM,
    OnlineTopKCUSUM,
    OnlineIndependentSSM,
    OnlinePooledSSM,
    OnlineHierarchicalSSM,
    create_streaming_detector,
)
from canary_ssm.baselines import adjusted_ewma, adjusted_cusum, topk_cusum
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.factor import Adjusted
from canary_ssm.preprocess import Nuisance, fit_nuisance, scalar_nll
from canary_ssm.simulate import SimConfig, simulate


# =====================================================================
# 1. Scalar Kalman Fixture Verification
# =====================================================================
def test_kalman_scalar_exact_fixture():
    """Exact test matching prompt scalar fixture:

    m0=0, P0=1, rho=1, q=0.1 (Q=0.1), R=0.5:
      y1=1 -> m=0.6875, P=0.34375
      y2=1 -> m=126/151, P=71/302
    """
    F = np.array([[1.0]])
    Q = np.array([[0.1]])
    m0 = np.array([0.0])
    P0 = np.array([[1.0]])
    H = np.array([[1.0]])
    R = np.array([[0.5]])

    kf = KalmanFilter(F, Q, m0, P0)

    # Step 1: y1 = 1.0
    kf.step(np.array([1.0]), H, R)
    assert np.isclose(kf.m[0], 0.6875, atol=1e-12)
    assert np.isclose(kf.P[0, 0], 0.34375, atol=1e-12)

    # Step 2: y2 = 1.0
    kf.step(np.array([1.0]), H, R)
    assert np.isclose(kf.m[0], 126.0 / 151.0, atol=1e-12)
    assert np.isclose(kf.P[0, 0], 71.0 / 302.0, atol=1e-12)


# =====================================================================
# 2. Independent Multivariate Reference Verification
# =====================================================================
def _independent_multivariate_reference_step(m, P, F, Q, H, V, y):
    """Direct, independent textbook implementation of Kalman step without using KalmanFilter class."""
    # 1. Predict
    m_pred = F @ m
    P_pred = F @ P @ F.T + Q
    if y is None or len(y) == 0:
        return m_pred, 0.5 * (P_pred + P_pred.T)

    # 2. Innovation & Covariance
    v = y - H @ m_pred
    S = H @ P_pred @ H.T + V
    # 3. Kalman Gain (direct solve)
    K = P_pred @ H.T @ np.linalg.inv(S)
    # 4. State Update
    m_upd = m_pred + K @ v
    # 5. Joseph Form Covariance Update: (I - KH) P_pred (I - KH)^T + K V K^T
    I = np.eye(len(m))
    IKH = I - K @ H
    P_upd = IKH @ P_pred @ IKH.T + K @ V @ K.T
    return m_upd, 0.5 * (P_upd + P_upd.T)


def test_tiny_multivariate_independent_reference():
    """Verify 2D state, 2D observation Kalman filter with correlated observation noise against independent equations."""
    F = np.array([[0.9, 0.15],
                  [0.0, 0.85]])
    Q = np.array([[0.05, 0.01],
                  [0.01, 0.03]])
    m0 = np.array([0.5, -0.3])
    P0 = np.array([[1.0, 0.2],
                   [0.2, 0.8]])

    # Correlated observation noise (non-diagonal V)
    H = np.array([[1.0, 0.5],
                  [0.0, 1.0]])
    V = np.array([[0.25, 0.08],
                  [0.08, 0.18]])

    kf = KalmanFilter(F, Q, m0, P0)
    ref_m, ref_P = m0.copy(), P0.copy()

    observations = [
        np.array([1.2, -0.1]),
        np.array([0.8, 0.4]),
        None,  # Missing observation: grid gap predict-only
        np.array([1.5, 0.9]),
    ]

    for step_idx, y in enumerate(observations):
        # Step our KalmanFilter
        if y is not None:
            kf.step(y, H, V)
        else:
            kf.step()

        # Step independent reference
        ref_m, ref_P = _independent_multivariate_reference_step(ref_m, ref_P, F, Q, H, V, y)

        # Numerical agreement to machine precision
        np.testing.assert_allclose(kf.m, ref_m, atol=1e-13, err_msg=f"Mean mismatch at step {step_idx}")
        np.testing.assert_allclose(kf.P, ref_P, atol=1e-13, err_msg=f"Covariance mismatch at step {step_idx}")


# =====================================================================
# 3. Stable Covariance Under Long Gaps & Correlated Observations
# =====================================================================
def test_stable_covariance_long_gaps_and_correlated_obs():
    """Joseph form maintains PSD symmetry and stable positive eigenvalues over 300 steps."""
    rng = np.random.default_rng(42)
    n = 5
    F = 0.98 * np.eye(n)
    Q = 0.001 * np.eye(n)
    m0 = np.zeros(n)
    P0 = np.eye(n)

    # Correlated observation noise
    A = rng.normal(size=(3, 3))
    V = A @ A.T + 0.05 * np.eye(3)
    H = rng.normal(size=(3, n))

    kf = KalmanFilter(F, Q, m0, P0)

    for t in range(300):
        if t % 40 < 20:
            y = rng.normal(size=3)
            kf.step(y, H, V)
        else:
            # Long missing gap: predict only
            kf.step()

        # Check symmetry
        assert np.allclose(kf.P, kf.P.T, atol=1e-12)
        # Check positive eigenvalues
        min_eig = float(np.linalg.eigvalsh(kf.P).min())
        assert min_eig > -1e-10
        assert kf.min_eig_seen > -1e-10


# =====================================================================
# 4. Exact Grid Gap Propagation
# =====================================================================
def test_exact_grid_gap_propagation():
    """Predicting gap k must match k sequential single-interval transitions."""
    F = np.array([[0.88, 0.1], [0.0, 0.92]])
    Q = np.array([[0.04, 0.005], [0.005, 0.02]])
    m0 = np.array([1.5, -0.8])
    P0 = np.array([[0.5, 0.1], [0.1, 0.4]])

    kf_jump = KalmanFilter(F, Q, m0, P0)
    kf_step = KalmanFilter(F, Q, m0, P0)

    # Gap of 5 intervals
    kf_jump.predict(k=5)
    for _ in range(5):
        kf_step.predict(k=1)

    np.testing.assert_allclose(kf_jump.m, kf_step.m, atol=1e-14)
    np.testing.assert_allclose(kf_jump.P, kf_step.P, atol=1e-14)


# =====================================================================
# 5. Parsimonious No-Effect AR Noise Fitting
# =====================================================================
def test_parsimonious_ar_noise_fitting_and_separation():
    """Fit AR noise on simulated healthy rollouts, separating process noise q from measurement noise v."""
    healthy_rollouts = [simulate(SimConfig(), seed=100 + i, harm=False)[0] for i in range(4)]
    nuis = fit_nuisance(healthy_rollouts, factor_rank=1, noise="ar_only")

    # Mode ar_only: pins white SD at V_FLOOR (1e-4) to prevent weak identifiability
    for g, v_val in enumerate(nuis.v):
        assert np.isclose(v_val, 1e-4, atol=1e-6)

    # AR persistence phi_e and innovation q_e must be strictly in bounded statistical ranges
    for g in range(len(nuis.phi_e)):
        assert -0.95 <= nuis.phi_e[g] <= 0.99
        assert 1e-4 <= nuis.q_e[g] <= 0.20


# =====================================================================
# 6. Hand-Computed Baseline Update Fixtures
# =====================================================================
def test_hand_computed_ewma_and_cusum_updates():
    """Verify hand-computed scalar update equations for EWMA and CUSUM."""
    # EWMA hand-calculation:
    # S_0 = 0.0, alpha = 0.2
    # z_1 = 1.0 -> S_1 = 0.2 * 1.0 + 0.8 * 0.0 = 0.20
    # z_2 = 2.0 -> S_2 = 0.2 * 2.0 + 0.8 * 0.2 = 0.40 + 0.16 = 0.56
    # z_3 = missing -> S_3 = S_2 = 0.56
    ewma = OnlineEWMA(t0=0, n_canaries=1, sigma=np.array([1.0]), alpha=0.2)
    ewma._pre_scale_computed = True
    ewma._scale = np.array([1.0])

    r1 = ewma.step(0, np.array([1.0]), np.array([True]))
    assert np.isclose(r1.host_scores[0], 0.20)

    r2 = ewma.step(1, np.array([2.0]), np.array([True]))
    assert np.isclose(r2.host_scores[0], 0.56)

    r3 = ewma.step(2, np.array([99.0]), np.array([False]))  # unobserved
    assert np.isclose(r3.host_scores[0], 0.56)

    # CUSUM hand-calculation:
    # C_0 = 0.0, k = 0.25
    # z_1 = 1.0  -> C_1 = max(0, 0 + 1.0 - 0.25) = 0.75
    # z_2 = -0.5 -> C_2 = max(0, 0.75 - 0.5 - 0.25) = 0.00
    # z_3 = 2.0  -> C_3 = max(0, 0 + 2.0 - 0.25) = 1.75
    # z_4 = missing -> C_4 = C_3 = 1.75
    cusum = OnlineCUSUM(t0=0, n_canaries=1, sigma=np.array([1.0]), k=0.25)
    c1 = cusum.step(0, np.array([1.0]), np.array([True]))
    assert np.isclose(c1.host_scores[0], 0.75)

    c2 = cusum.step(1, np.array([-0.5]), np.array([True]))
    assert np.isclose(c2.host_scores[0], 0.00)

    c3 = cusum.step(2, np.array([2.0]), np.array([True]))
    assert np.isclose(c3.host_scores[0], 1.75)

    c4 = cusum.step(3, np.array([99.0]), np.array([False]))
    assert np.isclose(c4.host_scores[0], 1.75)


def test_hand_computed_topk_cusum():
    """Verify Top-K CUSUM sums exactly the top K host accumulators."""
    # 4 hosts: C = [1.5, 0.5, 2.0, 0.0], K = 2
    # Top 2 are 2.0 and 1.5 -> sum = 3.5
    topk = OnlineTopKCUSUM(t0=0, n_canaries=4, sigma=np.ones(4), K=2, k=0.0)
    # Feed residuals directly
    res = topk.step(0, np.array([1.5, 0.5, 2.0, 0.0]), np.ones(4, bool))
    assert np.isclose(res.score, 3.50)


# =====================================================================
# 7. Causal Streaming Parity (Streaming vs Batch Parity)
# =====================================================================
@pytest.fixture(scope="module")
def sample_rollout_and_nuisance():
    healthy = [simulate(SimConfig(), seed=50 + i, harm=False)[0] for i in range(3)]
    nuis = fit_nuisance(healthy, factor_rank=1, noise="ar_only")
    harm_roll, _ = simulate(SimConfig(), seed=777, harm=True)
    from canary_ssm.factor import adjust
    adj = adjust(harm_roll, nuis.x_center, np.array(nuis.class_lambda))
    return adj, nuis


def test_causal_streaming_parity_ewma(sample_rollout_and_nuisance):
    """OnlineEWMA tick-by-tick step() matches adjusted_ewma(adj) batch run."""
    adj, _ = sample_rollout_and_nuisance
    batch_out = adjusted_ewma(adj, alpha=0.2)

    online_det = OnlineEWMA(t0=adj.t0, n_canaries=adj.r.shape[1], sigma=adj.sigma, alpha=0.2)
    stream_out = online_det.run(adj)

    np.testing.assert_allclose(batch_out.score, stream_out.score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_score, stream_out.host_score, equal_nan=True, atol=1e-12)


def test_causal_streaming_parity_cusum(sample_rollout_and_nuisance):
    """OnlineCUSUM tick-by-tick step() matches adjusted_cusum(adj) batch run."""
    adj, _ = sample_rollout_and_nuisance
    batch_out = adjusted_cusum(adj, k=0.25)

    online_det = OnlineCUSUM(t0=adj.t0, n_canaries=adj.r.shape[1], sigma=adj.sigma, k=0.25)
    stream_out = online_det.run(adj)

    np.testing.assert_allclose(batch_out.score, stream_out.score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_score, stream_out.host_score, equal_nan=True, atol=1e-12)


def test_causal_streaming_parity_topk_cusum(sample_rollout_and_nuisance):
    """OnlineTopKCUSUM tick-by-tick step() matches topk_cusum(adj) batch run."""
    adj, _ = sample_rollout_and_nuisance
    batch_out = topk_cusum(adj, K=3, k=0.25)

    online_det = OnlineTopKCUSUM(t0=adj.t0, n_canaries=adj.r.shape[1], sigma=adj.sigma, K=3, k=0.25)
    stream_out = online_det.run(adj)

    np.testing.assert_allclose(batch_out.score, stream_out.score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_score, stream_out.host_score, equal_nan=True, atol=1e-12)


def test_causal_streaming_parity_independent_ssm(sample_rollout_and_nuisance):
    """OnlineIndependentSSM step() matches EffectDetector(kind='indep') batch run."""
    adj, nuis = sample_rollout_and_nuisance
    params = EffectParams(kind="indep")
    batch_out = EffectDetector(nuis, params).run(adj)

    online_det = OnlineIndependentSSM(
        nuis=nuis,
        params=params,
        t0=adj.t0,
        class_id=adj.class_id,
        lam=adj.lam,
        sigma=adj.sigma,
    )
    stream_out = online_det.run(adj)

    np.testing.assert_allclose(batch_out.score, stream_out.score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_score, stream_out.host_score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_prob, stream_out.host_prob, equal_nan=True, atol=1e-12)


def test_causal_streaming_parity_pooled_ssm(sample_rollout_and_nuisance):
    """OnlinePooledSSM step() matches EffectDetector(kind='pooled') batch run."""
    adj, nuis = sample_rollout_and_nuisance
    params = EffectParams(kind="pooled")
    batch_out = EffectDetector(nuis, params).run(adj)

    online_det = OnlinePooledSSM(
        nuis=nuis,
        params=params,
        t0=adj.t0,
        class_id=adj.class_id,
        lam=adj.lam,
        sigma=adj.sigma,
    )
    stream_out = online_det.run(adj)

    np.testing.assert_allclose(batch_out.score, stream_out.score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_score, stream_out.host_score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_prob, stream_out.host_prob, equal_nan=True, atol=1e-12)


def test_causal_streaming_parity_hierarchical_ssm(sample_rollout_and_nuisance):
    """OnlineHierarchicalSSM step() matches EffectDetector(kind='hier') batch run."""
    adj, nuis = sample_rollout_and_nuisance
    params = EffectParams(kind="hier")
    batch_out = EffectDetector(nuis, params).run(adj)

    online_det = OnlineHierarchicalSSM(
        nuis=nuis,
        params=params,
        t0=adj.t0,
        class_id=adj.class_id,
        lam=adj.lam,
        sigma=adj.sigma,
    )
    stream_out = online_det.run(adj)

    np.testing.assert_allclose(batch_out.score, stream_out.score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_score, stream_out.host_score, equal_nan=True, atol=1e-12)
    np.testing.assert_allclose(batch_out.host_prob, stream_out.host_prob, equal_nan=True, atol=1e-12)


# =====================================================================
# 8. Correct Pooled Covariance Propagation
# =====================================================================
def test_pooled_ssm_covariance_shrinks_with_sample_size(sample_rollout_and_nuisance):
    """Complete pooling SSM pools all observed canaries; posterior variance of theta shrinks as 1/n."""
    _, nuis = sample_rollout_and_nuisance
    params = EffectParams(kind="pooled", prior_sd=0.05)

    # Compare 1 canary vs 10 canaries under same measurement noise
    det_1 = OnlinePooledSSM(nuis, params, t0=0, class_id=np.array([0]), lam=np.ones(1), sigma=np.ones(1))
    det_10 = OnlinePooledSSM(nuis, params, t0=0, class_id=np.zeros(10, int), lam=np.ones(10), sigma=np.ones(10))

    # Single update with observed residual 0.05
    det_1.step(0, np.array([0.05]), np.array([True]))
    det_10.step(0, np.full(10, 0.05), np.ones(10, bool))

    # Posterior variance for theta in det_10 must be strictly smaller than det_1
    var_1 = det_1.kf.P[0, 0]
    var_10 = det_10.kf.P[0, 0]

    assert var_10 < var_1
    # Ratio should be approximately ~ 10x smaller
    assert var_10 < 0.25 * var_1


# =====================================================================
# 9. Factory Function Verification
# =====================================================================
def test_create_streaming_detector_factory(sample_rollout_and_nuisance):
    """create_streaming_detector correctly instantiates all supported detector types."""
    adj, nuis = sample_rollout_and_nuisance
    nc = len(adj.class_id)

    ewma = create_streaming_detector("adj_ewma", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma)
    assert isinstance(ewma, OnlineEWMA)

    cusum = create_streaming_detector("adj_cusum", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma)
    assert isinstance(cusum, OnlineCUSUM)

    topk = create_streaming_detector("topk_cusum", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma, K=3)
    assert isinstance(topk, OnlineTopKCUSUM)

    indep = create_streaming_detector("indep_ssm", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma, nuis=nuis)
    assert isinstance(indep, OnlineIndependentSSM)

    pooled = create_streaming_detector("pooled_ssm", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma, nuis=nuis)
    assert isinstance(pooled, OnlinePooledSSM)

    hier = create_streaming_detector("hier_ssm", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma, nuis=nuis)
    assert isinstance(hier, OnlineHierarchicalSSM)

    with pytest.raises(ValueError, match="Unknown detector name"):
        create_streaming_detector("unknown_magic_detector", t0=adj.t0, class_id=adj.class_id, sigma=adj.sigma)
