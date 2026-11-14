"""
Argo Rollouts-inspired Analysis Policy (Section 11.3).
Simulates Argo Rollouts analysis run failure-limit tracking.
Supports AR-1 (failureLimit=1), AR-3 (failureLimit=3), AR-5 (failureLimit=5),
and consecutive failure modes.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..baselines import DetectorOutput
from ..factor import Adjusted


@dataclass
class ArgoPolicyConfig:
    failure_limit: int = 3            # AR-1, AR-3, AR-5
    consecutive: bool = False         # True: consecutive failures reset on pass; False: cumulative failures
    base_window: int = 1              # Rolling window for metric check


class ArgoRolloutsPolicy:
    """
    Argo Rollouts analysis engine.
    Wraps an instantaneous contrast or degradation detector, tracking failureLimit counts.
    Produces both a sequential score (monotonic in failure progress) and explicit discrete state.
    """
    def __init__(self, config: ArgoPolicyConfig | None = None):
        self.config = config or ArgoPolicyConfig()

    def run(self, adj: Adjusted, raw_detector_output: DetectorOutput | None = None) -> DetectorOutput:
        T, nc = adj.r.shape
        t0 = int(adj.t0)

        # If no raw detector provided, use standardized contrast
        if raw_detector_output is None:
            z_can = np.where(adj.obs & np.isfinite(adj.r), adj.r / adj.sigma[None], np.nan)
            raw_signal = np.nanmean(z_can, axis=1)
            raw_signal = np.nan_to_num(raw_signal, nan=0.0)
        else:
            raw_signal = np.nan_to_num(raw_detector_output.score, nan=0.0)

        # For sequential scoring and calibration:
        # We track the failure counter or rolling cumulative score
        score = np.full(T, np.nan, dtype=float)
        counter = 0.0

        for t in range(t0, T):
            val = raw_signal[t]
            if val > 0.0:
                counter += 1.0
            else:
                if self.config.consecutive:
                    counter = 0.0

            # Normalized score indicates progress towards failureLimit
            score[t] = float(counter / max(1, self.config.failure_limit))

        return DetectorOutput(
            method=f"argo_ar{self.config.failure_limit}",
            score=score,
            elig=adj.elig,
            host_score=None,
            params={
                "failure_limit": self.config.failure_limit,
                "consecutive": self.config.consecutive,
            }
        )
