# Results (generated from CSVs; interpret per handbook Section 15)

Simulation results under stated assumptions only. Losing methods stay in the tables.

**Calibration gate: FAIL** (117/128 method x family cells ok; 0 have n>=400). Delay/power comparisons are valid only for methods inside this gate.


## table_null_rates

| method           |   alerts |   n_null |   rate |   ci_lo |   ci_hi | pass_contains_5pct   | pass_upper_le_8pct   | above_target   | gate_evaluable   |
|:-----------------|---------:|---------:|-------:|--------:|--------:|:---------------------|:---------------------|:---------------|:-----------------|
| adj_cusum        |       24 |      500 |  0.048 |  0.031  |  0.0706 | True                 | True                 | False          | True             |
| adj_ewma         |       23 |      500 |  0.046 |  0.0294 |  0.0682 | True                 | True                 | False          | True             |
| combo_hier_m0    |       10 |      500 |  0.02  |  0.0096 |  0.0365 | False                | True                 | False          | True             |
| combo_hier_topk  |       19 |      500 |  0.038 |  0.023  |  0.0587 | True                 | True                 | False          | True             |
| combo_m0_topk    |       20 |      500 |  0.04  |  0.0246 |  0.0611 | True                 | True                 | False          | True             |
| hier_arwhite     |       15 |      500 |  0.03  |  0.0169 |  0.049  | False                | True                 | False          | True             |
| hier_degraded    |       18 |      500 |  0.036 |  0.0215 |  0.0563 | True                 | True                 | False          | True             |
| hier_huber       |       12 |      500 |  0.024 |  0.0125 |  0.0415 | False                | True                 | False          | True             |
| hier_no_persist  |       17 |      500 |  0.034 |  0.0199 |  0.0539 | True                 | True                 | False          | True             |
| hier_rank0       |       11 |      500 |  0.022 |  0.011  |  0.039  | False                | True                 | False          | True             |
| hier_ssm         |       15 |      500 |  0.03  |  0.0169 |  0.049  | False                | True                 | False          | True             |
| hier_white       |       17 |      500 |  0.034 |  0.0199 |  0.0539 | True                 | True                 | False          | True             |
| indep_ssm        |       23 |      500 |  0.046 |  0.0294 |  0.0682 | True                 | True                 | False          | True             |
| matched_contrast |       15 |      500 |  0.03  |  0.0169 |  0.049  | False                | True                 | False          | True             |
| pooled_ssm       |       18 |      500 |  0.036 |  0.0215 |  0.0563 | True                 | True                 | False          | True             |
| topk_cusum       |       20 |      500 |  0.04  |  0.0246 |  0.0611 | True                 | True                 | False          | True             |

## table_null_by_family

| family          | method           |   alerts |   n_null |   rate |   ci_lo |   ci_hi | pass_contains_5pct   | pass_upper_le_8pct   | above_target   | gate_evaluable   |
|:----------------|:-----------------|---------:|---------:|-------:|--------:|--------:|:---------------------|:---------------------|:---------------|:-----------------|
| S1_sparse       | adj_cusum        |        0 |      108 | 0      |  0      |  0.0336 | False                | True                 | False          | False            |
| S1_sparse       | adj_ewma         |        3 |      108 | 0.0278 |  0.0058 |  0.079  | True                 | True                 | False          | False            |
| S1_sparse       | combo_hier_m0    |        2 |      108 | 0.0185 |  0.0023 |  0.0653 | True                 | True                 | False          | False            |
| S1_sparse       | combo_hier_topk  |        2 |      108 | 0.0185 |  0.0023 |  0.0653 | True                 | True                 | False          | False            |
| S1_sparse       | combo_m0_topk    |        2 |      108 | 0.0185 |  0.0023 |  0.0653 | True                 | True                 | False          | False            |
| S1_sparse       | hier_arwhite     |        2 |      108 | 0.0185 |  0.0023 |  0.0653 | True                 | True                 | False          | False            |
| S1_sparse       | hier_degraded    |        1 |      108 | 0.0093 |  0.0002 |  0.0505 | True                 | True                 | False          | False            |
| S1_sparse       | hier_huber       |        1 |      108 | 0.0093 |  0.0002 |  0.0505 | True                 | True                 | False          | False            |
| S1_sparse       | hier_no_persist  |        7 |      108 | 0.0648 |  0.0265 |  0.129  | True                 | False                | False          | False            |
| S1_sparse       | hier_rank0       |        5 |      108 | 0.0463 |  0.0152 |  0.1047 | True                 | False                | False          | False            |
| S1_sparse       | hier_ssm         |        2 |      108 | 0.0185 |  0.0023 |  0.0653 | True                 | True                 | False          | False            |
| S1_sparse       | hier_white       |        1 |      108 | 0.0093 |  0.0002 |  0.0505 | True                 | True                 | False          | False            |
| S1_sparse       | indep_ssm        |        3 |      108 | 0.0278 |  0.0058 |  0.079  | True                 | True                 | False          | False            |
| S1_sparse       | matched_contrast |        3 |      108 | 0.0278 |  0.0058 |  0.079  | True                 | True                 | False          | False            |
| S1_sparse       | pooled_ssm       |        3 |      108 | 0.0278 |  0.0058 |  0.079  | True                 | True                 | False          | False            |
| S1_sparse       | topk_cusum       |        0 |      108 | 0      |  0      |  0.0336 | False                | True                 | False          | False            |
| S1_step         | adj_cusum        |       22 |       79 | 0.2785 |  0.1835 |  0.3907 | False                | False                | True           | False            |
| S1_step         | adj_ewma         |       14 |       79 | 0.1772 |  0.1004 |  0.2794 | False                | False                | True           | False            |
| S1_step         | combo_hier_m0    |        3 |       79 | 0.038  |  0.0079 |  0.107  | True                 | False                | False          | False            |
| S1_step         | combo_hier_topk  |       17 |       79 | 0.2152 |  0.1306 |  0.322  | False                | False                | True           | False            |
| S1_step         | combo_m0_topk    |       13 |       79 | 0.1646 |  0.0906 |  0.2649 | False                | False                | True           | False            |
| S1_step         | hier_arwhite     |        9 |       79 | 0.1139 |  0.0534 |  0.2053 | False                | False                | True           | False            |
| S1_step         | hier_degraded    |       11 |       79 | 0.1392 |  0.0716 |  0.2355 | False                | False                | True           | False            |
| S1_step         | hier_huber       |        9 |       79 | 0.1139 |  0.0534 |  0.2053 | False                | False                | True           | False            |
| S1_step         | hier_no_persist  |        1 |       79 | 0.0127 |  0.0003 |  0.0685 | True                 | True                 | False          | False            |
| S1_step         | hier_rank0       |        0 |       79 | 0      |  0      |  0.0456 | False                | True                 | False          | False            |
| S1_step         | hier_ssm         |        9 |       79 | 0.1139 |  0.0534 |  0.2053 | False                | False                | True           | False            |
| S1_step         | hier_white       |       13 |       79 | 0.1646 |  0.0906 |  0.2649 | False                | False                | True           | False            |
| S1_step         | indep_ssm        |       14 |       79 | 0.1772 |  0.1004 |  0.2794 | False                | False                | True           | False            |
| S1_step         | matched_contrast |        3 |       79 | 0.038  |  0.0079 |  0.107  | True                 | False                | False          | False            |
| S1_step         | pooled_ssm       |        2 |       79 | 0.0253 |  0.0031 |  0.0885 | True                 | False                | False          | False            |
| S1_step         | topk_cusum       |       19 |       79 | 0.2405 |  0.1514 |  0.3498 | False                | False                | True           | False            |
| S2_class_wide   | adj_cusum        |        1 |       93 | 0.0108 |  0.0003 |  0.0585 | True                 | True                 | False          | False            |
| S2_class_wide   | adj_ewma         |        3 |       93 | 0.0323 |  0.0067 |  0.0914 | True                 | False                | False          | False            |
| S2_class_wide   | combo_hier_m0    |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | combo_hier_topk  |        0 |       93 | 0      |  0      |  0.0389 | False                | True                 | False          | False            |
| S2_class_wide   | combo_m0_topk    |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_arwhite     |        1 |       93 | 0.0108 |  0.0003 |  0.0585 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_degraded    |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_huber       |        1 |       93 | 0.0108 |  0.0003 |  0.0585 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_no_persist  |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_rank0       |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_ssm         |        1 |       93 | 0.0108 |  0.0003 |  0.0585 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_white       |        0 |       93 | 0      |  0      |  0.0389 | False                | True                 | False          | False            |
| S2_class_wide   | indep_ssm        |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | matched_contrast |        2 |       93 | 0.0215 |  0.0026 |  0.0755 | True                 | True                 | False          | False            |
| S2_class_wide   | pooled_ssm       |        5 |       93 | 0.0538 |  0.0177 |  0.121  | True                 | False                | False          | False            |
| S2_class_wide   | topk_cusum       |        0 |       93 | 0      |  0      |  0.0389 | False                | True                 | False          | False            |
| S3_broad        | adj_cusum        |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | adj_ewma         |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | combo_hier_m0    |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | combo_hier_topk  |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | combo_m0_topk    |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | hier_arwhite     |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | hier_degraded    |        1 |       54 | 0.0185 |  0.0005 |  0.0989 | True                 | False                | False          | False            |
| S3_broad        | hier_huber       |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | hier_no_persist  |        2 |       54 | 0.037  |  0.0045 |  0.1275 | True                 | False                | False          | False            |
| S3_broad        | hier_rank0       |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | hier_ssm         |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | hier_white       |        1 |       54 | 0.0185 |  0.0005 |  0.0989 | True                 | False                | False          | False            |
| S3_broad        | indep_ssm        |        2 |       54 | 0.037  |  0.0045 |  0.1275 | True                 | False                | False          | False            |
| S3_broad        | matched_contrast |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S3_broad        | pooled_ssm       |        1 |       54 | 0.0185 |  0.0005 |  0.0989 | True                 | False                | False          | False            |
| S3_broad        | topk_cusum       |        0 |       54 | 0      |  0      |  0.066  | True                 | True                 | False          | False            |
| S4_weak_sparse  | adj_cusum        |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | adj_ewma         |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | combo_hier_m0    |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | combo_hier_topk  |        0 |       46 | 0      |  0      |  0.0771 | True                 | True                 | False          | False            |
| S4_weak_sparse  | combo_m0_topk    |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_arwhite     |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_degraded    |        2 |       46 | 0.0435 |  0.0053 |  0.1484 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_huber       |        0 |       46 | 0      |  0      |  0.0771 | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_no_persist  |        2 |       46 | 0.0435 |  0.0053 |  0.1484 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_rank0       |        0 |       46 | 0      |  0      |  0.0771 | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_ssm         |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_white       |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | indep_ssm        |        2 |       46 | 0.0435 |  0.0053 |  0.1484 | True                 | False                | False          | False            |
| S4_weak_sparse  | matched_contrast |        1 |       46 | 0.0217 |  0.0006 |  0.1153 | True                 | False                | False          | False            |
| S4_weak_sparse  | pooled_ssm       |        2 |       46 | 0.0435 |  0.0053 |  0.1484 | True                 | False                | False          | False            |
| S4_weak_sparse  | topk_cusum       |        0 |       46 | 0      |  0      |  0.0771 | True                 | True                 | False          | False            |
| S5_label_errors | adj_cusum        |        0 |       51 | 0      |  0      |  0.0698 | True                 | True                 | False          | False            |
| S5_label_errors | adj_ewma         |        0 |       51 | 0      |  0      |  0.0698 | True                 | True                 | False          | False            |
| S5_label_errors | combo_hier_m0    |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| S5_label_errors | combo_hier_topk  |        0 |       51 | 0      |  0      |  0.0698 | True                 | True                 | False          | False            |
| S5_label_errors | combo_m0_topk    |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| S5_label_errors | hier_arwhite     |        2 |       51 | 0.0392 |  0.0048 |  0.1346 | True                 | False                | False          | False            |
| S5_label_errors | hier_degraded    |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| S5_label_errors | hier_huber       |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| S5_label_errors | hier_no_persist  |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| S5_label_errors | hier_rank0       |        2 |       51 | 0.0392 |  0.0048 |  0.1346 | True                 | False                | False          | False            |
| S5_label_errors | hier_ssm         |        2 |       51 | 0.0392 |  0.0048 |  0.1346 | True                 | False                | False          | False            |
| S5_label_errors | hier_white       |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| S5_label_errors | indep_ssm        |        0 |       51 | 0      |  0      |  0.0698 | True                 | True                 | False          | False            |
| S5_label_errors | matched_contrast |        3 |       51 | 0.0588 |  0.0123 |  0.1624 | True                 | False                | False          | False            |
| S5_label_errors | pooled_ssm       |        4 |       51 | 0.0784 |  0.0218 |  0.1888 | True                 | False                | False          | False            |
| S5_label_errors | topk_cusum       |        1 |       51 | 0.0196 |  0.0005 |  0.1045 | True                 | False                | False          | False            |
| single_canary   | adj_cusum        |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | adj_ewma         |        2 |       43 | 0.0465 |  0.0057 |  0.1581 | True                 | False                | False          | False            |
| single_canary   | combo_hier_m0    |        1 |       43 | 0.0233 |  0.0006 |  0.1229 | True                 | False                | False          | False            |
| single_canary   | combo_hier_topk  |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | combo_m0_topk    |        1 |       43 | 0.0233 |  0.0006 |  0.1229 | True                 | False                | False          | False            |
| single_canary   | hier_arwhite     |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | hier_degraded    |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | hier_huber       |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | hier_no_persist  |        1 |       43 | 0.0233 |  0.0006 |  0.1229 | True                 | False                | False          | False            |
| single_canary   | hier_rank0       |        2 |       43 | 0.0465 |  0.0057 |  0.1581 | True                 | False                | False          | False            |
| single_canary   | hier_ssm         |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | hier_white       |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | indep_ssm        |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| single_canary   | matched_contrast |        3 |       43 | 0.0698 |  0.0146 |  0.1906 | True                 | False                | False          | False            |
| single_canary   | pooled_ssm       |        1 |       43 | 0.0233 |  0.0006 |  0.1229 | True                 | False                | False          | False            |
| single_canary   | topk_cusum       |        0 |       43 | 0      |  0      |  0.0822 | True                 | False                | False          | False            |
| transient       | adj_cusum        |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | adj_ewma         |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | combo_hier_m0    |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | combo_hier_topk  |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | combo_m0_topk    |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | hier_arwhite     |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | hier_degraded    |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | hier_huber       |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | hier_no_persist  |        1 |       26 | 0.0385 |  0.001  |  0.1964 | True                 | False                | False          | False            |
| transient       | hier_rank0       |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | hier_ssm         |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | hier_white       |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | indep_ssm        |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | matched_contrast |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | pooled_ssm       |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |
| transient       | topk_cusum       |        0 |       26 | 0      |  0      |  0.1323 | True                 | False                | False          | False            |

## table_abstention

| family          | method           |   eligible_fraction |
|:----------------|:-----------------|--------------------:|
| S1_sparse       | adj_cusum        |                   1 |
| S1_sparse       | adj_ewma         |                   1 |
| S1_sparse       | combo_hier_m0    |                   1 |
| S1_sparse       | combo_hier_topk  |                   1 |
| S1_sparse       | combo_m0_topk    |                   1 |
| S1_sparse       | hier_arwhite     |                   1 |
| S1_sparse       | hier_degraded    |                   1 |
| S1_sparse       | hier_huber       |                   1 |
| S1_sparse       | hier_no_persist  |                   1 |
| S1_sparse       | hier_rank0       |                   1 |
| S1_sparse       | hier_ssm         |                   1 |
| S1_sparse       | hier_white       |                   1 |
| S1_sparse       | indep_ssm        |                   1 |
| S1_sparse       | matched_contrast |                   1 |
| S1_sparse       | pooled_ssm       |                   1 |
| S1_sparse       | topk_cusum       |                   1 |
| S1_step         | adj_cusum        |                   1 |
| S1_step         | adj_ewma         |                   1 |
| S1_step         | combo_hier_m0    |                   1 |
| S1_step         | combo_hier_topk  |                   1 |
| S1_step         | combo_m0_topk    |                   1 |
| S1_step         | hier_arwhite     |                   1 |
| S1_step         | hier_degraded    |                   1 |
| S1_step         | hier_huber       |                   1 |
| S1_step         | hier_no_persist  |                   1 |
| S1_step         | hier_rank0       |                   1 |
| S1_step         | hier_ssm         |                   1 |
| S1_step         | hier_white       |                   1 |
| S1_step         | indep_ssm        |                   1 |
| S1_step         | matched_contrast |                   1 |
| S1_step         | pooled_ssm       |                   1 |
| S1_step         | topk_cusum       |                   1 |
| S2_class_wide   | adj_cusum        |                   1 |
| S2_class_wide   | adj_ewma         |                   1 |
| S2_class_wide   | combo_hier_m0    |                   1 |
| S2_class_wide   | combo_hier_topk  |                   1 |
| S2_class_wide   | combo_m0_topk    |                   1 |
| S2_class_wide   | hier_arwhite     |                   1 |
| S2_class_wide   | hier_degraded    |                   1 |
| S2_class_wide   | hier_huber       |                   1 |
| S2_class_wide   | hier_no_persist  |                   1 |
| S2_class_wide   | hier_rank0       |                   1 |
| S2_class_wide   | hier_ssm         |                   1 |
| S2_class_wide   | hier_white       |                   1 |
| S2_class_wide   | indep_ssm        |                   1 |
| S2_class_wide   | matched_contrast |                   1 |
| S2_class_wide   | pooled_ssm       |                   1 |
| S2_class_wide   | topk_cusum       |                   1 |
| S3_broad        | adj_cusum        |                   1 |
| S3_broad        | adj_ewma         |                   1 |
| S3_broad        | combo_hier_m0    |                   1 |
| S3_broad        | combo_hier_topk  |                   1 |
| S3_broad        | combo_m0_topk    |                   1 |
| S3_broad        | hier_arwhite     |                   1 |
| S3_broad        | hier_degraded    |                   1 |
| S3_broad        | hier_huber       |                   1 |
| S3_broad        | hier_no_persist  |                   1 |
| S3_broad        | hier_rank0       |                   1 |
| S3_broad        | hier_ssm         |                   1 |
| S3_broad        | hier_white       |                   1 |
| S3_broad        | indep_ssm        |                   1 |
| S3_broad        | matched_contrast |                   1 |
| S3_broad        | pooled_ssm       |                   1 |
| S3_broad        | topk_cusum       |                   1 |
| S4_weak_sparse  | adj_cusum        |                   1 |
| S4_weak_sparse  | adj_ewma         |                   1 |
| S4_weak_sparse  | combo_hier_m0    |                   1 |
| S4_weak_sparse  | combo_hier_topk  |                   1 |
| S4_weak_sparse  | combo_m0_topk    |                   1 |
| S4_weak_sparse  | hier_arwhite     |                   1 |
| S4_weak_sparse  | hier_degraded    |                   1 |
| S4_weak_sparse  | hier_huber       |                   1 |
| S4_weak_sparse  | hier_no_persist  |                   1 |
| S4_weak_sparse  | hier_rank0       |                   1 |
| S4_weak_sparse  | hier_ssm         |                   1 |
| S4_weak_sparse  | hier_white       |                   1 |
| S4_weak_sparse  | indep_ssm        |                   1 |
| S4_weak_sparse  | matched_contrast |                   1 |
| S4_weak_sparse  | pooled_ssm       |                   1 |
| S4_weak_sparse  | topk_cusum       |                   1 |
| S5_label_errors | adj_cusum        |                   1 |
| S5_label_errors | adj_ewma         |                   1 |
| S5_label_errors | combo_hier_m0    |                   1 |
| S5_label_errors | combo_hier_topk  |                   1 |
| S5_label_errors | combo_m0_topk    |                   1 |
| S5_label_errors | hier_arwhite     |                   1 |
| S5_label_errors | hier_degraded    |                   1 |
| S5_label_errors | hier_huber       |                   1 |
| S5_label_errors | hier_no_persist  |                   1 |
| S5_label_errors | hier_rank0       |                   1 |
| S5_label_errors | hier_ssm         |                   1 |
| S5_label_errors | hier_white       |                   1 |
| S5_label_errors | indep_ssm        |                   1 |
| S5_label_errors | matched_contrast |                   1 |
| S5_label_errors | pooled_ssm       |                   1 |
| S5_label_errors | topk_cusum       |                   1 |
| single_canary   | adj_cusum        |                   1 |
| single_canary   | adj_ewma         |                   1 |
| single_canary   | combo_hier_m0    |                   1 |
| single_canary   | combo_hier_topk  |                   1 |
| single_canary   | combo_m0_topk    |                   1 |
| single_canary   | hier_arwhite     |                   1 |
| single_canary   | hier_degraded    |                   1 |
| single_canary   | hier_huber       |                   1 |
| single_canary   | hier_no_persist  |                   1 |
| single_canary   | hier_rank0       |                   1 |
| single_canary   | hier_ssm         |                   1 |
| single_canary   | hier_white       |                   1 |
| single_canary   | indep_ssm        |                   1 |
| single_canary   | matched_contrast |                   1 |
| single_canary   | pooled_ssm       |                   1 |
| single_canary   | topk_cusum       |                   1 |
| transient       | adj_cusum        |                   1 |
| transient       | adj_ewma         |                   1 |
| transient       | combo_hier_m0    |                   1 |
| transient       | combo_hier_topk  |                   1 |
| transient       | combo_m0_topk    |                   1 |
| transient       | hier_arwhite     |                   1 |
| transient       | hier_degraded    |                   1 |
| transient       | hier_huber       |                   1 |
| transient       | hier_no_persist  |                   1 |
| transient       | hier_rank0       |                   1 |
| transient       | hier_ssm         |                   1 |
| transient       | hier_white       |                   1 |
| transient       | indep_ssm        |                   1 |
| transient       | matched_contrast |                   1 |
| transient       | pooled_ssm       |                   1 |
| transient       | topk_cusum       |                   1 |

## table_detection

| method           |   n_events |   miss |   premature |   late_after_recovery |   mean_capped_time |   cond_delay_mean |   cond_delay_median |   P_detect_5m |   P_detect_15m |   P_detect_30m |   P_detect_60m |   P_detect_120m |
|:-----------------|-----------:|-------:|------------:|----------------------:|-------------------:|------------------:|--------------------:|--------------:|---------------:|---------------:|---------------:|----------------:|
| matched_contrast |        474 | 0.5127 |           0 |                0.0105 |            69.3502 |           13.7699 |                  11 |        0.1688 |         0.2954 |         0.4241 |         0.4768 |          0.4768 |
| adj_ewma         |        474 | 0.4325 |           0 |                0.0359 |            70.9156 |           27.6746 |                  28 |        0      |         0.057  |         0.3249 |         0.5316 |          0.5316 |
| adj_cusum        |        474 | 0.4726 |           0 |                0.1203 |            85.9852 |           36.4611 |                  37 |        0      |         0      |         0.0654 |         0.4072 |          0.4072 |
| topk_cusum       |        474 | 0.23   |           0 |                0.038  |            52.9705 |           28.438  |                  28 |        0      |         0.0295 |         0.403  |         0.7321 |          0.7321 |
| pooled_ssm       |        474 | 0.4536 |           0 |                0      |            56.135  |            3.1197 |                   0 |        0.462  |         0.5063 |         0.5338 |         0.5464 |          0.5464 |
| indep_ssm        |        474 | 0.1139 |           0 |                0.0084 |            27.3059 |           14.3822 |                  12 |        0.1835 |         0.5401 |         0.789  |         0.8776 |          0.8776 |
| hier_ssm         |        474 | 0.1624 |           0 |                0.0021 |            27.1287 |            8.8359 |                   5 |        0.4325 |         0.6477 |         0.7827 |         0.8354 |          0.8354 |
| hier_no_persist  |        474 | 0.5865 |           0 |                0.0105 |            74.1709 |            6.267  |                   0 |        0.2911 |         0.3291 |         0.3797 |         0.403  |          0.403  |
| hier_rank0       |        474 | 0.5759 |           0 |                0      |            71.1181 |            4.7264 |                   2 |        0.3101 |         0.3882 |         0.4177 |         0.4241 |          0.4241 |
| hier_arwhite     |        474 | 0.1624 |           0 |                0.0021 |            27.1287 |            8.8359 |                   5 |        0.4325 |         0.6477 |         0.7827 |         0.8354 |          0.8354 |
| hier_white       |        474 | 0.1857 |           0 |                0.0021 |            33.403  |           13.3844 |                  10 |        0.2278 |         0.5359 |         0.7342 |         0.8122 |          0.8122 |
| hier_huber       |        474 | 0.1603 |           0 |                0      |            26.8861 |            9.1055 |                   5 |        0.4219 |         0.6414 |         0.7869 |         0.8397 |          0.8397 |
| hier_degraded    |        474 | 0.1582 |           0 |                0.0021 |            27.0316 |            9.2789 |                   5 |        0.4304 |         0.6498 |         0.789  |         0.8397 |          0.8397 |
| combo_hier_topk  |        474 | 0.1857 |           0 |                0.0042 |            31.6118 |           10.8958 |                   7 |        0.3544 |         0.5717 |         0.7405 |         0.8101 |          0.8101 |
| combo_hier_m0    |        474 | 0.2743 |           0 |                0.0063 |            42.8333 |           12.7361 |                   9 |        0.2637 |         0.4684 |         0.6456 |         0.7194 |          0.7194 |
| combo_m0_topk    |        474 | 0.4177 |           0 |                0.0274 |            65.7046 |           22.1445 |                  26 |        0.1224 |         0.2152 |         0.346  |         0.5549 |          0.5549 |

## table_paired_differences

| A        | B               |   mean_capped_diff_A_minus_B |    ci_lo |    ci_hi | reading                                    |
|:---------|:----------------|-----------------------------:|---------:|---------:|:-------------------------------------------|
| hier_ssm | indep_ssm       |                      -0.1772 |  -2.8693 |   2.7094 | negative favours A (faster / fewer misses) |
| hier_ssm | pooled_ssm      |                     -29.0063 | -33.7786 | -24.4535 | negative favours A (faster / fewer misses) |
| hier_ssm | topk_cusum      |                     -25.8418 | -28.9476 | -22.8855 | negative favours A (faster / fewer misses) |
| hier_ssm | hier_no_persist |                     -47.0422 | -51.7764 | -42.3897 | negative favours A (faster / fewer misses) |
| hier_ssm | hier_rank0      |                     -43.9895 | -48.7429 | -39.1    | negative favours A (faster / fewer misses) |
| hier_ssm | hier_white      |                      -6.2743 |  -8.8104 |  -3.6959 | negative favours A (faster / fewer misses) |
| hier_ssm | hier_degraded   |                       0.097  |  -1.7682 |   2.0169 | negative favours A (faster / fewer misses) |

## table_localization

| method           |   top3_recall |   cut_precision |   cut_recall |   cut_fdp |
|:-----------------|--------------:|----------------:|-------------:|----------:|
| adj_cusum        |        0.9276 |          0.7004 |       0.9062 |    0.2996 |
| adj_ewma         |        0.9233 |          0.6996 |       0.907  |    0.3004 |
| hier_arwhite     |        0.9466 |          0.7194 |       0.9283 |    0.2806 |
| hier_degraded    |        0.9529 |          0.7143 |       0.9238 |    0.2857 |
| hier_huber       |        0.9466 |          0.719  |       0.9276 |    0.281  |
| hier_no_persist  |        0.6343 |          0.5549 |       0.69   |    0.4451 |
| hier_rank0       |        0.9451 |          0.7194 |       0.9271 |    0.2806 |
| hier_ssm         |        0.9466 |          0.7194 |       0.9283 |    0.2806 |
| hier_white       |        0.9409 |          0.7143 |       0.9226 |    0.2857 |
| indep_ssm        |        0.9487 |          0.7122 |       0.9219 |    0.2878 |
| matched_contrast |        0.7187 |          0.5831 |       0.7478 |    0.4169 |
| pooled_ssm       |        0.5084 |          0.4574 |       0.5346 |    0.5426 |
| topk_cusum       |        0.9276 |          0.7004 |       0.9062 |    0.2996 |

## table_brier

| method          |   brier |
|:----------------|--------:|
| hier_arwhite    |  0.0311 |
| hier_degraded   |  0.0331 |
| hier_huber      |  0.0313 |
| hier_no_persist |  0.0625 |
| hier_rank0      |  0.0657 |
| hier_ssm        |  0.0311 |
| hier_white      |  0.0336 |
| indep_ssm       |  0.0524 |
| pooled_ssm      |  0.0529 |

## table_flicker

| method           | harm   |   reversals |   time_paused |
|:-----------------|:-------|------------:|--------------:|
| adj_cusum        | False  |       0.048 |         1.474 |
| adj_cusum        | True   |       0.638 |        35.39  |
| adj_ewma         | False  |       0.078 |         1.25  |
| adj_ewma         | True   |       1.096 |        20.426 |
| combo_hier_m0    | False  |       0.036 |         0.388 |
| combo_hier_m0    | True   |       1.378 |        37.622 |
| combo_hier_topk  | False  |       0.046 |         1.644 |
| combo_hier_topk  | True   |       1.034 |        77.84  |
| combo_m0_topk    | False  |       0.052 |         1.03  |
| combo_m0_topk    | True   |       0.688 |        49.812 |
| hier_arwhite     | False  |       0.052 |         1.26  |
| hier_arwhite     | True   |       1.582 |        53.1   |
| hier_degraded    | False  |       0.066 |         1.672 |
| hier_degraded    | True   |       1.588 |        52.888 |
| hier_huber       | False  |       0.04  |         1.116 |
| hier_huber       | True   |       1.594 |        52.536 |
| hier_no_persist  | False  |       0.066 |         0.216 |
| hier_no_persist  | True   |       0.898 |        10.16  |
| hier_rank0       | False  |       0.044 |         0.982 |
| hier_rank0       | True   |       0.81  |        27.792 |
| hier_ssm         | False  |       0.052 |         1.26  |
| hier_ssm         | True   |       1.582 |        53.1   |
| hier_white       | False  |       0.064 |         1.396 |
| hier_white       | True   |       1.538 |        43.234 |
| indep_ssm        | False  |       0.08  |         2.176 |
| indep_ssm        | True   |       1.622 |        57.79  |
| matched_contrast | False  |       0.058 |         0.232 |
| matched_contrast | True   |       1.086 |        11.62  |
| pooled_ssm       | False  |       0.072 |         0.728 |
| pooled_ssm       | True   |       1.068 |        29.876 |
| topk_cusum       | False  |       0.04  |         1.74  |
| topk_cusum       | True   |       1.08  |        56.52  |

## table_transient

| method           |   alarm_rate |
|:-----------------|-------------:|
| adj_cusum        |       0      |
| adj_ewma         |       0.0385 |
| combo_hier_m0    |       0.0769 |
| combo_hier_topk  |       0.1538 |
| combo_m0_topk    |       0.0385 |
| hier_arwhite     |       0.3462 |
| hier_degraded    |       0.2308 |
| hier_huber       |       0.3846 |
| hier_no_persist  |       0.0769 |
| hier_rank0       |       0.1538 |
| hier_ssm         |       0.3462 |
| hier_white       |       0.1538 |
| indep_ssm        |       0.2308 |
| matched_contrast |       0.0385 |
| pooled_ssm       |       0.3077 |
| topk_cusum       |       0      |