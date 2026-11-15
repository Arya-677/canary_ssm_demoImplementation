# Deterministic world clock (chunk 02)

Chunk 03 adds an optional `engine.resources` configuration and bounded resource
phase adapters to this same clock; see [resources.md](resources.md). The static
`world_clock.yaml` fixture described below is retained. Replay now checks the
selected adapter and resource code hash when resource modeling is enabled.

Run the headless 100-tick fixture from the repository root:

```bash
python -m canary_ssm world-run --config configs/world_clock.yaml --ticks 100 --out world_clock_run.json
python -m canary_ssm world-replay --artifact world_clock_run.json
```

The first command writes a replay artifact and prints a small summary. The
second reconstructs the run from its initial configuration and accepted
commands, verifies the derived event log, publication hashes, final snapshot
and RNG states, and prints `replay_verified: true`. Neither command fits or
runs an SSM or needs a browser. The topology file is resolved relative to the
clock config, not the shell's working directory. Existing research commands
and the statistical latency simulator retain their original behavior.

## Clock and lifecycle

`engine.load_engine_config(path) -> EngineConfig` uses the existing shared
YAML reader and topology loader. A clock config contains exactly one of
`topology_file` or inline `topology`, and an optional `engine` mapping with
`seed`, `tick_seconds` and `events`. Unknown fields are rejected. The default
seed is `seeds.seed_for("smoke", 0)`; this fixture uses that registered smoke
seed explicitly. This world-clock fixture is not a research calibration/test
data generator and must not be mixed into those roles.

```python
from canary_ssm.engine import SimulationEngine, ScheduledEvent, load_engine_config

engine = SimulationEngine(load_engine_config("configs/world_clock.yaml"))
engine.start()
engine.advance(10)
engine.pause()
engine.schedule(ScheduledEvent("operator-note", at_tick=12))
engine.step(2)
engine.resume()
engine.advance(88)
engine.pause()
engine.save("run.json")
engine.reset()
```

| Operation | Required state | Result |
| --- | --- | --- |
| Construct | — | `ready`, tick 0, initial topology/RNGs/events |
| `start()` | ready | running; no implicit tick |
| `advance(n=1)` | running | Exactly n ticks |
| `pause()` | running | paused; clock, world and RNGs stop advancing |
| `resume()` | paused | running; no implicit tick |
| `step(n=1)` | ready or paused | Exactly n ticks, ending paused |
| `reset()` | any | ready at tick 0, original world, fresh RNGs, original event queue |
| `schedule(event)` | any | Add a validated future world event without advancing time |

Tick counts must be positive integers, with booleans rejected. Invalid state
transitions, past/current events, duplicate event IDs and unknown host targets
fail without modifying the engine. No thread, wall-clock timer, sleep or
playback speed exists in this kernel. A later UI/driver can call `advance` at
its chosen wall-clock frequency; `simulated_seconds = tick * tick_seconds`
remains unchanged by that frequency. Tick 1 is the first completed tick.

## Stable tick phases

Every tick executes these phases synchronously:

1. Increment the simulated tick and apply events due at that tick.
2. Route workload through `route_workload()`.
3. Update world resources through `update_resources(workload)`.
4. Emit observations through `emit_observations()`.
5. Publish the resulting snapshot by appending its hash and phase sequence.

Events are sorted by `(at_tick, insertion_order)`. Initial events take their
order from the config list; subsequently scheduled events receive monotonically
increasing insertion indices. Event names do not change this order. A tie of
host lifecycle commands applies sequentially, so the final command determines
that host's state before routing begins. Events run once per reset epoch.

Supported actions are `marker` and `set_host_lifecycle`; the latter requires
an existing `host_id` and `ready`, `offline` or `maintenance`. These are manual
world-state commands, not random fault mechanisms. Events cannot invoke clock
controls recursively. Operator clock commands are recorded outside tick phases.

## Honest phase adapters and RNG contract

This chunk's default routing adapter explicitly reports `static-no-workload`
and zero routed requests. Resource update retains the topology's usage records.
Observations are host-state/usage snapshots, not latency measurements or
request statistics. The fixture's maintenance/ready commands demonstrate event
ordering without simulating service outages or recovery physics.

`rngs` holds four independent explicit NumPy PCG64 generators, keyed by
`workload`, `faults`, `host_noise`, and `telemetry_loss`. Each uses
`SeedSequence([root_seed, fixed_stream_index])`; adding draws to one does not
advance another. The static adapters do not need random draws yet. Tests use
a separately labeled, test-only phase adapter to consume all four streams and
prove reset/replay equivalence with nontrivial RNG state.

Later chunks should replace the named phase adapters within this engine.
Adapters must use their designated RNGs, frozen configuration and engine state,
without hidden external mutable state or wall time. External ad hoc RNG draws
or direct attribute mutation are not replay commands. The replay CLI supports
the versioned built-in static and resource adapters; future changes need their
own version and replay compatibility contract.

## Snapshot, reset and replay artifacts

`snapshot()` returns a detached dictionary containing tick, simulated seconds,
engine state, the full topology snapshot, routed workload and observations.
It contains no wall-clock timestamp. `log` returns a detached ordered log;
entries include sequence number, simulated tick, accepted command, applied
event/insertion index, or published snapshot hash/phase order.

Reset restores the configured topology, all four RNG initial states, tick,
pending initial events and their insertion indices. It discards dynamically
scheduled events and clears the latest workload/observations. It retains the
audit log including the reset command; sequence numbers stay monotonic even
though simulated ticks return to zero. Applied initial events run again after
reset. A caller requesting a wholly new empty audit log creates a new engine.

`save(path)` writes JSON schema version 1 with embedded initial topology,
engine config, seed, complete ordered log, final snapshot, RNG states and a
manifest of config hash, engine source hash and environment versions. It does
not depend on the original topology config file remaining present. Replay
reexecutes commands and checks derived evidence, rejecting incompatible schema,
engine ID/source, NumPy version or altered config/log/output/RNG state. This is
an integrity/compatibility check, not a security signature. The engine records
no git provenance itself; this project is an extracted ZIP without `.git`.

The 100-tick fixture verifies the clock/replay mechanism only. Queueing,
resource dynamics, faults, telemetry aggregation and detectors remain later
chunks. See [implementation status](implementation_status.md) and
[the checkpoint report](wp/ENGINE-02.md).
