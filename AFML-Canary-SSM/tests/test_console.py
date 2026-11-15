import base64
import json
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from canary_ssm.dashboard import ApiError, WorldController, make_server
from canary_ssm.engine import load_engine_config, SimulationEngine

ROOT = Path(__file__).resolve().parents[1]


def controller(directory=None):
    return WorldController(load_engine_config(ROOT / "configs/world_console.yaml"), state_dir=directory)


def command(c, name, args=None, cid=None):
    payload = {"command_id": cid or f"c-{c.revision}", "run_id": c.run_id, "epoch": c.epoch, "command": name}
    if args is not None:
        payload["args"] = args
    return c.command(payload)


def test_complete_release_fault_telemetry_rollback_without_detector(tmp_path):
    c = controller(tmp_path / "state")
    uploaded = command(c, "register_release", {"filename": "candidate.py", "content_base64": base64.b64encode(b'raise RuntimeError("must not execute")').decode(), "profile": "leak"})["result"]
    assert uploaded["executed"] is False
    plan = command(c, "preview", {"release_id": uploaded["release_id"], "per_rack": 1})["result"]
    assert len(plan["canaries"]) == 4 and len(plan["controls"]) == 16
    assert all(len(r["controls"]) >= 3 for r in plan["racks"])
    baseline = {r.replica_id: r.release_id for r in c.engine.world.replicas}
    command(c, "deploy", {"plan_id": plan["plan_id"]})
    for _ in range(6):
        command(c, "step")
    for r in c.engine.world.replicas:
        assert r.release_id == (uploaded["release_id"] if r.host_id in plan["canaries"] else baseline[r.replica_id])
    assert any(row["memory_retained_mb"] > 0 for row in c.engine.resource_model.last_hosts if row["host_id"] in plan["canaries"])
    assert all(row["memory_retained_mb"] == 0 for row in c.engine.resource_model.last_hosts if row["host_id"] in plan["controls"])
    command(c, "fault", {"kind": "network_degradation", "scope": "rack", "target": "rack-02", "duration": 2})
    command(c, "random_faults", {"seed": 10000, "count": 3})
    command(c, "step")
    assert c.packet()["detector_status"] == "DETECTOR NOT CONNECTED"
    command(c, "rollback", {})
    command(c, "step")
    assert c.engine.demo.deployment["status"] == "rolled_back"
    assert {r.replica_id: r.release_id for r in c.engine.world.replicas} == baseline
    command(c, "rollback", {})  # idempotent after completion
    artifact = c.engine.artifact()
    assert SimulationEngine.replay(artifact).artifact() == artifact
    for row in c.engine.resource_model.service_trace:
        assert row["queue_start"]+row["accepted"] == row["queue_end"]+row["completed"]+row["dropped_unavailable_queued"]+row["dropped_restart"]
    saved = c.export_run()
    c.close()
    resumed = controller(tmp_path / "state")
    assert resumed.run_id == c.run_id
    assert resumed.engine.snapshot() == c.engine.snapshot()
    assert resumed.outcomes == c.outcomes
    replay = controller()
    command(replay, "load_run", {"run": saved})
    assert replay.read_only and replay.packet()["mode"] == "replay"
    assert replay.engine.snapshot() == c.engine.snapshot()
    with pytest.raises(ApiError, match="read only"):
        command(replay, "step")
    command(replay, "reset")
    assert not replay.read_only and replay.engine.tick == 0
    resumed.close()


def test_invalid_allocation_uploads_and_stale_plan_are_rejected():
    c = controller()
    with pytest.raises(ApiError):
        command(c, "preview", {"release_id": "sample-slow-v2", "per_rack": 3})
    with pytest.raises(ApiError):
        command(c, "register_release", {"filename": "x", "content_base64": "bad", "profile": "exec"})
    plan = command(c, "preview", {"release_id": "sample-slow-v2"})["result"]
    command(c, "fault", {"kind": "service_crash", "scope": "host", "target": "host-01-01"})
    command(c, "step")
    with pytest.raises(ApiError, match="stale"):
        command(c, "deploy", {"plan_id": plan["plan_id"]})
    assert c.outcomes[-1]["status"] == "rejected"


def test_persisted_receipts_remain_idempotent_after_restart(tmp_path):
    c = controller(tmp_path)
    payload = {"command_id": "unique", "run_id": c.run_id, "epoch": 0, "command": "step"}
    original = c.command(payload)
    c.close()
    b = controller(tmp_path)
    assert b.command(payload) == original
    assert b.engine.tick == 1 and len(b.outcomes) == 1
    b.close()


def test_invalid_saved_run_leaves_world_unchanged_and_records_rejection():
    c = controller()
    before = c.engine.artifact()
    with pytest.raises(ApiError):
        command(c, "load_run", {"run": {"log": []}})
    assert c.engine.artifact() == before
    assert c.outcomes[-1]["status"] == "rejected"


def test_developer_truth_api_is_separate_from_read_only_polling():
    c = controller()
    command(c, "fault", {"kind": "memory_pressure", "scope": "host", "target": "host-01-01"})
    command(c, "fault", {"kind": "service_crash", "scope": "host", "target": "host-02-01"})
    command(c, "step")
    server = make_server(c, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base+"/api/state") as r:
            state = json.load(r)
        with urlopen(base+"/api/fault-lab?developer=1") as r:
            truth = json.load(r)
        assert "memory_pressure" not in json.dumps(state)
        assert state["summary"]["ready"] == 19
        assert truth["developer_only"] and truth["injected_truth"][0]["kind"] == "memory_pressure"
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
