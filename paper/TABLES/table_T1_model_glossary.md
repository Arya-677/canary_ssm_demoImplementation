# table_T1_model_glossary: Mathematical Parameter Glossary and Dimensions



| Symbol    | Dimension   | Domain   | Description                                                     |
|:----------|:------------|:---------|:----------------------------------------------------------------|
| y_{it}    | Scalar      | Real     | Log-transformed latency measurement on host i at time t         |
| x_t       | Scalar      | Real     | Measured cluster workload covariate (log QPS) at time t         |
| \mu_i     | Scalar      | Real     | Pre-period baseline latency intercept for host i                |
| \beta_i   | Scalar      | Real     | Workload sensitivity regression slope for host i                |
| \lambda_i | Scalar      | Real     | Factor loading mapping rank-1 shared shock to host i            |
| a_{it}    | Scalar      | Real     | Latent software deployment treatment effect on host i at time t |
| C         | n x G       | {0, 1}   | Host class allocation indicator matrix                          |
| B         | n x (n-G)   | Real     | Block-diagonal orthonormal sum-zero basis matrix                |
| \rho      | Scalar      | [0, 1)   | AR(1) state-space temporal persistence / inertia parameter      |
| \kappa    | Scalar      | Real     | Preregistered qualifying harm boundary: log(1.02) ~= 0.0198     |
| \tau      | Scalar      | Real     | Order-statistic calibrated decision stopping threshold          |
