"""Simulated releases/canaries and developer-only fault schedules. Never executes uploads."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import replace

import numpy as np

from .faults import FaultEvent, FaultKind, Recovery
from .releases import ReleaseRegistry,example_payloads,behavior_manifest
from .fault_scheduler import BackgroundFaultConfig, BackgroundFaultScheduler

PROFILES = {"healthy": {"work_multiplier": 1.0, "retained_mb_per_completion": 0.0},
            "slow": {"work_multiplier": 8.0, "retained_mb_per_completion": 0.0},
            "leak": {"work_multiplier": 1.0, "retained_mb_per_completion": 16.0}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class DemoOperations:
    def __init__(self, engine):
        self.engine = engine
        self.service_id = engine.config.resources.services[0].service_id
        self.registry = getattr(engine,'_release_registry',None) or ReleaseRegistry(engine.resource_model.services)
        engine._release_registry = self.registry
        for index,(rid,sid) in enumerate(sorted({(r.release_id,r.service_id) for r in engine.world.replicas})):
            if rid not in {r.release_id for r in self.registry.records()}:
                self.registry.register({'schema_version':1,'release_id':rid,'service_id':sid,'version':f'0.0.0-baseline-{index}',
                    'creation_metadata':{'author':'initial-world'},'behavior_manifest':{'schema_version':1,'profiles':[{'kind':'healthy'}]}},0)
            elif self.registry.get(rid).service_id!=sid:raise ValueError('Initial release_id belongs to conflicting services')
        for profile in PROFILES:
            self.registry.register({'schema_version':1,'release_id':f'sample-{profile}-v2','service_id':self.service_id,
                'version':f'0.0.0-legacy-{profile}','creation_metadata':{'author':'legacy-sample'},
                'behavior_manifest':self._legacy_manifest(profile)},0)
        for payload in example_payloads(self.service_id):self.registry.register(payload,0)
        from .releases import memory_example_payloads
        for payload in memory_example_payloads(self.service_id):self.registry.register(payload,0)
        self.pending_process_restarts=[]
        self.plans = {}
        self.deployment = {"status": "idle", "canaries": [], "controls": []}
        self.baselines = {}
        self.faults = []
        self.background = BackgroundFaultScheduler(engine.config.background_faults or BackgroundFaultConfig(),
                                                   engine.world, engine.config.tick_seconds)

    @staticmethod
    def _legacy_manifest(profile):
        b=PROFILES[profile]
        profiles=[]
        if b['work_multiplier']!=1:profiles.append({'kind':'extra_cpu_work','work_multiplier':b['work_multiplier']})
        if b['retained_mb_per_completion']:profiles.append({'kind':'retained_memory_leak','retained_mb_per_completion':b['retained_mb_per_completion']})
        return {'schema_version':1,'profiles':profiles or [{'kind':'healthy'}]}

    def _operator_record(self,record):
        row=record.to_dict()
        profile=next((p for p in PROFILES if record.release_id==f'sample-{p}-v2'),None)
        if profile is None and record.release_id.startswith('upload-'):profile=record.release_id.rsplit('-',1)[-1]
        from dataclasses import asdict
        row.update(profile=profile or 'manifest',behavior=asdict(record.behavior),source='upload' if record.attachment else 'sample' if record.creation.author in ('initial-world','legacy-sample','example-fixture') else 'manifest',
            artifact=asdict(record.attachment) if record.attachment else None)
        return row

    @property
    def releases(self):return {r.release_id:self._operator_record(r) for r in self.registry.records()}

    @property
    def attachments(self):return self.registry.source_attachments()

    def catalog(self):return [self._operator_record(r) for r in self.registry.records()]

    def preview(self, release_id, per_rack=1):
        if release_id not in self.releases:
            raise ValueError("Unknown release_id")
        if type(per_rack) is not int or not 1 <= per_rack <= 2:
            raise ValueError("Choose 1 or 2 canary hosts per rack; retain at least 3 controls")
        service = self.releases[release_id]["service_id"]
        base = self.engine.resource_model.services[service]
        replace(base, work_core_seconds=base.work_core_seconds*self.releases[release_id]["behavior"]["work_multiplier"])
        hosts = {h.host_id: h for h in self.engine.world.hosts}
        eligible = {r.host_id for r in self.engine.world.replicas if r.service_id == service and
                    hosts[r.host_id].lifecycle.value == "ready" and r.host_id not in self.engine.resource_model.unavailable_hosts}
        racks = sorted({hosts[h].rack_id for h in eligible})
        if not racks:
            raise ValueError("No eligible service hosts")
        canaries, controls, groups = [], [], []
        # Require every rack with service replicas, even when all hosts there are down.
        represented = {hosts[r.host_id].rack_id for r in self.engine.world.replicas if r.service_id == service}
        if set(racks) != represented:
            raise ValueError("A represented rack has no eligible hosts")
        for rack in racks:
            members = sorted(h for h in eligible if hosts[h].rack_id == rack)
            if len(members) < per_rack + 3:
                raise ValueError(f"{rack} needs {per_rack} canaries and 3 eligible controls")
            canaries += members[:per_rack]
            controls += members[per_rack:]
            groups.append({"rack_id": rack, "canaries": members[:per_rack], "controls": members[per_rack:]})
        plan = {"release_id": release_id, "release_metadata":self.registry.get(release_id).public_metadata(), "service_id": service, "per_rack": per_rack,
                "group_by": "rack_id", "canaries": canaries, "controls": controls, "racks": groups,
                "baseline_versions": {r.replica_id: r.release_id for r in self.engine.world.replicas if r.service_id == service}}
        plan["plan_id"] = digest(plan)
        return plan

    def command(self, action, args):
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        if action.startswith('policy_'):return self.engine.policy_controller.command(action,args)
        if action.startswith('rollout_'):self.engine.policy_controller.guard(action,args)
        if action=='restart_process':
            if set(args)!={'replica_id'} or args['replica_id'] not in self.engine.resource_model.replicas:raise ValueError('Provide one existing replica_id')
            if args['replica_id'] in self.pending_process_restarts:raise ValueError('Process restart already pending')
            self.pending_process_restarts.append(args['replica_id'])
            return {'replica_id':args['replica_id'],'applies_at_tick':self.engine.tick+1,'action':'actual_process_restart'}
        if action.startswith('rollout_'): return self.engine.rollouts.command(action,args)
        if action in ('deploy','rollback') and any(r['state'] not in ('ROLLED_BACK','PROMOTED') for r in self.engine.rollouts.records()):
            raise ValueError('Finish the fixed-cohort rollout before using legacy deployment commands')
        allowed = {"register_release": {"filename", "content_base64", "profile", "release"},
                   "preview": {"release_id", "per_rack"}, "deploy": {"plan_id"}, "rollback": set(),
                   "fault": {"fault_id", "kind", "scope", "target", "duration", "severity", "delay", "start_tick", "seed", "recovery"},
                   "random_faults": {"seed", "count"}, "background_set_enabled": {"enabled"}}
        if action not in allowed or set(args) - allowed[action]:
            raise ValueError("Unknown operation or argument")
        if action == "background_set_enabled":
            if set(args) != {"enabled"} or type(args["enabled"]) is not bool:
                raise ValueError("background_set_enabled requires boolean enabled")
            self.background.enabled = args["enabled"]
            return {"enabled": self.background.enabled, "applies_at_tick": self.engine.tick+1}
        if action == "register_release":
            if 'release' in args:
                if set(args)!={'release'}:raise ValueError('Use a release manifest or legacy upload fields, not both')
                payload=args['release']
            else:
                profile=args.get('profile','healthy');filename=args.get('filename');encoded=args.get('content_base64')
                if profile not in PROFILES or not isinstance(encoded,str) or len(encoded)>180000:raise ValueError('Invalid legacy upload/profile')
                try:content=base64.b64decode(encoded,validate=True)
                except (ValueError,TypeError) as exc:raise ValueError('Invalid base64 upload') from exc
                if not 1<=len(content)<=131072:raise ValueError('Upload must contain 1–131072 bytes')
                sha=hashlib.sha256(content).hexdigest()
                payload={'schema_version':1,'release_id':f'upload-{sha[:16]}-{profile}','service_id':self.service_id,
                    'version':f'0.0.0-upload-{sha[:16]}-{profile}','creation_metadata':{'author':'legacy-upload'},
                    'behavior_manifest':self._legacy_manifest(profile),'source_attachment':{'filename':filename,'content_base64':encoded}}
            if not isinstance(payload,dict):raise ValueError('release must be an object')
            manifest,behavior=behavior_manifest(payload.get('behavior_manifest'))
            service=self.engine.resource_model.services.get(payload.get('service_id'))
            if service is None:raise ValueError('Unknown service_id')
            replace(service,work_core_seconds=service.work_core_seconds*behavior.work_multiplier)
            record=self.registry.register(payload,self.engine.tick)
            return self._operator_record(record)
        if action == "preview":
            plan = self.preview(args.get("release_id"), args.get("per_rack", 1))
            self.plans = {plan["plan_id"]: plan}
            return copy.deepcopy(plan)
        if action == "deploy":
            if self.deployment["status"] not in ("idle", "rolled_back"):
                raise ValueError("Roll back the active candidate before another deployment")
            plan = self.plans.get(args.get("plan_id"))
            if plan is None or self.preview(plan["release_id"], plan["per_rack"]) != plan:
                raise ValueError("Allocation is missing or stale; preview again")
            self.deployment = {**copy.deepcopy(plan), "status": "deploy_pending", "exposure_tick": self.engine.tick + 1}
            self.baselines = dict(plan["baseline_versions"])
            return {"status": "queued", "applies_at_tick": self.engine.tick + 1}
        if action == "rollback":
            if self.deployment["status"] == "rolled_back":
                return {"status": "already_rolled_back"}
            if self.deployment["status"] not in ("deploy_pending", "canary", "rollback_pending"):
                raise ValueError("No active deployment to roll back")
            self.deployment["status"] = "rollback_pending"
            return {"status": "queued", "applies_at_tick": self.engine.tick + 1}
        if action == "fault":
            fault = self._validate_fault(args, len(self.faults))
            if len(self.faults) >= 100:
                raise ValueError("Reset before scheduling more than 100 faults")
            self.faults.append(fault)
            return {"status": "queued", "count": 1}
        seed, count = args.get("seed"), args.get("count", 5)
        if type(seed) is not int or not 0 <= seed < 2**32 or type(count) is not int or not 1 <= count <= 12:
            raise ValueError("Schedule needs an integer seed [0, 2^32) and count [1, 12]")
        if len(self.faults) + count > 100:
            raise ValueError("Reset before scheduling more than 100 faults")
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 1])))
        hosts = sorted(h.host_id for h in self.engine.world.hosts)
        if not hosts:
            raise ValueError("No hosts to fault")
        planned = []
        for i in range(count):
            params = {"kind": ("cpu_throttle", "service_crash")[int(rng.integers(2))], "scope": "host",
                      "target": hosts[int(rng.integers(len(hosts)))], "duration": int(rng.integers(3, 9)),
                      "delay": int(rng.integers(1, 25)), "severity": float(rng.uniform(0.4, 0.85))}
            fault = self._validate_fault(params, len(self.faults) + i)
            fault = replace(fault, seed=seed)
            planned.append(fault)
        self.faults.extend(planned)
        return {"status": "queued", "count": count, "seed": seed}

    def _validate_fault(self, args, index):
        if "start_tick" in args and "delay" in args:
            raise ValueError("Use start_tick or delay, not both")
        delay = args.get("delay", 1)
        if type(delay) is not int or not 1 <= delay <= 1000:
            raise ValueError("delay must be integer ticks in [1, 1000]")
        kind = args.get("kind")
        recovery = args.get("recovery", "restart" if kind == "service_crash" else "restore")
        event = FaultEvent(fault_id=args.get("fault_id", f"fault-{index+1}"), kind=kind,
            scope=args.get("scope", "host"), target=args.get("target", "world"),
            start_tick=args.get("start_tick", self.engine.tick+delay), duration=args.get("duration", 5),
            severity=args.get("severity", 0.75), seed=args.get("seed", self.engine.config.seed), recovery=recovery).resolve(self.engine.world)
        if event.start_tick <= self.engine.tick or event.start_tick > self.engine.tick+1000:
            raise ValueError("Fault must start in the next 1000 ticks")
        if any(f.fault_id == event.fault_id for f in self.faults + self.background.events):
            raise ValueError("Duplicate fault_id")
        return event

    def before_tick(self, tick):
        model = self.engine.resource_model
        for rid in self.pending_process_restarts:model.restart(rid,reason='manual_restart',tick=tick)
        self.pending_process_restarts.clear()
        if self.deployment["status"] in ("deploy_pending", "rollback_pending"):
            deploying = self.deployment["status"] == "deploy_pending"
            release = self.releases[self.deployment["release_id"]]
            replicas = []
            for r in self.engine.world.replicas:
                if r.service_id == release["service_id"] and r.host_id in self.deployment["canaries"]:
                    base = model.services[r.service_id]
                    behavior=self.registry.get(release['release_id'] if deploying else self.baselines[r.replica_id]).behavior
                    model.restart(r.replica_id,reason='release_replacement',tick=tick)
                    model.configure_behavior(r.replica_id,behavior)
                    r = replace(r, release_id=release["release_id"] if deploying else self.baselines[r.replica_id])
                    model.replicas[r.replica_id] = r
                replicas.append(r)
            self.engine.world = replace(self.engine.world, replicas=tuple(replicas))
            self.deployment["status"] = "canary" if deploying else "rolled_back"
            self.deployment["last_transition_tick"] = tick
        previously_unavailable = set(model.unavailable_hosts)
        model.cpu_factors = dict.fromkeys(model.host_replicas, 1.0)
        model.network_factors = dict.fromkeys(model.host_replicas, 1.0)
        model.platform_memory = dict.fromkeys(model.host_replicas, 0.0)
        model.unavailable_hosts = set()
        model.demand_multiplier = 1.0
        requested_memory = dict.fromkeys(model.host_replicas, 0.0)
        hosts = {h.host_id: h for h in self.engine.world.hosts}
        for fault in self.faults + self.background.active_events(tick):
            if not fault.active(tick):
                continue
            if fault.kind == FaultKind.DEMAND:
                model.demand_multiplier = min(8.0, model.demand_multiplier * (1+7*fault.severity))
            for host in fault.host_ids:
                if fault.kind == FaultKind.CPU:
                    model.cpu_factors[host] = max(0.05, model.cpu_factors[host]*(1-fault.severity))
                elif fault.kind == FaultKind.NETWORK:
                    model.network_factors[host] = max(0.05, model.network_factors[host]*(1-fault.severity))
                elif fault.kind == FaultKind.MEMORY:
                    requested_memory[host] += hosts[host].capacity.memory_mb*fault.severity
                elif fault.kind == FaultKind.CRASH:
                    model.unavailable_hosts.add(host)
        for host, amount in requested_memory.items():
            free = max(0.0, hosts[host].capacity.memory_mb-model.reserved_memory(host)-model.temporary_memory(host))
            model.platform_memory[host] = min(amount, free)
        for host in previously_unavailable-model.unavailable_hosts:
            for replica in model.host_replicas[host]:
                model.restart(replica.replica_id,reason='platform_recovery_restart',tick=tick)

    def developer_truth(self):
        manual = [{**f.to_dict(), "source": "manual", "active": f.active(self.engine.tick)} for f in self.faults]
        return manual + [{**f.to_dict(), "source": "background",
                          "active": self.background.enabled and f.active(self.engine.tick)} for f in self.background.events]

    def control_state(self):
        return {"releases": self.catalog(), "attachments": dict(self.attachments),
                "plans": copy.deepcopy(self.plans), "deployment": copy.deepcopy(self.deployment),
                "baselines": dict(self.baselines),"pending_process_restarts":list(self.pending_process_restarts),
                "background": {"enabled": self.background.enabled, "manifest": self.background.manifest()}}
