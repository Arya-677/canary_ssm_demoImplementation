"""Nuisance fitting on HEALTHY development data (handbook Sections 5, 7, 16).

Fits: workload centering, class-level fallback loadings, and AR(1)+white-noise parameters per class by
minimising the negative Kalman innovation log-likelihood of the no-effect model. Effect hyperparameters
are NOT touched here (they are tuned later, with nuisance noise held fixed).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from .factor import adjust, host_slopes
from .schema import Rollout

PHI_BOUNDS = (-0.95, 0.99)
LOGSD_BOUNDS = (np.log(1e-4), np.log(0.2))


@dataclass
class Nuisance:
    x_center: float
    class_lambda: list
    phi_e: list                 # per canary class
    q_e: list                   # AR innovation SD per class
    v: list                     # white measurement SD per class
    factor_rank: int = 1
    noise: str = "ar_only"          # ar_only (default, handoff) | ar_white | white
    beta_mode: str = "pre"          # pre (rollout pre-period) | pooled_dev (development-pooled slope)
    beta_pooled: float | None = None
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Nuisance":
        return Nuisance(**d)

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @staticmethod
    def load(path: Path) -> "Nuisance":
        return Nuisance(**json.loads(Path(path).read_text()))


def scalar_nll(params, R, X):
    """Vectorised AR(1)+white-noise Kalman negative log-likelihood. R,X: (B,T); X is extra known variance."""
    phi, lq, lv = params
    q2, v2 = np.exp(2 * lq), np.exp(2 * lv)
    B, T = R.shape
    m = np.zeros(B); P = np.full(B, q2 / (1 - phi ** 2))
    nll = 0.0
    for t in range(T):
        if t > 0:
            m = phi * m; P = phi ** 2 * P + q2
        ob = np.isfinite(R[:, t])
        S = P + v2 + X[:, t]
        inn = np.where(ob, R[:, t] - m, 0.0)
        nll += 0.5 * np.sum(np.where(ob, np.log(S) + inn ** 2 / S, 0.0))
        K = np.where(ob, P / S, 0.0)
        m = m + K * inn
        P = (1 - K) * P
    return nll


V_FLOOR = 1e-4


def fit_ar_class(R, X, fix_v: bool = False):
    """AR(1) innovation + (optionally) white noise by innovation likelihood. fix_v=True estimates only
    (phi, q) and pins the white SD at V_FLOOR: the split is weakly identified (handoff Experiment 2)."""
    best, rec = None, []
    if fix_v:
        bounds = [PHI_BOUNDS, LOGSD_BOUNDS]
        f = lambda p, R, X: scalar_nll([p[0], p[1], np.log(V_FLOOR)], R, X)
        starts = [np.array([p0, np.log(0.01)]) for p0 in (0.2, 0.6, 0.9)]
    else:
        bounds = [PHI_BOUNDS, LOGSD_BOUNDS, LOGSD_BOUNDS]; f = scalar_nll
        starts = [np.array([p0, np.log(0.01), np.log(0.005)]) for p0 in (0.2, 0.6, 0.9)]
    for x0 in starts:
        res = minimize(f, x0, args=(R, X), method="L-BFGS-B", bounds=bounds)
        hit = bool(any(abs(res.x[i] - b[j]) < 1e-3 for i, b in enumerate(bounds) for j in (0, 1)))
        rec.append({"init_phi": float(x0[0]), "nll": float(res.fun), "success": bool(res.success),
                    "boundary_hit": hit, "x": res.x.tolist()})
        if best is None or res.fun < best.fun:
            best = res
    x = best.x if not fix_v else np.r_[best.x, np.log(V_FLOOR)]
    return x, rec


def adjust_roll(roll: Rollout, nu: "Nuisance", factor_rank: int | None = None):
    """The ONE adjustment entry point: honours the nuisance object's beta mode and factor rank."""
    rank = nu.factor_rank if factor_rank is None else factor_rank
    bp = nu.beta_pooled if nu.beta_mode == "pooled_dev" else None
    return adjust(roll, nu.x_center, np.array(nu.class_lambda), rank, bp)


def fit_nuisance(healthy: list[Rollout], factor_rank: int = 1, noise: str = "ar_only",
                 beta_mode: str = "pre", max_series: int = 1500) -> Nuisance:
    """`healthy` = null development rollouts. Uses only detector-visible data."""
    x_center = float(np.mean([r.x[:r.t0].mean() for r in healthy]))
    G = int(max(r.class_id.max() for r in healthy)) + 1
    beta_pooled = float(np.nanmedian(np.concatenate([host_slopes(r, x_center) for r in healthy])))
    bp = beta_pooled if beta_mode == "pooled_dev" else None
    # pass 1: class-level fallback loadings
    lam_by_class = [[] for _ in range(G)]
    adj = []
    for r in healthy:
        a = adjust(r, x_center, np.ones(G), factor_rank, bp)
        adj.append(a)
        for k, g in enumerate(a.class_id):
            lam_by_class[g].append(a.lam[k])
    class_lambda = [float(np.median(l)) if l else 1.0 for l in lam_by_class]
    phi, q, v, diag = [], [], [], {"classes": []}
    for g in range(G):
        rows, xs = [], []
        for r, a in zip(healthy, adj):
            for k in np.flatnonzero(a.class_id == g):
                rows.append(a.r[:, k])
                xs.append(a.lam[k] ** 2 * np.nan_to_num(a.U, nan=0.0))
        R = np.array(rows)[:max_series]; X = np.array(xs)[:max_series]
        if noise in ("ar_only", "ar_white"):
            p, rec = fit_ar_class(R, X, fix_v=(noise == "ar_only"))
            phi.append(float(p[0])); q.append(float(np.exp(p[1]))); v.append(float(np.exp(p[2])))
        else:                                    # white-noise ablation: total variance as measurement noise
            rec = []
            phi.append(0.0); q.append(1e-4); v.append(float(np.sqrt(max(np.nanvar(R) - np.nanmean(X), 1e-8))))
        diag["classes"].append({"class": g, "n_series": len(R), "fits": rec})
    return Nuisance(x_center, class_lambda, phi, q, v, factor_rank, noise, beta_mode,
                    beta_pooled if beta_mode == "pooled_dev" else None, diag)
