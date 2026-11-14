# Preregistration V3 (frozen when Phase 3 starts; edits afterwards must be logged as amendments with a date)
Design: `study_inertia`. Calibration: B=2000 nulls per regime (seed block study_inertia_cal); validity audit on 2000 separate nulls
(study_inertia_val, exact Beta-Binomial, bb_p>0.001); scenarios on study_inertia_eval, n_harm paired rollouts per scenario (same seeds for all methods).
Methods: indep_ssm, hier_ssm, hier_ts, adj_cusum, glr_window. Hysteresis m ∈ {1,3,5,10,15} (predeclared, same for all methods;
exit rule n_clear=5, hyst_frac=0.5, untuned; no emergency offset in the primary analysis).
Primary metric: mean horizon-capped detection time on event rollouts (misses and premature = remaining horizon), paired by rollout.
Inference: two-sided paired sign-flip test (5000 perms) per scenario × contrast; Holm across ALL rows of the contrast table within a hypothesis.
Effect sizes are mean capped-time differences in minutes (negative = first configuration faster) with paired-bootstrap CI.
Contrasts: C1 hier_ts vs hier_ssm (same m); C2 hier_ssm vs indep_ssm; C3 (method,m) vs (method,1); C4 SSM vs classical (same m).
Calibration cells failing bb_p ≤ 0.001 are excluded from claims and reported.

H1 Pooling helps: C2 at m=1 negative with Holm p<0.05 in ≥2 of {weak_persistent_3host, class_wide, broad_fleet}. Cost check:
  in `single_host_persistent` C2 is reported; if hier_ssm is slower by >3 min or power lower by >5 pp, report "pooling suppresses local faults".
H2 Cross-level (two-scale) inertia adds value beyond persistence: C1 at m=1 negative with Holm p<0.05 AND |diff|≥1 minute in ≥1 of
  {slow_drift_3host, mixed_fast_slow, regression_recovery, partial_recovery, weak_persistent_3host}; AND in every other event scenario power
  not lower than hier_ssm by >2 pp; AND its calibration cell passes. If the C1 CI lies within ±1 minute in all of these → NOT SUPPORTED
  ("no practical difference"); otherwise INCONCLUSIVE. Only SUPPORTED permits the word "inertia contribution" (Addendum J1).
H3 Decision hysteresis reduces false pauses: for hier_ssm there is an m>1 such that (a) alert rate on harm rollouts WITHOUT an event
  (`harm_rollout_noevent_alert_rate`, scenarios iso_spike_1host and short_3host pooled) falls ≥50 % relative to m=1 and (b) mean capped time
  on weak_persistent_3host rises ≤3 min. First-pause FAR is calibrated to 5 % for every m by construction; benefits are about non-event disturbances.
H4 (exploratory, descriptive) Stability: hier_ts lowers mean recovery delay vs hier_ssm by ≥5 min at m=1 in both regression_recovery and partial_recovery; also report reversals and time paused.
H5 Classical comparison: SSM (hier_ts or hier_ssm) faster than the better of adj_cusum/glr_window with Holm p<0.05 in ≥ half the event scenarios and slower (Holm p<0.05) in none.
Reported regardless: runtime per method (table_runtime.csv), step-regime false-alert behaviour, every contradicted hypothesis.
Not claimed: production readiness; generalisation beyond the simulator; multivariate benefit.
