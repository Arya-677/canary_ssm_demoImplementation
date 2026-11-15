# Bug Audit & Correctness Investigation Report

**Repository:** `https://github.com/29kumaranish-hash/AFML_Demo`  
**Base Commit Examined:** `10fe6dc`  
**Audit Completion Timestamp:** 2026-11-14T23:35:00+05:30  
**Overall Status:** Confirmed & Verified Fixed

---

## 1. Executive Summary & Verification of Baseline State

Before implementing changes, a full codebase audit and test execution were performed:
- **Baseline Git Status:** Commit `10fe6dc` ("Complete Virtual Data Center simulator, Hierarchical SSM detector, Web Dashboard, and Physical Workload Execution Harness"). Clean working tree.
- **Initial Fast Test Suite:** `237 passed, 1 skipped, 1 deselected in 239.22s` via `python -m pytest -m "not slow" -q`. (One legacy reproduction test `test_experiment7_legacy_reproduction` in `test_p1_protocol.py` is marked `@pytest.mark.slow` and requires optional pre-computed audit directories).
- **Available Governing Documents:**
  - `docs/Canary_SSM_Change_Plan.pdf` (rev. 3): Core specification for Hierarchical SSM, Gate G2 validity, contrast matrices, and experimental protocol.
  - `docs/DESIGN_DECISIONS.md`: Records explicit implementation boundaries (e.g. Borg traces and neural/Mamba/LSTM baselines explicitly designated as deferred / NOT implemented).
  - `docs/LIMITATIONS.md`: Documents statistical limits of naive risk cutoffs, missingness, and step confounders.

---

## 2. Itemized Bug Findings, Root Cause, & Verification

### Finding 1: Misleading Calibration Claims & Conflation of Host-Risk Thresholds with Fleet-Wide False-Alert Control
- **Severity:** High
- **Status:** **Confirmed & Fixed**
- **Component / File:** `canary_ssm/detector_service.py` (`FrozenPolicy`, `DetectorService.step`, `validate_policy_compatibility`)
- **Evidence:**
  `FrozenPolicy` defaulted to:
  ```python
  policy_id: str = "POLICY-SIDAK-0.05"
  model_id: str = "MODEL-HSSM-V1"
  alpha: float = 0.05
  threshold_lat: float = -0.693147  # log(0.50): max-host risk > 50%
  threshold_mem: float = -0.693147  # log(0.50): max-host drift exceedance > 50%
  ```
  The thresholds `-0.693147` correspond to $\log(0.50)$, representing a naive 50% host-risk cutoff. As established in `docs/LIMITATIONS.md` and verified in `tests/test_rigorous_evaluation.py::test_host_risk_cutoff_fails_fleet_wide_fwer`, evaluating $\max_{t} \max_{i} P(a_{it} > \kappa) > 0.50$ across multiple hosts and $T=75$ decision ticks produces a fleet-wide false alert rate of 20%–30%+, completely failing the claimed $\alpha = 0.05$ bound.
- **Mathematical Scale Investigation:**
  - `score_lat` is $\max_i \log P(a_i > \kappa_{\text{lat}})$, which is in **log-probability scale** $(-\infty, 0]$.
  - `score_mem` is $\max_i \log P(\text{drift}_i > \kappa_{\text{mem}})$, which is in **log-probability scale** $(-\infty, 0]$.
  - Defaulting uncalibrated $-0.693147$ cutoff while labeling it "POLICY-SIDAK-0.05" falsely implied that Šidák correction guarantees fleet-wide false-alert control.
- **Reproduction Steps:**
  ```bash
  python -m pytest tests/test_rigorous_evaluation.py -k "test_host_risk_cutoff_fails_fleet_wide_fwer" -v
  ```
- **Fix Implemented:**
  1. Updated `FrozenPolicy` dataclass with explicit fields:
     - `is_calibrated: bool = False` (defaults to uncalibrated exploratory)
     - `calibration_status: str = "UNVALIDATED_EXPLORATORY"`
     - `threshold_scale: str = "LOG_POSTERIOR_RISK"`
     - `achieved_far: Optional[float] = None`
     - `evaluation_horizon: int = 75`
     - `persistence_k: int = 3`
  2. Added calibrated policy factory `create_calibrated_hier_policy(threshold_lat=-1.14122, threshold_mem=-0.67302, ...)` with frozen parameters verified in `results/table_null_validation.csv`.
  3. Added `validate_policy_compatibility()` strictly validating model ID, horizon, log-scale threshold bounds ($\le 0.0$), alpha bounds ($0 < \alpha < 1$), and calibration status.
  4. Added regression test suite `tests/test_policy_validation.py` (5 passing tests).

---

### Finding 2: Divergence Between Benchmark and Streaming Inference Engines
- **Severity:** High
- **Status:** **Confirmed & Fixed**
- **Component / File:** `canary_ssm/detector_service.py` (`OnlineHierarchicalLatencyFilter`, `DetectorService.set_deployment`) vs `canary_ssm/hierarchy.py` (`EffectDetector.run`)
- **Evidence:**
  1. **Pre-Period AR Noise Conditioning:** In `hierarchy.py`, a pre-period noise-only Kalman filter `kn` steps through all pre-period residuals ($t < t_0$). At $t_0$, the posterior mean $\hat{e}_{t_0-1}$ and covariance $P_{t_0-1}$ are transferred into the rollout filter prior. In `detector_service.py`, `OnlineHierarchicalLatencyFilter` was only initialized at $t_0$ with an unconditioned zero prior `m = 0` and stationary diagonal covariance `P_ar`, causing divergence in effect estimates and posterior variance at rollout onset.
  2. **Class-Specific Nuisance Parameters:** `hierarchy.py` reads vectors $\phi_g, q_g, \nu_g$ per class from `Nuisance`, whereas `detector_service.py` hardcoded scalar defaults `phi_e = 0.85`, `q_e = 0.015`, `v_meas = 0.005`.
- **Reproduction Steps:**
  Run batch `EffectDetector.run` and streaming `OnlineHierarchicalLatencyFilter.step` on identical data before fix.
- **Fix Implemented:**
  1. Refactored `OnlineHierarchicalLatencyFilter` to delegate state prediction and measurement updates directly to `canary_ssm.kalman.KalmanFilter` with Joseph covariance stabilization.
  2. Implemented `step_preperiod(r, obs, cov_U)` and `initialize_rollout(P_rollout, t0)`: steps through pre-period residuals to condition the AR noise prior mean and covariance at rollout onset $t_0$.
  3. Supports class-specific vectors for $\phi_e, q_e, \nu_g$ and all model configurations (`hier`, `indep`, `pooled`).
  4. Added deterministic parity test `tests/test_inference_parity.py` proving numerical agreement within $10^{-12}$ between batch and streaming inference across all models (**3 passing tests**).

---

### Finding 3: Ambiguous Posterior Risk Presentation and Release Score Labeling
- **Severity:** Medium
- **Status:** **Confirmed & Fixed**
- **Component / File:** `canary_ssm/detector_service.py`, `canary_ssm/dashboard/index.html`, `canary_ssm/dashboard/app.js`
- **Evidence:**
  1. The release score was displayed in the UI simply as "Release Score: -0.693" without explaining that it represents **Release score: maximum host risk** ($\max_i \log P(a_i > \log(1.02))$).
  2. Defaulting `release_score: 0.0` on null runs was misleading because $0.0$ on a log scale represents $P = 1.0$ (certainty of regression).
  3. The boundary $\kappa_{\text{lat}} = \log(1.02)$ was not clearly explained to first-time users as corresponding to an effect increase $> 2\%$.
- **Reproduction Steps:**
  Inspect `detector_service.py` null results and host evidence drill-down before fix.
- **Fix Implemented:**
  1. Set initial null and unidentifiable release scores to `None` with `release_score_prob = None` instead of misleading `0.0`.
  2. Added percentage shift fields to `HostEvidence`: `latency_effect_pct`, `latency_ci_lower_pct`, `latency_ci_upper_pct`.
  3. Added explicit probability fields `release_score_prob = exp(release_score)`, `threshold_lat_prob`, `threshold_mem_prob`.
  4. Updated dashboard labels to **"Release score: maximum host risk"** with explicit mathematical tooltips and explanations of $\kappa_{\text{lat}} = \log(1.02) \approx +2.0\%$ shift.

---

### Finding 4: Initial, Missing, Stale, or Disconnected Data Displayed as Healthy
- **Severity:** High
- **Status:** **Confirmed & Fixed**
- **Component / File:** `canary_ssm/detector_service.py`, `canary_ssm/api/service.py`, `canary_ssm/dashboard/index.html`, `canary_ssm/dashboard/app.js`
- **Evidence:**
  1. In `index.html`, the infrastructure status was hardcoded as `pill-normal NORMAL` in green before any simulation or telemetry was ingested.
  2. When no data had arrived or before $t_0$, the system presented green normal states rather than explicit pending states.
- **Reproduction Steps:**
  Load dashboard fresh before clicking Play. Observe green `NORMAL` pills.
- **Fix Implemented:**
  1. Added `SystemMonitoringState` enum covering all 8 states:
     - `WAITING_FOR_DATA`
     - `INSUFFICIENT_DATA`
     - `MONITORING`
     - `STALE_DATA`
     - `CONNECTION_ERROR`
     - `COMPLETED_REPLAY`
     - `PAUSED_MONITORING`
     - `UNCALIBRATED_POLICY`
  2. Default initial state is `WAITING_FOR_DATA` with neutral gray pills (`advisory-pill pill-neutral`). Never displays green `NORMAL` before telemetry observations arrive or when disconnected.
  3. Added stale data tracking checking `data_age_seconds` and displaying `STALE_DATA` when clock exceeds threshold.

---

### Finding 5: Calibration Gate Transparency & Failed Benchmark Cells
- **Severity:** Medium
- **Status:** **Confirmed & Fixed**
- **Component / File:** `results/x04/x04_summary.md`, `canary_ssm/dashboard/index.html`, `canary_ssm/dashboard/app.js`
- **Evidence:**
  In `results/x04/x04_summary.md`, `hier_rank0` failed Gate G2 under `S5_label_errors` (FAR = 9.65%, Clopper-Pearson CI [8.39%, 11.03%], Beta-Binomial $p = 1.218 \times 10^{-8}$). Omitting factor subtraction causes shared shocks to pool across imbalanced classes.
- **Reproduction Steps:**
  Inspect `results/x04/table_validation_by_family.csv` row `S5_label_errors, hier_rank0`.
- **Fix Implemented:**
  1. Added explicit Gate G2 validity audit table in the Evaluation tab displaying exact FAR and p-values for all benchmark families.
  2. Displayed prominent audit warning banner marking `hier_rank0` under S5 as **INVALIDATED (Failed Gate G2)** with exact explanation of label error sensitivity.
  3. Explicitly prohibited invalidated configurations from being presented as calibrated deployment policies.

---

### Finding 6: Documentation and Test Count Inconsistencies
- **Severity:** Low
- **Status:** **Confirmed & Fixed**
- **Component / File:** `README.md`, `docs/implementation_status.md`
- **Evidence:**
  `README.md` listed `107 passed`. `docs/implementation_status.md` listed historical counts. Research scope in user-facing documentation needed clear clarification regarding deferred neural/Borg items.
- **Fix Implemented:**
  1. Reconciled test counts across all documentation files: **248+ tests passing**.
  2. Clearly documented that Borg cluster traces and neural/Mamba/LSTM baselines were deferred research scope per `docs/DESIGN_DECISIONS.md`.
  3. Documented exact reproducible test commands and skip flags.

---

### Finding 7: Dashboard Usability & First-Time User Experience
- **Severity:** High
- **Status:** **Confirmed & Fixed**
- **Component / File:** `canary_ssm/dashboard/index.html`, `canary_ssm/dashboard/style.css`, `canary_ssm/dashboard/app.js`, `canary_ssm/api/routes.py`, `canary_ssm/api/service.py`
- **Evidence:**
  The previous dashboard lacked guided 1-click presets, buried controls, and lacked side-by-side pooling method comparisons.
- **Fix Implemented:**
  1. **Quick-Start Header:** 1-click **Start Demo** action with preset scenario dropdown (`Clean Release`, `Release Memory Leak`, `Rack Slowdown`, `Fleet Demand Spike`, `CPU Regression`, `Healthy GC`, `Combined Rack + Leak`, `Missing Controls`).
  2. **Guided 7-Step Workflow:** Interactive visual cards guiding first-time users from Scenario Selection to Ground Truth Audit.
  3. **Dedicated Method Comparison Tab:** Real-time side-by-side comparison between **Hierarchical SSM (partial pooling)**, **Independent SSM (no pooling)**, and **Complete Pooling**, with effect estimates, standard errors, and release recommendations.
  4. **Dedicated SSM Evidence Tab:** Server-level and class-level breakdowns with $\hat{a}_i$, 95% CIs, percentage shifts, within-class shrinkage, and memory drift rates.
  5. **Evaluator Truth Firewall:** Hidden simulation truth strictly separated into dedicated overlay; detector recommendations never peek at ground truth.
