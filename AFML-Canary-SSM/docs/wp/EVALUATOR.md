# Evaluator v2: executed evidence

The Linux rebuild extends the integrated-dashboard checkpoint with public-only scoring, evaluator-only retrospective targets, disjoint data roles, independently calibrated comparators/ablations, saved tables/figures and scoped performance measurements. Earlier Mac evaluator/cache results were unavailable and were not imported as v2 measurements.

## Independent null audits

| Generator / endpoint | B | Independent n | Policies | PASS | FAIL | INSUFFICIENT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| research / latent_effect | 2000 | 2000 | 11 | 11 | 0 | 0 |
| world / release_latency | 2000 | 2000 | 13 | 5 | 8 | 0 |
| world / infrastructure | 2000 | 2000 | 13 | 13 | 0 | 0 |

These are computed diagnostic audit verdicts. Release-null calibration is a declared six-family mixture, not independent per-family qualification. Platform nulls are all healthy. Continuous-maxima Beta–Binomial diagnostics can fail with saturated/tied scores even when strict thresholds produce conservative alarms; those failures remain visible. Final inputs stay sealed pending the governing per-family gate; no superiority claim follows from these mixture audits.

## Saved scenario outcomes

| Generator | Raw rows | Status counts |
| --- | ---: | --- |
| research | 242 | alarm: 10, miss: 13, not_supported_by_generator: 44, quiet: 166, success: 9 |
| world | 572 | alarm: 41, late_after_recovery: 26, miss: 75, quiet: 388, success: 29, unverifiable_target: 13 |

Smoke rows are one paired replay per scenario, not final-test power or delay estimates. Research memory mechanisms are unsupported rows, not fabricated latent memory outcomes. World missing targets, unmonitored affected controls, misses, late alarms and abstentions remain included. Raw generator tables never share a target definition or denominator.

## Numerical and leakage contracts

- Research preserves the original strict log(1.02)/15-minute latent event, first-crossing premature/success/miss/late rules, capped failure delay and onset+30 localization. Canonical prediction-only localization and its fresh-only counterpart remain separately labeled.
- World release attribution uses an offline paired completed-request log-mean difference. Infrastructure uses separate operator disturbance windows. Routing/queue interference is measured; no additive equality or directly observed online counterfactual is asserted.
- Classical methods have statistics, not fabricated posteriors. Independent, pooled, class/rack and nested Gaussian methods reuse the existing numerical engines and retain white shared uncertainty exactly once. Factor/AR ablations refit healthy nuisance models; persistence-off reselects effect settings without refitting a mathematically unchanged no-effect nuisance likelihood.
- Development decisions freeze before calibration. Calibration and independent validation use disjoint registered seeds. Tests cover future-data/truth perturbations, strict boundaries, capped outcomes, role isolation, paired identities, final locks and tampered caches.

## Performance measurements

| Component | Samples | Operations/second | Scope |
| --- | ---: | ---: | --- |
| api_snapshot_get | 50 | 79.88982732646275 | HTTP and JSON snapshot; no simulation step; no live detector attached |
| simulation_api_step | 20 | 3.1266968999340374 | verified one engine tick plus HTTP validation/journal/checkpoint; no browser; no live detector attached |
| simulation_tick | 100 | 54.62939844661447 | full engine including telemetry and snapshot; no HTTP or UI; no live detector attached |
| http_vm_render | 20 | 44.90702895549991 | actual HTTP plus app render; no browser layout paint |
| vm_public_renderer | 100 | 137.90498870041688 | real app renderer in strict DOM VM; no browser layout paint |

Per-update wall samples, state bytes and separate traced peak allocations are under `performance/`; traced allocations are not RSS. All timings were collected under concurrent audit load and are diagnostic, not isolated capacity limits. Renderer VM throughput is not browser layout/paint/input throughput. Local Chromium launch failed because the environment denied its Unix socket; the alternate cloud browser could not reach the workspace-local server. Browser throughput remains UNVERIFIED.

The first repeated API measurement reused persisted command IDs and counted cached receipts. Its raw files are retained under `performance/retired_duplicate_command_measurement/INVALID.json`. The corrected measurement uses a fresh runtime directory, asserts one actual engine tick per sample, and has a regression test rejecting duplicate-command samples.

## Regression verification

Latest complete test command: `python -m pytest -q`. Result: **625 passed, 1 warning in 190.38s (0:03:10)**.

Original-file comparison against the integrated dashboard ZIP is saved in `evaluator_preservation.json`. All original numerical modules and all original test files are byte-preserved. Changes to original files are documentation links plus the recorded dashboard fixture runtime metadata. The original Mac fixture is retained under `examples/evaluator_runtime/`.

## Executed commands

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m canary_ssm.replay_evaluator run --out examples/evaluator_v2 --B 2000 --n-validation 2000 --offset 12500 --workers 8
python -m canary_ssm.evaluation_performance --study examples/evaluator_v2 --inputs /tmp/evaluator_v2_pilot
python -m canary_ssm.evaluation_report --study examples/evaluator_v2
python -m canary_ssm.evaluation_check --study examples/evaluator_v2
python -m canary_ssm.evaluation_archive replay-null --study examples/evaluator_v2 --generator world --endpoint release_latency --role null-validation --index 0
python -m canary_ssm.replay_evaluator check-final-lock --out examples/evaluator_v2
python -m pytest -q
```

The pilot input path was used only for separately hashed public performance inputs; copies are included under `performance/inputs`. Future performance reproduction can use `--inputs examples/evaluator_v2` after the full smoke export exists. Use the evaluator guide for verified resume/null replay commands.

The freeze binds source/config/runtime/models and seed plans. Full scenario public arrays/evaluator truth, every raw result table and per-minute score/mask, independent maxima and config/seed/ordered commands are saved. The compact delivery replaces large null-input buffers with verified semantic fingerprints and exact source/seed regeneration; no negative outcome or score is omitted. Source snapshots permit exact provenance inspection. No online policy is attached by this offline study.
