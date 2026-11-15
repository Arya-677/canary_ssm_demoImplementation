"""Healthy Telemetry Generation Engine for the Virtual Data Center.

Generates realistic multi-metric telemetry for simulated datacenter servers:
- Request counts, CPU utilization, process memory, log latency, and error counts.
- Fleet-wide demand changes, rack-shared variation, hardware differences, and request volume effects.
- Strict bounds: CPU in [0.0, 1.0], latency > 0, error_count in [0, request_count], memory <= capacity.
- Measurement uncertainty scaled inversely with request volume.
- Latency statistic represents the estimated geometric mean response time in ms over the 1-minute window.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from canary_ssm.telemetry import TelemetryRecord
from .models import Fleet, Rack, Server, ServerResourceState


@dataclass
class HealthyTelemetryConfig:
    """Parameters governing healthy multi-metric dynamics and temporal noise."""
    # Fleet workload demand
    phi_workload: float = 0.95
    sd_workload: float = 0.03
    diurnal_amplitude: float = 0.10
    diurnal_period_ticks: int = 1440
    # Fleet shared factor
    phi_factor: float = 0.80
    sd_factor: float = 0.010
    # Rack shared nuisance
    phi_rack: float = 0.70
    sd_rack: float = 0.008
    # Host temporal AR(1) latency noise
    phi_noise: float = 0.60
    sd_noise: float = 0.010
    sd_meas_base: float = 0.005
    # Host memory dynamics (MB)
    phi_mem_noise: float = 0.80
    sd_mem_noise: float = 20.0
    mem_workload_scale: float = 150.0     # MB increase per unit log-workload
    # Garbage Collection (GC) and Allocator Warmup Dynamics (MB)
    gc_period_ticks: int = 15             # GC collection cycle period in minutes
    gc_amplitude_mb: float = 0.0          # Peak temporary allocation within cycle before sweep
    warmup_ticks: int = 15                # Allocator initial heap warmup duration in minutes
    warmup_amplitude_mb: float = 0.0      # Warmup growth from cold startup to steady working set
    # Traffic and request volume
    nominal_requests: int = 6000
    base_error_prob: float = 0.0005       # 5 errors per 10,000 requests
    # Class offsets
    class_latency_offsets: tuple[float, ...] = (0.0, 0.08)
    class_memory_offsets_mb: tuple[float, ...] = (0.0, 1024.0)


class HealthyTelemetryEngine:
    """Generates observable telemetry records from physical and resource response functions."""

    def __init__(
        self,
        config: HealthyTelemetryConfig | None = None,
        seed: int = 42,
    ) -> None:
        self.cfg = config or HealthyTelemetryConfig()
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)

        # Dynamic state variables
        self.current_workload_x: float = 0.0
        self.current_factor_f: float = 0.0
        self.rack_nuisances: dict[str, float] = {}
        self.host_latency_ar: dict[str, float] = {}
        self.host_mem_ar: dict[str, float] = {}
        self.host_uptime_ticks: dict[str, int] = {}

        # Shared offsets for controllable experiments
        self.fleet_workload_offset: float = 0.0
        self.rack_offsets: dict[str, float] = {}

    def set_fleet_workload_offset(self, offset: float) -> None:
        """Apply a shared external workload demand shift across the entire fleet."""
        self.fleet_workload_offset = float(offset)

    def set_rack_offset(self, rack_id: str, offset: float) -> None:
        """Apply a shared nuisance or load shift to a specific rack."""
        self.rack_offsets[str(rack_id)] = float(offset)

    def reset(self, seed: int | None = None) -> None:
        """Reset internal noise states and RNG for deterministic replay."""
        active_seed = self.seed if seed is None else int(seed)
        self.rng = np.random.default_rng(active_seed)
        self.current_workload_x = 0.0
        self.current_factor_f = 0.0
        self.rack_nuisances.clear()
        self.host_latency_ar.clear()
        self.host_mem_ar.clear()
        self.host_uptime_ticks.clear()
        self.fleet_workload_offset = 0.0
        self.rack_offsets.clear()

    def generate_tick_telemetry(
        self,
        fleet: Fleet,
        tick: int,
        run_id: str = "run-default",
        fault_deltas: dict[str, dict[str, Any]] | None = None,
    ) -> list[TelemetryRecord]:
        """Generate multi-metric observations for all servers in the fleet at discrete tick."""
        cfg = self.cfg

        # Extract fleet-wide demand delta from faults if present
        fleet_demand_delta = 0.0
        if fault_deltas:
            first_val = next(iter(fault_deltas.values()), None)
            if first_val:
                fleet_demand_delta = float(first_val.get("fleet_demand_delta", 0.0))

        # 1. Update fleet-wide workload demand x_t
        w_innov = self.rng.normal(0.0, cfg.sd_workload)
        diurnal = cfg.diurnal_amplitude * math.sin(2.0 * math.pi * tick / float(cfg.diurnal_period_ticks))
        self.current_workload_x = cfg.phi_workload * self.current_workload_x + w_innov
        x_t = self.current_workload_x + diurnal + self.fleet_workload_offset + fleet_demand_delta

        # 2. Update fleet common factor f_t
        f_innov = self.rng.normal(0.0, cfg.sd_factor)
        self.current_factor_f = cfg.phi_factor * self.current_factor_f + f_innov
        f_t = self.current_factor_f

        records: list[TelemetryRecord] = []

        # 3. Process each rack and server
        for rack in fleet.list_racks():
            rid = rack.rack_id
            # Update rack shared nuisance gamma_j(t)
            prev_rack_gamma = self.rack_nuisances.get(rid, 0.0)
            rack_innov = self.rng.normal(0.0, cfg.sd_rack)
            rack_offset = self.rack_offsets.get(rid, 0.0)
            self.rack_nuisances[rid] = cfg.phi_rack * prev_rack_gamma + rack_innov
            rack_gamma = self.rack_nuisances[rid] + rack_offset

            for srv in rack.servers.values():
                sid = srv.server_id
                cid = srv.class_id
                fd = fault_deltas.get(sid, {}) if fault_deltas else {}
                is_outage = fd.get("is_outage", False) or (not srv.online) or (not rack.online)

                # If server or rack is offline or in outage, emit offline record
                if is_outage:
                    self.host_uptime_ticks[sid] = 0
                    srv.current_state = ServerResourceState(
                        workload_demand=x_t,
                        request_count=0,
                        cpu_fraction=0.0,
                        memory_mb=srv.base_memory_mb,
                        latency_ms=srv.base_latency_ms,
                        log_latency=math.log(srv.base_latency_ms),
                        error_count=0,
                        noise_ar=0.0,
                        mem_noise_ar=0.0,
                        observed=False,
                    )
                    records.append(
                        TelemetryRecord(
                            run_id=run_id,
                            tick=tick,
                            event_time=tick,
                            arrival_time=tick,
                            server_id=sid,
                            rack_id=rid,
                            class_id=cid,
                            version=srv.installed_version,
                            exposure=(srv.installed_version != "v1.0.0-baseline"),
                            request_count=0,
                            latency_ms=srv.base_latency_ms,
                            memory_mb=srv.base_memory_mb,
                            cpu_fraction=0.0,
                            error_count=0,
                            observed=False,
                        )
                    )
                    continue

                # ---------------- Healthy + Fault Response Dynamics ----------------
                # Hardware class offsets
                cls_lat_offset = cfg.class_latency_offsets[cid % len(cfg.class_latency_offsets)]
                cls_mem_offset = cfg.class_memory_offsets_mb[cid % len(cfg.class_memory_offsets_mb)]

                # A. Request Volume (N_it)
                # Driven by fleet demand x_t and rack traffic jitter
                capacity_scale = float(srv.cpu_cores) / 16.0
                mean_requests = cfg.nominal_requests * math.exp(x_t + 0.2 * rack_gamma) * capacity_scale
                req_noise = self.rng.normal(0.0, math.sqrt(max(1.0, mean_requests)))
                req_count = max(0, int(round(mean_requests + req_noise)))

                # B. CPU Utilization (cpu_fraction in [0.0, 1.0])
                base_cpu = 0.15 + 0.03 * cid
                load_ratio = float(req_count) / max(1.0, cfg.nominal_requests * 1.5)
                cpu_innov = self.rng.normal(0.0, 0.015)
                cpu_saturation_delta = float(fd.get("cpu_saturation_delta", 0.0))
                cpu_raw = base_cpu + 0.60 * load_ratio + cpu_innov + cpu_saturation_delta
                cpu_fraction = float(np.clip(cpu_raw, 0.0, 1.0))

                # C. Process Memory (memory_mb in [100.0, memory_capacity_mb])
                uptime = self.host_uptime_ticks.get(sid, 0) + 1
                self.host_uptime_ticks[sid] = uptime

                prev_mem_noise = self.host_mem_ar.get(sid, 0.0)
                mem_innov = self.rng.normal(0.0, cfg.sd_mem_noise)
                mem_noise = cfg.phi_mem_noise * prev_mem_noise + mem_innov
                self.host_mem_ar[sid] = mem_noise

                # GC cycle temporary allocation (periodic sawtooth)
                gc_alloc = 0.0
                if cfg.gc_amplitude_mb > 0.0 and cfg.gc_period_ticks > 0:
                    phase = float(tick % cfg.gc_period_ticks) / float(cfg.gc_period_ticks)
                    gc_alloc = cfg.gc_amplitude_mb * phase

                # Allocator warmup ramp post-startup / post-restart
                warmup_alloc = 0.0
                if cfg.warmup_amplitude_mb > 0.0 and cfg.warmup_ticks > 0:
                    warmup_alloc = cfg.warmup_amplitude_mb * (1.0 - math.exp(-float(uptime) / max(1.0, float(cfg.warmup_ticks) / 3.0)))

                base_mem = srv.base_memory_mb + cls_mem_offset
                workload_mem = cfg.mem_workload_scale * max(0.0, x_t) * (float(req_count) / float(cfg.nominal_requests))
                memory_leak_mb = float(fd.get("memory_leak_mb", 0.0))
                mem_raw = base_mem + warmup_alloc + workload_mem + gc_alloc + mem_noise + memory_leak_mb
                memory_mb = float(np.clip(mem_raw, 100.0, srv.memory_capacity_mb))

                # D. Latency Response (latency_ms strictly > 0, log units)
                prev_lat_noise = self.host_latency_ar.get(sid, 0.0)
                lat_innov = self.rng.normal(0.0, cfg.sd_noise)
                lat_noise = cfg.phi_noise * prev_lat_noise + lat_innov
                self.host_latency_ar[sid] = lat_noise

                # Queuing expansion under high request volume
                queue_factor = 0.05 * max(0.0, (req_count - cfg.nominal_requests) / float(cfg.nominal_requests))

                # Measurement uncertainty from low request volume:
                # Lower request count -> higher variance on estimated geometric mean
                rel_volume = max(1.0, req_count) / float(cfg.nominal_requests)
                meas_sd = cfg.sd_meas_base / math.sqrt(rel_volume)
                meas_noise = self.rng.normal(0.0, meas_sd)

                # Fault latency delta (e.g. rack network latency or release regression)
                latency_log_delta = float(fd.get("latency_log_delta", 0.0))

                # Log-latency decomposition:
                # y_it = mu_i + class_offset + beta_i * x_t + lambda_i * f_t + gamma_j(t) + e_it + queue + nu_it + delta
                mu_i = math.log(srv.base_latency_ms) + cls_lat_offset
                y_it = (
                    mu_i
                    + srv.workload_elasticity * x_t
                    + srv.factor_loading * f_t
                    + rack_gamma
                    + lat_noise
                    + queue_factor
                    + meas_noise
                    + latency_log_delta
                )
                latency_ms = float(math.exp(y_it))

                # E. Error Count (integer in [0, req_count])
                # In healthy state, tiny error probability with slight increase under high CPU
                error_rate_delta = float(fd.get("error_rate_delta", 0.0))
                p_err = cfg.base_error_prob + error_rate_delta
                if cpu_fraction > 0.85:
                    p_err += 0.002 * (cpu_fraction - 0.85) / 0.15

                if req_count > 0:
                    err_count = int(self.rng.binomial(req_count, min(1.0, max(0.0, p_err))))
                else:
                    err_count = 0
                err_count = max(0, min(req_count, err_count))

                # Exposure flag: derived strictly from installed version / deployment metadata
                exposure = (srv.installed_version != "v1.0.0-baseline")

                # Update server's numerical state
                srv.current_state = ServerResourceState(
                    workload_demand=x_t,
                    request_count=req_count,
                    cpu_fraction=cpu_fraction,
                    memory_mb=memory_mb,
                    latency_ms=latency_ms,
                    log_latency=y_it,
                    error_count=err_count,
                    noise_ar=lat_noise,
                    mem_noise_ar=mem_noise,
                    observed=True,
                )

                # Emit TelemetryRecord (Firewall: NO fault_type or injected_severity!)
                rec = TelemetryRecord(
                    run_id=run_id,
                    tick=tick,
                    event_time=tick,
                    arrival_time=tick,
                    server_id=sid,
                    rack_id=rid,
                    class_id=cid,
                    version=srv.installed_version,
                    exposure=exposure,
                    request_count=req_count,
                    latency_ms=latency_ms,
                    memory_mb=memory_mb,
                    cpu_fraction=cpu_fraction,
                    error_count=err_count,
                    observed=True,
                )
                records.append(rec)

        return records
