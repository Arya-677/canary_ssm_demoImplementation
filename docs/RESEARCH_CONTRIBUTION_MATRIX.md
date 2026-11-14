# Research contribution matrix (Addendum A2). "Status" cells are to be updated ONLY from preregistered verdicts.
| Component | Established technique | Our implementation | Classification | Potential contribution | Status |
|---|---|---|---|---|---|
| Gaussian SSM / Kalman | Established (Kalman 1960; Durbin & Koopman) | `kalman.py`, tested vs statsmodels | reuse | application + evaluation | tested |
| Hierarchical partial pooling | Established (random effects; Gelman & Hill) | class effect + sum-zero local deviations | reuse/engineering | strength knob `prior_h_ratio` newly tunable | audit CSV + tests; value: H1 |
| AR latent persistence | Established | ρ per level | reuse | interaction with canary detection | H1 (vs persistence) |
| Cross-level inertia | Needs definition | `hier_ts` (two-scale) | modification of established model | asymmetric time scales beyond equal-ρ persistence | **H2 pending** |
| Decision hysteresis | Established (hysteresis / run rules) | `persist_score`, exact order-stat calibration | engineering | exact calibration of m-consecutive rule for ANY score | H3 pending (calibration claim is exact; benefit is empirical) |
| Workload adjustment | Established regression/factor | `factor.py` with factor-uncertainty covariance | engineering | uncertainty-aware integration (β uncertainty NOT yet propagated) | open |
| Sequential release policy | Established | order-statistic calibrated maxima, G2 audit | engineering | calibrated hierarchical release decisions | validity gates |
| Multivariate observations | Established | none | future work | — | deferred (Phase 6) |
| Fast/slow components; state-dep. noise; evidence-conditioned transition | Established ideas | not built (see INERTIA_MODEL_DESIGNS) | rejected/future | — | — |
Default novelty position if H2 fails: "rigorous methodological integration and comparative evaluation", not a new model family.
