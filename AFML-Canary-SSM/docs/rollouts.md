# Fixed-cohort service rollouts v1

This is a manual, simulated rollout protocol, `fixed-cohort-rack-class-v1`.
It uses the immutable release registry and backend world clock. Source attachments
are inert. No simulator truth, fault schedule or evaluator label drives a transition.
No compatible calibrated policy is supplied: every epoch is **UNCALIBRATED**,
`alerts_enabled=false`. The existing research filters and eligibility defaults are unchanged.

## Run and inspect

From the repository root, after installing the project dependencies:

```sh
python -m canary_ssm.rollout_fixture --out examples/rollouts
python -m pytest tests/test_rollouts.py -q
python -m canary_ssm.cli world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/rollout-dashboard
```

Open `http://localhost:8765`, choose Releases, select `release-002`, and use the
**Fixed-cohort service rollout** card. The old one-shot deployment is explicitly
labeled legacy and keeps its compatibility API. Finish a rollout before using the
legacy deploy/rollback commands. Choose Start baseline, step the world until the
baseline duration completes, then Expose candidate and step again. Clock controls
pause simulation time; rollout pause leaves time, traffic and telemetry running.

The default baseline is 3600 simulated seconds; the evaluation horizon is 7200.
Both must be integer, tick-aligned seconds between one tick and 86400 seconds.
The tiny headless fixture uses 2/10 seconds to test lifecycle behavior only; it
cannot produce a full clean monitoring window or claim detector readiness.

## Commands and states

Backend entry point: `SimulationEngine.operations_command(action,args)`; HTTP uses
the existing `/api/commands` token, run/epoch, idempotent command ID and receipt
validation. Commands below use `args={"rollout_id":"..."}`, except creation.
Actions apply before routing on the next simulated tick; creation is immediate.
Only one pending action is allowed. Invalid commands do not change the engine log,
rollout record, routing or placements. Rejected HTTP outcomes are recorded by the
existing controller. Read-only saved-run mode rejects mutation commands.

| Command | Accepted state | Result |
| --- | --- | --- |
| `rollout_create` | No active service rollout; previous PROMOTED or ROLLED_BACK | CREATED; freezes cohort, fraction, horizon, baseline versions and a new epoch |
| `rollout_baseline` | CREATED | BASELINING; restarts service replicas and installs fixed routing |
| `rollout_expose` | BASELINING after required baseline ticks | CANARY; restarts canaries, places candidate and initializes monitoring epoch at exposure |
| `rollout_pause` | CANARY | PAUSED; preserves traffic, placements and evaluation clock |
| `rollout_resume` | PAUSED with evaluation still active | CANARY in the same epoch |
| `rollout_promote` | CANARY or PAUSED | PROMOTED; ends evaluation before routing, places candidate on remaining replicas |
| `rollout_rollback` | Any state except ROLLED_BACK | ROLLED_BACK; restores original release placement and normal routing |
| `rollout_fail` | CREATED, BASELINING, CANARY or PAUSED | FAILED; ends evaluation; retains placement/routing pending explicit rollback |

Creation args: `release_id`, optional `per_rack` (1 or 2), `canary_fraction` in
(0,1), `baseline_seconds`, `monitoring_seconds`. Defaults choose one canary per
rack and a fraction equal to the chosen cohort's share of eligible hosts. The
candidate must be registered and not already placed on that service. Effective
CPU work is validated against the existing resource bounds before creation.

At horizon expiry the state becomes PAUSED with `evaluation_active=false`.
Traffic stays frozen until manual promotion/rollback; resume is then rejected.
A public placement mismatch fails evaluation; v1 offers no migration operation.
FAILED is a protocol condition, not an inferred anomaly. Reset appends a
ROLLED_BACK entry with reason `world_reset_restores_initial_world`, restores the
configured world and RNGs and clears current routing. It preserves all historical
records, transition hashes and monotonically increasing monitoring epoch IDs.
Tick values may restart after reset; global transition sequence never restarts.

## Selection and fixed routing

`rollouts.select_cohort` deterministically searches sorted stable host IDs, one or
two canaries per represented rack, requiring at least one canary in every
represented rack **and** class and at least three unexposed controls in each.
Racks/classes are crossed partitions, not nested levels or their intersections.
One service replica per host is required in this first version. Lifecycle and
public last-observed availability determine initial eligibility. Other active
rollouts reserve their host cohorts to prevent exposure/control conflicts;
other-service promoted exposure also excludes those hosts. Impossible selections
fail before mutation; bounded search rejects after 100000 visits. A run accepts
at most 1000 rollout records. There is no automatic reselection after a failure.

For A admitted arrivals in a tick, C frozen canary replicas, K frozen controls and
fixed fraction f, routing samples

\[
(N_1,\ldots,N_{|C|+|K|})\sim\operatorname{Multinomial}(A,p),\quad
p_i=f/|C|\ (i\in C),\qquad p_i=(1-f)/|K|\ (i\in K).
\]

This is equal expected traffic within each cohort, not exact integer proportions
each tick. Baseline uses the same weights as candidate exposure, avoiding a load
step at deployment. Unavailable frozen slots retain their probability; their
requests are explicitly dropped, with no redistribution or fallback between
cohorts. Other hosts do not receive this service's fixed-cohort traffic. Resource
queues and processing retain their bounded discrete-time assumptions.

Service traces record `canary_requested`, `control_requested`,
`routing_rollout_id`, arrivals, accepted and each drop reason. Host traces retain
routed requests and now include `dropped_unavailable_routes`. For fixed routing:
canary_requested + control_requested = arrivals - dropped_arrival_limit;
accepted + dropped_queue + dropped_memory + dropped_unavailable_routes equals
that admitted count. Existing queued completions/drops are accounted separately.
Legacy routing and RNG consumption are unchanged when fixed routing is absent.

## Exposure, monitoring and version visibility

Snapshots expose `rollout.rollouts` (identity, versions, cohorts, fraction,
state, pending action, exposure/horizon ticks, epoch and eligibility policy) and
`rollout.transitions`. Candidate identity/hash and baseline versions are public;
behavior manifests and injected truth stay outside telemetry and inference.
The Releases view renders both version sets and the append-only transition table.

Exposure is applied before routing at tick t; its first interval starts at
(t-1) times dt. `first_decision_time` is the end of the first minute whose whole
window is exposed: `(ceil((t-1)*dt/60)+1)*60`. A mixed baseline/candidate minute
is skipped. Evaluation ends before routing at `evaluation_end_tick`, exclusive.
Current-run detector streams must match the frozen canary roster, declare this
first full-window timestamp, and append only within the active epoch/horizon and
received world clock. Pre-exposure, old-epoch and post-promotion/rollback frames
are rejected. Creating a new rollout disconnects an old current-run feed.
Saved demonstrations for other runs remain explicitly separate.

The epoch initializes monitoring metadata at exposure; it does not fabricate a
connected detector or effect posterior. Fresh controls, sufficient baseline,
80% observed canaries and three fresh controls per represented monitoring group
remain the upstream adjustment/filter requirements. Availability loss does not
silently change membership or make carried values fresh. Contaminated controls
remain a documented challenge; no robust estimator is claimed. This protocol
adds no pre-exposure alerts, threshold or automatic transition.

## Restart and closure semantics

Baseline start restarts all service replicas. Candidate exposure restarts only
canaries. Promotion preserves current canary retained state and restarts newly
promoted controls; it removes fixed routing and ends this fixed-cohort evaluation.
Rollback, including rollback after promotion or failure, restores every original
service replica's release parameters/version, restarts all such replicas, drops
queued CPU work and delayed responses (recorded as `dropped_restart`), clears
partial progress and restores configured initial retained memory. Newly arriving
baseline requests may immediately allocate temporary memory again. Host capacity,
platform faults and other services are unaffected. Replica hosts never move in
this protocol; version placement/routing return to their original service layout.

A promoted candidate becomes the production baseline for a later candidate, but
that requires a new record/monitoring epoch and compatible new calibration.
There are no progressive-cohort or traffic-edit commands. Changed cohort,
traffic, baseline or policy cannot reuse an existing epoch's evidence.

## Persistence and evidence

Transitions are hash chained, monotonically sequenced frozen records. Public
snapshots are detached copies. Private replay artifacts include the rollout
state, ordered engine command log, config, seed/RNG states and rollout source
hash. Replay re-executes transitions and checks the full saved state, not just its
hash chain. Controller checkpoints persist command receipts/outcomes and engine
artifacts; exports remain replayable. This is local append-only application
behavior, not a signed tamper-proof external audit service.

Evidence: `tests/test_rollouts.py`, `examples/rollouts/checks.json`,
`docs/wp/rollout_pytest.txt`, `docs/wp/rollout_ui_validation.json` and
`docs/wp/rollout_artifact_validation.json`. The UI check executes actual button
handlers against a local HTTP backend with a DOM harness; browser layout at
specific viewport sizes remains unverified for this patch.
