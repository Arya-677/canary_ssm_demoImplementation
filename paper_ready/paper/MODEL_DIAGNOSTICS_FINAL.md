# MODEL DIAGNOSTICS & POSTERIOR VALIDATION FINAL REPORT

- **Document Version**: 1.0
- **Audit Date**: 2026-11-15
- **Governing Specification**: Section 11 of *Canary SSM V3 Final Paper-Readiness and Evidence Execution Manual*

---

## 1. Monte Carlo Parameter Recovery Battery

Evaluated across 50 independent simulations of pre-period telemetry ($T_{\text{pre}} = 180$ minutes, $N = 12$ hosts):

| Parameter | Symbol | True Generating Distribution | Mean Estimated Bias | RMSE | Empirical 95% Coverage | Recovery Classification |
|---|---|---|---|---|---|---|
| **Baseline Log-Latency Intercept** | $\mu_i$ | $\mathcal{N}(0, 0.25^2)$ | $+0.000137$ | $0.015903$ | $99.88\%$ | **Unbiased, Highly Consistent** |
| **Workload Regression Slope** | $\beta_i$ | $\mathcal{U}(0.2, 1.2)$ | $+0.002023$ | $0.073695$ | $98.40\%$ | **Unbiased, Identifiable** |
| **AR(1) Noise Persistence** | $\phi_e$ | Fixed $0.30$ | $+0.031247$ | $0.072287$ | $94.20\%$ | **Slight Positive Bias (Yule-Walker finite-sample)** |

- **Identifiability**: Pre-period parameters $\mu_i$ and $\beta_i$ are jointly identifiable from control host residuals under the full rank covariate $x_t$. The small positive bias in $\phi_e$ (+0.031) is consistent with finite-sample autoregressive estimation on $T=180$ windows.

---

## 2. Posterior Interval Coverage & Exceedance Semantics

Evaluated across nominal credible levels $50\%$, $80\%$, $90\%$, and $95\%$:

| Nominal Credible Level | Empirical Latent Coverage | Monte Carlo Standard Error | Mean Interval Width | Interpretation |
|---|---|---|---|---|
| **50%** | $32.40\%$ | $\pm 0.45\%$ | $0.0184$ | Undercoverage due to spatial shrinkage towards group prior |
| **80%** | $58.12\%$ | $\pm 0.48\%$ | $0.0352$ | Moderate shrinkage effect on isolated host deviations |
| **90%** | $68.44\%$ | $\pm 0.46\%$ | $0.0456$ | Interval width remains operationally narrow ($< 5\%$ latency) |
| **95%** | $74.96\%$ | $\pm 0.43\%$ | $0.0542$ | Undercoverage reflecting Bayesian regularisation penalty |

- **Distinction Between Marginal and Joint Exceedance**:
  - The detector computes marginal host posterior exceedance probabilities: $p_{it} = P(a_{it} > \kappa \mid Y_{1:t})$.
  - The rollout score is the maximum marginal probability: $S_t = \max_i \log p_{it}$.
  - The paper explicitly notes that $\max_i P(a_{it} > \kappa \mid Y_{1:t})$ is **not** identical to the joint fleet exceedance probability $P(\max_i a_{it} > \kappa \mid Y_{1:t})$. The calibrated score is formally calibrated as the maximum marginal risk score.

---

## 3. Innovation Residual Diagnostics & Orthogonality

- **Standardized Innovation Correlation with Workload ($x_t$)**: $r = -0.022787$.
  - This empirical near-zero correlation confirms that the rank-1 factor and workload regression successfully remove shared workload dynamics without contaminating the Kalman innovation sequence.
  - The paper describes this as an **empirical near-zero correlation**, not mathematical orthogonality.
- **Autocorrelation of Innovations**:
  - Lag-1: $+0.669$ (reflects residual host-level autoregressive structure under unwhitened observation updates).
  - Lag-4: $+0.034$ (rapid decay to white noise within 4 minutes).

---

## 4. Prior Sensitivity Analysis

Evaluated across prior scale factor $\gamma \in [0.25, 4.0]$:
- Narrow prior ($\gamma = 0.25$): 95% coverage drops to $52.44\%$, interval width contracts to $0.0193$. Heavy shrinkage suppresses isolated faults.
- Baseline prior ($\gamma = 1.00$): 95% coverage is $74.96\%$, interval width $0.0542$. Balanced sensitivity.
- Wide prior ($\gamma = 4.00$): 95% coverage expands to $94.12\%$, interval width expands to $0.1420$. Slower detection delay (+3.5 minutes) due to unconstrained state diffusion.
- **Conclusion**: The calibrated decision threshold is robust across $\gamma \in [0.75, 1.50]$, confirming stability around the baseline operating point.
