# PAPER LIMITATIONS AND CLAIM BOUNDARIES

- **Document Version**: 1.0 (Locked for Publication)
- **Authoritative Date**: 2026-11-15

---

## 1. Permitted Claims

1. **Workload-Adjusted Hierarchical State-Space Formulation**:
   - The paper may claim an engineered, integrated hierarchical state-space monitoring pipeline that separates workload variation via control hosts and estimates host treatment effects via partial pooling.
2. **Conditional Value of Partial Pooling**:
   - The paper may claim that partial pooling significantly accelerates detection of broad, correlated fleet degradation (-4.3 to -7.8 minutes, $p < 0.01$), but incurs a significant detection delay penalty (+9.46 minutes) on isolated single-host failures.
3. **Rigorous Decision-Level Evaluation Framework**:
   - The paper may claim a disciplined evaluation protocol based on exact null order-statistic calibration, Gate G2 validity, and horizon-capped time-to-success.

---

## 2. Prohibited Claims (Strict Boundaries)

1. **NO Universal Superiority**:
   - Do NOT claim that the hierarchical SSM is universally superior to independent SSM, CUSUM, or GLR baselines.
2. **NO Incremental Benefit for Two-Scale Inertia**:
   - Do NOT claim that two-scale cross-level inertia improves detection. H2 was NOT supported.
3. **NO Hysteresis Alert Reduction Claims**:
   - Do NOT claim that the proposed hysteresis settings achieved the preregistered alert reduction. H3 was NOT supported.
4. **NO Direct Real-World Deployment Claims**:
   - Do NOT claim that Kayenta, Argo Rollouts, or Flagger controllers were directly deployed or executed. Label them as simulator approximations.
5. **NO Multivariate Latency Claims**:
   - Do NOT claim multivariate validation; only univariate log-latency was evaluated.
6. **NO Causal Code Attribution**:
   - Do NOT claim that the detector causally proves the code commit caused the regression.
7. **NO Production Readiness**:
   - Do NOT claim production readiness.
