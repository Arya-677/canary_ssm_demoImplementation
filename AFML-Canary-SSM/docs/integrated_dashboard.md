# Integrated simulation dashboard

The existing frontend and Python HTTP API now expose seven coordinated views.
All simulation state, resource/telemetry history, routing, model outputs, policy
decisions, command outcomes and replay data remain in the backend. The browser
renders backend records and sends commands; it does not run another world loop.

```sh
python -m pip install -e '.[dev,report]'
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/integrated-console
```

Open `http://127.0.0.1:8765`. Navigation can also be bookmarked, for example
`http://127.0.0.1:8765/#rollout`. Refresh keeps the same backend run and restores
the selected view. Server restart with the same state directory reconstructs the
saved run and pauses the clock. A new state directory starts a separate run.

## Views and shared context

| View | Backend evidence and actions |
| --- | --- |
| World | Shared center → rack → host tree and rack/server map; active replica releases/versions, nominal traffic shares, actual last-tick request counts and public event timeline |
| Host Details | Stable host selector, CPU/memory/latency histories, replica allocation, retained memory/headroom, observed resource advisory and explicit process restart |
| Fault Scenarios | Separate developer controls for manual, seeded and background faults; injected truth stays here and outside public inference evidence |
| Release Registry | Immutable manifest builder/upload, inert source attachment, registry content hashes, service/version and explicit simulated-behavior labels |
| Canary Rollout | The same shared topology, candidate selector, backend-balanced cohort preview, frozen rollout creation, baseline/exposure/pause/resume/promotion/rollback, policy attachments and decision timeline |
| Monitoring Evidence | Existing saved/streamed posterior charts, masks/quality, uncertainty and risk; committed public minute telemetry and resource traces |
| Run History | Backend checkpoints, full command IDs/outcomes, verified read-only replay and direct backend JSON export |

The persistent header shows simulation/replay mode, run, seed, simulated clock,
model/policy IDs, calibration status and decision reason. A connected uncalibrated
current-run stream shows its actual method IDs; a different saved detector run
keeps its own identity in Monitoring Evidence. A qualified policy and a marginal
posterior are different things. No connected detector means **DETECTOR NOT
CONNECTED**, never a fake healthy score. Calibration remains subject to the
existing exact model/preprocessing/simulator/protocol/runtime compatibility guards.

The map shows observed availability, CPU and memory. Canary outlines represent
cohort membership, not inferred harm. Nominal traffic weights are allocation
probabilities, not realized request fractions. The backend separately provides
actual routed request counts; frozen traffic directed at unavailable replicas can
be dropped. Replica versions change only after their queued action actually
applies. Charts keep analytical queue/service estimates distinct from aggregated
request latency. Neither is renamed p95.

## Delivery workflow

1. Register a validated release manifest in Release Registry, or choose an
   existing version. Uploaded source remains unexecuted.
2. In Canary Rollout choose one or two canaries per rack, the candidate traffic
   fraction, baseline duration and fixed monitoring horizon. Preview displays the
   exact backend-selected host IDs and controls, then create the frozen rollout.
   This version uses the existing deterministic balanced selector across racks
   **and** hardware classes, retaining at least three controls in every group.
   Arbitrary individual host editing is not offered. Creation revalidates current
   availability; membership/traffic stay fixed after creation.
3. If using a qualified matching policy, attach policy and independent validation
   before baseline at tick zero. Otherwise the workflow remains explicitly
   uncalibrated and manual. Existing policy timing/eligibility rules still apply.
4. Start baseline, advance the backend clock to its declared boundary, launch the
   canary, then inspect Host Details and Monitoring Evidence. Pending actions
   apply on the next tick. Short manual demo baselines do not establish research
   eligibility or calibration.
5. Pause or manually roll back through validated commands. Rollout pause keeps
   fixed routing/time/telemetry; the separate clock Pause freezes time. Rollback
   follows the existing explicit process-restart/memory cleanup semantics.
   Promotion guards and automatic policy actions remain backend-owned.

Fault scheduling remains independent of delivery. An operator can inspect its
effects without converting known injected labels into detector classifications.
The public timeline includes command outcomes, rollout transitions and policy
reasons; it excludes mechanism/severity/truth payloads. Events have a deterministic
display order by simulated tick, source and that source's sequence. Separate
source logs do not claim a shared sub-tick execution timestamp.

## Command safety and reconnects

Every mutating request has a full command ID, run and epoch. Pending controls are
blocked, and duplicate clicks share no second execution. Backend validation is
authoritative even if clients bypass disabled buttons. Errors and queued actions
are shown separately from success at the next simulated tick.

If a response is lost, the page remembers the request in tab session storage and
looks up that command ID after reconnect/refresh. Retry uses the exact original
payload and ID. The backend persists a compact command journal, so an applied
command cannot execute again after the 256-entry full-receipt cache evicts it or
the server restarts. Reusing an ID with different parameters is rejected. Older
retries may return a summary receipt with `result_not_cached=true`; the world
state remains authoritative. Rejected outcomes remain rejected for that ID.

Very large upload bodies may exceed browser session-storage limits: the page
remembers their ID, but cannot promise to retain the whole body for automatic
retry after a refresh. An unknown outcome is never labeled success. Explicitly
acknowledge it and inspect backend history before another operation. Requests
from a different run/epoch are not resubmitted. Connection loss/staleness disables
world mutations while keeping the last received evidence visible.

The journal is bounded at 10000 unique IDs and refuses new identities rather than
evicting duplicate protection. Export/checkpoint and start a fresh backend state
directory at that boundary. It stores compact outcomes, not unbounded copies of
large response bodies. Checkpoint history is bounded to 128 snapshots, each at
most 32 MiB. With no state directory, history remains backend memory only; the UI
labels that limitation. Checkpoint metadata is cached to avoid rereading every
full saved world on each history poll.

## Checkpoints, replay and working checks

Save a backend checkpoint from Run History. Reset or replacement also preserves
the current run before changing it. Loading a checkpoint verifies its content
hash, existing engine source/runtime/RNG replay guards and saved detector feed,
then enters read-only replay. Imported run IDs now match the actual saved engine
through refresh, reset and server restart. Export downloads backend JSON directly,
preserving full integer RNG state without browser-calculated summaries.

```sh
python -m canary_ssm.integrated_console_fixture --out examples/integrated_console
python -m pytest -q
```

The small fixture registers a process-memory release, previews/freezes its cohort,
collects a short baseline, exposes it, schedules a rack disturbance separately,
pauses and rolls back. Upload `paused_session.json` or `recovered_session.json`
from `examples/integrated_console` to inspect versions, routing, memory and timeline.
Public telemetry and evaluator truth are exported to separate subdirectories.
This fixture has no SSM and makes no detector calibration/power claim.

New adapter code: `dashboard_evidence.py`, `dashboard.py`; frontend composition:
`web/index.html`, `web/app.js`, `web/console.js`, `web/styles.css`. The engine,
resource equations, fault models, inference, rollout protocol, thresholds and
existing calibration artifacts are unchanged. Older artifacts retain their
original numerical runtime requirements; this UI task does not silently
recalibrate or migrate them. The recorded snapshot was regenerated with the new
public context and the actual runtime used for this checkpoint.

Acceptance evidence: [wp/INTEGRATED-DASHBOARD.md](wp/INTEGRATED-DASHBOARD.md).
Real authenticated HTTP/renderer checks live in
`scripts/check_integrated_console.mjs`; the harness validates every requested DOM
ID against the actual HTML. Responsive breakpoints cover laptop/narrow layouts.
Native Chrome headless execution aborted in this sandbox, so screenshot/viewport
visual QA is explicitly **unverified**; it is not inferred from the HTTP tests.
