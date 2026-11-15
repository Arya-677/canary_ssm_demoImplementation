"""Public console projections and backend-owned checkpoint storage.

No scoring, simulation loop, or evaluator labels live in this adapter.
"""
import copy
import hashlib
import json
import re
from pathlib import Path


def preview_rollout(engine, args):
    """Validate with the actual manager on detached bookkeeping; never advance it."""
    if engine.demo is None:
        raise ValueError('Resource console required')
    manager = copy.copy(engine.rollouts)
    manager._records = copy.deepcopy(manager._records)
    manager._latest = dict(manager._latest)
    manager._log = list(manager._log)
    row = manager.command('rollout_create', args)
    return {k:copy.deepcopy(row[k]) for k in ('release_id','service_id','canaries','controls','groups','canary_fraction','cohort_sha256','baseline_ticks','horizon_ticks')}


def console_evidence(engine, outcomes):
    model = engine.resource_model
    rollout = engine.rollouts.records()[-1] if engine.demo and engine.rollouts.records() else None
    bindings = engine.policy_controller.bindings if engine.demo else {}
    binding = bindings.get(rollout['rollout_id']) if rollout else None
    frozen = binding['policy']['frozen'] if binding else None
    context = dict(simulation_mode='SIMULATION · declared behavior, source never executed',seed=engine.config.seed,
        model_id=(frozen['effect_settings']['kind']+':'+frozen['hashes']['model_hash']) if frozen else 'DETECTOR NOT CONNECTED',
        policy_id=binding['policy']['policy_hash'] if binding else None,
        calibration_status=('CALIBRATED_VALIDATED' if binding['active'] else 'CLOSED CALIBRATED EPOCH') if binding else 'UNCALIBRATED',
        protocol_id=rollout['policy_id'] if rollout else None,
        decision_reason=(binding['blocked_reasons'][-1] if binding['blocked_reasons'] else binding['runtime'].snapshot()['state'] if binding['runtime'] else 'Awaiting eligible evidence') if binding else 'No compatible policy attached; operator commands only')
    allocations = []
    for replica in engine.world.replicas:
        route = model.fixed_routes.get(replica.service_id) if model else None
        peers = [r for r in engine.world.replicas if r.service_id==replica.service_id]
        role, weight = 'balanced', None
        if route:
            if replica.host_id in route['canary_hosts']:
                role, weight = 'canary',route['canary_fraction']/len(route['canary_hosts'])
            elif replica.host_id in route['control_hosts']:
                role, weight = 'control',(1-route['canary_fraction'])/len(route['control_hosts'])
            else:
                role, weight = 'outside frozen cohort',0.
        elif model:
            ready = [r for r in peers if next(h for h in engine.world.hosts if h.host_id==r.host_id).lifecycle.value=='ready'
                and r.host_id not in model.unavailable_hosts and model.process_states[r.replica_id]=='RUNNING']
            weight = 1/len(ready) if replica in ready else 0.
        release = engine.demo.registry.get(replica.release_id).public_metadata() if engine.demo else {}
        allocations.append(dict(service_id=replica.service_id,replica_id=replica.replica_id,host_id=replica.host_id,
            release_id=replica.release_id,version=release.get('version'),role=role,nominal_traffic_fraction=weight,
            routed_requests_last_tick=model.routed_by_replica.get(replica.replica_id,0) if model else None,
            process_state=model.process_states.get(replica.replica_id) if model else None))
    timeline = [dict(tick=x['tick'],sequence=x['seq'],kind='command',reason=x.get('error') or x['status'],
        command=x['command'],command_id=x['command_id']) for x in outcomes]
    if engine.demo:
        timeline += [dict(tick=x['tick'],sequence=x['sequence'],kind='rollout',reason=x['reason'],
            state=x['to_state'],rollout_id=x['rollout_id']) for x in engine.rollouts.transition_log()]
        timeline += [dict(tick=x['tick'],sequence=x['sequence'],kind='policy',reason=x['reason'],
            action=x.get('action'),rollout_id=x['rollout_id']) for x in engine.policy_controller.log]
    timeline.sort(key=lambda x:(x['tick'],{'command':0,'rollout':1,'policy':2}[x['kind']],x['sequence']))
    return dict(context=context,replicas=allocations,timeline=timeline[-200:],timeline_limit=200)


class RunArchive:
    def __init__(self,state_dir):
        self.directory = Path(state_dir)/'runs' if state_dir else None
        self.memory = {}
        self.metadata_cache = {}

    def save(self,saved):
        raw = json.dumps(saved,allow_nan=False,sort_keys=True).encode()
        if len(raw)>32*1024*1024:
            raise ValueError('Checkpoint exceeds 32 MiB; export the current run directly')
        identity = hashlib.sha256(raw).hexdigest()
        row = self.metadata(identity,saved)
        if self.directory:
            self.directory.mkdir(parents=True,exist_ok=True)
            if not (self.directory/(identity+'.json')).exists():
                if len(list(self.directory.glob('*.json')))>=128:
                    raise ValueError('128 backend checkpoints reached; export before creating another')
                temp = self.directory/(identity+'.tmp')
                temp.write_bytes(raw)
                temp.replace(self.directory/(identity+'.json'))
        else:
            if identity not in self.memory and len(self.memory)>=128:
                raise ValueError('128 backend checkpoints reached')
            self.memory[identity] = copy.deepcopy(saved)
        self.metadata_cache[identity]=copy.deepcopy(row)
        return row

    @staticmethod
    def metadata(identity,saved):
        engine = saved['engine']
        final = engine['final_snapshot']
        return dict(checkpoint_id=identity,run_id=saved['run_id'],epoch=saved['epoch'],tick=final['tick'],
            simulated_seconds=final['simulated_seconds'],seed=engine['config']['seed'],state=final['state'],
            command_outcomes=len(saved.get('outcomes',[])),source='backend saved session')

    def get(self,identity):
        if not isinstance(identity,str) or not re.fullmatch('[0-9a-f]{64}',identity):
            raise ValueError('Invalid checkpoint ID')
        if self.directory:
            path = self.directory/(identity+'.json')
            if not path.is_file():
                raise ValueError('Unknown checkpoint ID')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=identity:
                raise ValueError('Checkpoint content hash mismatch')
            return json.loads(raw)
        if identity not in self.memory:
            raise ValueError('Unknown checkpoint ID')
        return copy.deepcopy(self.memory[identity])

    def list(self):
        ids = [p.stem for p in self.directory.glob('*.json')] if self.directory and self.directory.exists() else list(self.memory)
        for identity in ids:
            if identity not in self.metadata_cache:
                self.metadata_cache[identity]=self.metadata(identity,self.get(identity))
        rows = [copy.deepcopy(self.metadata_cache[i]) for i in ids]
        return sorted(rows,key=lambda x:(x['run_id'],x['epoch'],x['tick'],x['checkpoint_id']),reverse=True)
