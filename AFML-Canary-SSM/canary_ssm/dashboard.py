"""Local dashboard adapter: one backend-owned engine, validated commands and polling."""
from __future__ import annotations

import copy
import hmac
import hashlib
import json
import math
import secrets
import threading
import time
import uuid
from dataclasses import replace
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .engine import EngineState, SimulationEngine, load_engine_config
from .monitor_feed import DetectorFeed
from .dashboard_evidence import RunArchive, console_evidence, preview_rollout

SPEEDS = (0.25, 0.5, 1, 2, 4, 8, 16)
WEB = Path(__file__).with_name("web")


class ApiError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class WorldController:
    def __init__(self, config, *, monotonic=time.monotonic, wall_time=time.time, run_id=None, state_dir=None):
        if config.resources is not None:
            config = replace(config, demo=True)
        self.run_id = run_id or uuid.uuid4().hex
        self.engine = SimulationEngine(config,run_id=self.run_id)
        self.command_token = secrets.token_urlsafe(32)
        self.detector_feed = DetectorFeed(self.engine.world.snapshot()["hosts"], monotonic)
        self.epoch, self.revision, self.speed = 0, 0, 1.0
        self._monotonic, self._wall_time = monotonic, wall_time
        self._condition = threading.Condition(threading.RLock())
        self._closed, self._thread, self._next_tick = False, None, None
        self._receipts = OrderedDict()
        self.command_journal = {}
        self.last_update = wall_time()
        self.driver_error = None
        self.read_only = False
        self.replay_source_run_id = None
        self.outcomes = []
        self.outcome_sequence = 0
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self.archive = RunArchive(self.state_dir)
        self._last_checkpoint = float("-inf")
        if self.state_dir and (self.state_dir / "session.json").exists():
            saved = json.loads((self.state_dir / "session.json").read_text())
            self.engine = SimulationEngine.replay(saved["engine"])
            self.run_id = self.engine.run_id
            self.epoch, self.revision, self.speed = saved["epoch"], saved["revision"], saved["speed"]
            self.outcomes = saved.get("outcomes", [])[-500:]
            self.outcome_sequence = saved.get("outcome_sequence", len(self.outcomes))
            self._receipts = OrderedDict((key, tuple(value)) for key, value in saved.get("receipts", [])[-256:])
            self.command_journal = copy.deepcopy(saved.get('command_journal',{}))
            self.read_only = saved.get("read_only", False)
            self.replay_source_run_id = saved.get("replay_source_run_id")
            if self.engine.state == EngineState.RUNNING:
                self.engine.pause()
            if saved.get("detector_feed"):
                attachment=saved['detector_feed']
                self.detector_feed.command('monitor_load',{'artifact':attachment['artifact']})
                self.detector_feed.command('monitor_seek',{'index':attachment['cursor']})
            self._touch()

    def export_run(self):
        with self._condition:
            return {"format": "world-console-session-v1", "run_id": self.run_id,
                    "epoch": self.epoch, "revision": self.revision, "speed": self.speed,
                    "read_only": self.read_only, "replay_source_run_id": self.replay_source_run_id,
                    "engine": self.engine.artifact(), "outcomes": copy.deepcopy(self.outcomes),
                    "outcome_sequence": self.outcome_sequence, "receipts": list(self._receipts.items()),
                    "command_journal": copy.deepcopy(self.command_journal),
                    "detector_feed": {"artifact":copy.deepcopy(self.detector_feed.artifact),"cursor":self.detector_feed.cursor} if self.detector_feed.artifact and self.detector_feed.cursor>=0 else None}

    def _checkpoint(self, force=False):
        if self.state_dir is None or (not force and self._monotonic()-self._last_checkpoint < 0.75):
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_dir / "session.tmp"
        temporary.write_text(json.dumps(self.export_run(), allow_nan=False), encoding="utf-8")
        temporary.replace(self.state_dir / "session.json")
        self._last_checkpoint = self._monotonic()

    def _touch(self):
        self.revision += 1
        self.last_update = self._wall_time()

    def _delay(self):
        return self.engine.config.tick_seconds / self.speed

    def advance_due(self, now=None):
        """At most one whole model tick per due wall-clock deadline; no catch-up burst."""
        with self._condition:
            now = self._monotonic() if now is None else now
            if self.engine.state != EngineState.RUNNING or self._next_tick is None or now < self._next_tick:
                return False
            self.engine.advance(1)
            self._next_tick = now + self._delay()
            self._touch()
            self._checkpoint()
            return True

    def start_scheduler(self):
        with self._condition:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._drive, name="world-clock", daemon=True)
            self._thread.start()

    def _drive(self):
        while True:
            with self._condition:
                if self._closed:
                    return
                self.detector_feed.advance()
                if self.engine.state != EngineState.RUNNING:
                    self._condition.wait(timeout=0.1)
                    continue
                wait = max(0.0, self._next_tick - self._monotonic())
                if wait:
                    self._condition.wait(timeout=min(wait,0.1))
                    continue
                try:
                    self.advance_due()
                except Exception as exc:
                    # Keep the last backend state visible and allow an explicit reset.
                    self.driver_error = f"{type(exc).__name__}: {exc}"
                    if self.engine.state == EngineState.RUNNING:
                        self.engine.pause()
                    self._next_tick = None
                    self._touch()

    def close(self):
        with self._condition:
            self._checkpoint(force=True)
            self._closed = True
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def command(self, payload):
        with self._condition:
            cached = isinstance(payload, dict) and isinstance(payload.get("command_id"), str) and (payload["command_id"] in self._receipts or payload["command_id"] in self.command_journal)
            try:
                result = self._apply_command(payload)
            except ApiError as exc:
                cid=payload.get('command_id') if isinstance(payload,dict) else None
                if isinstance(cid,str) and 1<=len(cid)<=128 and cid not in self.command_journal and len(self.command_journal)<10000:
                    self.command_journal[cid]={'fingerprint':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
                        'status':'rejected','command':payload.get('command'),'command_id':cid,'error':str(exc),'http_status':exc.status,
                        'run_id':self.run_id,'epoch':self.epoch,'tick':self.engine.tick}
                self.outcome_sequence += 1
                self.outcomes.append({"seq": self.outcome_sequence,
                    "command_id": payload.get("command_id") if isinstance(payload, dict) else None,
                    "command": payload.get("command") if isinstance(payload, dict) else "invalid",
                    "status": "rejected", "error": str(exc), "tick": self.engine.tick,
                    "epoch": self.epoch, "wall_time_ms": round(self._wall_time()*1000)})
                self.outcomes = self.outcomes[-500:]
                self._touch()
                self._checkpoint(force=True)
                raise
            if not cached:
                self.outcome_sequence += 1
                self.outcomes.append({"seq": self.outcome_sequence, "command_id": result["command_id"],
                    "command": result["command"], "status": "applied", "tick": self.engine.tick,
                    "epoch": self.epoch, "wall_time_ms": round(self._wall_time()*1000)})
                self.outcomes = self.outcomes[-500:]
                self._checkpoint(force=True)
            return result

    def _apply_command(self, payload):
        with self._condition:
            if not isinstance(payload, dict):
                raise ApiError("Command must be a JSON object")
            required = {"command_id", "run_id", "epoch", "command"}
            if not required <= payload.keys() or payload.keys() - (required | {"speed", "args"}):
                raise ApiError("Invalid command fields")
            cid = payload["command_id"]
            if not isinstance(cid, str) or not 1 <= len(cid) <= 128 or not cid.strip():
                raise ApiError("command_id must be a nonempty string of at most 128 characters")
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if cid in self._receipts:
                previous, receipt = self._receipts[cid]
                if previous != fingerprint:
                    raise ApiError("command_id was already used with different parameters", 409)
                return copy.deepcopy(receipt)
            if cid in self.command_journal:
                entry=self.command_journal[cid]
                if entry['fingerprint']!=fingerprint:raise ApiError('command_id was already used with different parameters',409)
                if entry['status']=='rejected':raise ApiError(entry['error'],entry['http_status'])
                return {**copy.deepcopy(entry['receipt']),'result_not_cached':True}
            if len(self.command_journal)>=10000:
                raise ApiError('Command journal reached 10000 identities; export/checkpoint this run and start a fresh backend state directory',409)
            if payload["run_id"] != self.run_id or type(payload["epoch"]) is not int or payload["epoch"] != self.epoch:
                raise ApiError("Run or reset epoch changed; refresh before sending a command", 409)
            command = payload["command"]
            monitoring=("monitor_load","monitor_play","monitor_pause","monitor_seek","monitor_speed","monitor_begin","monitor_append")
            operations = ("policy_attach", "policy_observe", "policy_advisory", "restart_process", "rollout_create", "rollout_baseline", "rollout_expose", "rollout_pause", "rollout_resume", "rollout_promote", "rollout_rollback", "rollout_fail", "register_release", "preview", "deploy", "rollback", "fault", "random_faults", "background_set_enabled")
            if command not in ("start", "pause", "resume", "step", "reset", "speed", "load_run", "rollout_preview", "history_save", "history_load") + operations + monitoring:
                raise ApiError("Unknown world command")
            if self.read_only and command not in ("reset", "load_run", "history_save", "history_load") + monitoring:
                raise ApiError("Saved-run replay is read only; reset to return to a live world", 409)
            if self.driver_error and command != "reset" and command not in monitoring:
                raise ApiError("Clock driver failed; reset the run to recover", 409)
            result = None
            if command in ('rollout_preview','history_save'):
                if 'speed' in payload:
                    raise ApiError('speed is only valid for clock playback')
                args=payload.get('args',{})
                try:
                    if command=='rollout_preview':
                        result=preview_rollout(self.engine,args)
                    else:
                        if args!={}:raise ValueError('history_save accepts no arguments')
                        result=self.archive.save(self.export_run())
                except (ValueError,TypeError,KeyError,OSError) as exc:
                    raise ApiError(str(exc),400) from exc
            elif command in monitoring:
                if "speed" in payload:raise ApiError("Use detector command args for playback")
                try:
                    args=payload.get('args',{})
                    if command=='monitor_append' and self.detector_feed.artifact and self.detector_feed.artifact['run_id']==self.run_id:
                        if args['frame']['decision_time']>self.engine.tick*self.engine.config.tick_seconds:raise ValueError('Current-world detector frames cannot be from the future')
                    metadata=args.get('metadata') if command=='monitor_begin' else self.detector_feed.artifact
                    if command in ('monitor_begin','monitor_append') and metadata and metadata.get('run_id')==self.run_id:
                        rollout=self.engine.rollouts.binding_for([h['host_id'] for h in metadata['host_roster']])
                        if self.engine.rollouts.records() and rollout is None:raise ValueError('Current-world detector roster must match a fixed canary cohort')
                        if rollout:
                            if not rollout['evaluation_active'] or rollout['exposure_tick'] is None:raise ValueError('Rollout evaluation is not active; no pre-exposure or closed-epoch outputs')
                            if metadata['exposure_time']!=rollout['first_decision_time']:raise ValueError('Detector exposure must be the first complete exposed monitoring window')
                            if command=='monitor_append':
                                frame=args['frame'];end=(rollout['evaluation_end_tick']-1)*self.engine.config.tick_seconds
                                if frame['decision_time']<rollout['first_decision_time'] or frame['event_time']<rollout['first_decision_time'] or frame['decision_time']>end:raise ValueError('Detector frame is outside the fixed monitoring horizon')
                                if getattr(self,'_rollout_feed_epoch',None)!=rollout['monitoring_epoch']:raise ValueError('Begin a new detector stream for this monitoring epoch')
                    result=self.detector_feed.command(command,args)
                    if command=='monitor_begin' and metadata and metadata.get('run_id')==self.run_id:
                        self._rollout_feed_epoch=rollout['monitoring_epoch'] if rollout else None
                except (ValueError,TypeError,KeyError) as exc:raise ApiError(str(exc)) from exc
            elif command in operations:
                if "speed" in payload:
                    raise ApiError("speed is only valid for the speed command")
                try:
                    result = self.engine.operations_command(command, payload.get("args", {}))
                    if command=='rollout_create' and self.detector_feed.artifact and self.detector_feed.artifact['run_id']==self.run_id:
                        self.detector_feed=DetectorFeed(self.engine.world.snapshot()['hosts'],self._monotonic)
                        self._rollout_feed_epoch=None
                except (ValueError, TypeError, KeyError) as exc:
                    raise ApiError(str(exc), 400) from exc
            elif command in ("load_run", "history_load"):
                if self.engine.state == EngineState.RUNNING:
                    raise ApiError("Pause before loading a saved run", 409)
                args = payload.get("args", {})
                expected={'run'} if command=='load_run' else {'checkpoint_id'}
                if not isinstance(args, dict) or set(args) != expected or "speed" in payload:
                    raise ApiError(command+" requires only "+','.join(expected))
                try:
                    saved = args['run'] if command=='load_run' else self.archive.get(args['checkpoint_id'])
                except (ValueError,OSError) as exc:
                    raise ApiError(str(exc),404) from exc
                try:
                    # Preserve large RNG integers and float spelling across browser uploads.
                    if isinstance(saved,str):
                        if len(saved.encode('utf-8'))>32*1024*1024:raise ValueError('Saved run exceeds 32 MiB')
                        saved=json.loads(saved)
                    if not isinstance(saved, dict):
                        raise ValueError("Saved run must be an object")
                    artifact = saved.get("engine", saved)
                    log = artifact.get("log")
                    if not isinstance(log, list) or len(log) > 20000 or not all(isinstance(e, dict) for e in log):
                        raise ValueError("Saved run needs a bounded command log")
                    steps = [e.get("ticks") for e in log if e.get("kind") == "command" and e.get("command") in ("step", "advance")]
                    if any(type(n) is not int or n < 1 for n in steps) or sum(steps) > 10000:
                        raise ValueError("Replay is limited to 10000 simulated ticks")
                    outcomes = saved.get("outcomes", [])
                    if not isinstance(outcomes, list) or len(outcomes) > 500 or not all(isinstance(o, dict) and type(o.get("seq")) is int for o in outcomes):
                        raise ValueError("Invalid saved command outcomes")
                    candidate = SimulationEngine.replay(artifact)
                    feed=DetectorFeed(candidate.world.snapshot()['hosts'],self._monotonic)
                    if saved.get('detector_feed'):
                        attachment=saved['detector_feed']
                        feed.command('monitor_load',{'artifact':attachment['artifact']})
                        feed.command('monitor_seek',{'index':attachment['cursor']})
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    raise ApiError(f"Cannot replay saved run: {exc}") from exc
                if candidate.state == EngineState.RUNNING:
                    candidate.pause()
                try:self.archive.save(self.export_run())
                except (ValueError,OSError) as exc:raise ApiError('Could not preserve current run: '+str(exc),409) from exc
                self.engine = candidate
                self.run_id = candidate.run_id
                self.detector_feed = feed
                self.read_only = True
                self.epoch += 1
                self.replay_source_run_id = candidate.run_id
                self.outcomes = copy.deepcopy(saved.get("outcomes", []))[-499:]
                self.outcome_sequence = max([self.outcome_sequence] + [o.get("seq", 0) for o in self.outcomes])
                result = {"status": "verified_read_only_replay", "tick": candidate.tick}
            elif command == "speed":
                if "args" in payload:
                    raise ApiError("args are not valid for the speed command")
                speed = payload.get("speed")
                if type(speed) not in (int, float) or not math.isfinite(speed) or speed not in SPEEDS:
                    raise ApiError("speed must be one of 0.25, 0.5, 1, 2, 4, 8, 16")
                self.speed = float(speed)
            else:
                if "args" in payload:
                    raise ApiError("args are not valid for clock controls")
                if "speed" in payload:
                    raise ApiError("speed is only valid for the speed command")
                try:
                    if command=='reset':self.archive.save(self.export_run())
                    getattr(self.engine, command)()
                except (ValueError,OSError) as exc:
                    raise ApiError(str(exc), 409) from exc
                if command == "reset":
                    self.epoch += 1
                    self.driver_error = None
                    self.read_only = False
                    self.replay_source_run_id = None
                    self.detector_feed=DetectorFeed(self.engine.world.snapshot()['hosts'],self._monotonic)
            if command not in monitoring:
                self._next_tick = self._monotonic() + self._delay() if self.engine.state == EngineState.RUNNING else None
            self._touch()
            receipt = {"command_id": cid, "command": command, "status": "applied",
                       "run_id": self.run_id, "epoch": self.epoch, "tick": self.engine.tick,
                       "revision": self.revision}
            if result is not None:
                receipt["result"] = result
            self._receipts[cid] = (fingerprint, receipt)
            self.command_journal[cid]={'fingerprint':fingerprint,'status':'applied','command_id':cid,
                'receipt':{k:copy.deepcopy(v) for k,v in receipt.items() if k!='result'}}
            while len(self._receipts) > 256:
                self._receipts.popitem(last=False)
            self._condition.notify_all()
            return copy.deepcopy(receipt)

    def packet(self, host_id=None):
        with self._condition:
            snapshot = self.engine.snapshot()
            hosts = snapshot["world"]["hosts"]
            host_id = host_id or (hosts[0]["host_id"] if hosts else None)
            if host_id is not None and host_id not in {h["host_id"] for h in hosts}:
                raise ApiError("Unknown host_id", 404)
            model = self.engine.resource_model
            history = [copy.deepcopy(r) for r in model.host_trace if r["host_id"] == host_id][-120:] if model else []
            availability = {r["host_id"]: r["available"] for r in model.last_hosts} if model else {}
            linked = self.detector_feed.mode=='stream' and self.detector_feed.artifact is not None and self.detector_feed.artifact['run_id']==self.run_id
            console=console_evidence(self.engine,self.outcomes)
            if linked and console['context']['policy_id'] is None:
                console['context']['model_id']='UNCALIBRATED STREAM · '+', '.join(m['method_id']+':'+m['version'] for m in self.detector_feed.artifact['methods'])
            policy_status=None
            if self.engine.demo:
                for rid,b in self.engine.policy_controller.bindings.items():
                    if b['active'] and b['runtime']:
                        row=self.engine.rollouts._records[rid]
                        policy_status='Saved calibrated policy replay' if self.read_only else 'Closed calibrated policy evaluation' if not row['evaluation_active'] else 'Stale calibrated policy input' if self.engine.tick*self.engine.config.tick_seconds-b['runtime'].last_decision>120 else 'Calibrated policy input'

            return {"schema_version": 1, "mode": "replay" if self.read_only else "live", "run_id": self.run_id,
                    "epoch": self.epoch, "revision": self.revision, "speed": self.speed,
                    "tick_seconds": self.engine.config.tick_seconds,
                    "console": console,
                    "server_time_unix_ms": round(self._wall_time() * 1000),
                    "last_update_unix_ms": round(self.last_update * 1000),
                    "driver_error": self.driver_error, "command_token": self.command_token,
                    "monitoring": policy_status or ("Uncalibrated output stream" if linked else "Monitoring not connected"), "snapshot": snapshot,
                    "detector_status": policy_status.upper() if policy_status else "UNCALIBRATED DETECTOR STREAM" if linked else "DETECTOR NOT CONNECTED", "simulated": True,
                    "read_only": self.read_only, "console_available": self.engine.demo is not None,
                    "replay_source_run_id": self.replay_source_run_id,
                    "outcomes": copy.deepcopy(self.outcomes[-30:]),
                    "history": {"host_id": host_id, "rows": history},
                    "summary": {"hosts": len(hosts), "ready": sum(h["lifecycle"] == "ready" and availability.get(h["host_id"], True) for h in hosts),
                                "racks": len(snapshot["world"]["racks"]), "data_centers": len(snapshot["world"]["data_centers"])}}


def recorded_fixture(config, ticks=50):
    """Save genuine backend outputs for a static HTTP server, with controls disabled."""
    controller = WorldController(config, run_id="recorded-world-50")
    controller.engine.step(ticks)
    packet = controller.packet()
    packet.update(mode="recorded", command_token=None, server_time_unix_ms=None, last_update_unix_ms=None)
    packet["recorded_history"] = {h.host_id: controller.packet(h.host_id)["history"]["rows"] for h in controller.engine.world.hosts}
    packet["recording"] = {"synthetic": True, "source": "world_recovery.yaml", "tick": ticks,
                           "engine_manifest": controller.engine.artifact()["manifest"]}
    return packet


def make_server(controller, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _host_ok(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def _send(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "Invalid local host"})
            parsed = urlsplit(self.path)
            if parsed.path == "/api/state":
                try:
                    host = parse_qs(parsed.query).get("host_id", [None])[0]
                    return self._send(200, controller.packet(host))
                except ApiError as exc:
                    return self._send(exc.status, {"error": str(exc)})
            if parsed.path == "/api/commands":
                identity=parse_qs(parsed.query).get('command_id',[None])[0]
                if not isinstance(identity,str) or not 1<=len(identity)<=128:
                    return self._send(400,{'error':'Provide a bounded command_id'})
                with controller._condition:
                    cached=controller._receipts.get(identity)
                    outcome=next((x for x in reversed(controller.outcomes) if x['command_id']==identity),None)
                    entry=controller.command_journal.get(identity)
                    receipt=copy.deepcopy(cached[1]) if cached else copy.deepcopy(entry['receipt']) if entry and entry['status']=='applied' else None
                    return self._send(200,{'known':cached is not None or outcome is not None or entry is not None,'receipt':receipt,'outcome':copy.deepcopy(outcome or entry)})
            if parsed.path == "/api/detectors":
                with controller._condition:
                    try:return self._send(200,controller.detector_feed.snapshot(parse_qs(parsed.query).get('host_id',[None])[0]))
                    except ValueError as exc:return self._send(404,{'error':str(exc)})
            if parsed.path == "/api/detectors/evaluator":
                if parse_qs(parsed.query).get('developer') != ['1']:return self._send(403,{'error':'Evaluator view required'})
                from .monitor_evaluator import recipe_for
                with controller._condition:
                    artifact=controller.detector_feed.artifact
                    recipe=recipe_for(artifact['artifact_id']) if artifact else None
                    return self._send(200,recipe) if recipe else self._send(404,{'error':'No authored demo recipe'})
            if parsed.path == "/api/detectors/export":
                with controller._condition:
                    if controller.detector_feed.artifact is None:return self._send(404,{'error':'No detector feed loaded'})
                    return self._send(200,controller.detector_feed.artifact)
            if parsed.path == "/api/releases":
                with controller._condition:
                    return self._send(200, {"releases": controller.engine.demo.catalog() if controller.engine.demo else []})
            if parsed.path == "/api/telemetry":
                with controller._condition:
                    pipeline = controller.engine.telemetry
                    if pipeline is None:
                        return self._send(200,{"enabled":False,"detector_status":"DETECTOR NOT CONNECTED"})
                    query = parse_qs(parsed.query)
                    if "decision_time" in query:
                        try:
                            timestamp = float(query["decision_time"][0])
                            if timestamp not in pipeline.store.decisions:
                                raise ValueError("Only committed decision timestamps may be queried")
                            return self._send(200,pipeline.store.time_slice(timestamp))
                        except ValueError as exc:
                            return self._send(400,{"error":str(exc)})
                    public = pipeline.public_artifact()
                    public["records"] = public["records"][-500:]
                    public["windows"] = public["windows"][-2000:]
                    public.update(enabled=True,summary=pipeline.summary(),detector_status="DETECTOR NOT CONNECTED",
                                  page_limits={"records":500,"windows":2000})
                    return self._send(200,public)
            if parsed.path == "/api/fault-lab":
                if parse_qs(parsed.query).get("developer") != ["1"]:
                    return self._send(403, {"error": "Developer Fault Lab view required"})
                with controller._condition:
                    demo = controller.engine.demo
                    return self._send(200, {"developer_only": True, "injected_truth": demo.developer_truth() if demo else [],
                                           "background": demo.background.preview(controller.engine.tick) if demo else None})
            if parsed.path == "/api/run":
                return self._send(200, controller.export_run())
            if parsed.path == "/api/history":
                with controller._condition:
                    try:
                        identity=parse_qs(parsed.query).get('checkpoint_id',[None])[0]
                        return self._send(200,controller.archive.get(identity) if identity else {'checkpoints':controller.archive.list(),'persistent':controller.state_dir is not None})
                    except (ValueError,OSError) as exc:
                        return self._send(404,{'error':str(exc)})
            files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                     "/console.js": ("console.js", "text/javascript"),
                     "/styles.css": ("styles.css", "text/css"), "/detectors.js":("detectors.js","text/javascript"),
                     "/recorded_snapshot.json": ("recorded_snapshot.json", "application/json")}
            if parsed.path not in files:
                return self._send(404, {"error": "Not found"})
            file, mime = files[parsed.path]
            try:
                return self._send(200, (WEB / file).read_bytes(), mime + "; charset=utf-8")
            except OSError:
                return self._send(404, {"error": "Dashboard asset not found"})

        def do_POST(self):
            if urlsplit(self.path).path != "/api/commands":
                return self._send(404, {"error": "Not found"})
            origin = self.headers.get("Origin")
            token = self.headers.get("X-World-Token", "")
            if not self._host_ok() or (origin and origin != "http://" + self.headers.get("Host", "")) or not hmac.compare_digest(token, controller.command_token):
                return self._send(403, {"error": "Invalid local command origin or token"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._send(415, {"error": "Expected application/json"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 32*1024*1024 if length > 8192 else 8192
                # Small commands retain their bound; uploads/replay have explicit operation bounds.
                if not 0 < length <= maximum:
                    raise ApiError("Command body exceeds 32 MiB")
                raw = self.rfile.read(length)
                payload = json.loads(raw)
                if length > 8192 and (not isinstance(payload, dict) or payload.get("command") not in ("policy_attach", "register_release", "load_run", "monitor_load", "monitor_append")):
                    raise ApiError("Only artifact uploads and saved runs may exceed 8192 bytes")
                receipt = controller.command(payload)
                return self._send(200, {"receipt": receipt})
            except ApiError as exc:
                return self._send(exc.status, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                return self._send(400, {"error": f"Invalid command JSON: {exc}"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve_dashboard(config_path, port=8765, state_dir="runtime/world_dashboard"):
    controller = WorldController(load_engine_config(config_path), state_dir=state_dir)
    server = make_server(controller, port)
    controller.start_scheduler()
    print(f"World dashboard: http://127.0.0.1:{server.server_port}  run_id={controller.run_id}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        controller.close()
        server.server_close()
