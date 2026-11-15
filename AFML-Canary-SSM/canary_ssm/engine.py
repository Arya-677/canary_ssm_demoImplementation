"""Deterministic world clock with static or bounded-resource phases and verified replay."""
from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

import numpy as np

from .configuration import read_yaml_mapping
from .seeds import seed_for
from .topology import HostLifecycle, Topology
from .resources import ResourceConfig, ResourceModel
from .fault_scheduler import BackgroundFaultConfig
from .telemetry_transport import TelemetryConfig, TelemetryPipeline

RNG_STREAMS = ("workload", "faults", "host_noise", "telemetry_loss")
PHASES = ("apply_events", "route_workload", "update_resources", "emit_observations", "publish_snapshot")
ENGINE_ID = "clock-static-v1"


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ScheduledEvent:
    event_id: str
    at_tick: int
    action: str = "marker"
    host_id: str | None = None
    lifecycle: str | None = None

    def __post_init__(self):
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a nonempty string")
        _integer(self.at_tick, "at_tick", 1)
        if self.action == "set_host_lifecycle":
            if not isinstance(self.host_id, str) or not self.host_id:
                raise ValueError("set_host_lifecycle requires host_id")
            try:
                HostLifecycle(self.lifecycle)
            except (ValueError, TypeError) as exc:
                raise ValueError("invalid event lifecycle") from exc
        elif self.action != "marker" or self.host_id is not None or self.lifecycle is not None:
            raise ValueError("event action must be marker or set_host_lifecycle with valid fields")

    def to_dict(self):
        return dict(event_id=self.event_id, at_tick=self.at_tick, action=self.action,
                    host_id=self.host_id, lifecycle=self.lifecycle)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("event must be a mapping")
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError(f"invalid event fields: {exc}") from exc


@dataclass(frozen=True)
class EngineConfig:
    topology: Topology
    seed: int = seed_for("smoke", 0)
    tick_seconds: int = 1
    events: tuple[ScheduledEvent, ...] = ()
    resources: ResourceConfig | None = None
    demo: bool = False
    background_faults: BackgroundFaultConfig | None = None
    telemetry: TelemetryConfig | None = None

    def __post_init__(self):
        if not isinstance(self.topology, Topology):
            raise ValueError("topology must be a validated Topology")
        _integer(self.seed, "seed")
        _integer(self.tick_seconds, "tick_seconds", 1)
        if type(self.demo) is not bool or (self.demo and self.resources is None):
            raise ValueError("demo must be boolean and requires resource configuration")
        if self.background_faults is not None and (not isinstance(self.background_faults, BackgroundFaultConfig) or not self.demo):
            raise ValueError("background_faults requires a validated config and demo resource mode")
        if self.telemetry is not None:
            if not isinstance(self.telemetry, TelemetryConfig) or self.resources is None:
                raise ValueError("telemetry requires resource configuration")
            if self.telemetry.enabled and (self.tick_seconds>60 or 60%self.tick_seconds or self.telemetry.decision_delay_seconds%self.tick_seconds):
                raise ValueError("Enabled telemetry requires ticks dividing 60 and aligned decision grace")
        if self.resources is not None:
            if not isinstance(self.resources, ResourceConfig):
                raise ValueError("resources must be ResourceConfig")
            ResourceModel(self.resources, self.topology, self.tick_seconds)
        if not isinstance(self.events, (tuple, list)):
            raise ValueError("events must be a sequence")
        object.__setattr__(self, "events", tuple(self.events))
        ids = set()
        hosts = {h.host_id for h in self.topology.hosts}
        for event in self.events:
            if not isinstance(event, ScheduledEvent):
                raise ValueError("events must contain ScheduledEvent records")
            if event.event_id in ids:
                raise ValueError(f"duplicate event_id: {event.event_id}")
            ids.add(event.event_id)
            if event.action == "set_host_lifecycle" and event.host_id not in hosts:
                raise ValueError(f"unknown event host_id: {event.host_id}")

    def to_dict(self):
        value = {"topology": self.topology.snapshot(), "seed": self.seed,
                 "tick_seconds": self.tick_seconds, "events": [e.to_dict() for e in self.events]}
        if self.resources is not None:
            value["resources"] = self.resources.to_dict()
        if self.demo:
            value["demo"] = True
        if self.background_faults is not None:
            value["background_faults"] = self.background_faults.to_dict()
        if self.telemetry is not None:
            value["telemetry"] = self.telemetry.to_dict()
        return value

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {"topology", "seed", "tick_seconds", "events", "resources", "demo", "background_faults", "telemetry"}:
            raise ValueError("invalid engine configuration keys")
        if "topology" not in value or not isinstance(value.get("events", []), list):
            raise ValueError("engine requires topology and an events list")
        return cls(Topology.from_dict(value["topology"]), value.get("seed", seed_for("smoke", 0)),
                   value.get("tick_seconds", 1),
                   tuple(ScheduledEvent.from_dict(e) for e in value.get("events", [])),
                   ResourceConfig.from_dict(value["resources"]) if "resources" in value else None,
                   value.get("demo", False),
                   BackgroundFaultConfig.from_dict(value["background_faults"]) if "background_faults" in value else None,
                   TelemetryConfig.from_dict(value["telemetry"]) if "telemetry" in value else None)


def load_engine_config(path):
    """Reuse the project's YAML reader; resolve topology_file relative to this config."""
    path = Path(path)
    value = read_yaml_mapping(path)
    if set(value) - {"engine", "topology", "topology_file"}:
        raise ValueError("world config permits only engine, topology or topology_file")
    if ("topology" in value) == ("topology_file" in value):
        raise ValueError("provide exactly one of topology or topology_file")
    if "topology_file" in value:
        from .topology import load_topology
        if not isinstance(value["topology_file"], str):
            raise ValueError("topology_file must be a path string")
        topology = load_topology(path.parent / value["topology_file"]).snapshot()
    else:
        topology = value["topology"]
    engine = value.get("engine", {})
    if not isinstance(engine, dict) or "topology" in engine:
        raise ValueError("engine must be a mapping without nested topology")
    return EngineConfig.from_dict({**engine, "topology": topology})


class EngineState(str, Enum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"


class SimulationEngine:
    """Single-threaded, explicit clock. Wall time never advances this engine.

    route_workload/update_resources/emit_observations dispatch to configured
    resource phases, or static adapters when resources are absent. Overrides must be
    deterministic and consume only their named RNG streams; no external state.
    """

    def __init__(self, config: EngineConfig, *, run_id=None):
        self.config = config
        self.run_id = run_id or "world-"+_digest(config.to_dict())[:16]
        from .telemetry import identifier
        identifier(self.run_id, "run_id")
        self.telemetry_epoch = 0
        self._log = []
        self._initialize()

    def _initialize(self):
        self.world = self.config.topology
        self.tick = 0
        self.state = EngineState.READY
        # Explicit PCG64 and fixed stream indices avoid coupling stream consumption.
        self.rngs = {name: np.random.Generator(np.random.PCG64(np.random.SeedSequence(
            [self.config.seed, index]))) for index, name in enumerate(RNG_STREAMS)}
        if self.config.resources and self.config.resources.paired_exogenous:
            self.rngs["routing"] = np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.config.seed,4])))
        self._queue = list(enumerate(self.config.events))
        self._next_order = len(self._queue)
        self._event_ids = {e.event_id for e in self.config.events}
        self._workload = {}
        self._observations = []
        self.resource_model = ResourceModel(self.config.resources, self.world, self.config.tick_seconds,release_seed=self.config.seed) if self.config.resources else None
        if self.resource_model:
            self.world = self.resource_model.initial_world(self.world)
        self.demo = None
        if self.config.demo:
            from .operations import DemoOperations
            self.demo = DemoOperations(self)
            from .rollouts import RolloutManager
            if not hasattr(self, 'rollouts'): self.rollouts = RolloutManager(self)
            from .policy_control import PolicyController
            if not hasattr(self,'policy_controller'): self.policy_controller=PolicyController(self)
        self.telemetry = None
        self.telemetry_evaluator = None
        if self.config.telemetry and self.config.telemetry.enabled:
            from .telemetry_evaluator import TelemetryEvaluator
            self.telemetry = TelemetryPipeline(self.config.telemetry,self.world,self.config.tick_seconds,self.run_id,self.telemetry_epoch)
            self.telemetry_evaluator = TelemetryEvaluator()

    def operations_command(self, action, args):
        if self.demo is None:
            raise ValueError("Release/fault console requires demo resource configuration")
        result = self.demo.command(action, args)
        self._record("command", command="demo", action=action, args=copy.deepcopy(args))
        return result

    @property
    def log(self):
        return copy.deepcopy(self._log)

    def _record(self, kind, **payload):
        self._log.append({"seq": len(self._log), "tick": self.tick, "kind": kind, **payload})

    def start(self):
        if self.state != EngineState.READY:
            raise ValueError("start requires ready state")
        self._record("command", command="start")
        self.state = EngineState.RUNNING

    def pause(self):
        if self.state != EngineState.RUNNING:
            raise ValueError("pause requires running state")
        self._record("command", command="pause")
        self.state = EngineState.PAUSED

    def resume(self):
        if self.state != EngineState.PAUSED:
            raise ValueError("resume requires paused state")
        self._record("command", command="resume")
        self.state = EngineState.RUNNING

    def reset(self):
        # Keep the audit log, but restore initial topology, pending events and RNGs.
        self._record("command", command="reset")
        if self.demo:
            self.policy_controller.on_reset()
            self.rollouts.on_reset()
        self.telemetry_epoch += 1
        self._initialize()

    def schedule(self, event: ScheduledEvent):
        if not isinstance(event, ScheduledEvent):
            raise ValueError("schedule requires ScheduledEvent")
        if event.at_tick <= self.tick or event.event_id in self._event_ids:
            raise ValueError("event must be in the future with an unused event_id")
        EngineConfig(self.world, self.config.seed, self.config.tick_seconds, (event,))
        self._record("command", command="schedule", event=event.to_dict())
        self._queue.append((self._next_order, event))
        self._next_order += 1
        self._event_ids.add(event.event_id)

    def advance(self, ticks=1):
        _integer(ticks, "ticks", 1)
        if self.state != EngineState.RUNNING:
            raise ValueError("advance requires running state; use step while paused")
        self._record("command", command="advance", ticks=ticks)
        for _ in range(ticks):
            self._tick_once()
        return self.snapshot()

    def step(self, ticks=1):
        _integer(ticks, "ticks", 1)
        if self.state == EngineState.RUNNING:
            raise ValueError("pause before stepping")
        self._record("command", command="step", ticks=ticks)
        self.state = EngineState.PAUSED
        for _ in range(ticks):
            self._tick_once()
        return self.snapshot()

    def _tick_once(self):
        self.tick += 1
        for order, event in sorted(self._queue, key=lambda entry: (entry[1].at_tick, entry[0])):
            if event.at_tick == self.tick:
                if event.action == "set_host_lifecycle":
                    self.world = replace(self.world, hosts=tuple(
                        replace(h, lifecycle=event.lifecycle) if h.host_id == event.host_id else h
                        for h in self.world.hosts))
                self._record("event", order=order, event=event.to_dict())
        self._queue = [(o, e) for o, e in self._queue if e.at_tick > self.tick]
        if self.demo:
            self.demo.before_tick(self.tick)
            self.policy_controller.before_rollout_tick()
            self.rollouts.before_tick(self.tick)
            self.policy_controller.before_tick()
        self._workload = self.route_workload()
        self.world = self.update_resources(self._workload)
        self._observations = self.emit_observations()
        if self.telemetry:
            deployment = self.demo.deployment if self.demo else {}
            exposed = {r.replica_id for r in self.world.replicas if r.release_id==deployment.get("release_id")
                       and r.host_id in deployment.get("canaries",[]) and r.service_id==deployment.get("service_id")}
            if self.demo: exposed.update(self.rollouts.exposed_replicas())
            self.telemetry.emit(self.world,self.tick,self.resource_model.completed_batches,
                self.resource_model.routed_by_replica,self.resource_model.last_hosts,exposed,self.rngs["telemetry_loss"])
            self.telemetry_evaluator.capture(self.telemetry.last_source_records,self.tick,self.demo,self.resource_model)
        if self.demo:self.policy_controller.after_observations()
        self._record("published", phases=list(PHASES), snapshot_hash=_digest(self.snapshot()))

    def route_workload(self):
        if self.resource_model:
            return self.resource_model.route(self.world, self.tick, self.rngs["workload"],self.rngs.get("routing"))
        return {"adapter": "static-no-workload", "routed_requests": 0}

    def update_resources(self, workload):
        if self.resource_model:
            return self.resource_model.update(self.world, self.tick)
        return self.world

    def emit_observations(self):
        if self.resource_model:
            return copy.deepcopy(self.resource_model.last_hosts)
        # State snapshots, not request-level telemetry or invented latency measurements.
        return [{"tick": self.tick, "simulated_seconds": self.tick * self.config.tick_seconds,
                 "host_id": h.host_id, "lifecycle": h.lifecycle.value,
                 "usage": {"cpu_cores": h.usage.cpu_cores, "memory_mb": h.usage.memory_mb,
                           "disk_mb": h.usage.disk_mb, "network_mbps": h.usage.network_mbps}}
                for h in self.world.hosts]

    def snapshot(self):
        value = {"tick": self.tick, "simulated_seconds": self.tick * self.config.tick_seconds,
                              "state": self.state.value, "world": self.world.snapshot(),
                              "workload": self._workload, "observations": self._observations}
        if self.resource_model:
            value["resources"] = self.resource_model.snapshot()
            from .resource_health import summarize
            value['resource_health']=summarize(self.resource_model.host_trace,self.tick*self.config.tick_seconds,self.config.resources.health_policy)
        if self.demo:
            value["deployment"] = copy.deepcopy(self.demo.deployment)
            if self.policy_controller.bindings:value["release_policy"]=self.policy_controller.snapshot()
            if self.rollouts.records(): value["rollout"] = self.rollouts.snapshot()
        if self.telemetry:
            value["telemetry"] = self.telemetry.summary()
        return copy.deepcopy(value)

    def export_traces(self, directory):
        if not self.resource_model:
            raise ValueError("trace export requires resource configuration")
        self.resource_model.export_traces(directory)

    def artifact(self):
        config = self.config.to_dict()
        value = {"schema_version": 1, "engine_id": "world-resources-v1" if self.resource_model else ENGINE_ID, "config": config,
                "seed": self.config.seed, "log": self.log, "final_snapshot": self.snapshot(),
                "run_id": self.run_id,
                "rng_states": {n: copy.deepcopy(r.bit_generator.state) for n, r in self.rngs.items()},
                "manifest": {"config_hash": _digest(config),
                             "engine_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                             "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
                             "git": "not recorded by clock kernel", "phase_adapter": "resources-v1" if self.resource_model else "static-v1"}}
        if self.resource_model:
            value["resource_trace"] = self.resource_model.trace()
            if self.config.resources.paired_exogenous:
                value["world_exogenous"] = copy.deepcopy(list(self.resource_model.exogenous_trace))
                value["manifest"]["world_pairing"] = "uniform-quantile-arrivals-routing-v1"
                value["manifest"]["generator_id"] = "resource-world-scenarios-v1"
            value['manifest']['resource_health_sha256']=hashlib.sha256(Path(__file__).with_name('resource_health.py').read_bytes()).hexdigest()
            value["manifest"]["resource_sha256"] = hashlib.sha256(Path(__file__).with_name("resources.py").read_bytes()).hexdigest()
        if self.demo:
            value["release_policy_state"]=self.policy_controller.snapshot()
            value["manifest"]["policy_sha256"]=_digest({n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ("first_crossing.py","policy_artifacts.py","policy_control.py","policy_hash.py")})
            value["rollout_state"] = self.rollouts.snapshot()
            value["manifest"]["rollouts_sha256"] = hashlib.sha256(Path(__file__).with_name("rollouts.py").read_bytes()).hexdigest()
            value["demo_control_state"] = self.demo.control_state()
            value["developer_fault_truth"] = self.demo.developer_truth()
            value["manifest"]["release_registry_sha256"] = hashlib.sha256(Path(__file__).with_name("releases.py").read_bytes()).hexdigest()
            value["manifest"]["release_behavior_model"] = "declared-release-response-v1"
            value["manifest"]["operations_sha256"] = hashlib.sha256(Path(__file__).with_name("operations.py").read_bytes()).hexdigest()
            value["manifest"]["faults_sha256"] = hashlib.sha256(Path(__file__).with_name("faults.py").read_bytes()).hexdigest()
            value["manifest"]["scheduler_sha256"] = hashlib.sha256(Path(__file__).with_name("fault_scheduler.py").read_bytes()).hexdigest()
            value["manifest"]["background_faults"] = self.demo.background.manifest()
        if self.telemetry:
            value["public_telemetry"] = self.telemetry.public_artifact()
            value["telemetry_transport_state"] = self.telemetry.transport_state()
            value["evaluator_telemetry_truth"] = self.telemetry_evaluator.artifact()
            for name in ("telemetry","telemetry_transport","telemetry_evaluator"):
                value["manifest"][name+"_sha256"] = hashlib.sha256(Path(__file__).with_name(name+".py").read_bytes()).hexdigest()
        return value

    def export_telemetry(self,directory):
        if not self.telemetry:
            raise ValueError("Public telemetry is not enabled")
        self.telemetry.export_public(Path(directory)/"public")
        self.telemetry_evaluator.export(Path(directory)/"evaluator")

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.artifact(), indent=2, allow_nan=False) + "\n", encoding="utf-8")

    @classmethod
    def replay(cls, artifact):
        if artifact.get("schema_version") != 1 or artifact.get("engine_id") not in (ENGINE_ID, "world-resources-v1"):
            raise ValueError("incompatible replay artifact")
        engine = cls(EngineConfig.from_dict(artifact["config"]),run_id=artifact.get("run_id"))
        expected = engine.artifact()["manifest"]
        compatibility = ("config_hash", "engine_sha256", "numpy", "phase_adapter")
        if engine.resource_model:
            compatibility += ("resource_sha256","resource_health_sha256")
            if engine.config.resources.paired_exogenous:
                compatibility += ("world_pairing","generator_id")
        if engine.demo:
            compatibility += ("policy_sha256", "rollouts_sha256", "operations_sha256", "release_registry_sha256", "release_behavior_model", "faults_sha256", "scheduler_sha256", "background_faults")
        if engine.telemetry:
            compatibility += ("telemetry_sha256","telemetry_transport_sha256","telemetry_evaluator_sha256")
        if artifact["engine_id"] != engine.artifact()["engine_id"] or any(artifact["manifest"].get(k) != expected[k] for k in compatibility):
            raise ValueError("replay config, engine code or NumPy version mismatch")
        if artifact.get("seed") != engine.config.seed:
            raise ValueError("replay seed mismatch")
        for entry in artifact["log"]:
            if entry["kind"] != "command":
                continue
            command = entry["command"]
            if command in ("start", "pause", "resume", "reset"):
                getattr(engine, command)()
            elif command in ("step", "advance"):
                getattr(engine, command)(entry["ticks"])
            elif command == "schedule":
                engine.schedule(ScheduledEvent.from_dict(entry["event"]))
            elif command == "demo":
                engine.operations_command(entry["action"], entry["args"])
            else:
                raise ValueError(f"unknown replay command: {command}")
        actual = engine.artifact()
        outputs = ("log", "final_snapshot", "rng_states") + (("resource_trace",) if engine.resource_model else ())
        if engine.resource_model and engine.config.resources.paired_exogenous:
            outputs += ("world_exogenous",)
        if engine.demo:
            outputs += ("release_policy_state", "rollout_state", "demo_control_state", "developer_fault_truth")
        if engine.telemetry:
            outputs += ("public_telemetry","telemetry_transport_state","evaluator_telemetry_truth")
        if any(actual[k] != artifact[k] for k in outputs):
            raise ValueError("replay verification failed: log, snapshot or RNG state differs")
        return engine
