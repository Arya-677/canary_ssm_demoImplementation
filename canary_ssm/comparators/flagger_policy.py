"""
Flagger-inspired Metric Analysis Policy (Section 11.4).
Simulates Flagger progressive delivery metric analysis:
Tracks cumulative failed metric checks against a threshold, triggering rollback when threshold is breached.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..baselines import DetectorOutput
from ..factor import Adjusted


@dataclass
class FlaggerPolicyConfig:
    max_failed_checks: int = 5        # Flagger threshold (e.g. 5 or 10 failed checks)
    step_weight: float = 10.0         # Canary weight step increment percentage
    max_weight: float = 50.0          # Max canary weight before promotion


class FlaggerPolicy:
    """
    Flagger canary analysis policy.
    Maintains cumulative failed-check budget and traffic weight progression.
    """
    def __init__(self, config: FlaggerPolicyConfig | None = None):
        self.config = config or FlaggerPolicyConfig()

    def run(self, adj: Adjusted, raw_detector_output: DetectorOutput | None = None) -> DetectorOutput:
        T, nc = adj.r.shape
        t0 = int(adj.t0)

        if raw_detector_output is None:
            z_can = np.where(adj.obs & np.isfinite(adj.r), adj.r / adj.sigma[None], np.nan)
            raw_signal = np.nanmean(z_can, axis=1)
            raw_signal = np.nan_to_num(raw_signal, nan=0.0)
        else:
            raw_signal = np.nan_to_num(raw_detector_output.score, nan=0.0)

        score = np.full(T, np.nan, dtype=float)
        failed_checks = 0

        for t in range(t0, T):
            if raw_signal[t] > 0.0:
                failed_checks += 1

            # Score represents the fraction of failed-check budget consumed
            score[t] = float(failed_checks / max(1, self.config.max_failed_checks))

        return DetectorOutput(
            method="flagger_policy",
            score=score,
            elig=adj.elig,
            host_score=None,
            params={
                "max_failed_checks": self.config.max_failed_checks,
                "step_weight": self.config.step_weight,
                "max_weight": self.config.max_weight,
            }
        )
