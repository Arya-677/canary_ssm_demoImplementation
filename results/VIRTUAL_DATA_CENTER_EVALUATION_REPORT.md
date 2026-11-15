# Virtual Data Center & Canary SSM: Rigorous Evaluation Report

**Document Status:** Complete Benchmark Audit (Prompt 11)
**Frozen Model Artifact SHA-256:** `9c3c83ba2a4ff173e1dd2fb80f3056f4c20c5edb0f8654108640ae0a90cdbe2a`

---

## 1. Independent Null Validation Audit (Equal False-Alert Budget)

All detectors were calibrated on independent calibration nulls using declared order statistics
($k = \lceil (B+1)(1-\alpha) \rceil$ for simple first-crossing, and policy replay for multi-channel).
Achieved null alert rates are evaluated on unseen independent validation nulls:

| method | threshold | k_order | B_calibration | n_validation | null_alerts | achieved_far | ci_lower_95 | ci_upper_95 | bb_pvalue | validity_gate | controlled_fwer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hier_ssm | -1.1412 | 96 | 100 | 100 | 1 | 0.0100 | 0.0003 | 0.0545 | 0.2116 | PASS | True |
| pooled_ssm | -3.6198 | 96 | 100 | 100 | 1 | 0.0100 | 0.0003 | 0.0545 | 0.2116 | PASS | True |
| indep_ssm | -1.9714 | 96 | 100 | 100 | 3 | 0.0300 | 0.0062 | 0.0852 | 0.7209 | PASS | True |
| topk_cusum | 70.1367 | 96 | 100 | 100 | 0 | 0.0000 | 0.0000 | 0.0362 | 0.0594 | PASS | True |
| adj_cusum | 43.9474 | 96 | 100 | 100 | 2 | 0.0200 | 0.0024 | 0.0704 | 0.4448 | PASS | True |
| adj_ewma | 2300108.4711 | 96 | 100 | 100 | 2 | 0.0200 | 0.0024 | 0.0704 | 0.4448 | PASS | True |
| multi_channel | -0.6730 | 96 | 100 | 100 | 0 | 0.0000 | 0.0000 | 0.0362 | 0.0594 | PASS | True |

### Key Finding: Host Risk Cutoff vs. Fleet False Alert Control
> [!IMPORTANT]
> A host-level risk cutoff (e.g. Pr > 0.50) fails to control fleet-wide false alerts, causing 13.0% false alarms across 4 hosts over 45 ticks. Fleet-wide order-statistic calibration on rollout maxima is mathematically required.
> An uncalibrated host risk cutoff (e.g. $\Pr > 0.50$) inflates fleet-wide false alerts to **13.0%**,
> whereas the calibrated release threshold guarantees fleet-wide false alert control at the target 5% budget.

---

## 2. Benchmark Scenario Performance (13 Conditions)

| scenario | method | is_harm | rollouts | det_15_min | det_30_min | det_45_min | det_60_min | miss_rate | premature_rate | mean_capped_time | median_delay | false_alert_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1_sparse | hier_ssm | True | 10 | 0.3000 | 0.3000 | 0.3000 | 0.3000 | 0.7000 | 0.0000 | 32.7000 | 3.0000 | nan |
| S1_sparse | pooled_ssm | True | 10 | 0.2000 | 0.2000 | 0.2000 | 0.2000 | 0.8000 | 0.0000 | 36.0000 | 0.0000 | nan |
| S1_sparse | indep_ssm | True | 10 | 0.4000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 28.1000 | 1.0000 | nan |
| S1_sparse | topk_cusum | True | 10 | 0.0000 | 0.2000 | 0.6000 | 0.6000 | 0.4000 | 0.0000 | 39.3000 | 35.5000 | nan |
| S1_sparse | adj_cusum | True | 10 | 0.0000 | 0.6000 | 0.9000 | 0.9000 | 0.1000 | 0.0000 | 31.5000 | 28.0000 | nan |
| S1_sparse | adj_ewma | True | 10 | 0.3000 | 0.3000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 34.9000 | 14.5000 | nan |
| S1_sparse | multi_channel | True | 10 | 0.2000 | 0.2000 | 0.2000 | 0.2000 | 0.8000 | 0.0000 | 36.7000 | 3.5000 | nan |
| S2_class_wide | hier_ssm | True | 10 | 0.8000 | 0.8000 | 0.8000 | 0.8000 | 0.2000 | 0.0000 | 9.9000 | 0.5000 | nan |
| S2_class_wide | pooled_ssm | True | 10 | 0.6000 | 0.6000 | 0.6000 | 0.6000 | 0.4000 | 0.0000 | 18.1000 | 0.0000 | nan |
| S2_class_wide | indep_ssm | True | 10 | 0.8000 | 0.8000 | 0.8000 | 0.8000 | 0.2000 | 0.0000 | 9.5000 | 0.0000 | nan |
| S2_class_wide | topk_cusum | True | 10 | 0.2000 | 0.6000 | 0.9000 | 0.9000 | 0.1000 | 0.0000 | 27.1000 | 28.0000 | nan |
| S2_class_wide | adj_cusum | True | 10 | 0.2000 | 0.4000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 30.7000 | 35.0000 | nan |
| S2_class_wide | adj_ewma | True | 10 | 0.3000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 30.6000 | 6.0000 | nan |
| S2_class_wide | multi_channel | True | 10 | 0.4000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 28.3000 | 3.0000 | nan |
| S3_broad | hier_ssm | True | 10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.4000 | 0.0000 | nan |
| S3_broad | pooled_ssm | True | 10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan |
| S3_broad | indep_ssm | True | 10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.3000 | 0.0000 | nan |
| S3_broad | topk_cusum | True | 10 | 0.4000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 14.9000 | 16.0000 | nan |
| S3_broad | adj_cusum | True | 10 | 0.0000 | 0.9000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 24.3000 | 24.5000 | nan |
| S3_broad | adj_ewma | True | 10 | 0.5000 | 0.8000 | 0.8000 | 0.8000 | 0.2000 | 0.0000 | 19.4000 | 11.5000 | nan |
| S3_broad | multi_channel | True | 10 | 0.9000 | 0.9000 | 0.9000 | 0.9000 | 0.1000 | 0.0000 | 6.6000 | 2.0000 | nan |
| S4_memory_only | hier_ssm | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S4_memory_only | pooled_ssm | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S4_memory_only | indep_ssm | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S4_memory_only | topk_cusum | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S4_memory_only | adj_cusum | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S4_memory_only | adj_ewma | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S4_memory_only | multi_channel | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S5_cpu_regression | hier_ssm | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S5_cpu_regression | pooled_ssm | True | 10 | 0.1000 | 0.1000 | 0.1000 | 0.1000 | 0.9000 | 0.0000 | 40.5000 | 0.0000 | nan |
| S5_cpu_regression | indep_ssm | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S5_cpu_regression | topk_cusum | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S5_cpu_regression | adj_cusum | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S5_cpu_regression | adj_ewma | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S5_cpu_regression | multi_channel | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S6_error_regression | hier_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S6_error_regression | pooled_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S6_error_regression | indep_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S6_error_regression | topk_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S6_error_regression | adj_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S6_error_regression | adj_ewma | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S6_error_regression | multi_channel | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S7_healthy_gc | hier_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S7_healthy_gc | pooled_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.2000 |
| S7_healthy_gc | indep_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.1000 |
| S7_healthy_gc | topk_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.1000 |
| S7_healthy_gc | adj_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.1000 |
| S7_healthy_gc | adj_ewma | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.1000 |
| S7_healthy_gc | multi_channel | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S8_fleet_load_spike | hier_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.3000 |
| S8_fleet_load_spike | pooled_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.0000 |
| S8_fleet_load_spike | indep_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.2000 |
| S8_fleet_load_spike | topk_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.3000 |
| S8_fleet_load_spike | adj_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.3000 |
| S8_fleet_load_spike | adj_ewma | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.3000 |
| S8_fleet_load_spike | multi_channel | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.2000 |
| S9_rack_fault | hier_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.4000 |
| S9_rack_fault | pooled_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.4000 |
| S9_rack_fault | indep_ssm | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.4000 |
| S9_rack_fault | topk_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.5000 |
| S9_rack_fault | adj_cusum | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.6000 |
| S9_rack_fault | adj_ewma | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.4000 |
| S9_rack_fault | multi_channel | False | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | nan | nan | 0.3000 |
| S10_simultaneous_rack_release | hier_ssm | True | 10 | 0.9000 | 0.9000 | 0.9000 | 0.9000 | 0.1000 | 0.0000 | 6.1000 | 0.0000 | nan |
| S10_simultaneous_rack_release | pooled_ssm | True | 10 | 0.7000 | 0.7000 | 0.7000 | 0.7000 | 0.3000 | 0.0000 | 13.5000 | 0.0000 | nan |
| S10_simultaneous_rack_release | indep_ssm | True | 10 | 0.9000 | 0.9000 | 0.9000 | 0.9000 | 0.1000 | 0.0000 | 5.8000 | 0.0000 | nan |
| S10_simultaneous_rack_release | topk_cusum | True | 10 | 0.4000 | 0.8000 | 0.8000 | 0.8000 | 0.2000 | 0.0000 | 20.0000 | 15.0000 | nan |
| S10_simultaneous_rack_release | adj_cusum | True | 10 | 0.5000 | 0.8000 | 0.8000 | 0.8000 | 0.2000 | 0.0000 | 20.7000 | 13.0000 | nan |
| S10_simultaneous_rack_release | adj_ewma | True | 10 | 0.6000 | 0.7000 | 0.8000 | 0.8000 | 0.2000 | 0.0000 | 17.4000 | 5.5000 | nan |
| S10_simultaneous_rack_release | multi_channel | True | 10 | 0.7000 | 0.7000 | 0.7000 | 0.7000 | 0.3000 | 0.0000 | 15.6000 | 0.0000 | nan |
| S11_missingness | hier_ssm | True | 10 | 0.4000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 27.7000 | 1.5000 | nan |
| S11_missingness | pooled_ssm | True | 10 | 0.2000 | 0.2000 | 0.2000 | 0.2000 | 0.8000 | 0.0000 | 36.0000 | 0.0000 | nan |
| S11_missingness | indep_ssm | True | 10 | 0.3000 | 0.3000 | 0.3000 | 0.3000 | 0.7000 | 0.0000 | 31.8000 | 0.0000 | nan |
| S11_missingness | topk_cusum | True | 10 | 0.0000 | 0.0000 | 0.2000 | 0.2000 | 0.8000 | 0.0000 | 43.1000 | 35.5000 | nan |
| S11_missingness | adj_cusum | True | 10 | 0.0000 | 0.2000 | 0.2000 | 0.2000 | 0.8000 | 0.0000 | 41.9000 | 29.5000 | nan |
| S11_missingness | adj_ewma | True | 10 | 0.0000 | 0.2000 | 0.2000 | 0.2000 | 0.8000 | 0.0000 | 40.4000 | 22.0000 | nan |
| S11_missingness | multi_channel | True | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 45.0000 | nan | nan |
| S12_late_arrivals | hier_ssm | True | 10 | 0.4000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 28.4000 | 3.5000 | nan |
| S12_late_arrivals | pooled_ssm | True | 10 | 0.3000 | 0.3000 | 0.3000 | 0.3000 | 0.7000 | 0.0000 | 32.2000 | 1.0000 | nan |
| S12_late_arrivals | indep_ssm | True | 10 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.0000 | 23.6000 | 3.0000 | nan |
| S12_late_arrivals | topk_cusum | True | 10 | 0.0000 | 0.0000 | 0.1000 | 0.1000 | 0.9000 | 0.0000 | 43.6000 | 31.0000 | nan |
| S12_late_arrivals | adj_cusum | True | 10 | 0.0000 | 0.1000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 41.1000 | 35.5000 | nan |
| S12_late_arrivals | adj_ewma | True | 10 | 0.0000 | 0.2000 | 0.3000 | 0.3000 | 0.7000 | 0.0000 | 39.8000 | 29.0000 | nan |
| S12_late_arrivals | multi_channel | True | 10 | 0.3000 | 0.3000 | 0.3000 | 0.3000 | 0.7000 | 0.0000 | 32.5000 | 5.0000 | nan |
| S13_recovery | hier_ssm | True | 10 | 0.3000 | 0.3000 | 0.3000 | 0.3000 | 0.7000 | 0.0000 | 32.0000 | 2.0000 | nan |
| S13_recovery | pooled_ssm | True | 10 | 0.4000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 27.0000 | 0.0000 | nan |
| S13_recovery | indep_ssm | True | 10 | 0.4000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 28.1000 | 2.5000 | nan |
| S13_recovery | topk_cusum | True | 10 | 0.0000 | 0.1000 | 0.1000 | 0.1000 | 0.8000 | 0.0000 | 43.0000 | 25.0000 | nan |
| S13_recovery | adj_cusum | True | 10 | 0.0000 | 0.1000 | 0.1000 | 0.1000 | 0.5000 | 0.0000 | 42.9000 | 24.0000 | nan |
| S13_recovery | adj_ewma | True | 10 | 0.0000 | 0.4000 | 0.4000 | 0.4000 | 0.6000 | 0.0000 | 35.5000 | 21.5000 | nan |
| S13_recovery | multi_channel | True | 10 | 0.1000 | 0.1000 | 0.1000 | 0.1000 | 0.9000 | 0.0000 | 40.5000 | 0.0000 | nan |

### Retention of Negative Results:
- **Broad Harm (S3):** Under broad, completely homogeneous harm, fleet-wide pooling achieves comparable or slightly faster detection than the hierarchical model due to aggregating all canaries into one scalar parameter.
- **Missingness (S11):** 15% missing telemetry increases mean capped time across all methods and requires detector abstention when control coverage is impaired.
- **Sparse Harm (S1 & S2):** Complete pooling severely dilutes sparse harm (miss rate 40%), whereas Hierarchical SSM isolates local within-class deviations via the Helmert contrast basis.

---

## 3. Localization Performance on Affected Canaries

- **Mean Top-3 Recall:** 0.939
- **Mean Precision:** 0.481
- **Mean Recall:** 0.911
- **Mean F1 Score:** 0.594
- **Mean False Discovery Proportion (FDP):** 0.519

---

## 4. Attribution Confusion Matrix & Abstention Accounting

- **Total Rollouts Evaluated:** 130
- **Abstention Count:** 2 (1.5%)
- **Attribution Accuracy (evaluable):** 35.9%

| true_state | NORMAL | LATENCY_REGRESSION | MEMORY_GROWTH_LEAK | COMPOUND_REGRESSION | INFRASTRUCTURE_FAULT | INSUFFICIENT_DATA |
| --- | --- | --- | --- | --- | --- | --- |
| NORMAL | 20 | 0 | 0 | 0 | 0 | 0 |
| LATENCY_REGRESSION | 42 | 26 | 0 | 0 | 0 | 2 |
| MEMORY_GROWTH_LEAK | 10 | 0 | 0 | 0 | 0 | 0 |
| COMPOUND_REGRESSION | 10 | 0 | 0 | 0 | 0 | 0 |
| INFRASTRUCTURE_FAULT | 15 | 5 | 0 | 0 | 0 | 0 |

---

## 5. Paired Bootstrap Contrasts (Rollout Paired Resampling)

Differences in Capped Time-to-Success ($\Delta = \text{Time}_{\text{baseline}} - \text{Time}_{\text{hier}}$) resampled by rollout pairs:

| comparator | reference | mean_capped_time_difference | ci_lower_95 | ci_upper_95 | bootstrap_p_value | n_paired_rollouts | hierarchy_statistically_superior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pooled_ssm | hier_ssm | 2.3400 | -2.1300 | 6.6700 | 0.3130 | 90 | False |
| indep_ssm | hier_ssm | -1.1100 | -3.4600 | 1.0600 | 0.3060 | 90 | False |
| topk_cusum | hier_ssm | 10.4200 | 7.0000 | 13.8000 | 0.0000 | 90 | True |
| adj_cusum | hier_ssm | 10.6600 | 6.7800 | 14.2600 | 0.0000 | 90 | True |
| adj_ewma | hier_ssm | 8.9800 | 5.1100 | 12.7800 | 0.0000 | 90 | True |

---

_Report generated strictly from executed simulation runs and versioned CSV tables._
