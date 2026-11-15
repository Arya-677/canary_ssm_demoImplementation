# Public telemetry checkpoint

14 November 2026. Extends `canary_ssm_background_scheduler.zip`.

Implemented a public-only record contract, bounded simulated transport, completed
FIFO cohort latency statistics, frozen one-minute aggregation and causal slices.
The source, receiver and evaluator are separate modules. The backend exposes a
read-only public endpoint and a distinct Monitoring minute table. No inference,
research schema, calibration model or preexisting test was edited.

## Executed commands and results

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 360 passed in 83.92s (0:01:23) |
| `python -m pytest -q tests/test_public_telemetry.py` | 41 passed in 4.60s |
| Resource/engine/console/scheduler plus telemetry focused run | 122 passed in 8.19s, before the two extra offline-slice tests; full suite covers both |
| `node --check canary_ssm/web/app.js` | Exit 0 |
| Dashboard and scheduler real-API DOM harnesses | All gates passed |
| `node scripts/check_telemetry_ui.mjs http://127.0.0.1:8768` | All six minute-table/API gates passed; not visual QA |
| `python -m canary_ssm.telemetry_fixture --out examples/public_telemetry` | All 11 computed gates passed |
| `world-run --config configs/world_telemetry.yaml --ticks 180 --run-id cli-telemetry --out ... --telemetry-out ...` | 180 ticks; public and evaluator exports written |
| `world-replay --artifact ...` | Verified CLI replay |
| Saved example replays | All 14 verified |

## Generated fixture evidence

The saved four-minute run has 3600 unique received public
records and 80 minute rows. First-minute observations
arrive late and remain masked; minute two is dropped entirely; later complete
windows recover. Duplicates are counted but never inflate moments. The fixture
compares offline and online frozen inputs and checks earlier receipts after
future arrivals. Public data contains no injected truth; the separate evaluator
file has targeted platform labels and null counterfactual latent effect.

`tests/test_public_telemetry.py` also checks exact weighted moments, right-closed
timing, deadline ties, grace, receiver-stamped backdating, conflicting duplicates,
missing/carry/mixed-version masks, reset epochs, persistent sessions, receipt-only
GETs, strict schema fields and AST truth boundaries. Future traffic and future
payload perturbations leave previous inputs and successful callback scores intact.

## Files and scope

New modules: `telemetry.py`, `telemetry_transport.py`, `telemetry_evaluator.py`,
`telemetry_fixture.py`. Small integrations: `resources.py`, `engine.py`,
`dashboard.py`, `cli.py`, packaged frontend, console config. New tests and DOM
harness are additive. New config: `world_telemetry.yaml`; examples, guides,
audit/status and raw validation JSON are included. Previous saved world examples
were regenerated because exact source hashes and runtime manifests changed.

Physical measurements are tick-quantized simulation assumptions. No p95, SSM
alarm, fitted model result or invented benchmark is produced. The optional
receiver callback is not a connected engine detector; external inference needs
a separate observation adapter and committed scoring ledger. No git branch or
merge is claimed for an extracted ZIP. The new table's visual layout was not
browser-verified; actual HTTP and DOM-state checks passed.
