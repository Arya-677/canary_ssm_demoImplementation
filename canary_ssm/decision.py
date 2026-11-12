"""Alert policy and threshold calibration (handbook Sections 3 and 9).

Primary policy: first eligible score strictly above a method-specific threshold, LATCHED per rollout.
Threshold: order statistic of full-horizon null maxima, k = ceil((B+1)(1-alpha)); infinite if k > B.
Advisory (reversible) policy exists only for the separate flicker experiment.
"""
from __future__ import annotations

import math

import numpy as np

NORMAL, PAUSE, UNKNOWN = 0, 1, 2


def release_max(score: np.ndarray, elig: np.ndarray, t0: int) -> float:
    """Largest ELIGIBLE score at or after rollout time; -inf if never eligible."""
    s = np.where(elig & np.isfinite(score), score, -np.inf)
    s[:t0] = -np.inf
    return float(s.max())


def calibrate_threshold(maxima: np.ndarray, alpha: float = 0.05) -> dict:
    M = np.sort(np.asarray(maxima, float)); B = len(M)
    k = math.ceil((B + 1) * (1 - alpha))
    thr = float("inf") if k > B else float(M[k - 1])
    return {"threshold": thr, "k": k, "B": B, "alpha": alpha, "ties_at_threshold": int((M == thr).sum())}


def first_alarm(score: np.ndarray, elig: np.ndarray, thr: float, t0: int) -> int | None:
    ok = elig & np.isfinite(score) & (score > thr)         # strict inequality
    ok[:t0] = False
    idx = np.flatnonzero(ok)
    return int(idx[0]) if idx.size else None


def advisory_replay(score, elig, t0, h_on, h_off, n_clear: int = 5) -> dict:
    """NORMAL -> PAUSE when score > h_on; PAUSE -> NORMAL after n_clear consecutive eligible scores < h_off;
    ineligible minutes are reported UNKNOWN and reset the clear counter (mode is retained)."""
    mode, clear = NORMAL, 0
    states = np.full(len(score), -1); reversals = 0; first_pause = None
    for t in range(t0, len(score)):
        if not (elig[t] and np.isfinite(score[t])):
            states[t] = UNKNOWN; clear = 0; continue
        if mode == NORMAL and score[t] > h_on:
            mode = PAUSE; reversals += 1; clear = 0
            first_pause = t if first_pause is None else first_pause
        elif mode == PAUSE:
            clear = clear + 1 if score[t] < h_off else 0
            if clear >= n_clear:
                mode = NORMAL; reversals += 1; clear = 0
        states[t] = mode
    return {"states": states, "reversals": reversals, "time_paused": int((states == PAUSE).sum()),
            "first_pause": first_pause}


def calibrate_advisory(null_scores: list, null_elig: list, t0: int, alpha: float = 0.05,
                       hyst_frac: float = 0.5) -> dict:
    """h_on from the one-crossing rule (so first-pause rate on nulls is <= alpha); h_off set below it by a
    development-chosen fraction of the gap to the median null score. The full policy is then replayed."""
    maxima = [release_max(s, e, t0) for s, e in zip(null_scores, null_elig)]
    c = calibrate_threshold(np.array(maxima), alpha)
    allv = np.concatenate([s[t0:][e[t0:] & np.isfinite(s[t0:])] for s, e in zip(null_scores, null_elig)])
    med = float(np.median(allv)) if allv.size else 0.0
    h_on = c["threshold"]
    h_off = h_on - hyst_frac * (h_on - med) if np.isfinite(h_on) else h_on
    return {"h_on": h_on, "h_off": float(h_off), "hyst_frac": hyst_frac, "n_clear": 5, "base": c}
