"""Evaluator-side metrics (handbook Sections 3, 9, 10). May read Truth; detectors may not."""
from __future__ import annotations

import numpy as np
from scipy.stats import beta, betabinom, rankdata

from .schema import KAPPA, D_MIN
from .simulate import Truth

DETECT_HORIZONS = (5, 15, 30, 60, 120)


# ----------------------------------------------------------------- event labels
def _runs(b: np.ndarray):
    """Contiguous True runs as (start, end_exclusive)."""
    out, start = [], None
    for t, v in enumerate(b):
        if v and start is None:
            start = t
        if not v and start is not None:
            out.append((start, t)); start = None
    if start is not None:
        out.append((start, len(b)))
    return out


def event_truth(truth: Truth, nc: int, kappa: float = KAPPA, D: int = D_MIN) -> dict:
    """J(i,t)=1 iff a(i,t) > kappa strictly. Qualifying event = run of J for >= D grid minutes on >=1 canary.
    Onset = start of the FIRST qualifying run (known only retrospectively; the detector never sees it)."""
    J = truth.a[:, :nc] > kappa
    q, any_runs, affected = [], False, set()
    for h in range(nc):
        for s, e in _runs(J[:, h]):
            any_runs = True
            if e - s >= D:
                q.append((h, s, e)); affected.add(h)
    return {"J": J, "has_event": bool(q), "onset": min(s for _, s, _ in q) if q else None,
            "intervals": q, "affected": sorted(affected), "transient": bool(any_runs and not q)}


def classify(t_alarm: int | None, ev: dict, T: int) -> dict:
    """Outcome of ONE latched alarm for one rollout. delay is onset-relative for successes only."""
    if not ev["has_event"]:
        return {"kind": "transient" if ev["transient"] else "no_event", "alarm": t_alarm is not None,
                "status": "alarm" if t_alarm is not None else "quiet", "delay": np.nan, "capped": np.nan}
    on = ev["onset"]; remaining = T - on
    if t_alarm is None:
        status, delay = "miss", np.nan
    elif t_alarm < on:
        status, delay = "premature", np.nan
    elif any(s <= t_alarm < e for _, s, e in ev["intervals"]):
        status, delay = "success", t_alarm - on
    else:
        status, delay = "late_after_recovery", np.nan
    capped = float(delay) if status == "success" else float(remaining)
    return {"kind": "event", "alarm": t_alarm is not None, "status": status, "delay": delay, "capped": capped,
            "followup": remaining}


# ----------------------------------------------------------------- localization / calibration
def host_ranking(out, t: int) -> np.ndarray:
    v = out.host_prob[t] if out.host_prob is not None else out.host_score[t]
    return np.where(np.isfinite(v), v, -np.inf)


def localization(out, ev: dict, landmark: int = 30, topk: int = 3, cutoff: int = 3) -> dict | None:
    if not ev["has_event"] or (out.host_prob is None and out.host_score is None):
        return None
    tl = ev["onset"] + landmark
    if tl >= len(out.score):
        return None                                   # insufficient follow-up: excluded, not imputed
    rank = np.argsort(-host_ranking(out, tl), kind="stable")
    A = set(ev["affected"])
    top = set(rank[:topk].tolist()); cut = set(rank[:cutoff].tolist())
    return {"top3_recall": len(top & A) / min(topk, len(A)),
            "cut_precision": len(cut & A) / cutoff, "cut_recall": len(cut & A) / len(A),
            "cut_fdp": 1 - len(cut & A) / cutoff}


def host_auc(out, ev: dict, landmark: int = 30) -> float:
    """ROC AUC of host scores/probabilities at `onset + landmark` (tie-aware, evaluator-only)."""
    if not ev["has_event"] or (out.host_prob is None and out.host_score is None):
        return np.nan
    tl = ev["onset"] + landmark
    if tl >= len(out.score):
        return np.nan
    s = np.asarray(out.host_prob[tl] if out.host_prob is not None else out.host_score[tl], float)
    n = len(s)
    y = np.zeros(n, dtype=bool)
    y[list(ev["affected"])] = True
    valid = np.isfinite(s)
    s, y = s[valid], y[valid]
    n_pos = int(y.sum())
    n_neg = int(len(y) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return np.nan
    ranks = rankdata(s, method="average")
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def brier(out, ev: dict, t0: int) -> float:
    """Time-averaged Brier of host Pr(a>kappa) vs instantaneous J(i,t); averaged within rollout first."""
    if out.host_prob is None:
        return np.nan
    P = out.host_prob[t0:]; J = ev["J"][t0:].astype(float)
    m = out.elig[t0:][:, None] & np.isfinite(P)
    return float(np.mean(((P - J) ** 2)[m])) if m.any() else np.nan


# ----------------------------------------------------------------- statistics
def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    a = 1 - level
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return float(lo), float(hi)


def upper_one_sided(k: int, n: int, level: float = 0.95) -> float:
    return 1.0 if k == n else float(beta.ppf(level, k + 1, n - k))


def paired_bootstrap(diff: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Bootstrap over ROLLOUTS (never timestamps) of a paired per-rollout difference."""
    d = np.asarray(diff, float); d = d[np.isfinite(d)]
    if d.size == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    bs = d[rng.integers(0, d.size, (n_boot, d.size))].mean(1)
    return float(d.mean()), float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))


def betabinom_validity(k_alerts: int, n_val: int, B: int, k_order: int) -> dict:
    """Exact Beta-Binomial validity test for order-statistic thresholds under exchangeability (WP-C3).

    Under continuous exchangeable null maxima M_1..M_B and validation nulls M_1'..M_n',
    exceedance probability p = 1 - F(M_(k_order)) ~ Beta(B + 1 - k_order, k_order),
    so the alert count K ~ BetaBinomial(n_val, B + 1 - k_order, k_order).
    """
    if B < 1:
        raise ValueError(f"B must be >= 1, got {B}")
    if k_order < 1 or k_order > B:
        raise ValueError(f"k_order={k_order} must satisfy 1 <= k_order <= B={B}")
    if n_val < 1:
        raise ValueError(f"n_val must be >= 1, got {n_val}")
    if k_alerts < 0 or k_alerts > n_val:
        raise ValueError(f"k_alerts={k_alerts} must satisfy 0 <= k_alerts <= n_val={n_val}")
    a = int(B + 1 - k_order)
    b = int(k_order)
    exp = float(n_val * a / (B + 1))
    sd = float(betabinom.std(n_val, a, b))
    p_lo = float(betabinom.cdf(k_alerts, n_val, a, b))
    p_hi = 1.0 if k_alerts <= 0 else float(betabinom.sf(k_alerts - 1, n_val, a, b))
    p_two = float(min(1.0, 2.0 * min(p_lo, p_hi)))
    return {
        "expected_alerts": exp,
        "bb_sd": sd,
        "bb_pvalue_two_sided": p_two,
        "p_lower": p_lo,
        "p_upper": p_hi,
        "a": a,
        "b": b,
    }


def betabinom_for_threshold(k_alerts: int, n_val: int, B: int, k_order: int) -> dict:
    """Beta-Binomial validity test that also handles degenerate `k_order > B` (`thr = +inf`)."""
    if k_order > B:
        p = 1.0 if k_alerts == 0 else 0.0
        return {
            "expected_alerts": 0.0,
            "bb_sd": 0.0,
            "bb_pvalue_two_sided": p,
            "p_lower": 1.0 if k_alerts == 0 else 0.0,
            "p_upper": p,
            "a": 0,
            "b": int(B),
        }
    return betabinom_validity(k_alerts, n_val, B, k_order)
