# CHANGELOG V3 (reviewer-made changes; everything else is untouched)
Modified: canary_ssm/hierarchy.py (+TwoScaleParams, prior_scale_vector, branch for prior_h_ratio; legacy path bit-identical),
canary_ssm/experiments.py (TwoScaleParams dispatch in Models.run and _simplicity_key; removed duplicated `adj =` line),
canary_ssm/decision.py (+persist_score, persistence_maxima, calibrate_persistence, replay_policy),
canary_ssm/simulate.py (+10 SimConfig knobs, appended "scen" RNG stream, mixed modes; defaults bit-identical),
canary_ssm/parallel.py (env CANARY_MAX_DISK_USED), canary_ssm/seeds.py (+3 blocks), canary_ssm/studies/__init__.py (+inertia), canary_ssm/cli.py (+--opts).
Added: canary_ssm/inertia.py, canary_ssm/studies/study_inertia.py, configs/grids_inertia.yaml, configs/inertia_scenarios.yaml,
scripts/partial_pooling_audit.py, scripts/make_review_bundle.py, tests/test_v3_changes.py, tests/data/legacy_sim_hashes.json,
results/v3_prep/partial_pooling_audit.csv (prior-level linear algebra, not an experiment), docs/*V3*, INERTIA_MODEL_DESIGNS, RESEARCH_CONTRIBUTION_MATRIX,
THREE_LEVEL_ARCHITECTURE_ANALYSIS, MATHEMATICAL_MODEL_AUDIT, RELATED_WORK_MATRIX, MULTIVARIATE_PROTOTYPE_SPEC, START_HERE_ANTIGRAVITY.md.
Verified by reviewer (sandbox): 31 new tests pass; legacy simulator hashes identical (24/24); inertia study and hier_ts tuning ran end-to-end at SMOKE scale
(no result is reportable). Baseline: 98 existing tests passed in sandbox; failures there were the disk guard (sandbox quirk) and one data-dependent test.
