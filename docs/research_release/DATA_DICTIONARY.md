# Data Dictionary: Canary SSM V3 Research Outputs
## Schema Specifications for CSV and JSON Experimental Records

- **Role Separation Standards:** Detector Inputs vs Evaluator-Only Truth
- **Partition Roles:** Development (`dev`), Calibration (`cal`), Validation (`val`), Evaluation (`eval`), Held-Out Test (`test`)

---

### 1. Primary Output Files Summary

| File Path | Partition Role | Row Meaning | Evaluator Truth Included? | Primary Research Use |
| :--- | :---: | :--- | :---: | :--- |
| `results/study_inertia/table_paired_contrasts.csv` | `eval` | Paired contrast test per scenario $\times$ contrast | No | Primary hypothesis testing (H1, H2, H3, H5) |
| `results/study_inertia/table_scenario_summary.csv` | `eval` | Aggregated performance metrics per scenario $\times$ method $\times$ $m$ | No | Scenario summary metrics (power, delay, miss rate) |
| `results/study_inertia/table_calibration_validity.csv` | `cal`/`val` | Calibration and Gate G2 audit per method $\times$ $m$ $\times$ regime | No | Verification of false-alert budget validity |
| `results/study_inertia/per_rollout_policy.csv` | `eval` | Individual rollout evaluation per policy instance | Yes (`has_event`) | Micro-level rollout decision traces |
| `results/plain_final/table_detection.csv` | `test` | Held-out plain test detection metrics per method | No | Final test power and delay comparisons |
| `results/plain_final/table_null_rates.csv` | `test` | Held-out plain test null false-alert rate per method | No | Gate G2 verification on unseen test data |
| `results/plain_final/table_paired_differences.csv` | `test` | Paired bootstrap differences against `hier_ssm` | No | Final test statistical significance tests |
| `results/plain_final/per_rollout_metrics.csv` | `test` | Raw per-rollout evaluation record on plain test | Yes (`harm`, `onset`) | Base record for held-out plain test tables |
| `results/study_combined/table_scenario_summary.csv` | `eval` | Multi-stressor scenario metrics per method $\times$ $m$ | No | Boundary robustness evaluation under noise |
| `artifacts/model_v3/model_config.json` | `dev` | Selected hyperparameter configuration dictionary | No | Model configuration for state-space filters |
| `artifacts/policy_plain_v3/policy.json` | `cal` | Calibrated decision thresholds and policy rules | No | Operational decision parameters for plain regime |
| `artifacts/policy_step_v3/policy.json` | `cal` | Calibrated decision thresholds and policy rules | No | Operational decision parameters for step regime |

---

### 2. Detailed Schema Definitions

#### 2.1 `results/study_inertia/table_paired_contrasts.csv`
- **Description:** Paired contrast differences and sign-flip permutation tests for all preregistered hypotheses.
- **Row Grain:** One row per scenario $\times$ contrast comparison $\times$ confirmation depth $m$.
- **Columns:**
  - `scenario` (*string*): Identifier of the 16 scenarios (e.g., `broad_fleet`, `class_wide`, `single_host_persistent`).
  - `contrast` (*string*): Comparative contrast string (e.g., `C1_asymmetry:hier_ts-vs-hier_ssm@m1`, `C2_pooling:hier_ssm-vs-indep_ssm@m1`).
  - `n` (*integer*): Number of paired rollouts evaluated (300 per cell).
  - `mean_capped_diff` (*float, minutes*): Mean horizon-capped delay difference ($\text{Method A} - \text{Method B}$). Negative favors Method A.
  - `ci_lo` (*float, minutes*): Lower bound of 95% paired bootstrap confidence interval.
  - `ci_hi` (*float, minutes*): Upper bound of 95% paired bootstrap confidence interval.
  - `p_signflip` (*float, $[0, 1]$*): Two-sided permutation test $p$-value (5,000 sign-flips).
  - `hypothesis` (*string*): Preregistered hypothesis family (`H1`, `H2`, `H3`, `H5`).
  - `p_holm` (*float, $[0, 1]$*): Step-down Holm-adjusted $p$-value controlling FWER within hypothesis family.

#### 2.2 `results/study_inertia/table_calibration_validity.csv`
- **Description:** Finite-sample order-statistic threshold calibration and Beta-Binomial validity audit.
- **Row Grain:** One row per regime $\times$ method $\times$ confirmation depth $m$.
- **Columns:**
  - `regime` (*string*): Operational regime (`plain`, `step`).
  - `method` (*string*): Candidate detector method identifier (`hier_ssm`, `hier_ts`, `indep_ssm`, `glr_window`, `adj_cusum`).
  - `m_on` (*integer*): Confirmation depth in minutes ($m \in \{1, 3, 5, 10, 15\}$).
  - `B` (*integer*): Number of exchangeable calibration null rollouts ($2,000$).
  - `k_order` (*integer*): Order statistic index used for threshold selection ($1,901$).
  - `h_on` (*float*): Calibrated alarm threshold $\tau_{\text{high}}$ on persistence score scale.
  - `h_off` (*float*): Calibrated clear / recovery threshold $\tau_{\text{low}}$ on persistence score scale.
  - `alerts` (*integer*): Observed false-alert count on validation null rollouts.
  - `n_val` (*integer*): Number of independent validation null rollouts ($2,000$).
  - `far` (*float, $[0, 1]$*): Achieved false-alert rate ($\text{alerts} / n_{\text{val}}$).
  - `ci_lo` (*float*): Lower bound of 95% Clopper-Pearson exact binomial confidence interval.
  - `ci_hi` (*float*): Upper bound of 95% Clopper-Pearson exact binomial confidence interval.
  - `expected_alerts` (*float*): Theoretical expected alerts under exchangeability ($99.95$).
  - `bb_pvalue_two_sided` (*float, $[0, 1]$*): Exact two-sided Beta-Binomial validity test $p$-value.
  - `gate_evaluable` (*boolean*): Whether $n_{\text{val}} \ge 2,000$ meeting Gate G2 sample size requirements (`True`).

#### 2.3 `results/plain_final/table_detection.csv`
- **Description:** Detection performance on the held-out plain test partition ($N = 959$ event rollouts).
- **Row Grain:** One row per evaluated detector method.
- **Columns:**
  - `method` (*string*): Evaluated detector method name.
  - `n_events` (*integer*): Number of evaluated rollouts containing a true qualifying event ($959$).
  - `miss` (*float, $[0, 1]$*): Empirical miss rate (proportion of event rollouts receiving no alarm).
  - `premature` (*float, $[0, 1]$*): Proportion of rollouts triggering an alarm before true event onset.
  - `late_after_recovery` (*float, $[0, 1]$*): Proportion of rollouts alarming after true event remediation.
  - `mean_capped_time` (*float, minutes*): Mean horizon-capped detection time (misses and premature penalized with remaining horizon).
  - `cond_delay_mean` (*float, minutes*): Mean detection delay conditioned on successful, timely detection.
  - `cond_delay_median` (*float, minutes*): Median detection delay conditioned on successful detection.
  - `P_detect_5m` .. `P_detect_120m` (*float, $[0, 1]$*): Cumulative detection probability within 5, 15, 30, 60, and 120 minutes of onset.
  - `is_oracle` (*boolean*): Whether the method is an omniscient reference oracle (`False`).
  - `role` (*string*): Algorithm categorization (`method`, `ablation`, `baseline`).

#### 2.4 `results/study_combined/table_scenario_summary.csv`
- **Description:** Multi-stressor robustness summary under composite perturbations.
- **Row Grain:** One row per scenario $\times$ method $\times$ confirmation depth $m$.
- **Columns:**
  - `scenario` (*string*): Composite scenario identifier (`regression_plus_heavytail`, `regression_plus_missing`, `regression_plus_step`, `regression_plus_contamination`, `regression_plus_labelerror`).
  - `method` (*string*): Detector method name.
  - `m_on` (*integer*): Confirmation depth $m$.
  - `null_alert_rate` (*float, $[0, 1]$*): Empirical false-alert rate on paired null rollouts ($n=300$).
  - `power` (*float, $[0, 1]$*): Empirical detection power ($1 - \text{miss}$).
  - `miss` (*float, $[0, 1]$*): Empirical miss rate on event rollouts.
  - `mean_capped` (*float, minutes*): Mean horizon-capped detection time.

---

### 3. Truth Separation & Safeguard Verification

In accordance with Hard Rule 1:
- Detector input data streams contain only observed metric timestamps and host values.
- Truth labels (`harm`, `onset`, `has_event`, `true_effect`) are stored in segregated evaluator structures and are accessed exclusively by `metrics.py` after detector scoring is complete.
