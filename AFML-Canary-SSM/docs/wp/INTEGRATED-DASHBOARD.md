# Integrated dashboard checkpoint — 15 November 2026

Extends `canary_ssm_world_policy.zip` using the existing frontend/API. No new simulation loop or detector was added. The engine, resource equations, rollout protocol, preprocessing, inference and frozen policies remain unchanged.

Full repository suite: **599 passed in 106.84s (0:01:46)**. Actual HTTP/HTML-ID integration harness: **PASS**. Both command-driven replay fixture checks: **PASS**.

The UI harness covers manifest success/error, exact balanced allocation preview, baseline/exposure/pause/rollback, versions and traffic, full command IDs, lost responses, undelivered retries, duplicate clicks, backend checkpoint replay/export and refresh to the same run/tick. New regression tests first exposed and then verified fixes for imported-run identity, receipt-cache eviction/restart and current-run stream model labels. The strict renderer harness also caught a missing dynamic control ID; the repaired harness rejects references absent from actual HTML.

The first focused run found the old recorded snapshot lacked the new context and used a different numerical runtime. It was regenerated from actual backend outputs; no existing test was modified. Original research/calibration evidence is retained rather than reinterpreted in the current runtime. No null calibration or research benchmark was rerun for this UI package.

| Requirement | Status | Actual file/function | Evidence | Smallest next patch / boundary |
| --- | --- | --- | --- | --- |
| Seven coordinated views | implemented | web/index.html; app.selectView; console.js | Actual HTTP/HTML-ID harness covers all seven views | None |
| Shared topology in World and Canary Rollout | implemented | shared-topology; selectView; render rack-grid/tree | Both views keep the same map/tree; stable backend host IDs | None |
| Mode, run/seed, clock, model/policy/calibration IDs | implemented | dashboard.packet; dashboard_evidence.console_evidence; renderDashboard | Current-world uncalibrated stream IDs and disconnected state tested; replay identity regression fixed | None |
| Active replica version, routing and actual counts | implemented | console_evidence.replicas; replicaTable | Hand-checked .35/4=.0875 and .65/16=.040625; actual last-tick counts; exposure/rollback versions checked | None |
| Manifest/source registration | implemented | Existing registry validation; Release Registry form/upload; send | Valid and malformed registration exercised through actual frontend/API; uploaded source stays inert | None |
| Choose and preview canaries | implemented | preview_rollout; existing RolloutManager.command/select_cohort; rollout-preview | One/two balanced canaries per rack; exact IDs shown, three controls per rack/class retained; preview is nonmutating | Arbitrary individual host editing is outside this bounded selector |
| Baseline, exposure, pause and manual rollback | implemented | Existing rollout commands; Canary Rollout view | Queued versus applied state, frozen traffic and restart cleanup preserved; API workflow passes | None |
| Memory and latency inspection | implemented | Moved Host Details; existing resource-health and monitoring renderers | Backend request/memory traces; advisory and analytical/sample-mean latency labels remain distinct | None |
| Separate fault scheduling and truth | implemented | Fault Scenarios; existing developer fault endpoint | Public console excludes injected mechanism/severity/type; fixture schedules a rack disturbance separately | None |
| Full command IDs, pending/success/error and duplicate suppression | implemented | app.send; WorldController.command; command_journal | Duplicate click and accepted-response-loss checks pass; same ID/different parameters rejected | None within declared command bounds |
| Receipt eviction/restart deduplication | implemented | Persistent compact command journal and receipt lookup | Actual cache eviction and restart regression prevents a second step; bounded at 10000 IDs | Export/checkpoint and use fresh state directory at journal limit |
| Disconnect/refresh recovery | implemented | session-storage pending request; recoverUnconfirmed; GET /api/commands | Undelivered retry keeps exact ID; prior run/epoch is never resubmitted; large-body limits declared | Large upload payload may need reselection after refresh; unknown outcomes require explicit acknowledgement |
| Refresh/server restart reconnects to same run | implemented | WorldController restore/load; command_journal persistence | Imported run now matches actual engine ID through refresh/reset/restart; frontend refresh reads existing backend | None |
| Backend Run History and checkpoints | implemented | RunArchive; history_save/history_load; GET /api/history | 128 bounded content-addressed snapshots; cached metadata; hash corruption/traversal rejected | Use --state-dir for disk persistence |
| Replay/export from saved backend data | implemented | Existing strict SimulationEngine.replay; /api/run; /api/history | Paused/recovered fixtures replay exactly; direct JSON export avoids browser RNG/summary calculation | Older artifacts require their exact compatible numerical runtime/source |
| Laptop/narrow responsive structure | implemented | web/styles.css; seven-view navigation and table scroll containers | CSS breakpoints at 1150/760; HTML IDs and view visibility checked | Viewport screenshot QA remains unverified |
| Native screenshot/viewport visual review | unverified | Headless Chrome attempt log | Chrome exited -6 in sandbox; no screenshot or visual-pass claim | Inspect actual app at laptop width in a browser capable of running here |
| Inference, simulator and calibration preservation | implemented | integrated_preservation.json | All original inference/engine/protocol code, 32 test files and existing research/calibration artifacts byte-preserved | No new calibration/benchmark claimed |

Run/setup and explicit bounds: [integrated_dashboard.md](../integrated_dashboard.md). Evidence: `integrated_tests_full.txt`, `integrated_ui_validation.json`, regression-before logs, `integrated_preservation.json`, and `examples/integrated_console/checks.json`. This is an archive-based repository update; no remote branch/merge is claimed.
