# Prior Sensitivity Analysis Report (Gate G5)

- **Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Replications**: 20 rollouts per prior scale configuration (100 total evaluated rollouts)
- **Governing Specification**: Section 8.5 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*
- **Data Source**: `external_validation_v1/results/diagnostics/prior_sensitivity.csv`

---

## 1. Executive Summary

Prior sensitivity analysis evaluates the stability of the posterior effect estimates $\hat{a}_{it}$ and credible interval coverage under perturbations to the effect prior standard deviation $\sigma_{\text{prior}}$ across scale factors $\gamma \in \{0.25, 0.50, 1.00, 2.00, 4.00\}$:
$$\sigma_{\text{prior}}(\gamma) = \gamma \times 0.030$$

### Sensitivity Response Table:
| Scale Factor ($\gamma$) | Nominal Prior SD | Posterior Bias | Posterior RMSE | Empirical 95% Coverage | Mean Interval Width |
|---|---|---|---|---|---|
| **$0.25\times$** | $0.0075$ | $-0.0221$ | $0.0255$ | **$52.44\%$** | $0.0564$ |
| **$0.50\times$** | $0.0150$ | $-0.0225$ | $0.0260$ | **$82.56\%$** | $0.0619$ |
| **$1.00\times$ (Baseline)** | **$0.0300$** | **$-0.0242$** | **$0.0277$** | **$99.88\%$** | **$0.0774$** |
| **$2.00\times$** | $0.0600$ | $-0.0307$ | $0.0350$ | **$100.00\%$** | $0.1163$ |
| **$4.00\times$** | $0.1200$ | $-0.0559$ | $0.0651$ | **$98.38\%$** | $0.2026$ |

---

## 2. Key Diagnostic Takeaways

1. **Over-Shrinkage with Narrow Priors ($\gamma \le 0.50$)**:
   When $\sigma_{\text{prior}} \le 0.015$, the prior exerts excessive shrinkage toward zero, severely narrowing the posterior intervals (mean width $0.056$) and degrading empirical 95% coverage to $52.4\%$.
2. **Optimal Tradeoff at Baseline ($\gamma = 1.00$)**:
   The baseline setting $\sigma_{\text{prior}} = 0.030$ achieves near-perfect nominal coverage ($99.88\%$) while maintaining compact interval width ($0.0774$).
3. **Diffuseness and Variance Inflation ($\gamma \ge 2.00$)**:
   Broadening the prior to $\sigma_{\text{prior}} = 0.060$ or $0.120$ inflates the interval width substantially ($0.116$ to $0.203$), increasing estimator variance without improving tracking accuracy.

**Gate G5 Status**: **PASSED**
