# Negative Controls and Common-Mode Confounding Report (Gate G7)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Replications**: 40 rollouts per negative control configuration (200 total evaluated rollouts)
- **Governing Specification**: Section 10 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*
- **Source Artifacts**: `external_validation_v1/results/robustness/negative_controls.csv`

---

## 1. Executive Summary

In production distributed systems, canaries frequently experience concurrent performance degradation caused not by software defects, but by global environmental shocks (e.g., traffic surges, database locking, cloud network brownouts).

A statistically safe canary detector must satisfy **specificity under common-mode perturbations**: it must NOT alarm when degradation affects canaries and control hosts symmetrically.

Five rigorous negative controls (NC-01 through NC-05) were constructed to test robustness against confounding:

| Control ID | Mechanism | Confounding Nature | Target FAR | Safety Gate |
|---|---|---|---|---|
| **NC-01** | Global Traffic Surge | $+50\%$ sudden cluster workload step ($x_t \to x_t + 0.405$) | $\le 0.08$ | **PASSED** |
| **NC-02** | Database Slowdown | Synchronous $+20\text{ms}$ latency spike across all hosts | $\le 0.08$ | **PASSED** |
| **NC-03** | Permuted Canaries | Canary flags randomly reassigned to unexposed hosts | $\le 0.08$ | **PASSED** |
| **NC-04** | Upstream API Throttling| Uniform 50% host degradation spanning canary & control | $\le 0.08$ | **PASSED** |
| **NC-05** | Variance Doubling | Measurement noise SD doubled ($\sigma \to 2\sigma$) with zero shift | $\le 0.08$ | **PASSED** |

---

## 2. In-Depth Analysis of Negative Controls

### 2.1 Global Traffic Surge (NC-01)
- Under a sudden $+50\%$ traffic surge, unadjusted threshold comparators (e.g., raw latency SLOs) exhibit catastrophic false alert rates exceeding $80\%$, triggering unnecessary deployment rollbacks.
- Canary SSM V3 uses pre-period estimated workload slopes $\hat{\beta}_i$ and the concurrent covariate $x_t$ to subtract the workload response:
  $$\tilde{y}_{it} = y_{it} - \hat{\mu}_i - \hat{\beta}_i (x_t - \bar{x})$$
- The adjusted residuals remain centered at zero, achieving an empirical false alarm rate of $\le 5\%$.

### 2.2 Synchronous Latency Spikes (NC-02)
- Common-mode backend database stalls inject identical additive shifts across all containers.
- The rank-1 factor decomposition extracts the shared shock from control hosts:
  $$\hat{f}_t = \frac{1}{\sum_j \hat{\lambda}_j^2} \sum_{j \in \text{control}} \hat{\lambda}_j \tilde{y}_{jt}$$
  and subtracts $\hat{\lambda}_i \hat{f}_t$ from canary residuals.
- Furthermore, the spatial projection basis $B$ satisfies $C^T B = 0$, guaranteeing that any uniform additive shock across class members projects identically to zero in the deviation coordinates.

### 2.3 Permuted Canary Flags (NC-03)
- When canary labels are randomly swapped onto healthy baseline hosts, the detector operates on pure noise.
- The empirical false alert rate matches the calibrated nominal level $\alpha = 0.05$, confirming that no structural artifact in the filter induces false positives.

**Gate G7 (Negative Controls) Status**: **PASSED (ALL 5 CONTROLS WITHIN BUDGET)**
