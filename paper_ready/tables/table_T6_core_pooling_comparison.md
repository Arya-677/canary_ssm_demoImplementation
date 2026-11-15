# table_T6_core_pooling_comparison: Core Pooling Comparison Across Scenario Classes (Independent vs Pooled vs Hierarchical)



| Scenario_Class              | indep_ssm_delay   | pooled_ssm_delay   | hier_ssm_delay   | Hier_vs_Indep_Delta   | Hier_vs_Pooled_Delta   | Best_Method   |
|:----------------------------|:------------------|:-------------------|:-----------------|:----------------------|:-----------------------|:--------------|
| Class-wide Harm (S2)        | 13.4 min          | 9.2 min            | 8.8 min          | -4.6 min (p=0.001)    | -0.4 min (ns)          | hier_ssm      |
| Broad-fleet Harm (S3)       | 11.8 min          | 8.6 min            | 7.5 min          | -4.3 min (p=0.001)    | -1.1 min (p=0.04)      | hier_ssm      |
| Single-Host Persistent (S5) | 7.4 min           | 26.8 min           | 16.8 min         | +9.4 min (p<0.001)    | -10.0 min (p<0.001)    | indep_ssm     |
| Weak Sparse Harm (S4)       | 14.2 min          | 22.4 min           | 12.6 min         | -1.6 min (p=0.08)     | -9.8 min (p<0.001)     | hier_ssm      |
| Overall Capped TTS (Plain)  | 18.10 min         | 35.00 min          | 15.57 min        | -2.53 min (p=0.0012)  | -19.43 min (p<0.001)   | hier_ssm      |
