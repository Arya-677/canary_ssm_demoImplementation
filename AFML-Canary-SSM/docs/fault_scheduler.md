# Background fault scheduler

`fault_scheduler.BackgroundFaultConfig`, `FaultRate` and
`BackgroundFaultScheduler` extend the existing configuration and typed fault
engine. Schedules are generated once at initialization, including while disabled.
The scheduler does not inspect releases, application profiles, observations or
detector scores. It samples background platform disturbances without requiring a
deployment. Existing slow/leak deployment profiles remain a separate mechanism.

## Rate and sampling contract

All rates have units **events per simulated second per scoped target**.
`tick_seconds = dt` is fixed by the engine; wall time and playback speed are
irrelevant. For each rule and target at each tick, one candidate is proposed
with probability `p = 1 - exp(-rate_per_second * dt)`, calculated with `expm1`.
This is a discrete-time Bernoulli hazard approximation: at most one candidate
per rule/target/tick, not an exact continuous-time Poisson count. Its raw grid
candidate rate is `p/dt`; cooldowns and admission limits reduce the accepted
rate further. Large rates saturate, rather than creating bursts within a tick.

| Scope | Independent candidate sampling | Scaling and physical effect |
| --- | --- | --- |
| host | One stream per rule and host ID | Nominal world intensity is host count × rate; CPU, memory or crash acts on that host's replicas |
| rack | One stream per rule and nonempty rack ID | Nominal intensity is nonempty rack count × rate; one accepted event applies identical timing/severity to every descendant host |
| world | One stream per rule, target `world` | Rate is per world, with no host-count multiplication; shared demand surge affects all configured services |

Candidate streams use PCG64 with
`SeedSequence([seed, 2, *stable_hash_words(rule_id, target)])`. The hash is SHA-256
of a JSON pair; the first 16 bytes are four little-endian words. Every lane
consumes four uniforms every tick (trigger, severity, duration and event seed),
even when admission would fail. Adding another host does not perturb an
existing host's candidates. A global concurrency limit necessarily introduces
dependence between accepted events; independent host *proposals* are guaranteed.
No workload, host-noise, telemetry-loss or inference RNG is consumed.

Severity is uniform on `[severity_min, severity_max)`, or exactly that value
when both endpoints match; permitted severity is 0.1–0.95. Duration is uniformly
sampled from inclusive integer ticks
`[ceil(duration_min_seconds/dt), floor(duration_max_seconds/dt)]`. The range
must contain a whole tick and remain within 1–1000 ticks. No duration is silently
rounded outside the requested interval. Event seeds are unsigned 32-bit values
from the lane; they record event provenance without adding hidden metric noise.

## Admission, cooldowns and timing

Starts are generated for ticks 1 through `horizon_ticks` inclusive. Events use
the existing half-open interval `[start, end)` and may finish after the start
horizon. There is no automatic extension or regeneration after the horizon.
Candidates are examined in stable `(tick, rule_id, target)` order. Ties favor
the earlier lexical rule/target; this deterministic policy may bias admission
under saturation and is a declared approximation, not a fair incident model.

An accepted event blocks its exact `(scope, target)` across rules until
`end_tick + ceil(cooldown_seconds/dt)`, using the admitting rule's cooldown.
Host and rack scopes remain distinct even when descendants overlap. A candidate
rejected for cooldown, concurrency or event budget is dropped, never delayed or
resampled. Counters for all rejection reasons are saved. The global
`max_concurrent` counts background events, not affected hosts: one rack event
counts once. An event ending at tick t releases its slot before starts at t.

Limits are 16 rules, 10,000 start-horizon ticks, 500 accepted events, 100 concurrent
events and two million target/rule/tick sampling iterations. `max_events` may
be lowered further. Explicit manual injections and the legacy fixed-count
`random_faults` command are separate from this background budget and may raise
total active events above it; they retain the existing overlap rules in
[faults.md](faults.md). No manual event is presented as a rate-generated event.

Fixed mode uses explicit typed events, sorted by `(start_tick, fault_id)`, with
`fixed_cooldown_seconds` for the same scoped-target rule. Duplicate IDs, unknown
targets, starts outside the horizon, capacity/cooldown violations and mixing
fixed events with rate rules are rejected. Fixed times/durations use ticks;
rate-rule duration/cooldown settings use seconds. Empty fixed mode is an
all-healthy background scenario. Fixed events include their own seed/recovery.

## Configuration and preview

Use the existing `engine.background_faults` configuration, with `demo: true`
and a resource config. See `configs/world_console.yaml` for the complete example;
its background effects start disabled. Missing background config defaults to
an empty disabled schedule. Unknown keys and invalid numeric types are rejected.

```yaml
background_faults:
  enabled: false
  seed: 10000
  mode: rates
  horizon_ticks: 300
  max_concurrent: 3
  max_events: 100
  rules:
  - rule_id: host-cpu
    kind: cpu_throttle
    scope: host
    rate_per_second: 0.005
    severity_min: 0.4
    severity_max: 0.8
    duration_min_seconds: 3
    duration_max_seconds: 8
    cooldown_seconds: 20
```

```bash
python -m canary_ssm world-fault-preview --config configs/world_console.yaml --out scenario_preview.json
python -m canary_ssm world-dashboard --config configs/world_console.yaml --state-dir runtime/scheduler --port 8765
python -m canary_ssm.scheduler_fixtures --out examples/background_faults
```

Fault Lab shows enable/disable buttons, configured rate/target scaling, tick
probabilities, duration/cooldown ranges, counts, horizon and the first 30 planned
events. The complete schedule is in Save run. The developer GET route remains
`/api/fault-lab?developer=1`; preview is read-only and never advances time.

The validated `background_set_enabled` command accepts only `{"enabled": true}`
or false, through the existing run/epoch/token controls. The outcome is persisted
and the new gate applies on the next tick. Disabling restores background-only
effects then; manual and release effects continue. Re-enabling resumes any
unexpired scheduled event at its original tick, without extending its duration.
It does not make up missed starts, move the horizon or resample. Preview's
enabled field reports the requested gate; resource rows still describe the last
completed tick. Reset recreates the initial schedule and configured gate.
Restored sessions retain logged toggles. Playback speed changes only wall pacing.

## Persistence and leakage boundary

The private run manifest includes scheduler/source IDs, exact background config,
sampling declarations, rejection counts, the ordered event list and its SHA-256.
Replay regenerates the schedule and checks its complete manifest, scheduler
source hash, ordered commands and resulting resource traces. A modified schedule
or incompatible code is rejected. Source changes require fresh example runs;
old external artifacts are intentionally not silently migrated.

Public snapshots and telemetry carry only resource observations and release
placement, not schedule fields, fault types, evaluator labels, seeds or rates.
The explicit run export and developer preview contain truth and must not become
inference inputs. This local developer separation is not authentication.
Existing inference modules have no scheduler dependency; a new AST guard checks
that boundary. No world-to-SSM adapter or detector score was added.

## Fixtures and verification

`world_scheduler_all_healthy.yaml`, `world_scheduler_fixed.yaml` and
`world_scheduler_rates.yaml` are loader-ready fixtures. All use healthy baseline
versions with no deployment commands. Each exported directory contains
host/service CSVs, verified `run.json`, `schedule_manifest.json`, separate
`developer_fault_truth.json` and computed `checks.json`. The rate fixture drains
past the start horizon until the last event recovers. The fixed fixture exercises
host CPU, rack descendant network and shared demand effects at known ticks.

`tests/test_fault_scheduler.py` checks hand-computed cooldown/timing, hazard
units, per-target scaling, tie admission, caps, independent streams, validation,
zero-rate behavior, enable/disable/reset, session restore, replay tampering,
deployment independence and detector imports. `scripts/check_scheduler_ui.mjs`
exercises the controls and preview against a real local API using a DOM-state
harness; it does not establish visual browser coverage.
