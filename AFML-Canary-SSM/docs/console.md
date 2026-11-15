# World, Releases, Fault Lab and Monitoring

Run from the repository root in the existing Python environment:

```bash
python -m canary_ssm world-dashboard --config configs/world_console.yaml --state-dir runtime/world_dashboard --port 8765
```

Open `http://127.0.0.1:8765`. This is the existing local Python API and packaged
frontend, extended without a frontend build or new dependencies. One backend
engine owns state, queues, RNG and time. Polling reads never advance the world.
The console config uses steady healthy traffic so release and platform effects
can be investigated independently. The earlier recovery config remains usable.

| View | Observed behavior |
| --- | --- |
| World | Center/rack/host drill-down; rack cards, version badges, resource values and selected-host CPU/memory/latency traces |
| Releases | Sample selection or unexecuted artifact registration; validated allocation preview; queued deploy and manual rollback |
| Fault Lab | Explicit developer-only injected schedule and all five manual mechanisms; separate seeded host CPU/crash schedule |
| Monitoring | Saved/polled resource telemetry; neutral `DETECTOR NOT CONNECTED`; no alarm or score derived from known injected labels |

Start/pause/resume/step/reset/speed retain the existing run/epoch/token/state
validation. Speed controls wall pacing only. Stale/disconnected states retain
the last received observations and disable commands until fresh contact.
The browser never fills gaps with synthetic points. Controls are native
buttons/selects; layout stacks at narrow widths. Actual browser verification
at the 1280×720 preview checked preview/deploy/fault/telemetry/rollback.

## Release behavior and allocation

This is a simulated deployment, not code execution or a real infrastructure
deployment. The registry applies to the first configured service. Samples:
`sample-healthy-v2` (normal work), `sample-slow-v2` (8× core-seconds/request),
`sample-leak-v2` (16 MB retained per completed request). Uploads contain
1–131072 bytes; up to ten per reset. Filename/hash/size and declared profile
are stored; file contents never execute or infer a behavior. Duplicate content
and profile reuse the registered ID. A healthy profile does not inject harm.

Preview chooses sorted eligible service hosts, one or two canaries per
represented rack, with at least three eligible controls per rack. Crashed and
non-ready hosts are excluded. The plan hash captures baseline versions and
cohort; deploy recalculates it and rejects missing/stale plans. One active
deployment is allowed. Deploy and rollback apply before routing on the next
tick; candidate replicas restart. Rollback restores captured versions and
healthy workload parameters, resets application retention to its configured
baseline and explicitly counts abandoned queued requests. Platform effects
continue independently. Preview validates current availability; a future
scheduled fault can still make a deployed host unavailable.

Retention is bounded by physical headroom after temporary request memory.
`retention_blocked_mb` reports truncated growth. This approximates leak
pressure, not an OOM crash. [faults.md](faults.md) defines platform effects,
overlap rules and their separation from release behavior.

## Persistence, receipts and replay

The server checkpoints `session.json` using temporary-file replacement after
commands, on shutdown and at most every 0.75 wall seconds during ticking.
It saves the engine config/seed/log, registry, unexecuted upload bytes, plans,
deployment, separate developer truth, last 500 outcomes and last 256 accepted
receipts. Reopening the same state directory restores the run ID and backend
state; a previously running world reopens paused. A crash may lose work since
the last checkpoint. A malformed or incompatible checkpoint fails explicitly;
use a fresh state directory when intentionally changing simulator source.

Command outcomes distinguish accepted (`applied` means scheduled for deploy/
rollback/fault) and rejected requests; deployment status and tick establish
when effects actually occur. Cached accepted IDs are idempotent, including
after restart. Rejections are recorded as attempts and are not cached.
Clock/reset outcomes remain in the bounded audit list; reset clears the world,
release registry, fault schedules and telemetry through engine initialization.

Save run downloads an explicit replay bundle via `/api/run`. Pause, select
Replay saved run and import it. The backend verifies source hashes and
reexecutes the ordered command/event log, then publishes the verified final
snapshot and saved history in read-only mode. This is final-state replay,
not an animated timeline scrubber. Reset returns to a live initial world.
Imports accept up to 32 MiB, 20,000 log entries and 10,000 simulated ticks.
Raw engine artifacts are also accepted. Bundles contain developer truth and
upload bytes for replay; ordinary monitoring polling does not.

```bash
python -m canary_ssm.console_fixture --out examples/console_demo
python -m canary_ssm.fault_fixtures --out examples/faults
python -m pytest -q
```

The headless console fixture executes a 52-tick upload → allocation → deploy →
fault → telemetry → rollback demo, verifies saved-run import and exports
`run.json`, host/service CSVs, a canary snapshot, separate truth and an exit
gate. Select that `run.json` to inspect its history in the dashboard.
All twelve gates passed in the delivered example. The five fault fixtures
also passed; these are functional simulation checks, not SSM benchmarks.

For UI development without Python, serve `canary_ssm/web` with a static server
and use `?recorded=1`; it loads only `recorded_snapshot.json`, never engine
APIs, and disables live actions. Recorded mode does not execute new release or
fault operations. See [dashboard.md](dashboard.md) for transport details.


The rate-based background scheduler is documented in [fault_scheduler.md](fault_scheduler.md).
Its pre-generated events, scope scaling, cooldowns, budgets and enable/disable
controls are separate from explicit manual faults and deployment profiles.
The earlier `random_faults` command is a fixed-count manual batch, not a rate model.


The console config now enables the public telemetry pipeline. Monitoring adds a
separate backend-sourced one-minute table with request-weighted completion
latencies and coverage/masks. Existing resource charts remain analytical
estimates. Public event/arrival fields, exports, causal slices and private
evaluator labels are documented in [public_telemetry.md](public_telemetry.md).
