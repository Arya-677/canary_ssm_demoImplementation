# Local world dashboard (chunk 04)

Updated console behavior is documented in [console.md](console.md), including
release/fault views, persistence and verified saved-run import. The original
chunk 04 transport/layout evidence below is retained as historical context.

No frontend or HTTP backend existed in the inspected repository. This chunk
adds one small local HTTP adapter and packaged HTML/CSS/JavaScript, reusing the
existing `SimulationEngine`, topology, resource observations and CLI. It has no
new Python or JavaScript dependencies and no hosted service requirement.

## Start the live dashboard

From the extracted repository root, with its Python environment activated:

```bash
python -m canary_ssm world-dashboard --config configs/world_recovery.yaml --port 8765
```

Open `http://127.0.0.1:8765` in a browser. The server starts one world at tick 0
in `ready` state. Click Start, or Step to advance exactly one tick and remain
paused. Playback speed controls wall-clock pacing; simulated seconds per model
tick remain unchanged. The recovery config uses increased demand from tick 21
through 60, then healthy baseline demand again, making its traces easy to inspect.

The page shows data center → rack → host navigation, rack cards, serving status,
host CPU/memory/queue/latency values and recent per-host traces. Select a data
center or rack to filter the world view. Select a host in either view to show
that host's backend history and replica/version placement. “All infrastructure”
returns to the fleet view. The layout includes narrow-screen breakpoints and
native focusable controls, chart text labels and status announcements.

CPU, memory and latency values are synthetic resource observations. Latency is
explicitly labeled as a queue/service estimate, with no p95 claim. There is no
detector implementation in the browser or HTTP adapter. The monitoring panel
says **Monitoring not connected**.

## Backend ownership, time and commands

`dashboard.WorldController` owns one engine, one scheduler thread, and a lock.
GET requests read snapshots and never create/advance engines. Page refreshes
and multiple tabs connect to the same run while the server process remains
alive. With `--state-dir`, a server restart restores its persisted run and opens
paused; a fresh state directory creates a new run ID. Reset retains the run ID, adds a
reset epoch, and restores initial world/queue/RNG state through the engine.

The scheduler uses a monotonic wall-clock deadline to call `engine.advance(1)`.
Its interval is `tick_seconds / playback_speed`. It advances at most one tick
when due and schedules the next deadline from that instant, so a stalled host
does not trigger an unbounded catch-up burst. Playback is best-effort pacing,
not a change to the physical model's time units or resource equations. The
supported speeds are 0.25×, 0.5×, 1×, 2×, 4×, 8× and 16×.

| Action | Backend validation / behavior |
| --- | --- |
| start | Requires ready; enables the scheduler |
| pause | Requires running; freezes the clock before the response is returned |
| resume | Requires paused; schedules future ticks |
| step | Requires ready or paused; exactly one whole tick, ending paused |
| reset | Restores the initial engine, clears resource histories and increments epoch |
| speed | Requires a supported finite numeric speed; only wall pacing changes |

Every command includes a command ID, expected run ID and reset epoch. Unknown
fields/actions, invalid transitions, wrong run/epoch and unsupported speeds are
rejected. The last 256 accepted command IDs have duplicate protection: repeating
the same ID/payload returns its original receipt without applying it twice;
reusing an ID for different parameters fails. Reset retains this receipt cache.
The UI disables commands while a response is pending and displays command
confirmation/rejection. It never retries a control automatically after a timeout.

The server binds only to `127.0.0.1`. Static routes are allowlisted; repository
files are not generally served. Commands require same-origin JSON requests and
the per-process command token obtained from the state endpoint. Responses are
uncached. This is a local simulator interface, not a deployed multi-user service.

## Polling and connection states

The browser polls at 750 ms intervals, with a three-second snapshot timeout.
Each response carries a backend revision, run/epoch identity, server wall
timestamp, simulated timestamp, world snapshot and requested host history.
Older revisions and out-of-order responses cannot replace newer displayed data.
The UI uses the latest successful response for display; it never extrapolates
the world clock or fabricates resource points between responses.

- **Connected:** fresh responses are arriving, even if the simulated world is paused.
- **Stale data:** no successful response for 2.5 seconds, a response timestamp
  older than five seconds, or a reported backend driver error. Live controls
  are disabled; a driver error allows Reset to recover.
- **Disconnected:** a request fails or times out. The last received view stays
  visible with a clear banner and disabled live controls; polling reconnects.
- **Recorded snapshot:** immutable recorded outputs, with a separate banner
  and disabled world/playback commands.

The wall-clock contact indicator is distinct from simulated HH:MM:SS and tick.
A stationary simulated tick during Pause is not treated as a broken connection.
Backend driver exceptions pause the engine and expose an error rather than
silently continuing with a healthy-looking status.

## API contract

```text
GET /api/state?host_id=host-02-03
POST /api/commands
Content-Type: application/json
X-World-Token: <token from the state response>

{"command_id":"unique-id","run_id":"<current run>","epoch":0,"command":"step"}
```

State includes `schema_version: 1`, `mode`, `run_id`, `epoch`, `revision`,
`speed`, wall-clock timestamps, driver health, the engine `snapshot`, summary
counts and `history: {host_id, rows}`. History is capped at the last 120 recorded
rows for the selected host and uses the existing bounded resource trace buffer.
The static clock config has no resource traces; charts say No observations yet.
Successful commands return an applied receipt. Invalid payloads use HTTP 400,
invalid state/epoch or conflicting IDs use 409, and invalid host selection uses
404. No API accepts source code, detector settings, hidden truth or fault labels.

## Develop the UI without an engine

The packaged `canary_ssm/web/recorded_snapshot.json` contains genuine synthetic
backend outputs at tick 50 of the recovery fixture, including per-host history.
It contains no command token. It can be served by an ordinary static server:

```bash
python -m http.server 8766 --bind 127.0.0.1 --directory canary_ssm/web
```

Open `http://127.0.0.1:8766/?recorded=1`. Host/rack navigation and charts work
from this fixed JSON alone. No engine/API process is required, no browser
simulation runs, and world controls remain disabled. Opening `index.html`
directly as a `file:` URL is not supported because browsers restrict fetches.
To regenerate the bundled recording from the repository root:

```python
import json
from canary_ssm.dashboard import WEB, recorded_fixture
from canary_ssm.engine import load_engine_config
data = recorded_fixture(load_engine_config("configs/world_recovery.yaml"), 50)
(WEB / "recorded_snapshot.json").write_text(json.dumps(data, indent=2) + "\n")
```

## Verification and limits

```bash
python -m pytest -q tests/test_dashboard.py
node --check canary_ssm/web/app.js
node scripts/check_dashboard_ui.mjs http://127.0.0.1:8765
node scripts/check_dashboard_ui.mjs http://127.0.0.1:8766 recorded_checks.json --recorded-only
```

The Node script uses a DOM-state harness plus the real local HTTP server. It
checks selection, charts receiving the selected host's rows, controls, speed,
run reuse, stale/disconnected/reconnected states and static recording behavior.
It is explicitly **not browser rendering or visual QA**. The available browser
launch aborted and the in-app preview could not open, so actual browser layout
and manual browser interaction remain unverified. API and JavaScript state
checks ran successfully; see `docs/wp/dashboard_validation.json` for evidence.

Stop the local server with Ctrl+C. The scheduler shuts down with it. There is
no run persistence across server restarts or distributed serving in this chunk.
The next guide chunk is fault mechanisms; monitoring remains disconnected.
