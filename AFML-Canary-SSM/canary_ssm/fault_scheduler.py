"""Pre-generated background disturbances; developer/evaluator data, never inference input."""
from dataclasses import asdict, dataclass, field
import copy
import hashlib
import json
import math

import numpy as np

from .faults import FaultEvent
from .seeds import seed_for


def _int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")


def _num(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite in [{low}, {high}]")


def schedule_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class FaultRate:
    rule_id: str
    kind: str
    scope: str
    rate_per_second: float
    severity_min: float = .4
    severity_max: float = .8
    duration_min_seconds: float = 3
    duration_max_seconds: float = 8
    cooldown_seconds: float = 10

    def __post_init__(self):
        if not isinstance(self.rule_id, str) or not self.rule_id or len(self.rule_id) > 64 or self.rule_id.strip() != self.rule_id:
            raise ValueError("rule_id must be a nonempty identifier of at most 64 characters")
        FaultEvent("validate", self.kind, self.scope, "world", 1, 1, .5, 0,
                   "restart" if self.kind == "service_crash" else "restore")
        _num(self.rate_per_second, "rate_per_second", 0, 1000)
        _num(self.severity_min, "severity_min", .1, .95)
        _num(self.severity_max, "severity_max", self.severity_min, .95)
        _num(self.duration_min_seconds, "duration_min_seconds", .001, 1_000_000)
        _num(self.duration_max_seconds, "duration_max_seconds", self.duration_min_seconds, 1_000_000)
        _num(self.cooldown_seconds, "cooldown_seconds", 0, 1_000_000)

    def duration_ticks(self, dt):
        low, high = math.ceil(self.duration_min_seconds/dt), math.floor(self.duration_max_seconds/dt)
        if low > high or low < 1 or high > 1000:
            raise ValueError("Duration range must contain whole ticks in [1, 1000]")
        return low, high


@dataclass(frozen=True)
class BackgroundFaultConfig:
    enabled: bool = False
    seed: int = field(default_factory=lambda: seed_for("smoke", 0))
    mode: str = "rates"
    horizon_ticks: int = 120
    max_concurrent: int = 3
    max_events: int = 500
    fixed_cooldown_seconds: float = 0
    rules: tuple[FaultRate, ...] = ()
    fixed_events: tuple[FaultEvent, ...] = ()

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("background enabled must be boolean")
        _int(self.seed, "background seed", 0, 2**32-1)
        _int(self.horizon_ticks, "horizon_ticks", 1, 10000)
        _int(self.max_concurrent, "max_concurrent", 1, 100)
        _int(self.max_events, "max_events", 1, 500)
        _num(self.fixed_cooldown_seconds, "fixed_cooldown_seconds", 0, 1_000_000)
        if self.mode not in ("rates", "fixed"):
            raise ValueError("background mode must be rates or fixed")
        for name, record in (("rules", FaultRate), ("fixed_events", FaultEvent)):
            items = getattr(self, name)
            if not isinstance(items, (tuple, list)) or not all(isinstance(x, record) for x in items):
                raise ValueError(f"Invalid background {name}")
            object.__setattr__(self, name, tuple(items))
        if len(self.rules) > 16 or len({r.rule_id for r in self.rules}) != len(self.rules):
            raise ValueError("Use at most 16 uniquely named rules")
        if (self.mode == "rates" and self.fixed_events) or (self.mode == "fixed" and self.rules):
            raise ValueError("Do not mix fixed events and rate rules")
        if len(self.fixed_events) > self.max_events:
            raise ValueError("Fixed schedule exceeds max_events")

    def to_dict(self):
        return {"enabled": self.enabled, "seed": self.seed, "mode": self.mode,
                "horizon_ticks": self.horizon_ticks, "max_concurrent": self.max_concurrent,
                "max_events": self.max_events, "fixed_cooldown_seconds": self.fixed_cooldown_seconds,
                "rules": [asdict(r) for r in self.rules],
                "fixed_events": [{k: v for k, v in f.to_dict().items()
                                  if k not in ("end_tick", "host_ids", "origin")} for f in self.fixed_events]}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("background_faults must be an object")
        data = dict(value)
        try:
            for name, record in (("rules", FaultRate), ("fixed_events", FaultEvent)):
                items = data.get(name, [])
                if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                    raise ValueError(f"background {name} must be a list of objects")
                data[name] = tuple(record(**item) for item in items)
            return cls(**data)
        except TypeError as exc:
            raise ValueError(f"Invalid background configuration: {exc}") from exc


class BackgroundFaultScheduler:
    """Absolute run ticks; enabling never shifts time or changes the schedule."""
    def __init__(self, config, world, tick_seconds):
        self.config, self.dt = config, tick_seconds
        self.enabled = config.enabled
        self.events, self.rule_ids = [], {}
        self.summary = {"candidate_events": 0, "rejected_cooldown": 0,
                        "rejected_concurrency": 0, "rejected_capacity": 0}
        self.sampling = []
        if config.mode == "fixed":
            self._fixed(world)
        else:
            self._sample(world)

    def _fixed(self, world):
        next_allowed, ids = {}, set()
        cooldown = math.ceil(self.config.fixed_cooldown_seconds/self.dt)
        for event in sorted(self.config.fixed_events, key=lambda f: (f.start_tick, f.fault_id)):
            event = event.resolve(world)
            if event.fault_id in ids or event.start_tick > self.config.horizon_ticks:
                raise ValueError("Duplicate fixed ID or start outside schedule horizon")
            key = (event.scope.value, event.target)
            if event.start_tick < next_allowed.get(key, 1):
                raise ValueError("Fixed schedule violates cooldown")
            if sum(f.active(event.start_tick) for f in self.events) >= self.config.max_concurrent:
                raise ValueError("Fixed schedule exceeds max_concurrent")
            self.events.append(event)
            ids.add(event.fault_id)
            next_allowed[key] = event.end_tick + cooldown
        self.summary["candidate_events"] = len(self.events)

    def _sample(self, world):
        lanes = []
        for rule in sorted(self.config.rules, key=lambda r: r.rule_id):
            low, high = rule.duration_ticks(self.dt)
            targets = sorted(h.host_id for h in world.hosts) if rule.scope == "host" else sorted({h.rack_id for h in world.hosts}) if rule.scope == "rack" else ["world"]
            for target in targets:
                key = hashlib.sha256(json.dumps([rule.rule_id, target]).encode()).digest()
                words = [int.from_bytes(key[i:i+4], "little") for i in range(0, 16, 4)]
                rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.config.seed, 2, *words])))
                lanes.append((rule, target, rng, low, high))
            self.sampling.append({"rule_id": rule.rule_id, "scope": rule.scope,
                "rate_per_second_per_target": rule.rate_per_second, "targets": len(targets),
                "nominal_world_rate_per_second": len(targets)*rule.rate_per_second,
                "candidate_probability_per_tick": -math.expm1(-rule.rate_per_second*self.dt),
                "duration_ticks_inclusive": [low, high], "cooldown_ticks": math.ceil(rule.cooldown_seconds/self.dt)})
        if len(lanes)*self.config.horizon_ticks > 2_000_000:
            raise ValueError("Background sampling exceeds 2000000 lane-ticks; shorten horizon or reduce rules")
        next_allowed, active_ends = {}, []
        for tick in range(1, self.config.horizon_ticks+1):
            active_ends = [end for end in active_ends if end > tick]
            for rule, target, rng, low, high in lanes:
                # Draw even if suppressed, keeping each lane's future candidates independent of admission.
                trigger, severity_u, duration_u, seed_u = rng.random(4)
                if trigger >= -math.expm1(-rule.rate_per_second*self.dt):
                    continue
                self.summary["candidate_events"] += 1
                key = (rule.scope, target)
                if tick < next_allowed.get(key, 1):
                    self.summary["rejected_cooldown"] += 1
                    continue
                if len(active_ends) >= self.config.max_concurrent:
                    self.summary["rejected_concurrency"] += 1
                    continue
                if len(self.events) >= self.config.max_events:
                    self.summary["rejected_capacity"] += 1
                    continue
                event = FaultEvent(f"background-{len(self.events)+1}", rule.kind, rule.scope, target,
                    tick, low+min(high-low, int(duration_u*(high-low+1))),
                    float(rule.severity_min+severity_u*(rule.severity_max-rule.severity_min)), int(seed_u*2**32),
                    "restart" if rule.kind == "service_crash" else "restore").resolve(world)
                self.events.append(event)
                active_ends.append(event.end_tick)
                self.rule_ids[event.fault_id] = rule.rule_id
                next_allowed[key] = event.end_tick+math.ceil(rule.cooldown_seconds/self.dt)

    def active_events(self, tick):
        return [f for f in self.events if self.enabled and f.active(tick)]

    def manifest(self):
        events = [{**f.to_dict(), "source": "background", "rule_id": self.rule_ids.get(f.fault_id)} for f in self.events]
        return {"scheduler_id": "background-grid-hazard-v1", "sampling_rule": "bernoulli-per-target-per-tick",
                "time_unit": "simulated_second", "config": self.config.to_dict(),
                "sampling": copy.deepcopy(self.sampling), "summary": {**self.summary, "accepted_events": len(events)},
                "events": events, "schedule_sha256": schedule_hash(events)}

    def preview(self, tick):
        return {**self.manifest(), "developer_only": True, "enabled": self.enabled,
                "tick": tick, "horizon_exhausted": tick >= self.config.horizon_ticks,
                "active_events": len(self.active_events(tick)),
                "future_events": sum(f.start_tick > tick for f in self.events)}
