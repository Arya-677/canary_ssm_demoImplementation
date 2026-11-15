# table_T9_robustness_matrix: Stress Testing and Robustness Matrix Across Non-Ideal Conditions



| Stress_Condition                   | hier_ssm_far   | indep_ssm_far   | adj_cusum_far   | glr_window_far   | Evaluation                                                                |
|:-----------------------------------|:---------------|:----------------|:----------------|:-----------------|:--------------------------------------------------------------------------|
| Workload Step Surge (50% Jump)     | 47.5%          | 49.0%           | 58.0%           | 50.0%            | Material failure mode: shared step leakage triggers alerts                |
| Heavy Tails (Student-t df=3)       | 6.0%           | 6.2%            | 12.7%           | 85.7%            | SSM robust via Kalman filtering; GLR suffers severe FAR inflation         |
| 20% Missing Data (MCAR)            | 5.2%           | 5.4%            | 8.8%            | 9.1%             | SSM preserves power (82.4%) via Kalman missing projection                 |
| Control Contamination (20%)        | 5.8%           | 5.9%            | 9.4%            | 11.2%            | Factor estimate partially absorbs signal; detection delay increases +3.2m |
| Label Noise (30% Group Error)      | 5.4%           | 5.2%            | 8.2%            | 8.5%             | Degrades class pooling benefits to independent SSM levels                 |
| Negative Controls (NC-01 to NC-05) | < 5.0%         | < 5.0%          | < 5.0%          | < 5.0%           | All methods pass non-alarm safety under zero true harm                    |
