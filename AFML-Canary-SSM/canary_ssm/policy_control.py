"""Controller adapter for separately calibrated release evidence and observed advisories."""
import copy,math
from .policy_hash import digest
from .first_crossing import protocol,LatchedFirstCrossing,hash_value
from .policy_artifacts import validated_attachment,sources


def world_simulator(engine):
    config=copy.deepcopy(engine.config.to_dict());config.pop('seed',None);config.pop('events',None)
    if 'background_faults' in config:config['background_faults'].pop('seed',None)
    for replica in config['topology']['replicas']:replica.pop('release_id',None)
    return {'generator_id':'resource-world-scenarios-v1','config':config,
        'baseline_content_hashes':sorted({engine.demo.registry.get(r.release_id).public_metadata()['content_hash'] for r in engine.world.replicas}),
        'source_hashes':sources(['engine.py','resources.py','releases.py','telemetry.py','telemetry_transport.py','faults.py','fault_scheduler.py','resource_health.py','topology.py','seeds.py'])}

def world_protocol(engine,r,group_by):
    seconds=r['horizon_ticks']*engine.config.tick_seconds
    if seconds%60:raise ValueError('Calibrated policy requires whole monitoring minutes')
    prefix='rack:' if group_by=='rack_id' else 'class:'
    groups={g:m['controls'] for g,m in r['groups'].items() if g.startswith(prefix)}
    return protocol(r['canaries'],r['controls'],groups,baseline_seconds=r['baseline_ticks']*engine.config.tick_seconds,
        horizon_windows=seconds//60,canary_fraction=r['canary_fraction'],group_by=group_by)


class PolicyController:
    def __init__(self,engine):self.engine=engine;self.bindings={};self.log=[]

    def _row(self,rid):
        if rid not in self.engine.rollouts._records:raise ValueError('Unknown rollout')
        row=self.engine.rollouts._records[rid]
        if self.engine.rollouts._latest.get(row['service_id'])!=rid:raise ValueError('Superseded monitoring epoch')
        return row

    def _event(self,rid,reason,**fields):
        self.log.append({'sequence':len(self.log),'rollout_id':rid,'tick':self.engine.tick,'reason':reason,**copy.deepcopy(fields)})

    def _queue(self,rid,action,reason):
        r=self._row(rid)
        if r['pending_action'] is not None:
            self._event(rid,'action_already_pending',requested=action,pending=r['pending_action'],trigger=reason);return
        self.engine.rollouts.command(action,{'rollout_id':rid});r['pending_reason']=reason
        self._event(rid,reason,action=action,applies_at_tick=self.engine.tick+1)

    def guard(self,action,args):
        rid=args.get('rollout_id');b=self.bindings.get(rid)
        if not b or not b['active']:return
        r=self._row(rid)
        if action=='rollout_baseline' and self.engine.tick!=0:raise ValueError('Frozen policy baseline must begin at the fresh-run origin')
        if action=='rollout_expose' and self.engine.tick*self.engine.config.tick_seconds!=b['policy']['frozen']['protocol']['baseline_seconds']:raise ValueError('Exposure must match the exact frozen baseline boundary; extended preperiods need a new protocol')
        if action=='rollout_resume' and b['blocked_reasons']:raise ValueError('Latched release/incident/guardrail pause requires rollback or a new epoch')
        if action=='rollout_promote':
            state=b['runtime'].snapshot() if b['runtime'] else None
            if not state or not state['healthy_ready'] or b['blocked_reasons']:raise ValueError('Promotion holds: require completed eligible budget and declared healthy criteria, never absence of data')

    def command(self,action,args):
        if not isinstance(args,dict) or 'rollout_id' not in args:raise ValueError('Provide rollout_id and validated policy arguments')
        rid=args['rollout_id'];r=self._row(rid)
        if action=='policy_attach':
            if set(args)-{'rollout_id','policy','validation','auto_rollback'} or not {'policy','validation'}<=args.keys():raise ValueError('Attach policy and independent validation receipt')
            if rid in self.bindings:raise ValueError('Policy is immutable within an epoch')
            if r['state']!='CREATED' or self.engine.tick!=0 or r['exposure_tick'] is not None or r['pending_action'] is not None:raise ValueError('Commit policy in a fresh run before baseline, never after inspecting rollout data')
            if self.engine.config.events:raise ValueError('Scheduled lifecycle interventions need a separately calibrated protocol')
            bg=self.engine.config.background_faults
            if bg and bg.enabled and bg.mode=='fixed':raise ValueError('Fixed injected schedules are not inference compatibility features; use a calibrated sampling family')
            auto=args.get('auto_rollback',False)
            if type(auto) is not bool:raise ValueError('auto_rollback must be explicit boolean; default is false')
            p=validated_attachment(args['policy'],args['validation']);f=p['frozen']
            used=f['development']+p['calibration_lineage']+args['validation']['outcomes']
            if self.engine.config.seed in {x['seed'] for x in used} or self.engine.run_id in {x['run_id'] for x in used}:raise ValueError('Online rollout cannot reuse fitting/calibration/validation identity or seed')
            expected=world_protocol(self.engine,r,f['protocol']['group_by'])
            if f['hashes']['simulator_hash']!=digest(world_simulator(self.engine)) or f['protocol']!=expected:raise ValueError('Policy simulator/protocol is incompatible with this world; conditional/statistical demos cannot authorize world actions')
            if sorted(f['preprocessing_model']['canary_ids'])!=sorted(r['canaries']):raise ValueError('Frozen preprocessing canary cohort differs')
            controller_hash=digest({'policy_hash':p['policy_hash'],'auto_rollback':auto,'adapter':'policy-controller-v1','source':sources(['policy_control.py'])})
            self.bindings[rid]={'active':True,'policy':p,'validation_hash':args['validation']['validation_hash'],'validation_rates':args['validation']['rates'],
                'auto_rollback':auto,'controller_hash':controller_hash,'runtime':None,'blocked_reasons':[],'observations':0}
            r['calibration_status']='CALIBRATED_VALIDATED';r['alerts_enabled']=True
            self._event(rid,'validated_policy_attached',policy_hash=p['policy_hash'],controller_hash=controller_hash,auto_rollback=auto)
            return self.snapshot(rid)
        b=self.bindings.get(rid)
        if not b or not b['active']:raise ValueError('No validated compatible policy is attached')
        if r['state'] not in ('CANARY','PAUSED') or not r['evaluation_active'] or r['pending_action'] in ('rollout_promote','rollout_rollback'):raise ValueError('Policy evidence requires an active exposed fixed-cohort epoch')
        now=self.engine.tick*self.engine.config.tick_seconds
        if action=='policy_observe':
            if set(args)!={'rollout_id','record','hashes','run_id','monitoring_epoch'}:raise ValueError('Provide explicit producer identity, epoch, five hashes and observation')
            if args['run_id']!=self.engine.run_id or type(args['monitoring_epoch']) is not int or args['monitoring_epoch']!=r['monitoring_epoch']:raise ValueError('Policy evidence belongs to another run or epoch')
            expected={**b['policy']['frozen']['hashes'],'policy_hash':b['policy']['policy_hash']}
            if args['hashes']!=expected:raise ValueError('Model/preprocessing/simulator/protocol/policy hash mismatch')
            record=args['record']
            if record['decision_time']>now or record['decision_time']>(r['evaluation_end_tick']-1)*self.engine.config.tick_seconds:raise ValueError('Policy observation is from the future or outside monitoring horizon')
            runtime=b['runtime'] or LatchedFirstCrossing(b['policy']['frozen']['protocol'],b['policy']['frozen']['rule'],b['policy']['calibration']['threshold'],exposure_time=r['first_decision_time'])
            result=runtime.observe(record);b['runtime']=runtime
            if not result['duplicate']:
                b['observations']+=1;self._event(rid,'release_policy_observation',decision=result)
                if result['first_crossing'] and 'release_regression_alarm' not in b['blocked_reasons']:
                    b['blocked_reasons'].append('release_regression_alarm')
                    if r['state']=='CANARY':self._queue(rid,'rollout_pause','release_regression_alarm')
                    else:self._event(rid,'release_regression_alarm',action='already_paused')
            return result
        if action=='policy_advisory':
            if set(args)!={'rollout_id','kind','source','evidence_hash','decision_time','represented_groups'} or args['source']!='observed_metrics':raise ValueError('Require observed evidence, not simulator injection labels')
            hash_value(args['evidence_hash'])
            if type(args['decision_time']) not in (int,float) or not math.isfinite(args['decision_time']) or args['decision_time']>now or args['decision_time']<(r['exposure_tick']-1)*self.engine.config.tick_seconds:raise ValueError('Advisory must be causal and within exposed monitoring')
            if args['kind']=='platform':
                if b['policy']['frozen']['rule']['platform_incidents']!='pause_only':raise ValueError('Platform incident pause is disabled')
                groups=args['represented_groups']
                if not isinstance(groups,list) or len(set(groups))<2 or not set(groups)<=set(b['policy']['frozen']['protocol']['groups']):raise ValueError('Shared incident needs observed evidence across two represented groups')
                reason='shared_platform_incident'
            elif args['kind']=='resource':
                if b['policy']['frozen']['rule']['resource_guardrails']!='observed_pause':raise ValueError('Resource guardrail is separately disabled')
                reason='resource_health_guardrail'
            else:raise ValueError('Unknown observed advisory kind')
            if reason not in b['blocked_reasons']:b['blocked_reasons'].append(reason)
            self._event(rid,reason,evidence_hash=args['evidence_hash'],source=args['source'])
            if r['state']=='CANARY':self._queue(rid,'rollout_pause',reason)
            return self.snapshot(rid)
        raise ValueError('Unknown policy command')

    def before_rollout_tick(self):
        for rid,b in self.bindings.items():
            if not b['active'] or not b['blocked_reasons']:continue
            r=self.engine.rollouts._records[rid]
            if r['pending_action'] in ('rollout_resume','rollout_promote'):
                cancelled=r['pending_action'];r['pending_action']=None;r.pop('pending_reason',None)
                self._event(rid,'queued_action_cancelled_by_latch',cancelled=cancelled,blocked_reasons=b['blocked_reasons'])

    def before_tick(self):
        for rid,b in self.bindings.items():
            if not b['active']:continue
            r=self.engine.rollouts._records[rid]
            if r['state'] in ('ROLLED_BACK','PROMOTED','FAILED'):
                b['active']=False;r['alerts_enabled']=False;continue
            if b['blocked_reasons'] and r['state']=='CANARY' and r['pending_action'] is None:self._queue(rid,'rollout_pause',b['blocked_reasons'][0])
            if b['auto_rollback'] and 'release_regression_alarm' in b['blocked_reasons'] and r['state']=='PAUSED' and r['pending_action'] is None:
                self._queue(rid,'rollout_rollback','opt_in_release_alarm_auto_rollback')

    def after_observations(self):
        # Direct observed resource channel, separate from latency inference and
        # from injected fault labels. This hook never reads Fault Lab truth.
        from .resource_health import summarize
        enabled=[(rid,b) for rid,b in self.bindings.items() if b['active'] and b['policy']['frozen']['rule']['resource_guardrails']=='observed_pause' and 'resource_health_guardrail' not in b['blocked_reasons']]
        if not enabled:return
        now=self.engine.tick*self.engine.config.tick_seconds
        health=summarize(self.engine.resource_model.host_trace,now,self.engine.config.resources.health_policy)
        for rid,b in enabled:
            r=self.engine.rollouts._records[rid]
            if r['state'] not in ('CANARY','PAUSED') or not r['evaluation_active'] or r['pending_action'] in ('rollout_promote','rollout_rollback'):continue
            hosts=set(r['canaries'])|set(r['controls'])
            warnings=[x for x in health['advisories'] if x['host_id'] in hosts and x['fresh'] and any(flag in x['flags'] for flag in ('observed_memory_growth_warning','observed_low_headroom','process_unavailable_after_oom'))]
            if warnings:self.command('policy_advisory',{'rollout_id':rid,'kind':'resource','source':'observed_metrics','evidence_hash':digest({'policy':health['policy_sha256'],'observations':warnings}),'decision_time':now,'represented_groups':[]})

    def on_reset(self):
        for rid,b in self.bindings.items():
            if b['active']:b['active']=False;self._event(rid,'world_reset_closes_policy_epoch')
            self.engine.rollouts._records[rid]['alerts_enabled']=False

    def snapshot(self,rid=None):
        rows=[]
        for key,b in self.bindings.items():
            if rid is not None and key!=rid:continue
            rows.append({'rollout_id':key,'active':b['active'],'policy_hash':b['policy']['policy_hash'],'hashes':copy.deepcopy(b['policy']['frozen']['hashes']),
                'validation_hash':b['validation_hash'],'controller_hash':b['controller_hash'],'auto_rollback':b['auto_rollback'],
                'blocked_reasons':list(b['blocked_reasons']),'observations':b['observations'],'decision':b['runtime'].snapshot() if b['runtime'] else {'state':'HOLD','quality_reasons':['no_eligible_data'],'healthy_ready':False},
                'validation_false_alerts':copy.deepcopy(b['validation_rates'])})
        return {'adapter':'policy-controller-v1','bindings':rows,'decisions':copy.deepcopy(self.log)}
