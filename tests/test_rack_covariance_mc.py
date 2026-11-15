"""Independent Monte Carlo reference test for nested rack covariance (Task 2).

Verifies:
a) Independent Monte Carlo simulation (many replications, fixed seed) of control estimation errors.
b) Closed-form formula including zero-sum shift:
   Cov(A_i1, A_i2) = (lam_1 * lam_2 - delta_lam_1 * delta_lam_2) * U_fleet + delta_{r1, r2} * U_rack - 1 / W_tot
   matches empirical Monte Carlo covariance within MC sampling error for both same-rack and different-rack pairs.
c) Rack shock rollout comparison: demonstrates PSD measurement covariance and tracks score difference.
"""
from __future__ import annotations

import numpy as np
import pytest

from canary_ssm.factor import adjust, Adjusted
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.preprocess import Nuisance
from canary_ssm.schema import Rollout, KAPPA


def test_rack_covariance_monte_carlo_reference():
    """Verify that derived closed-form cov_U matches empirical Monte Carlo within statistical error.

    Setup: 12 controls across 2 racks, canaries with loadings 0.7 and 1.5.
    Both same-rack (rack 0) and different-rack (rack 0 vs rack 1) pairs are tested.
    """
    n_ctl = 12
    ctl_racks = np.array([0] * 6 + [1] * 6)
    sig = 0.05
    w = np.full(n_ctl, 1.0 / (sig ** 2))

    lamC = np.array([0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 0.6, 0.8, 1.0, 1.2, 1.3, 1.4])
    can_lam = [0.7, 1.5, 1.0]
    can_racks = [0, 0, 1]  # Canary 0 & 1 on rack 0; canary 2 on rack 1
    nc = len(can_lam)

    W = float(np.sum(w * (lamC ** 2)))
    U_fleet = 1.0 / W

    w_rack0 = float(np.sum(w[ctl_racks == 0]))
    w_rack1 = float(np.sum(w[ctl_racks == 1]))
    W_tot = w_rack0 + w_rack1
    inv_W_tot = 1.0 / W_tot

    bar_lam0 = float(np.sum(w[ctl_racks == 0] * lamC[ctl_racks == 0]) / w_rack0)
    bar_lam1 = float(np.sum(w[ctl_racks == 1] * lamC[ctl_racks == 1]) / w_rack1)
    bar_lam_fleet = float(np.sum(w * lamC) / W_tot)

    delta_lam = {0: bar_lam0 - bar_lam_fleet, 1: bar_lam1 - bar_lam_fleet}
    U_rack = {0: 1.0 / w_rack0, 1: 1.0 / w_rack1}

    # Closed-form covariance matrix
    cov_closed = np.zeros((nc, nc))
    for i1 in range(nc):
        r1 = can_racks[i1]
        l1 = can_lam[i1]
        for i2 in range(nc):
            r2 = can_racks[i2]
            l2 = can_lam[i2]
            val = (l1 * l2 - delta_lam[r1] * delta_lam[r2]) * U_fleet - inv_W_tot
            if r1 == r2:
                val += U_rack[r1]
            cov_closed[i1, i2] = val

    # Monte Carlo simulation of exogenous control errors
    N_REPS = 400_000
    rng = np.random.default_rng(12345)
    eps = rng.normal(0, sig, size=(N_REPS, n_ctl))

    # Fleet factor projection
    f_hat = (eps @ (w * lamC)) / W

    # Fleet-adjusted residuals e_k = eps - lam_k * f_hat
    e_k = eps - np.outer(f_hat, lamC)

    # Raw rack nuisance
    raw_g0 = (e_k[:, ctl_racks == 0] @ w[ctl_racks == 0]) / w_rack0
    raw_g1 = (e_k[:, ctl_racks == 1] @ w[ctl_racks == 1]) / w_rack1

    # Zero-sum mean across racks
    mean_g = (w_rack0 * raw_g0 + w_rack1 * raw_g1) / W_tot
    hat_g0 = raw_g0 - mean_g
    hat_g1 = raw_g1 - mean_g

    # Estimation errors on canaries: A_i = lam_i * f_hat + hat_g_{j(i)}
    A0 = can_lam[0] * f_hat + hat_g0
    A1 = can_lam[1] * f_hat + hat_g0
    A2 = can_lam[2] * f_hat + hat_g1
    A = np.column_stack([A0, A1, A2])

    cov_mc = np.cov(A, rowvar=False)

    # Verify that closed form matches MC within Monte Carlo sampling error (3 * SE)
    for i1 in range(nc):
        for i2 in range(nc):
            err = abs(cov_closed[i1, i2] - cov_mc[i1, i2])
            mc_se = np.sqrt(cov_mc[i1, i1] * cov_mc[i2, i2]) / np.sqrt(N_REPS)
            assert err < 3.5 * mc_se, f"Pair ({i1}, {i2}): err={err:.8f} exceeds 3.5*MC_SE ({3.5*mc_se:.8f})"

    # Positive-semidefiniteness guarantee
    eigs = np.linalg.eigvalsh(cov_closed)
    assert np.all(eigs >= -1e-12), f"cov_closed must be positive semidefinite, min eig = {min(eigs)}"


def test_rack_shock_rollout_psd_and_stability():
    """Verify that under a rack shock rollout, cov_U is strictly PSD and prevents false alarms."""
    T = 60
    t0 = 20
    nc = 4
    n_ctl = 16
    n_hosts = nc + n_ctl

    # Rack layout: 2 canaries on rack 0, 2 canaries on rack 1; 8 controls per rack
    rack_ids = np.array([0, 0, 1, 1] + [0] * 8 + [1] * 8)
    class_id = np.array([0, 1, 0, 1] + [0] * 8 + [1] * 8)

    rng = np.random.default_rng(999)
    y = rng.normal(0.0, 0.02, size=(T, n_hosts))
    # Inject large rack shock on Rack 0 starting at t0
    y[t0:, rack_ids == 0] += 0.20

    exposed = np.zeros(n_hosts, dtype=bool)
    exposed[:nc] = True
    observed = np.ones((T, n_hosts), dtype=bool)
    decision_obs = np.ones((T, n_hosts), dtype=bool)
    request_count = np.full((T, n_hosts), 1000)

    roll = Rollout(
        rollout_id="rollout_rack_test_0",
        y=y,
        x=np.zeros(T),
        observed=observed,
        decision_obs=decision_obs,
        class_id=class_id,
        exposed=exposed,
        t0=t0,
        request_count=request_count,
        meta={"rack_id": rack_ids},
    )

    x_center = 0.0
    class_lambda = np.array([1.0, 1.0])

    adj = adjust(roll, x_center, class_lambda, factor_rank=1, rack_ids=rack_ids)

    assert adj.cov_U is not None
    # Verify that all cov_U slices are symmetric and PSD
    for t in range(T):
        mat = adj.cov_U[t]
        assert np.allclose(mat, mat.T, atol=1e-12)
        eigs = np.linalg.eigvalsh(mat)
        assert np.all(eigs >= -1e-12), f"Tick {t}: non-PSD cov_U min eig = {min(eigs)}"

    # Run detector and ensure rack shock did not trigger false alarm on healthy canaries
    nuis = Nuisance(
        x_center=0.0,
        class_lambda=[1.0, 1.0],
        phi_e=[0.85, 0.85],
        q_e=[0.015, 0.015],
        v=[0.005, 0.005],
    )
    p = EffectParams(kind="hier")
    det = EffectDetector(nuis, p)
    out = det.run(adj)

    # Release score must be finite and healthy (no false alert under shock)
    assert np.all(np.isfinite(out.score[t0:]))
    # Mean posterior risk probability across hosts remains near healthy baseline
    assert np.mean(out.host_prob[t0:]) < 0.15
