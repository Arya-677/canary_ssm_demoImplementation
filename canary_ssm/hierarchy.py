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
from scipy.linalg import null_space, block_diag
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


def long_run_sd(p: "EffectParams") -> float:
    """Stationary SD of the effect state(s). Handoff audit: keep it below kappa or healthy data cross risk 0.5."""
    f = lambda sd, rho: float("inf") if abs(rho) >= 1 else sd / np.sqrt(1 - rho ** 2)
    return max(f(p.sd_g, p.rho_g), f(p.sd_g * p.sd_h_ratio, p.rho_h) if p.kind == "hier" else 0.0)


def class_structure(class_id: np.ndarray):
    """C (n x G), B (n x (n-G)) block-diag orthonormal sum-zero basis; singleton classes add no column."""
    classes = np.unique(class_id); n = len(class_id)
    C = np.zeros((n, len(classes))); blocks = []
    for j, g in enumerate(classes):
        idx = np.flatnonzero(class_id == g); C[idx, j] = 1.0
        m = len(idx)
        if m > 1:
            Bg = np.zeros((n, m - 1)); Bg[idx] = null_space(np.ones((1, m))); blocks.append(Bg)
    B = np.hstack(blocks) if blocks else np.zeros((n, 0))
    return C, B


def build_model(p: EffectParams, class_id: np.ndarray):
    n = len(class_id)
    if p.kind == "hier":
        C, B = class_structure(class_id)
        L = np.hstack([C, B])
        rho = np.r_[np.full(C.shape[1], p.rho_g), np.full(B.shape[1], p.rho_h)]
        sd = np.r_[np.full(C.shape[1], p.sd_g), np.full(B.shape[1], p.sd_g * p.sd_h_ratio)]
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
        P0 = block_diag(np.eye(d) * self.p.prior_sd ** 2, kn.P)
        kf = KalmanFilter(F, Q, m0, P0)
        H = np.hstack([L, np.eye(n)]); Lfull = np.hstack([L, np.zeros((n, n))])
        mean = np.full((T, n), np.nan); prob = np.full((T, n), np.nan); score = np.full(T, np.nan)
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
            av = np.maximum(np.einsum("ij,jk,ik->i", Lfull, kf.P, Lfull), 1e-18)
            mean[t] = am
            zz = (self.kappa - am) / np.sqrt(av)
            prob[t] = norm.sf(zz)
            score[t] = np.nanmax(norm.logsf(zz))      # log max-host risk: same ordering as max p, no underflow
            times.append(time.perf_counter() - ts)
        return DetectorOutput(self.name, score, adj.elig, mean, prob,
                              1000 * float(np.mean(times)), {**asdict(self.p), "min_eig": kf.min_eig_seen,
                                                              "floor_events": kf.floor_events},
                              update_times_ms=1000 * np.array(times))
