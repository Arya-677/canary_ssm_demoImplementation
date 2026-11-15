"""Rigorous Statistical Evaluation Suite for Virtual Data Center & Canary SSM.

This package provides:
- Seed and data bundle separation (smoke, dev, calibration, null_validation, test).
- Hand-labeled metric fixtures (misses, premature alarms, capped time, localization, attribution).
- Order-statistic threshold calibration and policy replay calibration.
- Independent null validation with exact binomial Clopper-Pearson CIs and Beta-Binomial validity tests.
- Broad multi-scenario benchmarking across 13 conditions.
- Versioned result table generation and reporting.
"""
from __future__ import annotations

from .splits import (
    DataRole,
    RoleSeedBundle,
    get_seed_bundle,
    verify_seed_separation,
    get_all_role_bundles,
)
from .fixtures import (
    EventLabel,
    MultiMetricEventTruth,
    classify_run,
    compute_localization,
    attribution_confusion_matrix,
    paired_bootstrap_contrast,
)
from .calibration import (
    calibrate_first_crossing_threshold,
    calibrate_multichannel_by_replay,
    evaluate_host_risk_vs_fleet_control,
)
from .runner import (
    run_full_evaluation_suite,
    EvaluationSummary,
)

__all__ = [
    "DataRole",
    "RoleSeedBundle",
    "get_seed_bundle",
    "verify_seed_separation",
    "get_all_role_bundles",
    "EventLabel",
    "MultiMetricEventTruth",
    "classify_run",
    "compute_localization",
    "attribution_confusion_matrix",
    "paired_bootstrap_contrast",
    "calibrate_first_crossing_threshold",
    "calibrate_multichannel_by_replay",
    "evaluate_host_risk_vs_fleet_control",
    "run_full_evaluation_suite",
    "EvaluationSummary",
]
