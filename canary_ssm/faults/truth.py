"""Evaluator Fault Truth Store.

STRICT ANTI-LEAKAGE FIREWALL:
This module contains ground truth about injected faults, schedules, affected sets,
and downtime gaps. It is intended EXCLUSIVELY for the Evaluator and Developer Fault Lab.
Inference and detector modules (`factor`, `preprocess`, `kalman`, `hierarchy`, `decision`, `telemetry`)
must NEVER import, reference, or read this store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import FaultDefinition


@dataclass
class TickFaultTruth:
    """Evaluator-only ground truth state at a single discrete simulation tick."""
    tick: int
    active_fault_ids: list[str] = field(default_factory=list)
    affected_server_ids: list[str] = field(default_factory=list)
    outage_server_ids: list[str] = field(default_factory=list)
    oom_restarting_server_ids: list[str] = field(default_factory=list)
    # Per-server injected ground truth signal deltas: server_id -> {signal_name: float}
    server_truth_deltas: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "active_fault_ids": list(self.active_fault_ids),
            "affected_server_ids": list(self.affected_server_ids),
            "outage_server_ids": list(self.outage_server_ids),
            "oom_restarting_server_ids": list(self.oom_restarting_server_ids),
            "server_truth_deltas": {sid: dict(d) for sid, d in self.server_truth_deltas.items()},
        }


class EvaluatorFaultTruthStore:
    """Evaluator-only repository of injected fault truth."""

    def __init__(self) -> None:
        self.faults: dict[str, FaultDefinition] = {}
        self.tick_history: dict[int, TickFaultTruth] = {}
        self.oom_crash_events: list[dict[str, Any]] = []

    def register_fault(self, fault: FaultDefinition) -> None:
        self.faults[fault.fault_id] = fault

    def record_oom_crash(self, server_id: str, tick: int, restart_until_tick: int, memory_mb: float) -> None:
        """Record an out-of-memory crash event and the resulting telemetry gap."""
        self.oom_crash_events.append({
            "server_id": server_id,
            "crash_tick": tick,
            "restart_until_tick": restart_until_tick,
            "memory_at_crash_mb": float(memory_mb),
        })

    def record_tick_truth(self, truth: TickFaultTruth) -> None:
        self.tick_history[truth.tick] = truth

    def get_tick_truth(self, tick: int) -> TickFaultTruth | None:
        return self.tick_history.get(tick)

    def is_server_affected(self, server_id: str, tick: int) -> bool:
        rec = self.tick_history.get(tick)
        return server_id in rec.affected_server_ids if rec else False

    def is_server_in_outage(self, server_id: str, tick: int) -> bool:
        rec = self.tick_history.get(tick)
        return server_id in rec.outage_server_ids if rec else False

    def clear(self) -> None:
        self.faults.clear()
        self.tick_history.clear()
        self.oom_crash_events.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "registered_faults": [f.to_dict() for f in self.faults.values()],
            "oom_crash_events": list(self.oom_crash_events),
            "total_ticks_recorded": len(self.tick_history),
        }
