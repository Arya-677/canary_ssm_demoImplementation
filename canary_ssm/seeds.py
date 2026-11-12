"""Central deterministic seed registry (WP-A4).

Disjoint integer seed blocks per experimental purpose and family index so no two
studies or data roles can ever silently share exogenous Monte Carlo streams.
"""
from __future__ import annotations

REGISTRY_VERSION = "2.0"
BLOCK = 1_000_000
FAMILY_STRIDE = 20_000
MAX_FAMILIES = BLOCK // FAMILY_STRIDE  # 50 families per 1M block

RANGES: dict[str, int] = {
    "smoke": 10_000,
    "dev": 1_000_000,
    "calibration": 2_000_000,
    "null_validation": 3_000_000,
    "test": 4_000_000,
    "stress": 5_000_000,
    "audit": 6_000_000,
    "noise_sweep": 7_000_000,
    "study_R1": 8_000_000,
    "study_R2": 9_000_000,
    "study_R3": 10_000_000,
    "study_R4": 11_000_000,
    "study_R5": 12_000_000,
    "study_R6": 13_000_000,
    "study_R7": 14_000_000,
    "study_R8": 15_000_000,
    "study_R9": 16_000_000,
    "study_E3": 17_000_000,
    "study_X": 18_000_000,
    "realtrace": 20_000_000,
    "study_regime": 21_000_000,
    "study_robust": 22_000_000,
    "study_E2": 23_000_000,
    "study_E4": 24_000_000,
    "study_E5": 25_000_000,
    "study_E6": 26_000_000,
    "study_E7": 27_000_000,
    "study_E8": 28_000_000,
}

# Documentation of exact seed bases used by the Revision 1 / first full run (do not reuse blindly).
LEGACY: dict[str, object] = {
    "v1_main": {
        "dev": 1_000_000,
        "calibration": 2_000_000,
        "null_validation": 3_000_000,
        "test": 4_000_000,
    },
    "v1_experiment_7": [2_100_000, 2_600_000, 7_500_000, 8_000_000, 8_200_000, 8_500_000],
    "v1_experiment_8": [1_000_000, 2_000_000, 4_100_000, 6_300_000, 6_400_000, 7_300_000, 7_400_000],
    "note": "Legacy Experiment 8 calibration (2_000_000+) overlapped v1_main calibration; new studies must use RANGES via seed_for().",
}


def max_families_for(purpose: str) -> int:
    """Maximum family slots available in `purpose` without invading the next block."""
    if purpose == "smoke":
        return (1_000_000 - RANGES["smoke"]) // FAMILY_STRIDE  # 49 -> strictly < 1_000_000
    return MAX_FAMILIES


def seed_for(purpose: str, i: int, family_idx: int = 0) -> int:
    """Return a deterministic, globally unique seed for `(purpose, family_idx, i)`."""
    if purpose not in RANGES:
        raise KeyError(f"Unknown seed purpose {purpose!r}; valid purposes: {sorted(RANGES)}")
    if not isinstance(i, (int, np.integer)) if False else not isinstance(i, int):
        i = int(i)
    if not isinstance(family_idx, int):
        family_idx = int(family_idx)
    if i < 0 or i >= FAMILY_STRIDE:
        raise ValueError(f"Seed item index i={i} out of bounds [0, {FAMILY_STRIDE})")
    mf = max_families_for(purpose)
    if family_idx < 0 or family_idx >= mf:
        raise ValueError(f"family_idx={family_idx} out of bounds [0, {mf}) for purpose={purpose!r}")
    return RANGES[purpose] + family_idx * FAMILY_STRIDE + i


def purpose_span(purpose: str) -> tuple[int, int]:
    """Half-open interval `[lo, hi)` owned by `purpose`."""
    lo = RANGES[purpose]
    hi = lo + max_families_for(purpose) * FAMILY_STRIDE
    return lo, hi


def range_summary(purpose: str, n: int, family_idx: int = 0) -> dict:
    """Metadata summary of `[first_seed, last_seed]` used for manifest logging."""
    if n <= 0:
        return {"purpose": purpose, "family_idx": family_idx, "count": 0}
    lo = seed_for(purpose, 0, family_idx)
    hi = seed_for(purpose, min(n - 1, FAMILY_STRIDE - 1), family_idx)
    return {"purpose": purpose, "family_idx": family_idx, "count": int(n), "min_seed": lo, "max_seed": hi}


def assert_disjoint() -> None:
    """Verify every `(purpose, family_idx)` span in `RANGES` is strictly pairwise disjoint."""
    spans = sorted((purpose_span(p), p) for p in RANGES)
    for idx in range(len(spans) - 1):
        (lo_a, hi_a), name_a = spans[idx]
        (lo_b, hi_b), name_b = spans[idx + 1]
        if hi_a > lo_b:
            raise AssertionError(
                f"Seed ranges overlap: {name_a} [{lo_a}, {hi_a}) vs {name_b} [{lo_b}, {hi_b})"
            )


assert_disjoint()
