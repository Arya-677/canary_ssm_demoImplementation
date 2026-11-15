import json
from dataclasses import replace
from pathlib import Path

import pytest

from canary_ssm.engine import SimulationEngine, load_engine_config
from canary_ssm.dashboard import WorldController
from canary_ssm.faults import FaultEvent, FaultKind
from canary_ssm.fault_fixtures import run_fixture

ROOT = Path(__file__).resolve().parents[1]


def engine():
    return SimulationEngine(load_engine_config(ROOT / "configs/world_console.yaml"))


def event(**changes):
    args = dict(fault_id="f1", kind="cpu_throttle", scope="host", target="host-01-01",
                start_tick=2, duration=3, severity=.5, seed=10000, recovery="restore")
    return FaultEvent(**(args | changes))


@pytest.mark.parametrize("kind", list(FaultKind))
def test_each_fault_before_during_after_and_truth_separation(kind):
    e, result = run_fixture(kind.value)
    assert result["passed"], result
    truth = e.demo.developer_truth()[0]
    assert truth["duration"] == 3 and truth["end_tick"] == 6
    assert truth["seed"] == 10000 and truth["origin"] == "platform"
    assert isinstance(e.demo.faults[0], FaultEvent)


@pytest.mark.parametrize("changes", [
    {"fault_id": ""}, {"kind": "unknown"}, {"scope": "invalid"}, {"target": ""},
    {"start_tick": True}, {"start_tick": 0}, {"duration": 0}, {"duration": 1.5},
    {"seed": -1}, {"seed": True}, {"severity": float("nan")}, {"severity": True},
    {"severity": 1}, {"recovery": "forever"}, {"kind": "service_crash", "recovery": "restore"},
    {"kind": "network_degradation", "scope": "host"}, {"kind": "demand_surge", "scope": "host"},
])
def test_typed_fault_validation(changes):
    with pytest.raises(ValueError):
        event(**changes)


def test_half_open_timing_and_unknown_targets():
    f = event()
    assert not f.active(1) and f.active(2) and f.active(4) and not f.active(5)
    with pytest.raises(ValueError, match="target"):
        event(target="absent").resolve(engine().world)


def test_overlaps_compose_and_recover_one_at_a_time():
    e = engine()
    for i, duration in enumerate((2, 4)):
        e.operations_command("fault", {"fault_id": f"cpu-{i}", "kind": "cpu_throttle", "scope": "host",
            "target": "host-01-01", "start_tick": 1, "duration": duration, "severity": .5})
    e.step()
    assert e.resource_model.cpu_factors["host-01-01"] == .25
    e.step(2)
    assert e.resource_model.cpu_factors["host-01-01"] == .5
    e.step(2)
    assert e.resource_model.cpu_factors["host-01-01"] == 1


def test_memory_overlaps_are_clamped_and_rack_network_affects_descendants_only():
    e = engine()
    for i in range(2):
        e.operations_command("fault", {"fault_id": f"mem-{i}", "kind": "memory_pressure", "scope": "host",
            "target": "host-01-01", "duration": 2, "severity": .95})
    e.operations_command("fault", {"kind": "network_degradation", "scope": "rack", "target": "rack-02", "duration": 2, "severity": .9})
    e.step()
    rows = e.resource_model.last_hosts
    for r in rows:
        assert r["memory_mb"] <= r["memory_capacity_mb"]
        assert r["network_capacity_mbps"] == pytest.approx(100 if r["rack_id"] == "rack-02" else 1000)
    assert e.resource_model.platform_memory["host-01-01"] > 0
    e.step(2)
    assert e.resource_model.platform_memory["host-01-01"] == 0
    assert all(v == 1 for v in e.resource_model.network_factors.values())


def test_crash_union_restarts_only_after_last_overlap_and_versions_do_not_change():
    e = engine()
    versions = e.world.replicas
    for i, duration in enumerate((2, 4)):
        e.operations_command("fault", {"fault_id": f"crash-{i}", "kind": "service_crash", "scope": "host",
            "target": "host-01-01", "duration": duration})
    e.resource_model.retained["replica-01-01"] = 100
    e.step(3)
    assert "host-01-01" in e.resource_model.unavailable_hosts
    assert e.resource_model.retained["replica-01-01"] == 100
    e.step(2)
    assert "host-01-01" not in e.resource_model.unavailable_hosts
    assert e.resource_model.retained["replica-01-01"] == 0
    assert e.world.replicas == versions


def test_duplicate_fault_ids_and_past_events_do_not_mutate_state():
    e = engine()
    args = {"fault_id": "one", "kind": "cpu_throttle", "scope": "host", "target": "host-01-01"}
    e.operations_command("fault", args)
    before = e.artifact()
    with pytest.raises(ValueError, match="Duplicate"):
        e.operations_command("fault", args)
    assert e.artifact() == before
    with pytest.raises(ValueError):
        e.operations_command("fault", args | {"fault_id": "new", "start_tick": 0})


def test_seeded_schedules_reproduce_and_public_packets_contain_no_fault_truth():
    a, b = engine(), engine()
    for e in (a, b):
        e.operations_command("random_faults", {"seed": 10000, "count": 5})
        e.step(35)
    assert a.artifact() == b.artifact()
    assert SimulationEngine.replay(a.artifact()).artifact() == a.artifact()
    controller = WorldController(a.config)
    controller.engine = a
    public = json.dumps(controller.packet())
    assert "fault_id" not in public and "cpu_throttle" not in public and "developer_fault_truth" not in public
    assert controller.packet()["detector_status"] == "DETECTOR NOT CONNECTED"
