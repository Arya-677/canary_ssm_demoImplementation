"""
No-Inertia SSM Ablation Detector (Section 7.4 & Section 11.5).
Neutralizes temporal transition persistence (rho_g = 0, rho_h = 0)
while preserving the hierarchical projection basis B, observation covariance, and calibration protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..baselines import DetectorOutput
from ..factor import Adjusted
from ..hierarchy import EffectDetector, EffectParams
from ..preprocess import Nuisance


class NoInertiaSSM:
    """
    Ablated State-Space Model without inertia / persistence.
    The effect transition is memoryless (rho = 0.0), isolating the contribution
    of temporal inertia from hierarchical spatial shrinkage.
    """
    def __init__(self, nuis: Nuisance, prior_sd: float = 0.03, sd_g: float = 0.005):
        self.nuis = nuis
        self.params = EffectParams(
            kind="hier",
            rho_g=0.0,
            rho_h=0.0,
            sd_g=sd_g,
            sd_h_ratio=1.0,
            prior_sd=prior_sd
        )
        self.detector = EffectDetector(self.nuis, self.params)

    def run(self, adj: Adjusted) -> DetectorOutput:
        out = self.detector.run(adj)
        out.method = "no_inertia_ssm"
        return out
