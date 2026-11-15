# table_T2_code_integrity: Frozen Protocol and Experimental Dataset Splits



| Split_Role        | Purpose                                            |   N_Null |   N_Harmful | Scenarios                | Tuning_Permitted   |
|:------------------|:---------------------------------------------------|---------:|------------:|:-------------------------|:-------------------|
| Development       | Code debugging & hyperparameter candidate bounds   |      200 |         200 | Synthetic Pilots         | True               |
| Calibration       | Null threshold determination via order statistics  |     1000 |           0 | 12 Null Scenarios        | False              |
| Validation        | Gate G2 exact Beta-Binomial validity audit         |      500 |           0 | Stationary Baseline Null | False              |
| Confirmatory Test | Final head-to-head benchmarking & hypothesis tests |      600 |         700 | 26 Matched Scenarios     | False              |
