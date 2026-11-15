"""Headless world -> release -> fault -> telemetry -> rollback acceptance demo."""
import argparse
import base64
import json
from pathlib import Path

from .dashboard import WorldController
from .engine import SimulationEngine, load_engine_config


def export_demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    config = Path(__file__).resolve().parents[1] / "configs/world_console.yaml"
    c = WorldController(load_engine_config(config), run_id="console-demo", wall_time=lambda: 0.0)

    def command(name, args=None):
        payload = {"command_id": f"demo-{c.revision}", "run_id": c.run_id,
                   "epoch": c.epoch, "command": name}
        if args is not None:
            payload["args"] = args
        return c.command(payload)

    def steps(count):
        for _ in range(count):
            command("step")

    steps(3)
    baseline = {r.replica_id: r.release_id for r in c.engine.world.replicas}
    upload = command("register_release", {"filename": "candidate.py", "profile": "leak",
        "content_base64": base64.b64encode(b'raise RuntimeError("this artifact must never execute")\n').decode()})["result"]
    plan = command("preview", {"release_id": upload["release_id"], "per_rack": 1})["result"]
    command("deploy", {"plan_id": plan["plan_id"]})
    steps(6)
    canary_rows = c.engine.resource_model.last_hosts
    (directory / "canary_snapshot.json").write_text(json.dumps(c.packet(), indent=2) + "\n")
    command("fault", {"fault_id": "demo-rack-network", "kind": "network_degradation",
        "scope": "rack", "target": "rack-02", "duration": 4, "severity": .9, "seed": 10000})
    command("random_faults", {"seed": 10000, "count": 3})
    steps(8)
    command("rollback", {})
    steps(35)
    artifact = c.engine.artifact()
    saved = c.export_run()
    replay = WorldController(load_engine_config(config))
    replay.command({"command_id": "import", "run_id": replay.run_id, "epoch": 0,
                    "command": "load_run", "args": {"run": saved}})
    checks = {
        "upload_never_executed": upload["executed"] is False,
        "valid_allocation": len(plan["canaries"]) == 4 and len(plan["controls"]) == 16
                            and all(len(r["controls"]) >= 3 for r in plan["racks"]),
        "candidate_retains_memory": any(r["memory_retained_mb"] > 0 for r in canary_rows if r["host_id"] in plan["canaries"]),
        "controls_keep_healthy_memory": all(r["memory_retained_mb"] == 0 for r in canary_rows if r["host_id"] in plan["controls"]),
        "rack_effect_reaches_descendants": any(r["rack_id"] == "rack-02" and r["network_capacity_mbps"] < 1000
                                                for r in c.engine.resource_model.host_trace),
        "rollback_restores_versions": {r.replica_id: r.release_id for r in c.engine.world.replicas} == baseline,
        "rollback_reclaims_retained_memory": all(r["memory_retained_mb"] == 0 for r in c.engine.resource_model.last_hosts),
        "detector_honest": c.packet()["detector_status"] == "DETECTOR NOT CONNECTED",
        "public_packet_excludes_truth": "fault_id" not in json.dumps(c.packet()),
        "verified_engine_replay": SimulationEngine.replay(artifact).artifact() == artifact,
        "saved_run_import_matches": replay.read_only and replay.engine.snapshot() == c.engine.snapshot(),
        "outcomes_saved": len(saved["outcomes"]) == c.outcome_sequence > 0,
    }
    c.engine.export_traces(directory)
    (directory / "run.json").write_text(json.dumps(saved, indent=2) + "\n")
    (directory / "developer_fault_truth.json").write_text(json.dumps({"developer_only": True,
        "injected_truth": c.engine.demo.developer_truth()}, indent=2) + "\n")
    result = {"synthetic": True, "ticks": c.engine.tick, "checks": checks, "passed": all(checks.values())}
    (directory / "exit_gate.json").write_text(json.dumps(result, indent=2) + "\n")
    c.close()
    replay.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="examples/console_demo")
    result = export_demo(parser.parse_args().out)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
