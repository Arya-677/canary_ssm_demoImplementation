"""Evaluator-Side Metric Fixtures, Truth Labels & Statistical Contrasts (Prompt 11).

STRICT ANTI-LEAKAGE FIREWALL:
This module contains ground truth classification, hand-labeled metric fixtures,
and evaluator-only metrics. Detector and inference code must NEVER import or read it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

import numpy as np
from scipy.stats import rankdata


class EventLabel(str, Enum):
    """Declared, distinct evaluator event labels across all telemetry channels."""
    NO_EVENT = "NO_EVENT"
    HEALTHY_GC_CYCLES = "HEALTHY_GC_CYCLES"
    HARM_LATENCY_PERSISTENT = "HARM_LATENCY_PERSISTENT"
    HARM_MEMORY_GROWTH = "HARM_MEMORY_GROWTH"
    HARM_CPU_SATURATION = "HARM_CPU_SATURATION"
    HARM_ERROR_REGRESSION = "HARM_ERROR_REGRESSION"
    HARM_COMPOUND = "HARM_COMPOUND"
    FAULT_RACK_LATENCY = "FAULT_RACK_LATENCY"
    FAULT_FLEET_DEMAND = "FAULT_FLEET_DEMAND"


@dataclass
class MultiMetricEventTruth:
    """Evaluator-only ground truth representation of multi-metric rollout events."""
    has_event: bool
    event_label: EventLabel
    onset: int | None
    intervals: list[tuple[int, int]]  # Contiguous active [start, end) intervals
    affected_canary_ids: list[str]
    transient: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return list of (start_idx, end_idx_exclusive) for contiguous True runs."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for t, val in enumerate(mask):
        if val and start is None:
            start = t
        elif not val and start is not None:
            runs.append((start, t))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def evaluate_event_truth(
    a_latency: np.ndarray | None = None,
    memory_drift: np.ndarray | None = None,
    cpu_values: np.ndarray | None = None,
    error_rates: np.ndarray | None = None,
    canary_ids: list[str] | None = None,
    kappa_lat: float = 0.0198026,       # log(1.02)
    kappa_mem: float = 0.50,            # 0.50 MB/min (distinct from log latency!)
    kappa_cpu: float = 0.85,            # 85% CPU saturation
    kappa_err: float = 0.05,            # 5% error rate
    d_min: int = 15,                    # Minimum persistence duration (ticks)
    fault_type: str | None = None,
) -> MultiMetricEventTruth:
    """Construct multi-metric event truth from latent arrays. Evaluator only."""
    canaries = canary_ids or []
    nc = len(canaries)

    # 1. Latency Persistent Harm Check
    lat_affected: set[str] = set()
    lat_intervals: list[tuple[int, int]] = []
    any_lat_transient = False
    if a_latency is not None and a_latency.size > 0:
        for i in range(min(nc, a_latency.shape[1])):
            mask = a_latency[:, i] > kappa_lat
            runs = _contiguous_runs(mask)
            for s, e in runs:
                if e - s >= d_min:
                    lat_affected.add(canaries[i])
                    lat_intervals.append((s, e))
                else:
                    any_lat_transient = True

    # 2. Memory Growth Harm Check (Declared separate boundary: kappa_mem = 0.50 MB/min)
    mem_affected: set[str] = set()
    mem_intervals: list[tuple[int, int]] = []
    any_mem_transient = False
    if memory_drift is not None and memory_drift.size > 0:
        for i in range(min(nc, memory_drift.shape[1])):
            mask = memory_drift[:, i] >= kappa_mem
            runs = _contiguous_runs(mask)
            for s, e in runs:
                if e - s >= d_min:
                    mem_affected.add(canaries[i])
                    mem_intervals.append((s, e))
                else:
                    any_mem_transient = True

    # 3. CPU Saturation Check
    cpu_affected: set[str] = set()
    cpu_intervals: list[tuple[int, int]] = []
    if cpu_values is not None and cpu_values.size > 0:
        for i in range(min(nc, cpu_values.shape[1])):
            mask = cpu_values[:, i] >= kappa_cpu
            runs = _contiguous_runs(mask)
            for s, e in runs:
                if e - s >= d_min:
                    cpu_affected.add(canaries[i])
                    cpu_intervals.append((s, e))

    # 4. Error Regression Check
    err_affected: set[str] = set()
    err_intervals: list[tuple[int, int]] = []
    if error_rates is not None and error_rates.size > 0:
        for i in range(min(nc, error_rates.shape[1])):
            mask = error_rates[:, i] >= kappa_err
            runs = _contiguous_runs(mask)
            for s, e in runs:
                if e - s >= d_min:
                    err_affected.add(canaries[i])
                    err_intervals.append((s, e))

    # Determine Event Classification
    has_lat = bool(lat_affected)
    has_mem = bool(mem_affected)
    has_cpu = bool(cpu_affected)
    has_err = bool(err_affected)

    all_intervals: list[tuple[int, int]] = sorted(lat_intervals + mem_intervals + cpu_intervals + err_intervals)
    all_affected = sorted(lat_affected | mem_affected | cpu_affected | err_affected)
    onset = min(s for s, _ in all_intervals) if all_intervals else None

    # Infrastructure faults without canary-specific divergence
    if fault_type == "RACK_NETWORK_LATENCY":
        return MultiMetricEventTruth(
            has_event=False,
            event_label=EventLabel.FAULT_RACK_LATENCY,
            onset=None,
            intervals=[],
            affected_canary_ids=[],
            transient=False,
            metadata={"fault_type": fault_type},
        )
    elif fault_type == "FLEET_DEMAND_SPIKE":
        return MultiMetricEventTruth(
            has_event=False,
            event_label=EventLabel.FAULT_FLEET_DEMAND,
            onset=None,
            intervals=[],
            affected_canary_ids=[],
            transient=False,
            metadata={"fault_type": fault_type},
        )
    elif fault_type == "HEALTHY_GC":
        return MultiMetricEventTruth(
            has_event=False,
            event_label=EventLabel.HEALTHY_GC_CYCLES,
            onset=None,
            intervals=[],
            affected_canary_ids=[],
            transient=False,
            metadata={"fault_type": fault_type},
        )

    # Multi-metric / Compound classification
    active_count = sum([has_lat, has_mem, has_cpu, has_err])
    if active_count >= 2:
        lbl = EventLabel.HARM_COMPOUND
    elif has_lat:
        lbl = EventLabel.HARM_LATENCY_PERSISTENT
    elif has_mem:
        lbl = EventLabel.HARM_MEMORY_GROWTH
    elif has_cpu:
        lbl = EventLabel.HARM_CPU_SATURATION
    elif has_err:
        lbl = EventLabel.HARM_ERROR_REGRESSION
    else:
        lbl = EventLabel.NO_EVENT

    return MultiMetricEventTruth(
        has_event=(lbl != EventLabel.NO_EVENT),
        event_label=lbl,
        onset=onset,
        intervals=all_intervals,
        affected_canary_ids=all_affected,
        transient=(any_lat_transient or any_mem_transient) and (lbl == EventLabel.NO_EVENT),
        metadata={
            "lat_affected": sorted(lat_affected),
            "mem_affected": sorted(mem_affected),
            "cpu_affected": sorted(cpu_affected),
            "err_affected": sorted(err_affected),
        },
    )


def classify_run(
    t_alarm: int | None,
    truth: MultiMetricEventTruth,
    total_ticks: int,
    exposure_tick: int,
) -> dict[str, Any]:
    """Outcome classification of one rollout. Evaluator only.

    Follows handbook Sections 3 and 10:
    - Misses, premature alarms, and late alarms after recovery receive capped follow-up time.
    - Successes receive onset-relative delay.
    """
    if not truth.has_event:
        return {
            "kind": "null",
            "event_label": truth.event_label.value,
            "alarm": t_alarm is not None,
            "status": "false_alarm" if t_alarm is not None else "quiet",
            "delay": np.nan,
            "capped_time": np.nan,
            "is_correct": t_alarm is None,
            "followup": total_ticks - exposure_tick,
        }

    onset = truth.onset if truth.onset is not None else exposure_tick
    remaining_followup = float(total_ticks - onset)

    if t_alarm is None:
        status = "miss"
        delay = np.nan
        capped = remaining_followup
        is_correct = False
    elif t_alarm < onset:
        status = "premature"
        delay = np.nan
        capped = remaining_followup
        is_correct = False
    elif any(s <= t_alarm < e for s, e in truth.intervals):
        status = "success"
        delay = float(t_alarm - onset)
        capped = float(t_alarm - onset)
        is_correct = True
    else:
        status = "late_after_recovery"
        delay = np.nan
        capped = remaining_followup
        is_correct = False

    return {
        "kind": "event",
        "event_label": truth.event_label.value,
        "alarm": t_alarm is not None,
        "status": status,
        "delay": delay,
        "capped_time": capped,
        "is_correct": is_correct,
        "followup": remaining_followup,
    }


def compute_localization(
    host_scores: dict[str, float] | np.ndarray,
    true_affected: list[str] | set[str] | Sequence[int],
    canary_order: list[str] | None = None,
    topk: int = 3,
) -> dict[str, float]:
    """Evaluate localization accuracy on affected canary hosts. Evaluator only."""
    if isinstance(host_scores, dict):
        canaries = canary_order or list(host_scores.keys())
        scores = np.array([host_scores.get(c, -np.inf) for c in canaries], dtype=float)
        affected_set = set(true_affected)
        canary_names = canaries
    else:
        scores = np.asarray(host_scores, dtype=float)
        canary_names = canary_order if canary_order is not None else [f"c{i}" for i in range(len(scores))]
        affected_set = {canary_names[i] for i in true_affected} if true_affected and isinstance(list(true_affected)[0], int) else set(true_affected)

    if not affected_set or scores.size == 0 or np.all(np.isnan(scores)):
        return {
            "topk_recall": np.nan,
            "precision": np.nan,
            "recall": np.nan,
            "f1": np.nan,
            "fdp": np.nan,
        }

    # Stable rank descending
    order = np.argsort(-scores, kind="stable")
    top_indices = order[:min(topk, len(order))]
    top_canaries = {canary_names[idx] for idx in top_indices}

    intersect = top_canaries & affected_set
    topk_denom = min(topk, len(affected_set))
    topk_recall = float(len(intersect) / topk_denom) if topk_denom > 0 else 0.0

    k_eff = len(top_indices)
    prec = float(len(intersect) / k_eff) if k_eff > 0 else 0.0
    rec = float(len(intersect) / len(affected_set)) if len(affected_set) > 0 else 0.0
    f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    fdp = float(1.0 - prec)

    return {
        "topk_recall": topk_recall,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "fdp": fdp,
    }


def attribution_confusion_matrix(
    true_labels: list[EventLabel | str],
    inferred_attributions: list[str],
) -> dict[str, Any]:
    """Build confusion matrix of True Scenario vs. Inferred Detector Attribution."""
    categories = [
        "NORMAL",
        "LATENCY_REGRESSION",
        "MEMORY_GROWTH_LEAK",
        "COMPOUND_REGRESSION",
        "INFRASTRUCTURE_FAULT",
        "INSUFFICIENT_DATA",
    ]

    def map_true(lbl: EventLabel | str) -> str:
        s = lbl.value if isinstance(lbl, EventLabel) else str(lbl)
        if s in ("NO_EVENT", "HEALTHY_GC_CYCLES"):
            return "NORMAL"
        elif s == "HARM_LATENCY_PERSISTENT":
            return "LATENCY_REGRESSION"
        elif s == "HARM_MEMORY_GROWTH":
            return "MEMORY_GROWTH_LEAK"
        elif s in ("HARM_COMPOUND", "HARM_CPU_SATURATION", "HARM_ERROR_REGRESSION"):
            return "COMPOUND_REGRESSION"
        elif "FAULT_" in s:
            return "INFRASTRUCTURE_FAULT"
        return "NORMAL"

    matrix: dict[str, dict[str, int]] = {
        true_c: {pred_c: 0 for pred_c in categories}
        for true_c in ["NORMAL", "LATENCY_REGRESSION", "MEMORY_GROWTH_LEAK", "COMPOUND_REGRESSION", "INFRASTRUCTURE_FAULT"]
    }

    abstentions = 0
    total = len(true_labels)
    for t_raw, p_raw in zip(true_labels, inferred_attributions):
        t_cat = map_true(t_raw)
        p_cat = p_raw.upper()
        if p_cat not in categories:
            if "LATENCY" in p_cat:
                p_cat = "LATENCY_REGRESSION"
            elif "MEMORY" in p_cat or "LEAK" in p_cat:
                p_cat = "MEMORY_GROWTH_LEAK"
            elif "COMPOUND" in p_cat:
                p_cat = "COMPOUND_REGRESSION"
            elif "INSUFFICIENT" in p_cat or "CONFLICT" in p_cat:
                p_cat = "INSUFFICIENT_DATA"
            elif "RACK" in p_cat or "OUTAGE" in p_cat or "DEGRADED" in p_cat:
                p_cat = "INFRASTRUCTURE_FAULT"
            else:
                p_cat = "NORMAL"

        if p_cat == "INSUFFICIENT_DATA":
            abstentions += 1

        matrix[t_cat][p_cat] += 1

    abstention_rate = float(abstentions / total) if total > 0 else 0.0

    # Calculate overall attribution accuracy (excluding abstentions)
    diag_sum = sum(matrix[c][c] for c in matrix if c in matrix[c])
    evaluable = total - abstentions
    accuracy = float(diag_sum / evaluable) if evaluable > 0 else 0.0

    return {
        "matrix": matrix,
        "total_rollouts": total,
        "abstention_count": abstentions,
        "abstention_rate": abstention_rate,
        "evaluable_count": evaluable,
        "attribution_accuracy": accuracy,
    }


def paired_bootstrap_contrast(
    metric_a: Sequence[float] | np.ndarray,
    metric_b: Sequence[float] | np.ndarray,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict[str, float]:
    """Paired bootstrap comparison resampling ROLLOUT PAIRS (never timestamps!).

    Computes difference delta = metric_a - metric_b.
    Returns:
    - mean_diff: mean of paired difference
    - ci_lower: 2.5% quantile of bootstrap distribution
    - ci_upper: 97.5% quantile of bootstrap distribution
    - p_value: two-sided bootstrap p-value
    """
    a = np.asarray(metric_a, dtype=float)
    b = np.asarray(metric_b, dtype=float)
    if len(a) != len(b):
        raise ValueError(f"Lengths must match for paired bootstrap: {len(a)} vs {len(b)}")

    diffs = a - b
    valid = np.isfinite(diffs)
    d = diffs[valid]
    n = len(d)
    if n == 0:
        return {
            "mean_diff": np.nan,
            "ci_lower": np.nan,
            "ci_upper": np.nan,
            "p_value": np.nan,
            "n_pairs": 0,
        }

    mean_obs = float(np.mean(d))
    rng = np.random.default_rng(seed)
    boot_indices = rng.integers(0, n, size=(n_boot, n))
    boot_means = np.mean(d[boot_indices], axis=1)

    ci_lo = float(np.percentile(boot_means, 2.5))
    ci_hi = float(np.percentile(boot_means, 97.5))

    # Two-sided empirical p-value for H0: delta = 0
    p_le = np.mean(boot_means <= 0.0)
    p_ge = np.mean(boot_means >= 0.0)
    p_val = float(min(1.0, 2.0 * min(p_le, p_ge)))

    return {
        "mean_diff": mean_obs,
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "p_value": p_val,
        "n_pairs": int(n),
    }
