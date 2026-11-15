"""Manual fixed-cohort rollout protocol. Decisions never consume simulator truth."""
import copy
import itertools
import math
from dataclasses import dataclass,asdict,replace
from enum import Enum

from .telemetry import digest,identifier


class RolloutState(str,Enum):
    CREATED='CREATED'
    BASELINING='BASELINING'
    CANARY='CANARY'
    PAUSED='PAUSED'
    PROMOTED='PROMOTED'
    ROLLED_BACK='ROLLED_BACK'
    FAILED='FAILED'


@dataclass(frozen=True)
class Transition:
    sequence:int
    rollout_id:str
    monitoring_epoch:int
    tick:int
    from_state:str|None
    to_state:str
    reason:str
    previous_hash:str|None
    entry_hash:str


def select_cohort(world,service_id,per_rack=1,unavailable=()):
    """Deterministic bounded search across rack AND class partitions (not nested)."""
    if type(per_rack) is not int or per_rack not in (1,2):raise ValueError('Use one or two canaries per rack')
    hosts={h.host_id:h for h in world.hosts};replicas=[r for r in world.replicas if r.service_id==service_id]
    if not replicas or len({r.host_id for r in replicas})!=len(replicas):raise ValueError('Fixed-cohort v1 requires one service replica per host')
    racks=sorted({hosts[r.host_id].rack_id for r in replicas});classes=sorted({hosts[r.host_id].class_id for r in replicas})
    eligible=sorted(r.host_id for r in replicas if hosts[r.host_id].lifecycle.value=='ready' and r.host_id not in unavailable)
    groups={**{'rack:'+r:{h for h in eligible if hosts[h].rack_id==r} for r in racks},
        **{'class:'+str(c):{h for h in eligible if hosts[h].class_id==c} for c in classes}}
    if any(len(m)<4 for m in groups.values()):raise ValueError('Each represented rack/class needs a canary and three unexposed controls')
    options=[]
    for rack in racks:
        members=sorted(groups['rack:'+rack])
        if len(members)<per_rack+3:raise ValueError('Rack cannot retain three controls')
        options.append(list(itertools.combinations(members,per_rack)))
    visits=0
    def search(index,chosen):
        nonlocal visits
        visits+=1
        if visits>100000:raise ValueError('Cohort search budget exceeded; simplify the topology')
        C=set(chosen)
        if any(len(m-C)<3 for m in groups.values()):return None
        if index==len(racks):return tuple(sorted(C)) if all(C&m for m in groups.values()) else None
        covered={hosts[h].class_id for h in C}
        choices=sorted(options[index],key=lambda candidate:(-len({hosts[h].class_id for h in candidate}-covered),candidate))
        for candidate in choices:
            result=search(index+1,chosen+candidate)
            if result is not None:return result
        return None
    canaries=search(0,())
    if canaries is None:raise ValueError('No cohort covers represented racks/classes while retaining three controls in each')
    controls=tuple(h for h in eligible if h not in canaries)
    return canaries,controls,{g:{'canaries':sorted(set(canaries)&m),'controls':sorted(set(controls)&m)} for g,m in groups.items()}


class RolloutManager:
    def __init__(self,engine):
        self.engine=engine;self._records={};self._latest={};self._log=[];self._next_epoch=1

    def records(self):return copy.deepcopy(list(self._records.values()))
    def transition_log(self):return [asdict(t) for t in self._log]
    def latest(self,service_id):return copy.deepcopy(self._records[self._latest[service_id]]) if service_id in self._latest else None

    def _transition(self,r,state,reason,tick):
        previous=self._log[-1].entry_hash if self._log else None
        row={'sequence':len(self._log),'rollout_id':r['rollout_id'],'monitoring_epoch':r['monitoring_epoch'],
            'tick':tick,'from_state':r.get('state'),'to_state':state,'reason':reason,'previous_hash':previous}
        self._log.append(Transition(**row,entry_hash=digest(row)))
        r['state']=state;r['last_transition_tick']=tick

    def _observed_unavailable(self):
        return {r['host_id'] for r in self.engine.resource_model.last_hosts if not r['available'] or 'OOM' in r.get('process_state','')}

    def _blocked_exposure(self, exclude_service=None):
        blocked=set()
        for sid in self._latest:
            if sid==exclude_service:continue
            r=self._records[self._latest[sid]]
            if r['state']!='ROLLED_BACK':blocked.update(set(r['canaries'])|set(r['controls']) if r['state']!='PROMOTED' else r['original_placement'].values())
        legacy=self.engine.demo.deployment
        if legacy['status'] in ('deploy_pending','canary','rollback_pending'):blocked.update(legacy['canaries'])
        return blocked

    def command(self,action,args):
        if not isinstance(args,dict):raise ValueError('Rollout args must be an object')
        if action=='rollout_create':
            allowed={'release_id','per_rack','canary_fraction','baseline_seconds','monitoring_seconds'}
            if set(args)-allowed or 'release_id' not in args:raise ValueError('Invalid fixed-cohort rollout configuration')
            if len(self._records)>=1000:raise ValueError('Run rollout limit reached; export this run before starting a new one')
            release=self.engine.demo.registry.get(args['release_id']);sid=release.service_id
            old=self.latest(sid)
            if old and old['state'] not in ('ROLLED_BACK','PROMOTED'):raise ValueError('Finish the active service rollout first')
            if self.engine.demo.deployment['status'] in ('deploy_pending','canary','rollback_pending'):raise ValueError('Finish the legacy deployment first')
            placement=[r for r in self.engine.world.replicas if r.service_id==sid]
            if any(r.release_id==release.release_id for r in placement):raise ValueError('Candidate is already exposed on this service')
            base=self.engine.resource_model.services[sid]
            replace(base,work_core_seconds=base.work_core_seconds*release.behavior.work_multiplier)
            dt=self.engine.config.tick_seconds
            baseline=args.get('baseline_seconds',3600);horizon=args.get('monitoring_seconds',7200)
            if any(type(v) is not int or not dt<=v<=86400 or v%dt for v in (baseline,horizon)):raise ValueError('Baseline/horizon seconds must be tick-aligned integers in [dt,86400]')
            blocked=self._observed_unavailable()|self._blocked_exposure(sid)
            # A completed promotion is production baseline for its next epoch.

            C,K,groups=select_cohort(self.engine.world,sid,args.get('per_rack',1),blocked)
            fraction=args.get('canary_fraction',len(C)/(len(C)+len(K)))
            if type(fraction) not in (int,float) or not math.isfinite(fraction) or not 0<fraction<1:raise ValueError('Canary traffic fraction must be in (0,1)')
            row={'release_id':release.release_id,'service_id':sid,'candidate':release.public_metadata(),
                'baseline_versions':{r.replica_id:r.release_id for r in placement},'original_placement':{r.replica_id:r.host_id for r in placement},
                'baseline_releases':[self.engine.demo.registry.get(rid).public_metadata() for rid in sorted({r.release_id for r in placement})],
                'canaries':list(C),'controls':list(K),'groups':groups,'canary_fraction':float(fraction),
                'policy_id':'fixed-cohort-rack-class-v1','min_controls_per_group':3,'minimum_canary_coverage':.8,
                'baseline_ticks':baseline//dt,'horizon_ticks':horizon//dt,'baseline_start_tick':None,'exposure_tick':None,
                'first_decision_time':None,'evaluation_end_tick':None,'evaluation_active':False,'monitoring_epoch':self._next_epoch,
                'calibration_status':'UNCALIBRATED','alerts_enabled':False,'pending_action':None}
            row['cohort_sha256']=digest({'canaries':C,'controls':K,'groups':groups,'fraction':fraction})
            row['rollout_id']='rollout-'+digest([sid,self._next_epoch,row['cohort_sha256'],release.release_id])[:24]
            self._records[row['rollout_id']]=row;self._latest[sid]=row['rollout_id'];self._next_epoch+=1
            self._transition(row,'CREATED','manual_create',self.engine.tick);return copy.deepcopy(row)
        if set(args)!={'rollout_id'}:raise ValueError('Provide exactly rollout_id; cohort/traffic changes require a new epoch and recalibration')
        rid=args['rollout_id'];identifier(rid,'rollout_id')
        if rid not in self._records or self._latest.get(self._records[rid]['service_id'])!=rid:raise ValueError('Unknown or superseded rollout')
        r=self._records[rid];state=r['state']
        if r['pending_action'] is not None:raise ValueError('A rollout action is pending for the next tick')
        allowed={'rollout_baseline':('CREATED',),'rollout_expose':('BASELINING',),'rollout_pause':('CANARY',),
            'rollout_resume':('PAUSED',),'rollout_promote':('CANARY','PAUSED'),
            'rollout_rollback':('CREATED','BASELINING','CANARY','PAUSED','PROMOTED','FAILED'),
            'rollout_fail':('CREATED','BASELINING','CANARY','PAUSED')}
        if action not in allowed or state not in allowed[action]:raise ValueError('Invalid rollout state transition')
        if action=='rollout_expose' and self.engine.tick-r['baseline_start_tick']+1<r['baseline_ticks']:raise ValueError('Baseline duration is not complete')
        if action=='rollout_resume' and not r['evaluation_active']:raise ValueError('Monitoring horizon ended; create a new epoch and recalibrate')
        r['pending_action']=action
        return {'rollout_id':rid,'state':state,'pending_action':action,'applies_at_tick':self.engine.tick+1}

    def _place(self,r,mode):
        model=self.engine.resource_model;world=self.engine.world;replicas=[]
        for replica in world.replicas:
            if replica.service_id!=r['service_id']:replicas.append(replica);continue
            change=mode=='rollback' or mode=='promote' and replica.release_id!=r['release_id'] or mode=='canary' and replica.host_id in r['canaries']
            if change:
                rid=r['baseline_versions'][replica.replica_id] if mode=='rollback' else r['release_id']
                release=self.engine.demo.registry.get(rid);behavior=release.behavior;base=model.services[replica.service_id]
                model.restart(replica.replica_id,reason='rollout_'+mode,tick=self.engine.tick)
                model.configure_behavior(replica.replica_id,behavior)
                replica=replace(replica,release_id=rid);model.replicas[replica.replica_id]=replica
            replicas.append(replica)
        self.engine.world=replace(world,replicas=tuple(replicas))

    def before_tick(self,tick):
        for sid in sorted(self._latest):
            r=self._records[self._latest[sid]];action=r['pending_action'];r['pending_action']=None
            policy_reason=r.pop('pending_reason',None)
            current={x.replica_id:x.host_id for x in self.engine.world.replicas if x.service_id==sid}
            if r['state'] not in ('ROLLED_BACK','PROMOTED','FAILED') and current!=r['original_placement']:
                self._close(r,tick);self._transition(r,'FAILED','public_placement_changed',tick);continue
            if action=='rollout_baseline':
                model=self.engine.resource_model
                for replica in self.engine.world.replicas:
                    if replica.service_id==sid:model.restart(replica.replica_id,reason='rollout_baseline',tick=tick)
                model.fixed_routes[sid]={'canary_hosts':tuple(r['canaries']),'control_hosts':tuple(r['controls']),
                    'canary_fraction':r['canary_fraction'],'rollout_id':r['rollout_id'],'monitoring_epoch':r['monitoring_epoch']}
                r['baseline_start_tick']=tick;self._transition(r,'BASELINING','manual_baseline',tick)
            elif action=='rollout_expose':
                self._place(r,'canary');r['exposure_tick']=tick;r['evaluation_end_tick']=tick+r['horizon_ticks'];r['evaluation_active']=True
                dt=self.engine.config.tick_seconds;r['first_decision_time']=(math.ceil(((tick-1)*dt)/60)+1)*60
                self._transition(r,'CANARY','manual_exposure',tick)
            elif action=='rollout_pause':self._transition(r,'PAUSED',policy_reason or 'manual_pause_fixed_traffic',tick)
            elif action=='rollout_resume':self._transition(r,'CANARY','manual_resume_same_epoch',tick)
            elif action=='rollout_promote':
                self._close(r,tick);self._place(r,'promote');self.engine.resource_model.fixed_routes.pop(sid,None)
                self._transition(r,'PROMOTED',policy_reason or 'manual_promote_ends_evaluation',tick)
            elif action=='rollout_rollback':
                self._close(r,tick);self._place(r,'rollback');self.engine.resource_model.fixed_routes.pop(sid,None)
                self._transition(r,'ROLLED_BACK',policy_reason or 'manual_rollback_restart_all_service_replicas',tick)
            elif action=='rollout_fail':self._close(r,tick);self._transition(r,'FAILED','manual_fail',tick)
            if r['evaluation_active'] and tick>=r['evaluation_end_tick']:
                r['evaluation_active']=False;self._transition(r,'PAUSED','monitoring_horizon_elapsed',tick)

    def _close(self,r,tick):
        r['evaluation_active']=False
        if r['exposure_tick'] is not None:r['evaluation_end_tick']=min(r['evaluation_end_tick'],tick)

    def exposed_replicas(self):
        exposed=set()
        for sid in self._latest:
            r=self._records[self._latest[sid]]
            if r['exposure_tick'] is None or r['state']=='ROLLED_BACK':continue
            exposed.update(x.replica_id for x in self.engine.world.replicas if x.service_id==sid and x.release_id==r['release_id'])
        return exposed

    def binding_for(self,hosts):
        for sid in self._latest:
            r=self._records[self._latest[sid]]
            if set(hosts)==set(r['canaries']):return copy.deepcopy(r)
        return None

    def on_reset(self):
        for rid in list(self._latest.values()):
            r=self._records[rid]
            self._close(r,self.engine.tick);r['pending_action']=None;r.pop('pending_reason',None)
            if r['state']!='ROLLED_BACK':self._transition(r,'ROLLED_BACK','world_reset_restores_initial_world',self.engine.tick)
        self._latest.clear()

    def snapshot(self):return {'protocol_version':'fixed-cohort-rack-class-v1','rollouts':self.records(),'transitions':self.transition_log()}
