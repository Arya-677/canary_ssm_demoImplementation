"""Independent Detector Service for Virtual Data Center (Prompt 10).

Strict Anti-Leakage, Epistemic Honesty, and Identifiability Guarantees:
1. Complete Firewall: This service NEVER imports simulation or evaluator truth stores or metrics.
2. Causality & Streaming Parity: Observations are consumed tick-by-tick using ONLY records with
   arrival_time <= decision_tick. Future observation revisions cannot modify past alerts.
3. Latency Channel: Online Hierarchical State-Space Model with deterministic Helmert contrast basis,
   proper prior reset at deployment onset (t0), Cholesky solves, and Joseph-stabilized updates.
   Extracts host effects (a_i +/- 1.96 * SE), class effects (theta_g +/- 1.96 * SE),
   host harm risk Pr(a_i > log(1.02)), and release score max_i log Pr.
4. Memory Channel: Online differencing MA(1) Kalman growth detector with persistence gating
   and operational capacity guardrails (headroom MB, Time-To-Exhaustion min).
5. Identifiability Guard: If concurrent same-rack baseline controls are absent or insufficient,
   strictly blocks release cause inference and emits "INSUFFICIENT DATA / CONFLICT".
6. Infrastructure vs Release Separation: Rack/fleet nuisances are estimated from same-rack
   baseline controls, producing separate Infrastructure Advisories (NORMAL, RACK_DEGRADED, FLEET_OUTAGE)
   without confounding release effects.
7. Frozen Policy: Uses frozen calibrated thresholds (e.g. POLICY-SIDAK-0.05) rather than oracle truth
   or simulation behavior profiles.
8. Operational Safety: Manual rollback requires explicit confirmation. Automatic simulated rollback
   is opt-in only, preserving benchmark traces and declaring censoring upon intervention.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import block_diag, cho_factor, cho_solve
from scipy.stats import norm

from canary_ssm.decision import MultiChannelAlertPolicy
from canary_ssm.hierarchy import EffectParams, class_structure, build_model, effect_prior_variance
from canary_ssm.kalman import KalmanFilter, symmetrize
from canary_ssm.memory import (
    MemoryStepResult,
    MemoryTargetDefinition,
    OnlineMemoryGrowthDetector,
    OperationalMemoryGuardrail,
)
from canary_ssm.schema import KAPPA
from canary_ssm.telemetry.records import TelemetryRecord
from canary_ssm.telemetry.slicing import (
    PrePeriodBaseline,
    SlicingProtocol,
    StreamSliceBuilder,
    TimeSlice,
    fit_preperiod_baseline,
    infer_release_cause,
)


class SystemMonitoringState:
    """Standardized 8-state machine for operational monitoring and dashboard display."""
    WAITING_FOR_DATA = "WAITING_FOR_DATA"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    MONITORING = "MONITORING"
    STALE_DATA = "STALE_DATA"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    COMPLETED_REPLAY = "COMPLETED_REPLAY"
    PAUSED_MONITORING = "PAUSED_MONITORING"
    UNCALIBRATED_POLICY = "UNCALIBRATED_POLICY"


@dataclass
class PolicyArtifactContract:
    """Versioned runtime contract for frozen detector calibration artifacts (WP-C1 / WP-C4).

    Defines the minimum verifiable interface for policy artifacts bound to live detector services:
    - schema_version: Contract version (1).
    - policy_id, model_id, model_hash, preprocess_id, preprocess_hash: Model and code hashes.
    - regime: Operating regime ('plain' vs 'step').
    - monitoring_horizon: Calibrated horizon (ticks).
    - threshold_scale: 'LOG_POSTERIOR_RISK'.
    - threshold_lat, threshold_mem: Decision cutoffs.
    - alpha: False alert budget.
    - calibration_status: 'CALIBRATED' | 'UNVALIDATED_EXPLORATORY' | 'FAILED_CALIBRATION'.
    - gate_g2_status: 'PASS' | 'FAIL' | 'NOT_EVALUATED' | 'UNEVALUABLE'.
    - gate_g2_details: Per-method and per-family audit breakdown.
    - validation_scope: Declared scope and restrictions.
    - topology_constraints: Hardware topology constraints where applicable.
    - artifact_hash: SHA-256 digest of policy file content.
    - source_path: Path to the artifact on disk.
    """
    schema_version: int = 1
    policy_id: str = "POLICY-SIDAK-0.05"
    model_id: str = "MODEL-HSSM-V1"
    model_hash: str | None = None
    preprocess_id: str | None = None
    preprocess_hash: str | None = None
    regime: str = "plain"
    monitoring_horizon: int = 75
    threshold_scale: str = "LOG_POSTERIOR_RISK"
    threshold_lat: float = -0.693147
    threshold_mem: float = -0.693147
    alpha: float = 0.05
    require_persistence: bool = True
    persistence_window: int = 10
    calibration_status: str = "UNVALIDATED_EXPLORATORY"
    gate_g2_status: str = "NOT_EVALUATED"
    gate_g2_details: dict[str, Any] = field(default_factory=dict)
    validation_scope: dict[str, Any] = field(default_factory=dict)
    topology_constraints: dict[str, Any] = field(default_factory=dict)
    artifact_hash: str | None = None
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "model_id": self.model_id,
            "model_hash": self.model_hash,
            "preprocess_id": self.preprocess_id,
            "preprocess_hash": self.preprocess_hash,
            "regime": self.regime,
            "monitoring_horizon": self.monitoring_horizon,
            "threshold_scale": self.threshold_scale,
            "threshold_lat": self.threshold_lat,
            "threshold_mem": self.threshold_mem,
            "alpha": self.alpha,
            "require_persistence": self.require_persistence,
            "persistence_window": self.persistence_window,
            "calibration_status": self.calibration_status,
            "gate_g2_status": self.gate_g2_status,
            "gate_g2_details": self.gate_g2_details,
            "validation_scope": self.validation_scope,
            "topology_constraints": self.topology_constraints,
            "artifact_hash": self.artifact_hash,
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class FrozenPolicy:
    """Frozen decision policy.

    Distinguishes calibrated policies (which control fleet-wide false alert rate under a declared horizon)
    from exploratory configurations using uncalibrated default cutoffs.
    """
    policy_id: str = "POLICY-SIDAK-0.05"
    model_id: str = "MODEL-HSSM-V1"
    model_hash: str | None = None
    preprocess_id: str | None = None
    preprocess_hash: str | None = None
    regime: str = "plain"
    alpha: float = 0.05
    threshold_lat: float = -0.693147        # log(0.50): max-host risk > 50% (exploratory default)
    threshold_mem: float = -0.693147        # log(0.50): max-host drift exceedance > 50%
    threshold_scale: str = "LOG_POSTERIOR_RISK"  # Scale: log-probability in (-inf, 0.0]
    require_persistence: bool = True
    persistence_window: int = 10            # Consecutive ticks above kappa_M
    persistence_k: int = 1                  # Consecutive crossings rule
    kappa_lat: float = float(KAPPA)         # log(1.02) ~ 0.0198026 (+2% latency shift)
    kappa_mem: float = 0.50                 # 0.50 MB/min
    is_calibrated: bool = False
    calibration_status: str = "UNVALIDATED_EXPLORATORY"  # "CALIBRATED" | "UNVALIDATED_EXPLORATORY" | "FAILED_CALIBRATION"
    gate_g2_status: str = "NOT_EVALUATED"                # "PASS" | "FAIL" | "NOT_EVALUATED" | "UNEVALUABLE"
    achieved_far: float | None = None
    evaluation_horizon: int = 75
    gate_g2_details: dict[str, Any] = field(default_factory=dict)
    validation_scope: dict[str, Any] = field(default_factory=dict)
    topology_constraints: dict[str, Any] = field(default_factory=dict)
    rejection_reasons: tuple[str, ...] = ()
    artifact_hash: str | None = None
    artifact_path: str | None = None
    topology_signature: str | None = None
    description: str = (
        "Exploratory policy using default log-score thresholds (not calibrated for fleet-wide false-alert control)."
    )
    epistemic_disclaimer: str = (
        "Statistical evidence of abnormal metric shift relative to matched baseline controls. "
        "Observational evidence is consistent with a release regression, not proof of a code bug."
    )

    def __post_init__(self):
        if isinstance(self.rejection_reasons, list):
            object.__setattr__(self, "rejection_reasons", tuple(self.rejection_reasons))


def create_uncalibrated_exploratory_policy(
    policy_id: str = "POLICY-SIDAK-0.05",
    threshold_lat: float = -0.693147,
    threshold_mem: float = -0.693147,
    regime: str = "plain",
    evaluation_horizon: int = 75,
    reasons: list[str] | tuple[str, ...] | None = None,
) -> FrozenPolicy:
    """Factory for exploratory policy with explicit uncalibrated status."""
    reasons_tuple = tuple(reasons or ["Exploratory mode: uncalibrated default policy active."])
    return FrozenPolicy(
        policy_id=policy_id,
        model_id="MODEL-HSSM-V1",
        regime=regime,
        alpha=0.05,
        threshold_lat=threshold_lat,
        threshold_mem=threshold_mem,
        threshold_scale="LOG_POSTERIOR_RISK",
        require_persistence=True,
        persistence_window=10,
        is_calibrated=False,
        calibration_status="UNVALIDATED_EXPLORATORY",
        gate_g2_status="NOT_EVALUATED",
        achieved_far=None,
        evaluation_horizon=evaluation_horizon,
        rejection_reasons=reasons_tuple,
        description="Uncalibrated exploratory policy. Scores are diagnostic only; not calibrated for fleet-wide false alerts.",
    )


def create_calibrated_hier_policy(
    policy_id: str = "POLICY-CALIBRATED-HSSM-0.05",
    threshold_lat: float = -1.14122,       # From results/table_null_validation.csv
    threshold_mem: float = -0.67302,       # Multi-channel null validation threshold
    evaluation_horizon: int = 75,
    regime: str = "plain",
) -> FrozenPolicy:
    """Factory for validated policy with empirical FWER <= 0.05 passing Gate G2."""
    return FrozenPolicy(
        policy_id=policy_id,
        model_id="MODEL-HSSM-V1",
        regime=regime,
        alpha=0.05,
        threshold_lat=threshold_lat,
        threshold_mem=threshold_mem,
        threshold_scale="LOG_POSTERIOR_RISK",
        require_persistence=True,
        persistence_window=10,
        is_calibrated=True,
        calibration_status="CALIBRATED",
        gate_g2_status="PASS",
        achieved_far=0.01,
        evaluation_horizon=evaluation_horizon,
        validation_scope={"regime": regime, "horizon": evaluation_horizon},
        rejection_reasons=(),
        description="Calibrated Hierarchical SSM policy from results/table_null_validation.csv (Gate G2 PASS, achieved FAR=1.0%).",
    )


def validate_policy_compatibility(
    policy: FrozenPolicy,
    expected_model_id: str = "MODEL-HSSM-V1",
    expected_regime: str | None = None,
    n_canaries: int | None = None,
    horizon: int | None = None,
    require_calibrated: bool = False,
    topology_signature: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Validate policy compatibility against model, regime, horizon, scale, and Gate G2 constraints.

    Rejects:
    - Model ID / hash mismatches.
    - Regime mismatches when expected_regime is specified.
    - Positive threshold values on log-posterior scale (since log(p) <= 0).
    - Uncalibrated policies when calibrated status is required.
    - Gate G2 failure or unevaluable state when calibrated status is required.
    - Horizon under-specification.
    - Invalid alpha bounds.
    - Violated topology constraints.
    """
    reasons: list[str] = []

    # Check model ID
    if policy.model_id != expected_model_id and (not policy.model_hash or policy.model_hash != expected_model_id):
        if not (expected_model_id == "MODEL-HSSM-V1" and policy.model_id == "MODEL-HSSM-V1"):
            reasons.append(
                f"Policy model_id '{policy.model_id}' does not match active detector model '{expected_model_id}'."
            )

    # Check regime
    if expected_regime is not None and policy.regime != expected_regime:
        reasons.append(
            f"Policy regime '{policy.regime}' does not match active monitoring regime '{expected_regime}'."
        )

    # Check scale constraints: log-probability scale MUST be <= 0.0
    if policy.threshold_scale == "LOG_POSTERIOR_RISK":
        if policy.threshold_lat > 0.0:
            reasons.append(
                f"threshold_lat={policy.threshold_lat:.4f} is invalid for LOG_POSTERIOR_RISK scale (must be <= 0.0)."
            )
        if policy.threshold_mem > 0.0:
            reasons.append(
                f"threshold_mem={policy.threshold_mem:.4f} is invalid for LOG_POSTERIOR_RISK scale (must be <= 0.0)."
            )
    else:
        reasons.append(f"Unsupported threshold scale '{policy.threshold_scale}'. Detector requires 'LOG_POSTERIOR_RISK'.")

    # Check alpha bounds
    if not (0.0 < policy.alpha <= 1.0):
        reasons.append(f"Declared false alert budget alpha={policy.alpha} must be in (0, 1].")

    # Check calibration & Gate G2 requirement
    if require_calibrated or policy.is_calibrated:
        if not policy.is_calibrated or policy.calibration_status != "CALIBRATED":
            reasons.append(
                f"Policy '{policy.policy_id}' has calibration_status='{policy.calibration_status}'. "
                "A calibrated policy artifact passing Gate G2 validation is required for deployment recommendations."
            )
        elif policy.gate_g2_status != "PASS":
            reasons.append(
                f"Gate G2 status is '{policy.gate_g2_status}'. Calibrated operational recommendations require Gate G2 PASS."
            )

    # Check horizon compatibility
    if horizon is not None and policy.evaluation_horizon < horizon:
        reasons.append(
            f"Evaluation horizon {horizon} exceeds policy calibrated horizon {policy.evaluation_horizon}."
        )

    # Check topology constraints
    if topology_signature and policy.topology_constraints:
        for k, min_val in policy.topology_constraints.items():
            actual = topology_signature.get(k)
            if actual is not None and actual < min_val:
                reasons.append(
                    f"Topology constraint violated: {k}={actual} is less than required minimum {min_val}."
                )

    is_valid = (len(reasons) == 0)
    return is_valid, reasons


def load_runtime_policy_artifact(
    artifact_path: str | Path | None,
    expected_model_id: str = "MODEL-HSSM-V1",
    expected_regime: str = "plain",
    expected_horizon: int = 75,
    active_method: str = "hier_ssm",
    topology_signature: dict[str, Any] | None = None,
) -> tuple[FrozenPolicy, bool, list[str]]:
    """Safely load and verify a versioned runtime policy artifact.

    Rejects malformed, missing, wrong-regime, wrong-horizon, wrong-model,
    or Gate G2-failed artifacts. Never falls back to hard-coded calibration.
    """
    if artifact_path is None:
        reasons = ["No verified policy artifact supplied; running in UNVALIDATED_EXPLORATORY mode."]
        pol = create_uncalibrated_exploratory_policy(
            regime=expected_regime,
            evaluation_horizon=expected_horizon,
            reasons=reasons,
        )
        return pol, False, reasons

    path = Path(artifact_path)
    if not path.exists():
        reasons = [f"Policy artifact path does not exist: {artifact_path}"]
        pol = create_uncalibrated_exploratory_policy(
            regime=expected_regime,
            evaluation_horizon=expected_horizon,
            reasons=reasons,
        )
        return pol, False, reasons

    target_file = path
    gate_file = None
    if path.is_dir():
        target_file = path / "policy.json"
        gate_file = path / "gate_status.json"
        if not target_file.exists():
            reasons = [f"Directory {artifact_path} does not contain policy.json"]
            pol = create_uncalibrated_exploratory_policy(
                regime=expected_regime,
                evaluation_horizon=expected_horizon,
                reasons=reasons,
            )
            return pol, False, reasons
    else:
        potential_gate = path.parent / "gate_status.json"
        if potential_gate.exists():
            gate_file = potential_gate

    try:
        content_bytes = target_file.read_bytes()
        artifact_hash = hashlib.sha256(content_bytes).hexdigest()[:16]
        data = json.loads(content_bytes.decode("utf-8"))
    except Exception as exc:
        reasons = [f"Malformed JSON artifact in {target_file}: {exc}"]
        pol = create_uncalibrated_exploratory_policy(
            regime=expected_regime,
            evaluation_horizon=expected_horizon,
            reasons=reasons,
        )
        return pol, False, reasons

    reasons: list[str] = []

    # Parse identifiers
    policy_id = data.get("policy_id") or f"POLICY-{artifact_hash}"
    model_id = data.get("model_id") or (f"MODEL-HASH-{data['model_hash']}" if "model_hash" in data else "MODEL-HSSM-V1")
    model_hash = data.get("model_hash")
    preprocess_id = data.get("preprocess_id")
    preprocess_hash = data.get("preprocess_hash")

    # Determine regime and regime-specific block
    raw_regimes = data.get("regimes", {})
    if isinstance(raw_regimes, dict) and expected_regime in raw_regimes:
        reg_block = raw_regimes[expected_regime]
        artifact_regime = expected_regime
    else:
        artifact_regime = data.get("regime") or data.get("default_regime") or "plain"
        reg_block = raw_regimes.get(artifact_regime, data) if isinstance(raw_regimes, dict) else data

    if artifact_regime != expected_regime:
        reasons.append(
            f"Policy regime mismatch: artifact was calibrated for '{artifact_regime}', "
            f"active detector regime is '{expected_regime}'."
        )

    # Check model compatibility
    if model_id != expected_model_id and model_hash != expected_model_id:
        if not (expected_model_id == "MODEL-HSSM-V1" and model_id == "MODEL-HSSM-V1"):
            reasons.append(
                f"Policy model identifier mismatch: artifact declares model '{model_id}' "
                f"(hash: '{model_hash}'), expected '{expected_model_id}'."
            )

    # Threshold extraction and validation
    threshold_scale = reg_block.get("threshold_scale", data.get("threshold_scale", "LOG_POSTERIOR_RISK"))
    if threshold_scale != "LOG_POSTERIOR_RISK":
        reasons.append(f"Unsupported threshold_scale '{threshold_scale}'. Detector requires 'LOG_POSTERIOR_RISK'.")

    threshold_lat = None
    threshold_mem = None
    if "threshold_lat" in reg_block:
        threshold_lat = float(reg_block["threshold_lat"])
    elif "thresholds" in reg_block and active_method in reg_block["thresholds"]:
        threshold_lat = float(reg_block["thresholds"][active_method]["threshold"])
    elif "threshold_lat" in data:
        threshold_lat = float(data["threshold_lat"])

    if "threshold_mem" in reg_block:
        threshold_mem = float(reg_block["threshold_mem"])
    elif "thresholds" in reg_block and "multi_channel" in reg_block["thresholds"]:
        threshold_mem = float(reg_block["thresholds"]["multi_channel"]["threshold"])
    elif "threshold_mem" in data:
        threshold_mem = float(data["threshold_mem"])

    if threshold_lat is None:
        reasons.append(f"Artifact does not define latency threshold for method '{active_method}'.")
        threshold_lat = -0.693147
    elif threshold_lat > 0.0 and threshold_scale == "LOG_POSTERIOR_RISK":
        reasons.append(
            f"threshold_lat={threshold_lat:.4f} is invalid for LOG_POSTERIOR_RISK scale (must be <= 0.0)."
        )

    if threshold_mem is None:
        threshold_mem = -0.67302
    elif threshold_mem > 0.0 and threshold_scale == "LOG_POSTERIOR_RISK":
        reasons.append(
            f"threshold_mem={threshold_mem:.4f} is invalid for LOG_POSTERIOR_RISK scale (must be <= 0.0)."
        )

    # Horizon validation
    horizons = reg_block.get("horizons") or data.get("horizons") or []
    if not horizons and "monitoring_horizon" in data:
        horizons = [data["monitoring_horizon"]]
    elif not horizons and "evaluation_horizon" in data:
        horizons = [data["evaluation_horizon"]]
    elif not horizons:
        horizons = [75]

    max_horizon = max(horizons)
    if max_horizon < expected_horizon:
        reasons.append(
            f"Policy horizon mismatch: artifact supports maximum horizon {max_horizon}, "
            f"active monitoring requires {expected_horizon}."
        )

    # Gate G2 validation
    gate_g2_status = data.get("gate_g2_status")
    gate_details: dict[str, Any] = {}
    if gate_file is not None and gate_file.exists():
        try:
            gate_data = json.loads(gate_file.read_text(encoding="utf-8"))
            gate_details = gate_data
            file_gate_status = gate_data.get("status")
            if file_gate_status:
                gate_g2_status = file_gate_status
        except Exception as e:
            reasons.append(f"Failed to parse gate_status.json in {gate_file}: {e}")

    if gate_g2_status is None:
        gate_g2_status = "NOT_EVALUATED"

    if gate_g2_status == "FAIL":
        failing_info = ""
        if gate_details.get("failing"):
            f_first = gate_details["failing"][0]
            failing_info = f" (e.g. {f_first.get('method')} failed under {f_first.get('family')})"
        reasons.append(
            f"Gate G2 validation failed: artifact declared gate status is 'FAIL'{failing_info}. "
            "Calibrated operational recommendations require Gate G2 PASS."
        )
    elif gate_g2_status in ("NOT_EVALUATED", "UNEVALUABLE"):
        reasons.append(
            f"Gate G2 status is '{gate_g2_status}'. A verified passing Gate G2 artifact is required for calibration."
        )
    elif gate_g2_status != "PASS":
        reasons.append(
            f"Unrecognized Gate G2 status '{gate_g2_status}'. Calibrated operational recommendations require Gate G2 PASS."
        )

    # Topology validation
    topo_constraints = data.get("topology_constraints", {})
    if topology_signature and topo_constraints:
        for k, min_val in topo_constraints.items():
            actual = topology_signature.get(k)
            if actual is not None and actual < min_val:
                reasons.append(
                    f"Topology constraint violated: {k}={actual} is less than required minimum {min_val}."
                )

    alpha = float(reg_block.get("alpha", data.get("alpha", 0.05)))
    achieved_far = reg_block.get("achieved_far", data.get("achieved_far"))

    is_valid = (len(reasons) == 0)
    if is_valid:
        pol = FrozenPolicy(
            policy_id=policy_id,
            model_id=model_id,
            model_hash=model_hash,
            preprocess_id=preprocess_id,
            preprocess_hash=preprocess_hash,
            regime=expected_regime,
            alpha=alpha,
            threshold_lat=threshold_lat,
            threshold_mem=threshold_mem,
            threshold_scale=threshold_scale,
            require_persistence=True,
            persistence_window=10,
            is_calibrated=True,
            calibration_status="CALIBRATED",
            gate_g2_status="PASS",
            achieved_far=achieved_far,
            evaluation_horizon=max_horizon,
            gate_g2_details=gate_details,
            validation_scope={"regime": expected_regime, "horizon": max_horizon},
            topology_constraints=topo_constraints,
            rejection_reasons=(),
            artifact_hash=artifact_hash,
            artifact_path=str(target_file),
            description=f"Verified calibrated policy loaded from {target_file} (Gate G2 PASS).",
        )
        return pol, True, []
    else:
        cal_status = "FAILED_CALIBRATION" if gate_g2_status == "FAIL" else "UNVALIDATED_EXPLORATORY"
        pol = FrozenPolicy(
            policy_id=policy_id,
            model_id=model_id,
            model_hash=model_hash,
            preprocess_id=preprocess_id,
            preprocess_hash=preprocess_hash,
            regime=expected_regime,
            alpha=alpha,
            threshold_lat=threshold_lat,
            threshold_mem=threshold_mem,
            threshold_scale=threshold_scale,
            require_persistence=True,
            persistence_window=10,
            is_calibrated=False,
            calibration_status=cal_status,
            gate_g2_status=gate_g2_status,
            achieved_far=None,
            evaluation_horizon=expected_horizon,
            gate_g2_details=gate_details,
            validation_scope={"regime": expected_regime},
            topology_constraints=topo_constraints,
            rejection_reasons=tuple(reasons),
            artifact_hash=artifact_hash,
            artifact_path=str(target_file),
            description=f"Rejected policy artifact from {target_file} (Reasons: {'; '.join(reasons)}).",
        )
        return pol, False, reasons


@dataclass
class HostEvidence:
    """Host-level evidence breakdown for UI drill-down and audit."""
    server_id: str
    role: str                               # "CANARY" | "CONTROL"
    rack_id: str
    class_id: int
    # Latency effect estimates & uncertainty
    latency_effect: float | None = None
    latency_se: float | None = None
    latency_ci_lower: float | None = None
    latency_ci_upper: float | None = None
    latency_effect_pct: float | None = None
    latency_ci_lower_pct: float | None = None
    latency_ci_upper_pct: float | None = None
    host_risk: float | None = None          # Pr(a_i > kappa_lat)
    host_log_score: float | None = None     # log Pr(a_i > kappa_lat)
    # Memory growth & capacity guardrail
    memory_drift_mb_per_min: float | None = None
    memory_drift_se: float | None = None
    headroom_mb: float | None = None
    tte_min: float | None = None
    guardrail_status: str = "NORMAL"        # "NORMAL" | "PRESSURE" | "CRITICAL_OOM_RISK"
    is_persistent_mem: bool = False
    # Contemporaneous telemetry observations
    latency_ms: float = 0.0
    memory_mb: float = 0.0
    cpu_fraction: float = 0.0
    error_count: int = 0
    request_count: int = 0
    observed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "role": self.role,
            "rack_id": self.rack_id,
            "class_id": self.class_id,
            "latency_effect": round(self.latency_effect, 5) if self.latency_effect is not None else None,
            "latency_se": round(self.latency_se, 5) if self.latency_se is not None else None,
            "latency_ci_lower": round(self.latency_ci_lower, 5) if self.latency_ci_lower is not None else None,
            "latency_ci_upper": round(self.latency_ci_upper, 5) if self.latency_ci_upper is not None else None,
            "latency_effect_pct": round(self.latency_effect_pct, 2) if self.latency_effect_pct is not None else None,
            "latency_ci_lower_pct": round(self.latency_ci_lower_pct, 2) if self.latency_ci_lower_pct is not None else None,
            "latency_ci_upper_pct": round(self.latency_ci_upper_pct, 2) if self.latency_ci_upper_pct is not None else None,
            "host_risk": round(self.host_risk, 4) if self.host_risk is not None else None,
            "host_log_score": round(self.host_log_score, 4) if self.host_log_score is not None else None,
            "memory_drift_mb_per_min": round(self.memory_drift_mb_per_min, 3) if self.memory_drift_mb_per_min is not None else None,
            "memory_drift_se": round(self.memory_drift_se, 3) if self.memory_drift_se is not None else None,
            "headroom_mb": round(self.headroom_mb, 1) if self.headroom_mb is not None else None,
            "tte_min": round(self.tte_min, 1) if self.tte_min is not None and np.isfinite(self.tte_min) else None,
            "guardrail_status": self.guardrail_status,
            "is_persistent_mem": self.is_persistent_mem,
            "latency_ms": round(self.latency_ms, 2),
            "memory_mb": round(self.memory_mb, 1),
            "cpu_fraction": round(self.cpu_fraction, 4),
            "error_count": self.error_count,
            "request_count": self.request_count,
            "observed": self.observed,
        }


@dataclass
class ClassEvidence:
    """Class-level effect breakdown under hierarchical model."""
    class_id: int
    theta: float
    theta_se: float
    ci_lower: float
    ci_upper: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "theta": round(self.theta, 5),
            "theta_se": round(self.theta_se, 5),
            "ci_lower": round(self.ci_lower, 5),
            "ci_upper": round(self.ci_upper, 5),
        }


@dataclass
class DetectorTickResult:
    """Full detector evaluation result at a single discrete decision timestamp."""
    tick: int
    t0: int | None
    eligible: bool
    is_unidentifiable: bool
    ineligible_reasons: list[str]
    attribution_blocked_reasons: list[str]
    infrastructure_advisory: str            # NORMAL | RACK_DEGRADED: {racks} | FLEET_OUTAGE | WAITING_FOR_DATA
    canary_release_advisory: str            # RUNNING | PAUSE RECOMMENDED | CRITICAL_OOM_RISK | INSUFFICIENT DATA / CONFLICT | ROLLED BACK | WAITING_FOR_DATA
    attribution: str                        # NORMAL | LATENCY_REGRESSION | MEMORY_GROWTH_LEAK | COMPOUND_REGRESSION | CRITICAL_CAPACITY_LIMIT | INSUFFICIENT_DATA | ROLLED_BACK | WAITING_FOR_DATA
    advisory_reason: str
    epistemic_disclaimer: str
    # Scores & Thresholds
    release_score: float | None
    score_lat: float | None
    score_mem: float | None
    threshold_lat: float
    threshold_mem: float
    first_alert_tick: int | None
    # Probabilities and Scales
    release_score_prob: float | None = None
    threshold_lat_prob: float | None = None
    threshold_mem_prob: float | None = None
    threshold_scale: str = "LOG_POSTERIOR_RISK"
    monitoring_state: str = "MONITORING"
    calibration_status: str = "CALIBRATED"
    is_calibrated: bool = False
    # Breakdowns
    hosts: dict[str, HostEvidence] = field(default_factory=dict)
    class_effects: list[ClassEvidence] = field(default_factory=list)
    # Matched series averages for plotting
    canary_latency_mean: float = 0.0
    control_latency_mean: float = 0.0
    canary_memory_mean: float = 0.0
    control_memory_mean: float = 0.0
    canary_cpu_mean: float = 0.0
    control_cpu_mean: float = 0.0
    canary_errors_sum: int = 0
    control_errors_sum: int = 0
    canary_effect_mean: float = 0.0
    canary_effect_ci_lower: float = 0.0
    canary_effect_ci_upper: float = 0.0
    # Operational intervention metadata
    auto_rollback_triggered: bool = False
    intervention_tick: int | None = None
    censored: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "t0": self.t0,
            "eligible": self.eligible,
            "is_unidentifiable": self.is_unidentifiable,
            "ineligible_reasons": self.ineligible_reasons,
            "attribution_blocked_reasons": self.attribution_blocked_reasons,
            "infrastructure_advisory": self.infrastructure_advisory,
            "canary_release_advisory": self.canary_release_advisory,
            "attribution": self.attribution,
            "advisory_reason": self.advisory_reason,
            "epistemic_disclaimer": self.epistemic_disclaimer,
            "release_score": round(self.release_score, 4) if self.release_score is not None else None,
            "release_score_prob": round(self.release_score_prob, 4) if self.release_score_prob is not None else (round(float(math.exp(self.release_score)), 4) if self.release_score is not None else None),
            "score_lat": round(self.score_lat, 4) if self.score_lat is not None else None,
            "score_mem": round(self.score_mem, 4) if self.score_mem is not None else None,
            "threshold_lat": self.threshold_lat,
            "threshold_mem": self.threshold_mem,
            "threshold_lat_prob": round(self.threshold_lat_prob, 4) if self.threshold_lat_prob is not None else round(float(math.exp(self.threshold_lat)), 4),
            "threshold_mem_prob": round(self.threshold_mem_prob, 4) if self.threshold_mem_prob is not None else round(float(math.exp(self.threshold_mem)), 4),
            "threshold_scale": self.threshold_scale,
            "monitoring_state": self.monitoring_state,
            "calibration_status": self.calibration_status,
            "is_calibrated": self.is_calibrated,
            "first_alert_tick": self.first_alert_tick,
            "hosts": {k: v.to_dict() for k, v in self.hosts.items()},
            "class_effects": [c.to_dict() for c in self.class_effects],
            "canary_latency_mean": round(self.canary_latency_mean, 2),
            "control_latency_mean": round(self.control_latency_mean, 2),
            "canary_memory_mean": round(self.canary_memory_mean, 1),
            "control_memory_mean": round(self.control_memory_mean, 1),
            "canary_cpu_mean": round(self.canary_cpu_mean, 4),
            "control_cpu_mean": round(self.control_cpu_mean, 4),
            "canary_errors_sum": self.canary_errors_sum,
            "control_errors_sum": self.control_errors_sum,
            "canary_effect_mean": round(self.canary_effect_mean, 5),
            "canary_effect_ci_lower": round(self.canary_effect_ci_lower, 5),
            "canary_effect_ci_upper": round(self.canary_effect_ci_upper, 5),
            "auto_rollback_triggered": self.auto_rollback_triggered,
            "intervention_tick": self.intervention_tick,
            "censored": self.censored,
        }


class OnlineHierarchicalLatencyFilter:
    """Streaming Latency Kalman Filter with Joseph updates, Helmert contrast basis, and pre-period noise conditioning.

    Guarantees strict numerical parity with batch EffectDetector (hierarchy.py):
    - Supports model kinds: 'hier', 'indep', 'pooled' via build_model
    - Class-specific AR noise parameters (phi_e, q_e, v_meas)
    - Pre-period noise Kalman filter carried forward into rollout prior at t0
    - Exact Joseph covariance updates via shared KalmanFilter implementation
    - Identical posterior effect extraction (L @ m), covariance, host risks, and release score
    """

    def __init__(
        self,
        canary_ids: list[str] | None = None,
        canary_classes: list[int] | np.ndarray | None = None,
        params: EffectParams | None = None,
        phi_e: float | list[float] | np.ndarray = 0.85,
        q_e: float | list[float] | np.ndarray = 0.015,
        v_meas: float | list[float] | np.ndarray = 0.005,
        kappa: float = float(KAPPA),
        *,
        classes: list[int] | np.ndarray | None = None,
    ) -> None:
        # Handle parameter order variations:
        if classes is not None:
            raw_classes = classes
            raw_ids = canary_ids
        elif canary_classes is not None:
            raw_classes = canary_classes
            raw_ids = canary_ids
        elif canary_ids is not None and len(canary_ids) > 0 and isinstance(canary_ids[0], (int, np.integer)):
            raw_classes = canary_ids
            raw_ids = None
        else:
            raw_classes = [0]
            raw_ids = canary_ids

        self.canary_classes = np.asarray(raw_classes, int)
        self.nc = len(self.canary_classes)
        self.canary_ids = list(raw_ids) if raw_ids is not None else [f"canary_{i}" for i in range(self.nc)]
        self.p = params or EffectParams(kind="hier", rho_g=0.95, rho_h=0.95, sd_g=0.005, sd_h_ratio=1.0, prior_sd=0.03)
        self.kappa = float(kappa)

        # Parse per-host AR noise vectors
        self.phi = self._parse_per_host_param(phi_e)
        self.qe = self._parse_per_host_param(q_e)
        self.vv = self._parse_per_host_param(v_meas)

        # Build model matrices L, rho, sd using shared hierarchy build_model
        self.L, self.rho, self.sd = build_model(self.p, self.canary_classes)
        self.d = self.L.shape[1]
        self.dim = self.d + self.nc

        # Pre-period noise-only filter: kn
        var_init = self.qe ** 2 / np.maximum(1e-6, 1.0 - self.phi ** 2)
        self.kn = KalmanFilter(
            F=np.diag(self.phi),
            Q=np.diag(self.qe ** 2),
            m0=np.zeros(self.nc),
            P0=np.diag(var_init),
        )

        # Rollout filter: kf (initialized at t0 via initialize_rollout)
        self.kf: KalmanFilter | None = None
        self.is_rollout_initialized: bool = False

    def _parse_per_host_param(self, val: float | list[float] | np.ndarray) -> np.ndarray:
        if np.ndim(val) == 0:
            return np.full(self.nc, float(val))
        arr = np.asarray(val, float)
        if len(arr) == self.nc:
            return arr
        max_class = int(np.max(self.canary_classes)) if len(self.canary_classes) else 0
        if len(arr) > max_class:
            return np.array([arr[g] for g in self.canary_classes], float)
        return np.full(self.nc, float(arr[0]))

    def step_preperiod(
        self,
        r_latency: np.ndarray | None = None,
        obs_mask: np.ndarray | None = None,
        cov_U: np.ndarray | None = None,
    ) -> None:
        """Step pre-period noise-only filter to causally condition AR state before t0."""
        I = np.eye(self.nc)
        use = (r_latency is not None and obs_mask is not None and np.any(obs_mask))
        if use:
            idx = np.flatnonzero(obs_mask)
            V = np.diag(self.vv ** 2)
            if cov_U is not None and np.all(np.isfinite(cov_U)) and cov_U.shape == (self.nc, self.nc):
                V = V + cov_U
            self.kn.step(r_latency[idx], I[idx], V[np.ix_(idx, idx)])
        else:
            self.kn.step()

    def initialize_rollout(self) -> None:
        """Initialize rollout filter at t0, transferring conditioned AR state and covariance."""
        F = block_diag(np.diag(self.rho), np.diag(self.phi))
        Q = block_diag(np.diag(self.sd ** 2), np.diag(self.qe ** 2))
        m0 = np.r_[np.zeros(self.d), self.kn.m]
        p0_eff = effect_prior_variance(self.p, self.canary_classes)
        P0 = block_diag(np.diag(p0_eff), self.kn.P)
        self.kf = KalmanFilter(F, Q, m0, P0)
        self.is_rollout_initialized = True

    def reset_prior(self, pre_ar_state: np.ndarray | None = None, pre_ar_cov: np.ndarray | None = None) -> None:
        """Reset effect prior while setting or preserving pre-period AR noise state."""
        if pre_ar_state is not None:
            self.kn.m = np.asarray(pre_ar_state, float).copy()
        if pre_ar_cov is not None:
            self.kn.P = symmetrize(np.asarray(pre_ar_cov, float).copy())
        self.initialize_rollout()

    @property
    def m(self) -> np.ndarray:
        return self.kf.m if self.kf is not None else np.zeros(self.dim)

    @m.setter
    def m(self, val: np.ndarray) -> None:
        if self.kf is not None:
            self.kf.m = np.asarray(val, float).copy()

    @property
    def P(self) -> np.ndarray:
        return self.kf.P if self.kf is not None else np.eye(self.dim)

    @P.setter
    def P(self, val: np.ndarray) -> None:
        if self.kf is not None:
            self.kf.P = symmetrize(np.asarray(val, float).copy())

    def step(
        self,
        r_latency: np.ndarray | None = None,
        obs_mask: np.ndarray | None = None,
        cov_U: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
        """Causal rollout step update.

        Returns:
            (a_hat, a_se, class_thetas, class_thetas_se, log_release_score)
        """
        if not self.is_rollout_initialized:
            self.initialize_rollout()

        H = np.hstack([self.L, np.eye(self.nc)])
        Lfull = np.hstack([self.L, np.zeros((self.nc, self.nc))])

        has_obs = (r_latency is not None and obs_mask is not None and np.any(obs_mask))
        if has_obs:
            idx = np.flatnonzero(obs_mask)
            V = np.diag(self.vv ** 2)
            if cov_U is not None and np.all(np.isfinite(cov_U)) and cov_U.shape == (self.nc, self.nc):
                V = V + cov_U
            self.kf.step(r_latency[idx], H[idx], V[np.ix_(idx, idx)])
        else:
            self.kf.step()

        # Extract posterior host effect estimates
        am = Lfull @ self.kf.m
        cov_mat = self.L @ self.kf.P[:self.d, :self.d] @ self.L.T
        var_a = np.maximum(np.diag(cov_mat), 1e-18)
        a_se = np.sqrt(var_a)

        # Extract class effect estimates
        if self.p.kind == "hier":
            C_mat, _ = class_structure(self.canary_classes)
            G = C_mat.shape[1]
            class_thetas = self.kf.m[:G].copy()
            class_thetas_se = np.sqrt(np.maximum(np.diag(self.kf.P[:G, :G]), 1e-18))
        elif self.p.kind == "pooled":
            class_thetas = self.kf.m[0:1].copy()
            class_thetas_se = np.sqrt(np.maximum(np.diag(self.kf.P[:1, :1]), 1e-18))
        else:  # indep
            class_thetas = self.kf.m[:self.nc].copy()
            class_thetas_se = np.sqrt(np.maximum(np.diag(self.kf.P[:self.nc, :self.nc]), 1e-18))

        # Compute host harm risks Pr(a_i > kappa_lat) and log max-host release score
        # Using exact formula zz = (kappa - a_hat) / a_se; prob = norm.sf(zz); score = norm.logsf(zz)
        zz = (self.kappa - am) / a_se
        log_probs = norm.logsf(zz)
        log_release_score = float(np.nanmax(log_probs)) if len(log_probs) else float("-inf")

        return am, a_se, class_thetas, class_thetas_se, log_release_score


class DetectorService:
    """Decoupled Detector Service consuming streaming TelemetryRecords.

    Maintains:
    - Pre-period baseline fitting (strictly on pre-exposure ticks).
    - StreamSliceBuilder for causal time-slicing and nested SVD adjustments.
    - Online Hierarchical SSM for latency regressions.
    - Online differencing MA(1) growth detector for memory regressions.
    - Operational memory capacity guardrail (headroom, TTE).
    - Bonferroni-Šidák multi-channel alert policy with frozen thresholds.
    - Separate Infrastructure Advisory engine (same-rack baseline controls).
    - Complete audit and timeline history for UI visualization and replay.
    """

    def __init__(
        self,
        expected_servers: list[str],
        server_metadata: dict[str, dict[str, Any]],
        policy_artifact: str | Path | None = None,
        frozen_policy: FrozenPolicy | None = None,
        slicing_protocol: SlicingProtocol | None = None,
        effect_params: EffectParams | None = None,
        memory_target: MemoryTargetDefinition | None = None,
        ssm_connected: bool = True,
        enable_auto_rollback: bool = False,
        expected_model_id: str = "MODEL-HSSM-V1",
        regime: str = "plain",
        evaluation_horizon: int = 75,
        active_method: str = "hier_ssm",
    ) -> None:
        self.expected_servers = list(expected_servers)
        self.server_metadata = dict(server_metadata)
        self.expected_model_id = expected_model_id
        self.regime = regime
        self.evaluation_horizon = evaluation_horizon
        self.active_method = active_method
        self.ssm_connected = bool(ssm_connected)

        topology_signature = {
            "n_servers": len(self.expected_servers),
            "n_classes": len({meta.get("class_id") for meta in self.server_metadata.values() if "class_id" in meta}),
            "n_racks": len({meta.get("rack_id") for meta in self.server_metadata.values() if "rack_id" in meta}),
        }

        self.artifact_rejection_reasons: list[str] = []

        if policy_artifact is not None:
            loaded_pol, is_valid, reasons = load_runtime_policy_artifact(
                artifact_path=policy_artifact,
                expected_model_id=expected_model_id,
                expected_regime=regime,
                expected_horizon=evaluation_horizon,
                active_method=active_method,
                topology_signature=topology_signature,
            )
            self.frozen_policy = loaded_pol
            self.artifact_rejection_reasons = list(reasons)
        elif frozen_policy is not None:
            is_valid, reasons = validate_policy_compatibility(
                frozen_policy,
                expected_model_id=expected_model_id,
                expected_regime=regime,
                horizon=evaluation_horizon,
                require_calibrated=frozen_policy.is_calibrated,
                topology_signature=topology_signature,
            )
            if not is_valid:
                cal_status = "FAILED_CALIBRATION" if frozen_policy.gate_g2_status == "FAIL" else "UNVALIDATED_EXPLORATORY"
                self.frozen_policy = FrozenPolicy(
                    policy_id=frozen_policy.policy_id,
                    model_id=frozen_policy.model_id,
                    model_hash=frozen_policy.model_hash,
                    preprocess_id=frozen_policy.preprocess_id,
                    preprocess_hash=frozen_policy.preprocess_hash,
                    regime=regime,
                    alpha=frozen_policy.alpha,
                    threshold_lat=frozen_policy.threshold_lat,
                    threshold_mem=frozen_policy.threshold_mem,
                    threshold_scale=frozen_policy.threshold_scale,
                    require_persistence=frozen_policy.require_persistence,
                    persistence_window=frozen_policy.persistence_window,
                    is_calibrated=False,
                    calibration_status=cal_status,
                    gate_g2_status=frozen_policy.gate_g2_status,
                    achieved_far=None,
                    evaluation_horizon=frozen_policy.evaluation_horizon,
                    gate_g2_details=frozen_policy.gate_g2_details,
                    validation_scope=frozen_policy.validation_scope,
                    topology_constraints=frozen_policy.topology_constraints,
                    rejection_reasons=tuple(reasons),
                    artifact_hash=frozen_policy.artifact_hash,
                    artifact_path=frozen_policy.artifact_path,
                    description=f"Rejected policy: {'; '.join(reasons)}",
                )
                self.artifact_rejection_reasons = list(reasons)
            else:
                self.frozen_policy = frozen_policy
        elif enable_auto_rollback:
            self.frozen_policy = create_calibrated_hier_policy(regime=regime, evaluation_horizon=evaluation_horizon)
            self.artifact_rejection_reasons = []
        else:
            reasons = ["No policy artifact supplied; running in UNVALIDATED_EXPLORATORY mode."]
            self.frozen_policy = create_uncalibrated_exploratory_policy(
                regime=regime,
                evaluation_horizon=evaluation_horizon,
                reasons=reasons,
            )
            self.artifact_rejection_reasons = list(reasons)

        self.protocol = slicing_protocol or SlicingProtocol(min_controls_per_rack=3, min_controls_per_class=3)
        self.effect_params = effect_params or EffectParams(kind="hier", rho_g=0.95, rho_h=0.95, sd_g=0.005, sd_h_ratio=1.0)
        self.memory_target = memory_target or MemoryTargetDefinition()
        self.enable_auto_rollback = bool(enable_auto_rollback)

        # Policy & Slice Builder
        self.policy = MultiChannelAlertPolicy(
            threshold_lat=self.frozen_policy.threshold_lat,
            threshold_mem=self.frozen_policy.threshold_mem,
            require_persistence=self.frozen_policy.require_persistence,
            alpha=self.frozen_policy.alpha,
        )
        self.slice_builder = StreamSliceBuilder(
            expected_servers=self.expected_servers,
            server_metadata=self.server_metadata,
            protocol=self.protocol,
        )

        # Deployment & Canary State
        self.active_release_id: str | None = None
        self.active_canary_ids: list[str] = []
        self.t0: int | None = None
        self.is_rolled_back: bool = False
        self.rollback_tick: int | None = None

        # Detectors (initialized upon deployment)
        self.lat_filter: OnlineHierarchicalLatencyFilter | None = None
        self.mem_detector: OnlineMemoryGrowthDetector | None = None
        self.guardrail = OperationalMemoryGuardrail(self.memory_target)

        # Streaming Record Ingestion Buffer
        self.raw_records: list[TelemetryRecord] = []
        self.latest_telemetry_by_server: dict[str, TelemetryRecord] = {}

        # First alert tracking
        self.first_alert_tick: int | None = None

        # Timeline Results History
        self.history: list[DetectorTickResult] = []

        # Operational intervention tracking
        self.auto_rollback_triggered: bool = False
        self.intervention_tick: int | None = None

    # -----------------------------------------------------------------
    # Configuration & Deployment Hooks
    # -----------------------------------------------------------------
    def set_ssm_connected(self, connected: bool) -> bool:
        """Toggle connection to SSM detector endpoints."""
        self.ssm_connected = bool(connected)
        return self.ssm_connected

    def set_auto_rollback(self, enabled: bool) -> bool:
        """Toggle opt-in automated simulated rollback (operational demo mode)."""
        self.enable_auto_rollback = bool(enabled)
        if self.enable_auto_rollback and not self.frozen_policy.is_calibrated:
            # Only elevate if no artifact was actively rejected
            if self.frozen_policy.calibration_status != "FAILED_CALIBRATION" and not any("Gate G2" in r or "mismatch" in r for r in self.artifact_rejection_reasons):
                if self.frozen_policy.policy_id == "POLICY-SIDAK-0.05":
                    self.frozen_policy = create_calibrated_hier_policy(regime=self.regime, evaluation_horizon=self.evaluation_horizon)
                    self.policy = MultiChannelAlertPolicy(
                        threshold_lat=self.frozen_policy.threshold_lat,
                        threshold_mem=self.frozen_policy.threshold_mem,
                        require_persistence=self.frozen_policy.require_persistence,
                        alpha=self.frozen_policy.alpha,
                    )
        return self.enable_auto_rollback

    def set_policy(self, policy: FrozenPolicy) -> None:
        """Set active policy, updating decision thresholds and calibration status."""
        is_valid, reasons = validate_policy_compatibility(
            policy,
            expected_model_id=self.expected_model_id,
            expected_regime=self.regime,
            horizon=self.evaluation_horizon,
            require_calibrated=policy.is_calibrated,
        )
        if not is_valid:
            cal_status = "FAILED_CALIBRATION" if policy.gate_g2_status == "FAIL" else "UNVALIDATED_EXPLORATORY"
            self.frozen_policy = FrozenPolicy(
                policy_id=policy.policy_id,
                model_id=policy.model_id,
                model_hash=policy.model_hash,
                preprocess_id=policy.preprocess_id,
                preprocess_hash=policy.preprocess_hash,
                regime=self.regime,
                alpha=policy.alpha,
                threshold_lat=policy.threshold_lat,
                threshold_mem=policy.threshold_mem,
                threshold_scale=policy.threshold_scale,
                require_persistence=policy.require_persistence,
                persistence_window=policy.persistence_window,
                is_calibrated=False,
                calibration_status=cal_status,
                gate_g2_status=policy.gate_g2_status,
                achieved_far=None,
                evaluation_horizon=policy.evaluation_horizon,
                gate_g2_details=policy.gate_g2_details,
                validation_scope=policy.validation_scope,
                topology_constraints=policy.topology_constraints,
                rejection_reasons=tuple(reasons),
                artifact_hash=policy.artifact_hash,
                artifact_path=policy.artifact_path,
                description=f"Rejected policy: {'; '.join(reasons)}",
            )
            self.artifact_rejection_reasons = list(reasons)
        else:
            self.frozen_policy = policy
            self.artifact_rejection_reasons = []

        self.policy = MultiChannelAlertPolicy(
            threshold_lat=self.frozen_policy.threshold_lat,
            threshold_mem=self.frozen_policy.threshold_mem,
            require_persistence=self.frozen_policy.require_persistence,
            alpha=self.frozen_policy.alpha,
        )

    def set_deployment(self, release_id: str, canary_ids: list[str], t0: int) -> None:
        """Notify detector service of an active canary deployment at tick t0.

        Strict Causality:
        Fits PrePeriodBaseline using ONLY records received before t0 (event_time < t0).
        """
        self.active_release_id = release_id
        self.active_canary_ids = list(canary_ids)
        self.t0 = int(t0)
        self.is_rolled_back = False
        self.rollback_tick = None
        self.first_alert_tick = None
        self.auto_rollback_triggered = False
        self.intervention_tick = None

        # Fit pre-period baseline if not already fitted
        pre_records = [r for r in self.raw_records if r.event_time < self.t0 and r.arrival_time <= self.t0]
        if pre_records:
            baseline = fit_preperiod_baseline(
                records=pre_records,
                t0=self.t0,
                expected_servers=self.expected_servers,
                protocol=self.protocol,
            )
            self.slice_builder.baseline = baseline

        # Initialize Latency & Memory Detectors for active canaries
        canary_classes = [self.server_metadata[cid].get("class_id", 0) for cid in self.active_canary_ids]
        canary_caps = [float(self.server_metadata[cid].get("memory_capacity_mb", 16384.0)) for cid in self.active_canary_ids]
        ctrl_ids = [s for s in self.expected_servers if s not in self.active_canary_ids]

        self.memory_target = MemoryTargetDefinition(
            persistence_window_ticks=self.frozen_policy.persistence_window,
            growth_boundary_mb_per_min=self.frozen_policy.kappa_mem,
        )
        self.lat_filter = OnlineHierarchicalLatencyFilter(
            canary_ids=self.active_canary_ids,
            canary_classes=canary_classes,
            params=self.effect_params,
            kappa=self.frozen_policy.kappa_lat,
        )
        self.lat_filter_indep = OnlineHierarchicalLatencyFilter(
            canary_ids=self.active_canary_ids,
            canary_classes=canary_classes,
            params=EffectParams(kind="indep", rho_g=self.effect_params.rho_g, sd_g=self.effect_params.sd_g, prior_sd=self.effect_params.prior_sd),
            kappa=self.frozen_policy.kappa_lat,
        )
        self.lat_filter_pooled = OnlineHierarchicalLatencyFilter(
            canary_ids=self.active_canary_ids,
            canary_classes=canary_classes,
            params=EffectParams(kind="pooled", rho_g=self.effect_params.rho_g, sd_g=self.effect_params.sd_g, prior_sd=self.effect_params.prior_sd),
            kappa=self.frozen_policy.kappa_lat,
        )
        self.mem_detector = OnlineMemoryGrowthDetector(
            t0=self.t0,
            canary_ids=self.active_canary_ids,
            control_ids=ctrl_ids,
            canary_capacities_mb=canary_caps,
            target_definition=self.memory_target,
        )

        # Pre-period noise conditioning: step through pre-period residuals to align prior at t0
        if self.slice_builder.baseline is not None and self.t0 is not None and self.t0 > 0:
            for t_pre in range(self.t0):
                slice_pre = self.slice_builder.build_slice(t_pre)
                nc = len(self.active_canary_ids)
                r_pre = np.zeros(nc, dtype=float)
                m_pre = np.zeros(nc, dtype=bool)
                cov_pre = np.zeros((nc, nc), dtype=float)
                for i, cid in enumerate(self.active_canary_ids):
                    if cid in slice_pre.canary_ids:
                        s_idx = slice_pre.canary_ids.index(cid)
                        r_pre[i] = slice_pre.r_latency[s_idx]
                        m_pre[i] = slice_pre.mask_latency[s_idx]
                if slice_pre.cov_U is not None and slice_pre.cov_U.size > 0:
                    for i, cid_i in enumerate(self.active_canary_ids):
                        if cid_i in slice_pre.canary_ids:
                            idx_i = slice_pre.canary_ids.index(cid_i)
                            for j, cid_j in enumerate(self.active_canary_ids):
                                if cid_j in slice_pre.canary_ids:
                                    idx_j = slice_pre.canary_ids.index(cid_j)
                                    cov_pre[i, j] = slice_pre.cov_U[idx_i, idx_j]
                self.lat_filter.step_preperiod(r_pre, m_pre, cov_pre)
                self.lat_filter_indep.step_preperiod(r_pre, m_pre, cov_pre)
                self.lat_filter_pooled.step_preperiod(r_pre, m_pre, cov_pre)

            self.lat_filter.initialize_rollout()
            self.lat_filter_indep.initialize_rollout()
            self.lat_filter_pooled.initialize_rollout()

    def set_rollback(self, tick: int) -> None:
        """Record rollback event. Freezes further canary release alerts."""
        self.is_rolled_back = True
        self.rollback_tick = int(tick)
        self.active_release_id = None
        self.active_canary_ids.clear()

    # -----------------------------------------------------------------
    # Telemetry Ingestion & Tick Evaluation
    # -----------------------------------------------------------------
    def ingest(self, records: list[TelemetryRecord]) -> None:
        """Ingest new TelemetryRecords arriving from the world or network."""
        for r in records:
            self.raw_records.append(r)
            self.latest_telemetry_by_server[r.server_id] = r
        self.slice_builder.ingest(records)

    def step(self, decision_tick: int) -> DetectorTickResult:
        """Process one discrete decision timestamp causally.

        Guarantees:
        - Only records with arrival_time <= decision_tick are admitted.
        - Physical rack nuisances are estimated from baseline controls.
        - Latency effect extraction isolates release effect with uncertainty intervals.
        - Memory drift and capacity guardrails are evaluated.
        - If rack controls are absent, release cause inference is strictly prohibited.
        """
        # Contemporaneous telemetry records
        contemp_recs = {
            r.server_id: r for r in self.raw_records
            if r.event_time == decision_tick and r.arrival_time <= decision_tick
        }

        # Step 0: Ensure baseline exists for slice builder if we have enough pre-period records
        if self.slice_builder.baseline is None:
            pre_records = [r for r in self.raw_records if r.arrival_time <= decision_tick]
            if len(pre_records) >= len(self.expected_servers):
                t0_fit = decision_tick + 1 if not self.active_canary_ids else (self.t0 or (decision_tick + 1))
                try:
                    self.slice_builder.baseline = fit_preperiod_baseline(
                        records=pre_records,
                        t0=t0_fit,
                        expected_servers=self.expected_servers,
                        protocol=self.protocol,
                    )
                except Exception:
                    pass

        # If baseline is still None or no active canary, evaluate infrastructure and return null result
        if self.slice_builder.baseline is None or not self.active_canary_ids:
            infra_adv, infra_reason = self._evaluate_infrastructure_advisory(None, contemp_recs)
            release_adv = "ROLLED BACK" if self.is_rolled_back else "RUNNING"
            attr = "ROLLED_BACK" if self.is_rolled_back else "NORMAL"
            res = self._build_null_result(
                tick=decision_tick,
                infra_adv=infra_adv,
                infra_reason=infra_reason,
                release_adv=release_adv,
                attribution=attr,
                contemp_recs=contemp_recs,
                time_slice=None,
            )
            self.history.append(res)
            return res

        # Step 1: Form contemporaneous TimeSlice
        time_slice = self.slice_builder.build_slice(decision_tick)

        # Step 2: Separate Infrastructure Advisory (From same-rack baseline controls)
        infra_adv, infra_reason = self._evaluate_infrastructure_advisory(time_slice, contemp_recs)

        # Step 3: Handle No Active Canary / Post-Rollback State
        if not self.active_canary_ids:
            release_adv = "ROLLED BACK" if self.is_rolled_back else "RUNNING"
            attr = "ROLLED_BACK" if self.is_rolled_back else "NORMAL"
            res = self._build_null_result(
                tick=decision_tick,
                infra_adv=infra_adv,
                infra_reason=infra_reason,
                release_adv=release_adv,
                attribution=attr,
                contemp_recs=contemp_recs,
                time_slice=time_slice,
            )
            self.history.append(res)
            return res

        # Step 4: Identifiability Guard & Control Coverage Check
        can_infer, ident_reason = infer_release_cause(time_slice)
        if not can_infer or time_slice.is_unidentifiable:
            res = self._build_unidentifiable_result(
                tick=decision_tick,
                infra_adv=infra_adv,
                ident_reason=ident_reason,
                contemp_recs=contemp_recs,
                time_slice=time_slice,
            )
            self.history.append(res)
            return res

        # Step 5: Latency Channel Update
        nc = len(self.active_canary_ids)
        r_lat_canaries = np.zeros(nc, dtype=float)
        mask_lat_canaries = np.zeros(nc, dtype=bool)
        for i, cid in enumerate(self.active_canary_ids):
            if cid in time_slice.canary_ids:
                s_idx = time_slice.canary_ids.index(cid)
                r_lat_canaries[i] = time_slice.r_latency[s_idx]
                mask_lat_canaries[i] = time_slice.mask_latency[s_idx]

        cov_canaries = np.zeros((nc, nc), dtype=float)
        if hasattr(time_slice, "cov_U") and time_slice.cov_U is not None and time_slice.cov_U.size > 0:
            for i, cid_i in enumerate(self.active_canary_ids):
                if cid_i in time_slice.canary_ids:
                    idx_i = time_slice.canary_ids.index(cid_i)
                    for j, cid_j in enumerate(self.active_canary_ids):
                        if cid_j in time_slice.canary_ids:
                            idx_j = time_slice.canary_ids.index(cid_j)
                            cov_canaries[i, j] = time_slice.cov_U[idx_i, idx_j]

        a_hat, a_se, class_thetas, class_thetas_se, score_lat = self.lat_filter.step(
            r_latency=r_lat_canaries,
            obs_mask=mask_lat_canaries,
            cov_U=cov_canaries,
        )

        # Step comparison filters (Independent and Pooled SSM) for real-time shrinkage analysis
        if hasattr(self, "lat_filter_indep") and self.lat_filter_indep is not None:
            self.lat_filter_indep.step(r_latency=r_lat_canaries, obs_mask=mask_lat_canaries, cov_U=cov_canaries)
        if hasattr(self, "lat_filter_pooled") and self.lat_filter_pooled is not None:
            self.lat_filter_pooled.step(r_latency=r_lat_canaries, obs_mask=mask_lat_canaries, cov_U=cov_canaries)

        # Step 6: Memory Channel Update
        ctrl_recs = {
            s: contemp_recs[s] for s in self.expected_servers
            if s not in self.active_canary_ids and s in contemp_recs
        }
        canary_recs = {
            s: contemp_recs[s] for s in self.active_canary_ids if s in contemp_recs
        }
        mem_res: MemoryStepResult = self.mem_detector.step(
            tick=decision_tick,
            canary_records=canary_recs,
            control_records=ctrl_recs,
            eligible=time_slice.eligible,
        )
        score_mem = float(mem_res.score) if np.isfinite(mem_res.score) else float("-inf")

        # Step 7: Multi-Channel Policy Decision & Attribution
        policy_eval = self.policy.evaluate_step(
            score_lat=score_lat,
            score_mem=score_mem,
            guardrail_status=mem_res.guardrail_status,
            is_persistent_mem=mem_res.is_persistent_leak,
            eligible=time_slice.eligible,
        )

        canary_release_adv = policy_eval["advisory"]
        attribution = policy_eval["attribution"]

        # Track first alert timestamp
        if policy_eval["is_alert"] and self.first_alert_tick is None:
            self.first_alert_tick = decision_tick

        # Formulate epistemic evidence text without claiming causal certainty
        advisory_reason = self._build_epistemic_reason(
            policy_eval=policy_eval,
            a_hat=a_hat,
            a_se=a_se,
            mem_res=mem_res,
            infra_reason=infra_reason,
        )

        # Check automated simulated rollback (Opt-in operational mode)
        auto_rollback_now = False
        is_policy_calibrated = getattr(self.frozen_policy, "is_calibrated", False)
        if (
            self.enable_auto_rollback
            and is_policy_calibrated
            and policy_eval["is_alert"]
            and not self.auto_rollback_triggered
        ):
            self.auto_rollback_triggered = True
            self.intervention_tick = decision_tick
            auto_rollback_now = True

        # Build HostEvidence and ClassEvidence records
        hosts_evidence = self._build_host_evidence(
            contemp_recs=contemp_recs,
            a_hat=a_hat,
            a_se=a_se,
            mem_res=mem_res,
        )
        class_evidence = [
            ClassEvidence(
                class_id=int(self.lat_filter.canary_classes[g] if g < len(self.lat_filter.canary_classes) else g),
                theta=float(class_thetas[g]),
                theta_se=float(class_thetas_se[g]),
                ci_lower=float(class_thetas[g] - 1.96 * class_thetas_se[g]),
                ci_upper=float(class_thetas[g] + 1.96 * class_thetas_se[g]),
            )
            for g in range(len(class_thetas))
        ]

        # Aggregate series stats for charting
        canary_obs = [contemp_recs[s] for s in self.active_canary_ids if s in contemp_recs and contemp_recs[s].observed]
        ctrl_obs = [contemp_recs[s] for s in self.expected_servers if s not in self.active_canary_ids and s in contemp_recs and contemp_recs[s].observed]

        mean_c_eff = float(np.mean(a_hat)) if len(a_hat) else 0.0
        mean_c_se = float(np.mean(a_se)) if len(a_se) else 0.0

        rel_score = float(max(score_lat, score_mem))
        mon_state = SystemMonitoringState.MONITORING if self.frozen_policy.is_calibrated else SystemMonitoringState.UNCALIBRATED_POLICY

        tick_result = DetectorTickResult(
            tick=decision_tick,
            t0=self.t0,
            eligible=time_slice.eligible,
            is_unidentifiable=False,
            ineligible_reasons=list(time_slice.ineligible_reasons),
            attribution_blocked_reasons=[],
            infrastructure_advisory=infra_adv,
            canary_release_advisory=canary_release_adv,
            attribution=attribution,
            advisory_reason=advisory_reason,
            epistemic_disclaimer=self.frozen_policy.epistemic_disclaimer,
            release_score=rel_score,
            release_score_prob=round(float(math.exp(rel_score)), 4) if np.isfinite(rel_score) else 0.0,
            score_lat=score_lat,
            score_mem=score_mem,
            threshold_lat=self.frozen_policy.threshold_lat,
            threshold_mem=self.frozen_policy.threshold_mem,
            threshold_lat_prob=round(float(math.exp(self.frozen_policy.threshold_lat)), 4),
            threshold_mem_prob=round(float(math.exp(self.frozen_policy.threshold_mem)), 4),
            threshold_scale=self.frozen_policy.threshold_scale,
            monitoring_state=mon_state,
            calibration_status=self.frozen_policy.calibration_status,
            is_calibrated=self.frozen_policy.is_calibrated,
            first_alert_tick=self.first_alert_tick,
            hosts=hosts_evidence,
            class_effects=class_evidence,
            canary_latency_mean=float(np.mean([r.latency_ms for r in canary_obs])) if canary_obs else 0.0,
            control_latency_mean=float(np.mean([r.latency_ms for r in ctrl_obs])) if ctrl_obs else 0.0,
            canary_memory_mean=float(np.mean([r.memory_mb for r in canary_obs])) if canary_obs else 0.0,
            control_memory_mean=float(np.mean([r.memory_mb for r in ctrl_obs])) if ctrl_obs else 0.0,
            canary_cpu_mean=float(np.mean([r.cpu_fraction for r in canary_obs])) if canary_obs else 0.0,
            control_cpu_mean=float(np.mean([r.cpu_fraction for r in ctrl_obs])) if ctrl_obs else 0.0,
            canary_errors_sum=int(sum(r.error_count for r in canary_obs)),
            control_errors_sum=int(sum(r.error_count for r in ctrl_obs)),
            canary_effect_mean=mean_c_eff,
            canary_effect_ci_lower=mean_c_eff - 1.96 * mean_c_se,
            canary_effect_ci_upper=mean_c_eff + 1.96 * mean_c_se,
            auto_rollback_triggered=self.auto_rollback_triggered,
            intervention_tick=self.intervention_tick,
            censored=self.auto_rollback_triggered,
        )

        self.history.append(tick_result)
        return tick_result

    # -----------------------------------------------------------------
    # Advisory Helpers & Epistemic Honesty
    # -----------------------------------------------------------------
    def _evaluate_infrastructure_advisory(
        self,
        time_slice: TimeSlice | None,
        contemp_recs: dict[str, TelemetryRecord],
    ) -> tuple[str, str]:
        """Separately evaluate physical rack and fleet infrastructure nuisances."""
        degraded_racks: list[str] = []
        racks_seen = set()

        for sid, rec in contemp_recs.items():
            if sid not in self.active_canary_ids and rec.observed:
                racks_seen.add(rec.rack_id)

        # Check estimated rack nuisances from TimeSlice (gamma_hat_j) if available
        if time_slice is not None and time_slice.gamma_hat:
            for rk, gamma_val in time_slice.gamma_hat.items():
                if gamma_val > 0.12:  # > +13% log-latency shift on baseline controls
                    degraded_racks.append(rk)
        else:
            # Direct contrast from contemporaneous control observations
            ctrl_recs = [r for sid, r in contemp_recs.items() if sid not in self.active_canary_ids and r.observed]
            if ctrl_recs:
                fleet_mean_log = float(np.mean([math.log(max(1.0, r.latency_ms)) for r in ctrl_recs]))
                for rk in racks_seen:
                    rk_ctrls = [r for r in ctrl_recs if r.rack_id == rk]
                    if rk_ctrls:
                        rk_mean_log = float(np.mean([math.log(max(1.0, r.latency_ms)) for r in rk_ctrls]))
                        if rk_mean_log - fleet_mean_log > 0.12:
                            degraded_racks.append(rk)

        if len(degraded_racks) >= len(racks_seen) and len(racks_seen) > 1:
            return "FLEET_OUTAGE", f"Fleet-wide degradation detected across all {len(degraded_racks)} racks."
        elif degraded_racks:
            return f"RACK_DEGRADED: {', '.join(degraded_racks)}", f"Infrastructure slowdown detected on {', '.join(degraded_racks)}."
        else:
            return "NORMAL", "Infrastructure telemetry within nominal bounds."

    def _build_epistemic_reason(
        self,
        policy_eval: dict[str, Any],
        a_hat: np.ndarray,
        a_se: np.ndarray,
        mem_res: MemoryStepResult,
        infra_reason: str,
    ) -> str:
        """Construct user-facing explanation preserving epistemic honesty."""
        attr = policy_eval["attribution"]
        if attr == "NORMAL":
            return f"Canary telemetry healthy and matched to concurrent controls. | {infra_reason}"

        details: list[str] = []
        if policy_eval["lat_breach"]:
            max_idx = int(np.argmax(a_hat))
            eff_pct = (np.exp(a_hat[max_idx]) - 1.0) * 100.0
            ci_lo = (np.exp(a_hat[max_idx] - 1.96 * a_se[max_idx]) - 1.0) * 100.0
            ci_hi = (np.exp(a_hat[max_idx] + 1.96 * a_se[max_idx]) - 1.0) * 100.0
            details.append(
                f"Elevated latency contrast on {self.active_canary_ids[max_idx]} (+{eff_pct:.1f}%, 95% CI: [{ci_lo:.1f}%, {ci_hi:.1f}%])"
            )

        if policy_eval["mem_breach"]:
            max_g_idx = int(np.argmax(mem_res.growth_rate_estimates))
            g_rate = mem_res.growth_rate_estimates[max_g_idx]
            details.append(
                f"Canary process memory elevated with persistent growth on {self.active_canary_ids[max_g_idx]} (+{g_rate:.2f} MB/min over controls, >=15 min)"
            )

        if policy_eval["guardrail_status"] == "CRITICAL_OOM_RISK":
            details.append("Critical capacity headroom limit reached (<1024 MB or TTE < 30 min)")

        explanation = "; ".join(details)
        return (
            f"STATISTICAL PAUSE ADVISORY [{attr}]: {explanation}. "
            f"Consistent with release regression; observational evidence, not proof of code bug. | {infra_reason}"
        )

    def _build_host_evidence(
        self,
        contemp_recs: dict[str, TelemetryRecord],
        a_hat: np.ndarray,
        a_se: np.ndarray,
        mem_res: MemoryStepResult,
    ) -> dict[str, HostEvidence]:
        """Compile host-level evidence dictionary."""
        res: dict[str, HostEvidence] = {}
        for sid in self.expected_servers:
            meta = self.server_metadata.get(sid, {})
            rk = meta.get("rack_id", "unknown")
            cls_id = meta.get("class_id", 0)
            rec = contemp_recs.get(sid)

            is_canary = sid in self.active_canary_ids
            if is_canary:
                idx = self.active_canary_ids.index(sid)
                eff = float(a_hat[idx])
                se = float(a_se[idx])
                z = (eff - self.frozen_policy.kappa_lat) / se
                risk = float(norm.sf(-z))
                score = float(norm.logsf(-z))
                eff_pct = (math.exp(eff) - 1.0) * 100.0 if np.isfinite(eff) else None
                ci_lo_pct = (math.exp(eff - 1.96 * se) - 1.0) * 100.0 if np.isfinite(eff) and np.isfinite(se) else None
                ci_hi_pct = (math.exp(eff + 1.96 * se) - 1.0) * 100.0 if np.isfinite(eff) and np.isfinite(se) else None
                g_rate = float(mem_res.growth_rate_estimates[idx]) if idx < len(mem_res.growth_rate_estimates) else None
                g_se = float(mem_res.growth_rate_se[idx]) if idx < len(mem_res.growth_rate_se) else None
                headroom = float(mem_res.host_headroom_mb[idx]) if idx < len(mem_res.host_headroom_mb) else None
                tte = float(mem_res.host_tte_min[idx]) if idx < len(mem_res.host_tte_min) else None
                guard = mem_res.guardrail_status
                persist = mem_res.is_persistent_leak
            else:
                eff = se = risk = score = eff_pct = ci_lo_pct = ci_hi_pct = g_rate = g_se = headroom = tte = None
                guard = "NORMAL"
                persist = False

            res[sid] = HostEvidence(
                server_id=sid,
                role="CANARY" if is_canary else "CONTROL",
                rack_id=rk,
                class_id=cls_id,
                latency_effect=eff,
                latency_se=se,
                latency_ci_lower=eff - 1.96 * se if eff is not None and se is not None else None,
                latency_ci_upper=eff + 1.96 * se if eff is not None and se is not None else None,
                latency_effect_pct=eff_pct,
                latency_ci_lower_pct=ci_lo_pct,
                latency_ci_upper_pct=ci_hi_pct,
                host_risk=risk,
                host_log_score=score,
                memory_drift_mb_per_min=g_rate,
                memory_drift_se=g_se,
                headroom_mb=headroom,
                tte_min=tte,
                guardrail_status=guard,
                is_persistent_mem=persist,
                latency_ms=rec.latency_ms if rec else 0.0,
                memory_mb=rec.memory_mb if rec else 0.0,
                cpu_fraction=rec.cpu_fraction if rec else 0.0,
                error_count=rec.error_count if rec else 0,
                request_count=rec.request_count if rec else 0,
                observed=rec.observed if rec else False,
            )
        return res

    def _build_null_result(
        self,
        tick: int,
        infra_adv: str,
        infra_reason: str,
        release_adv: str,
        attribution: str,
        contemp_recs: dict[str, TelemetryRecord],
        time_slice: TimeSlice | None = None,
    ) -> DetectorTickResult:
        """Build null result when no canary is actively deployed, release is rolled back, or awaiting data."""
        hosts = {}
        for sid in self.expected_servers:
            rec = contemp_recs.get(sid)
            meta = self.server_metadata.get(sid, {})
            hosts[sid] = HostEvidence(
                server_id=sid,
                role="CONTROL",
                rack_id=meta.get("rack_id", "unknown"),
                class_id=meta.get("class_id", 0),
                latency_ms=rec.latency_ms if rec else 0.0,
                memory_mb=rec.memory_mb if rec else 0.0,
                cpu_fraction=rec.cpu_fraction if rec else 0.0,
                error_count=rec.error_count if rec else 0,
                request_count=rec.request_count if rec else 0,
                observed=rec.observed if rec else False,
            )

        # Distinguish truly uninitialized state from post-rollback or healthy baseline
        if not contemp_recs:
            mon_state = SystemMonitoringState.WAITING_FOR_DATA
            infra_adv = "WAITING_FOR_DATA"
            release_adv = "WAITING_FOR_DATA"
            attribution = "WAITING_FOR_DATA"
            adv_reason = "Awaiting initial simulation telemetry slice."
        elif self.is_rolled_back:
            mon_state = SystemMonitoringState.MONITORING
            adv_reason = f"Release was rolled back at tick {self.rollback_tick}. | {infra_reason}"
        else:
            mon_state = SystemMonitoringState.MONITORING
            adv_reason = f"No active canary release deployed. | {infra_reason}"

        return DetectorTickResult(
            tick=tick,
            t0=self.t0,
            eligible=True,
            is_unidentifiable=False,
            ineligible_reasons=[],
            attribution_blocked_reasons=[],
            infrastructure_advisory=infra_adv,
            canary_release_advisory=release_adv,
            attribution=attribution,
            advisory_reason=adv_reason,
            epistemic_disclaimer=self.frozen_policy.epistemic_disclaimer,
            release_score=None,
            release_score_prob=None,
            score_lat=None,
            score_mem=None,
            threshold_lat=self.frozen_policy.threshold_lat,
            threshold_mem=self.frozen_policy.threshold_mem,
            threshold_lat_prob=round(float(math.exp(self.frozen_policy.threshold_lat)), 4),
            threshold_mem_prob=round(float(math.exp(self.frozen_policy.threshold_mem)), 4),
            threshold_scale=self.frozen_policy.threshold_scale,
            monitoring_state=mon_state,
            calibration_status=self.frozen_policy.calibration_status,
            is_calibrated=self.frozen_policy.is_calibrated,
            first_alert_tick=None,
            hosts=hosts,
            class_effects=[],
            canary_latency_mean=0.0,
            control_latency_mean=float(np.mean([r.latency_ms for r in contemp_recs.values()])) if contemp_recs else 0.0,
            canary_memory_mean=0.0,
            control_memory_mean=float(np.mean([r.memory_mb for r in contemp_recs.values()])) if contemp_recs else 0.0,
            canary_cpu_mean=0.0,
            control_cpu_mean=float(np.mean([r.cpu_fraction for r in contemp_recs.values()])) if contemp_recs else 0.0,
            canary_errors_sum=0,
            control_errors_sum=int(sum(r.error_count for r in contemp_recs.values())),
            canary_effect_mean=0.0,
            canary_effect_ci_lower=0.0,
            canary_effect_ci_upper=0.0,
        )

    def _build_unidentifiable_result(
        self,
        tick: int,
        infra_adv: str,
        ident_reason: str,
        contemp_recs: dict[str, TelemetryRecord],
        time_slice: TimeSlice,
    ) -> DetectorTickResult:
        """Build unidentifiable result when rack or class control coverage is violated."""
        hosts = {}
        for sid in self.expected_servers:
            rec = contemp_recs.get(sid)
            meta = self.server_metadata.get(sid, {})
            hosts[sid] = HostEvidence(
                server_id=sid,
                role="CANARY" if sid in self.active_canary_ids else "CONTROL",
                rack_id=meta.get("rack_id", "unknown"),
                class_id=meta.get("class_id", 0),
                latency_ms=rec.latency_ms if rec else 0.0,
                memory_mb=rec.memory_mb if rec else 0.0,
                cpu_fraction=rec.cpu_fraction if rec else 0.0,
                error_count=rec.error_count if rec else 0,
                request_count=rec.request_count if rec else 0,
                observed=rec.observed if rec else False,
            )
        return DetectorTickResult(
            tick=tick,
            t0=self.t0,
            eligible=False,
            is_unidentifiable=True,
            ineligible_reasons=list(time_slice.ineligible_reasons),
            attribution_blocked_reasons=list(time_slice.attribution_blocked_reasons),
            infrastructure_advisory=infra_adv,
            canary_release_advisory="INSUFFICIENT DATA / CONFLICT",
            attribution="INSUFFICIENT_DATA",
            advisory_reason=f"IDENTIFIABILITY_GUARD: Confounded allocation - {ident_reason}. Release cause attribution is strictly prohibited without concurrent same-rack controls.",
            epistemic_disclaimer=self.frozen_policy.epistemic_disclaimer,
            release_score=None,
            release_score_prob=None,
            score_lat=None,
            score_mem=None,
            threshold_lat=self.frozen_policy.threshold_lat,
            threshold_mem=self.frozen_policy.threshold_mem,
            threshold_lat_prob=round(float(math.exp(self.frozen_policy.threshold_lat)), 4),
            threshold_mem_prob=round(float(math.exp(self.frozen_policy.threshold_mem)), 4),
            threshold_scale=self.frozen_policy.threshold_scale,
            monitoring_state=SystemMonitoringState.INSUFFICIENT_DATA,
            calibration_status=self.frozen_policy.calibration_status,
            is_calibrated=self.frozen_policy.is_calibrated,
            first_alert_tick=self.first_alert_tick,
            hosts=hosts,
            class_effects=[],
            canary_latency_mean=0.0,
            control_latency_mean=float(np.mean([r.latency_ms for r in contemp_recs.values()])) if contemp_recs else 0.0,
            canary_memory_mean=0.0,
            control_memory_mean=float(np.mean([r.memory_mb for r in contemp_recs.values()])) if contemp_recs else 0.0,
            canary_cpu_mean=0.0,
            control_cpu_mean=float(np.mean([r.cpu_fraction for r in contemp_recs.values()])) if contemp_recs else 0.0,
            canary_errors_sum=0,
            control_errors_sum=int(sum(r.error_count for r in contemp_recs.values())),
            canary_effect_mean=0.0,
            canary_effect_ci_lower=0.0,
            canary_effect_ci_upper=0.0,
        )

    # -----------------------------------------------------------------
    # Query API (Used by FastAPI Routes)
    # -----------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        """Return current detector state, advisories, models, and eligibility."""
        common_policy_meta = {
            "model_id": self.frozen_policy.model_id,
            "policy_id": self.frozen_policy.policy_id,
            "regime": self.frozen_policy.regime,
            "calibration_status": self.frozen_policy.calibration_status,
            "is_calibrated": self.frozen_policy.is_calibrated,
            "gate_g2_status": self.frozen_policy.gate_g2_status,
            "gate_g2_details": self.frozen_policy.gate_g2_details,
            "artifact_path": self.frozen_policy.artifact_path,
            "artifact_hash": self.frozen_policy.artifact_hash,
            "artifact_rejection_reasons": list(self.artifact_rejection_reasons),
            "validation_scope": self.frozen_policy.validation_scope,
            "threshold_scale": self.frozen_policy.threshold_scale,
            "threshold_lat": self.frozen_policy.threshold_lat,
            "threshold_mem": self.frozen_policy.threshold_mem,
            "threshold_lat_prob": round(float(math.exp(self.frozen_policy.threshold_lat)), 4),
            "threshold_mem_prob": round(float(math.exp(self.frozen_policy.threshold_mem)), 4),
            "evaluation_horizon": self.frozen_policy.evaluation_horizon,
            "achieved_far": self.frozen_policy.achieved_far,
            "epistemic_disclaimer": self.frozen_policy.epistemic_disclaimer,
            "auto_rollback_enabled": self.enable_auto_rollback,
            "auto_rollback_triggered": self.auto_rollback_triggered,
            "intervention_tick": self.intervention_tick,
        }

        if not self.ssm_connected:
            latest = self.history[-1] if self.history else None
            return {
                "ssm_connected": False,
                **common_policy_meta,
                "monitoring_state": SystemMonitoringState.CONNECTION_ERROR,
                "tick": latest.tick if latest else 0,
                "canary_release_advisory": "DETECTOR NOT CONNECTED",
                "infrastructure_advisory": latest.infrastructure_advisory if latest else "DETECTOR NOT CONNECTED",
                "attribution": "INSUFFICIENT_DATA",
                "release_score": None,
                "release_score_prob": None,
                "first_alert_tick": None,
                "advisory_reason": "DETECTOR NOT CONNECTED: Hierarchical SSM is offline or pending connection. Telemetry stream remains visible.",
                "data_eligibility": {
                    "eligible": False,
                    "is_unidentifiable": True,
                    "reason": "DETECTOR NOT CONNECTED",
                },
            }

        latest = self.history[-1] if self.history else None
        if not latest:
            return {
                "ssm_connected": True,
                **common_policy_meta,
                "monitoring_state": SystemMonitoringState.WAITING_FOR_DATA,
                "tick": 0,
                "canary_release_advisory": "WAITING_FOR_DATA",
                "infrastructure_advisory": "WAITING_FOR_DATA",
                "attribution": "WAITING_FOR_DATA",
                "release_score": None,
                "release_score_prob": None,
                "first_alert_tick": None,
                "advisory_reason": "Awaiting initial simulation telemetry slice.",
                "data_eligibility": {
                    "eligible": True,
                    "is_unidentifiable": False,
                },
            }

        # Check post-rollback state
        if self.is_rolled_back and not self.active_canary_ids:
            return {
                "ssm_connected": True,
                **common_policy_meta,
                "monitoring_state": SystemMonitoringState.MONITORING,
                "tick": latest.tick,
                "t0": self.t0,
                "canary_release_advisory": "ROLLED BACK",
                "infrastructure_advisory": latest.infrastructure_advisory,
                "attribution": "ROLLED_BACK",
                "release_score": None,
                "release_score_prob": None,
                "score_lat": None,
                "score_mem": None,
                "first_alert_tick": self.first_alert_tick,
                "advisory_reason": f"Release was rolled back at tick {self.rollback_tick}. | {latest.infrastructure_advisory}",
                "data_eligibility": {
                    "eligible": True,
                    "is_unidentifiable": False,
                },
            }

        # Determine active monitoring state
        if latest.is_unidentifiable or not latest.eligible:
            mon_state = SystemMonitoringState.INSUFFICIENT_DATA
        elif not self.frozen_policy.is_calibrated or len(self.artifact_rejection_reasons) > 0:
            mon_state = SystemMonitoringState.UNCALIBRATED_POLICY
        else:
            mon_state = SystemMonitoringState.MONITORING

        return {
            "ssm_connected": True,
            **common_policy_meta,
            "monitoring_state": mon_state,
            "tick": latest.tick,
            "t0": latest.t0,
            "canary_release_advisory": latest.canary_release_advisory,
            "infrastructure_advisory": latest.infrastructure_advisory,
            "attribution": latest.attribution,
            "release_score": latest.release_score,
            "release_score_prob": round(float(math.exp(latest.release_score)), 4) if latest.release_score is not None else None,
            "score_lat": latest.score_lat,
            "score_mem": latest.score_mem,
            "first_alert_tick": latest.first_alert_tick,
            "advisory_reason": latest.advisory_reason,
            "data_eligibility": {
                "eligible": latest.eligible,
                "is_unidentifiable": latest.is_unidentifiable,
                "ineligible_reasons": latest.ineligible_reasons,
                "attribution_blocked_reasons": latest.attribution_blocked_reasons,
                "active_canaries": len(self.active_canary_ids),
                "min_controls_per_rack": self.protocol.min_controls_per_rack,
                "min_controls_per_class": self.protocol.min_controls_per_class,
            },
        }

    def get_comparison_evidence(self) -> dict[str, Any]:
        """Return side-by-side comparison of Hierarchical SSM, Independent SSM, and Complete Pooling."""
        if not self.active_canary_ids or self.lat_filter is None:
            return {
                "active": False,
                "reason": "No active canary deployment.",
                "methods": {},
            }

        def format_filter_stats(flt: OnlineHierarchicalLatencyFilter, name: str, kind: str, description: str) -> dict[str, Any]:
            if flt.kf is None:
                return {"name": name, "kind": kind, "description": description, "active": False}
            am = flt.L @ flt.kf.m[:flt.d] if hasattr(flt, "L") else np.zeros(flt.nc)
            cov_mat = flt.L @ flt.kf.P[:flt.d, :flt.d] @ flt.L.T
            av = np.maximum(np.diag(cov_mat), 1e-18)
            ase = np.sqrt(av)
            zz = (flt.kappa - am) / ase
            probs = norm.sf(zz)
            log_probs = norm.logsf(zz)
            score = float(np.nanmax(log_probs)) if len(log_probs) else float("-inf")
            max_risk = float(np.nanmax(probs)) if len(probs) else 0.0

            hosts = []
            for i, cid in enumerate(flt.canary_ids):
                eff = float(am[i])
                se = float(ase[i])
                hosts.append({
                    "server_id": cid,
                    "effect": round(eff, 5),
                    "effect_pct": round((np.exp(eff) - 1.0) * 100.0, 2),
                    "se": round(se, 5),
                    "risk": round(float(probs[i]), 4),
                    "log_score": round(float(log_probs[i]), 4),
                })

            is_method_calibrated = (kind == "hier" and getattr(self.frozen_policy, "is_calibrated", False))
            cal_status = "CALIBRATED" if is_method_calibrated else "DIAGNOSTIC_ONLY"
            return {
                "name": name,
                "kind": kind,
                "description": description,
                "calibration_status": cal_status,
                "mean_effect": round(float(np.mean(am)), 5),
                "mean_effect_pct": round((np.exp(float(np.mean(am))) - 1.0) * 100.0, 2),
                "release_score": round(score, 4),
                "release_risk": round(max_risk, 4),
                "alert": bool(score > self.frozen_policy.threshold_lat) if is_method_calibrated else False,
                "diagnostic_alert": bool(score > self.frozen_policy.threshold_lat),
                "hosts": hosts,
            }

        methods = {
            "hierarchical": format_filter_stats(
                self.lat_filter,
                name="Hierarchical SSM (Partial Pooling)",
                kind="hier",
                description="Shrinks host-level canary estimates toward their class mean via Helmert contrast basis. Balances noise reduction with host-level sensitivity.",
            ),
        }
        if hasattr(self, "lat_filter_indep") and self.lat_filter_indep is not None:
            methods["independent"] = format_filter_stats(
                self.lat_filter_indep,
                name="Independent SSM (No Pooling)",
                kind="indep",
                description="Estimates each canary host in total isolation. High estimation variance on small samples; zero cross-host shrinkage.",
            )
        if hasattr(self, "lat_filter_pooled") and self.lat_filter_pooled is not None:
            methods["pooled"] = format_filter_stats(
                self.lat_filter_pooled,
                name="Pooled SSM (Complete Pooling)",
                kind="pooled",
                description="Forces all canaries to share a single common effect parameter. High power when harm is uniform, but completely washes out isolated single-host harm.",
            )

        return {
            "active": True,
            "canary_ids": list(self.active_canary_ids),
            "threshold_lat": self.frozen_policy.threshold_lat,
            "threshold_scale": self.frozen_policy.threshold_scale,
            "methods": methods,
        }

    def get_evidence(self) -> dict[str, Any]:
        """Return server-level and class-level evidence breakdowns."""
        latest = self.history[-1] if self.history else None
        if not latest:
            return {"servers": {}, "class_effects": []}

        return {
            "tick": latest.tick,
            "ssm_connected": self.ssm_connected,
            "servers": {k: v.to_dict() for k, v in latest.hosts.items()},
            "class_effects": [c.to_dict() for c in latest.class_effects],
        }

    def get_timeline(self, limit: int = 120) -> list[dict[str, Any]]:
        """Return historical detector timeline records for UI plotting."""
        entries = self.history[-limit:]
        return [e.to_dict() for e in entries]
