"""
Kayenta-inspired Canary Judge (Section 11.1).
Implements non-parametric Mann-Whitney U test comparison between canary and control hosts
with minimum sample thresholds, directionality checks, effect-size filtering, and calibrated rolling mode.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.stats import mannwhitneyu

from ..baselines import DetectorOutput
from ..factor import Adjusted


@dataclass
class KayentaConfig:
    window: int = 15                  # Retrospective sliding window (minutes)
    min_samples: int = 5              # Minimum samples required per group to evaluate
    alpha: float = 0.05               # Significance level for batch classification
    effect_size_threshold: float = 0.0 # Minimum median difference required for critical failure
    alternative: str = "greater"      # Directional hypothesis: canary > control


class KayentaJudge:
    """
    Kayenta canary judge comparator.
    Evaluates distributional deviation between canary and control groups.
    Supports both batch retrospective evaluation and causal rolling sequential scoring.
    """
    def __init__(self, config: KayentaConfig | None = None):
        self.config = config or KayentaConfig()

    def evaluate_sample(self, canary_samples: np.ndarray, control_samples: np.ndarray) -> tuple[str, float, float]:
        """
        Evaluate a single pair of sample sets.
        Returns:
            outcome: "PASS", "FAIL_CRITICAL", or "NODATA"
            p_value: Mann-Whitney p-value (or 1.0 if NODATA)
            z_score: Standardized test statistic
        """
        can = canary_samples[np.isfinite(canary_samples)]
        ctl = control_samples[np.isfinite(control_samples)]

        if len(can) < self.config.min_samples or len(ctl) < self.config.min_samples:
            return "NODATA", 1.0, 0.0

        n1, n2 = len(can), len(ctl)
        # Handle zero-variance degenerate case
        if np.allclose(can, can[0]) and np.allclose(ctl, ctl[0]) and can[0] == ctl[0]:
            return "PASS", 1.0, 0.0

        res = mannwhitneyu(can, ctl, alternative=self.config.alternative)
        p_val = float(res.pvalue)

        # Standard normal approximation z-score
        mean_u = n1 * n2 / 2.0
        std_u = np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
        u_stat = float(res.statistic)
        z_score = float((u_stat - mean_u) / max(std_u, 1e-9))

        med_diff = float(np.median(can) - np.median(ctl))
        if p_val <= self.config.alpha and med_diff > self.config.effect_size_threshold:
            outcome = "FAIL_CRITICAL"
        else:
            outcome = "PASS"

        return outcome, p_val, z_score

    def run(self, adj: Adjusted) -> DetectorOutput:
        """
        Causal rolling sequential scoring on Adjusted residuals.
        Produces (T,) standardized score sequence where higher score indicates greater canary degradation.
        """
        if adj.ctl_r is None or adj.ctl_class_id is None:
            raise ValueError("KayentaJudge requires Adjusted.ctl_r and Adjusted.ctl_class_id")

        T, nc = adj.r.shape
        t0 = int(adj.t0)
        win = max(1, int(self.config.window))
        classes = np.unique(adj.class_id)
        can_masks = {int(g): np.flatnonzero(adj.class_id == g) for g in classes}
        ctl_masks = {int(g): np.flatnonzero(adj.ctl_class_id == g) for g in classes}

        r_can = np.where(adj.obs & np.isfinite(adj.r), adj.r, np.nan)
        r_ctl = adj.ctl_r
        host_score = np.full((T, nc), np.nan, dtype=float)
        score = np.full(T, np.nan, dtype=float)

        for t in range(t0, T):
            lo = max(0, t - win + 1)
            class_scores = []
            for g in classes:
                gi = int(g)
                c_idx = can_masks[gi]
                k_idx = ctl_masks[gi]
                yg = r_ctl[lo : t + 1][:, k_idx]
                yg = yg[np.isfinite(yg)]
                xg = r_can[lo : t + 1][:, c_idx]
                xg_flat = xg[np.isfinite(xg)]

                _, _, z_cls = self.evaluate_sample(xg_flat, yg)
                class_scores.append(z_cls)

                for col in c_idx:
                    xi = r_can[lo : t + 1, col]
                    xi = xi[np.isfinite(xi)]
                    _, _, z_host = self.evaluate_sample(xi, yg)
                    host_score[t, col] = z_host

            score[t] = float(max(class_scores)) if class_scores else 0.0

        return DetectorOutput(
            method="kayenta_judge",
            score=score,
            elig=adj.elig,
            host_score=host_score,
            params={"window": win, "min_samples": self.config.min_samples, "alpha": self.config.alpha}
        )
