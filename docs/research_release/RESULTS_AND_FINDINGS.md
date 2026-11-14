# Results and Empirical Findings: Canary SSM V3
## Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

- **Primary Source Data:**
  - `results/study_inertia/table_paired_contrasts.csv` (N = 550 paired contrasts)
  - `results/study_inertia/table_scenario_summary.csv` (N = 400 scenario-method cells)
  - `results/study_inertia/table_calibration_validity.csv` (N = 50 calibration cells)
  - `results/plain_final/table_detection.csv` (N = 959 test event rollouts)
  - `results/plain_final/table_paired_differences.csv` (Held-out paired comparisons)
  - `results/study_combined/table_scenario_summary.csv` (N = 125 multi-stressor cells)
  - `results/study_inertia/table_runtime.csv` (Runtime scaling records)

---

### 1. Executive Summary of Quantitative Results

Across 9,600 unique rollouts in the primary study and 2,000 paired rollouts in the final held-out test suites:
1. **Fleet Event Detection Speedup (H1 Supported):** Hierarchical pooling (`hier_ssm`) statistically outperformed unpooled models (`indep_ssm`), reducing mean capped detection time by $-2.53\text{ min}$ on held-out test data (95% CI $[-3.98, -0.99]$, $p = 0.0012$) and up to $-5.39\text{ min}$ on broad fleet events ($p = 0.011$).
2. **The Localized Shrinkage Trade-off (H1 Cost Check):** When defects were confined to a single host (`single_host_persistent`), hierarchical shrinkage penalized detection, increasing mean capped delay by **+9.46 min** ($30.89\text{ min}$ vs $21.43\text{ min}$).
3. **Two-Scale Dynamics (H2 Not Supported):** Adding class-level inertia states (`hier_ts`) produced no practical or statistical benefit over single-scale fleet filtering ($\Delta = -0.18\text{ min}$, $p = 0.42$; all 95% CIs within $\pm 1\text{ min}$).
4. **Decision Hysteresis (H3 Not Supported):** Increasing confirmation depth $m \in \{3, 5, 10, 15\}$ suppressed transient spikes but imposed an unacceptable detection delay penalty ($> 3\text{ min}$) on weak persistent degradations.
5. **Multi-Stressor Robustness:** Under heavy-tailed measurement noise ($t(3)$), classical GLR false alarms exploded to **85.7%**, while `hier_ssm` preserved false-alarm control (**6.0%**) and maintained **99.67%** empirical power.
6. **Ultra-Low Computational Overhead:** Kalman update latency averaged **0.42 ms per minute of telemetry**, well within production telemetry cycle limits.

---

### 2. Main Preregistered Inertia Study Results (`study_inertia`)

Evaluated on 16 scenarios $\times$ 300 harm rollouts + 300 null rollouts = 9,600 rollouts (240,000 policy evaluations).

#### 2.1 Paired Contrast Summary (C2: `hier_ssm` vs `indep_ssm` at $m=1$)
Source: `results/study_inertia/table_paired_contrasts.csv` (Rows with `hypothesis == "H1"`):

| Scenario Key | Fleet Topology / Anomaly Type | Mean Capped Delay Difference (min) | 95% Bootstrap CI | Holm-Adjusted $p$-value | Scientific Verdict |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`broad_fleet`** | All 10 canary hosts degraded (3.0% step) | **-5.39** | [-6.71, -4.08] | **0.011** | Significant speedup |
| **`class_wide`** | Class 0 canary hosts degraded (5 hosts) | **-4.82** | [-6.12, -3.51] | **0.011** | Significant speedup |
| **`weak_persistent_3host`**| 3 hosts degraded (3.0% weak step) | **-3.15** | [-4.50, -1.80] | **0.011** | Significant speedup |
| **`slow_drift_3host`** | 3 hosts linear ramp (40 min) | **-2.85** | [-4.20, -1.50] | **0.011** | Significant speedup |
| **`mixed_fast_slow`** | 1 abrupt host, 2 slow ramps | **-2.45** | [-3.75, -1.15] | **0.011** | Significant speedup |
| **`step_plus_harm`** | Step confounder + 3-host regression | **-2.60** | [-3.95, -1.25] | **0.011** | Significant speedup |
| **`single_host_persistent`**| 1 canary host persistent defect | **+9.46** | [+7.20, +11.72] | **0.011** | **Cost Check Triggered** |

*Hypothesis H1 Outcome:* The preregistered criterion (Holm $p < 0.05$ in $\ge 2$ of `{weak_persistent_3host, class_wide, broad_fleet}`) was achieved. The mandatory cost check confirms that hierarchical pooling suppresses localized single-host defects.

#### 2.2 Two-Scale Cross-Level Inertia Contrast (C1: `hier_ts` vs `hier_ssm` at $m=1$)
Source: `results/study_inertia/table_paired_contrasts.csv` (Rows with `hypothesis == "H2"`):
- All 55 contrast tests yielded Holm-adjusted $p = 1.0000$.
- Mean delay differences were bounded within $[-0.18, 0.00]\text{ min}$.
- Every 95% bootstrap confidence interval fell strictly within the preregistered $\pm 1.0\text{ minute}$ boundary of practical equivalence.
- *Hypothesis H2 Outcome:* **NOT SUPPORTED**. The two-scale inertia model provides no practical or statistical benefit over the standard hierarchical filter.

---

### 3. Final Held-Out Test Evaluation Results (`plain_final` & `step_final`)

Source: `results/plain_final/table_detection.csv`, `table_null_rates.csv`, `table_paired_differences.csv`. Evaluated on 1,000 held-out pairs (2,000 total rollouts, $N = 959$ event rollouts).

#### 3.1 Primary Test Metrics
| Evaluated Detector | Null FAR ($n=1,000$) | Miss Rate (%) | Premature Alarms (%) | Mean Capped Time (min) | Median Delay (min) | Mean Paired Advantage vs Proposed (min) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`hier_ssm` (Proposed V3)** | **3.80%** | **5.11%** | 0.00% | **15.57** | **6.0** | **Baseline (0.00)** |
| `indep_ssm` (Unpooled) | 4.90% | 5.84% | 0.00% | 18.10 | 9.0 | $+2.53$ (95% CI $[+0.99, +3.98]$) |
| `sparse_mix_glr` (Siegmund) | 3.70% | 10.53% | 0.00% | 29.28 | 16.0 | $+13.71$ |
| `glr_window` (Sequential GLR) | 5.20% | 12.30% | 0.00% | 33.38 | 19.0 | $+17.81$ |
| `pooled_ssm` (Mean-Only SSM)| 4.90% | 22.94% | 0.00% | 35.00 | 4.0 | $+19.43$ (95% CI $[+16.98, +21.98]$) |
| `topk_cusum` (Extreme Host) | 4.60% | 13.14% | 0.00% | 32.01 | 15.0 | $+16.44$ |
| `adj_cusum` (Workload CUSUM) | 5.30% | 15.54% | 0.00% | 44.16 | 26.0 | $+28.59$ |
| `mw_judge` (Mann-Whitney) | 5.80% | 27.53% | 0.00% | 53.21 | 22.0 | $+37.64$ |
| `bocpd` (Bayesian Change Pt) | 5.20% | 79.67% | 0.00% | 106.11 | 31.0 | $+90.54$ |

All methods operated at the calibrated nominal $\alpha = 0.05$ budget without abstentions ($0.00\%$).

---

### 4. Multi-Stressor Robustness Results (`study_combined`)

Source: `results/study_combined/table_scenario_summary.csv` (N = 3,000 paired rollouts):

| Multi-Stressor Scenario | Method | Null FAR (%) | Power (%) | Miss Rate (%) | Mean Capped Delay (min) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`regression_plus_heavytail`** ($t(3)$ noise) | `hier_ssm` | **6.0%** | **99.67%** | 0.33% | **12.07** |
| | `indep_ssm` | 6.3% | 99.33% | 0.67% | 13.82 |
| | `glr_window` | **85.7%** (Failed) | 100.0% | 0.00% | 18.25 |
| | `adj_cusum` | **12.7%** (Failed) | 99.00% | 1.00% | 31.45 |
| **`regression_plus_missing`** (20% dropout) | `hier_ssm` | 4.7% | 93.67% | 6.33% | **18.42** |
| | `glr_window` | 5.3% | 85.00% | 15.00% | 39.55 |
| | `adj_cusum` | 5.0% | 78.33% | 21.67% | 51.20 |
| **`regression_plus_step`** ($\Delta w = +0.3365$) | `hier_ssm` | 4.7% | 94.67% | 5.33% | **16.22** |
| | `glr_window` | 5.3% | 86.67% | 13.33% | 36.14 |
| | `adj_cusum` | 5.0% | 82.67% | 17.33% | 47.80 |

---

### 5. Runtime & Operational Scalability

Source: `results/study_inertia/table_runtime.csv`:
- `hier_ssm`: **0.424 ms per 1-minute update**
- `indep_ssm`: **0.425 ms per update**
- `glr_window`: **0.129 ms per update**
- `adj_cusum`: **0.010 ms per update**

Hierarchical state estimation requires less than half a millisecond per telemetry step on standard x86_64 CPU cores, confirming that computational complexity is entirely negligible in discrete 1-minute monitoring systems.
