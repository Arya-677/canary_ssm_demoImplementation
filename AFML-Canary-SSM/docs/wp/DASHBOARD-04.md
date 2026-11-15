# DASHBOARD-04 checkpoint

Added a local HTTP backend and dashboard in the existing Python package; there
was no existing web stack. Reused topology/resource outputs and the current
engine. The browser only renders backend state and sends validated commands.
No inference source, statistical definitions, model artifacts or existing tests
were modified. No hosted Site or second simulation engine was introduced.

## Files

- `canary_ssm/dashboard.py`: controller, one scheduler, validation/receipts,
  polling state API, loopback-only server and recorded fixture generation.
- `canary_ssm/web/index.html`, `styles.css`, `app.js`: topology drill-down,
  resource charts, controls, run/time identity and connection/recorded states.
- `canary_ssm/web/recorded_snapshot.json`: actual tick-50 recovery observations
  and histories; immutable development data, no engine required to serve it.
- `canary_ssm/cli.py`, `pyproject.toml`: dashboard CLI and packaged web assets.
- `tests/test_dashboard.py`, `scripts/check_dashboard_ui.mjs`: HTTP/controller
  tests and a DOM-state harness talking to real live/static HTTP servers.
- `README.md`, `docs/dashboard.md`, `docs/implementation_status.md`, this
  checkpoint and `docs/wp/dashboard_validation.json`: contracts and evidence.

## Executed checks

```bash
python -m pytest -q tests/test_dashboard.py
python -m pytest -q
node --check canary_ssm/web/app.js
python -m canary_ssm world-dashboard --config configs/world_recovery.yaml --port 8765
node scripts/check_dashboard_ui.mjs http://127.0.0.1:8765
python -m http.server 8766 --bind 127.0.0.1 --directory canary_ssm/web
node scripts/check_dashboard_ui.mjs http://127.0.0.1:8766 recorded_checks.json --recorded-only
```

Python commands used the local audit environment. Dashboard tests:
`22 passed in 1.72s`. Full regression:
`1 failed, 255 passed in 74.56s`. The sole failure is the previously confirmed
legacy reproduction test requiring the absent
`data_audit/model_pooled_dev/model_config.json`. It was not changed or skipped.

The HTTP page and API returned 200. Live DOM-state/API checks passed for
topology, selected host traces, controls/speed, run reuse, stale data,
disconnection/reconnection and recorded data. A separate ordinary static server
served the recording without the engine/API. Recorded controls stayed disabled.

**Browser visual QA remains unverified:** the headless browser process aborted
and the in-app preview failed to open. The DOM-state harness is not a browser
layout test and no screenshot or manual browser success is claimed.

All simulation state remains in the backend; a disconnected browser retains
the last snapshot and never advances a local simulation. Monitoring says
Monitoring not connected. The engine's physical/statistical models and replay
hashes remain unchanged. The original archive has no `.git`, so no branch,
commit, merge or publication is claimed.

Suggested commit: `feat: add backend-owned world dashboard and recorded UI mode`.
Stop at chunk 04; manual fault mechanisms are the next guide chunk.
