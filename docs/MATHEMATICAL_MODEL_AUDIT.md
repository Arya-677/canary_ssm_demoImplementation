# Mathematical model audit (Addendum D) — reviewer's reading of the code, with verification status
## 1. Models (all: x_t=F x_{t−1}+w, y_t=H x_t+v, w~N(0,Q), v~N(0,V_t))
Hierarchical (`hier`, `hier_ts`): x=[θ(d=n); e(n)], d=G+(n−G) (class + sum-zero local coordinates). F=blockdiag(diag ρ, diag φ_{c(i)}).
Q=blockdiag(diag σ², diag q_e²). H=[L I_n], L=[C B] (class indicator, orthonormal sum-zero basis). V_t=diag(v_c²)+λλᵀU_t (U_t = workload-adjustment
variance, shared across canaries). P_0 = blockdiag(diag((prior_sd·scale)²), diag(q_e²/(1−φ²))) after the pre-period noise filter.
Missing/ineligible minutes: prediction only. Posterior quantities used: a_i mean/variance ⇒ P(a_i>κ) ⇒ score log max_i.
`indep`: L=I (no sharing). `pooled`: single common effect. Ablations alter ρ,σ,φ,Huber, labels.
## 2. Independent numerical verification — DONE
`test_effect_detector_matches_direct_gaussian_conditioning`: filtering mean and exceedance probability equal direct stacked Gaussian conditioning
(solver written independently of `kalman.py`) to 1e-9, for balanced (2/2), unbalanced (3/1) and 5-host (2/3) class layouts, for hier, hier_ts
(ρ_g≠ρ_h, r_σ=3, r_p=0.4) and indep, with partial and total observation dropout. NOT yet covered: near-singular covariance, Huber, factor U_t>0.
## 3. Identifiability (reviewer's assessment; confirm by experiment)
Group vs local: separable only via class-structured repetition; singleton classes unidentifiable. Workload slope error vs real regression:
partially confounded after a workload step (this is the known step-regime failure mode; not solved by V3). Slow effect vs static offset:
distinguishable only through the pre-period baseline. Fast vs slow effect: not identifiable against nuisance AR (see INERTIA designs).
## 4. Known gaps (do not claim otherwise)
β and loading estimation uncertainty is not propagated; release score is a max of marginals, not a joint probability; effect prior resets at t0.
## 5. Proof: exactness of persistence calibration
Let S_t be the null score path (causal function of the rollout). s_m(t)=min(S_{t−m+1..t}) on eligible runs is a deterministic function of that
path. Hence M_m=max_t s_m(t) is a deterministic function of the rollout, so M_m of the B calibration nulls and of a fresh null are exchangeable under
the same null law. The (k/B)-order-statistic threshold then gives P(M_new > h) ≤ 1−k/(B+1) exactly as for m=1 (existing validity argument).
Pause iff s_m(t)>h for some t ⇔ m consecutive eligible minutes above h. Recovery hysteresis acts after the first pause and cannot change it.
Emergency offset δ: s=max(s_m, S_t−δ) is again a deterministic function of the path (δ predeclared). Needs a second human reader.
