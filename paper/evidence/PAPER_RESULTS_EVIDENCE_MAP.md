# Paper Results Evidence Registry and Claim Map

- **Document Version**: 1.0
- **Audit Date**: 2026-11-15
- **Branch**: `external-validation-v1`
- **Specification Source**: Section 18.3 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Registry Schema and Mapping Principles

Every quantitative claim, numerical table cell, and plotted figure in the Canary SSM V3 research package is mapped directly to machine-readable source artifacts.

```
+---------------------------------------------------------------------------------------------------------+
|                                  CLAIM-TO-EVIDENCE TRACEABILITY SCHEMA                                  |
|                                                                                                         |
|   Paper Text / Claim ----> Table / Figure ID ----> CSV File Path ----> Filter Condition ----> Exact Col |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Evidence Mapping Matrix

| Claim / Metric ID | Description | Source File Path | Filter / Row | Column Name | Verified Value |
|---|---|---|---|---|---|
| **EVD-01** | Scalar Kalman Prior Mean ($t=1$) | `docs/validation/KALMAN_REFERENCE_TEST_REPORT.md` | $t=1$ | `prior_mean` | $0.0000$ |
| **EVD-02** | Scalar Kalman Post Mean ($t=1$) | `docs/validation/KALMAN_REFERENCE_TEST_REPORT.md` | $t=1$ | `post_mean` | $0.6875$ |
| **EVD-03** | Scalar Kalman Post Var ($t=1$) | `docs/validation/KALMAN_REFERENCE_TEST_REPORT.md` | $t=1$ | `post_var` | $0.34375$ |
| **EVD-04** | Scalar Kalman Post Mean ($t=2$) | `docs/validation/KALMAN_REFERENCE_TEST_REPORT.md` | $t=2$ | `post_mean` | $126/151 \approx 0.8344$ |
| **EVD-05** | Scalar Kalman Post Var ($t=2$) | `docs/validation/KALMAN_REFERENCE_TEST_REPORT.md` | $t=2$ | `post_var` | $71/302 \approx 0.2351$ |
| **EVD-06** | Baseline Log-Latency ($\mu$) Bias | `external_validation_v1/results/diagnostics/parameter_recovery_summary.csv` | `param == 'mu'` | `bias` | $+0.000137$ |
| **EVD-07** | Baseline Log-Latency ($\mu$) RMSE | `external_validation_v1/results/diagnostics/parameter_recovery_summary.csv` | `param == 'mu'` | `rmse` | $0.015903$ |
| **EVD-08** | Workload Slope ($\beta$) Bias | `external_validation_v1/results/diagnostics/parameter_recovery_summary.csv` | `param == 'beta'` | `bias` | $+0.002023$ |
| **EVD-09** | Workload Slope ($\beta$) RMSE | `external_validation_v1/results/diagnostics/parameter_recovery_summary.csv` | `param == 'beta'` | `rmse` | $0.073695$ |
| **EVD-10** | AR(1) Noise Persistence ($\phi_e$) Bias | `external_validation_v1/results/diagnostics/parameter_recovery_summary.csv` | `param == 'phi_e'` | `bias` | $+0.031247$ |
| **EVD-11** | AR(1) Noise Persistence ($\phi_e$) RMSE | `external_validation_v1/results/diagnostics/parameter_recovery_summary.csv` | `param == 'phi_e'` | `rmse` | $0.072287$ |
| **EVD-12** | Empirical 95% Posterior Coverage | `external_validation_v1/results/diagnostics/posterior_coverage.csv` | `nominal_level == 0.95` | `empirical_coverage` | $74.96\%$ |
| **EVD-13** | Innovation Workload Correlation | `external_validation_v1/results/diagnostics/residual_diagnostics.csv` | Row 0 | `mean_corr_workload` | $-0.022787$ |
| **EVD-14** | Innovation Lag-1 Autocorrelation | `external_validation_v1/results/diagnostics/residual_diagnostics.csv` | Row 0 | `autocorr_lag_1` | $+0.669078$ |
| **EVD-15** | Innovation Lag-4 Autocorrelation | `external_validation_v1/results/diagnostics/residual_diagnostics.csv` | Row 0 | `autocorr_lag_4` | $+0.033501$ |
| **EVD-16** | Baseline Prior SD ($1.0\times$) 95% Coverage | `external_validation_v1/results/diagnostics/prior_sensitivity.csv` | `prior_scale == 1.0` | `coverage_95` | $99.88\%$ |
| **EVD-17** | Baseline Prior SD ($1.0\times$) Width | `external_validation_v1/results/diagnostics/prior_sensitivity.csv` | `prior_scale == 1.0` | `mean_interval_width` | $0.077367$ |
| **EVD-18** | Narrow Prior ($0.25\times$) Coverage | `external_validation_v1/results/diagnostics/prior_sensitivity.csv` | `prior_scale == 0.25` | `coverage_95` | $52.44\%$ |
| **EVD-19** | Calibrated Threshold: Hierarchical SSM | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `hier_ssm` | - | $-0.030264$ |
| **EVD-20** | Calibrated Threshold: Independent SSM | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `indep_ssm` | - | $-0.047395$ |
| **EVD-21** | Calibrated Threshold: No-Inertia SSM | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `no_inertia_ssm` | - | $-3.197556$ |
| **EVD-22** | Calibrated Threshold: Kayenta Judge | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `kayenta_judge` | - | $+5.940092$ |
| **EVD-23** | Calibrated Threshold: Argo Policy (AR-3) | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `argo_policy` | - | $+16.333333$ |
| **EVD-24** | Calibrated Threshold: Flagger Policy | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `flagger_policy` | - | $+9.800000$ |
| **EVD-25** | Calibrated Threshold: SLO Threshold | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `slo_threshold` | - | $+1.722136$ |
| **EVD-26** | Calibrated Threshold: Adjusted CUSUM | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `adj_cusum` | - | $+65.665074$ |
| **EVD-27** | Calibrated Threshold: GLR Window | `external_validation_v1/artifacts/calibrated_thresholds.json` | Key: `glr_window` | - | $+49.786213$ |
