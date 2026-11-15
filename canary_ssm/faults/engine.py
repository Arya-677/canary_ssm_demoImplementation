"""Fault Engine for the Virtual Data Center.

Applies explicit infrastructure and release faults with:
- Independent RNG streams (workload, noise, fault_scheduling, susceptibility, missingness).
- Distinct infrastructure vs. release scopes.
- Strict anti-leakage: Truth is recorded exclusively in EvaluatorFaultTruthStore.
- Resource pressure coupling for memory leaks (Normal -> Pressure -> Thrashing -> OOM crash/restart).
- Overlapping fault composition and recovery semantics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from canary_ssm.world.models import Fleet, Rack, Server

from .models import FaultCategory, FaultDefinition, FaultScope, FaultType
from .truth import EvaluatorFaultTruthStore, TickFaultTruth


@dataclass
class FaultHazardConfig:
    """Per-tick (minute^-1) spontaneous fault hazards for stochastic simulations."""
    enable_stochastic: bool = False
    server_outage_hazard_per_min: float = 0.0001        # 1 per 10,000 server-minutes
    rack_network_latency_hazard_per_min: float = 0.0005 # 5 per 10,000 rack-minutes
    cpu_saturation_hazard_per_min: float = 0.0002       # 2 per 10,000 server-minutes
    fleet_demand_spike_hazard_per_min: float = 0.0010   # 1 per 1,000 fleet-minutes
    default_outage_duration: int = 15                   # minutes
    default_rack_latency_duration: int = 30             # minutes
    default_cpu_duration: int = 20                      # minutes
    default_demand_duration: int = 45                   # minutes


class FaultEngine:
    """Engine orchestrating fault injection, scheduling, and effect composition."""

    def __init__(
        self,
        hazard_config: FaultHazardConfig | None = None,
        seed: int = 42,
    ) -> None:
        self.hazard_cfg = hazard_config or FaultHazardConfig()
        self.seed = int(seed)

        # Independent RNG streams to ensure pairing and reproducibility
        # Stream 0: workload (handled in telemetry)
        # Stream 1: noise (handled in telemetry)
        # Stream 2: fault_scheduling
        # Stream 3: susceptibility
        # Stream 4: missingness
        ss = np.random.SeedSequence(self.seed)
        sub_seeds = ss.spawn(5)
        self.rng_fault = np.random.default_rng(sub_seeds[2])
        self.rng_suscept = np.random.default_rng(sub_seeds[3])
        self.rng_missing = np.random.default_rng(sub_seeds[4])

        # Registered manual faults & active schedules
        self.registered_faults: list[FaultDefinition] = []
        self.truth_store: EvaluatorFaultTruthStore = EvaluatorFaultTruthStore()

        # Dynamic runtime fault tracking
        # Server ID -> restart_until_tick
        self._server_restarting_until: dict[str, int] = {}
        # Server ID -> accumulated leak MB
        self._server_memory_leaks_mb: dict[str, float] = {}

    def register_manual_fault(self, fault: FaultDefinition) -> None:
        """Register a fixed manual fault definition (for deterministic fixtures/scenarios)."""
        self.registered_faults.append(fault)
        self.truth_store.register_fault(fault)

    def terminate_release_faults(self, release_id: str, current_tick: int) -> list[str]:
        """Terminate / expire any active or scheduled faults targeting release_id."""
        import dataclasses
        terminated = []
        new_faults = []
        for f in self.registered_faults:
            if (
                f.target_id == release_id
                or (f.target_version and release_id in str(f.target_version))
                or f.fault_id.startswith(f"fault-{release_id}")
            ):
                new_f = dataclasses.replace(f, duration=max(0, current_tick - f.onset_tick))
                new_faults.append(new_f)
                terminated.append(f.fault_id)
            else:
                new_faults.append(f)
        self.registered_faults = new_faults
        return terminated

    def reset(self, seed: int | None = None) -> None:
        """Reset internal fault state and RNGs."""
        active_seed = self.seed if seed is None else int(seed)
        ss = np.random.SeedSequence(active_seed)
        sub_seeds = ss.spawn(5)
        self.rng_fault = np.random.default_rng(sub_seeds[2])
        self.rng_suscept = np.random.default_rng(sub_seeds[3])
        self.rng_missing = np.random.default_rng(sub_seeds[4])

        self.registered_faults.clear()
        self.truth_store.clear()
        self._server_restarting_until.clear()
        self._server_memory_leaks_mb.clear()

    def _evaluate_stochastic_hazards(self, fleet: Fleet, tick: int) -> None:
        """Evaluate spontaneous hazard rates for infrastructure faults at current tick."""
        if not self.hazard_cfg.enable_stochastic:
            return

        cfg = self.hazard_cfg
        # 1. Fleet demand spike
        if self.rng_fault.uniform(0.0, 1.0) < cfg.fleet_demand_spike_hazard_per_min:
            fid = f"stoch-fleet-spike-{tick}"
            f = FaultDefinition(
                fault_id=fid,
                fault_type=FaultType.FLEET_DEMAND_SPIKE,
                scope=FaultScope.FLEET,
                target_id="fleet",
                onset_tick=tick,
                duration=cfg.default_demand_duration,
                severity=float(self.rng_fault.uniform(0.20, 0.40)),
            )
            self.register_manual_fault(f)

        # 2. Rack network latency
        for rack in fleet.list_racks():
            if self.rng_fault.uniform(0.0, 1.0) < cfg.rack_network_latency_hazard_per_min:
                fid = f"stoch-rack-lat-{rack.rack_id}-{tick}"
                f = FaultDefinition(
                    fault_id=fid,
                    fault_type=FaultType.RACK_NETWORK_LATENCY,
                    scope=FaultScope.RACK,
                    target_id=rack.rack_id,
                    onset_tick=tick,
                    duration=cfg.default_rack_latency_duration,
                    severity=float(self.rng_fault.uniform(0.10, 0.25)),
                )
                self.register_manual_fault(f)

        # 3. Server outage & CPU saturation
        for srv in fleet.list_servers():
            if self.rng_fault.uniform(0.0, 1.0) < cfg.server_outage_hazard_per_min:
                fid = f"stoch-outage-{srv.server_id}-{tick}"
                f = FaultDefinition(
                    fault_id=fid,
                    fault_type=FaultType.SERVER_OUTAGE,
                    scope=FaultScope.SERVER,
                    target_id=srv.server_id,
                    onset_tick=tick,
                    duration=cfg.default_outage_duration,
                    severity=1.0,
                )
                self.register_manual_fault(f)

    def evaluate_tick_faults(
        self,
        fleet: Fleet,
        tick: int,
    ) -> dict[str, Any]:
        """Evaluate active faults at tick and compute per-server effect deltas.

        Returns:
            dict mapping server_id -> combined fault deltas:
                - "is_outage": bool
                - "latency_log_delta": float
                - "memory_leak_mb": float
                - "cpu_saturation_delta": float
                - "error_rate_delta": float
                - "fleet_demand_delta": float
        """
        # Step stochastic hazards if enabled
        self._evaluate_stochastic_hazards(fleet, tick)

        # Active faults at this tick
        active_faults = [f for f in self.registered_faults if f.is_active_at(tick)]
        active_fault_ids = [f.fault_id for f in active_faults]

        # Handle in-flight OOM restarts
        restarting_servers: set[str] = set()
        for sid, resume_tick in list(self._server_restarting_until.items()):
            if tick < resume_tick:
                restarting_servers.add(sid)
            else:
                del self._server_restarting_until[sid]
                # Upon restart, reset accumulated memory leak to 0 MB
                self._server_memory_leaks_mb[sid] = 0.0

        # Accumulated per-server fault deltas
        deltas: dict[str, dict[str, Any]] = {
            srv.server_id: {
                "is_outage": srv.server_id in restarting_servers,
                "latency_log_delta": 0.0,
                "memory_leak_mb": self._server_memory_leaks_mb.get(srv.server_id, 0.0),
                "cpu_saturation_delta": 0.0,
                "error_rate_delta": 0.0,
                "fleet_demand_delta": 0.0,
                "active_fault_ids": [],
            }
            for srv in fleet.list_servers()
        }

        affected_servers: set[str] = set(restarting_servers)
        outage_servers: set[str] = set(restarting_servers)

        # Apply each active fault according to scope and rules
        for f in active_faults:
            # 1. Fleet Demand Spike
            if f.fault_type == FaultType.FLEET_DEMAND_SPIKE:
                for sid in deltas:
                    deltas[sid]["fleet_demand_delta"] += f.severity
                    deltas[sid]["active_fault_ids"].append(f.fault_id)
                    affected_servers.add(sid)

            # 2. Rack Network Latency (Affects ALL servers in that rack)
            elif f.fault_type == FaultType.RACK_NETWORK_LATENCY:
                target_rack = f.target_id
                for srv in fleet.list_servers():
                    if srv.rack_id == target_rack:
                        sid = srv.server_id
                        deltas[sid]["latency_log_delta"] += f.severity
                        deltas[sid]["active_fault_ids"].append(f.fault_id)
                        affected_servers.add(sid)

            # 3. Server Outage
            elif f.fault_type == FaultType.SERVER_OUTAGE:
                sid = f.target_id
                if sid in deltas:
                    deltas[sid]["is_outage"] = True
                    deltas[sid]["active_fault_ids"].append(f.fault_id)
                    affected_servers.add(sid)
                    outage_servers.add(sid)

            # 4. CPU Saturation
            elif f.fault_type == FaultType.CPU_SATURATION:
                target_servers: list[str] = []
                if f.scope == FaultScope.SERVER and f.target_id in deltas:
                    target_servers = [f.target_id]
                elif f.parameters and "target_server_ids" in f.parameters:
                    target_servers = [sid for sid in f.parameters["target_server_ids"] if sid in deltas]
                elif f.target_id in ("canaries", "canary"):
                    target_servers = [
                        s.server_id for s in fleet.list_servers()
                        if s.installed_version != "v1.0.0-baseline" and s.server_id in deltas
                    ]
                elif f.target_version:
                    # Version-scoped CPU regression
                    target_servers = [
                        s.server_id for s in fleet.list_servers()
                        if s.installed_version == f.target_version
                        and (f.susceptible_class_id is None or s.class_id == f.susceptible_class_id)
                    ]
                elif f.scope == FaultScope.RACK:
                    target_servers = [s.server_id for s in fleet.list_servers() if s.rack_id == f.target_id]
                elif f.scope == FaultScope.FLEET:
                    target_servers = list(deltas.keys())

                if f.target_version:
                    target_servers = [sid for sid in target_servers if fleet.get_server(sid) and fleet.get_server(sid).installed_version == f.target_version]

                for sid in target_servers:
                    deltas[sid]["cpu_saturation_delta"] += f.severity
                    deltas[sid]["active_fault_ids"].append(f.fault_id)
                    affected_servers.add(sid)

            # 5. Release Faults (Process Memory Leak, Error Regression, Release Latency Regression)
            elif f.fault_type.category == FaultCategory.RELEASE:
                # Rule: ONLY affects exposed instances of target_version and optional susceptible class
                target_version = f.target_version
                susceptible_class = f.susceptible_class_id
                explicit_targets = f.parameters.get("target_server_ids")

                for srv in fleet.list_servers():
                    sid = srv.server_id

                    # Check version exposure & susceptibility
                    is_exposed = (srv.installed_version == target_version)
                    if not is_exposed:
                        # Pre-exposure or control host: MUST NOT be affected!
                        continue

                    if susceptible_class is not None and srv.class_id != susceptible_class:
                        continue

                    if explicit_targets is not None and sid not in explicit_targets:
                        continue

                    # Server is a matching exposed canary: apply release fault
                    affected_servers.add(sid)
                    deltas[sid]["active_fault_ids"].append(f.fault_id)

                    if f.fault_type == FaultType.PROCESS_MEMORY_LEAK:
                        # Memory leak adds incremental MB per tick
                        rate_mb = f.severity  # MB per tick
                        current_leak = self._server_memory_leaks_mb.get(sid, 0.0) + rate_mb
                        self._server_memory_leaks_mb[sid] = current_leak
                        deltas[sid]["memory_leak_mb"] = current_leak

                    elif f.fault_type == FaultType.ERROR_REGRESSION:
                        deltas[sid]["error_rate_delta"] += f.severity

                    elif f.fault_type == FaultType.RELEASE_LATENCY_REGRESSION:
                        deltas[sid]["latency_log_delta"] += f.severity

        # ---------------- Resource Pressure & Simulated OOM Coupling ----------------
        for srv in fleet.list_servers():
            sid = srv.server_id
            leak_mb = deltas[sid]["memory_leak_mb"]

            if leak_mb > 0.0 and not deltas[sid]["is_outage"]:
                cap_mb = srv.memory_capacity_mb
                total_mem = srv.base_memory_mb + leak_mb

                # Zone 2: Pressure Zone (70% - 90% capacity) -> GC CPU rise + slight latency jitter
                if 0.70 * cap_mb <= total_mem < 0.90 * cap_mb:
                    ratio = (total_mem - 0.70 * cap_mb) / (0.20 * cap_mb)
                    deltas[sid]["cpu_saturation_delta"] += 0.15 * ratio
                    deltas[sid]["latency_log_delta"] += 0.04 * ratio

                # Zone 3: Thrashing Zone (90% - 100% capacity) -> Severe paging latency & errors
                elif 0.90 * cap_mb <= total_mem < cap_mb:
                    ratio = (total_mem - 0.90 * cap_mb) / (0.10 * cap_mb)
                    deltas[sid]["latency_log_delta"] += 0.40 * ratio
                    deltas[sid]["cpu_saturation_delta"] += 0.30 * ratio
                    deltas[sid]["error_rate_delta"] += 0.02 * ratio

                # Zone 4: Out-Of-Memory (OOM) Crash & Restart Behavior
                elif total_mem >= cap_mb:
                    restart_dur = 2
                    # Find restart duration from active leak fault if specified
                    for f in active_faults:
                        if f.fault_type == FaultType.PROCESS_MEMORY_LEAK and sid in affected_servers:
                            restart_dur = f.restart_duration

                    resume_tick = tick + restart_dur
                    self._server_restarting_until[sid] = resume_tick
                    deltas[sid]["is_outage"] = True
                    outage_servers.add(sid)
                    self.truth_store.record_oom_crash(sid, tick, resume_tick, total_mem)

        # Record truth for this tick in the EvaluatorFaultTruthStore
        truth_deltas: dict[str, dict[str, float]] = {}
        for sid, d in deltas.items():
            truth_deltas[sid] = {
                "latency_log_delta": round(float(d["latency_log_delta"]), 4),
                "memory_leak_mb": round(float(d["memory_leak_mb"]), 2),
                "cpu_saturation_delta": round(float(d["cpu_saturation_delta"]), 4),
                "error_rate_delta": round(float(d["error_rate_delta"]), 4),
                "fleet_demand_delta": round(float(d["fleet_demand_delta"]), 4),
            }

        tick_truth = TickFaultTruth(
            tick=tick,
            active_fault_ids=active_fault_ids,
            affected_server_ids=sorted(affected_servers),
            outage_server_ids=sorted(outage_servers),
            oom_restarting_server_ids=sorted(restarting_servers),
            server_truth_deltas=truth_deltas,
        )
        self.truth_store.record_tick_truth(tick_truth)

        return deltas
