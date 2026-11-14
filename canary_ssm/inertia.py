"""V3 inertia model utilities: the hier_ts candidate grid and exact model-equivalence helpers.

hier_ts = hierarchical effect model with separate group/local persistence, innovation scale and prior scale
(hierarchy.TwoScaleParams). It is an exact linear-Gaussian model (Kalman filter, no approximation). It is NOT a new
model family: it is a hierarchical random-effects model with distinct variance components and time scales. What is
being tested is whether asymmetric group-vs-local time scales add detection value beyond (a) ordinary equal-rho
persistence and (b) decision-level hysteresis. See docs/INERTIA_MODEL_DESIGNS.md.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from .hierarchy import TwoScaleParams, long_run_sd
from .schema import KAPPA

DEFAULT_INERTIA_GRID = Path(__file__).resolve().parents[1] / "configs" / "grids_inertia.yaml"


def load_inertia_grid(path: Path | str | None = None) -> dict:
    p = Path(path) if path is not None else DEFAULT_INERTIA_GRID
    return yaml.safe_load(p.read_text(encoding="utf-8-sig"))


def ts_candidates(grids: dict | None = None) -> list[dict]:
    """Candidate parameter dicts for `hier_ts` (TwoScaleParams fields), pruned by long-run SD <= kappa."""
    g = (grids or load_inertia_grid())["hier_ts"]
    out = []
    for rg in g["rho_g"]:
        for rh in g["rho_h"]:
            for sd in g["sd_g"]:
                for hr in g["sd_h_ratio"]:
                    for ps in g["prior_sd"]:
                        for pr in g["prior_h_ratio"]:
                            p = TwoScaleParams(kind="hier", rho_g=float(rg), rho_h=float(rh), sd_g=float(sd),
                                               sd_h_ratio=float(hr), prior_sd=float(ps), prior_h_ratio=float(pr))
                            if g.get("constrain_long_run_sd_le_kappa", True) and long_run_sd(p) > KAPPA:
                                continue
                            out.append(asdict(p))
    return out


def nests_hier_ssm(candidates: list[dict], hier_params: dict, tol: float = 1e-12) -> bool:
    """True iff the ordinary-persistence hier_ssm point (equal rho, ratios 1) is inside the hier_ts grid."""
    keys = ("rho_g", "rho_h", "sd_g", "sd_h_ratio", "prior_sd")
    for c in candidates:
        if all(abs(float(c[k]) - float(hier_params[k])) <= tol for k in keys) and abs(c["prior_h_ratio"] - 1.0) <= tol:
            return True
    return False
