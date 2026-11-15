"""Alert policy and threshold calibration (handbook Sections 3 and 9).

Primary policy: first eligible score strictly above a method-specific threshold, LATCHED per rollout.
Threshold: order statistic of full-horizon null maxima, k = ceil((B+1)(1-alpha)); infinite if k > B.
Advisory (reversible) policy exists only for the separate flicker experiment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

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
    cal = calibrate_threshold(maxima, alpha)
    m = np.sort(np.asarray(maxima, float)[np.isfinite(maxima)])
    B = len(m)
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
        "n_no_eligible": int(cal["n_no_eligible"]),
        "n_finite_maxima": int(cal["n_finite_maxima"]),
    }


def calibrate_threshold(maxima: np.ndarray, alpha: float = 0.05, strict: bool = False) -> dict:
    M_raw = np.asarray(maxima, float)
    B_total = len(M_raw)
    finite_mask = np.isfinite(M_raw) & (~np.isneginf(M_raw))
    n_no_eligible = int(np.sum(~finite_mask))
    n_finite_maxima = int(np.sum(finite_mask))

    min_B = min_B_for_alpha(alpha)
    if strict and n_finite_maxima < min_B:
        raise ValueError(f"insufficient valid nulls ({n_finite_maxima} < {min_B}) for alpha={alpha}")

    valid_M = np.sort(M_raw[finite_mask])
    B_valid = len(valid_M)
    k = math.ceil((B_valid + 1) * (1.0 - alpha))
    thr = float("inf") if k > B_valid else float(valid_M[k - 1])
    return {
        "threshold": thr,
        "k": k,
        "B": B_valid,
        "alpha": alpha,
        "ties_at_threshold": int((valid_M == thr).sum()) if np.isfinite(thr) else 0,
        "n_no_eligible": n_no_eligible,
        "n_finite_maxima": n_finite_maxima,
        "B_total": B_total,
    }


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


@dataclass
class MultiChannelAlertPolicy:
    """Multi-channel alert decision rule combining Latency and Memory channels."""
    threshold_lat: float
    threshold_mem: float
    require_persistence: bool = True
    alpha: float = 0.05
    disclaimer: str = (
        "Multi-channel policy: Latency and Memory channels are separately evaluated. "
        "Cross-metric covariance is treated separately rather than assuming joint dynamics."
    )

    def evaluate_step(
        self,
        score_lat: float,
        score_mem: float,
        guardrail_status: str = "NORMAL",
        is_persistent_mem: bool = False,
        eligible: bool = True,
    ) -> dict[str, Any]:
        """Evaluate multi-channel alert and determine attribution at a single tick."""
        if not eligible or not (np.isfinite(score_lat) or np.isfinite(score_mem)):
            return {
                "is_alert": False,
                "advisory": "RUNNING",
                "attribution": "INSUFFICIENT_DATA",
                "score_lat": score_lat,
                "score_mem": score_mem,
                "threshold_lat": self.threshold_lat,
                "threshold_mem": self.threshold_mem,
                "guardrail_status": guardrail_status,
                "is_persistent_mem": is_persistent_mem,
            }

        lat_breach = np.isfinite(score_lat) and (score_lat > self.threshold_lat)
        mem_score_breach = np.isfinite(score_mem) and (score_mem > self.threshold_mem)
        mem_breach = mem_score_breach and (is_persistent_mem if self.require_persistence else True)
        oom_risk = (guardrail_status == "CRITICAL_OOM_RISK")

        is_alert = lat_breach or mem_breach or oom_risk

        if oom_risk:
            attribution = "CRITICAL_CAPACITY_LIMIT"
            advisory = "CRITICAL_OOM_RISK"
        elif lat_breach and mem_breach:
            attribution = "COMPOUND_REGRESSION"
            advisory = "PAUSE RECOMMENDED"
        elif lat_breach:
            attribution = "LATENCY_REGRESSION"
            advisory = "PAUSE RECOMMENDED"
        elif mem_breach:
            attribution = "MEMORY_GROWTH_LEAK"
            advisory = "PAUSE RECOMMENDED"
        else:
            attribution = "NORMAL"
            advisory = "RUNNING"

        return {
            "is_alert": is_alert,
            "advisory": advisory,
            "attribution": attribution,
            "score_lat": float(score_lat),
            "score_mem": float(score_mem),
            "threshold_lat": float(self.threshold_lat),
            "threshold_mem": float(self.threshold_mem),
            "lat_breach": bool(lat_breach),
            "mem_breach": bool(mem_breach),
            "mem_score_breach": bool(mem_score_breach),
            "is_persistent_mem": bool(is_persistent_mem),
            "guardrail_status": guardrail_status,
            "disclaimer": self.disclaimer,
        }


def calibrate_multichannel_policy(
    null_lat_maxima: np.ndarray,
    null_mem_maxima: np.ndarray,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Calibrate joint latency and memory thresholds on healthy null data to bound FWER <= alpha.

    Uses Bonferroni-Šidák split: alpha_channel = 1 - sqrt(1 - alpha) approx alpha / 2.
    """
    lat_m = np.asarray(null_lat_maxima, float)
    mem_m = np.asarray(null_mem_maxima, float)
    B = len(lat_m)
    if B != len(mem_m):
        raise ValueError(f"Mismatched sample sizes: {B} vs {len(mem_m)}")

    alpha_channel = 1.0 - math.sqrt(max(1.0 - alpha, 0.0))
    cal_lat = calibrate_threshold(lat_m, alpha_channel)
    cal_mem = calibrate_threshold(mem_m, alpha_channel)

    thr_lat = cal_lat["threshold"]
    thr_mem = cal_mem["threshold"]

    # Empirical false alert rate under joint policy
    joint_false_alarms = np.sum((lat_m > thr_lat) | (mem_m > thr_mem))
    achieved_far = float(joint_false_alarms) / float(B) if B > 0 else 0.0

    return {
        "threshold_lat": thr_lat,
        "threshold_mem": thr_mem,
        "alpha_budget": alpha,
        "alpha_channel": alpha_channel,
        "achieved_far": achieved_far,
        "calibration_successful": bool(achieved_far <= alpha),
        "B": B,
        "cal_lat": cal_lat,
        "cal_mem": cal_mem,
        "policy": MultiChannelAlertPolicy(threshold_lat=thr_lat, threshold_mem=thr_mem, alpha=alpha),
    }
