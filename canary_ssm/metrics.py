"""Evaluator-side metrics (handbook Sections 3, 9, 10). May read Truth; detectors may not."""
from __future__ import annotations

import numpy as np
from scipy.stats import beta

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
