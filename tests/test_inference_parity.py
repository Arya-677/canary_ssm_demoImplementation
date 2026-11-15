"""Deterministic parity test between batch EffectDetector and streaming OnlineHierarchicalLatencyFilter.

Verifies bit-for-bit numerical parity across:
- State definitions, transitions, and process noise matrices.
- Pre-period noise Kalman filter conditioning carried forward at t0.
- Observation and measurement-noise handling (including shared covariance cov_U).
- Missing observations (predict-only steps).
- Posterior effect means, standard errors, class effects, and log release scores.
"""
from __future__ import annotations

import numpy as np
import pytest

from canary_ssm.detector_service import OnlineHierarchicalLatencyFilter
from canary_ssm.factor import Adjusted
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.preprocess import Nuisance
from canary_ssm.schema import KAPPA


@pytest.fixture
def synthetic_experiment():
    """Deterministic synthetic rollout with pre-period, rollout, and missingness."""
    np.random.seed(42)
    n_canaries = 4
    canary_classes = np.array([0, 0, 1, 1], dtype=int)
    canary_ids = [f"srv-r{i}-s0" for i in range(n_canaries)]
    t0 = 20
    T = 50

    # Nuisance parameters
    phi_e = [0.80, 0.85]
    q_e = [0.012, 0.015]
    v = [0.004, 0.005]
    nuis = Nuisance(
        x_center=4.5,
        class_lambda=[1.0, 1.0],
        phi_e=phi_e,
        q_e=q_e,
        v=v,
    )

    # Synthetic residuals: shape (T, nc)
    R = np.random.normal(0.0, 0.02, size=(T, n_canaries))
    # Add true effect after t0 on canaries
    R[t0:, :] += 0.025

    # Observation masks: simulate some missing ticks
    obs = np.ones((T, n_canaries), dtype=bool)
    obs[10, :] = False         # Pre-period completely missing tick
    obs[25, 1] = False         # Rollout single host missing
    obs[35, :] = False         # Rollout completely missing tick

    elig = np.ones(T, dtype=bool)
    elig[10] = False
    elig[35] = False

    # Synthetic shared estimation covariance: shape (T, nc, nc)
    cov_U = np.zeros((T, n_canaries, n_canaries), dtype=float)
    for t in range(T):
        u_val = 0.0001 * (1.0 + np.sin(t))
        cov_U[t] = np.full((n_canaries, n_canaries), u_val)

    adj = Adjusted(
        r=R,
        obs=obs,
        elig=elig,
        U=np.zeros(T),
        lam=np.ones(n_canaries),
        sigma=np.full(n_canaries, 0.02),
        rm=R.copy(),
        class_id=canary_classes,
        t0=t0,
        fallback=np.zeros(n_canaries, dtype=bool),
        f_hat=np.zeros(T),
        cov_U=cov_U,
    )

    return {
        "canary_ids": canary_ids,
        "canary_classes": canary_classes,
        "nuis": nuis,
        "adj": adj,
        "t0": t0,
        "T": T,
        "phi_e": phi_e,
        "q_e": q_e,
        "v": v,
    }


@pytest.mark.parametrize("kind", ["hier", "indep", "pooled"])
def test_streaming_batch_deterministic_parity(synthetic_experiment, kind):
    """Enforce strict numerical agreement (tol <= 1e-10) between batch and streaming inference."""
    data = synthetic_experiment
    adj = data["adj"]
    t0 = data["t0"]
    T = data["T"]
    nuis = data["nuis"]
    canary_classes = data["canary_classes"]
    canary_ids = data["canary_ids"]

    effect_params = EffectParams(
        kind=kind,
        rho_g=0.95,
        rho_h=0.95,
        sd_g=0.005,
        sd_h_ratio=1.0,
        prior_sd=0.03,
    )

    # 1. Run batch EffectDetector
    batch_detector = EffectDetector(
        nuis=nuis,
        params=effect_params,
        class_override=canary_classes,
        kappa=float(KAPPA),
    )
    batch_out = batch_detector.run(adj)

    # 2. Run streaming OnlineHierarchicalLatencyFilter
    stream_filter = OnlineHierarchicalLatencyFilter(
        canary_ids=canary_ids,
        canary_classes=canary_classes,
        params=effect_params,
        phi_e=nuis.phi_e,
        q_e=nuis.q_e,
        v_meas=nuis.v,
        kappa=float(KAPPA),
    )

    # Condition pre-period
    for t in range(t0):
        use = adj.obs[t] & adj.elig[t]
        stream_filter.step_preperiod(
            r_latency=adj.r[t] if use.any() else None,
            obs_mask=use,
            cov_U=adj.cov_U[t] if use.any() else None,
        )

    stream_filter.initialize_rollout()

    # Step through rollout ticks and compare
    for t in range(t0, T):
        use = adj.obs[t] & adj.elig[t]
        a_hat, a_se, cls_thetas, cls_thetas_se, log_score = stream_filter.step(
            r_latency=adj.r[t] if use.any() else None,
            obs_mask=use,
            cov_U=adj.cov_U[t] if use.any() else None,
        )

        expected_mean = batch_out.host_score[t]
        expected_score = batch_out.score[t]
        expected_prob = batch_out.host_prob[t]
        expected_cov = batch_out.effect_cov[t]
        expected_se = np.sqrt(np.diag(expected_cov))

        # Verify host effect mean agreement within machine precision
        np.testing.assert_allclose(
            a_hat,
            expected_mean,
            rtol=1e-10,
            atol=1e-12,
            err_msg=f"Host effect mean mismatch at tick {t} for model {kind}",
        )

        # Verify host effect standard error agreement
        np.testing.assert_allclose(
            a_se,
            expected_se,
            rtol=1e-10,
            atol=1e-12,
            err_msg=f"Host effect standard error mismatch at tick {t} for model {kind}",
        )

        # Verify log release score agreement
        np.testing.assert_allclose(
            log_score,
            expected_score,
            rtol=1e-10,
            atol=1e-12,
            err_msg=f"Release log score mismatch at tick {t} for model {kind}",
        )

        # Verify class effects agreement
        expected_cls = batch_out.class_effects[t]
        np.testing.assert_allclose(
            cls_thetas,
            expected_cls,
            rtol=1e-10,
            atol=1e-12,
            err_msg=f"Class effects mismatch at tick {t} for model {kind}",
        )
