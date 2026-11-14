# Inertia model designs (Addendum B2) — derivations, decisions, status

Notation: host effect a_t = L θ_t, θ_t=[g;b] (G class coordinates, n−G sum-zero local coordinates), θ_t = diag(ρ)θ_{t−1}+w_t,
w_t~N(0,diag(σ²)); y = a + e + noise, e_{i,t}=φ_i e_{i,t−1}+η (nuisance AR(1)). Existing code: ρ_g=ρ_h, σ_h=σ_g (ratio 1).
Stationary prior covariance of hosts i,j in one class of size m: ps²... = σ_g²/(1−ρ_g²) + σ_h²/(1−ρ_h²)(δ_ij − 1/m).

## Three mechanisms (kept separate)
M1 latent persistence (ρ). M2 cross-level inertia (different time scales/variances per level). M3 decision inertia (hysteresis).
M3 is implemented in `decision.persist_score` and is independent of any latent model.

## Implemented: Design T — two-scale hierarchy (`hier_ts`, `TwoScaleParams`)
Free: ρ_g, ρ_h, σ_g, r_σ=σ_h/σ_g, prior_sd, r_p = prior_sd_h/prior_sd_g.
* Interpretation: with ρ_h<ρ_g and r_σ>1 the group level is slow and low-volatility, local deviations fast. A brief single-host
  disturbance is absorbed by the local coordinate; only evidence that is **coherent across hosts and time** moves the group
  coordinate. r_p<1 = stronger partial pooling (hosts shrink to class), r_p>1 = weaker.
* Exactness: linear-Gaussian ⇒ exact Kalman filter, same cost as `hier_ssm` (state dim 2n).
* Nesting: ρ_g=ρ_h, r_σ=r_p=1 gives `hier_ssm` bit-for-bit (test). Therefore any gain is attributable to the asymmetry.
* Distinguishability: from ordinary persistence (needs ρ_g≠ρ_h or r_σ≠1 or r_p≠1); from hysteresis (acts on the latent posterior,
  not on the decision). Evaluated crossed with hysteresis in `study_inertia` (contrast C1 at every m).
* Honest status: **engineering/modification of an established hierarchical random-effects model; not a new model family.**
  Contribution is conditional on preregistered H2 (see PREREGISTRATION_V3).

## Not implemented (with reasons)
**Alt A — evidence-conditioned group transition** g_t = A_g g_{t−1} + B_g q(E_t,…). (i) E_t is a function of the *posterior* of x,
so the group state would be driven by data already used to infer x: double counting, not a generative model. (ii) If q is linear,
g_t = A_g g_{t−1}+B_g x̄_{t−1}+w with x_{i,t}=A_h x_{i,t−1}+B_h g_{t−1}+w is a latent VAR(1); g is observed only through x, so
(A_g,B_g,B_h) are weakly identified and the system is equivalent to second-order (AR(2)-type) dynamics of x̄ — a "momentum" model,
useful for ramps but a different hypothesis. (iii) A nonlinear q breaks Gaussianity (needs UKF/particle filter). Decision: not built;
if ramps prove decisive in Phase 3, a local-linear-trend (level+slope) group state is the principled exact-KF version to propose.
**Alt B — fast+slow effect** x=f+s. f is observationally identical to the existing nuisance e_{i,t} (same AR(1) observed with the same
noise); the harm event is defined on the slow part only. Adding f to the *effect* double-counts nuisance and lets noise
trigger harm probability. The existing model already is a two-time-scale model (fast nuisance + slow effect). Not built.
**Alt C — state-dependent Q** (e.g., scale-mixture innovations). Not exactly Gaussian: needs Gaussian-sum/IMM or particles; cost grows
with the number of regimes. Candidate future work only if T fails on mixed-speed scenarios.
**B4 regulariser** λΣ‖x_t−x_{t−1}‖² is the MAP form of a Gaussian random walk (σ_w² ∝ 1/λ) = `hier_rw`. Duplicate; not built.
