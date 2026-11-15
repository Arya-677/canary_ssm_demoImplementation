"""Separate causal, latched release policy. No simulator/evaluator inputs."""
import copy
import math
from .telemetry import digest

RULE_ID='latched-first-crossing-v1'
HASH_KEYS=('model_hash','preprocessing_hash','simulator_hash','protocol_hash')


def hash_value(v):
    if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v):raise ValueError('Expected lowercase SHA-256')
    return v


def encode_threshold(x):return '+inf' if x==math.inf else '-inf' if x==-math.inf else float(x)
def decode_threshold(x):return math.inf if x=='+inf' else -math.inf if x=='-inf' else float(x)


def rule(horizon,**options):
    result={'rule_id':RULE_ID,'alpha':.05,'required_eligible_windows':horizon,'healthy_max_score':math.log(.05),'resource_guardrails':'disabled','platform_incidents':'pause_only'}
    result.update(options);validate_rule(result,horizon);return result


def validate_rule(r,horizon):
    fields={'rule_id','alpha','required_eligible_windows','healthy_max_score','resource_guardrails','platform_incidents'}
    if set(r)!=fields or r['rule_id']!=RULE_ID:raise ValueError('Unknown first-crossing rule')
    if type(r['alpha']) not in (float,int) or not math.isfinite(r['alpha']) or not 0<r['alpha']<1:raise ValueError('Invalid alpha')
    if type(r['required_eligible_windows']) is not int or not 1<=r['required_eligible_windows']<=horizon:raise ValueError('Invalid eligible observation budget')
    if type(r['healthy_max_score']) not in (float,int) or not math.isfinite(r['healthy_max_score']) or r['healthy_max_score']>0:raise ValueError('Use a declared log-risk promotion ceiling')
    if r['resource_guardrails'] not in ('disabled','observed_pause') or r['platform_incidents'] not in ('disabled','pause_only'):raise ValueError('Unknown advisory policy')


def protocol(canaries,controls,groups,*,baseline_seconds=3600,horizon_windows=4,canary_fraction=.2,group_by='rack_id'):
    p={'protocol_id':'fixed-cohort-policy-v1','canaries':sorted(canaries),'controls':sorted(controls),
       'groups':{g:sorted(ids) for g,ids in sorted(groups.items())},'baseline_seconds':baseline_seconds,'horizon_windows':horizon_windows,
       'canary_fraction':canary_fraction,'group_by':group_by,'window_seconds':60,'exposure_alignment':'minute_start',
       'minimum_observed_canaries':.8,'minimum_fresh_controls':3,'score_kind':'log_max_host_effect_risk'}
    validate_protocol(p);return p


def validate_protocol(p):
    if set(p)!={'protocol_id','canaries','controls','groups','baseline_seconds','horizon_windows','canary_fraction','group_by','window_seconds','exposure_alignment','minimum_observed_canaries','minimum_fresh_controls','score_kind'}:raise ValueError('Invalid policy protocol fields')
    if p['protocol_id']!='fixed-cohort-policy-v1' or p['window_seconds']!=60 or p['exposure_alignment']!='minute_start' or p['score_kind']!='log_max_host_effect_risk':raise ValueError('Unsupported policy protocol')
    if p['minimum_observed_canaries']!=.8 or p['minimum_fresh_controls']!=3:raise ValueError('Research 80%/3 eligibility defaults must be preserved')
    C,K=p['canaries'],p['controls']
    if not C or not K or len(set(C))!=len(C) or len(set(K))!=len(K) or set(C)&set(K):raise ValueError('Cohorts must be unique and unexposed controls distinct')
    if p['group_by'] not in ('rack_id','class_id') or not p['groups'] or any(len(set(v))!=len(v) or not set(v)<=set(K) or len(v)<3 for v in p['groups'].values()):raise ValueError('Each represented monitoring group needs three controls')
    if type(p['baseline_seconds']) is not int or p['baseline_seconds']<3600 or p['baseline_seconds']%60:raise ValueError('Require at least 60 healthy baseline minutes')
    if type(p['horizon_windows']) is not int or not 1<=p['horizon_windows']<=1000:raise ValueError('Invalid complete horizon')
    if type(p['canary_fraction']) not in (int,float) or not math.isfinite(p['canary_fraction']) or not 0<p['canary_fraction']<1:raise ValueError('Invalid frozen traffic')


def eligibility(record,p,exposure_time):
    fields={'window_index','event_time','decision_time','score','available','fresh_canaries','fresh_controls','exposed_hosts','quality_flags','input_sha256'}
    if not isinstance(record,dict) or set(record)!=fields:raise ValueError('Invalid policy observation fields')
    i=record['window_index'];t=record['event_time'];d=record['decision_time']
    if type(i) is not int or not 0<=i<p['horizon_windows']:raise ValueError('Observation outside frozen horizon')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (t,d)) or t!=exposure_time+i*60 or d<t:raise ValueError('Wrong monitoring epoch/minute or noncausal deadline')
    hash_value(record['input_sha256'])
    if type(record['available']) is not bool or not isinstance(record['quality_flags'],list) or any(not isinstance(x,str) for x in record['quality_flags']):raise ValueError('Invalid quality metadata')
    C=record['fresh_canaries'];K=record['fresh_controls'];E=record['exposed_hosts']
    if not isinstance(C,list) or len(set(C))!=len(C) or not set(C)<=set(p['canaries']) or not isinstance(K,dict) or set(K)!=set(p['groups']) or not isinstance(E,list) or len(set(E))!=len(E):raise ValueError('Fresh cohort evidence must match frozen protocol')
    for g,ids in K.items():
        if not isinstance(ids,list) or len(set(ids))!=len(ids) or not set(ids)<=set(p['groups'][g]):raise ValueError('Control evidence outside frozen group')
    reasons=[]
    if t<exposure_time:reasons.append('pre_exposure')
    if not record['available']:reasons.append('unavailable_observations')
    if record['quality_flags']:reasons.append('quality_hold')
    if len(C)/len(p['canaries'])<.8:reasons.append('insufficient_canary_coverage')
    if any(len(set(ids)-set(E)-set(p['canaries']))<3 for ids in K.values()):reasons.append('insufficient_fresh_unexposed_controls')
    score=record['score']
    if score is None:reasons.append('missing_score')
    elif type(score) not in (int,float) or not math.isfinite(score) or score>0:raise ValueError('Use a finite log max-host risk, or null for missing')
    return not reasons,reasons


class LatchedFirstCrossing:
    def __init__(self,p,settings,threshold,*,exposure_time):
        validate_protocol(p);validate_rule(settings,p['horizon_windows'])
        if type(exposure_time) not in (int,float) or not math.isfinite(exposure_time) or exposure_time<60 or exposure_time%60:raise ValueError('Exposure is a clean monitoring-minute end')
        self.protocol=copy.deepcopy(p);self.rule=copy.deepcopy(settings);self.threshold=decode_threshold(threshold)
        if math.isnan(self.threshold) or self.threshold>0 and self.threshold!=math.inf:raise ValueError('Invalid release threshold')
        self.exposure_time=exposure_time;self.first_crossing=None;self._records={};self.eligible_windows=[];self.maximum=-math.inf;self.last_decision=-math.inf

    def observe(self,record):
        ok,reasons=eligibility(record,self.protocol,self.exposure_time);i=record['window_index']
        if i in self._records:
            if record!=self._records[i]:raise ValueError('Earlier decisions are immutable; late revisions rejected')
            return self.snapshot(duplicate=True)
        if self._records and i<=max(self._records) or record['decision_time']<=self.last_decision:raise ValueError('Require a causal increasing prefix')
        self._records[i]=copy.deepcopy(record);self.last_decision=record['decision_time']
        if ok:
            self.eligible_windows.append(i);self.maximum=max(self.maximum,float(record['score']))
            if self.first_crossing is None and record['score']>self.threshold:self.first_crossing={'window_index':i,'event_time':record['event_time'],'decision_time':record['decision_time'],'score':record['score'],'input_sha256':record['input_sha256']}
        self.last_reasons=reasons
        return self.snapshot()

    def snapshot(self,duplicate=False):
        completed=len(self._records)==self.protocol['horizon_windows']
        budget=len(self.eligible_windows)>=self.rule['required_eligible_windows']
        healthy=completed and budget and self.first_crossing is None and self.maximum<=self.rule['healthy_max_score'] and math.isfinite(self.threshold)
        return {'state':'ALARM_LATCHED' if self.first_crossing else 'HEALTHY_CRITERIA_MET' if healthy else 'HOLD',
            'first_crossing':copy.deepcopy(self.first_crossing),'eligible_windows':len(self.eligible_windows),'required_eligible_windows':self.rule['required_eligible_windows'],
            'completed_horizon':completed,'healthy_ready':healthy,'maximum_eligible_score':encode_threshold(self.maximum),'threshold':encode_threshold(self.threshold),
            'quality_reasons':getattr(self,'last_reasons',['no_eligible_data']),'duplicate':duplicate}
