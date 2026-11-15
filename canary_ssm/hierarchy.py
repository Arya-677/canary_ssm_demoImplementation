"""Independent / complete-pooling / hierarchical effect state-space detectors (handbook Section 7).

State s = [effect (d), AR noise e (n)];  r_t = L s_eff + e_t + nu_t,   nu ~ N(0, V_t)
  hierarchical: a = C theta + B b, B = block-diagonal orthonormal sum-zero basis per class
  independent : a = I theta       (one effect state per canary, no pooling)
  pooled      : a = 1 theta       (one release effect)
V_t = diag(v_g^2) + lam lam' U_t   (white noise + shared factor-estimation error)
Release score = log max_i Pr(a_i > kappa | data <= t) (monotone in max-host risk; avoids underflow). It is a SCORE,
not Pr(any host harmful); its threshold is calibrated empirically in decision.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import numpy as np
from scipy.linalg import block_diag
from scipy.stats import norm

from .baselines import DetectorOutput
from .factor import Adjusted
from .kalman import KalmanFilter, symmetrize
from .preprocess import Nuisance
from .schema import KAPPA


@dataclass
class EffectParams:
    kind: str = "hier"            # hier | indep | pooled
    rho_g: float = 0.95
    rho_h: float = 0.95
    sd_g: float = 0.005           # effect innovation SD (log units / minute)
    sd_h_ratio: float = 1.0       # local-deviation SD relative to sd_g
    prior_sd: float = 0.03        # proper effect prior SD at rollout onset
    huber_c: float = 0.0          # >0: winsorise residuals at +-c pre-period SDs (heavy-tail robustness)
    prior_mode: str = "legacy"    # legacy | ratio_scaled
    variance_mode: str = "legacy" # legacy | matched | variance_matched


def long_run_sd(p: "EffectParams") -> float:
    """Stationary SD of the effect state(s). Handoff audit: keep it below kappa or healthy data cross risk 0.5."""
    f = lambda sd, rho: float("inf") if abs(rho) >= 1 else sd / np.sqrt(1 - rho ** 2)
    return max(f(p.sd_g, p.rho_g), f(p.sd_g * p.sd_h_ratio, p.rho_h) if p.kind == "hier" else 0.0)


def deterministic_helmert_basis(m: int) -> np.ndarray:
    """Deterministic orthonormal sum-zero basis for R^m (Helmert contrast matrix).

    Returns an (m, m - 1) matrix B such that:
    - 1^T B = 0 (each column sums to zero)
    - B^T B = I_{m-1} (orthonormal columns)
    For m <= 1, returns array of shape (m, 0).
    """
    if m <= 1:
        return np.zeros((m, 0), dtype=float)
    B = np.zeros((m, m - 1), dtype=float)
    for k in range(1, m):
        denom = np.sqrt(k * (k + 1))
        B[:k, k - 1] = 1.0 / denom
        B[k, k - 1] = -float(k) / denom
    return B


def class_structure(class_id: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """C (n x G), B (n x (n-G)) block-diag deterministic orthonormal sum-zero basis.
    
    Singleton classes add no column to B (m=1 -> 0 columns).
    Guarantees:
    - C^T B = 0 (deviations sum to zero within every class)
    - B^T B = I_{n-G} (orthonormal basis)
    """
    classes = np.unique(class_id)
    n = len(class_id)
    C = np.zeros((n, len(classes)), dtype=float)
    blocks = []
    for j, g in enumerate(classes):
        idx = np.flatnonzero(class_id == g)
        C[idx, j] = 1.0
        m = len(idx)
        if m > 1:
            Bg = np.zeros((n, m - 1), dtype=float)
            Bg[idx] = deterministic_helmert_basis(m)
            blocks.append(Bg)
    B = np.hstack(blocks) if blocks else np.zeros((n, 0), dtype=float)
    return C, B


def effect_prior_variance(p: EffectParams, class_id: np.ndarray) -> np.ndarray:
    """Return 1D array of prior variances for each effect state in build_model.

    Under legacy mode:
        All effect states have variance prior_sd^2.
    Under ratio_scaled mode (with legacy variance):
        theta states have variance prior_sd^2.
        b deviation states have variance (prior_sd * sd_h_ratio)^2.
    Under variance_matched mode:
        For class g of size m_g:
            c_g^2 = 1.0 / (1.0 + sd_h_ratio^2 * (m_g - 1) / m_g) if m_g > 1 else 1.0
            theta_g has variance c_g^2 * prior_sd^2
            b_g states have variance c_g^2 * (prior_sd * sd_h_ratio)^2
        Guarantees diag(L @ P0_eff @ L^T) == prior_sd^2 for every host.
    """
    class_id = np.asarray(class_id)
    n = len(class_id)
    if p.kind != "hier":
        d = 1 if p.kind == "pooled" else n
        return np.full(d, p.prior_sd ** 2, dtype=float)

    C, B = class_structure(class_id)
    G = C.shape[1]
    n_b = B.shape[1]
    d = G + n_b

    is_vm = p.variance_mode in ("variance_matched", "matched")
    if not is_vm and p.prior_mode == "legacy":
        return np.full(d, p.prior_sd ** 2, dtype=float)

    classes = np.unique(class_id)
    tau = p.sd_h_ratio
    p0_theta = []
    p0_b = []

    for g in classes:
        m = int(np.count_nonzero(class_id == g))
        if is_vm:
            c_g2 = 1.0 / (1.0 + (tau ** 2) * (m - 1.0) / m) if m > 1 else 1.0
        else:
            c_g2 = 1.0
        p0_theta.append(c_g2 * (p.prior_sd ** 2))
        if m > 1:
            p0_b.extend([c_g2 * ((p.prior_sd * tau) ** 2)] * (m - 1))

    return np.r_[np.array(p0_theta, dtype=float), np.array(p0_b, dtype=float)]


def implied_host_covariance(
    params: EffectParams,
    class_id: np.ndarray,
    stationary: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate implied host covariance and correlation under hierarchical effect model.
    
    Effect: a = C theta + B b
    Cov(a) = Var(theta) * C C^T + Var(b) * B B^T
    
    Args:
        params: EffectParams containing rho_g, rho_h, sd_g, sd_h_ratio, variance_mode.
        class_id: Array of class IDs for each host (length n).
        stationary: If True, uses stationary variances Var = sd^2 / (1 - rho^2).
                   If False, uses innovation variances Var = sd^2.
                   
    Returns:
        (cov_a, corr_a): Tuple of (n, n) covariance and correlation matrices.
    """
    class_id = np.asarray(class_id)
    n = len(class_id)

    sd_g = params.sd_g
    sd_h = params.sd_g * params.sd_h_ratio

    if stationary:
        var_theta = sd_g ** 2 / max(1.0 - params.rho_g ** 2, 1e-12)
        var_b = sd_h ** 2 / max(1.0 - params.rho_h ** 2, 1e-12)
    else:
        var_theta = sd_g ** 2
        var_b = sd_h ** 2

    if params.kind == "indep":
        cov_a = var_theta * np.eye(n)
        corr_a = np.eye(n)
        return cov_a, corr_a
    elif params.kind == "pooled":
        cov_a = var_theta * np.ones((n, n))
        corr_a = np.ones((n, n))
        return cov_a, corr_a

    C, B = class_structure(class_id)
    is_vm = params.variance_mode in ("variance_matched", "matched")
    
    if not is_vm:
        cov_a = var_theta * (C @ C.T)
        if B.shape[1] > 0:
            cov_a = cov_a + var_b * (B @ B.T)
    else:
        classes = np.unique(class_id)
        tau = params.sd_h_ratio
        cov_a = np.zeros((n, n), dtype=float)
        for g in classes:
            idx = np.flatnonzero(class_id == g)
            m = len(idx)
            c_g2 = 1.0 / (1.0 + (tau ** 2) * (m - 1.0) / m) if m > 1 else 1.0
            if stationary:
                vt = c_g2 * (sd_g ** 2 / max(1.0 - params.rho_g ** 2, 1e-12))
                vb = c_g2 * (sd_h ** 2 / max(1.0 - params.rho_h ** 2, 1e-12))
            else:
                vt = c_g2 * (sd_g ** 2)
                vb = c_g2 * (sd_h ** 2)
            cov_a[np.ix_(idx, idx)] += vt
            if m > 1:
                Bg = deterministic_helmert_basis(m)
                cov_a[np.ix_(idx, idx)] += vb * (Bg @ Bg.T)
        
    diag_std = np.sqrt(np.maximum(np.diag(cov_a), 1e-18))
    corr_a = cov_a / np.outer(diag_std, diag_std)
    np.fill_diagonal(corr_a, 1.0)
    
    return cov_a, corr_a


def pooling_correlation(sd_h_ratio: float, m: int) -> float:
    """Analytical within-class correlation as a function of pooling parameter tau = sd_h_ratio."""
    if m <= 1:
        return 1.0
    tau2 = float(sd_h_ratio) ** 2
    return float((1.0 - tau2 / m) / (1.0 + tau2 * (m - 1) / m))


def build_model(p: EffectParams, class_id: np.ndarray):
    n = len(class_id)
    if p.kind == "hier":
        C, B = class_structure(class_id)
        L = np.hstack([C, B])
        rho = np.r_[np.full(C.shape[1], p.rho_g), np.full(B.shape[1], p.rho_h)]
        is_vm = p.variance_mode in ("variance_matched", "matched")
        if not is_vm:
            sd = np.r_[np.full(C.shape[1], p.sd_g), np.full(B.shape[1], p.sd_g * p.sd_h_ratio)]
        else:
            classes = np.unique(class_id)
            tau = p.sd_h_ratio
            sd_theta = []
            sd_b = []
            for g in classes:
                m = int(np.count_nonzero(class_id == g))
                c_g = 1.0 / np.sqrt(1.0 + (tau ** 2) * (m - 1.0) / m) if m > 1 else 1.0
                sd_theta.append(c_g * p.sd_g)
                if m > 1:
                    sd_b.extend([c_g * p.sd_g * tau] * (m - 1))
            sd = np.r_[np.array(sd_theta, dtype=float), np.array(sd_b, dtype=float)]
    elif p.kind == "indep":
        L = np.eye(n); rho = np.full(n, p.rho_g); sd = np.full(n, p.sd_g)
    elif p.kind == "pooled":
        L = np.ones((n, 1)); rho = np.array([p.rho_g]); sd = np.array([p.sd_g])
    else:
        raise ValueError(p.kind)
    return L, rho, sd


class EffectDetector:
    def __init__(self, nuis: Nuisance, params: EffectParams, name: str | None = None,
                 class_override: np.ndarray | None = None, kappa: float = KAPPA):
        self.nuis, self.p, self.kappa = nuis, params, kappa
        self.name = name or {"hier": "hier_ssm", "indep": "indep_ssm", "pooled": "pooled_ssm"}[params.kind]
        self.class_override = class_override

    def run(self, adj: Adjusted) -> DetectorOutput:
        nu = self.nuis; n = adj.r.shape[1]; T, t0 = adj.r.shape[0], adj.t0
        cls = adj.class_id if self.class_override is None else self.class_override
        L, rho, sd = build_model(self.p, cls)
        d = L.shape[1]
        phi = np.array([nu.phi_e[g] for g in adj.class_id])
        qe = np.array([nu.q_e[g] for g in adj.class_id])
        vv = np.array([nu.v[g] for g in adj.class_id])
        lam = adj.lam
        R = adj.r if self.p.huber_c <= 0 else np.clip(adj.r, -self.p.huber_c * adj.sigma[None], self.p.huber_c * adj.sigma[None])

        def Vfun(t):
            if adj.cov_U is not None and np.isfinite(adj.cov_U[t]).all():
                return np.diag(vv ** 2) + adj.cov_U[t]
            return np.diag(vv ** 2) + np.outer(lam, lam) * (0.0 if not np.isfinite(adj.U[t]) else adj.U[t])

        # ---- pre-period: noise-only filter; carry AR state + covariance into the rollout ----
        kn = KalmanFilter(np.diag(phi), np.diag(qe ** 2), np.zeros(n), np.diag(qe ** 2 / (1 - phi ** 2)))
        I = np.eye(n)
        for t in range(t0):
            use = adj.obs[t] & adj.elig[t]
            if use.any():
                idx = np.flatnonzero(use); V = Vfun(t)
                kn.step(R[t, idx], I[idx], V[np.ix_(idx, idx)])
            else:
                kn.step()
        # ---- rollout filter: effect prior reset to zero with proper diagonal variance ----
        F = block_diag(np.diag(rho), np.diag(phi)); Q = block_diag(np.diag(sd ** 2), np.diag(qe ** 2))
        m0 = np.r_[np.zeros(d), kn.m]
        p0_eff = effect_prior_variance(self.p, cls)
        P0 = block_diag(np.diag(p0_eff), kn.P)
        kf = KalmanFilter(F, Q, m0, P0)
        H = np.hstack([L, np.eye(n)]); Lfull = np.hstack([L, np.zeros((n, n))])
        if self.p.kind == "hier":
            C_mat, B_mat = class_structure(cls)
            G = C_mat.shape[1]
        elif self.p.kind == "pooled":
            C_mat = np.ones((n, 1))
            B_mat = np.zeros((n, 0))
            G = 1
        else: # indep
            C_mat = np.eye(n)
            B_mat = np.zeros((n, 0))
            G = n

        mean = np.full((T, n), np.nan); prob = np.full((T, n), np.nan); score = np.full(T, np.nan)
        class_effects = np.full((T, G), np.nan)
        host_deviations = np.full((T, n), np.nan)
        effect_cov = np.full((T, n, n), np.nan)
        times = []
        for t in range(t0, T):
            ts = time.perf_counter()
            use = adj.obs[t] & adj.elig[t]
            if use.any():
                idx = np.flatnonzero(use); V = Vfun(t)
                kf.step(R[t, idx], H[idx], V[np.ix_(idx, idx)])
            else:
                kf.step()                                   # predict only: insufficient data
            am = Lfull @ kf.m
            cov_mat = L @ kf.P[:d, :d] @ L.T
            av = np.maximum(np.diag(cov_mat), 1e-18)
            mean[t] = am
            effect_cov[t] = cov_mat
            if self.p.kind == "hier":
                class_effects[t] = kf.m[:G]
                if B_mat.shape[1] > 0:
                    host_deviations[t] = B_mat @ kf.m[G:d]
                else:
                    host_deviations[t] = 0.0
            elif self.p.kind == "pooled":
                class_effects[t] = kf.m[0:1]
                host_deviations[t] = 0.0
            elif self.p.kind == "indep":
                class_effects[t] = kf.m[:n]
                host_deviations[t] = 0.0

            zz = (self.kappa - am) / np.sqrt(av)
            prob[t] = norm.sf(zz)
            score[t] = np.nanmax(norm.logsf(zz))      # log max-host risk: same ordering as max p, no underflow
            times.append(time.perf_counter() - ts)
        return DetectorOutput(
            self.name,
            score,
            adj.elig,
            mean,
            prob,
            1000 * float(np.mean(times)) if times else 0.0,
            {**asdict(self.p), "min_eig": kf.min_eig_seen, "floor_events": kf.floor_events},
            update_times_ms=1000 * np.array(times) if times else None,
            class_effects=class_effects,
            host_deviations=host_deviations,
            effect_cov=effect_cov,
        )
