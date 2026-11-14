"""
SLO Threshold Comparator (Section 11.2).
Evaluates raw or standardized contrast delta between canary and control groups.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..baselines import DetectorOutput
from ..factor import Adjusted


@dataclass
class SLOConfig:
    window: int = 5                   # Rolling window length
    standardize: bool = True          # Whether to divide by baseline sigma


class SLOThresholdComparator:
    """
    SLO delta contrast comparator.
    Computes delta_z_t = mean(canary) - mean(control).
    """
    def __init__(self, config: SLOConfig | None = None):
        self.config = config or SLOConfig()

    def run(self, adj: Adjusted) -> DetectorOutput:
        T, nc = adj.r.shape
        t0 = int(adj.t0)
        win = max(1, int(self.config.window))

        # Standardized residuals
        sigma = adj.sigma[None] if self.config.standardize else np.ones((1, nc))
        z_can = np.where(adj.obs & np.isfinite(adj.r), adj.r / sigma, np.nan)

        if adj.ctl_r is not None:
            if self.config.standardize:
                # Estimate control pre-period sigma or overall sigma
                ctl_pre = adj.ctl_r[:t0]
                ctl_std = np.nanstd(ctl_pre, axis=0)
                ctl_std = np.where(np.isfinite(ctl_std) & (ctl_std > 1e-6), ctl_std, 1.0)
                z_ctl = adj.ctl_r / ctl_std[None]
            else:
                z_ctl = adj.ctl_r
        else:
            z_ctl = None

        score = np.full(T, np.nan, dtype=float)
        host_score = np.full((T, nc), np.nan, dtype=float)

        for t in range(t0, T):
            lo = max(0, t - win + 1)
            can_window = z_can[lo : t + 1]
            can_mean_per_host = np.nanmean(can_window, axis=0)
            host_score[t] = can_mean_per_host

            can_mean_overall = np.nanmean(can_window)

            if z_ctl is not None:
                ctl_window = z_ctl[lo : t + 1]
                ctl_mean_overall = np.nanmean(ctl_window)
                diff = can_mean_overall - ctl_mean_overall
            else:
                diff = can_mean_overall

            score[t] = float(diff) if np.isfinite(diff) else 0.0

        return DetectorOutput(
            method="slo_threshold",
            score=score,
            elig=adj.elig,
            host_score=host_score,
            params={"window": win, "standardize": self.config.standardize}
        )
