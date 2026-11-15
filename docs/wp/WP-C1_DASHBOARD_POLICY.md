# Work Package Report: WP-C1 / WP-C4
## Live Dashboard Detector Policy Binding and Runtime Contract

**Status**: Completed  
**Governing Documents**: `docs/Canary_SSM_Change_Plan.pdf` (Part 0, WP-C1, WP-C3, WP-C4, WP-C5), `AGENTS.md`, `docs/DESIGN_DECISIONS.md`  
**Target Component**: `canary_ssm/detector_service.py`, `canary_ssm/api/service.py`, `canary_ssm/dashboard/`

---

### 1. Context and Problem Statement

Prior to this work package, the live `DetectorService` exhibited significant epistemic defects:
1. **Unverified Hard-Coded Defaults**: `DetectorService.__init__` and `set_auto_rollback` silently defaulted or escalated uncalibrated exploratory runs to `create_calibrated_hier_policy()` with hardcoded numbers (`threshold_lat = -1.14122`, `threshold_mem = -0.67302`), claiming calibration without inspecting an artifact file on disk or verifying model hashes, regimes, horizons, or Gate G2 validity.
2. **Unsupported Fleet-Wide Claims**: A naive host-risk cutoff fails fleet-wide false-alert control. A policy can only be described as calibrated if backed by a compatible, passing frozen calibration artifact produced under strict data-role separation.
3. **Open Failure Modes**: The saved plain-regime Gate G2 artifact (`artifacts/policy_plain/gate_status.json`) has an overall status of **FAIL** (118/119 cells passed; `hier_rank0` failed under `S5_label_errors` with $p = 1.22 \times 10^{-8}$). Furthermore, the shared-workload-step failure remains open. Global calibration cannot be claimed.

---

### 2. Runtime Policy-Artifact Contract

We defined the versioned runtime contract `PolicyArtifactContract` in `canary_ssm/detector_service.py`:

```python
@dataclass
class PolicyArtifactContract:
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
    calibration_status: str = "UNVALIDATED_EXPLORATORY"  # "CALIBRATED" | "UNVALIDATED_EXPLORATORY" | "FAILED_CALIBRATION"
    gate_g2_status: str = "NOT_EVALUATED"                # "PASS" | "FAIL" | "NOT_EVALUATED" | "UNEVALUABLE"
    gate_g2_details: dict[str, Any] = field(default_factory=dict)
    validation_scope: dict[str, Any] = field(default_factory=dict)
    topology_constraints: dict[str, Any] = field(default_factory=dict)
    artifact_hash: str | None = None
    source_path: str | None = None
```

---

### 3. Safe Artifact Loader & Verification Rules

The safe loader `load_runtime_policy_artifact` verifies the artifact against the running environment before granting calibrated status:

1. **Existence & Parse Safety**:
   - `artifact_path is None` => Explicit `UNVALIDATED_EXPLORATORY` policy; `is_calibrated = False`.
   - Missing path or corrupt JSON => Explicit rejection with detailed error; fallback to exploratory mode.
2. **Model Compatibility**:
   - Compares declared `model_id` and `model_hash` with `expected_model_id`. Mismatches are rejected.
3. **Regime Compatibility**:
   - Compares declared `regime` with `expected_regime` (e.g., `'plain'` vs `'step'`). Mismatches are rejected.
4. **Horizon Coverage**:
   - Verifies calibrated horizon $\ge$ active monitoring horizon. Under-specified horizons are rejected.
5. **Scale & Range Constraints**:
   - Validates `threshold_scale == "LOG_POSTERIOR_RISK"` and thresholds $\le 0.0$ ($\log p \le 0$). Positive values on log scale are rejected.
6. **Gate G2 Status**:
   - Checks declared Gate G2 status (from JSON or companion `gate_status.json`). If status is not `PASS` (e.g., `FAIL` or `UNEVALUABLE`), the artifact is rejected for operational calibration (`calibration_status = "FAILED_CALIBRATION"`, `is_calibrated = False`).
7. **Topology Constraints**:
   - Validates fleet topology signature (`n_servers`, `n_classes`, `n_racks`) against minimum constraints if declared.
8. **No Silent Fallback**:
   - A rejected or missing artifact **never** falls back to hardcoded calibrated numbers. `is_calibrated` is strictly `False`.

---

### 4. Service & Dashboard Binding

1. **`DetectorService.__init__`**:
   - Accepts `policy_artifact: str | Path | None = None`, `regime: str = "plain"`, `evaluation_horizon: int = 75`.
   - Missing artifact initializes with `create_uncalibrated_exploratory_policy()`.
   - Stores `artifact_rejection_reasons` for inspection.
   - `set_auto_rollback` toggles intervention in demo mode but **never** mutates policy calibration status.
2. **`SimulatorService` & API Routes**:
   - Exposes `regime`, `gate_g2_status`, `artifact_path`, `artifact_hash`, `artifact_rejection_reasons` across `/api/detector/status`, `/api/monitoring/advisory`, and `/api/world/status`.
3. **Dashboard UI (`app.js`, `index.html`)**:
   - Renders active `model_id`, `policy_id`, `regime`.
   - Calibration badge:
     - `Calibrated Policy (Gate G2 PASS)` (canary green) when verified artifact passes.
     - `Policy Rejected (Incompatible)` (danger red) when artifact fails checks.
     - `Uncalibrated Exploratory` (warning orange) when exploratory.
   - Displays concise incompatibility reasons directly in the UI.
   - Disclaims unsupported FAR, PASS, or global deployment-readiness claims.

---

### 5. Verification & Test Suite

All 8 independently reasoned test cases in `tests/test_policy_artifact_binding.py` passed:
1. `test_valid_compatible_artifact_accepted`: Hand-written fixture passing Gate G2 accepted with `is_calibrated=True`.
2. `test_missing_artifact_becomes_exploratory`: `policy_artifact=None` sets `is_calibrated=False`, status `UNVALIDATED_EXPLORATORY`.
3. `test_model_mismatch_rejected`: Incompatible model ID rejected with explicit reason.
4. `test_regime_mismatch_rejected`: Regime mismatch (`step` in `plain`) rejected with explicit reason.
5. `test_horizon_mismatch_rejected`: Calibrated horizon 30 rejected when monitoring requires 75.
6. `test_failed_or_unevaluable_gate_g2_rejected`: Gate G2 `FAIL` and `UNEVALUABLE` fixtures rejected for operational recommendations.
7. `test_rejected_artifact_cannot_produce_calibrated_dashboard_status`: Verified that rejected artifacts never produce `is_calibrated=True` on detector status, advisory, or simulator endpoints.
8. `test_detector_firewall_remains_intact`: AST analysis of all detector modules (`detector_service`, `hierarchy`, `kalman`, `baselines`, `preprocess`, `factor`, `decision`) verifies zero truth or metrics imports.

---

### 6. Intentional Deviations from Governing Plan

None. The implementation strictly conforms to Part 0 rules, WP-C1, and WP-C4 requirements.
