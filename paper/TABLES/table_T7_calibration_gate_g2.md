# table_T7_calibration_gate_g2: Decision Thresholds and Gate G2 Exact Beta-Binomial Validity Audit



| method         |   threshold |   n_val |   alarms |   achieved_far |   binom_pval | gate_g2_pass   |
|:---------------|------------:|--------:|---------:|---------------:|-------------:|:---------------|
| hier_ssm       |  -0.0302635 |     500 |       24 |          0.048 |     0.610066 | True           |
| indep_ssm      |  -0.0473949 |     500 |       26 |          0.052 |     0.447061 | True           |
| no_inertia_ssm |  -3.19756   |     500 |       21 |          0.042 |     0.821149 | True           |
| kayenta_judge  |   5.94009   |     500 |       23 |          0.046 |     0.687898 | True           |
| argo_policy    |  16.3333    |     500 |       22 |          0.044 |     0.759055 | True           |
| flagger_policy |   9.8       |     500 |       22 |          0.044 |     0.759055 | True           |
| slo_threshold  |   1.72214   |     500 |       16 |          0.032 |     0.980142 | True           |
| adj_cusum      |  65.6651    |     500 |       20 |          0.04  |     0.872765 | True           |
| glr_window     |  49.7862    |     500 |       18 |          0.036 |     0.944084 | True           |
