"""Bounded discrete-time request/resource model; equations in docs/resources.md."""
from __future__ import annotations

import copy
import csv
import math
import hashlib
import numpy as np
from collections import deque
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .topology import HostLifecycle, Topology
from .resource_health import ResourceHealthPolicy


def _finite(value, name, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")


def _bounded_int(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [1, {maximum}]")


@dataclass(frozen=True)
class ServiceWorkload:
    service_id: str
    arrival_rate_rps: float
    work_core_seconds: float = 0.05
    queue_limit: int = 300
    baseline_memory_mb: float = 128.0
    temporary_mb_per_request: float = 2.0
    initial_retained_memory_mb: float = 0.0

    def __post_init__(self):
        if not isinstance(self.service_id, str) or not self.service_id.strip():
            raise ValueError("service_id must be a nonempty string")
        _finite(self.arrival_rate_rps, "arrival_rate_rps")
        _finite(self.work_core_seconds, "work_core_seconds", True)
        if not 1e-6 <= self.work_core_seconds <= 1e6:
            raise ValueError("work_core_seconds must be in [1e-6, 1e6]")
        _bounded_int(self.queue_limit, "queue_limit", 10000)
        for n in ("baseline_memory_mb", "temporary_mb_per_request", "initial_retained_memory_mb"):
            _finite(getattr(self, n), n)


@dataclass(frozen=True)
class TrafficLevel:
    start_tick: int
    multiplier: float

    def __post_init__(self):
        _bounded_int(self.start_tick, "start_tick", 1000000000)
        _finite(self.multiplier, "multiplier")
        if self.multiplier > 1e6:
            raise ValueError("traffic multiplier must be <= 1e6")


@dataclass(frozen=True)
class ResourceConfig:
    services: tuple[ServiceWorkload, ...]
    traffic: tuple[TrafficLevel, ...] = ()
    shared_jitter: float = 0.1
    host_baseline_memory_mb: float = 256.0
    max_arrivals_per_service_tick: int = 100000
    trace_max_rows: int = 20000
    paired_exogenous: bool = False
    health_policy: ResourceHealthPolicy = ResourceHealthPolicy()

    def __post_init__(self):
        if not isinstance(self.services, (tuple, list)) or not self.services:
            raise ValueError("resources.services must be a nonempty sequence")
        if not isinstance(self.traffic, (tuple, list)):
            raise ValueError("resources.traffic must be a sequence")
        object.__setattr__(self, "services", tuple(self.services))
        object.__setattr__(self, "traffic", tuple(self.traffic))
        if any(not isinstance(s, ServiceWorkload) for s in self.services):
            raise ValueError("services must contain ServiceWorkload records")
        if len({s.service_id for s in self.services}) != len(self.services):
            raise ValueError("duplicate service_id")
        if any(not isinstance(t, TrafficLevel) for t in self.traffic):
            raise ValueError("traffic must contain TrafficLevel records")
        if list(self.traffic) != sorted(self.traffic, key=lambda t: t.start_tick) or len({t.start_tick for t in self.traffic}) != len(self.traffic):
            raise ValueError("traffic start ticks must be unique and increasing")
        _finite(self.shared_jitter, "shared_jitter")
        if self.shared_jitter > 1:
            raise ValueError("shared_jitter must be <= 1")
        _finite(self.host_baseline_memory_mb, "host_baseline_memory_mb")
        _bounded_int(self.max_arrivals_per_service_tick, "max_arrivals_per_service_tick", 1000000)
        _bounded_int(self.trace_max_rows, "trace_max_rows", 1000000)
        if not isinstance(self.health_policy,ResourceHealthPolicy):raise ValueError('Invalid health_policy')
        if type(self.paired_exogenous) is not bool:
            raise ValueError("paired_exogenous must be boolean")

    def to_dict(self):
        d = asdict(self)
        d["services"] = list(d["services"])
        d["traffic"] = list(d["traffic"])
        return d

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("services"), list):
            raise ValueError("resources requires a services list")
        value = dict(value)
        try:
            value["services"] = tuple(ServiceWorkload(**s) for s in value["services"])
            value["traffic"] = tuple(TrafficLevel(**t) for t in value.get("traffic", []))
            value["health_policy"]=ResourceHealthPolicy(**value.get("health_policy",{}))
            return cls(**value)
        except TypeError as exc:
            raise ValueError(f"invalid resource configuration: {exc}") from exc


def fair_work(demand: dict[str, float], budget: float) -> dict[str, float]:
    """Water-fill a host's core-seconds equally among nonempty replica queues."""
    allocation = dict.fromkeys(demand, 0.0)
    pending = sorted(k for k, v in demand.items() if v > 0)
    while pending and budget > 0:
        share = budget / len(pending)
        satisfied = [k for k in pending if demand[k] - allocation[k] <= share]
        if not satisfied:
            for k in pending:
                allocation[k] += share
            break
        for k in satisfied:
            used = demand[k] - allocation[k]
            allocation[k] += used
            budget = max(0.0, budget - used)
        pending = [k for k in pending if k not in satisfied]
    return allocation


class ResourceModel:
    """State owned by the existing engine, never a second clock or simulator loop."""

    def __init__(self, config: ResourceConfig, world: Topology, tick_seconds: int, release_seed=0):
        self.config, self.dt = config, tick_seconds
        self.fixed_routes = {}
        self.host_capacities={h.host_id:h.capacity.memory_mb for h in world.hosts}
        self.services = {s.service_id: s for s in config.services}
        self.replicas = {r.replica_id: r for r in sorted(world.replicas, key=lambda r: r.replica_id)}
        if any(r.service_id not in self.services for r in self.replicas.values()):
            raise ValueError("every placed replica requires a resource service configuration")
        maximum = max([1.0, *(t.multiplier for t in config.traffic)])
        if any(s.arrival_rate_rps * tick_seconds * maximum * (1 + config.shared_jitter) > 1e9 for s in config.services):
            raise ValueError("arrival expectation exceeds bounded sampler limit (1e9 per tick)")
        self.host_replicas = {h.host_id: [r for r in self.replicas.values() if r.host_id == h.host_id] for h in world.hosts}
        self.baseline = {h.host_id: h.usage.memory_mb + config.host_baseline_memory_mb + sum(
            self.services[r.service_id].baseline_memory_mb for r in self.host_replicas[h.host_id]) for h in world.hosts}
        self.retained = {r.replica_id: self.services[r.service_id].initial_retained_memory_mb for r in self.replicas.values()}
        self.platform_memory = dict.fromkeys(self.host_replicas, 0.0)
        for h in world.hosts:
            if self.reserved_memory(h.host_id) > h.capacity.memory_mb:
                raise ValueError(f"host {h.host_id}: baseline plus retained memory exceeds capacity")
        self.queues = {r: deque() for r in self.replicas}  # (arrival tick, integer count)
        self.queued = dict.fromkeys(self.replicas, 0)
        self.progress = dict.fromkeys(self.replicas, 0.0)   # core-seconds on head request
        self.host_trace = deque(maxlen=config.trace_max_rows)
        self.service_trace = deque(maxlen=config.trace_max_rows)
        self.trace_rows_evicted = {"host": 0, "service": 0}
        self.last_hosts, self.last_services = [], []
        self.profiles = {rid: self.services[r.service_id] for rid, r in self.replicas.items()}
        self.retention_rates = dict.fromkeys(self.replicas, 0.0)
        self.memory_models = dict.fromkeys(self.replicas,'legacy-bounded-v1')
        self.background_rates = dict.fromkeys(self.replicas,0.)
        self.retained_limits = dict.fromkeys(self.replicas,None)
        self.process_states = dict.fromkeys(self.replicas,'RUNNING')
        self.process_generations = dict.fromkeys(self.replicas,0)
        self.process_restarts = dict.fromkeys(self.replicas,0)
        self.oom_counts = dict.fromkeys(self.replicas,0)
        self.process_events = deque(maxlen=config.trace_max_rows)
        self.process_events_evicted=0
        self.current_tick=0
        self.error_probabilities = dict.fromkeys(self.replicas,0.0)
        self.response_delays_ms = dict.fromkeys(self.replicas,0.0)
        self.pending_responses = {rid:deque() for rid in self.replicas}
        self.pending_count = dict.fromkeys(self.replicas,0)
        self.release_seed = release_seed
        self.cpu_factors = dict.fromkeys(self.host_replicas, 1.0)
        self.network_factors = dict.fromkeys(self.host_replicas, 1.0)
        self.unavailable_hosts = set()
        self.demand_multiplier = 1.0
        self.restart_drops = dict.fromkeys(self.replicas, 0)
        self.completed_batches = []
        self.routed_by_replica = dict.fromkeys(self.replicas, 0)
        self.exogenous_trace = deque(maxlen=config.trace_max_rows)

    def configure_behavior(self,rid,behavior):
        """Update future work/allocation parameters; do not reclaim allocations."""
        base=self.services[self.replicas[rid].service_id]
        self.profiles[rid]=replace(base,work_core_seconds=base.work_core_seconds*behavior.work_multiplier)
        self.retention_rates[rid]=behavior.retained_mb_per_request if behavior.memory_model=='process-memory-v1' else behavior.retained_mb_per_completion
        self.memory_models[rid]=behavior.memory_model
        self.background_rates[rid]=behavior.background_mb_per_second
        self.retained_limits[rid]=behavior.retained_limit_mb
        self.error_probabilities[rid]=behavior.error_probability
        self.response_delays_ms[rid]=behavior.response_delay_ms

    def _process_event(self,rid,kind,reason,tick,reclaimed_mb,dropped):
        sequence=self.process_events_evicted+len(self.process_events)
        if len(self.process_events)==self.process_events.maxlen:self.process_events_evicted+=1
        self.process_events.append({'sequence':sequence,'tick':tick,'replica_id':rid,
            'host_id':self.replicas[rid].host_id,'kind':kind,'reason':reason,
            'generation':self.process_generations[rid],'reclaimed_retained_mb':reclaimed_mb,'dropped_requests':dropped})

    def restart(self, rid, *, reason='process_restart', tick=None):
        dropped=self.queued[rid]+self.pending_count[rid]
        reclaimed=self.retained[rid]
        self.process_generations[rid]+=1;self.process_restarts[rid]+=1;self.process_states[rid]='RUNNING'
        self._process_event(rid,'RESTART',reason,self.current_tick if tick is None else tick,reclaimed,dropped)
        self.restart_drops[rid] += dropped
        self.pending_responses[rid].clear();self.pending_count[rid]=0
        self.queued[rid] = 0
        self.progress[rid] = 0.0
        self.queues[rid].clear()
        initial=self.services[self.replicas[rid].service_id].initial_retained_memory_mb
        self.retained[rid]=0.
        hid=self.replicas[rid].host_id
        if initial>max(0.,self.host_capacities[hid]-self.reserved_memory(hid)-self.temporary_memory(hid))+1e-9:
            self.process_states[rid]='OOM';self.oom_counts[rid]+=1
            self._process_event(rid,'OOM','restart_initial_allocation_failed',self.current_tick if tick is None else tick,0.,0)
        else:self.retained[rid]=initial

    def reserved_memory(self, host_id):
        return self.baseline[host_id] + self.platform_memory[host_id] + sum(self.retained[r.replica_id] for r in self.host_replicas[host_id])

    def temporary_memory(self, host_id):
        return sum((self.queued[r.replica_id]+self.pending_count[r.replica_id]) * self.profiles[r.replica_id].temporary_mb_per_request
                   for r in self.host_replicas[host_id])

    def initial_world(self, world):
        return replace(world, hosts=tuple(replace(h, usage=replace(h.usage, cpu_cores=0.0,
            memory_mb=self.reserved_memory(h.host_id))) for h in world.hosts))

    def route(self, world, tick, rng, routing_rng=None):
        if self.config.paired_exogenous and routing_rng is None:
            raise ValueError("paired_exogenous requires a separate routing stream")
        self.current_tick=tick
        self.routed_by_replica = dict.fromkeys(self.replicas, 0)
        multiplier = 1.0
        for level in self.config.traffic:
            if level.start_tick <= tick:
                multiplier = level.multiplier
        shared_uniform = float(rng.random())
        factor = multiplier * self.demand_multiplier * (1 + self.config.shared_jitter * (2 * shared_uniform - 1))
        arrival_uniforms = {}
        hosts = {h.host_id: h for h in world.hosts}
        self._host_counts = {h.host_id: {"queue_start": sum(self.queued[r.replica_id]+self.pending_count[r.replica_id]+self.restart_drops[r.replica_id] for r in self.host_replicas[h.host_id]),
            "routed_requests": 0, "accepted": 0, "dropped_queue": 0, "dropped_memory": 0,
            "dropped_restart": sum(self.restart_drops[r.replica_id] for r in self.host_replicas[h.host_id]),
            "dropped_oom": 0, "dropped_unavailable_routes": 0, "dropped_unavailable_queued": 0, "completed": 0,"processed":0,"errors":0,"succeeded":0,"processed":0,"errors":0,"succeeded":0} for h in world.hosts}
        self._service_counts = {}
        for sid, service in sorted(self.services.items()):
            if self.config.paired_exogenous:
                from scipy.stats import poisson
                arrival_uniforms[sid] = float(rng.random())
                raw = 0 if arrival_uniforms[sid] == 0 else int(poisson.ppf(arrival_uniforms[sid],service.arrival_rate_rps * self.dt * factor))
            else:
                raw = int(rng.poisson(service.arrival_rate_rps * self.dt * factor))
            arrivals = min(raw, self.config.max_arrivals_per_service_tick)
            row = {"service_id": sid, "shared_traffic_factor": factor, "arrivals": raw,
                   "dropped_oom": 0, "canary_requested": 0, "control_requested": 0, "routing_rollout_id": None,
                   "dropped_arrival_limit": raw - arrivals, "dropped_unavailable_routes": 0,
                   "accepted": 0, "dropped_queue": 0, "dropped_memory": 0,
                   "dropped_unavailable_queued": 0, "completed": 0,"processed":0,"errors":0,"succeeded":0,
                   "dropped_restart": sum(self.restart_drops[r.replica_id] for r in self.replicas.values() if r.service_id == sid),
                   "queue_start": sum(self.queued[r.replica_id]+self.pending_count[r.replica_id]+self.restart_drops[r.replica_id] for r in self.replicas.values() if r.service_id == sid)}
            eligible = [r for r in self.replicas.values() if r.service_id == sid and hosts[r.host_id].lifecycle == HostLifecycle.READY and r.host_id not in self.unavailable_hosts and self.process_states[r.replica_id]=='RUNNING']
            fixed = self.fixed_routes.get(sid)
            weights = None
            if fixed:
                eligible = [r for r in self.replicas.values() if r.service_id == sid and r.host_id in fixed['canary_hosts'] + fixed['control_hosts']]
                weights = [fixed['canary_fraction']/len(fixed['canary_hosts']) if r.host_id in fixed['canary_hosts'] else (1-fixed['canary_fraction'])/len(fixed['control_hosts']) for r in eligible]
                row['routing_rollout_id'] = fixed['rollout_id']
            if not eligible:
                row["dropped_unavailable_routes"] = arrivals
            else:
                counts = (routing_rng if self.config.paired_exogenous else rng).multinomial(arrivals, weights if weights is not None else [1 / len(eligible)] * len(eligible))
                for replica, count in zip(eligible, counts):
                    count = int(count)
                    rid, hid = replica.replica_id, replica.host_id
                    self.routed_by_replica[rid] = count
                    service = self.profiles[rid]
                    stats = self._host_counts[hid]
                    stats["routed_requests"] += count
                    if fixed:
                        row['canary_requested' if hid in fixed['canary_hosts'] else 'control_requested'] += count
                        if hosts[hid].lifecycle != HostLifecycle.READY or hid in self.unavailable_hosts or self.process_states[rid]!='RUNNING':
                            row['dropped_unavailable_routes'] += count
                            stats['dropped_unavailable_routes'] += count
                            continue
                    queue_fit = min(count, service.queue_limit - self.queued[rid] - self.pending_count[rid])
                    free = max(0.0, hosts[hid].capacity.memory_mb - self.reserved_memory(hid) - self.temporary_memory(hid))
                    memory_fit = queue_fit if queue_fit * service.temporary_mb_per_request <= free else min(queue_fit, int(free / service.temporary_mb_per_request))
                    stats["dropped_queue"] += count - queue_fit
                    stats["dropped_memory"] += queue_fit - memory_fit
                    stats["accepted"] += memory_fit
                    row["dropped_queue"] += count - queue_fit
                    row["dropped_memory"] += queue_fit - memory_fit
                    row["accepted"] += memory_fit
                    if memory_fit:
                        self.queues[rid].append((tick, memory_fit))
                        self.queued[rid] += memory_fit
            self._service_counts[sid] = row
        self.restart_drops = dict.fromkeys(self.replicas, 0)
        self._peak = {h.host_id: self.reserved_memory(h.host_id) + self.temporary_memory(h.host_id) for h in world.hosts}
        if self.config.paired_exogenous:
            self.exogenous_trace.append({"tick":tick,"shared_traffic_uniform":shared_uniform,
                                         "arrival_uniforms":arrival_uniforms})
        return {"adapter": "bounded-fifo-core-seconds-v1", "shared_traffic_factor": factor,
                "services": copy.deepcopy(list(self._service_counts.values()))}

    def _consume(self, rid, work, tick):
        service = self.profiles[rid]
        total = self.progress[rid] + work
        completed = min(self.queued[rid], int(math.floor(total / service.work_core_seconds + 1e-10)))
        self.progress[rid] = max(0.0, total - completed * service.work_core_seconds) if completed < self.queued[rid] else 0.0
        self.queued[rid] -= completed
        remaining = completed
        while remaining:
            at, count = self.queues[rid].popleft()
            batch_count=min(count,remaining)
            delay=int(math.ceil(self.response_delays_ms[rid]/(self.dt*1000)))
            if delay:
                self.pending_responses[rid].append((tick+delay,at,batch_count,self.error_probabilities[rid]))
                self.pending_count[rid]+=batch_count
            else:self._emit_response(rid,at,batch_count,tick,self.error_probabilities[rid])
            if count > remaining:
                self.queues[rid].appendleft((at, count - remaining))
            remaining -= min(count, remaining)
        return completed

    def _emit_response(self,rid,arrival_tick,count,tick,probability):
        errors=0
        if probability:
            identity=int.from_bytes(hashlib.sha256(rid.encode()).digest()[:4],'little')
            rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.release_seed,991,identity,tick,arrival_tick,count])))
            errors=int(rng.binomial(count,probability))
        self.completed_batches.append({'replica_id':rid,'request_count':count,'latency_ms':(tick-arrival_tick+1)*self.dt*1000,'error_count':errors})

    def update(self, world, tick):
        self.completed_batches = []
        updated, self.last_hosts = [], []
        for host in world.hosts:
            hid = host.host_id
            stats = self._host_counts[hid]
            batch_offset=len(self.completed_batches)
            replicas = self.host_replicas[hid]
            available = host.lifecycle == HostLifecycle.READY and hid not in self.unavailable_hosts
            if not available:
                for r in replicas:
                    dropped = self.queued[r.replica_id]+self.pending_count[r.replica_id]
                    self.pending_responses[r.replica_id].clear();self.pending_count[r.replica_id]=0
                    self._service_counts[r.service_id]["dropped_unavailable_queued"] += dropped
                    stats["dropped_unavailable_queued"] += dropped
                    self.queued[r.replica_id] = 0
                    self.progress[r.replica_id] = 0.0
                    self.queues[r.replica_id].clear()
            if available:
                for r in replicas:
                    pending=self.pending_responses[r.replica_id]
                    while pending and pending[0][0]<=tick:
                        due,arrival,count,probability=pending.popleft();self.pending_count[r.replica_id]-=count
                        self._emit_response(r.replica_id,arrival,count,tick,probability)
            demand = {r.replica_id: max(0.0, self.queued[r.replica_id] * self.profiles[r.replica_id].work_core_seconds - self.progress[r.replica_id]) for r in replicas if self.process_states[r.replica_id]=='RUNNING'}
            occupancy = (self.reserved_memory(hid)+self.temporary_memory(hid))/host.capacity.memory_mb
            pressure_factor = max(0.1, 1-4*max(0.0, occupancy-0.8)) if self.platform_memory[hid] or any(self.retention_rates[r.replica_id] or self.retained[r.replica_id] or self.memory_models[r.replica_id]=='process-memory-v1' for r in replicas) else 1.0
            effective_cores = host.capacity.cpu_cores * self.cpu_factors[hid] * pressure_factor
            allocation = {r.replica_id:0. for r in replicas} | fair_work(demand, effective_cores * self.dt if available else 0.0)
            network_capacity = host.capacity.network_mbps * self.network_factors[hid]
            # 0.064 decimal MB per request-equivalent, transferred with its CPU work.
            network_requests = fair_work({r.replica_id: allocation[r.replica_id]/self.profiles[r.replica_id].work_core_seconds for r in replicas}, network_capacity*self.dt/(8*0.064) if available else 0.0)
            allocation = {r.replica_id: min(allocation[r.replica_id], network_requests[r.replica_id]*self.profiles[r.replica_id].work_core_seconds) for r in replicas}
            network_used = min(network_capacity, sum(network_requests.values())*8*0.064/self.dt)
            completed_by_replica = {}
            for r in replicas:
                done = self._consume(r.replica_id, allocation[r.replica_id], tick)
                stats["processed"] += done
                self._service_counts[r.service_id]["processed"] += done
                completed_by_replica[r.replica_id] = done
            for batch in self.completed_batches[batch_offset:]:
                sid=self.replicas[batch['replica_id']].service_id
                for counts in (stats,self._service_counts[sid]):
                    counts['completed']+=batch['request_count'];counts['errors']+=batch['error_count']
                    counts['succeeded']+=batch['request_count']-batch['error_count']
            temporary = self.temporary_memory(hid)
            blocked_retention = 0.0
            request_added=background_added=0.
            for r in replicas:
                rid=r.replica_id
                if self.process_states[rid]!='RUNNING':continue
                request_gain=completed_by_replica[rid]*self.retention_rates[rid]
                background_gain=self.background_rates[rid]*self.dt if available else 0.
                limit=self.retained_limits[rid]
                room=math.inf if limit is None else max(0.,limit-self.retained[rid])
                request_gain=min(request_gain,room);background_gain=min(background_gain,max(0.,room-request_gain))
                gain=request_gain+background_gain
                free = max(0.0, host.capacity.memory_mb-self.reserved_memory(hid)-temporary)
                if self.memory_models[rid]=='process-memory-v1' and gain>free+1e-9:
                    dropped=self.queued[rid]+self.pending_count[rid];reclaimed=self.retained[rid]
                    stats['dropped_oom']+=dropped;self._service_counts[r.service_id]['dropped_oom']+=dropped
                    self.queues[rid].clear();self.queued[rid]=0;self.progress[rid]=0.
                    self.pending_responses[rid].clear();self.pending_count[rid]=0
                    self.retained[rid]=0.;self.process_states[rid]='OOM';self.oom_counts[rid]+=1
                    self._process_event(rid,'OOM','retained_allocation_failed',tick,reclaimed,dropped)
                    blocked_retention+=gain
                    temporary=self.temporary_memory(hid)
                else:
                    actual=min(gain,free);self.retained[rid]+=actual
                    request_added+=min(request_gain,actual);background_added+=max(0.,actual-request_gain)
                    blocked_retention+=max(0.,gain-free)
                    self._peak[hid]=max(self._peak[hid],self.reserved_memory(hid)+temporary)
            retained = sum(self.retained[r.replica_id] for r in replicas)
            used_cores = min(host.capacity.cpu_cores, sum(allocation.values()) / self.dt)
            usage = replace(host.usage, cpu_cores=used_cores, memory_mb=self.reserved_memory(hid) + temporary, network_mbps=network_used)
            updated.append(replace(host, usage=usage))
            # Fixed equal configured replica shares for an analytical next-request proxy.
            share = effective_cores / max(1, sum(self.process_states[r.replica_id]=='RUNNING' for r in replicas))
            proxy = [1000 * (self.profiles[r.replica_id].work_core_seconds +
                max(0.0, self.queued[r.replica_id] * self.profiles[r.replica_id].work_core_seconds - self.progress[r.replica_id])) / share + 1000*8*0.064/host.capacity.network_mbps*(1/self.network_factors[hid]-1) for r in replicas if self.process_states[r.replica_id]=='RUNNING']
            row = {"tick": tick, "simulated_seconds": tick * self.dt, "host_id": hid,
                   "rack_id": host.rack_id, "class_id": host.class_id, "available": available,
                   **stats, "queue_end": sum(self.queued[r.replica_id]+self.pending_count[r.replica_id] for r in replicas),
                   "pending_response_count":sum(self.pending_count[r.replica_id] for r in replicas),
                   "cpu_cores": used_cores, "cpu_utilization": used_cores / host.capacity.cpu_cores,
                   "cpu_capacity_cores": effective_cores if available else 0.0,
                   "memory_baseline_mb": self.baseline[hid], "memory_temporary_mb": temporary,
                   "memory_retained_mb": retained, "memory_mb": usage.memory_mb,
                   "memory_platform_mb": self.platform_memory[hid], "network_mbps": network_used,
                   "network_capacity_mbps": network_capacity,
                   "memory_peak_mb": max(self._peak[hid], usage.memory_mb), "memory_capacity_mb": host.capacity.memory_mb,
                   "retention_blocked_mb": blocked_retention,
                   "memory_headroom_mb":host.capacity.memory_mb-usage.memory_mb,
                   "pressure_slowdown_factor":pressure_factor,
                   "request_retained_added_mb":request_added,"background_retained_added_mb":background_added,
                   "retained_added_mb_per_request":request_added/stats['processed'] if stats['processed'] else None,
                   "process_restart_count":sum(self.process_restarts[r.replica_id] for r in replicas),
                   "process_generation":sum(self.process_generations[r.replica_id] for r in replicas),
                   "oom_count":sum(self.oom_counts[r.replica_id] for r in replicas),
                   "process_state":', '.join(sorted(set(self.process_states[r.replica_id] for r in replicas))) or 'NO_REPLICAS',
                   "release_ids": ", ".join(sorted({self.replicas[r.replica_id].release_id for r in replicas})),
                   "sampled_latency_mean_ms":sum(b['latency_ms']*b['request_count'] for b in self.completed_batches[batch_offset:])/stats['completed'] if stats['completed'] else None,
                   "latency_proxy_ms": sum(proxy) / len(proxy) + sum(self.response_delays_ms[r.replica_id] for r in replicas if self.process_states[r.replica_id]=='RUNNING')/len(proxy) if proxy and available else None}
            self.last_hosts.append(row)
            self._append_trace("host", row)
        self.last_services = []
        for sid, stats in self._service_counts.items():
            row = {"tick": tick, "simulated_seconds": tick * self.dt, **stats,
                   "queue_end": sum(self.queued[r.replica_id]+self.pending_count[r.replica_id] for r in self.replicas.values() if r.service_id == sid),
                   "pending_response_count":sum(self.pending_count[r.replica_id] for r in self.replicas.values() if r.service_id==sid)}
            self.last_services.append(row)
            self._append_trace("service", row)
        return replace(world, hosts=tuple(updated))

    def _append_trace(self, kind, row):
        trace = self.host_trace if kind == "host" else self.service_trace
        if len(trace) == trace.maxlen:
            self.trace_rows_evicted[kind] += 1
        trace.append(copy.deepcopy(row))

    def snapshot(self):
        return {"adapter": "bounded-fifo-core-seconds-v1", "replicas": [
            {"replica_id": rid, "service_id": r.service_id, "host_id": r.host_id, "release_id": r.release_id,
             "queue": list(map(list, self.queues[rid])), "queued_requests": self.queued[rid], "pending_response_count":self.pending_count[rid],
             "process_state":self.process_states[rid],"process_generation":self.process_generations[rid],"restart_count":self.process_restarts[rid],"oom_count":self.oom_counts[rid],
             "head_progress_core_seconds": self.progress[rid], "retained_memory_mb": self.retained[rid]}
            for rid, r in self.replicas.items()], "services": copy.deepcopy(self.last_services),
            "process_events":copy.deepcopy(list(self.process_events)),"process_events_evicted":self.process_events_evicted,
            "trace_rows_evicted": dict(self.trace_rows_evicted)}

    def trace(self):
        return {"hosts": copy.deepcopy(list(self.host_trace)), "services": copy.deepcopy(list(self.service_trace)),
                "rows_evicted": dict(self.trace_rows_evicted)}

    def export_traces(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for name, rows in (("hosts", self.host_trace), ("services", self.service_trace)):
            with (directory / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
