"""Causal resource advisories from observed counters, separate from latency inference."""
from dataclasses import dataclass,asdict
import math
import hashlib
import json


@dataclass(frozen=True)
class ResourceHealthPolicy:
    policy_id:str='resource-health-dev-v1'
    window_seconds:int=10
    minimum_span_seconds:int=5
    minimum_samples:int=3
    minimum_processed:int=20
    growth_mb_per_request:float=.05
    growth_mb_per_second:float=.5
    pressure_fraction:float=.8

    def __post_init__(self):
        if self.policy_id!='resource-health-dev-v1':raise ValueError('Unknown resource health policy version')
        for key,maximum in [('window_seconds',3600),('minimum_span_seconds',3600),('minimum_samples',10000),('minimum_processed',1000000)]:
            v=getattr(self,key)
            if type(v) is not int or not 1<=v<=maximum:raise ValueError('Invalid '+key)
        if self.minimum_span_seconds>self.window_seconds:raise ValueError('Minimum span exceeds advisory window')
        for key in ('growth_mb_per_request','growth_mb_per_second','pressure_fraction'):
            v=getattr(self,key)
            if type(v) not in (float,int) or not math.isfinite(v) or v<=0:raise ValueError('Invalid '+key)
        if self.pressure_fraction>1:raise ValueError('pressure_fraction exceeds 1')


def summarize(rows,now,policy=ResourceHealthPolicy()):
    """Never read release parameters, fault labels or detector outputs."""
    by_host={}
    for row in rows:
        if row['simulated_seconds']<=now and now-row['simulated_seconds']<=policy.window_seconds:
            by_host.setdefault(row['host_id'],[]).append(row)
    result=[]
    for hid,history in sorted(by_host.items()):
        history=sorted(history,key=lambda r:r['simulated_seconds']);last=history[-1]
        # Restart OR OOM ends an allocation lifetime. Never bridge that boundary.
        history=[r for r in history if (r['process_generation'],r['oom_count'])==(last['process_generation'],last['oom_count'])]
        span=last['simulated_seconds']-history[0]['simulated_seconds']
        processed=sum(r['processed'] for r in history[1:])
        delta=last['memory_retained_mb']-history[0]['memory_retained_mb']
        per_request=delta/processed if processed else None
        per_second=delta/span if span else None
        fresh=last['simulated_seconds']==now
        enough=fresh and last['available'] and len(history)>=policy.minimum_samples and span>=policy.minimum_span_seconds
        request_warning=enough and processed>=policy.minimum_processed and per_request>=policy.growth_mb_per_request and per_second>=policy.growth_mb_per_second
        # Idle growth is deliberately a separate criterion, never divided by zero.
        idle_warning=enough and processed==0 and per_second>=policy.growth_mb_per_second
        growth_eligible=enough and (processed==0 or processed>=policy.minimum_processed)
        pressure=last['memory_mb']/last['memory_capacity_mb']>=policy.pressure_fraction
        flags=[]
        if not fresh:flags.append('stale_resource_data')
        if not last['available']:flags.append('unavailable_resource_data')
        if 0<processed<policy.minimum_processed:flags.append('insufficient_request_count')
        if 'OOM' in last['process_state']:flags.append('process_unavailable_after_oom')
        if pressure:flags.append('observed_low_headroom')
        if request_warning or idle_warning:flags.append('observed_memory_growth_warning')
        if not growth_eligible:flags.append('insufficient_growth_history')
        result.append({'host_id':hid,'policy_id':policy.policy_id,'criteria_provenance':'development-defined engineering criteria; not a calibrated SSM policy',
            'status':'stale' if not fresh else 'process_unavailable' if 'OOM' in last['process_state'] else 'advisory' if pressure or request_warning or idle_warning else 'insufficient_data' if not growth_eligible else 'no_current_resource_warning',
            'flags':flags,'label':'Observed memory-growth warning' if request_warning or idle_warning else 'Resource-health advisory',
            'interpretation':'Observed resource behavior; not SSM proof of a code-level leak. Cache warmup can warn too.',
            'request_growth_eligible':enough and processed>=policy.minimum_processed,'idle_growth_eligible':enough and processed==0,
            'span_seconds':span,'processed_requests':processed,'retained_delta_mb':delta,
            'growth_mb_per_request':per_request,'growth_mb_per_second':per_second,
            'memory_headroom_mb':last['memory_headroom_mb'],'process_restart_count':last['process_restart_count'],
            'oom_count':last['oom_count'],'fresh':fresh,'latency_detector_decision':None,'automatic_action':None})
    return {'policy':asdict(policy),'policy_sha256':hashlib.sha256(json.dumps(asdict(policy),sort_keys=True).encode()).hexdigest(),'advisories':result,'separate_from_latency_detector':True}
