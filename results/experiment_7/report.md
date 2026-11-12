# Experiment 7: Causal Workload Regime Rule Evaluation

**Null rollouts per cell:** 500 | **Harmed rollouts per scenario:** 200

## 1. Null False-Alert Rates (Target: 5.0%)

| true_regime   | method           | policy             |   alerts |   n |   rate |      ci_lo |     ci_hi | pass_upper_le_8pct   | pass_contains_5pct   |
|:--------------|:-----------------|:-------------------|---------:|----:|-------:|-----------:|----------:|:---------------------|:---------------------|
| plain         | matched_contrast | causal_dual_regime |       19 | 500 |  0.038 | 0.0230308  | 0.0587073 | True                 | True                 |
| plain         | matched_contrast | single_threshold   |       19 | 500 |  0.038 | 0.0230308  | 0.0587073 | True                 | True                 |
| plain         | adj_cusum        | causal_dual_regime |       32 | 500 |  0.064 | 0.0441842  | 0.0891506 | False                | True                 |
| plain         | adj_cusum        | single_threshold   |        5 | 500 |  0.01  | 0.00325472 | 0.0231814 | True                 | False                |
| plain         | topk_cusum       | causal_dual_regime |       26 | 500 |  0.052 | 0.0342457  | 0.0752664 | True                 | True                 |
| plain         | topk_cusum       | single_threshold   |        4 | 500 |  0.008 | 0.00218391 | 0.0203556 | True                 | False                |
| plain         | hier_ssm         | causal_dual_regime |       15 | 500 |  0.03  | 0.016886   | 0.0489982 | True                 | False                |
| plain         | hier_ssm         | single_threshold   |       16 | 500 |  0.032 | 0.0183992  | 0.0514468 | True                 | True                 |
| step          | matched_contrast | causal_dual_regime |       19 | 500 |  0.038 | 0.0230308  | 0.0587073 | True                 | True                 |
| step          | matched_contrast | single_threshold   |       46 | 500 |  0.092 | 0.0681433  | 0.120807  | False                | False                |
| step          | adj_cusum        | causal_dual_regime |       45 | 500 |  0.09  | 0.066404   | 0.118573  | False                | False                |
| step          | adj_cusum        | single_threshold   |      167 | 500 |  0.334 | 0.292747   | 0.37723   | False                | False                |
| step          | topk_cusum       | causal_dual_regime |       38 | 500 |  0.076 | 0.0543408  | 0.102826  | False                | False                |
| step          | topk_cusum       | single_threshold   |      163 | 500 |  0.326 | 0.285047   | 0.369025  | False                | False                |
| step          | hier_ssm         | causal_dual_regime |       34 | 500 |  0.068 | 0.0475482  | 0.0937296 | False                | True                 |
| step          | hier_ssm         | single_threshold   |       47 | 500 |  0.094 | 0.0698862  | 0.123038  | False                | False                |

## 2. Statistical Power & Horizon-Capped Time Comparison

| scenario   | method           |   n |   detection_rate_dual |   mean_capped_dual |   detection_rate_single |   mean_capped_single |   mean_capped_diff_dual_minus_single |     ci_lo |     ci_hi | power_gain_reading                                           |
|:-----------|:-----------------|----:|----------------------:|-------------------:|------------------------:|---------------------:|-------------------------------------:|----------:|----------:|:-------------------------------------------------------------|
| S1_plain   | adj_cusum        | 200 |                 0.44  |             83.595 |                   0.08  |              113.64  |                              -30.045 | -35.2664  | -25.0093  | negative favours dual causal rule (faster / more detections) |
| S1_plain   | hier_ssm         | 200 |                 0.41  |             71.05  |                   0.43  |               68.69  |                                2.36  |   0.585   |   4.74512 | negative favours dual causal rule (faster / more detections) |
| S1_plain   | matched_contrast | 200 |                 0.3   |             88.77  |                   0.305 |               88.18  |                                0.59  |   0       |   1.77    | negative favours dual causal rule (faster / more detections) |
| S1_plain   | topk_cusum       | 200 |                 0.795 |             52.145 |                   0.305 |               95.29  |                              -43.145 | -48.4957  | -37.6843  | negative favours dual causal rule (faster / more detections) |
| S1_step    | adj_cusum        | 200 |                 0.01  |            119.24  |                   0.23  |              101.305 |                               17.935 |  13.6591  |  22.5551  | negative favours dual causal rule (faster / more detections) |
| S1_step    | hier_ssm         | 200 |                 0.345 |             78.965 |                   0.425 |               69.33  |                                9.635 |   5.55475 |  14.335   | negative favours dual causal rule (faster / more detections) |
| S1_step    | matched_contrast | 200 |                 0.235 |             96.32  |                   0.37  |               82.14  |                               14.18  |   9.60975 |  19.3501  | negative favours dual causal rule (faster / more detections) |
| S1_step    | topk_cusum       | 200 |                 0.01  |            119.215 |                   0.485 |               80.16  |                               39.055 |  33.6593  |  44.8104  | negative favours dual causal rule (faster / more detections) |