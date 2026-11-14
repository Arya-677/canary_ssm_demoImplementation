# Results (generated from CSVs; interpret per handbook Section 15)

**Regime:** `plain`  

Simulation results under stated assumptions only. Losing methods stay in the tables.

**Calibration gate: FAIL** (167/168 method x family cells ok; 168 have n>=2000). Delay/power comparisons are valid only for methods inside this gate.


## table_null_rates

| method           |   alerts |   n_null |   rate |   ci_lo |   ci_hi | pass_contains_5pct   | pass_upper_le_8pct   | above_target   | gate_evaluable   | is_oracle   | role   |
|:-----------------|---------:|---------:|-------:|--------:|--------:|:---------------------|:---------------------|:---------------|:-----------------|:------------|:-------|
| adj_cusum        |       53 |     1000 |  0.053 |  0.0399 |  0.0688 | True                 | True                 | False          | True             | False       | method |
| adj_ewma         |       47 |     1000 |  0.047 |  0.0347 |  0.062  | True                 | True                 | False          | True             | False       | method |
| ar_cusum         |       52 |     1000 |  0.052 |  0.0391 |  0.0676 | True                 | True                 | False          | True             | False       | method |
| bocpd            |       52 |     1000 |  0.052 |  0.0391 |  0.0676 | True                 | True                 | False          | True             | False       | method |
| combo_hier_m0    |       39 |     1000 |  0.039 |  0.0279 |  0.0529 | True                 | True                 | False          | True             | False       | method |
| combo_hier_topk  |       51 |     1000 |  0.051 |  0.0382 |  0.0665 | True                 | True                 | False          | True             | False       | method |
| combo_m0_topk    |       57 |     1000 |  0.057 |  0.0435 |  0.0732 | True                 | True                 | False          | True             | False       | method |
| glr_window       |       52 |     1000 |  0.052 |  0.0391 |  0.0676 | True                 | True                 | False          | True             | False       | method |
| hier_arwhite     |       38 |     1000 |  0.038 |  0.027  |  0.0518 | True                 | True                 | False          | True             | False       | method |
| hier_degraded    |       34 |     1000 |  0.034 |  0.0237 |  0.0472 | False                | True                 | False          | True             | False       | method |
| hier_huber       |       43 |     1000 |  0.043 |  0.0313 |  0.0575 | True                 | True                 | False          | True             | False       | method |
| hier_no_persist  |       56 |     1000 |  0.056 |  0.0426 |  0.0721 | True                 | True                 | False          | True             | False       | method |
| hier_rank0       |       56 |     1000 |  0.056 |  0.0426 |  0.0721 | True                 | True                 | False          | True             | False       | method |
| hier_rw          |       42 |     1000 |  0.042 |  0.0304 |  0.0564 | True                 | True                 | False          | True             | False       | method |
| hier_ssm         |       38 |     1000 |  0.038 |  0.027  |  0.0518 | True                 | True                 | False          | True             | False       | method |
| hier_white       |       35 |     1000 |  0.035 |  0.0245 |  0.0483 | False                | True                 | False          | True             | False       | method |
| indep_ssm        |       49 |     1000 |  0.049 |  0.0365 |  0.0643 | True                 | True                 | False          | True             | False       | method |
| matched_contrast |       48 |     1000 |  0.048 |  0.0356 |  0.0631 | True                 | True                 | False          | True             | False       | method |
| msprt            |       56 |     1000 |  0.056 |  0.0426 |  0.0721 | True                 | True                 | False          | True             | False       | method |
| mw_judge         |       58 |     1000 |  0.058 |  0.0443 |  0.0743 | True                 | True                 | False          | True             | False       | method |
| pooled_ssm       |       49 |     1000 |  0.049 |  0.0365 |  0.0643 | True                 | True                 | False          | True             | False       | method |
| sparse_mix_glr   |       37 |     1000 |  0.037 |  0.0262 |  0.0506 | True                 | True                 | False          | True             | False       | method |
| topk_cusum       |       46 |     1000 |  0.046 |  0.0339 |  0.0609 | True                 | True                 | False          | True             | False       | method |
| wmean            |       48 |     1000 |  0.048 |  0.0356 |  0.0631 | True                 | True                 | False          | True             | False       | method |

## table_null_by_family

| family          | method           |   alerts |   n_null |   rate |   ci_lo |   ci_hi | pass_contains_5pct   | pass_upper_le_8pct   | above_target   | gate_evaluable   |
|:----------------|:-----------------|---------:|---------:|-------:|--------:|--------:|:---------------------|:---------------------|:---------------|:-----------------|
| S1_sparse       | adj_cusum        |       11 |      253 | 0.0435 |  0.0219 |  0.0765 | True                 | True                 | False          | False            |
| S1_sparse       | adj_ewma         |       10 |      253 | 0.0395 |  0.0191 |  0.0715 | True                 | True                 | False          | False            |
| S1_sparse       | ar_cusum         |       10 |      253 | 0.0395 |  0.0191 |  0.0715 | True                 | True                 | False          | False            |
| S1_sparse       | bocpd            |       12 |      253 | 0.0474 |  0.0247 |  0.0814 | True                 | False                | False          | False            |
| S1_sparse       | combo_hier_m0    |       14 |      253 | 0.0553 |  0.0306 |  0.0911 | True                 | False                | False          | False            |
| S1_sparse       | combo_hier_topk  |       13 |      253 | 0.0514 |  0.0276 |  0.0863 | True                 | False                | False          | False            |
| S1_sparse       | combo_m0_topk    |       15 |      253 | 0.0593 |  0.0336 |  0.0959 | True                 | False                | False          | False            |
| S1_sparse       | glr_window       |       15 |      253 | 0.0593 |  0.0336 |  0.0959 | True                 | False                | False          | False            |
| S1_sparse       | hier_arwhite     |        8 |      253 | 0.0316 |  0.0137 |  0.0614 | True                 | True                 | False          | False            |
| S1_sparse       | hier_degraded    |        9 |      253 | 0.0356 |  0.0164 |  0.0665 | True                 | True                 | False          | False            |
| S1_sparse       | hier_huber       |        9 |      253 | 0.0356 |  0.0164 |  0.0665 | True                 | True                 | False          | False            |
| S1_sparse       | hier_no_persist  |       18 |      253 | 0.0711 |  0.0427 |  0.1101 | True                 | False                | False          | False            |
| S1_sparse       | hier_rank0       |       11 |      253 | 0.0435 |  0.0219 |  0.0765 | True                 | True                 | False          | False            |
| S1_sparse       | hier_rw          |       11 |      253 | 0.0435 |  0.0219 |  0.0765 | True                 | True                 | False          | False            |
| S1_sparse       | hier_ssm         |        8 |      253 | 0.0316 |  0.0137 |  0.0614 | True                 | True                 | False          | False            |
| S1_sparse       | hier_white       |        9 |      253 | 0.0356 |  0.0164 |  0.0665 | True                 | True                 | False          | False            |
| S1_sparse       | indep_ssm        |       12 |      253 | 0.0474 |  0.0247 |  0.0814 | True                 | False                | False          | False            |
| S1_sparse       | matched_contrast |       10 |      253 | 0.0395 |  0.0191 |  0.0715 | True                 | True                 | False          | False            |
| S1_sparse       | msprt            |       10 |      253 | 0.0395 |  0.0191 |  0.0715 | True                 | True                 | False          | False            |
| S1_sparse       | mw_judge         |       11 |      253 | 0.0435 |  0.0219 |  0.0765 | True                 | True                 | False          | False            |
| S1_sparse       | pooled_ssm       |       10 |      253 | 0.0395 |  0.0191 |  0.0715 | True                 | True                 | False          | False            |
| S1_sparse       | sparse_mix_glr   |        8 |      253 | 0.0316 |  0.0137 |  0.0614 | True                 | True                 | False          | False            |
| S1_sparse       | topk_cusum       |       11 |      253 | 0.0435 |  0.0219 |  0.0765 | True                 | True                 | False          | False            |
| S1_sparse       | wmean            |        9 |      253 | 0.0356 |  0.0164 |  0.0665 | True                 | True                 | False          | False            |
| S2_class_wide   | adj_cusum        |       12 |      243 | 0.0494 |  0.0258 |  0.0847 | True                 | False                | False          | False            |
| S2_class_wide   | adj_ewma         |       12 |      243 | 0.0494 |  0.0258 |  0.0847 | True                 | False                | False          | False            |
| S2_class_wide   | ar_cusum         |       13 |      243 | 0.0535 |  0.0288 |  0.0897 | True                 | False                | False          | False            |
| S2_class_wide   | bocpd            |       11 |      243 | 0.0453 |  0.0228 |  0.0796 | True                 | True                 | False          | False            |
| S2_class_wide   | combo_hier_m0    |       10 |      243 | 0.0412 |  0.0199 |  0.0744 | True                 | True                 | False          | False            |
| S2_class_wide   | combo_hier_topk  |       10 |      243 | 0.0412 |  0.0199 |  0.0744 | True                 | True                 | False          | False            |
| S2_class_wide   | combo_m0_topk    |       13 |      243 | 0.0535 |  0.0288 |  0.0897 | True                 | False                | False          | False            |
| S2_class_wide   | glr_window       |       10 |      243 | 0.0412 |  0.0199 |  0.0744 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_arwhite     |        9 |      243 | 0.037  |  0.0171 |  0.0691 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_degraded    |        7 |      243 | 0.0288 |  0.0117 |  0.0584 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_huber       |       13 |      243 | 0.0535 |  0.0288 |  0.0897 | True                 | False                | False          | False            |
| S2_class_wide   | hier_no_persist  |        8 |      243 | 0.0329 |  0.0143 |  0.0638 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_rank0       |       14 |      243 | 0.0576 |  0.0319 |  0.0948 | True                 | False                | False          | False            |
| S2_class_wide   | hier_rw          |       11 |      243 | 0.0453 |  0.0228 |  0.0796 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_ssm         |        9 |      243 | 0.037  |  0.0171 |  0.0691 | True                 | True                 | False          | False            |
| S2_class_wide   | hier_white       |        9 |      243 | 0.037  |  0.0171 |  0.0691 | True                 | True                 | False          | False            |
| S2_class_wide   | indep_ssm        |       18 |      243 | 0.0741 |  0.0445 |  0.1145 | True                 | False                | False          | False            |
| S2_class_wide   | matched_contrast |       14 |      243 | 0.0576 |  0.0319 |  0.0948 | True                 | False                | False          | False            |
| S2_class_wide   | msprt            |       16 |      243 | 0.0658 |  0.0381 |  0.1047 | True                 | False                | False          | False            |
| S2_class_wide   | mw_judge         |       12 |      243 | 0.0494 |  0.0258 |  0.0847 | True                 | False                | False          | False            |
| S2_class_wide   | pooled_ssm       |       14 |      243 | 0.0576 |  0.0319 |  0.0948 | True                 | False                | False          | False            |
| S2_class_wide   | sparse_mix_glr   |        7 |      243 | 0.0288 |  0.0117 |  0.0584 | True                 | True                 | False          | False            |
| S2_class_wide   | topk_cusum       |       10 |      243 | 0.0412 |  0.0199 |  0.0744 | True                 | True                 | False          | False            |
| S2_class_wide   | wmean            |       10 |      243 | 0.0412 |  0.0199 |  0.0744 | True                 | True                 | False          | False            |
| S3_broad        | adj_cusum        |        7 |      104 | 0.0673 |  0.0275 |  0.1338 | True                 | False                | False          | False            |
| S3_broad        | adj_ewma         |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | ar_cusum         |        7 |      104 | 0.0673 |  0.0275 |  0.1338 | True                 | False                | False          | False            |
| S3_broad        | bocpd            |        6 |      104 | 0.0577 |  0.0215 |  0.1213 | True                 | False                | False          | False            |
| S3_broad        | combo_hier_m0    |        6 |      104 | 0.0577 |  0.0215 |  0.1213 | True                 | False                | False          | False            |
| S3_broad        | combo_hier_topk  |        7 |      104 | 0.0673 |  0.0275 |  0.1338 | True                 | False                | False          | False            |
| S3_broad        | combo_m0_topk    |        7 |      104 | 0.0673 |  0.0275 |  0.1338 | True                 | False                | False          | False            |
| S3_broad        | glr_window       |       11 |      104 | 0.1058 |  0.054  |  0.1814 | False                | False                | True           | False            |
| S3_broad        | hier_arwhite     |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | hier_degraded    |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | hier_huber       |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | hier_no_persist  |        9 |      104 | 0.0865 |  0.0403 |  0.1579 | True                 | False                | False          | False            |
| S3_broad        | hier_rank0       |        6 |      104 | 0.0577 |  0.0215 |  0.1213 | True                 | False                | False          | False            |
| S3_broad        | hier_rw          |        5 |      104 | 0.0481 |  0.0158 |  0.1086 | True                 | False                | False          | False            |
| S3_broad        | hier_ssm         |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | hier_white       |        3 |      104 | 0.0288 |  0.006  |  0.082  | True                 | False                | False          | False            |
| S3_broad        | indep_ssm        |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | matched_contrast |        8 |      104 | 0.0769 |  0.0338 |  0.146  | True                 | False                | False          | False            |
| S3_broad        | msprt            |        6 |      104 | 0.0577 |  0.0215 |  0.1213 | True                 | False                | False          | False            |
| S3_broad        | mw_judge         |        8 |      104 | 0.0769 |  0.0338 |  0.146  | True                 | False                | False          | False            |
| S3_broad        | pooled_ssm       |        4 |      104 | 0.0385 |  0.0106 |  0.0956 | True                 | False                | False          | False            |
| S3_broad        | sparse_mix_glr   |        9 |      104 | 0.0865 |  0.0403 |  0.1579 | True                 | False                | False          | False            |
| S3_broad        | topk_cusum       |        7 |      104 | 0.0673 |  0.0275 |  0.1338 | True                 | False                | False          | False            |
| S3_broad        | wmean            |        5 |      104 | 0.0481 |  0.0158 |  0.1086 | True                 | False                | False          | False            |
| S4_weak_sparse  | adj_cusum        |        3 |      122 | 0.0246 |  0.0051 |  0.0702 | True                 | True                 | False          | False            |
| S4_weak_sparse  | adj_ewma         |        2 |      122 | 0.0164 |  0.002  |  0.058  | True                 | True                 | False          | False            |
| S4_weak_sparse  | ar_cusum         |        3 |      122 | 0.0246 |  0.0051 |  0.0702 | True                 | True                 | False          | False            |
| S4_weak_sparse  | bocpd            |        7 |      122 | 0.0574 |  0.0234 |  0.1146 | True                 | False                | False          | False            |
| S4_weak_sparse  | combo_hier_m0    |        2 |      122 | 0.0164 |  0.002  |  0.058  | True                 | True                 | False          | False            |
| S4_weak_sparse  | combo_hier_topk  |        1 |      122 | 0.0082 |  0.0002 |  0.0448 | False                | True                 | False          | False            |
| S4_weak_sparse  | combo_m0_topk    |        3 |      122 | 0.0246 |  0.0051 |  0.0702 | True                 | True                 | False          | False            |
| S4_weak_sparse  | glr_window       |        1 |      122 | 0.0082 |  0.0002 |  0.0448 | False                | True                 | False          | False            |
| S4_weak_sparse  | hier_arwhite     |        3 |      122 | 0.0246 |  0.0051 |  0.0702 | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_degraded    |        2 |      122 | 0.0164 |  0.002  |  0.058  | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_huber       |        2 |      122 | 0.0164 |  0.002  |  0.058  | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_no_persist  |        4 |      122 | 0.0328 |  0.009  |  0.0818 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_rank0       |        4 |      122 | 0.0328 |  0.009  |  0.0818 | True                 | False                | False          | False            |
| S4_weak_sparse  | hier_rw          |        2 |      122 | 0.0164 |  0.002  |  0.058  | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_ssm         |        3 |      122 | 0.0246 |  0.0051 |  0.0702 | True                 | True                 | False          | False            |
| S4_weak_sparse  | hier_white       |        1 |      122 | 0.0082 |  0.0002 |  0.0448 | False                | True                 | False          | False            |
| S4_weak_sparse  | indep_ssm        |        4 |      122 | 0.0328 |  0.009  |  0.0818 | True                 | False                | False          | False            |
| S4_weak_sparse  | matched_contrast |        5 |      122 | 0.041  |  0.0134 |  0.0931 | True                 | False                | False          | False            |
| S4_weak_sparse  | msprt            |        6 |      122 | 0.0492 |  0.0183 |  0.104  | True                 | False                | False          | False            |
| S4_weak_sparse  | mw_judge         |       11 |      122 | 0.0902 |  0.0459 |  0.1556 | True                 | False                | False          | False            |
| S4_weak_sparse  | pooled_ssm       |        6 |      122 | 0.0492 |  0.0183 |  0.104  | True                 | False                | False          | False            |
| S4_weak_sparse  | sparse_mix_glr   |        2 |      122 | 0.0164 |  0.002  |  0.058  | True                 | True                 | False          | False            |
| S4_weak_sparse  | topk_cusum       |        1 |      122 | 0.0082 |  0.0002 |  0.0448 | False                | True                 | False          | False            |
| S4_weak_sparse  | wmean            |        5 |      122 | 0.041  |  0.0134 |  0.0931 | True                 | False                | False          | False            |
| S5_label_errors | adj_cusum        |        8 |      124 | 0.0645 |  0.0283 |  0.1232 | True                 | False                | False          | False            |
| S5_label_errors | adj_ewma         |        5 |      124 | 0.0403 |  0.0132 |  0.0916 | True                 | False                | False          | False            |
| S5_label_errors | ar_cusum         |        7 |      124 | 0.0565 |  0.023  |  0.1129 | True                 | False                | False          | False            |
| S5_label_errors | bocpd            |        7 |      124 | 0.0565 |  0.023  |  0.1129 | True                 | False                | False          | False            |
| S5_label_errors | combo_hier_m0    |        4 |      124 | 0.0323 |  0.0089 |  0.0805 | True                 | False                | False          | False            |
| S5_label_errors | combo_hier_topk  |        6 |      124 | 0.0484 |  0.018  |  0.1023 | True                 | False                | False          | False            |
| S5_label_errors | combo_m0_topk    |        8 |      124 | 0.0645 |  0.0283 |  0.1232 | True                 | False                | False          | False            |
| S5_label_errors | glr_window       |        6 |      124 | 0.0484 |  0.018  |  0.1023 | True                 | False                | False          | False            |
| S5_label_errors | hier_arwhite     |        7 |      124 | 0.0565 |  0.023  |  0.1129 | True                 | False                | False          | False            |
| S5_label_errors | hier_degraded    |        7 |      124 | 0.0565 |  0.023  |  0.1129 | True                 | False                | False          | False            |
| S5_label_errors | hier_huber       |        8 |      124 | 0.0645 |  0.0283 |  0.1232 | True                 | False                | False          | False            |
| S5_label_errors | hier_no_persist  |        7 |      124 | 0.0565 |  0.023  |  0.1129 | True                 | False                | False          | False            |
| S5_label_errors | hier_rank0       |       11 |      124 | 0.0887 |  0.0451 |  0.1532 | True                 | False                | False          | False            |
| S5_label_errors | hier_rw          |        5 |      124 | 0.0403 |  0.0132 |  0.0916 | True                 | False                | False          | False            |
| S5_label_errors | hier_ssm         |        7 |      124 | 0.0565 |  0.023  |  0.1129 | True                 | False                | False          | False            |
| S5_label_errors | hier_white       |        6 |      124 | 0.0484 |  0.018  |  0.1023 | True                 | False                | False          | False            |
| S5_label_errors | indep_ssm        |        8 |      124 | 0.0645 |  0.0283 |  0.1232 | True                 | False                | False          | False            |
| S5_label_errors | matched_contrast |        6 |      124 | 0.0484 |  0.018  |  0.1023 | True                 | False                | False          | False            |
| S5_label_errors | msprt            |        9 |      124 | 0.0726 |  0.0337 |  0.1333 | True                 | False                | False          | False            |
| S5_label_errors | mw_judge         |        5 |      124 | 0.0403 |  0.0132 |  0.0916 | True                 | False                | False          | False            |
| S5_label_errors | pooled_ssm       |        5 |      124 | 0.0403 |  0.0132 |  0.0916 | True                 | False                | False          | False            |
| S5_label_errors | sparse_mix_glr   |        4 |      124 | 0.0323 |  0.0089 |  0.0805 | True                 | False                | False          | False            |
| S5_label_errors | topk_cusum       |        5 |      124 | 0.0403 |  0.0132 |  0.0916 | True                 | False                | False          | False            |
| S5_label_errors | wmean            |        8 |      124 | 0.0645 |  0.0283 |  0.1232 | True                 | False                | False          | False            |
| single_canary   | adj_cusum        |        8 |      113 | 0.0708 |  0.0311 |  0.1347 | True                 | False                | False          | False            |
| single_canary   | adj_ewma         |        9 |      113 | 0.0796 |  0.0371 |  0.1458 | True                 | False                | False          | False            |
| single_canary   | ar_cusum         |        8 |      113 | 0.0708 |  0.0311 |  0.1347 | True                 | False                | False          | False            |
| single_canary   | bocpd            |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | combo_hier_m0    |        2 |      113 | 0.0177 |  0.0022 |  0.0625 | True                 | True                 | False          | False            |
| single_canary   | combo_hier_topk  |        9 |      113 | 0.0796 |  0.0371 |  0.1458 | True                 | False                | False          | False            |
| single_canary   | combo_m0_topk    |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | glr_window       |        4 |      113 | 0.0354 |  0.0097 |  0.0882 | True                 | False                | False          | False            |
| single_canary   | hier_arwhite     |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | hier_degraded    |        4 |      113 | 0.0354 |  0.0097 |  0.0882 | True                 | False                | False          | False            |
| single_canary   | hier_huber       |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | hier_no_persist  |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | hier_rank0       |       10 |      113 | 0.0885 |  0.0433 |  0.1567 | True                 | False                | False          | False            |
| single_canary   | hier_rw          |        7 |      113 | 0.0619 |  0.0253 |  0.1235 | True                 | False                | False          | False            |
| single_canary   | hier_ssm         |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | hier_white       |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | indep_ssm        |        3 |      113 | 0.0265 |  0.0055 |  0.0756 | True                 | True                 | False          | False            |
| single_canary   | matched_contrast |        4 |      113 | 0.0354 |  0.0097 |  0.0882 | True                 | False                | False          | False            |
| single_canary   | msprt            |        7 |      113 | 0.0619 |  0.0253 |  0.1235 | True                 | False                | False          | False            |
| single_canary   | mw_judge         |        5 |      113 | 0.0442 |  0.0145 |  0.1002 | True                 | False                | False          | False            |
| single_canary   | pooled_ssm       |        5 |      113 | 0.0442 |  0.0145 |  0.1002 | True                 | False                | False          | False            |
| single_canary   | sparse_mix_glr   |        3 |      113 | 0.0265 |  0.0055 |  0.0756 | True                 | True                 | False          | False            |
| single_canary   | topk_cusum       |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| single_canary   | wmean            |        6 |      113 | 0.0531 |  0.0197 |  0.112  | True                 | False                | False          | False            |
| transient       | adj_cusum        |        4 |       41 | 0.0976 |  0.0272 |  0.2313 | True                 | False                | False          | False            |
| transient       | adj_ewma         |        5 |       41 | 0.122  |  0.0408 |  0.262  | True                 | False                | False          | False            |
| transient       | ar_cusum         |        4 |       41 | 0.0976 |  0.0272 |  0.2313 | True                 | False                | False          | False            |
| transient       | bocpd            |        3 |       41 | 0.0732 |  0.0154 |  0.1992 | True                 | False                | False          | False            |
| transient       | combo_hier_m0    |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | combo_hier_topk  |        5 |       41 | 0.122  |  0.0408 |  0.262  | True                 | False                | False          | False            |
| transient       | combo_m0_topk    |        5 |       41 | 0.122  |  0.0408 |  0.262  | True                 | False                | False          | False            |
| transient       | glr_window       |        5 |       41 | 0.122  |  0.0408 |  0.262  | True                 | False                | False          | False            |
| transient       | hier_arwhite     |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | hier_degraded    |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | hier_huber       |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | hier_no_persist  |        4 |       41 | 0.0976 |  0.0272 |  0.2313 | True                 | False                | False          | False            |
| transient       | hier_rank0       |        0 |       41 | 0      |  0      |  0.086  | True                 | False                | False          | False            |
| transient       | hier_rw          |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | hier_ssm         |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | hier_white       |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | indep_ssm        |        0 |       41 | 0      |  0      |  0.086  | True                 | False                | False          | False            |
| transient       | matched_contrast |        1 |       41 | 0.0244 |  0.0006 |  0.1286 | True                 | False                | False          | False            |
| transient       | msprt            |        2 |       41 | 0.0488 |  0.006  |  0.1653 | True                 | False                | False          | False            |
| transient       | mw_judge         |        6 |       41 | 0.1463 |  0.0557 |  0.2917 | False                | False                | True           | False            |
| transient       | pooled_ssm       |        5 |       41 | 0.122  |  0.0408 |  0.262  | True                 | False                | False          | False            |
| transient       | sparse_mix_glr   |        4 |       41 | 0.0976 |  0.0272 |  0.2313 | True                 | False                | False          | False            |
| transient       | topk_cusum       |        6 |       41 | 0.1463 |  0.0557 |  0.2917 | False                | False                | True           | False            |
| transient       | wmean            |        5 |       41 | 0.122  |  0.0408 |  0.262  | True                 | False                | False          | False            |

## table_abstention

| family          | method           |   eligible_fraction |
|:----------------|:-----------------|--------------------:|
| S1_sparse       | adj_cusum        |                   1 |
| S1_sparse       | adj_ewma         |                   1 |
| S1_sparse       | ar_cusum         |                   1 |
| S1_sparse       | bocpd            |                   1 |
| S1_sparse       | combo_hier_m0    |                   1 |
| S1_sparse       | combo_hier_topk  |                   1 |
| S1_sparse       | combo_m0_topk    |                   1 |
| S1_sparse       | glr_window       |                   1 |
| S1_sparse       | hier_arwhite     |                   1 |
| S1_sparse       | hier_degraded    |                   1 |
| S1_sparse       | hier_huber       |                   1 |
| S1_sparse       | hier_no_persist  |                   1 |
| S1_sparse       | hier_rank0       |                   1 |
| S1_sparse       | hier_rw          |                   1 |
| S1_sparse       | hier_ssm         |                   1 |
| S1_sparse       | hier_white       |                   1 |
| S1_sparse       | indep_ssm        |                   1 |
| S1_sparse       | matched_contrast |                   1 |
| S1_sparse       | msprt            |                   1 |
| S1_sparse       | mw_judge         |                   1 |
| S1_sparse       | pooled_ssm       |                   1 |
| S1_sparse       | sparse_mix_glr   |                   1 |
| S1_sparse       | topk_cusum       |                   1 |
| S1_sparse       | wmean            |                   1 |
| S2_class_wide   | adj_cusum        |                   1 |
| S2_class_wide   | adj_ewma         |                   1 |
| S2_class_wide   | ar_cusum         |                   1 |
| S2_class_wide   | bocpd            |                   1 |
| S2_class_wide   | combo_hier_m0    |                   1 |
| S2_class_wide   | combo_hier_topk  |                   1 |
| S2_class_wide   | combo_m0_topk    |                   1 |
| S2_class_wide   | glr_window       |                   1 |
| S2_class_wide   | hier_arwhite     |                   1 |
| S2_class_wide   | hier_degraded    |                   1 |
| S2_class_wide   | hier_huber       |                   1 |
| S2_class_wide   | hier_no_persist  |                   1 |
| S2_class_wide   | hier_rank0       |                   1 |
| S2_class_wide   | hier_rw          |                   1 |
| S2_class_wide   | hier_ssm         |                   1 |
| S2_class_wide   | hier_white       |                   1 |
| S2_class_wide   | indep_ssm        |                   1 |
| S2_class_wide   | matched_contrast |                   1 |
| S2_class_wide   | msprt            |                   1 |
| S2_class_wide   | mw_judge         |                   1 |
| S2_class_wide   | pooled_ssm       |                   1 |
| S2_class_wide   | sparse_mix_glr   |                   1 |
| S2_class_wide   | topk_cusum       |                   1 |
| S2_class_wide   | wmean            |                   1 |
| S3_broad        | adj_cusum        |                   1 |
| S3_broad        | adj_ewma         |                   1 |
| S3_broad        | ar_cusum         |                   1 |
| S3_broad        | bocpd            |                   1 |
| S3_broad        | combo_hier_m0    |                   1 |
| S3_broad        | combo_hier_topk  |                   1 |
| S3_broad        | combo_m0_topk    |                   1 |
| S3_broad        | glr_window       |                   1 |
| S3_broad        | hier_arwhite     |                   1 |
| S3_broad        | hier_degraded    |                   1 |
| S3_broad        | hier_huber       |                   1 |
| S3_broad        | hier_no_persist  |                   1 |
| S3_broad        | hier_rank0       |                   1 |
| S3_broad        | hier_rw          |                   1 |
| S3_broad        | hier_ssm         |                   1 |
| S3_broad        | hier_white       |                   1 |
| S3_broad        | indep_ssm        |                   1 |
| S3_broad        | matched_contrast |                   1 |
| S3_broad        | msprt            |                   1 |
| S3_broad        | mw_judge         |                   1 |
| S3_broad        | pooled_ssm       |                   1 |
| S3_broad        | sparse_mix_glr   |                   1 |
| S3_broad        | topk_cusum       |                   1 |
| S3_broad        | wmean            |                   1 |
| S4_weak_sparse  | adj_cusum        |                   1 |
| S4_weak_sparse  | adj_ewma         |                   1 |
| S4_weak_sparse  | ar_cusum         |                   1 |
| S4_weak_sparse  | bocpd            |                   1 |
| S4_weak_sparse  | combo_hier_m0    |                   1 |
| S4_weak_sparse  | combo_hier_topk  |                   1 |
| S4_weak_sparse  | combo_m0_topk    |                   1 |
| S4_weak_sparse  | glr_window       |                   1 |
| S4_weak_sparse  | hier_arwhite     |                   1 |
| S4_weak_sparse  | hier_degraded    |                   1 |
| S4_weak_sparse  | hier_huber       |                   1 |
| S4_weak_sparse  | hier_no_persist  |                   1 |
| S4_weak_sparse  | hier_rank0       |                   1 |
| S4_weak_sparse  | hier_rw          |                   1 |
| S4_weak_sparse  | hier_ssm         |                   1 |
| S4_weak_sparse  | hier_white       |                   1 |
| S4_weak_sparse  | indep_ssm        |                   1 |
| S4_weak_sparse  | matched_contrast |                   1 |
| S4_weak_sparse  | msprt            |                   1 |
| S4_weak_sparse  | mw_judge         |                   1 |
| S4_weak_sparse  | pooled_ssm       |                   1 |
| S4_weak_sparse  | sparse_mix_glr   |                   1 |
| S4_weak_sparse  | topk_cusum       |                   1 |
| S4_weak_sparse  | wmean            |                   1 |
| S5_label_errors | adj_cusum        |                   1 |
| S5_label_errors | adj_ewma         |                   1 |
| S5_label_errors | ar_cusum         |                   1 |
| S5_label_errors | bocpd            |                   1 |
| S5_label_errors | combo_hier_m0    |                   1 |
| S5_label_errors | combo_hier_topk  |                   1 |
| S5_label_errors | combo_m0_topk    |                   1 |
| S5_label_errors | glr_window       |                   1 |
| S5_label_errors | hier_arwhite     |                   1 |
| S5_label_errors | hier_degraded    |                   1 |
| S5_label_errors | hier_huber       |                   1 |
| S5_label_errors | hier_no_persist  |                   1 |
| S5_label_errors | hier_rank0       |                   1 |
| S5_label_errors | hier_rw          |                   1 |
| S5_label_errors | hier_ssm         |                   1 |
| S5_label_errors | hier_white       |                   1 |
| S5_label_errors | indep_ssm        |                   1 |
| S5_label_errors | matched_contrast |                   1 |
| S5_label_errors | msprt            |                   1 |
| S5_label_errors | mw_judge         |                   1 |
| S5_label_errors | pooled_ssm       |                   1 |
| S5_label_errors | sparse_mix_glr   |                   1 |
| S5_label_errors | topk_cusum       |                   1 |
| S5_label_errors | wmean            |                   1 |
| single_canary   | adj_cusum        |                   1 |
| single_canary   | adj_ewma         |                   1 |
| single_canary   | ar_cusum         |                   1 |
| single_canary   | bocpd            |                   1 |
| single_canary   | combo_hier_m0    |                   1 |
| single_canary   | combo_hier_topk  |                   1 |
| single_canary   | combo_m0_topk    |                   1 |
| single_canary   | glr_window       |                   1 |
| single_canary   | hier_arwhite     |                   1 |
| single_canary   | hier_degraded    |                   1 |
| single_canary   | hier_huber       |                   1 |
| single_canary   | hier_no_persist  |                   1 |
| single_canary   | hier_rank0       |                   1 |
| single_canary   | hier_rw          |                   1 |
| single_canary   | hier_ssm         |                   1 |
| single_canary   | hier_white       |                   1 |
| single_canary   | indep_ssm        |                   1 |
| single_canary   | matched_contrast |                   1 |
| single_canary   | msprt            |                   1 |
| single_canary   | mw_judge         |                   1 |
| single_canary   | pooled_ssm       |                   1 |
| single_canary   | sparse_mix_glr   |                   1 |
| single_canary   | topk_cusum       |                   1 |
| single_canary   | wmean            |                   1 |
| transient       | adj_cusum        |                   1 |
| transient       | adj_ewma         |                   1 |
| transient       | ar_cusum         |                   1 |
| transient       | bocpd            |                   1 |
| transient       | combo_hier_m0    |                   1 |
| transient       | combo_hier_topk  |                   1 |
| transient       | combo_m0_topk    |                   1 |
| transient       | glr_window       |                   1 |
| transient       | hier_arwhite     |                   1 |
| transient       | hier_degraded    |                   1 |
| transient       | hier_huber       |                   1 |
| transient       | hier_no_persist  |                   1 |
| transient       | hier_rank0       |                   1 |
| transient       | hier_rw          |                   1 |
| transient       | hier_ssm         |                   1 |
| transient       | hier_white       |                   1 |
| transient       | indep_ssm        |                   1 |
| transient       | matched_contrast |                   1 |
| transient       | msprt            |                   1 |
| transient       | mw_judge         |                   1 |
| transient       | pooled_ssm       |                   1 |
| transient       | sparse_mix_glr   |                   1 |
| transient       | topk_cusum       |                   1 |
| transient       | wmean            |                   1 |

## table_detection

| method           |   n_events |   miss |   premature |   late_after_recovery |   mean_capped_time |   cond_delay_mean |   cond_delay_median |   P_detect_5m |   P_detect_15m |   P_detect_30m |   P_detect_60m |   P_detect_120m | is_oracle   | role   |
|:-----------------|-----------:|-------:|------------:|----------------------:|-------------------:|------------------:|--------------------:|--------------:|---------------:|---------------:|---------------:|----------------:|:------------|:-------|
| adj_cusum        |        959 | 0.1554 |           0 |                0.0282 |            44.1627 |           27.1162 |                  26 |        0      |         0.0521 |         0.5401 |         0.8165 |          0.8165 | False       | method |
| adj_ewma         |        959 | 0.4025 |           0 |                0.0115 |            65.1366 |           26.3808 |                  26 |        0      |         0.0824 |         0.3764 |         0.586  |          0.586  | False       | method |
| ar_cusum         |        959 | 0.17   |           0 |                0.0271 |            45.7998 |           27.587  |                  27 |        0      |         0.0501 |         0.5151 |         0.8029 |          0.8029 | False       | method |
| bocpd            |        959 | 0.7967 |           0 |                0.048  |           106.105  |           30.5705 |                  31 |        0      |         0.0063 |         0.0751 |         0.1554 |          0.1554 | False       | method |
| combo_hier_m0    |        959 | 0.0751 |           0 |                0.001  |            17.8415 |            9.4244 |                   4 |        0.4797 |         0.6861 |         0.853  |         0.9239 |          0.9239 | False       | method |
| combo_hier_topk  |        959 | 0.0584 |           0 |                0.0042 |            18.0073 |           11.2002 |                   7 |        0.3806 |         0.6705 |         0.8665 |         0.9374 |          0.9374 | False       | method |
| combo_m0_topk    |        959 | 0.1491 |           0 |                0.0083 |            29.6225 |           12.7327 |                  10 |        0.3723 |         0.5016 |         0.7289 |         0.8425 |          0.8425 | False       | method |
| glr_window       |        959 | 0.123  |           0 |                0.0073 |            33.3785 |           20.3957 |                  19 |        0.0563 |         0.3107 |         0.708  |         0.8697 |          0.8697 | False       | method |
| hier_arwhite     |        959 | 0.0511 |           0 |                0.0031 |            15.5693 |            9.5821 |                   6 |        0.4692 |         0.7216 |         0.8874 |         0.9458 |          0.9458 | False       | method |
| hier_degraded    |        959 | 0.0553 |           0 |                0.0021 |            16.367  |           10.0619 |                   7 |        0.414  |         0.7216 |         0.8822 |         0.9426 |          0.9426 | False       | method |
| hier_huber       |        959 | 0.0511 |           0 |                0.0031 |            15.4181 |            9.4223 |                   6 |        0.4661 |         0.7351 |         0.8863 |         0.9458 |          0.9458 | False       | method |
| hier_no_persist  |        959 | 0.5391 |           0 |                0.0209 |            70.3879 |            7.2559 |                   0 |        0.3014 |         0.3441 |         0.4098 |         0.44   |          0.44   | False       | method |
| hier_rank0       |        959 | 0.4108 |           0 |                0.0083 |            58.2294 |           13.6481 |                  10 |        0.1762 |         0.3806 |         0.5089 |         0.5808 |          0.5808 | False       | method |
| hier_rw          |        959 | 0.0469 |           0 |                0.001  |            14.4484 |            9.1303 |                   5 |        0.4995 |         0.7424 |         0.8926 |         0.952  |          0.952  | False       | method |
| hier_ssm         |        959 | 0.0511 |           0 |                0.0031 |            15.5693 |            9.5821 |                   6 |        0.4692 |         0.7216 |         0.8874 |         0.9458 |          0.9458 | False       | method |
| hier_white       |        959 | 0.049  |           0 |                0.0042 |            18.074  |           12.3491 |                   9 |        0.2576 |         0.6715 |         0.8936 |         0.9468 |          0.9468 | False       | method |
| indep_ssm        |        959 | 0.0584 |           0 |                0.0031 |            18.1001 |           11.42   |                   9 |        0.2857 |         0.6851 |         0.8905 |         0.9385 |          0.9385 | False       | method |
| matched_contrast |        959 | 0.3775 |           0 |                0.0021 |            48.537  |            4.8185 |                   0 |        0.4984 |         0.5537 |         0.5777 |         0.6204 |          0.6204 | False       | method |
| msprt            |        959 | 0.1773 |           0 |                0.0313 |            43.6006 |           23.469  |                  23 |        0.0313 |         0.2117 |         0.5631 |         0.7914 |          0.7914 | False       | method |
| mw_judge         |        959 | 0.2753 |           0 |                0.0261 |            53.2117 |           24.403  |                  22 |        0.0031 |         0.1084 |         0.5057 |         0.6986 |          0.6986 | False       | method |
| pooled_ssm       |        959 | 0.2294 |           0 |                0.0073 |            34.999  |            8.6393 |                   4 |        0.4307 |         0.5912 |         0.7122 |         0.7633 |          0.7633 | False       | method |
| sparse_mix_glr   |        959 | 0.1053 |           0 |                0.0073 |            29.2763 |           17.7626 |                  16 |        0.1335 |         0.4254 |         0.7435 |         0.8874 |          0.8874 | False       | method |
| topk_cusum       |        959 | 0.1314 |           0 |                0.0104 |            32.0094 |           17.469  |                  15 |        0.0532 |         0.44   |         0.7466 |         0.8582 |          0.8582 | False       | method |
| wmean            |        959 | 0.0813 |           0 |                0.0042 |            26.2398 |           17.4732 |                  15 |        0.0438 |         0.4609 |         0.8029 |         0.9145 |          0.9145 | False       | method |

## table_paired_differences

| A        | B               |   mean_capped_diff_A_minus_B |    ci_lo |    ci_hi | reading                                    |
|:---------|:----------------|-----------------------------:|---------:|---------:|:-------------------------------------------|
| hier_ssm | indep_ssm       |                      -2.5308 |  -3.9763 |  -0.9906 | negative favours A (faster / fewer misses) |
| hier_ssm | pooled_ssm      |                     -19.4296 | -21.9761 | -16.9781 | negative favours A (faster / fewer misses) |
| hier_ssm | wmean           |                     -10.6705 | -12.3254 |  -9.026  | negative favours A (faster / fewer misses) |
| hier_ssm | hier_no_persist |                     -54.8186 | -58.0241 | -51.3594 | negative favours A (faster / fewer misses) |
| hier_ssm | hier_rw         |                       1.121  |   0.2344 |   2.0335 | negative favours A (faster / fewer misses) |
| hier_ssm | hier_rank0      |                     -42.6601 | -45.8541 | -39.479  | negative favours A (faster / fewer misses) |
| hier_ssm | hier_white      |                      -2.5047 |  -3.4359 |  -1.4993 | negative favours A (faster / fewer misses) |
| hier_ssm | hier_degraded   |                      -0.7977 |  -1.9083 |   0.335  | negative favours A (faster / fewer misses) |

## table_localization

| method           |   top3_recall |   cut_precision |   cut_recall |   cut_fdp |   host_auc | is_oracle   | role   |
|:-----------------|--------------:|----------------:|-------------:|----------:|-----------:|:------------|:-------|
| adj_cusum        |        0.9287 |          0.7732 |       0.8128 |    0.2268 |     0.9491 | False       | method |
| adj_ewma         |        0.9319 |          0.7126 |       0.9059 |    0.2874 |     0.9642 | False       | method |
| ar_cusum         |        0.9228 |          0.7651 |       0.8034 |    0.2349 |     0.9414 | False       | method |
| bocpd            |        0.8856 |          0.7367 |       0.7729 |    0.2633 |     0.923  | False       | method |
| glr_window       |        0.9291 |          0.7771 |       0.8186 |    0.2229 |     0.9591 | False       | method |
| hier_arwhite     |        0.9468 |          0.7917 |       0.8304 |    0.2083 |     0.977  | False       | method |
| hier_degraded    |        0.9423 |          0.7878 |       0.827  |    0.2122 |     0.97   | False       | method |
| hier_huber       |        0.9468 |          0.7925 |       0.8314 |    0.2075 |     0.9775 | False       | method |
| hier_no_persist  |        0.6465 |          0.528  |       0.7608 |    0.472  |     0.7098 | False       | method |
| hier_rank0       |        0.9367 |          0.7205 |       0.9092 |    0.2795 |     0.9693 | False       | method |
| hier_rw          |        0.9597 |          0.8014 |       0.8432 |    0.1986 |     0.9847 | False       | method |
| hier_ssm         |        0.9468 |          0.7917 |       0.8304 |    0.2083 |     0.977  | False       | method |
| hier_white       |        0.9541 |          0.7967 |       0.8377 |    0.2033 |     0.9808 | False       | method |
| indep_ssm        |        0.9576 |          0.8003 |       0.8437 |    0.1997 |     0.9813 | False       | method |
| matched_contrast |        0.9506 |          0.7938 |       0.8372 |    0.2062 |     0.9759 | False       | method |
| msprt            |        0.91   |          0.7523 |       0.7892 |    0.2477 |     0.9315 | False       | method |
| mw_judge         |        0.9249 |          0.8464 |       0.7009 |    0.1536 |     0.9555 | False       | method |
| pooled_ssm       |        0.5297 |          0.4512 |       0.9415 |    0.5488 |     0.5    | False       | method |
| sparse_mix_glr   |        0.9465 |          0.8693 |       0.7193 |    0.1307 |     0.9716 | False       | method |
| topk_cusum       |        0.9072 |          0.7513 |       0.7871 |    0.2487 |     0.9182 | False       | method |
| wmean            |        0.9531 |          0.8745 |       0.7259 |    0.1255 |     0.9762 | False       | method |

## table_brier

| method          |   brier |
|:----------------|--------:|
| hier_arwhite    |  0.0573 |
| hier_degraded   |  0.0596 |
| hier_huber      |  0.0578 |
| hier_no_persist |  0.0633 |
| hier_rank0      |  0.0535 |
| hier_rw         |  0.0465 |
| hier_ssm        |  0.0573 |
| hier_white      |  0.0524 |
| indep_ssm       |  0.0524 |
| pooled_ssm      |  0.0611 |

## table_flicker

| method           | harm   |   reversals |   time_paused |
|:-----------------|:-------|------------:|--------------:|
| adj_cusum        | False  |       0.068 |         1.956 |
| adj_cusum        | True   |       1.369 |        56.657 |
| adj_ewma         | False  |       0.074 |         1.199 |
| adj_ewma         | True   |       1.175 |        22.603 |
| ar_cusum         | False  |       0.068 |         1.842 |
| ar_cusum         | True   |       1.366 |        53.173 |
| bocpd            | False  |       0.084 |         1.133 |
| bocpd            | True   |       0.367 |         6.826 |
| combo_hier_m0    | False  |       0.068 |         1.479 |
| combo_hier_m0    | True   |       1.356 |        87.362 |
| combo_hier_topk  | False  |       0.077 |         1.886 |
| combo_hier_topk  | True   |       1.374 |        87.017 |
| combo_m0_topk    | False  |       0.1   |         1.513 |
| combo_m0_topk    | True   |       1.606 |        56.345 |
| glr_window       | False  |       0.09  |         1.27  |
| glr_window       | True   |       1.711 |        41.135 |
| hier_arwhite     | False  |       0.06  |         2.055 |
| hier_arwhite     | True   |       1.283 |        92.83  |
| hier_degraded    | False  |       0.057 |         1.74  |
| hier_degraded    | True   |       1.295 |        91.372 |
| hier_huber       | False  |       0.07  |         2.288 |
| hier_huber       | True   |       1.306 |        92.574 |
| hier_no_persist  | False  |       0.106 |         0.393 |
| hier_no_persist  | True   |       1.024 |        11.678 |
| hier_rank0       | False  |       0.087 |         3.895 |
| hier_rank0       | True   |       0.833 |        52.985 |
| hier_rw          | False  |       0.072 |         2.128 |
| hier_rw          | True   |       1.315 |        93.621 |
| hier_ssm         | False  |       0.06  |         2.055 |
| hier_ssm         | True   |       1.283 |        92.83  |
| hier_white       | False  |       0.055 |         1.975 |
| hier_white       | True   |       1.404 |        87.458 |
| indep_ssm        | False  |       0.094 |         2.361 |
| indep_ssm        | True   |       1.647 |        78.55  |
| matched_contrast | False  |       0.096 |         0.625 |
| matched_contrast | True   |       1.224 |        32.222 |
| msprt            | False  |       0.056 |         2.249 |
| msprt            | True   |       0.792 |        75.105 |
| mw_judge         | False  |       0.093 |         1.867 |
| mw_judge         | True   |       1.383 |        39.709 |
| pooled_ssm       | False  |       0.095 |         1.361 |
| pooled_ssm       | True   |       1.517 |        42.542 |
| sparse_mix_glr   | False  |       0.056 |         1.225 |
| sparse_mix_glr   | True   |       1.733 |        54.074 |
| topk_cusum       | False  |       0.078 |         1.237 |
| topk_cusum       | True   |       1.637 |        51.312 |
| wmean            | False  |       0.078 |         1.746 |
| wmean            | True   |       1.755 |        55.19  |

## table_transient

| method           |   alarm_rate |
|:-----------------|-------------:|
| adj_cusum        |       0.0976 |
| adj_ewma         |       0.1707 |
| ar_cusum         |       0.0976 |
| bocpd            |       0.0732 |
| combo_hier_m0    |       0.439  |
| combo_hier_topk  |       0.3415 |
| combo_m0_topk    |       0.3902 |
| glr_window       |       0.122  |
| hier_arwhite     |       0.4146 |
| hier_degraded    |       0.3415 |
| hier_huber       |       0.4146 |
| hier_no_persist  |       0.122  |
| hier_rank0       |       0.1707 |
| hier_rw          |       0.4146 |
| hier_ssm         |       0.4146 |
| hier_white       |       0.2927 |
| indep_ssm        |       0.3171 |
| matched_contrast |       0.3659 |
| msprt            |       0.0732 |
| mw_judge         |       0.1463 |
| pooled_ssm       |       0.3902 |
| sparse_mix_glr   |       0.122  |
| topk_cusum       |       0.1463 |
| wmean            |       0.1707 |