import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from canary_ssm.dashboard import ApiError, SPEEDS, WEB, WorldController, make_server, recorded_fixture
from canary_ssm.engine import SimulationEngine, load_engine_config

ROOT = Path(__file__).resolve().parents[1]


class FakeClock:
    value = 1000.0

    def __call__(self):
        return self.value


@pytest.fixture
def controller():
    clock = FakeClock()
    ctrl = WorldController(load_engine_config(ROOT / "configs/world_recovery.yaml"), monotonic=clock, wall_time=clock)
    ctrl.test_clock = clock
    yield ctrl
    ctrl.close()


def command(controller, action, cid=None, **extra):
    p = {"command_id": cid or f"test-{controller.revision}", "command": action,
         "run_id": controller.run_id, "epoch": controller.epoch, **extra}
    return controller.command(p)


def test_get_is_read_only_and_one_tick_step_has_backend_history(controller):
    initial = controller.engine.artifact()
    for _ in range(3):
        assert controller.packet()["snapshot"]["tick"] == 0
    assert controller.engine.artifact() == initial
    command(controller, "step")
    packet = controller.packet("host-02-03")
    assert packet["history"]["host_id"] == "host-02-03"
    assert len(packet["history"]["rows"]) == 1
    assert all(r["host_id"] == "host-02-03" for r in packet["history"]["rows"])
    assert packet["monitoring"] == "Monitoring not connected"
    assert packet["snapshot"]["state"] == "paused"


def test_start_pause_resume_and_playback_do_not_change_model_units(controller):
    command(controller, "speed", speed=4)
    command(controller, "start")
    assert not controller.advance_due(1000.24)
    assert controller.advance_due(1000.25)
    assert controller.packet()["snapshot"]["simulated_seconds"] == 1
    command(controller, "pause")
    frozen = controller.engine.artifact()
    assert not controller.advance_due(999999)
    assert controller.engine.artifact() == frozen
    command(controller, "step")
    command(controller, "resume")
    assert controller.advance_due(1000.25)
    assert controller.engine.tick == 3


def test_speed_changes_wall_deadline_but_not_deterministic_engine(controller):
    command(controller, "speed", speed=16)
    command(controller, "start")
    for i in range(1, 11):
        assert controller.advance_due(1000+i/16)
    expected = SimulationEngine(controller.engine.config)
    expected.start()
    expected.advance(10)
    assert controller.engine.snapshot() == expected.snapshot()
    assert controller.engine.artifact()["rng_states"] == expected.artifact()["rng_states"]


def test_reset_restores_world_rng_history_and_increments_epoch(controller):
    run = controller.run_id
    command(controller, "step")
    command(controller, "reset")
    assert controller.run_id == run and controller.epoch == 1
    assert controller.engine.tick == 0
    assert controller.packet()["history"]["rows"] == []
    assert controller.engine.snapshot() == SimulationEngine(controller.engine.config).snapshot()


def test_duplicate_commands_are_not_applied_twice_and_epoch_guard(controller):
    payload = {"command_id": "same", "command": "step", "run_id": controller.run_id, "epoch": 0}
    receipt = controller.command(payload)
    assert controller.command(payload) == receipt and controller.engine.tick == 1
    with pytest.raises(ApiError, match="different parameters"):
        controller.command({**payload, "command": "reset"})
    command(controller, "reset")
    assert controller.command(payload) == receipt and controller.engine.tick == 0
    with pytest.raises(ApiError, match="epoch changed"):
        controller.command({**payload, "command_id": "different"})


@pytest.mark.parametrize("payload", [None, [], {}, {"command_id": ""}, {"command_id": "a", "command": "start", "epoch": 0, "run_id": "wrong"}])
def test_invalid_commands_are_rejected_without_engine_mutation(controller, payload):
    before = controller.engine.artifact()
    with pytest.raises(ApiError):
        controller.command(payload)
    assert controller.engine.artifact() == before


@pytest.mark.parametrize("speed", [0, -1, True, "8", 3, float("nan"), float("inf")])
def test_invalid_speed_is_rejected(controller, speed):
    with pytest.raises(ApiError):
        command(controller, "speed", speed=speed)
    assert controller.speed == 1


def test_host_id_and_invalid_state_validation(controller):
    with pytest.raises(ApiError, match="Unknown host_id"):
        controller.packet("absent")
    with pytest.raises(ApiError, match="pause requires"):
        command(controller, "pause")
    with pytest.raises(ApiError, match="only valid"):
        command(controller, "start", speed=1)


def test_one_scheduler_and_fault_visibility(controller):
    happened = threading.Event()
    def fail(*args):
        happened.set()
        raise RuntimeError("test clock fault")
    controller.engine.advance = fail
    command(controller, "speed", speed=16)
    command(controller, "start")
    controller.test_clock.value = 1001
    controller.start_scheduler()
    thread = controller._thread
    controller.start_scheduler()
    assert controller._thread is thread
    assert happened.wait(timeout=1)
    packet = controller.packet()
    assert "test clock fault" in packet["driver_error"]
    assert packet["snapshot"]["state"] == "paused"
    command(controller, "reset")
    assert controller.driver_error is None


@pytest.fixture
def http_server(controller):
    server = make_server(controller, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(url, payload=None, headers=None):
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                  headers=headers or {})
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def test_http_controls_origin_and_static_assets(controller, http_server):
    _, base = http_server
    status, headers, body = request(base + "/api/state")
    state = json.loads(body)
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert state["run_id"] == controller.run_id
    p = {"command_id": "http-step", "command": "step", "run_id": state["run_id"], "epoch": state["epoch"]}
    assert request(base + "/api/commands", p, {"Content-Type": "application/json"})[0] == 403
    valid = {"Content-Type": "application/json", "X-World-Token": state["command_token"]}
    assert request(base + "/api/commands", p, {**valid, "Origin": "https://other.example"})[0] == 403
    assert request(base + "/api/commands", p, valid)[0] == 200
    assert request(base + "/api/commands", p, valid)[0] == 200
    assert controller.engine.tick == 1
    for path in ("/", "/app.js", "/styles.css", "/recorded_snapshot.json"):
        assert request(base + path)[0] == 200
    assert request(base + "/../../AGENTS.md")[0] == 404
    assert request(base + "/api/state", headers={"Host": "other.example"})[0] == 403


def test_http_invalid_payload_and_missing_host(controller, http_server):
    _, base = http_server
    token = controller.command_token
    headers = {"Content-Type": "application/json", "X-World-Token": token}
    assert request(base + "/api/commands", {"large": "x"*9000}, headers)[0] == 400
    assert request(base + "/api/commands", {}, headers)[0] == 400
    assert request(base + "/api/commands", {}, {**headers, "Content-Type": "text/plain"})[0] == 415
    assert request(base + "/api/state?host_id=absent")[0] == 404


def test_recorded_fixture_is_engine_independent_read_only_data():
    saved = json.loads((WEB / "recorded_snapshot.json").read_text())
    expected = recorded_fixture(load_engine_config(ROOT / "configs/world_recovery.yaml"), 50)
    assert saved == expected
    assert saved["mode"] == "recorded" and saved["command_token"] is None
    assert saved["snapshot"]["tick"] == 50
    assert len(saved["recorded_history"]) == 20
    for host, rows in saved["recorded_history"].items():
        assert all(r["host_id"] == host for r in rows)
