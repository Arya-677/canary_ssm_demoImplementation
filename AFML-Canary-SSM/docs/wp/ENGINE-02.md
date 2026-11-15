# ENGINE-02 checkpoint

Added `canary_ssm/engine.py`, `configs/world_clock.yaml`,
`tests/test_engine.py`, and `docs/engine.md`. Extended the existing CLI and
README, and updated `docs/implementation_status.md`. No statistical inference,
calibration, research seed ranges or existing tests were changed.

Reused the topology records, shared YAML reader, registry smoke seed and
existing CLI. The engine owns only clock/lifecycle, event order, named RNGs,
phase execution, snapshots and replay. Resource/workload phase adapters are
explicit static placeholders for chunk 03. No random faults are introduced.

Executed from the repository root using the local audit Python environment:

```bash
python -m pytest -q tests/test_engine.py tests/test_topology.py
python -m canary_ssm world-run --config configs/world_clock.yaml --ticks 100 --out ../../outputs/world_clock_run.json
python -m canary_ssm world-replay --artifact ../../outputs/world_clock_run.json
```

Focused tests: `104 passed in 2.54s` (28 engine cases plus 76 topology cases).
The CLI run reported tick 100, simulated seconds 100, state paused. Replay
reported the same state and `replay_verified: true`. Tests cover independent
runs, state controls, exact phase/tie order, all RNG streams, reset, pending
events, invalid commands, detached snapshots and tampered replay rejection.

Full regression command: `python -m pytest -q`.
Result: `1 failed, 210 passed in 63.63s`. The only failure is the previously
confirmed `tests/test_p1_protocol.py::test_experiment7_legacy_reproduction`,
which requires the absent `data_audit/model_pooled_dev/model_config.json`.
All 28 new engine cases and all 76 topology cases passed. No existing tests
were changed or skipped. Raw regression output and computed fixture gates are
saved in `docs/wp/engine_validation.json`.

`examples/world_clock_100_ticks.json` contains the executed headless fixture's
embedded initial config, root seed, ordered command/event log, publication
hashes, final snapshot, RNG states and runtime manifest. It can be checked with
`python -m canary_ssm world-replay --artifact examples/world_clock_100_ticks.json`.

This remains an extracted ZIP without git history, so no merge or branch is
claimed. Suggested commit: `feat: add deterministic world clock and verified replay`.
The known legacy reproduction test requires a model artifact absent from the
supplied ZIP; no replacement is fabricated. The earlier repository-wide audit
is still incomplete. Stop at chunk 02; resource dynamics are the next chunk.
