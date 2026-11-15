# PAPER RESULTS EVIDENCE MAP & TRACEABILITY REGISTRY

- **Document Version**: 1.0
- **Audit Date**: 2026-11-15
- **Branch**: `v3` / `research-release-v3` / `external-validation-v1`
- **Governing Specification**: Section 18.3 of *Canary SSM V3 Final Paper-Readiness and Evidence Execution Manual*

---

## 1. Traceability Architecture

Every numerical value, statistical confidence interval, table cell, and figure in the Canary SSM V3 research paper is mapped directly to a machine-readable source artifact in the repository.

```
+----------------------------------------------------------------------------------------------------------+
|                                  CLAIM-TO-EVIDENCE TRACEABILITY SCHEMA                                   |
|                                                                                                          |
|  Paper Statement / Number -> Table / Figure ID -> Raw CSV File Path -> Row Filter -> Exact Column Name  |
+----------------------------------------------------------------------------------------------------------+
```

---

## 2. Claim-to-Evidence Registry Table

| Claim ID | Paper Claim / Table Cell | Source File | Row Filter / Key | Column Name | Verified Value | Status |
|---|---|---|---|---|---|---|
| **EVD-01** | Scalar Kalman Prior Mean ($t=1$) | `paper_ready/audits/KALMAN_REFERENCE_TEST_REPORT.md` | $t=1$ | `prior_mean` | $0.0000$ | VERIFIED |
| **EVD-02** | Scalar Kalman Post Mean ($t=1$) | `paper_ready/audits/KALMAN_REFERENCE_TEST_REPORT.md` | $t=1$ | `post_mean` | $0.6875$ | VERIFIED |
| **EVD-03** | Scalar Kalman Post Var ($t=1$) | `paper_ready/audits/KALMAN_REFERENCE_TEST_REPORT.md` | $t=1$ | `post_var` | $0.34375$ | VERIFIED |
| **EVD-04** | Scalar Kalman Post Mean ($t=2$) | `paper_ready/audits/KALMAN_REFERENCE_TEST_REPORT.md` | $t=2$ | `post_mean` | $126/151 \approx 0.8344$ | VERIFIED |
| **EVD-05** | Scalar Kalman Post Var ($t=2$) | `paper_ready/audits/KALMAN_REFERENCE_TEST_REPORT.md` | $t=2$ | `post_var` | $71/302 \approx 0.2351$ | VERIFIED |
| **EVD-06** | Baseline Log-Latency ($\mu$) Bias | `paper_ready/data/diagnostics/parameter_recovery_summary.csv` | `param == 'mu'` | `bias` | $+0.000137$ | VERIFIED |
| **EVD-07** | Baseline Log-Latency ($\mu$) RMSE | `paper_ready/data/diagnostics/parameter_recovery_summary.csv` | `param == 'mu'` | `rmse` | $0.015903$ | VERIFIED |
| **EVD-08** | Workload Slope ($\beta$) Bias | `paper_ready/data/diagnostics/parameter_recovery_summary.csv` | `param == 'beta'` | `bias` | $+0.002023$ | VERIFIED |
| **EVD-09** | Workload Slope ($\beta$) RMSE | `paper_ready/data/diagnostics/parameter_recovery_summary.csv` | `param == 'beta'` | `rmse` | $0.073695$ | VERIFIED |
| **EVD-10** | AR(1) Noise Persistence ($\phi_e$) Bias | `paper_ready/data/diagnostics/parameter_recovery_summary.csv` | `param == 'phi_e'` | `bias` | $+0.031247$ | VERIFIED |
| **EVD-11** | AR(1) Noise Persistence ($\phi_e$) RMSE | `paper_ready/data/diagnostics/parameter_recovery_summary.csv` | `param == 'phi_e'` | `rmse` | $0.072287$ | VERIFIED |
| **EVD-12** | Empirical 95% Posterior Coverage | `paper_ready/data/diagnostics/posterior_coverage.csv` | `nominal_level == 0.95` | `empirical_coverage` | $74.96\%$ | VERIFIED |
| **EVD-13** | Innovation Workload Correlation | `paper_ready/data/diagnostics/residual_diagnostics.csv` | Row 0 | `mean_corr_workload` | $-0.022787$ | VERIFIED |
| **EVD-14** | Calibrated Threshold: `hier_ssm` | `paper_ready/data/calibration/calibrated_thresholds.json` | Key: `hier_ssm` | - | $-0.030264$ | VERIFIED |
| **EVD-15** | Calibrated Threshold: `indep_ssm` | `paper_ready/data/calibration/calibrated_thresholds.json` | Key: `indep_ssm` | - | $-0.047395$ | VERIFIED |
| **EVD-16** | Calibrated Threshold: `no_inertia_ssm` | `paper_ready/data/calibration/calibrated_thresholds.json` | Key: `no_inertia_ssm` | - | $-3.197556$ | VERIFIED |
| **EVD-17** | Gate G2 Validity: `hier_ssm` FAR | `paper_ready/tables/table_T5_calibration_gate_g2.csv` | `method == 'hier_ssm'` | `achieved_far` | $0.048$ ($24/500$) | VERIFIED |
| **EVD-18** | Gate G2 Validity: `hier_ssm` p-val | `paper_ready/tables/table_T5_calibration_gate_g2.csv` | `method == 'hier_ssm'` | `binom_pval` | $0.6101 \ge 0.01$ | VERIFIED |
| **EVD-19** | Master Benchmark: `hier_ssm` Power | `paper_ready/data/DETECTOR_BENCHMARK_PANEL.csv` | `method == 'hier_ssm'` | `power` | $88.14\%$ ($617/700$) | VERIFIED |
| **EVD-20** | Master Benchmark: `hier_ssm` Mean Delay | `paper_ready/data/DETECTOR_BENCHMARK_PANEL.csv` | `method == 'hier_ssm'` | `mean_cond_delay` | $7.485$ min | VERIFIED |
| **EVD-21** | Master Benchmark: `hier_ssm` Capped H45 | `paper_ready/data/DETECTOR_BENCHMARK_PANEL.csv` | `method == 'hier_ssm'` | `mean_capped_tts_h45` | $11.933$ min | VERIFIED |
| **EVD-22** | Master Benchmark: `hier_ssm` Capped H120 | `paper_ready/data/DETECTOR_BENCHMARK_PANEL.csv` | `method == 'hier_ssm'` | `mean_capped_tts_h120` | $20.825$ min | VERIFIED |
| **EVD-23** | Paired Delta vs Indep (Mutually Detected)| `paper_ready/data/DETECTOR_BENCHMARK_PANEL.csv` | `method == 'indep_ssm'` | `paired_cond_delta_vs_hier` | $+0.408$ min ($p=.032$) | VERIFIED |
| **EVD-24** | Paired Delta vs Indep (Capped H120) | `paper_ready/data/DETECTOR_BENCHMARK_PANEL.csv` | `method == 'indep_ssm'` | `paired_capped120_delta_vs_hier` | $+0.198$ min | VERIFIED |
| **EVD-25** | Single-Canary Shrinkage Penalty | `paper_ready/tables/table_T6_core_pooling_comparison.csv` | `Scenario_Class == 'Single-Host Persistent (S5)'` | `Hier_vs_Indep_Delta` | $+9.4$ min ($p<0.001$) | VERIFIED |
| **EVD-26** | Workload Step Surge False Alert Rate | `paper_ready/tables/table_T9_robustness_matrix.csv` | `Stress_Condition == 'Workload Step Surge (50% Jump)'` | `hier_ssm_far` | $47.5\%$ | VERIFIED |
| **EVD-27** | Runtime Scaling Latency ($N=500$ hosts) | `paper_ready/tables/table_T10_runtime_scaling.csv` | `n_hosts == 500` | `update_p95_ms` | $2.34$ ms | VERIFIED |
