# COMPARATOR FIDELITY AUDIT & DOCUMENTATION MAPPING

- **Audit Date**: 2026-11-15
- **Governing Specification**: Supplemental Addendum (Sections A & B)

---

## 1. Upstream Documentation Mapping & Fidelity Classification

Every comparator implemented in the repository has been audited against its official documentation:

1. **Kayenta / Spinnaker Judge (`canary_ssm/comparators/kayenta_judge.py`)**:
   - *Upstream Reference*: [Spinnaker Canary Judge Documentation](https://spinnaker.io/docs/guides/user/canary/judge/)
   - *Fidelity Classification*: **Inspired abstraction only**
   - *Implemented*: Non-parametric Mann-Whitney U test, directionality check, effect-size threshold, rolling evaluation window.
   - *Omitted*: Multi-metric score weighting, Datadog/Prometheus API connector, judge DAG execution.
   - *Permitted Paper Wording*: "a Kayenta-inspired non-parametric statistical judge approximation".

2. **SLO Threshold Comparator (`canary_ssm/comparators/slo_threshold.py`)**:
   - *Upstream Reference*: [Google SRE Workbook: Canarying Releases](https://sre.google/workbook/canarying-releases/)
   - *Fidelity Classification*: **Faithful within the simulator**
   - *Implemented*: Rolling standardized difference-in-means between canary and control groups, strict threshold comparison.
   - *Permitted Paper Wording*: "a rolling standardized contrast SLO threshold baseline".

3. **Argo Rollouts Policy (`canary_ssm/comparators/argo_policy.py`)**:
   - *Upstream Reference*: [Argo Rollouts Analysis Documentation](https://argo-rollouts.readthedocs.io/en/latest/features/analysis/)
   - *Fidelity Classification*: **Inspired abstraction only**
   - *Implemented*: Cumulative and consecutive failureLimit tracking (AR-1, AR-3, AR-5).
   - *Omitted*: Kubernetes controller reconciliation, AnalysisTemplate CRD, container traffic routing.
   - *Permitted Paper Wording*: "an Argo Rollouts-style failureLimit analysis policy abstraction".

4. **Flagger Policy (`canary_ssm/comparators/flagger_policy.py`)**:
   - *Upstream Reference*: [Flagger How It Works Documentation](https://docs.flagger.app/usage/how-it-works)
   - *Fidelity Classification*: **Inspired abstraction only**
   - *Implemented*: Cumulative failed check budget (maxFailedChecks), progressive step progression abstraction.
   - *Omitted*: Istio/Envoy traffic splitting, service mesh reconciliation.
   - *Permitted Paper Wording*: "a Flagger-style progressive metric check policy abstraction".

---

## 2. Deterministic Semantic Tests Summary

The 8 deterministic semantic tests specified in Addendum Section B (`tests/test_comparator_semantics.py`) are fully passing:
- `KAY-01`: Independent Mann-Whitney U calculation, direction, and critical failure verdict (PASSED).
- `KAY-02`: Tie handling, insufficient sample counts (<5 samples -> NODATA), and NaN handling (PASSED).
- `ARGO-01`: Deterministic state trace across failureLimit (AR-3) and consecutive failure resets (PASSED).
- `ARGO-02`: Missing and errored measurement handling without state corruption (PASSED).
- `FLAG-01`: Step progression and cumulative failure threshold breach at maxFailedChecks=5 (PASSED).
- `FLAG-02`: Cumulative failure count retention across subsequent clean checks (PASSED).
- `SLO-01`: Boundary behavior (below, at, above threshold) and window averaging (PASSED).
- `COMMON-01`: Online streaming prefix invariance across all comparators (PASSED).
