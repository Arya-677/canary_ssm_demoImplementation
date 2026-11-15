"""VirtualWorld: Orchestrator uniting Fleet, SimulatedClock, and EventQueue.

Guarantees:
- Pure discrete-time simulation separated from wall clock.
- Strict determinism: step(N) matches N single steps of step(1).
- Reset with same config and seed bitwise reproduces the same world and event history.
- Bounded fast-forward with safety limits.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from canary_ssm.telemetry import TelemetryRecord
from canary_ssm.faults import (
    FaultDefinition,
    FaultEngine,
    FaultHazardConfig,
    EvaluatorFaultTruthStore,
)
from .clock import Event, EventQueue, SimulatedClock
from .models import Fleet, Rack, Server, create_default_fleet
from .telemetry import HealthyTelemetryConfig, HealthyTelemetryEngine


@dataclass
class WorldStepResult:
    """Outcome of advancing the world simulation."""
    tick: int
    ticks_advanced: int
    is_paused: bool
    events_executed: list[dict[str, Any]] = field(default_factory=list)
    telemetry: list[TelemetryRecord] = field(default_factory=list)


class VirtualWorld:
    """The Virtual Data Center world engine.

    Unites fleet topology, deterministic simulated clock, event scheduler,
    healthy multi-metric telemetry generation, and fault injection.
    """

    def __init__(
        self,
        fleet: Fleet | None = None,
        seed: int = 42,
        start_paused: bool = True,
        telemetry_config: HealthyTelemetryConfig | None = None,
        fault_hazard_config: FaultHazardConfig | None = None,
        run_id: str | None = None,
    ) -> None:
        self.initial_seed = int(seed)
        self.rng = np.random.default_rng(self.initial_seed)
        self.run_id = run_id or f"run-{self.initial_seed}"

        # Build initial fleet
        if fleet is None:
            self._initial_fleet_dict = create_default_fleet().to_dict()
        else:
            self._initial_fleet_dict = fleet.to_dict()

        self.fleet: Fleet = Fleet.from_dict(copy.deepcopy(self._initial_fleet_dict))
        self.clock: SimulatedClock = SimulatedClock(tick=0, is_paused=start_paused)
        self.event_queue: EventQueue = EventQueue()
        self.event_history: list[dict[str, Any]] = []

        # Telemetry generator
        self.telemetry_engine: HealthyTelemetryEngine = HealthyTelemetryEngine(
            config=telemetry_config,
            seed=self.initial_seed,
        )
        self.telemetry_history: list[TelemetryRecord] = []

        # Fault engine & Evaluator truth store
        self.fault_engine: FaultEngine = FaultEngine(
            hazard_config=fault_hazard_config,
            seed=self.initial_seed,
        )

    @classmethod
    def create_default(
        cls,
        n_racks: int = 4,
        servers_per_rack: int = 6,
        n_classes: int = 2,
        seed: int = 42,
        start_paused: bool = True,
        telemetry_config: HealthyTelemetryConfig | None = None,
        fault_hazard_config: FaultHazardConfig | None = None,
        run_id: str | None = None,
    ) -> "VirtualWorld":
        """Factory method to construct a VirtualWorld with default or sized fleet."""
        fleet = create_default_fleet(n_racks=n_racks, servers_per_rack=servers_per_rack, n_classes=n_classes)
        return cls(
            fleet=fleet,
            seed=seed,
            start_paused=start_paused,
            telemetry_config=telemetry_config,
            fault_hazard_config=fault_hazard_config,
            run_id=run_id,
        )

    def start(self) -> None:
        """Start or resume simulation clock."""
        self.clock.start()

    def pause(self) -> None:
        """Pause simulation clock."""
        self.clock.pause()

    def schedule_event(
        self,
        tick: int,
        event_type: str,
        payload: dict[str, Any] | None = None,
        target_id: str | None = None,
        priority: int = 10,
        callback: Callable[[Event, Any], None] | None = None,
    ) -> Event:
        """Schedule an event on the event queue."""
        if tick < self.clock.tick:
            raise ValueError(
                f"Cannot schedule event in the past: tick={tick} < current_tick={self.clock.tick}"
            )
        return self.event_queue.schedule(
            tick=tick,
            event_type=event_type,
            payload=payload,
            target_id=target_id,
            priority=priority,
            callback=callback,
        )

    def _dispatch_event(self, ev: Event) -> dict[str, Any]:
        """Dispatch a single event and apply built-in world state mutations."""
        exec_record: dict[str, Any] = {
            "tick": self.clock.tick,
            "event_tick": ev.tick,
            "seq": ev.seq,
            "event_type": ev.event_type,
            "target_id": ev.target_id,
            "payload": dict(ev.payload),
        }

        # Handle built-in topology lifecycle events
        if ev.event_type == "SET_SERVER_ONLINE" and ev.target_id:
            online = bool(ev.payload.get("online", True))
            self.set_server_online(ev.target_id, online)
            exec_record["applied"] = f"server {ev.target_id} online={online}"
        elif ev.event_type == "SET_SERVER_VERSION" and ev.target_id:
            ver = str(ev.payload.get("version", ""))
            self.set_server_version(ev.target_id, ver)
            exec_record["applied"] = f"server {ev.target_id} version={ver}"
        elif ev.event_type == "SET_RACK_ONLINE" and ev.target_id:
            online = bool(ev.payload.get("online", True))
            self.set_rack_online(ev.target_id, online)
            exec_record["applied"] = f"rack {ev.target_id} online={online}"

        # Execute custom callback if attached
        if ev.callback is not None:
            ev.callback(ev, self)
            exec_record["has_callback"] = True

        self.event_history.append(exec_record)
        return exec_record

    def step(self, n: int = 1) -> WorldStepResult:
        """Advance the simulation by n discrete ticks.

        Guarantees:
        Advancing N ticks together matches calling step(1) N times in succession.
        """
        if n < 1:
            raise ValueError(f"Step increment must be at least 1, got {n}")

        all_dispatched: list[dict[str, Any]] = []
        all_telemetry: list[TelemetryRecord] = []

        for _ in range(n):
            # Advance clock by 1 tick
            self.clock.step(1)
            current_tick = self.clock.tick

            # Pop all events scheduled at or before the current tick
            ready_events = self.event_queue.pop_until(current_tick)
            for ev in ready_events:
                rec = self._dispatch_event(ev)
                all_dispatched.append(rec)

            # Evaluate active faults for current tick
            fault_deltas = self.fault_engine.evaluate_tick_faults(self.fleet, current_tick)

            # Generate multi-metric telemetry observation for current tick
            tick_telemetry = self.telemetry_engine.generate_tick_telemetry(
                self.fleet, current_tick, self.run_id, fault_deltas=fault_deltas
            )
            all_telemetry.extend(tick_telemetry)
            self.telemetry_history.extend(tick_telemetry)

        return WorldStepResult(
            tick=self.clock.tick,
            ticks_advanced=n,
            is_paused=self.clock.is_paused,
            events_executed=all_dispatched,
            telemetry=all_telemetry,
        )

    def fast_forward(self, until_tick: int, max_ticks: int = 1000) -> WorldStepResult:
        """Advance simulation up to until_tick, bounded by max_ticks."""
        if until_tick < self.clock.tick:
            raise ValueError(
                f"Cannot fast-forward backward: current={self.clock.tick}, target={until_tick}"
            )
        delta = until_tick - self.clock.tick
        if delta == 0:
            return WorldStepResult(
                tick=self.clock.tick,
                ticks_advanced=0,
                is_paused=self.clock.is_paused,
                events_executed=[],
                telemetry=[],
            )
        if delta > max_ticks:
            raise ValueError(
                f"Fast-forward delta {delta} exceeds max_ticks limit of {max_ticks}"
            )
        return self.step(delta)

    def reset(self, seed: int | None = None) -> None:
        """Reset the world to its exact initial state and tick 0.

        Guarantees deterministic replay of world state.
        """
        active_seed = self.initial_seed if seed is None else int(seed)
        self.rng = np.random.default_rng(active_seed)
        self.fleet = Fleet.from_dict(copy.deepcopy(self._initial_fleet_dict))
        self.clock.reset(initial_tick=0)
        self.event_queue.clear()
        self.event_history.clear()
        self.telemetry_engine.reset(active_seed)
        self.telemetry_history.clear()
        self.fault_engine.reset(active_seed)

    # ---------------- Fault Injection & Evaluator Truth ----------------
    def inject_fault(self, fault: FaultDefinition) -> None:
        """Register a fault definition with the world's fault engine."""
        self.fault_engine.register_manual_fault(fault)

    @property
    def truth_store(self) -> EvaluatorFaultTruthStore:
        """Access evaluator-only fault ground truth store."""
        return self.fault_engine.truth_store

    # ---------------- Workload & Shared Variations ----------------
    def set_fleet_workload_offset(self, offset: float) -> None:
        """Introduce shared fleet-wide workload demand shift."""
        self.telemetry_engine.set_fleet_workload_offset(offset)

    def set_rack_offset(self, rack_id: str, offset: float) -> None:
        """Introduce shared rack-level nuisance / workload shift."""
        self.telemetry_engine.set_rack_offset(rack_id, offset)

    def get_latest_telemetry(self) -> list[TelemetryRecord]:
        """Return the most recent tick's telemetry observations."""
        n_servers = self.fleet.total_servers
        if len(self.telemetry_history) < n_servers:
            return list(self.telemetry_history)
        return self.telemetry_history[-n_servers:]

    # ---------------- Topology Mutations ----------------
    def set_server_online(self, server_id: str, online: bool) -> None:
        srv = self.fleet.get_server(server_id)
        srv.online = bool(online)

    def set_server_version(self, server_id: str, version: str) -> None:
        if not version:
            raise ValueError("Version string cannot be empty")
        srv = self.fleet.get_server(server_id)
        srv.installed_version = str(version)

    def set_rack_online(self, rack_id: str, online: bool) -> None:
        rack = self.fleet.get_rack(rack_id)
        rack.online = bool(online)

    def inspect_topology(self) -> dict[str, Any]:
        """Return structured summary of the world topology and clock state."""
        summary = self.fleet.summary()
        summary["clock"] = self.clock.to_dict()
        summary["pending_events"] = self.event_queue.count()
        summary["executed_events"] = len(self.event_history)
        return summary

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete world configuration and state."""
        return {
            "initial_seed": self.initial_seed,
            "clock": self.clock.to_dict(),
            "fleet": self.fleet.to_dict(),
            "event_queue": self.event_queue.to_list(),
            "event_history": list(self.event_history),
        }
