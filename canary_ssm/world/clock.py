"""Deterministic discrete simulated clock and event queue for the Virtual Data Center.

Separates simulated discrete time (integer ticks) completely from wall-clock time.
Guarantees deterministic event ordering and replay.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SimulatedClock:
    """Discrete simulation clock.

    Time advances only through explicit tick increments, strictly independent of wall clock.
    """
    tick: int = 0
    is_paused: bool = True

    def __post_init__(self) -> None:
        if self.tick < 0:
            raise ValueError(f"Clock tick cannot be negative, got {self.tick}")

    def start(self) -> None:
        """Unpause the clock."""
        self.is_paused = False

    def pause(self) -> None:
        """Pause the clock."""
        self.is_paused = True

    def step(self, n: int = 1) -> int:
        """Advance the clock by n discrete ticks."""
        if n < 0:
            raise ValueError(f"Step increment cannot be negative, got {n}")
        self.tick += n
        return self.tick

    def reset(self, initial_tick: int = 0) -> None:
        """Reset the clock to the initial tick and pause state."""
        if initial_tick < 0:
            raise ValueError(f"initial_tick cannot be negative, got {initial_tick}")
        self.tick = initial_tick
        self.is_paused = True

    @property
    def current_tick(self) -> int:
        return self.tick

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "is_paused": self.is_paused,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimulatedClock":
        return cls(
            tick=int(d.get("tick", 0)),
            is_paused=bool(d.get("is_paused", True)),
        )


@dataclass(order=False)
class Event:
    """Scheduled simulation event.

    Attributes:
        tick: Discrete simulated minute/step at which the event executes.
        priority: Execution priority at the same tick (lower executes first).
        seq: Deterministic sequence index for stable FIFO tie-breaking.
        event_type: Name of the event (e.g. "FAULT_INJECT", "DEPLOY", "CONFIG_CHANGE").
        target_id: Target entity ID (e.g., server_id, rack_id, or None).
        payload: Event parameters.
        callback: Optional hook callable: (event, world) -> None.
    """
    tick: int
    priority: int
    seq: int
    event_type: str
    target_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    callback: Callable[[Event, Any], None] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "priority": self.priority,
            "seq": self.seq,
            "event_type": self.event_type,
            "target_id": self.target_id,
            "payload": dict(self.payload),
        }


class EventQueue:
    """Deterministic min-heap event queue ordered by (tick, priority, seq)."""

    def __init__(self) -> None:
        # Heap elements are tuples: (tick, priority, seq, event)
        self._heap: list[tuple[int, int, int, Event]] = []
        self._seq_counter: int = 0

    def schedule(
        self,
        tick: int,
        event_type: str,
        payload: dict[str, Any] | None = None,
        target_id: str | None = None,
        priority: int = 10,
        callback: Callable[[Event, Any], None] | None = None,
    ) -> Event:
        """Schedule an event for execution at discrete tick."""
        if tick < 0:
            raise ValueError(f"Cannot schedule event at negative tick: {tick}")
        if not event_type:
            raise ValueError("event_type must be a non-empty string")

        self._seq_counter += 1
        ev = Event(
            tick=tick,
            priority=priority,
            seq=self._seq_counter,
            event_type=event_type,
            target_id=target_id,
            payload=payload or {},
            callback=callback,
        )
        heapq.heappush(self._heap, (tick, priority, ev.seq, ev))
        return ev

    def peek(self) -> Event | None:
        """Return the next earliest event without removing it."""
        if not self._heap:
            return None
        return self._heap[0][3]

    def pop_until(self, target_tick: int) -> list[Event]:
        """Pop and return all events scheduled at or before target_tick in strict order."""
        events: list[Event] = []
        while self._heap and self._heap[0][0] <= target_tick:
            _, _, _, ev = heapq.heappop(self._heap)
            events.append(ev)
        return events

    def clear(self) -> None:
        """Clear all events and reset the sequence counter."""
        self._heap.clear()
        self._seq_counter = 0

    def count(self) -> int:
        return len(self._heap)

    def all_events(self) -> list[Event]:
        """Return all scheduled events sorted by (tick, priority, seq)."""
        sorted_items = sorted(self._heap, key=lambda x: (x[0], x[1], x[2]))
        return [item[3] for item in sorted_items]

    def to_list(self) -> list[dict[str, Any]]:
        return [ev.to_dict() for ev in self.all_events()]
