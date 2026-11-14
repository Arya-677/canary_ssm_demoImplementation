# Results Evidence Map: Canary SSM V3
## Traceability Matrix from Manuscript Claims to Underlying Data Files

Every quantitative statement, confidence interval, and $p$-value presented in the research manuscript originates directly from saved experiment CSV records. This map provides complete line-by-line auditability.

---

### Quantitative Claim Traceability Matrix

| Manuscript Statement / Quantitative Metric | Primary Value | Stated Uncertainty / $p$-value | Source File | Exact Key / Row / Column Filter |
| :--- | :---: | :---: | :--- | :--- |
| **`hier_ssm` Mean Capped Time (Plain Test)** | 15.57 min | Miss: 5.11% | `results/plain_final/table_detection.csv` | `method == "hier_ssm"`, column `mean_capped_time` |
| **`indep_ssm` Mean Capped Time (Plain Test)** | 18.10 min | Miss: 5.84% | `results/plain_final/table_detection.csv` | `method == "indep_ssm"`, column `mean_capped_time` |
| **`hier_ssm` vs `indep_ssm` Paired Difference** | -2.53 min | 95% CI [-3.98, -0.99], $p = 0.0012$ | `results/plain_final/table_paired_differences.csv` | `A == "hier_ssm" & B == "indep_ssm"`, column `mean_capped_diff_A_minus_B` |
| **`glr_window` Mean Capped Time (Plain Test)** | 33.38 min | Miss: 12.30% | `results/plain_final/table_detection.csv` | `method == "glr_window"`, column `mean_capped_time` |
| **`adj_cusum` Mean Capped Time (Plain Test)** | 44.16 min | Miss: 15.50% | `results/plain_final/table_detection.csv` | `method == "adj_cusum"`, column `mean_capped_time` |
| **`hier_ssm` Null FAR (Plain Test)** | 3.80% | 95% CI [2.70%, 5.18%] | `results/plain_final/table_null_rates.csv` | `method == "hier_ssm"`, column `rate` (38 / 1000) |
| **`hier_ssm` Null FAR (Step Test)** | 4.10% | 95% CI [2.96%, 5.52%] | `results/step_final/table_null_rates.csv` | `method == "hier_ssm"`, column `rate` (41 / 1000) |
| **H1 Pooling Advantage in `broad_fleet`** | -5.39 min | 95% CI [-6.71, -4.08], Holm $p = 0.011$ | `results/study_inertia/table_paired_contrasts.csv` | `scenario == "broad_fleet" & contrast.str.contains("C2") & hypothesis == "H1"` |
| **H1 Pooling Advantage in `class_wide`** | -4.82 min | 95% CI [-6.12, -3.51], Holm $p = 0.011$ | `results/study_inertia/table_paired_contrasts.csv` | `scenario == "class_wide" & contrast.str.contains("C2") & hypothesis == "H1"` |
| **H1 Cost Check Penalty in `single_host_persistent`**| +9.46 min | 95% CI [+7.20, +11.72], Holm $p = 0.011$ | `results/study_inertia/table_paired_contrasts.csv` | `scenario == "single_host_persistent" & contrast.str.contains("C2") & hypothesis == "H1"` |
| **H2 Two-Scale Equivalence (C1 contrast)** | -0.18 min | 95% CI within $\pm 1.0$ min, Holm $p = 1.000$ | `results/study_inertia/table_paired_contrasts.csv` | Rows with `hypothesis == "H2"` |
| **H3 Hysteresis Delay Rise on Weak Harm** | +4.12 min | Exceeds 3.0 min bound | `results/study_inertia/table_scenario_summary.csv` | `scenario == "weak_persistent_3host" & method == "hier_ssm"` at $m=3$ vs $m=1$ |
| **`glr_window` False Alarms under Heavy Tails ($t(3)$)**| 85.7% | Failed Gate G2 | `results/study_combined/table_scenario_summary.csv` | `scenario == "regression_plus_heavytail" & method == "glr_window"`, column `null_alert_rate` |
| **`hier_ssm` False Alarms under Heavy Tails ($t(3)$)**| 6.0% | Power: 99.67% | `results/study_combined/table_scenario_summary.csv` | `scenario == "regression_plus_heavytail" & method == "hier_ssm"`, column `null_alert_rate` |
| **Primary Study Gate G2 Validity Range** | 3.9% – 5.9% | $p \in [0.107, 1.000]$ (50/50 Pass) | `results/study_inertia/table_calibration_validity.csv` | Columns `far` and `bb_pvalue_two_sided` across all 50 rows |
| **Multi-Family Gate G2 Audit** | 167/168 Pass | 1 fail (`hier_rank0` on S5) | `artifacts/policy_plain_v3/gate_status.json` | `cells_ok: 167, cells: 168` |
| **State-Space Filter Update Latency** | 0.424 ms | CPU single-thread | `results/study_inertia/table_runtime.csv` | `method == "hier_ssm"`, column `mean_update_ms` |
| **Evaluated Rollout Volume** | 9,600 rollouts | 240,000 policy evaluations | `results/study_inertia/per_rollout_policy.csv` | Length of table (240,000 rows across 5 methods $\times$ 5 $m$-values) |
| **Abstention Rate across Pipeline** | 0.00% | Eligible fraction = 1.0 | `results/plain_final/table_abstention.csv` | Column `eligible_fraction` everywhere $= 1.0$ |
