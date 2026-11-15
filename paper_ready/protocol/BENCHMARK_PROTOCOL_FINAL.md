# BENCHMARK PROTOCOL FINAL SPECIFICATION

- **Protocol Version**: 3.0-FINAL
- **Date**: 2026-11-15
- **Branch**: `v3` / `research-release-v3` / `external-validation-v1`
- **Governing Specification**: Section 7 of *Canary SSM V3 Final Paper-Readiness and Evidence Execution Manual*

---

## 1. Experimental Design & Cohort Definition

The confirmatory benchmark compares candidate monitoring methods under **identical underlying simulation rollouts** (common random numbers).
- **Cohort Size**: 26 scenarios $\times$ 50 paired rollouts = 2,600 total rollout evaluations per method.
- **Scenarios**:
  - **12 Null Scenarios** (`NULL-01` to `NULL-12`): stationary baseline, workload steps ($\Delta x = 0.3365$), diurnal oscillations, workload spikes, heavy tails ($t_3$), heterogeneous host noise, MCAR missingness (10%), burst missingness, control contamination (10%), label error (30%), late arrival telemetry, cluster scaling ($N=50$).
  - **14 Harm Scenarios** (`HARM-01` to `HARM-14`): sparse canary harm, class-wide harm, broad-fleet harm, weak sparse harm (2%), single-canary harm (5%), ramp onset, transient decay, step plus harm, class step, heavy tails, missingness (20%), control contamination (10%), label error (30%), delayed onset.
- **Harm Boundary**: $\kappa = \log(1.02) \approx 0.01980$ (2% latency increase).
- **Qualifying Event**: Latent treatment effect $a_{it} > \kappa$ for at least 15 consecutive minutes on at least one canary host. Event onset $t^*$ is the first minute of this qualifying run.
- **Observation Cadence**: 1-minute discrete windows ($t_{\text{pre}} = 60\text{m}$, $t_{\text{post}} = 60\text{m}$ or $120\text{m}$).

---

## 2. Data Splits & Leakage Prevention

| Split Role | Sample Size | Seed Hierarchy | Permitted Operations | Forbidden Operations |
|---|---|---|---|---|
| **Development** | 200 null, 200 harm | `10000 - 10399` | Code debugging, matrix algebra checks | Reporting final paper claims |
| **Calibration** | 1,000 null | `100000 - 100999` | Order-statistic threshold estimation ($k=951$) | Model selection, hyperparameter tuning |
| **Validation** | 500 null | `101000 - 101499` | Gate G2 Beta-Binomial validity audit | Recalibrating thresholds |
| **Confirmatory Test**| 600 null, 700 harm | `102000 + scen*1000 + p` | One-time evaluation of frozen detectors | Model tuning, peeking, threshold shifts |

---

## 3. Order-Statistic Calibration

For each method, the rollout-level decision threshold $\tau$ is determined from the empirical distribution of complete-horizon null rollout maxima:
$$\tau = X_{(k)}, \quad k = \lceil (B + 1)(1 - \alpha) \rceil$$
For $B = 1,000$ and $\alpha = 0.05$, the order-statistic index is $k = 951$ (rank 951 out of 1,000 sorted maxima).
- Strict exceedance: an alarm occurs at the first minute $t \ge t_0$ where $\text{score}_t \ge \tau$.
- Latched alarm: once triggered, the alarm remains active for that rollout.

---

## 4. Primary & Secondary Endpoints

1. **Rollout-Level False Alert Rate (FAR)**: Proportion of complete null rollouts triggering at least one alarm:
   $$\text{FAR} = \frac{1}{N_{\text{null}}} \sum_{j=1}^{N_{\text{null}}} \mathbf{1}\{\text{alarm}_j\}$$
2. **Detection Power**: Proportion of qualifying harmful rollouts triggering an alarm at or after qualifying onset:
   $$\text{Power} = \frac{1}{N_{\text{harm}}} \sum_{j=1}^{N_{\text{harm}}} \mathbf{1}\{\text{alarm}_j \wedge (t_{\text{alarm}} \ge t^*)\}$$
3. **Horizon-Capped Time-to-Success (TTS)**:
   $$\text{TTS}_j = \begin{cases} t_{\text{alarm}, j} - t^* & \text{if successfully detected} \\ H & \text{if missed, premature, or censored} \end{cases}$$
   Both $H = 45$ minutes (fault duration cap) and $H = 120$ minutes (full monitoring horizon cap) are explicitly reported.
4. **Conditional Delay**: Mean and median detection delay restricted strictly to the successfully detected cohort.
5. **Statistical Tests**: 5,000 paired sign-flip permutation tests and 2,000-sample bootstrap confidence intervals. Holm-Bonferroni step-down multiplicity correction across comparator families.
