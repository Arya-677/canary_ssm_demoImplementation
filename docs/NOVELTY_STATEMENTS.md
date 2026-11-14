# Formal Novelty Statements (Gate G4 / Addendum A2 / WP-7.3)

_Formulated strictly from empirical verdicts in `docs/V3_RESULTS_INERTIA.md` and Phase 4 test evaluations. Complies with Part 0 Rule 7 and Addendum J1._

---

## 1. Primary Research Contribution Statement

> **"This work establishes a rigorous, distribution-free methodological integration and comprehensive empirical benchmark evaluating hierarchical state-space models (SSMs) against classical sequential change-point detectors (CUSUM, EWMA, GLR) and non-parametric canary judges for automated software deployment decisions.**
> 
> **By formulating rollout safety as a sequential stopping problem on fleet telemetry, we demonstrate that order-statistic calibration on $B \ge 2,000$ exchangeable null sequences provides exact finite-sample false-alarm rate control ($\alpha = 0.05$) under continuous sequential monitoring. On unsealed test data, hierarchical partial pooling significantly reduces detection delay on fleet-wide regressions (-7.80 min on class-wide events, -4.52 min on broad fleet faults, $p_{\text{holm}} = 0.0110$), but incurs a quantifiable penalty on isolated host failures (+9.46 min delay, 5.33 pp lower power), formally demonstrating that pooling suppresses local faults."**

---

## 2. Explicit Negative Findings & Delimited Non-Claims

In accordance with Gate G4, PREREGISTRATION V3, and AFML scientific integrity standards, the following explicit non-claims are documented:

1. **No Claim of a Novel "Two-Scale Cross-Level Inertia" Model Family (H2 Not Supported):**
   - Hypothesis H2 was evaluated on 300 rollouts per scenario across 5 targeted slow-drift, recovery, and mixed-speed scenarios.
   - Under candidate budget parity ($28 \le 42$) and formal nesting verification, cross-validation grid search selected the nested boundary parameterization ($\text{prior\_h\_ratio} = 1.0$, $\rho = 0.999$).
   - Across all target scenarios, the mean capped-time difference between `hier_ts` and `hier_ssm` was $0.000$ minutes (95% CI $[0.000, 0.000] \subset [-1.0, 1.0]$).
   - In accordance with Addendum J1, the term **"inertia contribution" is not supported and is not claimed**. The architecture is classified as methodological reuse of hierarchical linear-Gaussian state-space filtering.

2. **No Claim of Unilateral Dominance Over Classical Baselines (H5 Not Supported):**
   - While SSMs achieved lower horizon-capped detection times than the best classical baseline in 9 of 11 event scenarios ($p_{\text{holm}} = 0.0440$), SSMs were significantly slower in two scenarios:
     - `slow_drift_3host`: SSM was slower by $+19.58$ minutes ($p_{\text{holm}} = 0.0440$) compared to windowed GLR.
     - `step_plus_harm`: SSM was slower by $+14.87$ minutes ($p_{\text{holm}} = 0.0440$) compared to windowed GLR.
   - Because the preregistered criterion required faster in $\ge$ half and slower in none, Hypothesis H5 failed.

3. **No Claim of Decision Hysteresis Suppressing Non-Event Alarms Without Delay Penalties (H3 Not Supported):**
   - Testing consecutive-crossing hysteresis ($m \in \{1, 3, 5, 10, 15\}$) demonstrated that while order-statistic calibration preserves the marginal $\alpha = 0.05$ budget for all $m$, increasing $m$ failed to achieve a $\ge 50\%$ relative reduction in non-event disturbances (max reduction 20.8% at $m=15$).
   - Concurrently, increasing $m$ inflated detection delay on weak persistent faults by $+7.34$ minutes ($> 3.0$ min limit).

4. **No Claim of Production Readiness or Multivariate Telemetry:**
   - The current benchmark evaluates simulated scalar latency telemetry with dynamic factor covariate adjustments.
   - It does not demonstrate multivariate observation scaling across CPU, memory, error rates, and distributed trace metrics (deferred to future work in Phase 6).
