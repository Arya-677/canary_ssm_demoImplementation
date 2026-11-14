# Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

**Authors:** [AUTHOR INPUT REQUIRED: Primary Investigator, Collaborators]  
**Affiliation:** [AUTHOR INPUT REQUIRED: Institution / Department]  
**Correspondence:** [AUTHOR INPUT REQUIRED: Contact Email]  
**Code & Data Archive:** `https://github.com/Arya-677/canary_ssm_demoImplementation`  

---

### Abstract

Progressive canary deployments are fundamental to cloud resilience, allowing operators to test software builds on a subset of instances before wide release. However, detecting performance degradation in live canary telemetry is complicated by environmental confounders: diurnal workload surges, background batch tasks, network throttling, and host-level heterogeneity. Classical sequential monitoring algorithms (CUSUM, EWMA, Sequential GLR) lack host-level hierarchy and latent state memory, causing false-alert rates to escalate under non-Gaussian noise (surpassing 85% in stress testing). 

In this work, we present an empirical evaluation of a **hierarchical Gaussian state-space model** that monitors canary health by decoupling shared workload drift (via pre-period regression and factor extraction) from fleet-level and class-level latent degradation states. Decision thresholds are calibrated via finite-sample order statistics on exchangeable null rollouts, guaranteeing exact false-alert budgets (Gate G2, Beta-Binomial $p \ge 0.01$). 

Benchmarked across 9,600 simulated canary rollouts and evaluated on held-out test suites, our findings reveal:
1. **Fleet Detection Speedup:** Hierarchical state-space modeling reduces mean horizon-capped detection delay on correlated fleet anomalies to **15.57 min**, a statistically significant **2.53 min advantage** over unpooled models ($p = 0.0012$) and a **17.81 min advantage** over sequential GLR.
2. **The Localized Shrinkage Trade-Off:** When defects are isolated to a single canary host, hierarchical shrinkage imposes a **+9.46 min detection delay penalty** ($30.89\text{ min}$ vs $21.43\text{ min}$ for unpooled filters).
3. **Robustness Under Heavy-Tailed Telemetry:** Under Student-$t$ noise ($df=3$), Kalman state smoothing bounds false alerts to **6.0%** (with 99.67% power), whereas classical windowed GLR false alerts explode to **85.7%**.
4. **Unsupported Secondary Mechanisms:** Two-scale class-level inertia states (H2) and multi-step confirmation hysteresis (H3) failed to provide practical benefits beyond fleet-level filtering.

These results define the operational boundaries of state-space filtering in continuous deployment infrastructure: hierarchical smoothing provides substantial protection against correlated environmental noise, but must be paired with extreme-value detectors to catch isolated single-host failures.

---

### 1. Introduction

Continuous software delivery requires releasing incremental changes into production environments hundreds of times per day. To prevent catastrophic outages, engineering organizations employ canary rollouts: routing a small percentage of production traffic (e.g., 5% to 10%) to a canary cluster serving the candidate build while the control cluster continues running the baseline build \cite{davidovic2018canary}.

Despite widespread adoption, automated canary analysis remains plagued by false alarms and slow detection:
1. **Confounded Metric Streams:** Service response times are heavily influenced by diurnal traffic patterns, shared cache warming, and external service latencies. A simple contrast between canary and control metrics is frequently contaminated by unequal load distributions or cluster-wide workload step shifts.
2. **False-Alarm Inflation Under Noise:** Classical sequential change-point detectors (e.g., CUSUM \cite{page1954continuous}, EWMA \cite{roberts1959control}, and Sequential GLR \cite{lorden1971procedures}) assume stationary, well-behaved Gaussian telemetry. When telemetry exhibits heavy tails or bursty dropouts, classical false-alarm rates increase uncontrollably.
3. **The Uncalibrated Budget Problem:** Industrial tooling (e.g., Netflix Kayenta \cite{kayenta2018netflix}) uses heuristic windowed non-parametric tests that lack formal finite-sample false-alarm guarantees.

#### Research Question
> **Can hierarchical state-space smoothing decouple shared environmental confounders to detect harmful canary rollouts faster than classical detectors at an identical, calibrated false-alert budget?**

---

### 2. Related Work

Our work unifies four established statistical methodologies:
- **Automated Canary Analysis Systems:** Google CAS \cite{davidovic2018canary} and Netflix Kayenta \cite{kayenta2018netflix} perform heuristic metric comparisons over batch windows. They lack recursive temporal state estimation and dynamic covariate adjustment.
- **Sequential Change-Point Detection:** Page's CUSUM \cite{page1954continuous}, Lorden's GLR \cite{lorden1971procedures}, and Xie & Siegmund's multi-sensor GLR \cite{xie2013sequential} provide optimal detection delay for independent streams under Gaussian assumptions, but do not model latent hierarchical fleet structures.
- **Dynamic Linear Models (DLMs) & State-Space Filtering:** West & Harrison \cite{west1997bayesian} and Stock & Watson \cite{stock2002forecasting} establish the foundations of latent factor decomposition and Kalman filtering. We adapt this architecture to canary contrast tracking.
- **Conformal and Order-Statistic Calibration:** David & Nagaraja \cite{david2003order} provide the finite-sample exchangeability theory underpinning our Gate G2 calibration protocol.

---

### 3. Mathematical Model & System Architecture

#### 3.1 Nuisance Estimation and Contrast Tracking
Telemetry $y_{it}$ is modeled on the logarithmic scale $z_{it} = \log y_{it}$. Nuisance parameters ($\mu_i, \beta_i, \boldsymbol{\lambda}_i$) are estimated strictly on pre-rollout telemetry ($t \le 180$):
$$\tilde{z}_{it} = z_{it} - \hat{\mu}_i - \hat{\beta}_i w_t$$
where $w_t$ is observed cluster workload. Residualized control telemetry is decomposed into leading dynamic factors $\hat{\mathbf{f}}_t$ via PCA, yielding the adjusted contrast vector $\mathbf{e}_t = \tilde{\mathbf{z}}_{\text{canary}, t} - \hat{\boldsymbol{\Lambda}}_{\text{canary}} \hat{\mathbf{f}}_t$.

#### 3.2 Hierarchical State Space
The latent state vector decomposes into fleet-wide effect $a_t$ and sum-to-zero class deviations $\boldsymbol{\delta}_t$:
$$\mathbf{x}_t = \begin{bmatrix} a_t \\ \boldsymbol{\delta}_t \end{bmatrix}, \quad \mathbf{x}_t = \mathbf{F} \mathbf{x}_{t-1} + \mathbf{q}_t, \quad \mathbf{e}_t = \mathbf{H}_t \mathbf{x}_t + \mathbf{v}_t$$
State estimation is computed recursively using the stabilized Joseph-form Kalman update.

#### 3.3 Posterior Harm Probability & Persistence
The marginal posterior distribution yields instantaneous harm probability against threshold $a^* = \log(1.03)$:
$$p_t = P(a_t \ge a^* \mid \mathbf{e}_{1:t}) = \Phi\left(\frac{\hat{a}_{t|t} - a^*}{\sqrt{[\mathbf{P}_{t|t}]_{1,1}}}\right)$$
The persistence score at depth $m$ tracks $S_t^{(m)} = \min_{j=0..m-1} p_{t-j}$.

---

### 4. Experimental Methodology

- **Simulation Fleet:** $N = 100$ hosts (10 canary, 90 control), 2 classes, 300 minutes total duration.
- **Preregistered Study (`study_inertia`):** 16 scenarios $\times$ 300 paired rollouts = 9,600 rollouts (240,000 policy evaluations).
- **Held-Out Test Suited (`plain_final`, `step_final`):** 1,000 paired rollouts (2,000 rollouts) evaluated strictly once.
- **Statistical Inference:** Paired sign-flip permutation tests (5,000 permutations) with Holm-Bonferroni FWER control within hypothesis families.

---

### 5. Empirical Results

#### 5.1 Primary Test Evaluation (Unseen Plain Test Set)
Refer to Table \ref{tab:plain_final} and Figure \ref{fig:delay_comparison}.
- `hier_ssm` achieved a mean horizon-capped detection time of **15.57 min** and a miss rate of **5.11%**.
- Unpooled SSM (`indep_ssm`) required **18.10 min** (paired difference: $-2.53\text{ min}$, 95% CI $[-3.98, -0.99]$, $p = 0.0012$).
- Sequential GLR (`glr_window`) required **33.38 min** (miss rate 12.30%).
- Classical CUSUM (`adj_cusum`) required **44.16 min** (miss rate 15.50%).

#### 5.2 The Shrinkage Penalty on Localized Defects (H1 Cost Check)
Refer to Figure \ref{fig:pooling_contrast}.
- In `broad_fleet`, hierarchical pooling accelerated detection by **-5.39 min** (Holm $p = 0.011$).
- In `class_wide`, pooling accelerated detection by **-4.82 min** (Holm $p = 0.011$).
- In `single_host_persistent`, hierarchical shrinkage delayed detection by **+9.46 min** ($30.89\text{ min}$ vs $21.43\text{ min}$, Holm $p = 0.011$), confirming that pooling suppresses isolated defects.

#### 5.3 Multi-Stressor Robustness
Refer to Table \ref{tab:robustness} and Figure \ref{fig:heavytail}.
- Under Student-$t$ noise ($\nu = 3$), `glr_window` false-alert rates escalated to **85.7%** and `adj_cusum` to **12.7%**.
- `hier_ssm` preserved false-alarm control (**6.0%**, Gate G2 compliant) and achieved **99.67%** power.

#### 5.4 Negative Findings on Secondary Hypotheses
- **H2 (Two-Scale Dynamics):** The two-scale class inertia model (`hier_ts`) showed no statistical difference from single-scale fleet filtering ($\Delta = -0.18\text{ min}$, $p = 0.42$; all CIs within $\pm 1.0\text{ min}$).
- **H3 (Decision Hysteresis):** Requiring confirmation depth $m \ge 3$ reduced false alarms on isolated spikes, but delayed detection on weak persistent harm by $+4.12\text{ min}$ (exceeding the 3.0 min tolerance).

---

### 6. Discussion & Practical Implications

The empirical results define clear design principles for automated canary deployment infrastructure:
1. **When to Pool:** Hierarchical pooling is strongly indicated for distributed services where software defects manifest across multiple instances (e.g., fleet-wide code regressions, class-specific architecture bugs).
2. **When Not to Pool:** For localized instance defects (e.g., bad local NVMe drive, isolated memory leak), hierarchical models should be accompanied by an unpooled extreme-value detector (e.g., `topk_cusum`).
3. **Robustness Advantage:** The primary practical justification for state-space filtering over classical sequential baselines is not marginal speedup in clean environments, but **extreme resilience to non-Gaussian measurement noise and telemetry dropouts**.

---

### 7. Limitations & Non-Claims

1. **Simulation Prototype:** All data are synthetic; industrial production validation in shadow mode is required before real deployment.
2. **Univariate Latency:** Multi-metric joint covariance calibration is deferred to future work.
3. **No Causal Attribution:** Filtering estimates are statistical projections, not causal proofs.
4. **No Novel Model Family:** The architecture adapts classical DLMs to canary monitoring; novelty claims are strictly disclaimed.

---

### 8. Conclusion

We evaluated hierarchical Gaussian state-space models for automated canary rollout decisions against classical sequential detectors under realistic cloud telemetry confounders. With exact finite-sample order-statistic calibration, the hierarchical filter reduces detection delay on fleet-wide regressions by over 17 minutes compared to classical GLR and provides robust false-alert protection under heavy-tailed noise. However, operators must account for a 9.5-minute shrinkage penalty when defects are isolated to single nodes.
