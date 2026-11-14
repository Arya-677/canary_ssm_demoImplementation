# Three-level architecture analysis (Addendum C)
Levels: L1 host (a_i), L2 group (g_c), L3 deployment (release decision).
| Option | State | Transition | Observation | Identifiability | Cost | Missing data | Verdict |
|---|---|---|---|---|---|---|---|
| A existing 2-component hier | θ (n) + e (n) | diag(ρ),diag(φ) | [L I] | host vs group identified only through repeated, class-structured evidence; sum-zero fixes the split | O((2n)³)/step, n=10 | native (skip update) | **baseline** |
| B host/group + release-level risk aggregation | as A | as A | as A | L3 is a *function* of L1/L2 posteriors | same | native | **this is what the repo does** (`log max_i P(a_i>κ)` then order-statistic threshold) |
| C 3-level latent (deployment state) | A + scalar d_t | d_t=ρ_d d_{t−1}+w; g driven by d | d unobserved except through g | d vs g confounded (one scalar behind G group coordinates) | +1 state | native | **rejected**: unidentifiable extra state; aggregation is calibrated, which a latent state would not be |
| D adaptive cross-level inertia | hier_ts | asymmetric ρ,σ,prior | same | adds 3 knobs; identifiable only if scenarios separate time scales (mixed-speed) | = A | native | **implemented as `hier_ts`**; adaptive (state-dependent) form not exact → not built |
Pooling checks (C3): `tests/test_v3_changes.py::test_sum_zero_*` (balanced, 8/2, 9/1, singletons) and `scripts/partial_pooling_audit.py`
(prior-level leakage of a single-host effect to classmates as a function of prior_h_ratio). Singleton: no local coordinate, so its
effect is the class effect (documented). Label errors / unknown groups / changing membership: **experiments** in Phase 5
(`label_error` knob exists; membership change is not simulated — listed as unimplemented).
Diagram: y_i,t ← a_i,t + e_i,t ; a_i,t = g_{c(i),t} + b_i,t ; (g,b) AR; release score = log max_i P(a_i>κ) → calibrated threshold → PAUSE/CONTINUE.
