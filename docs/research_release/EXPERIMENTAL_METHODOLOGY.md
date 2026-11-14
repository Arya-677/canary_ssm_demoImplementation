# Experimental Methodology: Canary SSM V3
## Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

- **Governing Plan:** `docs/Canary_SSM_Change_Plan.pdf` (Revision 3)
- **Preregistration:** `docs/PREREGISTRATION_V3.md` (Frozen)
- **Statistical Framework:** Paired Design, Order-Statistic Calibration, Permutation Testing, and Holm Multiplicity Correction

---

### 1. Simulation Design & Synthetic Fleet Telemetry

The experimental evaluation is built on a high-fidelity synthetic telemetry generator (`canary_ssm/simulate.py`) that models realistic microservice latency dynamics in a cloud infrastructure setting.

#### 1.1 Fleet Topology
- **Total Hosts:** $N = 100$ instances.
- **Canary Partition:** $N_c = 10$ hosts (10% traffic allocation).
- **Control Partition:** $N_0 = 90$ hosts (90% baseline traffic).
- **Hardware/Zone Classes:** $K = 2$ classes (50 hosts per class) with distinct baseline latency offsets ($\mu_c$) and workload sensitivity coefficients ($\beta_i$).

#### 1.2 Time Horizon
- **Pre-Rollout Calibration Window:** $t \in [1, 180]$ minutes (3 hours of historical telemetry used strictly for nuisance parameter estimation).
- **Post-Rollout Monitoring Window:** $t \in [181, 300]$ minutes (2 hours of active canary rollout observation).
- **Sampling Frequency:** Discrete 1-minute telemetry reporting intervals.

#### 1.3 Telemetry Confounders & Noise Generators
The simulator injects realistic distributed systems disturbances:
- **Diurnal Workload Stream ($w_t$):** AR(1) process with sinusoidal diurnal variations: $w_t = \phi_w w_{t-1} + A \sin(2\pi t / 1440) + \epsilon_w$.
- **Shared Latent Factor ($f_t$):** Environmental drift affecting all hosts with heterogeneous loadings $\lambda_i$.
- **Step Shifts ($\Delta w$):** Sustained $+0.3365$ workload step jumps simulating cluster traffic re-routing.
- **Heavy-Tailed Noise:** Student-$t$ distributed observation noise with degrees of freedom $\nu = 3$.
- **Telemetry Missingness:** 20% independent random dropouts and 3-minute burst dropouts.
- **Host Label Misclassification:** 30% random label contamination swapping canary and control tags.

---

### 2. Harm Boundary & Qualifying Event Definitions

- **Harm Boundary ($a^*$):** A relative latency degradation of 3.0%:
  $$a^* = \log(1.03) \approx 0.0295588$$
- **Qualifying Event Definition:** A rollout instance is classified as containing a genuine harmful event if the true injected degradation $a_t$ satisfies:
  $$a_t \ge a^* \quad \text{for at least } 15 \text{ consecutive minutes}$$
  Rollouts with transient spikes ($< 15$ min) or sub-boundary degradations ($< 3\%$) are designated as **non-event disturbances** to benchmark false-pause resistance.

---

### 3. Scenario Taxonomy (16 Preregistered Scenarios)

The primary empirical study (`study_inertia`) evaluated 16 distinct scenarios across 9,600 unique rollouts (240,000 policy evaluations):

#### 3.1 Event Scenarios (11 Harmful Perturbations)
1. **`broad_fleet`:** Fleet-wide shared regression affecting all 10 canary hosts simultaneously.
2. **`class_wide`:** Correlated degradation confined to Class 0 canary instances (5 hosts).
3. **`weak_persistent_3host`:** Subtle 3.0% regression affecting only 3 canary hosts.
4. **`single_host_persistent`:** Persistent 3.0% regression isolated to a single canary instance (Cost Check).
5. **`slow_drift_3host`:** Gradual linear ramp reaching 3.0% over 40 minutes across 3 hosts.
6. **`mixed_fast_slow`:** Heterogeneous rollout: 1 host degrades abruptly, 2 hosts degrade slowly.
7. **`regression_recovery`:** Canary regression followed by automated rollback at $t=240$ and full recovery.
8. **`partial_recovery`:** Canary regression where even-numbered hosts recover while odd-numbered hosts stay degraded.
9. **`step_plus_harm`:** Confounded scenario: sustained workload step concurrent with canary regression.
10. **`periodic_workload`:** Strong sinusoidal workload oscillation superimposed on rollout regression.
11. **`workload_spikes`:** Periodic burst workload spikes concurrent with rollout regression.

#### 3.2 Non-Event Disturbances (5 Benign Perturbations)
12. **`iso_spike_1host`:** Isolated 5-minute transient spike (+50% latency) on 1 host (benign).
13. **`short_3host`:** Brief 5-minute correlated spike across 3 hosts (benign).
14. **`sub_boundary_2pct`:** Persistent 2.0% latency increase (below the 3.0% harm boundary; benign).
15. **`improvement_3host`:** 3.0% latency improvement (negative effect; benign).
16. **`step_no_harm_proxy`:** Sustained workload step jump with zero canary software degradation (benign null).

---

### 4. Evaluated Methods and Baseline Hierarchy

1. **`hier_ssm` (Proposed V3):** Hierarchical Gaussian state-space model with fleet effect $a_t$, sum-to-zero class deviations $\boldsymbol{\delta}_t$, and Joseph-form Kalman update.
2. **`hier_ts` (Two-Scale Ablation):** Two-scale hierarchical model with class-level autoregressive inertia.
3. **`indep_ssm` (Unpooled SSM):** Independent state-space filter per host without cross-host shrinkage.
4. **`pooled_ssm` (Mean-Only SSM):** State-space filter on fleet-average contrast without host-level tracking.
5. **`glr_window` (Sequential GLR):** Sequential Generalized Likelihood Ratio detector with a 30-minute sliding window.
6. **`sparse_mix_glr` (Xie-Siegmund):** Mixture-GLR comparator designed for sparse multi-stream detection.
7. **`adj_cusum` (Workload CUSUM):** Page's Cumulative Sum control chart with pre-period baseline and variance calibration.
8. **`bocpd` (Adams-MacKay):** Bayesian Online Changepoint Detection with hazard function.
9. **`mw_judge` (Non-Parametric):** Rolling two-sample Mann-Whitney U test between canary and control pools.

---

### 5. Data Roles & Partitioning Protocol

In strict enforcement of scientific safeguards (Part 0 Rules):
- **Development Set (`dev`):** 500 null pairs used exclusively for grid search and hyperparameter tuning (`model_v3`).
- **Calibration Set (`calibration`):** $B = 2,000$ exchangeable null rollouts used to compute order-statistic thresholds $\tau_{\text{high}}$ and $\tau_{\text{low}}$.
- **Null Validation Set (`null_validation`):** $n = 2,000$ independent null rollouts evaluated via the exact Beta-Binomial test to verify Gate G2 compliance.
- **Held-Out Test Set (`test`):** 1,000 harmful + 1,000 null pairs evaluated **strictly once per regime** without retuning.

---

### 6. Primary Evaluation Metrics & Statistical Testing

#### 6.1 Mean Horizon-Capped Detection Time ($T_{\text{capped}}$)
For each rollout $j$, detection time is defined relative to event onset $t_{\text{onset}}$:
$$T_j = \begin{cases} t_{\text{alarm}, j} - t_{\text{onset}, j} & \text{if alarm occurs during event} \\ T_{\text{horizon}} - t_{\text{onset}, j} & \text{if miss or premature alarm} \end{cases}$$
Missed events and premature alarms are penalised with the full remaining monitoring horizon ($T_{\text{horizon}} = 120\text{ min}$).

#### 6.2 Paired Experimental Design & Hypothesis Testing
Because all detectors are evaluated on the exact same simulated rollouts sharing identical seeds:
1. **Paired Differences:** $\Delta_j = T_{j, \text{method A}} - T_{j, \text{method B}}$.
2. **Sign-Flip Permutation Test:** Exact two-sided $p$-value computed via $5,000$ random sign-flips of paired differences.
3. **Multiplicity Correction:** Family-wise error rate controlled via the Holm step-down procedure grouped by hypothesis family.
4. **Uncertainty Intervals:** 95% confidence intervals constructed via paired bootstrap resampling (1,000 iterations).
