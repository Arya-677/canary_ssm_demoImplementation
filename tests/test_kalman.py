import numpy as np
import pytest

from canary_ssm.kalman import KalmanFilter


def test_scalar_fixture():
    kf = KalmanFilter(np.eye(1), np.array([[0.1]]), np.zeros(1), np.eye(1))
    I, R = np.eye(1), np.array([[0.5]])
    kf.step(np.array([1.0]), I, R)
    assert np.isclose(kf.m[0], 0.6875) and np.isclose(kf.P[0, 0], 0.34375)
    kf.step(np.array([1.0]), I, R)
    assert np.isclose(kf.m[0], 126 / 151) and np.isclose(kf.P[0, 0], 71 / 302)


def test_matches_statsmodels_with_missing():
    sm = pytest.importorskip("statsmodels.tsa.statespace.kalman_filter")
    rng = np.random.default_rng(0)
    F = np.array([[0.9, 0.1, 0], [0, 0.7, 0.2], [0, 0, 0.5]]); Q = np.diag([0.1, 0.05, 0.02])
    H = rng.normal(size=(2, 3)); V = np.array([[0.3, 0.1], [0.1, 0.2]])
    m0, P0 = np.array([0.1, -0.2, 0.3]), np.eye(3)
    T = 40; y = rng.normal(size=(T, 2)); y[5, 0] = np.nan; y[6] = np.nan; y[20:25, 1] = np.nan
    skf = sm.KalmanFilter(k_endog=2, k_states=3, k_posdef=3)
    skf["design"], skf["transition"], skf["state_cov"], skf["obs_cov"] = H, F, Q, V
    skf["selection"] = np.eye(3)
    skf.initialize_known(F @ m0, F @ P0 @ F.T + Q)         # statsmodels init = predicted state for t=0
    skf.bind(y); res = skf.filter()
    kf = KalmanFilter(F, Q, m0, P0)
    for t in range(T):
        idx = np.flatnonzero(np.isfinite(y[t]))
        kf.step(y[t, idx] if idx.size else None, H[idx], V[np.ix_(idx, idx)]) if idx.size else kf.step()
        assert np.allclose(kf.m, res.filtered_state[:, t], atol=1e-8), t
        assert np.allclose(kf.P, res.filtered_state_cov[:, :, t], atol=1e-8), t


def test_joseph_stays_psd_over_long_gaps_and_correlated_obs():
    rng = np.random.default_rng(1)
    n = 6; F = 0.97 * np.eye(n); Q = 1e-4 * np.eye(n)
    H = rng.normal(size=(4, n)); A = rng.normal(size=(4, 4)); V = A @ A.T + 0.1 * np.eye(4)
    kf = KalmanFilter(F, Q, np.zeros(n), np.eye(n))
    for t in range(300):
        if t % 50 < 30:
            kf.step(rng.normal(size=4), H, V)
        else:
            kf.step()                                        # long gap = repeated transitions
        assert np.allclose(kf.P, kf.P.T) and np.linalg.eigvalsh(kf.P).min() > -1e-10


def test_gap_applies_k_transitions():
    a = KalmanFilter(0.9 * np.eye(1), np.eye(1) * 0.1, np.ones(1), np.eye(1)); b = a.copy()
    a.predict(3)
    for _ in range(3):
        b.predict(1)
    assert np.allclose(a.m, b.m) and np.allclose(a.P, b.P)
