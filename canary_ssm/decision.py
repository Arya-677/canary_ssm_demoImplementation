"""Alert policy and threshold calibration (handbook Sections 3 and 9).

Primary policy: first eligible score strictly above a method-specific threshold, LATCHED per rollout.
Threshold: order statistic of full-horizon null maxima, k = ceil((B+1)(1-alpha)); infinite if k > B.
Advisory (reversible) policy exists only for the separate flicker experiment.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import beta

NORMAL, PAUSE, UNKNOWN = 0, 1, 2


def release_max(score: np.ndarray, elig: np.ndarray, t0: int, horizon: int | None = None) -> float:
    """Largest ELIGIBLE score in [t0, t0 + horizon); -inf if never eligible."""
    end = len(score) if horizon is None else min(len(score), int(t0) + int(horizon))
    s = np.where(elig[:end] & np.isfinite(score[:end]), score[:end], -np.inf)
    s[:t0] = -np.inf
    return float(s.max())


def min_B_for_alpha(alpha: float) -> int:
    """Smallest sample size B where order statistic k = ceil((B+1)(1-alpha)) <= B (WP-C6)."""
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    return int(math.ceil((1.0 - alpha) / alpha))


def thresholds_for_alpha(
    maxima: np.ndarray,
    alphas: tuple[float, ...] = (0.01, 0.02, 0.05, 0.10),
) -> dict[str, dict]:
    """Compute exact order-statistic thresholds for multiple significance levels (WP-C2)."""
    return {f"{a}": calibrate_threshold(maxima, float(a)) for a in alphas}


def threshold_uncertainty(
    maxima: np.ndarray,
    alpha: float = 0.05,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Order-statistic threshold sampling uncertainty & exact Beta quantiles for achieved FAR (WP-C2)."""
    m = np.sort(np.asarray(maxima, float))
    B = len(m)
    cal = calibrate_threshold(m, alpha)
    k = int(cal["k"])
    rng = np.random.default_rng(seed)
    boot_thrs = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        draw = np.sort(m[rng.integers(0, B, size=B)])
        boot_thrs[i] = float("inf") if k > B else float(draw[k - 1])
    finite_b = boot_thrs[np.isfinite(boot_thrs)]
    boot_lo = float(np.quantile(finite_b, 0.025)) if finite_b.size else float("inf")
    boot_hi = float(np.quantile(finite_b, 0.975)) if finite_b.size else float("inf")

    if k > B:
        far_lo, far_hi, a_b, b_b = 0.0, 0.0, 0, B
    else:
        a_b, b_b = int(B + 1 - k), int(k)
        far_lo = float(beta.ppf(0.025, a_b, b_b))
        far_hi = float(beta.ppf(0.975, a_b, b_b))
    return {
        "alpha": float(alpha),
        "B": int(B),
        "k": k,
        "threshold": cal["threshold"],
        "boot_lo": boot_lo,
        "boot_hi": boot_hi,
        "far_beta_lo": far_lo,
        "far_beta_hi": far_hi,
        "beta_a": a_b,
        "beta_b": b_b,
    }


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


# ======================================================================================================
# V3: decision-level inertia (Addendum B1, Mechanism 3). Kept separate from latent-state dynamics.
#
# "Pause only after m consecutive eligible minutes above h" is EXACTLY the one-crossing rule applied to the
# running-minimum score  s_m(t) = min(score[t-m+1..t])  (valid only when all m minutes are eligible and finite).
# Because s_m is a causal, deterministic function of the score path, its full-horizon maximum is exchangeable
# across null rollouts exactly like the raw maximum, so the existing order-statistic calibration is exact for it.
# m = 1 reproduces the legacy score bit-for-bit. Recovery hysteresis only changes what happens AFTER the first
# pause (reversals, time paused); it cannot change the first-pause false-alert rate.
# ======================================================================================================
def persist_score(score: np.ndarray, elig: np.ndarray, t0: int, m: int = 1,
                  emergency_offset: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (s, valid): running minimum over the last `m` minutes, NaN unless all m minutes are >= t0, eligible
    and finite (an ineligible minute breaks the run: conservative). `emergency_offset` (>= 0) adds an escalation
    path: s(t) = max(s_m(t), score(t) - offset), valid whenever minute t itself is eligible, so a severe single
    minute can still pause. Offset is predeclared, never tuned on validation/test data."""
    m = int(m)
    if m < 1:
        raise ValueError("m must be >= 1")
    if emergency_offset is not None and emergency_offset < 0:
        raise ValueError("emergency_offset must be >= 0")
    score = np.asarray(score, float); T = len(score)
    ok = np.asarray(elig, bool) & np.isfinite(score)
    ok[:t0] = False
    s = np.full(T, np.nan)
    for t in range(t0 + m - 1, T):
        w = slice(t - m + 1, t + 1)
        if ok[w].all():
            s[t] = float(score[w].min())
    valid = np.isfinite(s)
    if emergency_offset is not None:
        em = np.where(ok, score - float(emergency_offset), np.nan)
        s = np.fmax(s, em)                      # fmax ignores NaN
        valid = ok.copy()
    return s, valid


def persistence_maxima(null_scores: list, null_elig: list, t0: int, m: int = 1,
                       emergency_offset: float | None = None) -> np.ndarray:
    out = []
    for sc, el in zip(null_scores, null_elig):
        s, v = persist_score(sc, el, t0, m, emergency_offset)
        out.append(release_max(s, v, t0))
    return np.array(out, float)


def calibrate_persistence(null_scores: list, null_elig: list, t0: int, m: int = 1, alpha: float = 0.05,
                          n_clear: int = 5, hyst_frac: float = 0.5,
                          emergency_offset: float | None = None) -> dict:
    """Order-statistic threshold for the persistence-filtered score plus the (predeclared, untuned) exit level."""
    maxima = persistence_maxima(null_scores, null_elig, t0, m, emergency_offset)
    base = calibrate_threshold(maxima, alpha)
    allv = np.concatenate([sc[t0:][el[t0:] & np.isfinite(sc[t0:])] for sc, el in zip(null_scores, null_elig)])
    med = float(np.median(allv)) if allv.size else 0.0
    h_on = base["threshold"]
    h_off = h_on - hyst_frac * (h_on - med) if np.isfinite(h_on) else h_on
    return {"h_on": h_on, "h_off": float(h_off), "m_on": int(m), "n_clear": int(n_clear), "hyst_frac": float(hyst_frac),
            "emergency_offset": emergency_offset, "base": base}


def replay_policy(score: np.ndarray, elig: np.ndarray, t0: int, h_on: float, h_off: float, m_on: int = 1,
                  n_clear: int = 5, emergency_offset: float | None = None) -> dict:
    """Full reversible policy replay. NORMAL -> PAUSE when the persistence-filtered score exceeds h_on;
    PAUSE -> NORMAL after n_clear consecutive eligible RAW scores below h_off. Ineligible minutes are UNKNOWN,
    keep the mode and reset the clear counter. Detector-side only: it never sees truth."""
    score = np.asarray(score, float)
    s, valid = persist_score(score, elig, t0, m_on, emergency_offset)
    mode, clear = NORMAL, 0
    states = np.full(len(score), -1); reversals = 0; first_pause = None; episodes = 0
    for t in range(t0, len(score)):
        if not (elig[t] and np.isfinite(score[t])):
            states[t] = UNKNOWN; clear = 0; continue
        if mode == NORMAL and valid[t] and s[t] > h_on:
            mode = PAUSE; reversals += 1; episodes += 1; clear = 0
            first_pause = t if first_pause is None else first_pause
        elif mode == PAUSE:
            clear = clear + 1 if score[t] < h_off else 0
            if clear >= n_clear:
                mode = NORMAL; reversals += 1; clear = 0
        states[t] = mode
    return {"states": states, "reversals": reversals, "time_paused": int((states == PAUSE).sum()),
            "first_pause": first_pause, "pause_episodes": episodes}
