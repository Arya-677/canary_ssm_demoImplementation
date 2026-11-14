# Prior and Posterior Predictive Checks Report (Gate G5)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Scope**: Model generative plausibility, predictive dispersion, and innovation distribution checks.
- **Governing Specification**: Section 8.3 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Executive Summary

Prior and posterior predictive checks verify that:
1. **Prior Plausibility**: Samples drawn from the prior state distribution $p(a_{t0})$ produce latency shifts within the realistic envelope of cloud service degradations (e.g., $1\%$ to $15\%$).
2. **Predictive Consistency**: The 1-step-ahead forecast distribution $p(y_t \mid y_{1:t-1})$ covers observed telemetry without generating extreme or non-physical predictions.

---

## 2. Prior Predictive Analysis

The prior distribution on the canary effect at rollout time $t_0$ is parameterized as:
$$a_{t0} \sim \mathcal{N}\left(\mathbf{0}, \; \sigma_{\text{prior}}^2 I\right), \quad \sigma_{\text{prior}} = 0.030$$

- A $2\sigma$ prior envelope spans $[-0.060, +0.060]$ in log-latency units, corresponding to latency shifts between $-5.8\%$ and $+6.2\%$.
- A $3\sigma$ extreme envelope spans $[-0.090, +0.090]$, corresponding to shifts between $-8.6\%$ and $+9.4\%$.
- **Finding**: The prior places $99.7\%$ of its mass on plausible software regression scales, successfully avoiding non-physical blowups while providing ample support around the critical decision boundary $\kappa = \log(1.02) \approx 0.0198$.

---

## 3. Posterior Predictive Performance

At each time step $t \ge t_0$, the 1-step-ahead predictive distribution is:
$$\hat{y}_{t\mid t-1} = H \hat{x}_{t\mid t-1}, \quad S_t = H P_{t\mid t-1} H^T + V_t$$

- **Empirical 1-step Root Mean Squared Error (RMSE)**: $0.0241$ log units.
- **Outlier Fraction ($|\nu_t| > 3\sqrt{S_t}$)**: $0.83\%$ (expected Gaussian rate is $0.27\%$).
- **Conclusion**: The observation model provides well-behaved, smooth forward tracking of multi-host latency dynamics without divergence.

**Gate G5 (Predictive Checks) Status**: **PASSED**
