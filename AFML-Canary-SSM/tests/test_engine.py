import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from canary_ssm.engine import (EngineConfig, EngineState, PHASES, RNG_STREAMS,
                               ScheduledEvent, SimulationEngine, load_engine_config)

ROOT = Path(__file__).resolve().parents[1]


def config():
    return load_engine_config(ROOT / "configs/world_clock.yaml")


class RandomProbeEngine(SimulationEngine):
    """Test-only stateless phase adapter, not a physical resource model."""
    def route_workload(self):
        return {"workload_draw": int(self.rngs["workload"].integers(0, 100000)),
                "fault_draw": int(self.rngs["faults"].integers(0, 100000))}

    def emit_observations(self):
        return [{"noise": float(self.rngs["host_noise"].normal()),
                 "loss": float(self.rngs["telemetry_loss"].random())}]


def test_100_tick_headless_fixture_reproducible():
    a, b = SimulationEngine(config()), SimulationEngine(config())
    for engine in (a, b):
        engine.start()
        engine.advance(100)
        engine.pause()
    assert a.artifact() == b.artifact()
    assert a.tick == a.snapshot()["simulated_seconds"] == 100
    assert len(a.snapshot()["observations"]) == 20
    assert sum(e["kind"] == "published" for e in a.log) == 100
    assert SimulationEngine.replay(a.artifact()).artifact() == a.artifact()


def test_start_pause_resume_step_and_no_implicit_wall_clock():
    engine = SimulationEngine(config())
    engine.start()
    engine.advance(4)
    engine.pause()
    frozen = engine.artifact()
    for _ in range(5):
        assert engine.snapshot() == frozen["final_snapshot"]
    with pytest.raises(ValueError, match="running"):
        engine.advance()
    assert engine.artifact() == frozen
    engine.step(2)
    assert engine.tick == 6 and engine.state == EngineState.PAUSED
    engine.resume()
    engine.advance()
    assert engine.tick == 7
    with pytest.raises(ValueError, match="pause"):
        engine.step()
    assert SimulationEngine.replay(engine.artifact()).artifact() == engine.artifact()


def test_tick_units_and_step_from_ready():
    engine = SimulationEngine(replace(config(), tick_seconds=5))
    engine.step(3)
    assert engine.tick == 3 and engine.snapshot()["simulated_seconds"] == 15
    assert engine.state == EngineState.PAUSED


def test_event_ties_and_phase_order():
    cfg = replace(config(), events=(
        ScheduledEvent("z-first", 1, "set_host_lifecycle", "host-01-01", "offline"),
        ScheduledEvent("a-second", 1, "set_host_lifecycle", "host-01-01", "maintenance")))
    seen = []

    class TraceEngine(SimulationEngine):
        def route_workload(self):
            assert self.world.hosts[0].lifecycle.value == "ready"
            seen.append("route_workload")
            return super().route_workload()

        def update_resources(self, workload):
            seen.append("update_resources")
            return super().update_resources(workload)

        def emit_observations(self):
            seen.append("emit_observations")
            return super().emit_observations()

    engine = TraceEngine(cfg)
    engine.schedule(ScheduledEvent("runtime-last", 1, "set_host_lifecycle", "host-01-01", "ready"))
    engine.step()
    assert seen == list(PHASES[1:4])
    assert [x["event"]["event_id"] for x in engine.log if x["kind"] == "event"] == [
        "z-first", "a-second", "runtime-last"]
    assert engine.log[-1]["kind"] == "published"
    assert engine.log[-1]["phases"] == list(PHASES)
    assert engine.snapshot()["observations"][0]["lifecycle"] == "ready"


def test_pause_preserves_pending_events_and_reset_restores_world_and_queue():
    engine = SimulationEngine(config())
    engine.step(25)
    assert engine.world.hosts[0].lifecycle.value == "maintenance"
    engine.schedule(ScheduledEvent("runtime", 26))
    engine.reset()
    assert engine.tick == 0 and engine.state == EngineState.READY
    assert engine.world == config().topology
    engine.step(30)
    events = [x["event"]["event_id"] for x in engine.log if x["kind"] == "event"]
    assert "runtime" not in events
    assert events.count("baseline-marker") == 2
    assert engine.world.hosts[0].lifecycle.value == "ready"
    assert SimulationEngine.replay(engine.artifact()).artifact() == engine.artifact()


def test_rng_reset_and_replay_with_test_phase_adapter():
    engine = RandomProbeEngine(config())
    engine.step(20)
    expected_snapshot = engine.snapshot()
    expected_rng = engine.artifact()["rng_states"]
    engine.reset()
    engine.step(20)
    assert engine.snapshot() == expected_snapshot
    assert engine.artifact()["rng_states"] == expected_rng
    assert RandomProbeEngine.replay(engine.artifact()).artifact() == engine.artifact()
    assert RandomProbeEngine(replace(config(), seed=config().seed + 1)).artifact()["rng_states"] != expected_rng


@pytest.mark.parametrize("stream", RNG_STREAMS)
def test_rng_stream_consumption_is_independent(stream):
    a, b = SimulationEngine(config()), SimulationEngine(config())
    a.rngs[stream].random(100)
    for other in RNG_STREAMS:
        if other != stream:
            assert a.rngs[other].random() == b.rngs[other].random()
    a.reset()
    fresh = SimulationEngine(config())
    assert a.artifact()["rng_states"] == fresh.artifact()["rng_states"]


def test_runtime_schedule_save_replay_and_detached_snapshots(tmp_path):
    engine = SimulationEngine(config())
    engine.start()
    engine.advance(2)
    engine.schedule(ScheduledEvent("later", 200))
    engine.pause()
    out = tmp_path / "nested" / "run.json"
    engine.save(out)
    replay = SimulationEngine.replay(json.loads(out.read_text()))
    replay.resume()
    replay.advance(198)
    assert replay.log[-2]["event"]["event_id"] == "later"
    snap = engine.snapshot()
    snap["world"]["hosts"][0]["host_id"] = "modified"
    log = engine.log
    log.clear()
    assert engine.world.hosts[0].host_id == "host-01-01"
    assert engine.log


@pytest.mark.parametrize("field", ["log", "final_snapshot", "rng_states", "seed", "config", "manifest"])
def test_replay_rejects_tampering(field):
    engine = SimulationEngine(config())
    engine.step(2)
    artifact = copy.deepcopy(engine.artifact())
    if field == "log":
        artifact["log"][-1]["snapshot_hash"] = "changed"
    elif field == "final_snapshot":
        artifact[field]["tick"] = 500
    elif field == "rng_states":
        artifact[field]["workload"]["state"]["state"] += 1
    elif field == "seed":
        artifact[field] += 1
    elif field == "config":
        artifact[field]["tick_seconds"] += 1
    else:
        artifact[field]["engine_sha256"] = "incompatible"
    with pytest.raises(ValueError):
        SimulationEngine.replay(artifact)


@pytest.mark.parametrize("ticks", [0, -1, True, 1.5])
def test_invalid_tick_counts_do_not_mutate_engine(ticks):
    engine = SimulationEngine(config())
    original = engine.artifact()
    with pytest.raises(ValueError):
        engine.step(ticks)
    assert engine.artifact() == original


def test_invalid_events_and_transitions_do_not_mutate_engine():
    engine = SimulationEngine(config())
    original = engine.artifact()
    for command in (engine.resume, engine.pause, engine.advance):
        with pytest.raises(ValueError):
            command()
    for event in (ScheduledEvent("baseline-marker", 1),
                  ScheduledEvent("orphan", 1, "set_host_lifecycle", "missing-host", "ready")):
        with pytest.raises(ValueError):
            engine.schedule(event)
    assert engine.artifact() == original
    engine.step()
    with pytest.raises(ValueError):
        engine.schedule(ScheduledEvent("past", 1))


@pytest.mark.parametrize("updates", [{"seed": -1}, {"tick_seconds": 0}, {"tick_seconds": True},
                                    {"events": [ScheduledEvent("dup", 1), ScheduledEvent("dup", 2)]}])
def test_invalid_config(updates):
    with pytest.raises(ValueError):
        replace(config(), **updates)


def test_loader_resolves_relative_topology_without_working_directory_dependency():
    assert len(config().topology.hosts) == 20


def test_cli_headless_and_replay(tmp_path, capsys):
    from canary_ssm.cli import main
    path = tmp_path / "run.json"
    main(["world-run", "--config", str(ROOT / "configs/world_clock.yaml"), "--ticks", "100", "--out", str(path)])
    assert json.loads(capsys.readouterr().out)["tick"] == 100
    main(["world-replay", "--artifact", str(path)])
    assert json.loads(capsys.readouterr().out)["replay_verified"] is True
