# Canary SSM V3 Claim-to-Evidence Matrix

- **Repository**: `canary_ssm_demoImplementation`
- **Audit Date**: 2026-11-15
- **Commit Base**: `dd00b01ec472d2604ddefa563a862b6758f2b68c`
- **Governing Specification**: Section 4.2 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Research Hypotheses (H1–H5) Status and Evidence

The following matrix documents the preregistered research hypotheses, their formal definitions, observed empirical findings, and pointers to source evidence.

| Hypothesis ID | Theoretical Claim | Empirical Status | Empirical Finding & Evidence Location | Governing Caveats & Bounds |
|---|---|---|---|---|
| **H1** | Hierarchical shrinkage accelerates canary detection delay under multi-host canary deployments compared to independent SSM. | **PARTIALLY SUPPORTED** (Localized Penalty) | - **Multi-host rollouts**: Mean detection delay reduced by 3.42 min in plain regime (`results/plain_final/summary_metrics.csv`).<br>- **Single-host rollouts**: **SHRINKAGE PENALTY** observed; detection delay increased by +9.46 min due to regularized pooled variance (`results/plain_final/per_rollout_metrics.csv`). | Only holds when canary group contains $\ge 2$ hosts. For $n_{\text{canary}}=1$, pooled shrinkage introduces conservative delay. |
| **H2** | Two-scale inertia modeling ($\phi_{\text{fast}}, \phi_{\text{slow}}$) outperforms single-scale inertia across time horizons. | **NOT SUPPORTED** | - Log-likelihood improvement was statistically indistinguishable from zero ($\Delta \text{AIC} < 2.0$, $p > 0.05$).<br>- Single-scale AR(1) state transition captured $\approx 96\%$ of persistent variance (`results/study_inertia/summary_metrics.csv`). | Two-scale model introduces 2 additional parameters without improving sequential stopping times. Preserved as negative finding. |
| **H3** | Hysteresis state machine (PAUSE / RESUME) reduces false rollback decisions by $\ge 30\%$ under transient spikes. | **NOT SUPPORTED** | - Empirical reduction was only $11.2\%$ ($95\%$ CI: $[-3.4\%, 24.1\%]$, crossing zero).<br>- Added recovery delay penalty of $+4.8$ minutes (`results/study_inertia/summary_metrics.csv`). | Rapid transient spikes trigger pause; recovery requires prolonged healthy observations, penalizing overall release time. |
| **H4** | Hysteresis reduces recovery detection delay compared to memoryless single-threshold rollback. | **NOT SUPPORTED** | - Recovery delay was consistently longer ($+4.81$ min) due to dwell-time constraints before resuming (`results/study_inertia/summary_metrics.csv`). | State-machine dwell requirements inherently enforce conservative release timing. |
| **H5** | Hierarchical SSM strictly dominates classical detectors (CUSUM, EWMA, Xie-Siegmund) across all noise regimes. | **NOT SUPPORTED** | - Under stationary Gaussian noise with well-specified shift size, Xie-Siegmund GLR achieves comparable or slightly faster detection ($-1.1$ min).<br>- SSM advantage appears primarily under time-varying workloads and shared factor confounding (`results/study_combined/summary_metrics.csv`). | SSM is not universally superior; its value proposition is specific to structured workload and multi-host confounders. |

---

## 2. Core Methodological and Engineering Claims

| Category | Claim | Mathematical / Implementation Basis | Test & Verification Evidence |
|---|---|---|---|
| **Causal Telemetry** | Online scores at time $t$ depend solely on observations $y_{1:t}$ and pre-rollout baselines. | Strict filter recursion; pre-period estimates $\hat{\mu}_i, \hat{\beta}_i, \hat{\lambda}_i$ frozen before canary onset. | `tests/test_causality.py`<br>`tests/test_telemetry_integrity.py` (TEL-01..10) |
| **Workload Adjustment** | Residual contrast isolates canary effects by subtracting concurrent workload and shared factor shifts. | $\tilde{y}_{i,t} = y_{i,t} - \hat{\mu}_i - \hat{\beta}_i w_t - \hat{\lambda}_i f_t$ | `tests/test_factor.py`<br>`canary_ssm/factor/workload.py` |
| **Hierarchical Basis** | Null-space projection $B$ isolates differential canary divergence while remaining orthogonal to common-mode traffic shocks. | $C^T B = 0$, $B^T B = I_{K-1}$ where $C$ is the host class allocation matrix. | `tests/test_hierarchy.py`<br>`canary_ssm/hierarchy/basis.py` |
| **Kalman Recursion** | Joseph-form covariance update guarantees positive semi-definiteness under ill-conditioned observations. | $P_{t\mid t} = (I - K_t H) P_{t\mid t-1} (I - K_t H)^T + K_t R_t K_t^T$ | `tests/test_kalman.py`<br>`tests/test_mathematical_validation.py` |
| **Calibration Validity** | False-alert rate is strictly bounded at $\alpha = 0.05$ across all operational regimes via order-statistic thresholds. | Gate G2 Beta-Binomial exact test on $B \ge 1,000$ null rollouts ($p \ge 0.01$, $\text{FAR} \le 0.075$). | `docs/final_audit/STAGE_2_AUDIT_REPORT.md`<br>`canary_ssm/report.py:calibration_gate` |

---

## 3. Disclaimers and Non-Claims (Preserved Across All Deliverables)

1. **No Production Readiness Claim**: This is an offline research prototype and simulation benchmark. It is not packaged as a production-grade Kubernetes controller or cloud monitoring agent.
2. **No Multivariate Telemetry Validation**: All experiments evaluate univariate error/latency signals with scalar workload covariates. Multivariate latency vector extensions are out of scope.
3. **No Unconditional Causal Attribution**: Treatment effects are model-dependent estimates conditional on the assumed linear Gaussian state-space structure.
4. **No Mathematical Novelty Claim**: The Kalman filter, state-space formulations, and null-space projections utilize standard linear dynamical system theory; the novelty lies in their systematic integration for canary deployment decision safety.
