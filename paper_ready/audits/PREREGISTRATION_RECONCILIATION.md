# PREREGISTRATION RECONCILIATION: ORIGINAL CRITERIA VS LATER ANALYSES

- **Audit Date**: 2026-11-15
- **Governing Specification**: *Canary SSM V3 Change Plan (Rev 3)* & *PREREGISTRATION_V3.md*

---

## 1. Confirmatory Hypotheses Reconciliation (H1 to H5)

| Hypothesis | Preregistered Confirmatory Target | Observed Primary Evidence | Preregistration Status | Final Paper Classification |
|---|---|---|---|---|
| **H1: Hierarchical Pooling** | Capped TTS reduction over `indep_ssm` at $m=1$ under matched FAR | Class-wide: -7.80 min ($p=.011$); Broad-fleet: -4.52 min ($p=.011$); Single-host persistent: +9.46 min penalty | **PARTIALLY SUPPORTED** | Core Trade-off: partial pooling accelerates broad/correlated faults but penalizes isolated local faults. |
| **H2: Two-Scale Dynamics** | Incremental capped TTS benefit of `hier_ts` over `hier_ssm` | Mean difference 0.000 min, CI [0, 0] across 5 scenarios; nested asymptote selected | **NOT SUPPORTED** | Negative Finding: two-scale cross-level dynamics provide no incremental detection power. |
| **H3: Hysteresis Alert Reduction** | $\ge 50\%$ reduction in non-event alerts with $\le 3$ min delay penalty | Maximum observed alert reduction was 20.8%; weak persistent delay was +7.34 min | **NOT SUPPORTED** | Negative Finding: fixed hysteresis policy fails the preregistered 50% target. |
| **H4: Recovery Stability** | Reduced time to return to normal state post-recovery | No recovery delay improvement; recovery tracking added +4.81 min dwell time | **NOT SUPPORTED** | Negative Finding: recovery tracking introduces decision latency rather than acceleration. |
| **H5: Classical Baseline Dominance** | Universal superiority of SSM over CUSUM and GLR baselines | SSM faster in 9/11 event scenarios, but slower in slow drift (+19.58m) and step (+14.87m) | **NO UNIVERSAL DOMINANCE** | Scenario-Dependent: SSM excels on abrupt/correlated faults; classical baselines win on gradual drift. |

---

## 2. Chronology of Study Generations

| Protocol Generation | Commit SHA | Scenario Count | Sample Size | Primary Methods | Hypotheses / Focus | Status |
|---|---|---|---|---|---|---|
| **Stage 1 Baseline** | `e6585ba` | 16 Scenarios | $N=9,600$ | `hier_ssm`, `indep_ssm`, `cusum`, `glr` | Pipeline integrity, smoke tests, scalar Kalman | Baseline verified |
| **Stage 2 Studies** | `11f5e11` | 12 Scenarios | $N=7,200$ | `hier_ssm`, `hier_ts`, `indep_ssm`, `pooled_ssm` | H1-H5 confirmatory tests, Gate G2 audit | Confirmatory audit frozen |
| **Stage 3 Evaluation** | `329bcbc` | 16 Scenarios | $N=9,600$ | 24 candidate methods & ablations | Final plain & step regime test evaluations | Final test frozen |
| **External Validation**| `06d6a05` | 26 Scenarios | $N=2,600$ | 9 candidate methods + external comparators | Kayenta, Argo, Flagger, SLO, stress tests | Confirmatory benchmarking |
