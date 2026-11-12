# READ FIRST: docs/Canary_SSM_Change_Plan.pdf (revision 3) is the governing work plan. Part 0 rules override anything older here.

# Rules for the coding agent (read before every task)

You are extending a research codebase. Correctness and leakage-safety outrank speed.

## Hard rules (never break; tests enforce most of them)
1. Detector code (`factor, preprocess, baselines, kalman, hierarchy, decision`) must NEVER import `simulate.Truth`,
   `metrics`, or read `*_truth` files. Only `metrics.py` / `experiments.py` evaluator paths may.
2. Data roles are separate: dev (fit + hyperparameter selection) / calibration (thresholds) / null_validation
   (audit only) / test (final, unseen until freeze). Never tune on null_validation or test. If a frozen policy
   changes, version it and generate FRESH validation data; record the failed version.
3. Causality: score at time t may use data <= t only. Per-host mu/beta/lambda come from the pre-period only.
4. Report all methods at the same calibrated false-alert budget. Never report conditional delay alone; show
   misses, premature alarms and capped time-to-success.
5. Do not invent results. All numbers come from executed runs saved to CSV; figures come from CSVs.
6. Do not weaken, delete, or "fix" a test to make it pass. If a test seems wrong, stop and explain why.
7. A statistical model is exact only conditional on fixed parameters; do not claim causal attribution, sparse
   Bayesian inference, or novelty.

## Lessons from the six pilot experiments (do not repeat)
8. Calibrate on the distribution you evaluate on. Calibrating CUSUM on step-contaminated nulls inflated its threshold ~2x and
   erased its power. Per-family thresholds need a CAUSAL runtime rule that picks the family; none exists yet.
9. PASS/FAIL is computed from numbers (`report.calibration_gate`), never typed. NOTE: the n >= 400 / upper-bound-8% rule in the current
   code is SUPERSEDED by gate G2 in docs/Canary_SSM_Change_Plan.pdf (exact beta-binomial validity test, B and n of at least 2000;
   a valid method fails the old rule 29% of the time at B = n = 500). Implement WP-A2 and WP-C3 before trusting any gate output.
10. A root-cause metric must be able to fail. Use SD/RMS of per-rollout post-minus-pre residual shifts, not signed means.
11. Do not call a detector robust to missingness without showing its power and abstention (`table_abstention.csv`).
12. Never pick K, thresholds, or hyperparameters using the true affected count or any validation/test data.
13. The shared-step failure is OPEN: no adjustment mode passes the gate (docs/SANDBOX_AUDIT.md). Do not paper over it.
14. Delay/power comparisons are valid only between methods inside the calibration gate.

## Workflow per task
Read the relevant section of the handbook + docs/DESIGN_DECISIONS.md -> write the smallest change ->
add an independently computed test -> `python -m pytest -q` -> show changed files and commands run.
AI-written tests can repeat the same maths error: use hand-computed fixtures or a separate reference
implementation (the Kalman filter is checked against statsmodels).

## Open work (in priority order; each is optional and separately estimated)
A. Run the tests, scripts/smoke.sh, then scripts/audit_quick.sh (frozen calibration audit, ~15-25 min).
B. Experiments 7-9 (see the brief, Section 7): calibration audit + causal regime rule; heterogeneous beta, phi_e, heavy tails;
   equal-false-alert benchmark with combined detectors. Gate on gate_status.json.
C. Xie-Siegmund mixture-GLR comparator (needed before any claim against specialised sparse detectors).
D. Monte Carlo release probability with reported MC error. E. Consecutive-crossing policy calibrated by replay.
F. Clean-environment rerun, requirements.lock, limitations.md, small notebook demo.
