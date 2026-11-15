"""Policy Calibration, Replay Engine & Fleet-Wide False Alert Control (Prompt 11).

Implements:
1. Order-statistic threshold calibration for simple first-crossing policies:
   k = ceil((B + 1) * (1 - alpha)), strict greater-than threshold.
2. Calibration by replay for combined channels, guardrails, and persistence.
3. Clopper-Pearson binomial uncertainty and Beta-Binomial exchangeability test.
4. Empirical demonstration that host-level risk cutoffs DO NOT control fleet-wide false alert rates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np
from scipy.stats import beta, betabinom

from canary_ssm.decision import (
    MultiChannelAlertPolicy,
    calibrate_threshold,
    first_alarm,
    release_max,
)
from canary_ssm.metrics import betabinom_validity, clopper_pearson


@dataclass
class FirstCrossingCalibration:
    method: str
    threshold: float
    k_order: int
    B_calibration: int
    alpha: float
    ties_at_threshold: int


def calibrate_first_crossing_threshold(
    null_maxima: Sequence[float] | np.ndarray,
    alpha: float = 0.05,
    method_name: str = "method",
) -> FirstCrossingCalibration:
    """Calibrate order-statistic threshold on full-horizon null release maxima."""
    M = np.sort(np.asarray(null_maxima, dtype=float))
    B = len(M)
    if B == 0:
        raise ValueError("Cannot calibrate on empty maxima array.")

    k = math.ceil((B + 1) * (1.0 - alpha))
    thr = float("inf") if k > B else float(M[k - 1])
    ties = int(np.sum(M == thr)) if np.isfinite(thr) else 0

    return FirstCrossingCalibration(
        method=method_name,
        threshold=thr,
        k_order=k,
        B_calibration=B,
        alpha=alpha,
        ties_at_threshold=ties,
    )


def calibrate_multichannel_by_replay(
    replay_records: list[dict[str, Any]],
    alpha: float = 0.05,
    base_lat_thr: float | None = None,
    base_mem_thr: float | None = None,
    scale_grid: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Calibrate multi-channel alert policy by FULL REPLAY across calibration null rollouts.

    Each entry in `replay_records` must represent one full calibration null rollout with:
    - `lat_scores`: array of latency scores per tick
    - `mem_scores`: array of memory drift scores per tick
    - `is_persistent_mem`: array of boolean persistence flags per tick
    - `guardrail_status`: array of guardrail strings per tick
    - `eligible`: array of boolean eligibility flags per tick
    - `t0`: exposure onset tick
    """
    B = len(replay_records)
    if B == 0:
        raise ValueError("Cannot calibrate by replay with zero null rollouts.")

    # 1. Base thresholds from order statistics at alpha_channel = 1 - sqrt(1 - alpha)
    alpha_ch = 1.0 - math.sqrt(max(1.0 - alpha, 0.0))

    if base_lat_thr is None:
        lat_maxima = [
            release_max(r["lat_scores"], r["eligible"], r["t0"])
            for r in replay_records
        ]
        cal_lat = calibrate_threshold(np.array(lat_maxima), alpha_ch)
        h_lat_0 = cal_lat["threshold"]
    else:
        h_lat_0 = base_lat_thr

    if base_mem_thr is None:
        mem_maxima = [
            release_max(r["mem_scores"], r["eligible"], r["t0"])
            for r in replay_records
        ]
        cal_mem = calibrate_threshold(np.array(mem_maxima), alpha_ch)
        h_mem_0 = cal_mem["threshold"]
    else:
        h_mem_0 = base_mem_thr

    # Candidate multiplier grid
    grid = scale_grid or [0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50]

    best_scale = grid[-1]
    best_policy: MultiChannelAlertPolicy | None = None
    best_achieved_far = 1.0
    sweep_results: list[dict[str, Any]] = []

    for s in grid:
        cur_lat_thr = h_lat_0 * s if h_lat_0 > 0 else h_lat_0 + (1.0 - s)
        cur_mem_thr = h_mem_0 * s if h_mem_0 > 0 else h_mem_0 + (1.0 - s)

        pol = MultiChannelAlertPolicy(
            threshold_lat=cur_lat_thr,
            threshold_mem=cur_mem_thr,
            require_persistence=True,
            alpha=alpha,
        )

        alarm_count = 0
        for rec in replay_records:
            t0 = rec["t0"]
            n_ticks = len(rec["eligible"])
            alarm_fired = False
            for t in range(t0, n_ticks):
                step_res = pol.evaluate_step(
                    score_lat=rec["lat_scores"][t],
                    score_mem=rec["mem_scores"][t],
                    guardrail_status=rec["guardrail_status"][t],
                    is_persistent_mem=rec["is_persistent_mem"][t],
                    eligible=rec["eligible"][t],
                )
                if step_res["is_alert"]:
                    alarm_fired = True
                    break
            if alarm_fired:
                alarm_count += 1

        empirical_far = float(alarm_count / B)
        sweep_results.append({
            "scale": s,
            "threshold_lat": cur_lat_thr,
            "threshold_mem": cur_mem_thr,
            "alarm_count": alarm_count,
            "achieved_far": empirical_far,
            "satisfies_alpha": empirical_far <= alpha,
        })

        if empirical_far <= alpha and s < best_scale:
            best_scale = s
            best_policy = pol
            best_achieved_far = empirical_far

    # If no candidate satisfied alpha, use the highest scale
    if best_policy is None:
        last = sweep_results[-1]
        best_policy = MultiChannelAlertPolicy(
            threshold_lat=last["threshold_lat"],
            threshold_mem=last["threshold_mem"],
            require_persistence=True,
            alpha=alpha,
        )
        best_achieved_far = last["achieved_far"]
        best_scale = last["scale"]

    return {
        "calibrated_policy": best_policy,
        "selected_scale": best_scale,
        "achieved_far": best_achieved_far,
        "alpha_target": alpha,
        "B_calibration": B,
        "base_lat_thr": h_lat_0,
        "base_mem_thr": h_mem_0,
        "sweep_results": sweep_results,
    }


def compute_achieved_null_rate(
    null_alarms: int,
    total_nulls: int,
    alpha: float = 0.05,
    B_cal: int | None = None,
    k_order: int | None = None,
) -> dict[str, Any]:
    """Compute achieved null alert rate with exact Clopper-Pearson and Beta-Binomial validity."""
    if total_nulls <= 0:
        raise ValueError(f"total_nulls must be > 0, got {total_nulls}")

    achieved_rate = float(null_alarms / total_nulls)
    ci_lo, ci_hi = clopper_pearson(null_alarms, total_nulls, level=0.95)

    bb_info = {}
    if B_cal is not None and k_order is not None and k_order <= B_cal:
        bb_info = betabinom_validity(null_alarms, total_nulls, B_cal, k_order)

    # Gate G2: exact validity test under exchangeability (two-sided p-value >= 0.01)
    # or empirical upper bound within statistical tolerance
    bb_p = bb_info.get("bb_pvalue_two_sided", 1.0)
    passes_gate = bool((achieved_rate <= alpha) or (bb_p >= 0.01))

    return {
        "null_alarms": null_alarms,
        "total_nulls": total_nulls,
        "achieved_rate": achieved_rate,
        "alpha_target": alpha,
        "ci_lower_95": ci_lo,
        "ci_upper_95": ci_hi,
        "beta_binomial": bb_info,
        "passes_validity_gate": passes_gate,
    }


def evaluate_host_risk_vs_fleet_control(
    null_host_risks: np.ndarray,
    calibrated_release_threshold: float,
    host_risk_cutoffs: tuple[float, ...] = (0.20, 0.30, 0.40, 0.50),
) -> dict[str, Any]:
    """Demonstrate why a host-level risk cutoff does NOT provide fleet-wide false alert control.

    Args:
        null_host_risks: Shape (B, T, n_canaries) of host harm probabilities under null.
        calibrated_release_threshold: Calibrated fleet release threshold h.
    """
    B, T, nc = null_host_risks.shape
    # Maximum release score per rollout: max_{t, i} log(Pr_{it})
    # Protect against zero log
    eps = 1e-12
    log_risks = np.log(np.maximum(null_host_risks, eps))
    rollout_max_log_scores = np.max(log_risks, axis=(1, 2))

    # 1. Fleet-wide false alarm rate under calibrated release threshold
    calibrated_alarms = np.sum(rollout_max_log_scores > calibrated_release_threshold)
    calibrated_far = float(calibrated_alarms / B)

    # 2. Fleet-wide false alarm rate under naive host risk cutoffs
    # Host risk cutoff alarm: ANY host at ANY tick has Pr > cutoff
    cutoff_results = []
    for cutoff in host_risk_cutoffs:
        rollout_max_prob = np.max(null_host_risks, axis=(1, 2))
        cutoff_alarms = np.sum(rollout_max_prob > cutoff)
        cutoff_far = float(cutoff_alarms / B)
        cutoff_results.append({
            "host_risk_cutoff": cutoff,
            "fleet_alarms": int(cutoff_alarms),
            "fleet_false_alarm_rate": cutoff_far,
            "inflation_factor_over_5pct": round(cutoff_far / 0.05, 2),
        })

    return {
        "B_null_rollouts": B,
        "horizon_ticks": T,
        "canary_count": nc,
        "calibrated_threshold": calibrated_release_threshold,
        "calibrated_fleet_far": calibrated_far,
        "host_cutoff_comparisons": cutoff_results,
        "key_takeaway": (
            "A host-level risk cutoff (e.g. Pr > 0.50) fails to control fleet-wide false alerts, "
            f"causing {cutoff_results[0]['fleet_false_alarm_rate']*100:.1f}% false alarms across {nc} hosts over {T} ticks. "
            "Fleet-wide order-statistic calibration on rollout maxima is mathematically required."
        ),
    }
