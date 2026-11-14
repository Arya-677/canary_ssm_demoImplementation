"""Additional sequential baselines on identical Adjusted streams (`WP-E1`, `docs/baselines.md`).

All detectors operate strictly causally (score[t] uses observations <= t), return NaN before t0,
never zero-impute missing observations, and never import Truth, simulate, or metrics.
"""
from __future__ import annotations

import numpy as np
from scipy.special import gammaln, logsumexp

from .baselines import DetectorOutput, _timed, _z
from .factor import Adjusted


def _masked_z(adj: Adjusted) -> np.ndarray:
    z = _z(adj)
    return np.where(adj.obs & np.isfinite(z), z, np.nan)


def _phi_vec(phi: np.ndarray | float | None, nc: int) -> np.ndarray:
    if phi is None:
        return np.zeros(nc, dtype=float)
    arr = np.asarray(phi, dtype=float)
    if arr.ndim == 0:
        arr = np.full(nc, float(arr), dtype=float)
    return np.clip(arr, -0.99, 0.99)


def _prewhiten(z: np.ndarray, phi: np.ndarray | float | None = None) -> np.ndarray:
    """Exact causal AR(1) prewhitening across arbitrary missing gaps (`docs/baselines.md` Sec 2)."""
    T, nc = z.shape
    phi_arr = _phi_vec(phi, nc)
    if np.all(phi_arr == 0.0):
        return z.copy()
    e = np.full((T, nc), np.nan, dtype=float)
    has_prev = np.zeros(nc, dtype=bool)
    t_prev = np.zeros(nc, dtype=int)
    z_prev = np.zeros(nc, dtype=float)
    for t in range(T):
        ok = np.isfinite(z[t])
        if not np.any(ok):
            continue
        fresh = ok & (~has_prev)
        if np.any(fresh):
            e[t, fresh] = z[t, fresh]
        cont = ok & has_prev
        if np.any(cont):
            delta = t - t_prev[cont]
            p_d = np.power(phi_arr[cont], delta)
            denom = np.sqrt(np.maximum(1.0 - p_d * p_d, 1e-12))
            e[t, cont] = (z[t, cont] - p_d * z_prev[cont]) / denom
        has_prev[ok] = True
        t_prev[ok] = t
        z_prev[ok] = z[t, ok]
    return e


@_timed
def wmean(adj: Adjusted, w: int = 15, K: int = 1) -> DetectorOutput:
    """Stateless trailing w-minute standardised mean with top-K aggregation (`docs/baselines.md` Sec 3.1)."""
    z = _masked_z(adj)
    T, nc = z.shape
    t0 = int(adj.t0)
    win = max(1, int(w))
    top_k = max(1, min(int(K), nc))

    host = np.full((T, nc), np.nan, dtype=float)
    score = np.full(T, np.nan, dtype=float)
    if t0 >= T:
        return DetectorOutput("wmean", score, adj.elig, host, params={"w": win, "K": int(K)})

    z_post = z[t0:]
    ok_post = np.isfinite(z_post)
    n_post = T - t0
    p_z = np.zeros((n_post + 1, nc), dtype=float)
    p_n = np.zeros((n_post + 1, nc), dtype=int)
    p_z[1:] = np.cumsum(np.where(ok_post, z_post, 0.0), axis=0)
    p_n[1:] = np.cumsum(ok_post.astype(int), axis=0)

    idx_hi = np.arange(1, n_post + 1)
    idx_lo = np.maximum(0, idx_hi - win)
    sz = p_z[idx_hi] - p_z[idx_lo]
    cnt = p_n[idx_hi] - p_n[idx_lo]
    with np.errstate(divide="ignore", invalid="ignore"):
        stat = np.where(cnt > 0, np.maximum(0.0, sz / np.sqrt(np.maximum(cnt, 1))), np.nan)
    host[t0:] = stat
    srt = -np.sort(-np.nan_to_num(stat, nan=0.0), axis=1)
    score[t0:] = srt[:, :top_k].sum(axis=1)
    return DetectorOutput("wmean", score, adj.elig, host, params={"w": win, "K": int(K)})


@_timed
def ar_cusum(
    adj: Adjusted,
    k: float = 0.25,
    phi: np.ndarray | float | None = None,
) -> DetectorOutput:
    """One-sided Page CUSUM on AR(1)-prewhitened unit-variance innovations (`docs/baselines.md` Sec 3.2)."""
    z = _masked_z(adj)
    T, nc = z.shape
    t0 = int(adj.t0)
    phi_arr = _phi_vec(phi, nc)
    e = _prewhiten(z, phi_arr)
    k_pw = float(k) * np.sqrt(np.maximum(1.0 - phi_arr, 1e-12) / np.maximum(1.0 + phi_arr, 1e-12))

    C = np.zeros(nc, dtype=float)
    host = np.full((T, nc), np.nan, dtype=float)
    for t in range(t0, T):
        ok = np.isfinite(e[t])
        if np.any(ok):
            C[ok] = np.maximum(0.0, C[ok] + e[t, ok] - k_pw[ok])
        host[t] = C
    score = np.full(T, np.nan, dtype=float)
    if t0 < T:
        score[t0:] = np.max(host[t0:], axis=1)
    return DetectorOutput("ar_cusum", score, adj.elig, host, params={"k": float(k)})


def _post_prewhitened_prefix(
    adj: Adjusted,
    phi: np.ndarray | float | None,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    z = _masked_z(adj)
    T, nc = z.shape
    t0 = int(adj.t0)
    e = _prewhiten(z, phi)
    if t0 >= T:
        return np.zeros((1, nc), dtype=float), np.zeros((1, nc), dtype=int), T, nc
    e_post = e[t0:]
    ok = np.isfinite(e_post)
    n_post = T - t0
    p_e = np.zeros((n_post + 1, nc), dtype=float)
    p_n = np.zeros((n_post + 1, nc), dtype=int)
    p_e[1:] = np.cumsum(np.where(ok, e_post, 0.0), axis=0)
    p_n[1:] = np.cumsum(ok.astype(int), axis=0)
    return p_e, p_n, T, nc


@_timed
def glr_window(
    adj: Adjusted,
    W: int = 30,
    K: int = 1,
    phi: np.ndarray | float | None = None,
) -> DetectorOutput:
    """Sliding-window one-sided normal GLR on prewhitened residuals (`docs/baselines.md` Sec 3.3)."""
    p_e, p_n, T, nc = _post_prewhitened_prefix(adj, phi)
    t0 = int(adj.t0)
    win = max(1, int(W))
    top_k = max(1, min(int(K), nc))

    host = np.full((T, nc), np.nan, dtype=float)
    score = np.full(T, np.nan, dtype=float)
    for u in range(1, T - t0 + 1):
        s0 = max(0, u - win)
        num = p_e[u][None, :] - p_e[s0:u]
        cnt = p_n[u][None, :] - p_n[s0:u]
        u_pos = np.where(cnt > 0, np.maximum(0.0, num / np.sqrt(np.maximum(cnt, 1))), 0.0)
        host[t0 + u - 1] = np.max(0.5 * u_pos * u_pos, axis=0)
    if t0 < T:
        srt = -np.sort(-host[t0:], axis=1)
        score[t0:] = srt[:, :top_k].sum(axis=1)
    return DetectorOutput("glr_window", score, adj.elig, host, params={"W": win, "K": int(K)})


@_timed
def sparse_mix_glr(
    adj: Adjusted,
    p0: float = 0.3,
    W: int = 30,
    phi: np.ndarray | float | None = None,
) -> DetectorOutput:
    """Xie-Siegmund (2013) Eq. (2)-(4) multi-stream mixture GLR (`docs/baselines.md` Sec 3.4)."""
    p0_f = float(p0)
    if not (0.0 < p0_f <= 1.0):
        raise ValueError(f"sparse_mix_glr requires 0 < p0 <= 1, got {p0!r}")
    p_e, p_n, T, nc = _post_prewhitened_prefix(adj, phi)
    t0 = int(adj.t0)
    win = max(1, int(W))

    lp1 = float(np.log1p(-p0_f)) if p0_f < 1.0 else -np.inf
    lp0 = float(np.log(p0_f))
    host = np.full((T, nc), np.nan, dtype=float)
    score = np.full(T, np.nan, dtype=float)
    for u in range(1, T - t0 + 1):
        s0 = max(0, u - win)
        num = p_e[u][None, :] - p_e[s0:u]
        cnt = p_n[u][None, :] - p_n[s0:u]
        u_pos = np.where(cnt > 0, np.maximum(0.0, num / np.sqrt(np.maximum(cnt, 1))), 0.0)
        summand = np.logaddexp(lp1, lp0 + 0.5 * u_pos * u_pos)
        mix = summand.sum(axis=1)
        s_best = int(np.argmax(mix))
        t = t0 + u - 1
        score[t] = float(mix[s_best])
        host[t] = summand[s_best]
    return DetectorOutput("sparse_mix_glr", score, adj.elig, host, params={"p0": p0_f, "W": win})


@_timed
def bocpd(
    adj: Adjusted,
    lambda_h: float = 120.0,
    phi: np.ndarray | float | None = None,
    r_max: int = 300,
) -> DetectorOutput:
    """Directional Adams-MacKay (2007) Eq. (1)-(3) BOCPD with Normal-Gamma conjugate prior."""
    lam_h = float(lambda_h)
    if lam_h <= 1.0:
        raise ValueError(f"bocpd requires lambda_h > 1, got {lambda_h!r}")
    z = _masked_z(adj)
    T, nc = z.shape
    t0 = int(adj.t0)
    e = _prewhiten(z, phi)

    H = 1.0 / lam_h
    log_H = float(np.log(H))
    log_1mH = float(np.log1p(-H))
    mu0, kappa0, alpha0, beta0 = 0.0, 1.0, 1.0, 1.0

    R = min(int(r_max) + 1, T + 1)
    log_R = np.full((R, nc), -np.inf, dtype=float)
    log_R[0, :] = 0.0
    mu = np.full((R, nc), mu0, dtype=float)
    kappa = np.full((R, nc), kappa0, dtype=float)
    alpha = np.full((R, nc), alpha0, dtype=float)
    beta = np.full((R, nc), beta0, dtype=float)
    n_seen = np.zeros(nc, dtype=int)
    m_post = np.zeros(nc, dtype=int)
    r_grid = np.arange(R, dtype=int)[:, None]

    host = np.full((T, nc), np.nan, dtype=float)
    score = np.full(T, np.nan, dtype=float)
    prev_p = np.zeros(nc, dtype=float)

    for t in range(T):
        x = e[t]
        ok = np.isfinite(x)
        cols = np.flatnonzero(ok)
        if cols.size > 0:
            L = min(R - 1, int(n_seen[cols].max()) + 1)
            mu_s = mu[:L, cols]
            kap_s = kappa[:L, cols]
            alp_s = alpha[:L, cols]
            bet_s = beta[:L, cols]
            nu = 2.0 * alp_s
            s2 = bet_s * (kap_s + 1.0) / (alp_s * kap_s)
            xc = x[None, cols] - mu_s
            log_pi = (
                gammaln(0.5 * (nu + 1.0))
                - gammaln(0.5 * nu)
                - 0.5 * np.log(nu * np.pi * s2)
                - 0.5 * (nu + 1.0) * np.log1p((xc * xc) / (nu * s2))
            )
            log_w = log_R[:L, cols] + log_pi
            log_cp = logsumexp(log_w, axis=0) + log_H
            log_growth = log_w + log_1mH

            log_R_next = np.full((R, cols.size), -np.inf, dtype=float)
            log_R_next[0, :] = log_cp
            log_R_next[1 : 1 + L, :] = log_growth
            norm = logsumexp(log_R_next[: 1 + L, :], axis=0)
            log_R_next[: 1 + L, :] -= norm[None, :]
            log_R[:, cols] = log_R_next

            kap_n = kap_s + 1.0
            mu_n = (kap_s * mu_s + x[None, cols]) / kap_n
            alp_n = alp_s + 0.5
            bet_n = bet_s + (kap_s * (xc * xc)) / (2.0 * kap_n)
            mu[0, cols] = mu0
            kappa[0, cols] = kappa0
            alpha[0, cols] = alpha0
            beta[0, cols] = beta0
            mu[1 : 1 + L, cols] = mu_n
            kappa[1 : 1 + L, cols] = kap_n
            alpha[1 : 1 + L, cols] = alp_n
            beta[1 : 1 + L, cols] = bet_n

            n_seen[cols] += 1
            if t >= t0:
                m_post[cols] += 1
                mask = (r_grid < m_post[cols][None, :]) & (mu[:, cols] > 0.0) & np.isfinite(log_R[:, cols])
                # Compute column-wise probability mass of positive post-rollout runs
                p_vals = np.sum(np.where(mask, np.exp(log_R[:, cols]), 0.0), axis=0)
                prev_p[cols] = p_vals
        if t >= t0:
            host[t] = prev_p
            score[t] = float(np.max(prev_p))
    return DetectorOutput("bocpd", score, adj.elig, host, params={"lambda_h": lam_h})


@_timed
def msprt(
    adj: Adjusted,
    tau: float = 0.5,
    phi: np.ndarray | float | None = None,
) -> DetectorOutput:
    """Always-valid normal mixture SPRT (Johari, Pekelis & Walsh Sec 2.2, `docs/baselines.md` Sec 3.6)."""
    tau_f = float(tau)
    if tau_f <= 0.0:
        raise ValueError(f"msprt requires tau > 0, got {tau!r}")
    z = _masked_z(adj)
    T, nc = z.shape
    t0 = int(adj.t0)
    e = _prewhiten(z, phi)

    s2 = 1.0
    tau2 = tau_f * tau_f
    m = np.zeros(nc, dtype=float)
    S = np.zeros(nc, dtype=float)
    best_llr = np.zeros(nc, dtype=float)
    host = np.full((T, nc), np.nan, dtype=float)
    for t in range(t0, T):
        ok = np.isfinite(e[t])
        if np.any(ok):
            m[ok] += 1.0
            S[ok] += e[t, ok]
            denom = s2 + m[ok] * tau2
            log_lam = 0.5 * np.log(s2 / denom) + (tau2 * S[ok] * S[ok]) / (2.0 * s2 * denom)
            best_llr[ok] = np.maximum(best_llr[ok], log_lam)
        host[t] = best_llr
    score = np.full(T, np.nan, dtype=float)
    if t0 < T:
        score[t0:] = np.max(host[t0:], axis=1)
    return DetectorOutput("msprt", score, adj.elig, host, params={"tau": tau_f})


def _mw_u_z(x: np.ndarray, y: np.ndarray) -> float:
    """Standardised directional Mann-Whitney z (X > Y) matching SciPy asymptotic without continuity."""
    n1 = x.size
    n2 = y.size
    if n1 < 3 or n2 < 3:
        return 0.0
    N = n1 + n2
    xy = np.concatenate([x, y])
    order = np.argsort(xy, kind="mergesort")
    s = xy[order]
    # Fast path when all values are distinct (true ~100% of the time for continuous log latency)
    eq = s[1:] == s[:-1]
    if not np.any(eq):
        ranks_sorted = np.arange(1.0, N + 1.0)
        tie = 0.0
    else:
        ranks_sorted = np.empty(N, dtype=float)
        tie = 0.0
        i = 0
        while i < N:
            j = i + 1
            while j < N and s[j] == s[i]:
                j += 1
            avg = 0.5 * (i + 1 + j)
            ranks_sorted[i:j] = avg
            cnt = j - i
            if cnt > 1:
                tie += float(cnt * cnt * cnt - cnt)
            i = j
    inv = np.empty(N, dtype=int)
    inv[order] = np.arange(N)
    u1 = float(ranks_sorted[inv[:n1]].sum()) - 0.5 * n1 * (n1 + 1.0)
    var_u = (n1 * n2 / 12.0) * ((N + 1.0) - tie / (N * (N - 1.0)))
    if var_u <= 1e-12:
        return 0.0
    return float((u1 - 0.5 * n1 * n2) / np.sqrt(var_u))


@_timed
def mw_judge(adj: Adjusted, w: int = 15) -> DetectorOutput:
    """Rank-based sliding-window Mann-Whitney canary judge (Kayenta style, `docs/baselines.md` Sec 3.7)."""
    if adj.ctl_r is None or adj.ctl_class_id is None:
        raise ValueError("mw_judge requires Adjusted.ctl_r and Adjusted.ctl_class_id (populate via factor.adjust)")
    T, nc = adj.r.shape
    t0 = int(adj.t0)
    win = max(1, int(w))
    classes = np.unique(adj.class_id)
    can_masks = {int(g): np.flatnonzero(adj.class_id == g) for g in classes}
    ctl_masks = {int(g): np.flatnonzero(adj.ctl_class_id == g) for g in classes}

    r_can = np.where(adj.obs & np.isfinite(adj.r), adj.r, np.nan)
    r_ctl = adj.ctl_r
    host = np.full((T, nc), np.nan, dtype=float)
    score = np.full(T, np.nan, dtype=float)

    for t in range(t0, T):
        lo = max(0, t - win + 1)
        class_scores = []
        for g in classes:
            gi = int(g)
            c_idx = can_masks[gi]
            k_idx = ctl_masks[gi]
            yg = r_ctl[lo : t + 1][:, k_idx]
            yg = yg[np.isfinite(yg)]
            xg = r_can[lo : t + 1][:, c_idx]
            xg_flat = xg[np.isfinite(xg)]
            class_scores.append(_mw_u_z(xg_flat, yg))
            for col in c_idx:
                xi = r_can[lo : t + 1, col]
                xi = xi[np.isfinite(xi)]
                host[t, col] = _mw_u_z(xi, yg)
        score[t] = float(max(class_scores)) if class_scores else 0.0
    return DetectorOutput("mw_judge", score, adj.elig, host, params={"w": win})


EXTRA_BASELINES = (
    "wmean",
    "ar_cusum",
    "glr_window",
    "sparse_mix_glr",
    "bocpd",
    "msprt",
    "mw_judge",
)

PREWHITENED_BASELINES = (
    "ar_cusum",
    "glr_window",
    "sparse_mix_glr",
    "bocpd",
    "msprt",
)


def extra_config_grid() -> list[tuple[str, dict]]:
    """Predeclared default grids (`<= 24` candidates per family)."""
    g = [("wmean", {"w": int(w), "K": int(K)}) for w in (5, 10, 15, 30, 45) for K in (1, 3, 5)]
    g += [("ar_cusum", {"k": float(k)}) for k in (0.1, 0.25, 0.5, 0.75)]
    g += [("glr_window", {"W": int(W), "K": int(K)}) for W in (15, 30, 45, 60) for K in (1, 3, 5)]
    g += [("sparse_mix_glr", {"p0": float(p0), "W": int(W)}) for p0 in (0.1, 0.3, 0.5) for W in (30, 60)]
    g += [("bocpd", {"lambda_h": float(lh)}) for lh in (60.0, 120.0, 240.0)]
    g += [("msprt", {"tau": float(tau)}) for tau in (0.25, 0.5, 1.0, 2.0)]
    g += [("mw_judge", {"w": int(w)}) for w in (15, 30)]
    return g


def run_extra_baseline(name: str, adj: Adjusted, **params) -> DetectorOutput:
    fn = {
        "wmean": wmean,
        "ar_cusum": ar_cusum,
        "glr_window": glr_window,
        "sparse_mix_glr": sparse_mix_glr,
        "bocpd": bocpd,
        "msprt": msprt,
        "mw_judge": mw_judge,
    }[name]
    return fn(adj, **params)
