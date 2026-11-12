"""Workload regression + control-derived rank-one factor (handbook Section 5).

One explicit adjustment pipeline:
  c_jt = y_jt - mu_j - beta_j x_t                          (workload-adjusted, all hosts)
  f_hat_t = (lam_C' W_t lam_C)^-1 lam_C' W_t c_C,t          (contemporaneous weighted projection,
                                                             NOT a dynamic-factor Kalman filter)
  r_it = c_it - lam_i f_hat_t                               (canary residual fed to every detector)
Everything per-host is fitted on the PRE-period only; post-period values at time t use data <= t.
"""
from __future__ import annotations

from dataclasses import dataclass

import warnings

import numpy as np

from .schema import Rollout

MIN_PRE_OBS = 60          # below this, canary loading falls back to the class-level value
MIN_CONTROLS_PER_CLASS = 3
MIN_CANARY_FRAC = 0.80


@dataclass
class Adjusted:
    r: np.ndarray            # (T, nc) canary residual; NaN where unusable
    obs: np.ndarray          # (T, nc) bool usable observation
    elig: np.ndarray         # (T,) decision eligible (coverage + freshness rules)
    U: np.ndarray            # (T,) factor-estimation variance (0 for rank zero)
    lam: np.ndarray          # (nc,) canary loadings
    sigma: np.ndarray        # (nc,) pre-period residual SD
    rm: np.ndarray           # (T, nc) matched-contrast residual (workload-adj canary - class-control mean)
    class_id: np.ndarray     # (nc,)
    t0: int
    fallback: np.ndarray     # (nc,) bool, class-level loading used
    f_hat: np.ndarray        # (T,)


def _ols_host(y, x, m):
    """Intercept + slope on masked samples."""
    X = np.column_stack([np.ones(m.sum()), x[m]])
    coef, *_ = np.linalg.lstsq(X, y[m], rcond=None)
    return coef


def host_slopes(roll: Rollout, x_center: float) -> np.ndarray:
    """Per-host pre-period workload slopes (used to build the development-pooled beta)."""
    xc = roll.x - x_center; ok = roll.decision_obs & np.isfinite(roll.y)
    return np.array([_ols_host(roll.y[:roll.t0, h], xc[:roll.t0], ok[:roll.t0, h])[1]
                     if ok[:roll.t0, h].sum() >= 10 else np.nan for h in range(roll.N)])


def adjust(roll: Rollout, x_center: float, class_lambda: np.ndarray, factor_rank: int = 1,
           beta_pooled: float | None = None) -> Adjusted:
    """beta_pooled=None: per-host beta from the rollout pre-period (weak when workload barely varies).
    beta_pooled=float: beta fixed at a development-pooled value; only the intercept is fitted per host."""
    T, N, t0 = roll.T, roll.N, roll.t0
    xc = roll.x - x_center
    ok = roll.decision_obs & np.isfinite(roll.y)
    can, ctl = roll.canary_idx, roll.control_idx
    wadj = np.full((T, N), np.nan)
    for h in range(N):
        m = ok[:t0, h]
        if m.sum() < 10:
            continue
        if beta_pooled is None:
            mu, beta = _ols_host(roll.y[:t0, h], xc[:t0], m)
        else:
            beta = beta_pooled; mu = float(np.mean(roll.y[:t0, h][m] - beta * xc[:t0][m]))
        wadj[:, h] = np.where(ok[:, h], roll.y[:, h] - mu - beta * xc, np.nan)

    nc = len(can)
    cls_c = roll.class_id[can]
    if factor_rank == 0:
        f_hat = np.zeros(T); U = np.zeros(T); lam = np.zeros(nc); fb = np.zeros(nc, bool)
        f_ok = np.ones(T, bool)
    else:
        C = wadj[:, ctl]
        Cp = np.nan_to_num(C[:t0], nan=0.0)                     # missing -> 0 residual (documented)
        u, s, vt = np.linalg.svd(Cp - 0.0, full_matrices=False)
        sc = np.sqrt(max(t0 - 1, 1))
        lamC = s[0] * vt[0] / sc
        if lamC.mean() < 0:                                      # sign convention: mean loading > 0
            lamC = -lamC
        f_pre = Cp @ lamC / max(lamC @ lamC, 1e-12)
        sig2 = np.maximum(np.nanvar(C[:t0] - lamC[None] * f_pre[:, None], axis=0), 1e-8)
        w = np.isfinite(C) / sig2[None]                          # (T, nctl) inverse-variance weights
        den = (w * lamC[None] ** 2).sum(1)
        num = (w * lamC[None] * np.nan_to_num(C)).sum(1)
        f_ok = den > 1e-9
        f_hat = np.where(f_ok, num / np.where(f_ok, den, 1), np.nan)
        U = np.where(f_ok, 1.0 / np.where(f_ok, den, 1), np.nan)
        lam = np.empty(nc); fb = np.zeros(nc, bool)
        fp = f_hat[:t0]
        for k, h in enumerate(can):
            m = np.isfinite(wadj[:t0, h]) & np.isfinite(fp)
            if m.sum() < MIN_PRE_OBS or (fp[m] ** 2).sum() < 1e-8:
                lam[k] = class_lambda[cls_c[k]]; fb[k] = True
            else:
                lam[k] = (fp[m] * wadj[:t0, h][m]).sum() / (fp[m] ** 2).sum()

    r = wadj[:, can] - lam[None] * np.where(np.isfinite(f_hat), f_hat, np.nan)[:, None]
    r = np.where(ok[:, can], r, np.nan)
    obs = np.isfinite(r)
    # --- eligibility: coverage of exposed canaries + >=3 fresh controls per represented class
    frac = obs.mean(1)
    elig = frac >= MIN_CANARY_FRAC
    ctl_ok = np.isfinite(wadj[:, ctl])
    for g in np.unique(cls_c):
        elig &= ctl_ok[:, roll.class_id[ctl] == g].sum(1) >= MIN_CONTROLS_PER_CLASS
    elig &= f_ok
    sigma = np.maximum(np.nanstd(r[:t0], axis=0), 1e-6)
    # --- matched-contrast comparator input: workload-adjusted canary - class-control mean (no factor removal)
    rm = np.full((T, nc), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN control rows are legitimate (ineligible)
        for g in np.unique(cls_c):
            cm = np.nanmean(np.where(ctl_ok[:, roll.class_id[ctl] == g], wadj[:, ctl][:, roll.class_id[ctl] == g], np.nan), axis=1)
            for k in np.flatnonzero(cls_c == g):
                rm[:, k] = wadj[:, can[k]] - cm
    return Adjusted(r, obs, elig, U, lam, sigma, rm, cls_c, t0, fb, f_hat)
