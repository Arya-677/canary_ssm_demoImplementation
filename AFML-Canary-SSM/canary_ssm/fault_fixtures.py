"""Tiny deterministic before/during/after fixtures. Truth is saved separately."""
from pathlib import Path
import argparse
import json

from .engine import EngineConfig, SimulationEngine
from .faults import FaultKind
from .resources import ResourceConfig, ServiceWorkload
from .seeds import seed_for
from .topology import DataCenter, Rack, Host, HostCapacity, ServiceReplica, Topology


def run_fixture(kind):
    world = Topology((DataCenter("dc"),), (Rack("rack-a", "dc"), Rack("rack-b", "dc")),
        tuple(Host(f"host-{x}", f"rack-{x}", "dc", 0, HostCapacity(2, 256, 1000, 100)) for x in ("a", "b")),
        tuple(ServiceReplica("service", f"replica-{x}", f"host-{x}", "healthy-v1") for x in ("a", "b")))
    config = ResourceConfig((ServiceWorkload("service", 120, work_core_seconds=.01,
        queue_limit=80, baseline_memory_mb=16, temporary_mb_per_request=1),),
        shared_jitter=0, host_baseline_memory_mb=16)
    engine = SimulationEngine(EngineConfig(world, seed=seed_for("smoke", 0), resources=config, demo=True))
    scope = "world" if kind == "demand_surge" else "rack" if kind == "network_degradation" else "host"
    target = "world" if scope == "world" else "rack-a" if scope == "rack" else "host-a"
    engine.operations_command("fault", {"fault_id": f"fixture-{kind}", "kind": kind, "scope": scope,
        "target": target, "start_tick": 3, "duration": 3, "severity": .95 if kind == "network_degradation" else .9,
        "seed": seed_for("smoke", 0), "recovery": "restart" if kind == "service_crash" else "restore"})
    engine.step(8)
    rows = engine.resource_model.trace()["hosts"]
    a = [r for r in rows if r["host_id"] == "host-a"]
    b = [r for r in rows if r["host_id"] == "host-b"]
    during, after = a[2:5], a[5:]
    checks = {"deterministic_replay": SimulationEngine.replay(engine.artifact()).artifact() == engine.artifact(),
              "before_available": all(r["available"] for r in a[:2]),
              "recovered_available": all(r["available"] for r in after),
              "memory_bounded": all(0 <= r["memory_mb"] <= r["memory_capacity_mb"] for r in rows),
              "no_truth_in_telemetry": not any(k in r for r in rows for k in ("fault_id", "kind", "seed", "severity", "active"))}
    if kind == "cpu_throttle":
        checks.update(effect=all(r["cpu_capacity_cores"] < 2 for r in during),
            scope=all(r["cpu_capacity_cores"] == 2 for r in b), recovery=all(r["cpu_capacity_cores"] == 2 for r in after))
    elif kind == "memory_pressure":
        checks.update(effect=all(r["memory_platform_mb"] > 0 for r in during),
            scope=all(r["memory_platform_mb"] == 0 for r in b), recovery=all(r["memory_platform_mb"] == 0 for r in after))
    elif kind == "service_crash":
        checks.update(effect=all(not r["available"] and r["completed"] == 0 for r in during),
            scope=all(r["available"] for r in b), recovery=all(r["available"] for r in after))
    elif kind == "network_degradation":
        checks.update(effect=all(r["network_capacity_mbps"] < 100 for r in during) and any(r["queue_end"] > 0 for r in during),
            scope=all(r["network_capacity_mbps"] == 100 for r in b), recovery=all(r["network_capacity_mbps"] == 100 for r in after))
    else:
        checks.update(effect=sum(r["routed_requests"] for r in during) > sum(r["routed_requests"] for r in a[:2]),
            scope=sum(r["routed_requests"] for r in b[2:5]) > sum(r["routed_requests"] for r in b[:2]),
            recovery=engine.resource_model.demand_multiplier == 1)
    return engine, {"kind": kind, "checks": checks, "passed": all(checks.values())}


def export_fixtures(directory):
    directory = Path(directory)
    results = []
    for kind in FaultKind:
        engine, result = run_fixture(kind.value)
        out = directory / kind.value
        engine.export_traces(out)
        engine.save(out / "run.json")
        (out / "fault_truth.json").write_text(json.dumps({"developer_only": True,
            "faults": engine.demo.developer_truth()}, indent=2) + "\n")
        (out / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
        results.append(result)
    summary = {"fixtures": results, "passed": all(r["passed"] for r in results)}
    (directory / "fixture_checks.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="examples/faults")
    result = export_fixtures(parser.parse_args().out)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
