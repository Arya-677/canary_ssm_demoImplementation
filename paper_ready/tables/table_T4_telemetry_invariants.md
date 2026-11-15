# table_T4_telemetry_invariants: Parameter Recovery and Posterior Interval Coverage



| Parameter                       | True_Value   |   Estimated_Bias |     RMSE | Nominal_95_Coverage   | Status                  |
|:--------------------------------|:-------------|-----------------:|---------:|:----------------------|:------------------------|
| Baseline Log-Latency (mu)       | [-0.5, 0.5]  |         0.000137 | 0.015903 | 99.88%                | UNBIASED                |
| Workload Sensitivity (beta)     | [0.2, 1.2]   |         0.002023 | 0.073695 | 98.40%                | UNBIASED                |
| AR(1) Noise Persistence (phi_e) | 0.30         |         0.031247 | 0.072287 | 94.20%                | SLIGHT_POS_BIAS         |
| Latent Treatment Effect (a_it)  | 0.0296 (3%)  |        -0.00184  | 0.00842  | 74.96%                | UNDERCOVERAGE_SHRINKAGE |
