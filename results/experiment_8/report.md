# Experiment 8: Robustness Evaluation

## 1. Beta Spread & Residual Shift Diagnostic Under Slope Heterogeneity

| variant      |   mean_error |   sd_error |   rms_error |   max_abs_error |
|:-------------|-------------:|-----------:|------------:|----------------:|
| per_host_pre |   0.00064093 |  0.0406149 |   0.0531084 |       0.0967718 |
| pooled_dev   |   0.0145304  |  0.0779332 |   0.0795753 |       0.153269  |


| variant          |   signed_mean_shift |   sd_residual_shift |   rms_residual_shift |   max_abs_shift |
|:-----------------|--------------------:|--------------------:|---------------------:|----------------:|
| matched_contrast |         0.000274218 |           0.0271623 |            0.0274632 |       0.0533598 |
| per_host_pre     |         0.000211036 |           0.0151707 |            0.0153216 |       0.0295243 |
| pooled_dev       |         0.00103354  |           0.0264699 |            0.0270089 |       0.0522952 |

## 2. Heavy Tails (Student-t(3)) Robustness

| detector            |   null_rate |     ci_lo |    ci_hi |   detection_rate |   mean_capped_time |
|:--------------------|------------:|----------:|---------:|-----------------:|-------------------:|
| hier_ssm (standard) |      0.1275 | 0.0964251 | 0.164212 |         0.326667 |            81.0333 |
| hier_huber (c=3.0)  |      0.095  | 0.0681067 | 0.128061 |         0.28     |            86.58   |

## 3. Persistent Noise (phi_e=0.8) Robustness

| detector                        |   null_rate |    ci_lo |    ci_hi |   detection_rate |   mean_capped_time |
|:--------------------------------|------------:|---------:|---------:|-----------------:|-------------------:|
| hier_ssm (nominal phi=0.6)      |      0.25   | 0.208302 | 0.295442 |         0.666667 |            40.4933 |
| hier_ssm (conservative phi=0.8) |      0.1775 | 0.141311 | 0.218541 |         0.553333 |            53.6333 |