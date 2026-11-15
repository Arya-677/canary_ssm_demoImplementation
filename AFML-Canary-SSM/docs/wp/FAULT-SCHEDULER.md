# Background fault scheduler checkpoint

14 November 2026. Extends `canary_ssm_console_faults.zip`. The interrupted work
was restored in the reconnected runtime, then regenerated and verified here.

`fault_scheduler.py` adds typed configuration, named candidate RNG streams,
per-target rates, bounded ranges, cooldowns, concurrency/event caps and fixed
schedules. The engine persists and verifies the full schedule manifest. Existing
operations apply background events through the same real descendant resource
effects while keeping background state separate from deployment profiles.

The local Fault Lab adds validated enable/disable and developer scenario preview.
A headless preview CLI and fixture exporter work without a browser or SSM.
Public telemetry does not carry fault schedules or evaluator labels. Inference
and all preexisting tests/model artifacts are byte-preserved against the base ZIP.

## Commands executed

| Command | Observed result |
| --- | --- |
| `python -m pytest -q` | 319 passed, 1 warning in 59.99s |
| `python -m pytest -q tests/test_fault_scheduler.py` | 27 focused cases passed |
| `node --check canary_ssm/web/app.js` | Exit 0 |
| `node scripts/check_dashboard_ui.mjs http://127.0.0.1:8767` | All existing DOM/API gates passed |
| `node scripts/check_scheduler_ui.mjs http://127.0.0.1:8767` | 7 scheduler DOM/API gates passed |
| `python -m canary_ssm.scheduler_fixtures --out examples/background_faults` | All three scenario gates passed |
| `python -m canary_ssm world-fault-preview --config configs/world_console.yaml --out scenario_preview.json` | Developer JSON generated at tick zero |
| `python -m canary_ssm world-run --config configs/world_scheduler_fixed.yaml --ticks 100 --out fixed_run.json --trace-out fixed_trace` | 100 simulated ticks, paused, traces saved |
| `python -m canary_ssm world-replay --artifact fixed_run.json` | Verified replay |
| Bundled saved-run checks | 13 verified replay artifacts |

The existing resource, typed-fault and release/fault/rollback demo generators
were rerun and their computed gates all passed. All saved examples and the
recorded UI fixture were regenerated for exact source/NumPy replay compatibility.
No detection benchmark, calibration audit or new inference performance claim
was run. The pytest warning is from the installed anyio plugin's deprecated
pytest import; tests completed successfully.

## Generated fixture results

| Scenario | Simulated ticks | Accepted background events | Computed pass |
| --- | --- | --- | --- |
| all_healthy | 100 | 0 | True |
| fixed | 100 | 3 | True |
| rates | 304 | 43 | True |

Rows above are generated from saved fixture gates. CSV traces, private schedule
manifests, separate developer truth and verified runs are in
`examples/background_faults`. No candidate release is deployed in these runs.

## Boundaries and limitations

Rates are simulated-second hazards per scoped target. Candidate draws are
independent; accepted events interact through the global cap. The start horizon
is finite. Ties are lexical, cooldowns run after end, suppression drops a
candidate, and manual injections are outside the background budget. Enabling
never resamples or shifts time. See `docs/fault_scheduler.md` for precise rules.

The new panel was checked through real HTTP plus a DOM-state harness; this is
not visual browser QA. The preexisting browser check in the previous checkpoint
is historical. The extracted archive is not a git checkout, so no branch or
merge is claimed. No test was weakened, skipped or edited for this extension.

Current verification environment: Python 3.12.14,
NumPy 2.3.5, Linux x86_64.
