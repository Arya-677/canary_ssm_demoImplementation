# Project Overview: Canary SSM V3
## Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

- **Research Domain:** Automated Software Deployment Safety, Canary Telemetry Monitoring, Sequential Anomaly Detection
- **Codebase:** Python 3.12 (NumPy, SciPy, Statsmodels)
- **Status:** Complete Research Archive & Publication Release
- **Repository Commit:** [`329bcbc`](file:///c:/afml-implementation/)

---

### 1. Executive Summary

Modern cloud infrastructure relies on progressive canary deployments to roll out software changes safely to subsets of instances before global release. However, telemetry streams (e.g., request latency, error rates) in production systems are severely confounded by shared environmental factors: diurnal workload shifts, cluster-wide background jobs, network throttling, and transient host-level noise.

Existing monitoring systems face an unavoidable dilemma:
- **Classical Threshold & Windowing Detectors (e.g., Netflix Kayenta, Prometheus alert rules):** Rely on static thresholds, rolling mean contrasts, or basic Mann-Whitney tests. They frequently trigger premature rollbacks during shared workload surges or miss subtle, slow-creeping degradations.
- **Classical Sequential Change-Point Baselines (e.g., CUSUM, EWMA, Sequential GLR):** Lack latent state memory and host-level hierarchy. Under non-Gaussian telemetry (e.g., heavy-tailed response times or missing telemetry), their false-alarm rates escalate dramatically (up to 85.7% in our stress tests).

**Canary SSM V3** implements and benchmarks a **two-level hierarchical Gaussian state-space model** that tracks latent rollout health by decomposing observed latency into:
1. Shared fleet-wide workload and environmental factors (estimated via pre-period regression and PCA rank reduction).
2. Group-level persistent deployment effects (class-level latent states).
3. Host-specific deviation states and measurement noise.

Coupled with finite-sample order-statistic threshold calibration (Gate G2, Beta-Binomial $p \ge 0.01$) and an automated replay policy, the system provides mathematically bounded false-alert budgets while reducing detection latency on correlated fleet regressions.

---

### 2. Core Research Question

> **Can hierarchical state-space smoothing decouple shared environmental confounders and cross-host correlated degradation to detect harmful canary rollouts faster than classical detectors at an identical, calibrated false-alert budget?**

#### Summary of Empirical Answer:
**Yes, for correlated fleet anomalies; but with a quantifiable shrinkage trade-off.**
- On correlated fleet events, hierarchical pooling (`hier_ssm`) reduces mean horizon-capped detection time to **15.57 min**, achieving a statistically significant **2.53 min advantage** over unpooled models ($p = 0.0012$) and a **17.81 min advantage** over sequential GLR.
- Under heavy-tailed measurement noise ($t(3)$), state-space variance regularizing bounds false alarms to **6.0%**, whereas classical GLR false alarms explode to **85.7%**.
- **Crucial Trade-off (The Cost Check):** When a defect is strictly localized to a single canary host (`single_host_persistent`), hierarchical pooling imposes a **+9.46 min detection delay penalty** because group-level states shrink the localized signal toward zero.

---

### 3. What the Implementation Does (and Does Not Do)

#### What It Does:
- **Synthetic High-Fidelity Simulation:** Simulates paired canary and control fleets across 4 host classes, incorporating diurnal workloads, step shifts, correlated shocks, heavy tails, missingness, and transient noise.
- **Pre-Period Nuisance Estimation:** Fits host-specific baselines $\mu_i$, workload sensitivities $\beta_i$, and factor loadings $\lambda_i$ strictly on pre-rollout telemetry.
- **Recursive Kalman Filtering:** Runs online prediction-correction updates with Joseph-form covariance stabilization and missing-data gap handling.
- **Gate G2 Calibration:** Calibrates decision thresholds using order statistics on $B = 2,000$ exchangeable null rollouts, validated on $n = 2,000$ independent nulls to guarantee false-alert rate $\le 0.075$ at $p \ge 0.01$.
- **Replay Decision Simulation:** Evaluates an advisory automated rollback/recovery policy with adjustable hysteresis confirmation depth $m \in \{1, 3, 5, 10, 15\}$.

#### What It Does Not Do (Preregistered Non-Claims):
- **No Novel Mathematical Model Family:** The core filter is an exact linear-Gaussian Kalman formulation / Dynamic Linear Model (DLM). We claim methodological integration, calibration rigor, and empirical benchmarking—not a novel mathematical filter family.
- **No Production Readiness Claim:** Evaluated exclusively on synthetic benchmarks. It is a research prototype, not an autonomous production gatekeeper.
- **No Multivariate Telemetry Validation:** Evaluated strictly on univariate latency telemetry.
- **No Causal Attribution:** State estimates are conditioned on fixed hyperparameter priors.

---

### 4. Primary Research Findings & Hypothesis Outcomes

In accordance with `docs/PREREGISTRATION_V3.md`:

| Hypothesis | Preregistered Criteria | Result | Empirical Status |
| :--- | :--- | :---: | :--- |
| **H1: Hierarchical Pooling Benefit** | C2 contrast (`hier_ssm` vs `indep_ssm`) negative with Holm $p < 0.05$ in $\ge 2$ fleet scenarios. Cost check: reported if single-host slower by $>3$ min. | $\Delta = -5.39$ min (`broad`), $\Delta = -4.82$ min (`class_wide`), both $p = 0.011$. Single-host penalty $= +9.46$ min. | **SUPPORTED**<br>(with mandatory cost-check caveat) |
| **H2: Two-Scale Inertia Benefit** | C1 contrast (`hier_ts` vs `hier_ssm`) negative with Holm $p < 0.05$ and $\|\Delta\| \ge 1$ min. | $\Delta = -0.18$ min ($p = 0.42$). All 95% CIs within $\pm 1$ min. | **NOT SUPPORTED**<br>(No practical difference) |
| **H3: Decision Hysteresis** | $\ge 50\%$ false pause reduction on non-event spikes with $\le 3$ min capped delay rise on weak harm. | Delay on weak harm rose by $>3$ min ($+4.12$ min at $m=3$). | **NOT SUPPORTED**<br>(Latency cost too high) |
| **H4: Exploratory Recovery Stability** | `hier_ts` lowers recovery delay vs `hier_ssm` by $\ge 5$ min at $m=1$ in recovery scenarios. | $\Delta = 0.00$ min difference in both scenarios. | **NOT SUPPORTED** |
| **H5: Classical Baseline Dominance** | SSM faster than classical baselines in $\ge$ half scenarios and slower in none. | SSM slower in `single_host_persistent` (+9.46 min). | **NOT SUPPORTED**<br>(No universal dominance) |

---

### 5. Repository Structure at a Glance

- [`canary_ssm/`](file:///c:/afml-implementation/canary_ssm/): Core Python package (simulation, Kalman filtering, hierarchy, baselines, decision logic).
- [`artifacts/`](file:///c:/afml-implementation/artifacts/): Frozen V3 model hyperparameters and calibrated decision policies (`model_v3`, `policy_plain_v3`, `policy_step_v3`).
- [`results/`](file:///c:/afml-implementation/results/): Immutable experimental results from Phase 3 (`study_inertia`), Phase 4 (`plain_final`, `step_final`), and Phase 5 (`study_combined`).
- [`docs/final_audit/`](file:///c:/afml-implementation/docs/final_audit/): Comprehensive technical and scientific audit reports.
- [`paper/`](file:///c:/afml-implementation/paper/): Manuscript skeleton, outline, evidence map, publication figures (PNG/SVG), and tables (CSV/MD/TeX).
- [`demo/`](file:///c:/afml-implementation/demo/): Self-contained interactive web prototype (`index.html`) and local Python server (`serve_demo.py`).
- [`review_bundles/`](file:///c:/afml-implementation/): Cryptographically hashed zip bundles for all phases (`P0` through `P7`).
