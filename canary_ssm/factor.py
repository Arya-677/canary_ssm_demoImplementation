"""Workload regression + control-derived rank-one factor and nested rack nuisance (handbook Section 5).

One explicit nested adjustment pipeline:
  c_jt = y_jt - mu_j - beta_j x_t                          (workload-adjusted, all hosts)
  f_hat_t = (lam_C' W_t lam_C)^-1 lam_C' W_t c_C,t          (contemporaneous weighted projection)
  gamma_hat_j(t) = mean_{k in C_jt} (c_kt - lam_k f_hat_t)  (rack nuisance orthogonal to fleet factor)
  r_it = c_it - lam_i f_hat_t - gamma_hat_j(t)             (canary residual fed to every detector)

Identifiability & Non-redundancy:
  Rack nuisance gamma_hat_j(t) is estimated strictly on fleet-adjusted control residuals
  e_kt = c_kt - lam_k f_hat_t with a zero-sum constraint across racks (sum_j W_j gamma_hat_j(t) = 0).
  This guarantees that fleet and rack variation are not subtracted twice.

Uncertainty Propagation:
  Shared control estimation error is carried into the residual covariance matrix:
  Cov(A_{i1, t}, A_{i2, t}) = U_{j, t}^{rack} + (lam_{i1} lam_{i2} - bar{lam}_{Cj}^2) U_t^{fleet}  (same rack)
                            = lam_{i1} lam_{i2} U_t^{fleet}                                         (different racks)
"""
from __future__ import annotations

from dataclasses import dataclass
import warnings
import numpy as np

from .schema import Rollout

MIN_PRE_OBS = 60          # below this, canary loading falls back to the class-level value
MIN_CONTROLS_PER_CLASS = 3
MIN_CONTROLS_PER_RACK = 3
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
    ctl_r: np.ndarray | None = None          # (T, nctl) factor- & workload-adjusted control residuals
    ctl_class_id: np.ndarray | None = None   # (nctl,) control class IDs
    gamma_hat: np.ndarray | None = None      # (T, n_racks) rack nuisance estimates
    U_rack: np.ndarray | None = None         # (T, n_racks) rack nuisance estimation variances
    cov_U: np.ndarray | None = None          # (T, nc, nc) full shared estimation covariance
    rack_id: np.ndarray | None = None        # (nc,) canary rack IDs
    ctl_rack_id: np.ndarray | None = None    # (nctl,) control rack IDs
    elig_reasons: list[list[str]] | None = None # (T,) per-tick ineligibility reasons


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
           beta_pooled: float | None = None, min_controls_per_rack: int = MIN_CONTROLS_PER_RACK,
           rack_ids: np.ndarray | list | None = None) -> Adjusted:
    """The ONE adjustment entry point: honours the nuisance object's beta mode and factor rank.

    If rack_ids is provided (or stored in roll.meta['rack_id'] / ['rack_ids']), performs nested
    rack-nuisance adjustment and evaluates per-rack control coverage.
    """
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
        lamC = np.zeros(len(ctl))
        sig2 = np.ones(len(ctl))
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

    # --- Check for Rack IDs
    if rack_ids is None:
        if "rack_ids" in roll.meta:
            rack_ids = roll.meta["rack_ids"]
        elif "rack_id" in roll.meta:
            rack_ids = roll.meta["rack_id"]

    has_racks = rack_ids is not None
    gamma_hat_arr = None
    U_rack_arr = None
    cov_U_arr = None
    can_racks = None
    ctl_racks = None
    elig_reasons = [[] for _ in range(T)]

    if has_racks:
        all_racks = np.asarray(rack_ids)
        can_racks = all_racks[can]
        ctl_racks = all_racks[ctl]
        unique_racks = np.unique(all_racks)
        n_racks = len(unique_racks)
        rack_to_idx = {rk: i for i, rk in enumerate(unique_racks)}
        can_rack_indices = np.array([rack_to_idx[rk] for rk in can_racks])

        gamma_hat_arr = np.zeros((T, n_racks))
        U_rack_arr = np.zeros((T, n_racks))
        cov_U_arr = np.zeros((T, nc, nc))

        ctl_ok = np.isfinite(wadj[:, ctl])

        for t in range(T):
            raw_gamma = np.zeros(n_racks)
            w_rack = np.zeros(n_racks)
            f_val = f_hat[t] if np.isfinite(f_hat[t]) else 0.0
            u_f = U[t] if np.isfinite(U[t]) else 0.0

            for rk_i, rk in enumerate(unique_racks):
                rk_ctl_mask = (ctl_racks == rk) & ctl_ok[t]
                if rk_ctl_mask.any():
                    ctl_pos = np.flatnonzero(rk_ctl_mask)
                    w_k = 1.0 / sig2[ctl_pos]
                    w_sum = float(w_k.sum())
                    if w_sum > 1e-9:
                        e_kt = wadj[t, ctl[ctl_pos]] - lamC[ctl_pos] * f_val
                        raw_gamma[rk_i] = float((w_k * e_kt).sum() / w_sum)
                        w_rack[rk_i] = w_sum
                        U_rack_arr[t, rk_i] = 1.0 / w_sum

            # Zero-sum identifiability across racks: sum_j W_j gamma_hat_j = 0
            w_tot = float(w_rack.sum())
            mean_g = float((w_rack * raw_gamma).sum() / w_tot) if w_tot > 1e-9 else 0.0
            for rk_i in range(n_racks):
                if w_rack[rk_i] > 0:
                    gamma_hat_arr[t, rk_i] = raw_gamma[rk_i] - mean_g

            # Build full estimation error covariance matrix for canaries (exact closed-form)
            bar_lam_rack = np.zeros(n_racks)
            for rk_i, rk in enumerate(unique_racks):
                rk_ctl_mask = (ctl_racks == rk) & ctl_ok[t]
                if rk_ctl_mask.any() and w_rack[rk_i] > 1e-9:
                    ctl_pos = np.flatnonzero(rk_ctl_mask)
                    bar_lam_rack[rk_i] = float(((1.0 / sig2[ctl_pos]) * lamC[ctl_pos]).sum() / w_rack[rk_i])
                else:
                    bar_lam_rack[rk_i] = 1.0

            bar_lam_fleet = float((w_rack * bar_lam_rack).sum() / w_tot) if w_tot > 1e-9 else 1.0
            delta_lam = bar_lam_rack - bar_lam_fleet
            inv_w_tot = (1.0 / w_tot) if w_tot > 1e-9 else 0.0

            for i1 in range(nc):
                rk_idx1 = can_rack_indices[i1]
                lam1 = lam[i1]
                d_lam1 = delta_lam[rk_idx1]

                for i2 in range(nc):
                    rk_idx2 = can_rack_indices[i2]
                    lam2 = lam[i2]
                    d_lam2 = delta_lam[rk_idx2]

                    c_val = (lam1 * lam2 - d_lam1 * d_lam2) * u_f - inv_w_tot
                    if rk_idx1 == rk_idx2:
                        c_val += U_rack_arr[t, rk_idx1]
                    cov_U_arr[t, i1, i2] = c_val

                cov_U_arr[t, i1, i1] = max(cov_U_arr[t, i1, i1], 0.0)
            cov_U_arr[t] = 0.5 * (cov_U_arr[t] + cov_U_arr[t].T)

        # Subtract both fleet factor and rack nuisance
        g_for_can = np.array([gamma_hat_arr[:, rack_to_idx[rk]] for rk in can_racks]).T
        r = wadj[:, can] - lam[None] * np.where(np.isfinite(f_hat), f_hat, np.nan)[:, None] - g_for_can
    else:
        r = wadj[:, can] - lam[None] * np.where(np.isfinite(f_hat), f_hat, np.nan)[:, None]

    r = np.where(ok[:, can], r, np.nan)
    obs = np.isfinite(r)

    # --- eligibility: coverage of exposed canaries + >=3 fresh controls per represented class + rack
    frac = obs.mean(1)
    elig = frac >= MIN_CANARY_FRAC
    ctl_ok = np.isfinite(wadj[:, ctl])

    for g in np.unique(cls_c):
        cls_count = ctl_ok[:, roll.class_id[ctl] == g].sum(1)
        elig &= cls_count >= MIN_CONTROLS_PER_CLASS
        for t in range(T):
            if cls_count[t] < MIN_CONTROLS_PER_CLASS:
                elig_reasons[t].append(f"INSUFFICIENT_CLASS_CONTROLS: class {g} has {cls_count[t]} < {MIN_CONTROLS_PER_CLASS}")

    if has_racks and can_racks is not None:
        for rk in np.unique(can_racks):
            rk_mask = (ctl_racks == rk)
            rk_count = (ctl_ok & rk_mask[None, :]).sum(1)
            elig &= rk_count >= min_controls_per_rack
            for t in range(T):
                if rk_count[t] < min_controls_per_rack:
                    elig_reasons[t].append(f"INSUFFICIENT_RACK_CONTROLS: rack {rk} has {rk_count[t]} < {min_controls_per_rack}")

    for t in range(T):
        if frac[t] < MIN_CANARY_FRAC:
            elig_reasons[t].append(f"INSUFFICIENT_CANARY_COVERAGE: {frac[t]:.1%} < {MIN_CANARY_FRAC:.1%}")
        if not f_ok[t]:
            elig_reasons[t].append("FLEET_FACTOR_INSUFFICIENT_CONTROLS")

    elig &= f_ok
    sigma = np.maximum(np.nanstd(r[:t0], axis=0), 1e-6)

    # --- matched-contrast comparator input
    rm = np.full((T, nc), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for g in np.unique(cls_c):
            cm = np.nanmean(np.where(ctl_ok[:, roll.class_id[ctl] == g], wadj[:, ctl][:, roll.class_id[ctl] == g], np.nan), axis=1)
            for k in np.flatnonzero(cls_c == g):
                rm[:, k] = wadj[:, can[k]] - cm

    ctl_r = np.where(
        ok[:, ctl],
        wadj[:, ctl] - lamC[None] * np.where(np.isfinite(f_hat), f_hat, np.nan)[:, None],
        np.nan,
    )
    return Adjusted(
        r, obs, elig, U, lam, sigma, rm, cls_c, t0, fb, f_hat,
        ctl_r=ctl_r, ctl_class_id=roll.class_id[ctl],
        gamma_hat=gamma_hat_arr, U_rack=U_rack_arr, cov_U=cov_U_arr,
        rack_id=can_racks, ctl_rack_id=ctl_racks, elig_reasons=elig_reasons,
    )
