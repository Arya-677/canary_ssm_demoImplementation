# COMPARATOR COMPARISON ADDENDUM: METHODOLOGICAL SEPARATION & FIDELITY AUDIT

- **Document Version**: 1.0
- **Governing Specification**: Supplemental Addendum (Sections C, D, E)

---

## 1. Methodological Separation of Comparison Panels

To prevent improper ranking of fundamentally different software abstractions, results are reported across three distinct methodological panels:

- **Panel A: Statistical Detection Methods**
  - Evaluates `hier_ssm`, `indep_ssm`, `pooled_ssm`, `no_inertia_ssm`, `adj_cusum`, `glr_window`, and `kayenta_judge`.
  - Matched on exact null rollout-level false alert budget (target $\alpha=0.05$).
  - Primary metric: Horizon-capped time-to-success (H=45 and H=120).
- **Panel B: Operational Metric/SLO Rules**
  - Evaluates `slo_threshold` as a simple fixed-threshold operational heuristic.
  - Primary metric: Threshold sensitivity, decision cadence, and false alert trade-offs.
- **Panel C: Progressive Rollout Decision Policies**
  - Evaluates `argo_policy` (failureLimit tracking) and `flagger_policy` (cumulative failure budget and progressive traffic shifting).
  - Primary metric: Time to protective pause/rollback, missed harmful rollouts, and action semantics.

---

## 2. Investigation of Argo vs Flagger Outputs

In `external_benchmark_summary.csv`, `argo_policy` and `flagger_policy` reported identical power (67.43%), FAR (5.33%), and delay (51.98 min).
- Both policies track cumulative positive standardized contrast $C(t) = \sum_{s=t0}^t \mathbf{1}\{z_s > 0\}$.
- Under null order-statistic calibration, dividing $C(t)$ by 3 (Argo) vs 5 (Flagger) scales the threshold proportionally, resulting in the exact same binary alarm condition.
- In `COMPARATOR_ACTION_TRACES.csv`, their discrete state traces and actions are properly distinguished: Argo pauses progression on breach, whereas Flagger shifts traffic percentages and triggers deployment rollback.
