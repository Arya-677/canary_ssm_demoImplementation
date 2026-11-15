# Typed platform faults

`faults.FaultEvent` is an immutable validated event, resolved to stable host IDs
before scheduling. `operations.DemoOperations.before_tick` applies its effects
before routing and resource updates. `resources.ResourceModel` produces the
resulting observations. No inference code is involved.

## Contract and timing

Required fields are `fault_id`, `kind`, `scope`, `target`, `start_tick`,
`duration`, `severity`, `seed`, and `recovery`. The manual handler supplies
documented defaults: next tick, five ticks, severity 0.75, engine seed, and
the recovery appropriate to the kind. Supply `start_tick` or relative `delay`,
never both. Events are active on `[start_tick, start_tick + duration)`.
Duration is an integer 1–1000 ticks, severity is finite 0.1–0.95, seed is an
integer in `[0, 2^32)`, and start must be within the next 1000 ticks.
Duplicate IDs, unknown/empty targets, inappropriate scope/recovery, booleans
in numeric fields and unknown arguments are rejected before mutation. At most
100 faults are retained per reset. Ties use accepted schedule insertion order.

| Kind | Scope | Resource effect | Recovery and overlap |
| --- | --- | --- | --- |
| `cpu_throttle` | host or rack | Effective host cores multiplied by `1-severity` | Restore when inactive; active factors multiply, floored at 0.05 |
| `memory_pressure` | host or rack | Platform memory requested as `severity * physical_memory_mb` | Requests sum, clamped to headroom after baseline, retained and existing request memory; allocation disappears when inactive |
| `service_crash` | host or rack | All service replicas on descendants become unavailable, receive no routing or CPU work; queued requests drop explicitly | Availability is the union of active crashes; restart once after the last overlap ends, clearing queue/progress and returning retained allocation to its configured baseline; release ID stays unchanged |
| `network_degradation` | rack only | Each descendant host's effective Mbps multiplied by `1-severity`; work/completions are network bounded and latency proxy increases | Restore when inactive; factors multiply, floored at 0.05 |
| `demand_surge` | world, target `world` | Shared service arrival rate multiplied by `1+7*severity` | Multipliers multiply, capped at 8; normal shared traffic variation remains separate |

All five effects may coexist. Factors and allocations are recomputed from the
active set each tick, so expiry of one event never erases a remaining event.
Crash wins over serving capacity: no requests are processed while unavailable.
Rack targets resolve through real descendants; they do not set a UI rack color.
This simulator's service-crash target is a host or rack, so it stops all placed
replicas there; independent single-process targeting is not implemented.

## Bounded physical approximations

These are laptop simulation assumptions, not measured data-center models.
Let `dt` be seconds/tick, `C` physical cores, `M` physical MB and `N` physical
Mbps. CPU budget is `C * cpu_factor * pressure_factor * dt` core-seconds.
When platform memory or a leak profile is present, with occupancy `o` including
baseline/platform/retained/temporary memory, the pressure factor is
`max(0.1, 1 - 4*max(0, o-0.8))`. It is a deliberately bounded slowdown.
Platform pressure never evicts existing requests and never exceeds physical
memory; this is not an OOM-killer implementation.

CPU-allocated work is also constrained by network budget. Each processed
request-equivalent transfers 0.064 decimal MB (0.512 megabits); available
request-equivalents/tick are `N * network_factor * dt / 0.512`. Work and
network transfer progress together, including fractional unfinished requests.
Usage is in Mbps, `request_equivalents * 0.512 / dt`. The latency estimate
adds the incremental serialization delay
`1000 * 0.512/N * (1/network_factor - 1)` ms to the CPU/backlog proxy.
There are no packet queues, link contention, retries or measured percentiles.

The request conservation identity includes restart drops:
`queue_start + accepted = queue_end + completed + dropped_unavailable_queued + dropped_restart`.
No-route arrivals, queue overflow, memory rejection and capped arrivals retain
their separate counters. See [resources.md](resources.md) for base equations.

## Platform truth versus release behavior

Fault records have `origin: platform` and do not change release versions or
release profile parameters. Slow/leak candidate profiles are selected separately
through the release registry. Their work/retention behavior is not a platform
fault event. A crash restart may reclaim application memory while keeping its
release profile active; a continuing leak can accumulate again after recovery.

`/api/state`, public snapshots and host/service CSV telemetry contain resource
measurements, availability and release IDs, with no event IDs, seeds, severity,
fault kind or active-truth labels. `memory_platform_mb` is simulated resource
accounting, not a detector classification. Developer truth is returned only by
the separate `/api/fault-lab?developer=1` route and explicit replay artifacts.
This separation is for demo/evaluation honesty; the local developer route is
not a security or authentication boundary. Full saved runs include command logs
and truth for reproducibility and must not become detector inputs.

## Manual entry points and deterministic fixtures

```bash
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765
python -m canary_ssm.fault_fixtures --out examples/faults
```

The dashboard's Fault Lab has all five mechanisms, scope/target, duration,
severity and seed. For precise tick/ID/recovery control, use the engine:

```python
from canary_ssm.engine import SimulationEngine, load_engine_config
e = SimulationEngine(load_engine_config("configs/world_console.yaml"))
e.operations_command("fault", {
    "fault_id": "rack-link-1", "kind": "network_degradation", "scope": "rack",
    "target": "rack-02", "start_tick": 3, "duration": 3, "severity": 0.9,
    "seed": 10000, "recovery": "restore",
})
e.step(8)
e.export_traces("fault_trace")
e.save("fault_run.json")
```

Each `examples/faults/<kind>/` has eight ticks: before 1–2, during 3–5,
after 6–8; saved host/service CSVs, verified `run.json`, separate truth and
`checks.json`. `tests/test_faults.py` also covers tied overlaps, recovery after
the last crash, memory bounds, target validation and deterministic replay.
Seed is provenance for deterministic manual effects; it does not add random
jitter. Optional `random_faults` uses its own seeded PCG64 schedule stream
(`SeedSequence([seed, 1])`) to choose bounded host CPU/crash events, independently
of workload RNG. Given equal seed, world, acceptance tick and count it repeats.


The rate-based background scheduler is documented in [fault_scheduler.md](fault_scheduler.md).
Its pre-generated events, scope scaling, cooldowns, budgets and enable/disable
controls are separate from explicit manual faults and deployment profiles.
The earlier `random_faults` command is a fixed-count manual batch, not a rate model.
