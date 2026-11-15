import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from canary_ssm.engine import EngineConfig, ScheduledEvent, SimulationEngine, load_engine_config
from canary_ssm.resources import ResourceConfig, ResourceModel, ServiceWorkload, TrafficLevel, fair_work
from canary_ssm.topology import DataCenter, Host, HostCapacity, Rack, ServiceReplica, Topology

ROOT = Path(__file__).resolve().parents[1]


def small_world(cores=1, memory=100):
    return Topology((DataCenter("dc"),), (Rack("rack", "dc"),),
                    (Host("host", "rack", "dc", 0, HostCapacity(cores, memory, 100, 100)),),
                    (ServiceReplica("service", "replica", "host", "healthy-v1"),))


def resources(**overrides):
    return ResourceConfig((ServiceWorkload("service", 1, work_core_seconds=1, queue_limit=10,
                                         baseline_memory_mb=2, temporary_mb_per_request=3, **overrides),),
                          host_baseline_memory_mb=1, shared_jitter=0)


class FixedArrivals:
    """Hand-calculated fixture: exact arrivals, all to the sole eligible replica."""
    def __init__(self, count):
        self.count = count

    def random(self):
        return 0.5

    def poisson(self, mean):
        return self.count

    def multinomial(self, count, probabilities):
        assert len(probabilities) == 1
        return [count]


def tick(model, world, n, arrivals):
    model.route(world, n, FixedArrivals(arrivals))
    return model.update(world, n)


def assert_conservation(row):
    assert row["arrivals"] == sum(row[c] for c in ("accepted", "dropped_queue", "dropped_memory", "dropped_arrival_limit", "dropped_unavailable_routes"))
    assert row["queue_start"] + row["accepted"] == row["queue_end"] + row["completed"] + row["dropped_unavailable_queued"]


def test_hand_calculated_work_cpu_memory_queue_and_latency():
    world = small_world(cores=1)
    model = ResourceModel(resources(), world, tick_seconds=1)
    world = tick(model, world, 1, 4)
    row = model.last_hosts[0]
    # Four admitted, one core-second serves one request; 3 remain, each using 3 MB.
    assert row["accepted"] == 4 and row["completed"] == 1 and row["queue_end"] == 3
    assert row["cpu_cores"] == 1
    assert row["memory_baseline_mb"] == 3 and row["memory_temporary_mb"] == 9
    assert row["memory_mb"] == 12 and row["memory_peak_mb"] == 15
    assert row["memory_retained_mb"] == 0
    assert row["latency_proxy_ms"] == 4000  # (1 core-second + 3 core-seconds) / 1 core
    assert_conservation(model.last_services[0])
    for t in range(2, 5):
        world = tick(model, world, t, 0)
    assert model.queued["replica"] == 0
    assert model.last_hosts[0]["memory_mb"] == 3
    assert model.last_hosts[0]["latency_proxy_ms"] == 1000


def test_work_longer_than_tick_carries_partial_progress_without_fractional_requests():
    cfg = replace(resources(), services=(replace(resources().services[0], work_core_seconds=2),))
    world = small_world()
    model = ResourceModel(cfg, world, 1)
    world = tick(model, world, 1, 1)
    assert model.queued["replica"] == 1 and model.progress["replica"] == 1
    assert model.last_hosts[0]["completed"] == 0
    world = tick(model, world, 2, 0)
    assert model.queued["replica"] == 0 and model.progress["replica"] == 0
    assert model.last_hosts[0]["completed"] == 1


def test_units_two_second_tick_and_cpu_budget():
    model = ResourceModel(resources(), small_world(cores=2), 2)
    tick(model, small_world(cores=2), 1, 5)
    row = model.last_hosts[0]
    assert row["completed"] == 4 and row["queue_end"] == 1
    assert row["cpu_cores"] == 2 and row["simulated_seconds"] == 2
    assert row["latency_proxy_ms"] == 1000


def test_arrival_equation_units_and_shared_traffic_level():
    class MeanProbe(FixedArrivals):
        def __init__(self):
            super().__init__(0)
            self.means = []

        def random(self):
            return 1.0  # deterministic upper-end unit fixture

        def poisson(self, mean):
            self.means.append(mean)
            return 0

    cfg = replace(resources(), shared_jitter=0.5, traffic=(TrafficLevel(2, 3),))
    model, probe = ResourceModel(cfg, small_world(), 2), MeanProbe()
    model.route(small_world(), 1, probe)
    model.route(small_world(), 2, probe)
    # 1 request/sec * 2 sec * (1 or 3) * 1.5 shared jitter.
    assert probe.means == [3.0, 9.0]


def test_idle_latency_depends_on_service_work_and_future_profile_is_causal():
    values = []
    for work in (1, 2):
        cfg = replace(resources(), services=(replace(resources().services[0], work_core_seconds=work),))
        model = ResourceModel(cfg, small_world(), 1)
        tick(model, small_world(), 1, 0)
        values.append(model.last_hosts[0]["latency_proxy_ms"])
    assert values == [1000, 2000]
    base = load_engine_config(ROOT / "configs/world_low_load.yaml")
    future = replace(base, resources=replace(base.resources, traffic=(TrafficLevel(21, 100),)))
    a, b = SimulationEngine(base), SimulationEngine(future)
    a.step(20)
    b.step(20)
    assert a.snapshot() == b.snapshot()
    assert a.artifact()["rng_states"] == b.artifact()["rng_states"]


def test_queue_overflow_and_memory_drops_are_distinct():
    cfg = replace(resources(), services=(replace(resources().services[0], queue_limit=3),))
    world = small_world(memory=9)  # 3 MB reserved + 2 queued * 3 MB.
    model = ResourceModel(cfg, world, 1)
    tick(model, world, 1, 8)
    row = model.last_services[0]
    assert row["dropped_queue"] == 5 and row["dropped_memory"] == 1
    assert row["accepted"] == 2 and row["completed"] == 1 and row["queue_end"] == 1
    assert model.last_hosts[0]["memory_peak_mb"] == 9
    assert_conservation(row)


def test_unavailable_host_drops_queue_and_does_not_receive_requests():
    world = small_world()
    model = ResourceModel(resources(), world, 1)
    world = tick(model, world, 1, 4)
    world = replace(world, hosts=(replace(world.hosts[0], lifecycle="offline"),))
    world = tick(model, world, 2, 5)
    row = model.last_services[0]
    assert row["dropped_unavailable_routes"] == 5 and row["dropped_unavailable_queued"] == 3
    assert row["completed"] == row["queue_end"] == 0
    assert model.last_hosts[0]["latency_proxy_ms"] is None and world.hosts[0].usage.cpu_cores == 0
    assert_conservation(row)


def test_retained_memory_is_separate_and_constant_healthy_allocation():
    world = small_world()
    model = ResourceModel(resources(initial_retained_memory_mb=7), world, 1)
    for t in range(1, 5):
        world = tick(model, world, t, 2 if t == 1 else 0)
    row = model.last_hosts[0]
    assert row["memory_baseline_mb"] == 3 and row["memory_retained_mb"] == 7
    assert row["memory_temporary_mb"] == 0 and row["memory_mb"] == 10
    assert world.replicas[0].release_id == "healthy-v1"


def test_fair_share_is_work_conserving_and_bounded():
    assert fair_work({"a": 1, "b": 5, "c": 10}, 9) == {"a": 1, "b": 4, "c": 4}
    assert fair_work({"a": 1, "b": 2}, 10) == {"a": 1, "b": 2}


def test_colocated_services_share_host_cpu_and_memory():
    world = small_world(cores=2)
    world = replace(world, replicas=(*world.replicas, ServiceReplica("second", "replica2", "host", "healthy-v1")))
    cfg = replace(resources(), services=(*resources().services, replace(resources().services[0], service_id="second")))
    model = ResourceModel(cfg, world, 1)
    tick(model, world, 1, 4)  # 4 arrivals for each service.
    assert model.last_hosts[0]["completed"] == 2
    assert model.last_hosts[0]["cpu_cores"] == 2
    assert model.queued == {"replica": 3, "replica2": 3}
    assert model.last_hosts[0]["memory_baseline_mb"] == 5
    assert model.last_hosts[0]["memory_mb"] == 23
    for row in model.last_services:
        assert_conservation(row)


def test_multinomial_routes_only_to_available_replicas_and_shared_factor():
    config = load_engine_config(ROOT / "configs/world_low_load.yaml")
    engine = SimulationEngine(config)
    engine.schedule(ScheduledEvent("offline", 1, "set_host_lifecycle", "host-01-01", "offline"))
    engine.step(4)
    rows = engine.resource_model.trace()["hosts"]
    assert all(r["routed_requests"] == 0 for r in rows if r["host_id"] == "host-01-01")
    assert sum(r["routed_requests"] for r in rows if r["host_id"] != "host-01-01") > 0
    world = small_world()
    model = ResourceModel(replace(resources(), services=(*resources().services, replace(resources().services[0], service_id="absent-service")), shared_jitter=0.5), world, 1)
    model.route(world, 1, np.random.default_rng(0))
    assert len({r["shared_traffic_factor"] for r in model._service_counts.values()}) == 1
    model.update(world, 1)
    assert_conservation(model.last_services[1])


def test_arrival_cap_reports_drops_and_bounded_trace_ring():
    cfg = replace(resources(), max_arrivals_per_service_tick=5, trace_max_rows=2)
    model = ResourceModel(cfg, small_world(), 1)
    world = small_world()
    for t in range(1, 5):
        world = tick(model, world, t, 100)
    assert model.last_services[0]["dropped_arrival_limit"] == 95
    assert len(model.host_trace) == 2 and model.trace_rows_evicted == {"host": 2, "service": 2}
    assert_conservation(model.last_services[0])


def test_resource_reset_replay_and_trace_tampering(tmp_path):
    cfg = load_engine_config(ROOT / "configs/world_recovery.yaml")
    a, b = SimulationEngine(cfg), SimulationEngine(cfg)
    for engine in (a, b):
        engine.step(100)
    assert a.artifact() == b.artifact()
    initial = a.snapshot()
    a.reset()
    a.step(100)
    assert a.snapshot() == initial and a.artifact()["resource_trace"] == b.artifact()["resource_trace"]
    a.save(tmp_path / "run.json")
    assert SimulationEngine.replay(json.loads((tmp_path / "run.json").read_text())).artifact() == a.artifact()
    bad = copy.deepcopy(a.artifact())
    bad["resource_trace"]["hosts"][0]["cpu_cores"] = 99
    with pytest.raises(ValueError, match="replay verification"):
        SimulationEngine.replay(bad)


@pytest.mark.parametrize("field,value", [("work_core_seconds", 0), ("work_core_seconds", float("inf")),
    ("queue_limit", True), ("queue_limit", 10001), ("arrival_rate_rps", -1),
    ("temporary_mb_per_request", -1), ("baseline_memory_mb", "128")])
def test_invalid_service_units(field, value):
    with pytest.raises(ValueError):
        replace(resources().services[0], **{field: value})


def test_invalid_placement_memory_profiles_and_resource_schema():
    with pytest.raises(ValueError, match="exceeds capacity"):
        EngineConfig(small_world(memory=2), resources=resources())
    with pytest.raises(ValueError, match="service configuration"):
        EngineConfig(small_world(), resources=replace(resources(), services=(replace(resources().services[0], service_id="wrong"),)))
    with pytest.raises(ValueError, match="increasing"):
        replace(resources(), traffic=(TrafficLevel(2, 1), TrafficLevel(1, 2)))
    with pytest.raises(ValueError):
        ResourceConfig.from_dict({"services": [], "unknown": 1})


def test_low_increased_and_recovery_behavior_from_actual_traces():
    engine = SimulationEngine(load_engine_config(ROOT / "configs/world_recovery.yaml"))
    engine.step(100)
    rows = engine.resource_model.trace()["hosts"]
    low = [r for r in rows if r["tick"] <= 20]
    high = [r for r in rows if 30 <= r["tick"] <= 60]
    final = [r for r in rows if r["tick"] >= 90]
    for metric in ("cpu_cores", "memory_mb", "queue_end", "latency_proxy_ms"):
        assert np.mean([r[metric] for r in high]) > np.mean([r[metric] for r in low])
    assert all(r["queue_end"] == 0 for r in final)
    assert all(0 <= r["cpu_utilization"] <= 1 and r["memory_peak_mb"] <= r["memory_capacity_mb"] and 0 <= r["queue_end"] <= 300 for r in rows)
    for row in engine.resource_model.service_trace:
        assert_conservation(row)


def test_cli_resource_traces(tmp_path, capsys):
    from canary_ssm.cli import main
    main(["world-run", "--config", str(ROOT / "configs/world_low_load.yaml"), "--ticks", "3",
          "--out", str(tmp_path / "run.json"), "--trace-out", str(tmp_path / "trace")])
    assert json.loads(capsys.readouterr().out)["tick"] == 3
    assert (tmp_path / "trace/hosts.csv").exists() and (tmp_path / "trace/services.csv").exists()
