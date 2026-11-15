# Fixed-cohort rollout checkpoint

Extends `canary_ssm_release_registry.zip`, 14 November 2026.

Implemented uppercase manual service lifecycle states, deterministic crossed rack/class
cohort selection, fixed expected traffic, explicit unavailable-slot drops, immutable
version identity, exposure-only monitoring epoch metadata, manual controls, append-only
hash-chained transitions, rollback restart semantics and promotion closure.

| Executed check | Observed result |
| --- | --- |
| `python -m pytest -q` | 519 passed in 88.72s |
| `python -m pytest tests/test_rollouts.py -q` | 12 passed in 1.73s |
| `python -m canary_ssm.rollout_fixture` | 9 gates pass, three lifecycle paths replay exactly |
| `node scripts/check_rollout_ui.mjs ...` | Five local HTTP/DOM gates pass |
| `node --check canary_ssm/web/app.js` | Exit 0 |
| Legacy compatibility | Three 30-tick healthy/CPU/memory cases preserve all original numeric trace fields and workload RNG states |
| Source preservation | Only engine/resources/operations/dashboard and web integration change among existing package files; inference/statistical generators/tests unchanged |
| Refreshed source-bound fixtures | 23 non-scenario artifacts replay, 22 scenario member manifests verify |

New fixture observations are lifecycle acceptance evidence, not benchmark or detector
results. Research definitions, old statistical additive pairs, model selection and
calibration remain untouched. The new protocol has no calibrated alert policy and does
not automatically connect inference; detector status remains honest. Short fixtures
cannot establish statistical readiness. Layout/viewport validation is unverified.

Raw checks: `rollout_pytest.txt`, `rollout_ui_validation.json`,
`rollout_artifact_validation.json`, `rollout_preservation.json`,
`rollout_changed_files.json`. Full semantics and commands: `docs/rollouts.md`.

A final reset regression verifies that legacy deployment remains usable after the
rollout manager clears its current pointer. The recorded UI fixture was refreshed
after the source-bound operations hash changed. The final full suite above passed
after that refresh. Additional checkpoint/replay gates are recorded in
`rollout_persistence_validation.json`: restored active state/log, continued pause,
restored outcomes, saved-session replay and rejection of read-only promotion.
