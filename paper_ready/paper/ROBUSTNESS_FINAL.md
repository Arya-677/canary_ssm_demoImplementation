# ROBUSTNESS AND STRESS TESTING FINAL REPORT

- **Document Version**: 1.0
- **Audit Date**: 2026-11-15
- **Governing Specification**: Section 12 of *Canary SSM V3 Final Paper-Readiness and Evidence Execution Manual*

---

## 1. Stress Testing Matrix and Audited Boundaries

Robustness evaluations were executed across 8 stress scenarios to establish empirical operating boundaries:

| Stress Condition | Detector Evaluated | Observed FAR | Observed Power | Detection Delay | Material Boundary Finding |
|---|---|---|---|---|---|
| **50% Workload Step Surge** | `hier_ssm` | **47.5%** | 100.0% | 3.5 min | **MATERIAL FAILURE MODE**: Step shock leaks into residuals, triggering high false alerts. |
| | `adj_cusum` | **58.0%** | 100.0% | 17.5 min | Classical CUSUM also suffers severe false alert breakdown under abrupt step. |
| **Heavy Tails ($t_3$ errors)** | `hier_ssm` | **6.0%** | 99.67% | 4.8 min | Robust: Kalman variance updates absorb outlier innovations. |
| | `glr_window` | **85.7%** | 100.0% | 2.1 min | **Severe GLR breakdown**: Gaussian likelihood assumption fails under heavy tails. |
| | `adj_cusum` | **12.7%** | 98.4% | 14.2 min | Moderate FAR inflation. |
| **20% Missing Data (MCAR)** | `hier_ssm` | **5.2%** | 82.4% | 8.9 min | Sub-projection update preserves power without false alert inflation. |
| | `kayenta_judge` | **7.5%** | 58.2% | 22.4 min | Non-parametric test loses power due to minimum sample size requirement. |
| **Control Contamination (20%)** | `hier_ssm` | **5.8%** | 84.1% | 10.6 min | Factor estimation partially absorbs treatment signal (+3.1m delay penalty). |
| **Label Noise (30% error)** | `hier_ssm` | **5.4%** | 86.2% | 8.2 min | Degrades class pooling benefits to independent SSM levels. |
| **Negative Controls (NC-01 to 05)** | `hier_ssm` | **< 5.0%** | N/A (Null) | N/A | Non-alarming under zero true harm across all 5 checks. |
| **OOD Calibration Transfer** | `hier_ssm` | **5.6%** | 87.4% | 7.8 min | Stable transfer from stationary nulls to shifted distribution. |

---

## 2. In-Depth Analysis of Material Failure Modes

### 2.1 Workload Step Surge Failure Mode (47.5% FAR)
- When a 50% workload step surge occurs instantaneously at rollout start, the pre-period regression estimate $\hat{\beta}_i$ leaves residual transient errors that are not completely eliminated by the contemporaneous factor $\hat{f}_t$.
- This residual shock enters the Kalman filter as an apparent common-mode shift, causing the posterior probability $P(a_{it} > \kappa)$ to breach threshold $\tau$ on $47.5\%$ of un-degraded rollouts.
- **Paper Framing**: Foregrounded as a primary limitation in Section 11 and Table T9. Workload steps represent an open operational challenge requiring causal step-detection filters or longer pre-periods.

### 2.2 GLR Heavy-Tail Inflation (85.7% FAR)
- Windowed GLR detector assumes standard Gaussian innovations. Under Student-$t$ noise with 3 degrees of freedom, heavy-tailed innovations frequently trigger the GLR likelihood ratio test, inflating false alarm rates to $85.7\%$.
- In contrast, the Kalman filter's recursive state error covariance $P_{t|t}$ damps isolated extreme innovations, maintaining false alarm rate near nominal ($6.00\%$).
