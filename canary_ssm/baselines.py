"""Strong sequential baselines on the SAME adjusted residuals and masks (handbook Section 6).

Every detector: accumulators reset at rollout time t0, current/past data only, missing observation
leaves state unchanged. Scores are NaN before t0. The release statistic is calibrated later in decision.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .factor import Adjusted


@dataclass
class DetectorOutput:
    method: str
    score: np.ndarray                 # (T,) release score, NaN before t0
    elig: np.ndarray                  # (T,) bool
    host_score: np.ndarray | None     # (T, nc) per-host ranking score
    host_prob: np.ndarray | None = None   # (T, nc) Pr(a_it > kappa) for SSMs
    runtime_ms: float = 0.0
    params: dict | None = None
    update_times_ms: np.ndarray | None = None


def _z(adj: Adjusted) -> np.ndarray:
    return adj.r / adj.sigma[None]


def _timed(fn):
    def wrap(*a, **k):
        t = time.perf_counter(); out = fn(*a, **k)
        out.runtime_ms = 1000 * (time.perf_counter() - t) / max(len(out.score) - a[0].t0, 1)
        return out
    return wrap


@_timed
def adjusted_cusum(adj: Adjusted, k: float = 0.25) -> DetectorOutput:
    z = _z(adj); T, n = z.shape
    C = np.zeros(n); host = np.full((T, n), np.nan)
    for t in range(adj.t0, T):
        ok = np.isfinite(z[t])
        C[ok] = np.maximum(0.0, C[ok] + z[t, ok] - k)
        host[t] = C
    score = np.where(np.arange(T) >= adj.t0, np.nanmax(host, axis=1, initial=-np.inf), np.nan)
    score[:adj.t0] = np.nan
    return DetectorOutput("adj_cusum", score, adj.elig, host, params={"k": k})


@_timed
def topk_cusum(adj: Adjusted, K: int = 3, k: float = 0.25) -> DetectorOutput:
    host = _cusum_hosts(adj, k)
    srt = -np.sort(-np.nan_to_num(host, nan=0.0), axis=1)
    score = srt[:, :K].sum(1); score[:adj.t0] = np.nan
    return DetectorOutput("topk_cusum", score, adj.elig, host, params={"K": K, "k": k})


def _cusum_hosts(adj: Adjusted, k: float) -> np.ndarray:
    z = _z(adj); T, n = z.shape
    C = np.zeros(n); host = np.full((T, n), np.nan)
    for t in range(adj.t0, T):
        ok = np.isfinite(z[t])
        C[ok] = np.maximum(0.0, C[ok] + z[t, ok] - k)
        host[t] = C
    return host


@_timed
def adjusted_ewma(adj: Adjusted, alpha: float = 0.2) -> DetectorOutput:
    z = _z(adj); T, n = z.shape
    # healthy scale of the EWMA from the pre-period run (skip a short warm-up)
    S = np.zeros(n); pre = np.full((adj.t0, n), np.nan)
    for t in range(adj.t0):
        ok = np.isfinite(z[t]); S[ok] = alpha * z[t, ok] + (1 - alpha) * S[ok]; pre[t] = S
    sd = np.maximum(np.nanstd(pre[20:], axis=0), 1e-6)
    S = np.zeros(n); host = np.full((T, n), np.nan)
    for t in range(adj.t0, T):
        ok = np.isfinite(z[t]); S[ok] = alpha * z[t, ok] + (1 - alpha) * S[ok]
        host[t] = S / sd
    score = np.nanmax(np.where(np.isnan(host), -np.inf, host), axis=1)
    score[:adj.t0] = np.nan
    return DetectorOutput("adj_ewma", score, adj.elig, host, params={"alpha": alpha})


@_timed
def matched_contrast(adj: Adjusted, window: int = 1) -> DetectorOutput:
    """Class-matched canary-minus-control contrast, standardised on the pre-period; optional trailing window."""
    rm = adj.rm; T, n = rm.shape
    mu = np.nanmean(rm[:adj.t0], axis=0); sd = np.maximum(np.nanstd(rm[:adj.t0], axis=0), 1e-6)
    z = (rm - mu) / sd
    z = np.where(adj.obs, z, np.nan)
    w = max(1, int(window))
    if w == 1:
        host = z
        score = np.nanmean(z, axis=1)
    else:
        host = np.full((T, n), np.nan)
        score = np.full(T, np.nan)
        for t in range(adj.t0, T):
            start = max(adj.t0, t - w + 1)
            sub = z[start:t + 1]
            with np.errstate(invalid="ignore"):
                hm = np.nanmean(sub, axis=0)
                host[t] = hm
                score[t] = float(np.nanmean(hm)) if np.any(np.isfinite(hm)) else np.nan
    score[:adj.t0] = np.nan
    return DetectorOutput("matched_contrast", score, adj.elig, host, params={"window": w})


def config_grid() -> list[tuple[str, dict]]:
    """Predeclared tuning grids, <=24 per family (handbook Section 6)."""
    g = [("adj_ewma", {"alpha": a}) for a in (0.05, 0.2, 0.5)]
    g += [("adj_cusum", {"k": k}) for k in (0.1, 0.25, 0.5)]
    g += [("topk_cusum", {"K": K, "k": k}) for K in (1, 3, 5, 10) for k in (0.1, 0.25, 0.5)]
    g += [("matched_contrast", {"window": 1})]
    return g


def run_baseline(name: str, adj: Adjusted, **p) -> DetectorOutput:
    fn = {"adj_ewma": adjusted_ewma, "adj_cusum": adjusted_cusum, "topk_cusum": topk_cusum,
          "matched_contrast": matched_contrast}[name]
    return fn(adj, **p)
