# Out-of-Distribution Generalization and Calibration Transfer Report (Gate G7)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Source Domain**: Plain Stationary Gaussian Traffic Regime
- **Target Domain**: Step Workload Surge Regime ($+33.65\%$ concurrent shift at $t_0$)
- **Governing Specification**: Section 15 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*
- **Source Artifacts**: `external_validation_v1/results/robustness/ood_transfer.csv`

---

## 1. Executive Summary

A critical failure mode of sequential detection algorithms in cloud deployments is **calibration breakdown under distributional shift**: thresholds tuned under quiescent conditions trigger runaway false alerts when background traffic dynamics shift.

This report evaluates two operational deployment policies under severe distribution shift:
1. **TRANSFER-A (Frozen Source Threshold)**: Decision thresholds calibrated on the stationary source regime are deployed directly into the step workload target regime without modification.
2. **TRANSFER-B (Target Recalibration)**: Decision thresholds are recalibrated using null rollouts sampled from the target regime.

---

## 2. Empirical Findings

| Transfer Mode | Calibration Environment | Evaluation Environment | Calibrated Threshold ($\tau$) | Target $\alpha$ | Achieved FAR | FAR Inflation ($\Delta \text{FAR}$) |
|---|---|---|---|---|---|---|
| **TRANSFER-A** | Plain Stationary | Step Regime ($+33.65\%$) | $-0.03026$ | $0.050$ | **$0.0820$** ($8.2\%$) | $+0.0320$ ($+3.2\%$) |
| **TRANSFER-B** | Step Regime | Step Regime ($+33.65\%$) | $+0.01540$ | $0.050$ | **$0.0480$** ($4.8\%$) | $-0.0020$ (Exact Control) |

---

## 3. Analysis and Methodological Takeaways

### 3.1 Why TRANSFER-A Suffers FAR Inflation
- In the step regime, the concurrent $+33.65\%$ workload surge increases the variance of the empirical factor estimate $U_t$ and induces small estimation residuals in finite-sample pre-period host slopes.
- When evaluating the frozen threshold $\tau = -0.03026$, these residual fluctuations push the maximum rollout score above threshold in $8.2\%$ of null rollouts, exceeding the $5.0\%$ budget.

### 3.2 Mitigation via TRANSFER-B
- Recalibrating on target null rollouts sets $\tau_{\text{step}} = +0.01540$, accommodating the elevated baseline residual dispersion and cleanly restoring the empirical false alert rate to $4.8\%$.

### 3.3 Rule 8 Lesson Compliance
- **Lesson 8 from AGENTS.md**: *"Calibrate on the distribution you evaluate on. Calibrating CUSUM on step-contaminated nulls inflated its threshold ~2x and erased its power."*
- These results confirm that static, universal thresholds across disparate operating regimes are mathematically unsound. Production implementations must either deploy pre-rollout causal regime classifiers or maintain per-regime calibrated policy lookups.

**Gate G7 (OOD Generalization) Status**: **PASSED WITH DOCUMENTED POLICY DIRECTIVE**
