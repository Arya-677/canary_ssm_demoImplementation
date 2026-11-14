"""Hypothesis property-based tests for KalmanFilter (WP-I3)."""
from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from canary_ssm.kalman import KalmanFilter


def _stable_kf(n: int, rng: np.random.Generator) -> KalmanFilter:
    A = rng.normal(0, 0.2, (n, n))
    F = 0.5 * A / max(1.0, np.linalg.norm(A, 2))
    Q = 0.05 * np.eye(n)
    m0 = np.zeros(n)
    P0 = 0.2 * np.eye(n)
    return KalmanFilter(F, Q, m0, P0)


@settings(max_examples=25, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    n=st.integers(2, 6),
    m=st.integers(2, 6),
    steps=st.integers(4, 15),
)
def test_kalman_psd_symmetry_and_invariance(seed, n, m, steps):
    rng = np.random.default_rng(seed)
    kf1 = _stable_kf(n, rng)
    kf2 = kf1.copy()

    H_full = rng.normal(size=(m, n))
    diag_v = rng.uniform(0.05, 0.5, size=m)
    V_full = np.diag(diag_v)

    for _ in range(steps):
        gap = int(rng.integers(1, 3))
        if rng.random() < 0.25:
            # Missing observation -> predict only
            kf1.step(gap=gap)
            kf2.step(gap=gap)
            continue

        k = int(rng.integers(1, m + 1))
        idx = rng.choice(m, size=k, replace=False)
        r_obs = rng.normal(size=k)
        H_obs = H_full[idx]
        V_obs = V_full[np.ix_(idx, idx)]

        # 1. Joint update
        kf1.step(r_obs, H_obs, V_obs, gap=gap)
        w1 = np.linalg.eigvalsh(kf1.P)
        assert np.allclose(kf1.P, kf1.P.T, atol=1e-12)
        assert w1[0] >= -1e-10

        # 2. Observation order invariance + sequential scalar equivalence (diagonal V)
        perm = rng.permutation(k)
        kf_perm = kf2.copy()
        kf_perm.step(r_obs[perm], H_obs[perm], V_obs[np.ix_(perm, perm)], gap=gap)
        assert np.allclose(kf_perm.m, kf1.m, atol=1e-9)
        assert np.allclose(kf_perm.P, kf1.P, atol=1e-9)

        kf2.predict(gap)
        for j in perm:
            kf2.update(r_obs[j:j + 1], H_obs[j:j + 1], V_obs[j:j + 1, j:j + 1])
        assert np.allclose(kf2.m, kf1.m, atol=1e-9)
        assert np.allclose(kf2.P, kf1.P, atol=1e-9)
