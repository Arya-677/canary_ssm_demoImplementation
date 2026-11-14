# Pre-Experimental Protocol: External Benchmarking and Validation (V1)

- **Study Identifier**: `external_validation_v1`
- **Specification Document**: *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification* (Revision 1.0)
- **Principal Focus**: Head-to-head empirical comparison of Hierarchical SSM against industry standards (Kayenta, Argo Rollouts, Flagger, SLO contrast) and mechanistic ablations.
- **Data Isolation Guarantee**: All seeds start from 100,000+. Historical V3 datasets (`data/plain/test/`, `data/step/test/`) are strictly quarantined and never referenced.

---

## 1. Research Questions (RQ1–RQ7)

| Question ID | Formulation | Primary Metric |
|---|---|---|
| **RQ1 (Shrinkage vs Independence)** | Does hierarchical shrinkage accelerate multi-host canary failure detection relative to independent SSM under sparse regressions? | Paired detection delay difference ($\Delta D = D_{\text{hier}} - D_{\text{indep}}$). |
| **RQ2 (Single-Host Shrinkage Penalty)** | Does hierarchical pooling impose an empirical delay penalty on isolated single-host failures? | Single-canary detection delay difference ($\Delta D$). |
| **RQ3 (Inertia Ablation)** | Does temporal inertia ($\rho > 0$) provide superior detection delay and false-alarm rejection compared to memoryless spatial regression ($\rho = 0$)? | Delay, power, and false alert rate vs `NoInertiaSSM`. |
| **RQ4 (Industry Comparator Parity)** | How does Hierarchical SSM compare against Kayenta-style Mann-Whitney tests and SLO contrast detectors at identical false-alarm budgets? | Capped time-to-success, empirical power, and detection delay. |
| **RQ5 (Policy Framework Performance)** | How do sequential stopping rules perform when wrapped with Argo Rollouts failureLimit (AR-1, AR-3, AR-5) and Flagger abort policies? | Delay-to-abort and premature false-alarm rates. |
| **RQ6 (Workload Step Robustness)** | How severely do unmodeled common-mode workload shifts degrade classical baseline detectors vs SSM factor adjustment? | Power degradation and false alert rate shift under step regimes. |
| **RQ7 (Telemetry Impairment Robustness)** | What is the relative breakdown threshold of each method under heavy missingness (20%), control contamination (10%), and label noise (30%)? | Power retention curve and abstention rate. |

---

## 2. Benchmark Scenario Matrix

### 2.1 Healthy Null Scenarios (NULL-01 to NULL-12)
1. **NULL-01**: Stationary baseline Gaussian noise ($\mu=100\text{ms}, \sigma=0.01$).
2. **NULL-02**: Step workload increase ($+33.65\%$ concurrent step at $t_0$).
3. **NULL-03**: Diurnal sinusoidal workload modulation.
4. **NULL-04**: Transient traffic spike (5-minute spike at random post-rollout time).
5. **NULL-05**: Heavy-tailed noise (Student-$t$ with $\nu=3$).
6. **NULL-06**: Latency variance heterogeneity across classes.
7. **NULL-07**: Random telemetry missingness (10% MCAR).
8. **NULL-08**: Burst telemetry missingness (5-minute consecutive drops).
9. **NULL-09**: Control contamination (5% degraded control hosts).
10. **NULL-10**: Host metadata misclassification (30% label error).
11. **NULL-11**: Late-arriving telemetry records (causal arrival delay).
12. **NULL-12**: Scaled cluster size ($N=50$ hosts, $n_c=5$ canaries).

### 2.2 Harmful Deployment Scenarios (HARM-01 to HARM-14)
1. **HARM-01**: Sparse localized harm (3 of 10 canaries degraded by $+3.0\%$).
2. **HARM-02**: Class-wide harm (entire class 0 degraded by $+3.0\%$).
3. **HARM-03**: Broad uniform harm (all 10 canaries degraded by $+3.0\%$).
4. **HARM-04**: Weak sparse harm (3 of 10 canaries degraded by $+2.0\%$).
5. **HARM-05**: Single-canary severe harm (1 of 10 canaries degraded by $+5.0\%$).
6. **HARM-06**: Ramp onset degradation (linear ramp over 15 min to $+4.0\%$).
7. **HARM-07**: Transient degradation (peak harm at 15 min, decaying to 0 by 35 min).
8. **HARM-08**: Sparse harm with concurrent workload step ($+33.65\%$).
9. **HARM-09**: Class-wide harm with concurrent workload step.
10. **HARM-10**: Sparse harm under heavy-tailed Student-$t$ noise ($\nu=3$).
11. **HARM-11**: Sparse harm with 20% telemetry missingness.
12. **HARM-12**: Sparse harm with 10% control contamination.
13. **HARM-13**: Class-wide harm with 30% metadata label error.
14. **HARM-14**: Delayed onset harm (degradation begins 10 min after rollout).

---

## 3. Calibration and Statistical Testing Protocol

1. **Calibration Sample**: $B = 1,000$ independent healthy null rollouts per operational regime.
2. **Order-Statistic Threshold**:
   $$\tau = s_{(k)}, \quad k = \lceil(B + 1)(1 - \alpha)\rceil = \lceil 1001 \times 0.95 \rceil = 951$$
3. **Gate G2 Validity Audit**: Exact Beta-Binomial tail test on independent null validation set ($p \ge 0.01$, achieved $\text{FAR} \le 0.075$).
4. **Statistical Significance Testing**:
   - Paired sign-flip permutation tests ($5,000$ random sign flips per pairwise comparison).
   - Holm-Bonferroni step-down multiplicity correction across all hypothesis families.
   - 95% percentile bootstrap confidence intervals ($2,000$ bootstrap replicates).
