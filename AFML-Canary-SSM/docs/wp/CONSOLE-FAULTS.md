# Console and typed-fault checkpoint

14 November 2026. Extends the extracted `canary_ssm_dashboard_fixed.zip`.
No existing test, research inference module or preexisting fitted statistical
model artifact was changed. No new benchmark claim is made.

## Implemented behavior

The existing local Python dashboard now has World, Releases, developer Fault
Lab and Monitoring views. The backend validates registry/allocation/deployment/
rollback/fault commands, saves outcomes and session state, and verifies saved
runs on import. Uploads are explicitly unexecuted. One backend loop drives
simulation; frontend polling only reads observations. The detector remains
disconnected and no injected label sets detector colors or scores.

Typed faults model CPU throttling, bounded platform memory pressure, host/rack
service unavailability, rack network capacity and shared demand surge. Rack
events act on descendants. Half-open timing, overlap/recovery, bounds and truth
separation are documented in [faults.md](../faults.md). Release slow/leak behavior
is a distinct per-replica profile. See [console.md](../console.md) for limits.

## Executed checks

Commands were run from the repository root using the available Python virtual
environment; the portable form is shown below.

| Command / check | Observed result |
| --- | --- |
| `python -m pytest -q` | **292 passed in 75.30s**; no skips or test changes |
| `python -m pytest -q tests/test_faults.py tests/test_console.py tests/test_dashboard.py tests/test_engine.py tests/test_resources.py` | 106 passed in 5.72s |
| `node --check canary_ssm/web/app.js` | Exit 0 |
| `node scripts/check_dashboard_ui.mjs http://127.0.0.1:8765` | All eight DOM-state/real HTTP checks pass, including stale/disconnect/reconnect and recorded mode |
| `python -m canary_ssm.console_fixture --out examples/console_demo` | 52 ticks, all twelve exit gates true: unexecuted upload, valid cohort, resource change, controls, descendant effect, rollback, honest detector, replay and outcomes |
| `python -m canary_ssm.fault_fixtures --out examples/faults` | All five deterministic before/during/after fixtures pass |
| `python -m canary_ssm world-fixtures --out examples/resource_world` | Equivalent generator call executed; all bounds/conservation/load/recovery/replay gates pass |
| 100-tick static engine fixture | `start/advance(100)/pause/save` executed and bundled; replay checked |
| In-app browser, 1280×720 | World with 4 rack cards and 20 host tiles; Step; Releases preview 4 canaries/16 controls; deploy; Step; manual CPU event; Step; Monitoring has real traces and DETECTOR NOT CONNECTED; manual rollback + Step visibly ROLLED_BACK |

The DOM-state harness's historical `browser_layout_verified: false` describes
that harness alone. Separate real browser verification succeeded this time.
Upload and saved-run import paths were exercised by backend integration and
headless demo checks, not through the browser file chooser. Broader devices,
cross-browser compatibility and animated replay are not claimed.

All bundled saved engine examples and the recorded UI fixture were regenerated
because replay intentionally checks exact simulator source hashes. Old external
artifacts from earlier simulator revisions are rejected explicitly. Current
raw checks/hashes are in `console_fault_validation.json`; tiny fault traces and
console-demo traces are under `examples/`.
