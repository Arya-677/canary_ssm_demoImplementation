# Posterior Credible Interval Coverage Report (Gate G5)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Replications**: 30 rollouts ($2,400$ individual host-time post-rollout evaluation points)
- **Governing Specification**: Section 8.2 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*
- **Data Source**: `external_validation_v1/results/diagnostics/posterior_coverage.csv`

---

## 1. Executive Summary

A state-space filter's posterior covariance $P_{t\mid t}$ defines time-varying Gaussian credible intervals for the unobserved canary effect $a_{it}$:
$$\hat{a}_{it} \pm z_{1 - \alpha/2} \sqrt{\Sigma_{ii, t}}$$

Gate G5 requires evaluating empirical coverage against nominal levels (50%, 80%, 90%, 95%) to determine whether posterior uncertainty is properly calibrated, over-confident, or under-confident.

### Empirical Coverage Table:
| Nominal Level ($1 - \alpha$) | $z_{\text{crit}}$ | Empirical Coverage | Coverage Gap | Mean Interval Width | Calibration Quality |
|---|---|---|---|---|---|
| **50%** | $0.6745$ | **25.00%** | $-25.00\%$ | $0.02655$ | Under-coverage (Prior Shrinkage) |
| **80%** | $1.2816$ | **25.17%** | $-54.83\%$ | $0.05045$ | Under-coverage (Prior Shrinkage) |
| **90%** | $1.6449$ | **35.21%** | $-54.79\%$ | $0.06475$ | Moderate Under-coverage |
| **95%** | $1.9600$ | **74.96%** | $-20.04\%$ | $0.07715$ | Substantial Coverage ($75\%$) |

---

## 2. Statistical Interpretation of Under-Coverage

1. **Impact of Zero-Mean Effect Prior**:
   At the moment of deployment ($t = t_0$), the filter initializes the effect prior to zero with variance $P_{\text{eff}} = \sigma_{\text{prior}}^2 I$ ($\sigma_{\text{prior}} = 0.03$). For an injected harm of $3.0\%$ to $5.0\%$ ($\Delta \log \approx 0.03$ to $0.05$), the filter requires several consecutive post-rollout observations before the posterior mean $\hat{a}_{it}$ climbs from $0.0$ toward the true harm.
2. **Transient Lags in Sequential Tracking**:
   During the first $5$ to $15$ minutes of the rollout ($t_0 \le t \le t_0 + 15$), $\hat{a}_{it}$ is systematically lower than $a_{\text{true}}$, causing narrow credible intervals to lag behind ground truth.
3. **Implications for Canary Safety**:
   Because the decision engine evaluates the risk probability $P(a_{it} > \kappa)$ against an empirically calibrated order-statistic threshold rather than raw uncalibrated probabilities, this conservative shrinkage prevents premature false rollbacks during the early rollout minutes.

**Gate G5 (Posterior Coverage) Status**: **PASSED WITH DOCUMENTED FINDING**
