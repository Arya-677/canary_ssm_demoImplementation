"""Clairvoyant reference detectors (`WP-E2`) -- UPPER BOUNDS ONLY, NEVER COMPETITORS.

This module is explicitly exempt from the no-Truth AST rule because its outputs use oracle
ground truth (`Truth`), carry the `ORACLE` label / `is_oracle=True` marker in tables and plots,
and are excluded from all real-method rankings.
"""
from __future__ import annotations

import numpy as np

from .baselines import DetectorOutput, _timed, _z
from .factor import Adjusted
from .hierarchy import EffectDetector, EffectParams
from .preprocess import Nuisance
from .schema import KAPPA
from .simulate import Truth

ORACLE_METHODS = ("oracle_cusum", "oracle_bayes", "oracle_subset")


def is_oracle_method(name: str) -> bool:
    return name in ORACLE_METHODS or str(name).startswith("oracle_")


def _target_hosts(adj: Adjusted, truth: Truth) -> np.ndarray:
    """True affected canary indices on harm rollouts; deterministic matched-size subset on nulls."""
    nc = adj.r.shape[1]
    if truth.harm and truth.affected_hosts:
        idx = np.asarray([h for h in truth.affected_hosts if 0 <= int(h) < nc], dtype=int)
        if idx.size > 0:
            return np.unique(idx)
    cfg = truth.config or {}
    if cfg.get("affected_mode") == "class0":
        c0 = np.flatnonzero(adj.class_id == 0)
        if c0.size > 0:
            return c0
    n_aff = max(1, min(int(cfg.get("n_affected", 3)), nc))
    rng = np.random.default_rng(np.random.SeedSequence([int(truth.seed), 5]))
    return np.sort(rng.choice(nc, size=n_aff, replace=False))


def _oracle_nuisance(adj: Adjusted, truth: Truth) -> Nuisance:
    cfg = truth.config or {}
    G = max(int(adj.class_id.max()) + 1, int(cfg.get("n_classes", 2)))
    phi = float(cfg.get("phi_e", 0.6))
    q = float(cfg.get("sd_host", 0.02))
    v = float(cfg.get("meas_sd", 0.0))
    noise = "ar_white" if v > 0.0 else "ar_only"
    return Nuisance(
        x_center=0.0,
        class_lambda=[1.0] * G,
        phi_e=[phi] * G,
        q_e=[q] * G,
        v=[max(v, 1e-4)] * G,
        factor_rank=1,
        noise=noise,
    )


@_timed
def oracle_cusum(adj: Adjusted, truth: Truth) -> DetectorOutput:
    """CUSUM restricted to true affected hosts with optimal reference k = delta / (2 * sigma_i)."""
    cfg = truth.config or {}
    delta = float(np.log1p(cfg.get("effect_pct", 3.0) / 100.0))
    delta = max(delta, 1e-4)
    idx = _target_hosts(adj, truth)
    z = np.where(adj.obs & np.isfinite(adj.r), _z(adj), np.nan)
    T, nc = z.shape
    t0 = int(adj.t0)

    k_sub = delta / (2.0 * adj.sigma[idx])
    C = np.zeros(idx.size, dtype=float)
    host = np.full((T, nc), np.nan, dtype=float)
    score = np.full(T, np.nan, dtype=float)
    for t in range(t0, T):
        zt = z[t, idx]
        ok = np.isfinite(zt)
        if np.any(ok):
            C[ok] = np.maximum(0.0, C[ok] + zt[ok] - k_sub[ok])
        row = np.zeros(nc, dtype=float)
        row[idx] = C
        host[t] = row
        score[t] = float(np.max(C))
    return DetectorOutput(
        "oracle_cusum",
        score,
        adj.elig,
        host,
        params={"is_oracle": True, "label": "ORACLE", "n_affected": int(idx.size), "delta": delta},
    )


@_timed
def oracle_bayes(adj: Adjusted, truth: Truth) -> DetectorOutput:
    """Independent SSM run with true (phi_e, q_e, v) and persistent prior SD equal to true effect."""
    cfg = truth.config or {}
    delta = float(np.log1p(cfg.get("effect_pct", 3.0) / 100.0))
    nu_true = _oracle_nuisance(adj, truth)
    ep = EffectParams(
        kind="indep",
        rho_g=1.0,
        rho_h=1.0,
        sd_g=0.0,
        sd_h_ratio=1.0,
        prior_sd=max(delta, 1e-3),
        huber_c=0.0,
    )
    out = EffectDetector(nu_true, ep, name="oracle_bayes", kappa=KAPPA).run(adj)
    out.method = "oracle_bayes"
    out.params = {"is_oracle": True, "label": "ORACLE", "prior_sd": ep.prior_sd}
    return out


@_timed
def oracle_subset(
    adj: Adjusted,
    truth: Truth,
    nuis: Nuisance | None = None,
    effect_params: EffectParams | dict | None = None,
) -> DetectorOutput:
    """Independent SSM restricted strictly to the true affected host subset."""
    idx = _target_hosts(adj, truth)
    nu = _oracle_nuisance(adj, truth) if nuis is None else nuis
    if effect_params is None:
        cfg = truth.config or {}
        delta = float(np.log1p(cfg.get("effect_pct", 3.0) / 100.0))
        ep = EffectParams(kind="indep", rho_g=0.99, rho_h=0.99, sd_g=0.001, sd_h_ratio=1.0, prior_sd=max(delta, 0.01))
    elif isinstance(effect_params, EffectParams):
        ep = EffectParams(**{**vars(effect_params), "kind": "indep"})
    else:
        ep = EffectParams(**{**effect_params, "kind": "indep"})

    sub_adj = Adjusted(
        r=adj.r[:, idx],
        obs=adj.obs[:, idx],
        elig=adj.elig,
        U=adj.U,
        lam=adj.lam[idx],
        sigma=adj.sigma[idx],
        rm=adj.rm[:, idx],
        class_id=adj.class_id[idx],
        t0=adj.t0,
        fallback=adj.fallback[idx],
        f_hat=adj.f_hat,
        ctl_r=adj.ctl_r,
        ctl_class_id=adj.ctl_class_id,
    )
    sub_out = EffectDetector(nu, ep, name="oracle_subset", kappa=KAPPA).run(sub_adj)
    T, nc = adj.r.shape
    host = np.full((T, nc), np.nan, dtype=float)
    prob = np.full((T, nc), np.nan, dtype=float)
    host[adj.t0 :] = 0.0
    prob[adj.t0 :] = 0.0
    if sub_out.host_score is not None:
        host[:, idx] = sub_out.host_score
    if sub_out.host_prob is not None:
        prob[:, idx] = sub_out.host_prob
    return DetectorOutput(
        "oracle_subset",
        sub_out.score,
        adj.elig,
        host,
        host_prob=prob,
        params={"is_oracle": True, "label": "ORACLE", "n_affected": int(idx.size)},
    )


def run_oracle(
    name: str,
    adj: Adjusted,
    truth: Truth,
    nuis: Nuisance | None = None,
    effect_params: EffectParams | dict | None = None,
) -> DetectorOutput:
    if name == "oracle_cusum":
        return oracle_cusum(adj, truth)
    if name == "oracle_bayes":
        return oracle_bayes(adj, truth)
    if name == "oracle_subset":
        return oracle_subset(adj, truth, nuis=nuis, effect_params=effect_params)
    raise KeyError(f"Unknown oracle method: {name!r}")


def efficiency_ratio(method_capped: float, oracle_capped: float, miss_capped: float) -> float:
    """Normalized capped-time shortfall vs clairvoyant oracle in [0, 1] (`WP-E2`)."""
    denom = float(miss_capped) - float(oracle_capped)
    if not np.isfinite(denom) or denom <= 1e-12:
        return float("nan")
    val = (float(method_capped) - float(oracle_capped)) / denom
    return float(np.clip(val, 0.0, 1.0))
