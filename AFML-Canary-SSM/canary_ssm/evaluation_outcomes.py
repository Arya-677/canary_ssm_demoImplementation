"""EVALUATOR ONLY: prediction/hidden-target joins never enter public scoring."""
import numpy as np
from .metrics import event_truth, classify, localization, host_auc, brier, _runs
from .baselines import DetectorOutput
from .schema import KAPPA

def interval_event(mask,duration=15):
    mask=np.asarray(mask,bool);intervals=[(j,s,e) for j in range(mask.shape[1]) for s,e in _runs(mask[:,j]) if e-s>=duration]
    return dict(J=mask,has_event=bool(intervals),onset=min(s for j,s,e in intervals) if intervals else None,intervals=intervals,affected=sorted({j for j,s,e in intervals}),transient=bool(mask.any() and not intervals))

def research_target(truth,n):
    return event_truth(truth,n),dict(target_id='research-latent-strict-2pct-D15-v1',target_unknown_windows=0,target_status='defined',nature='injected latent host effect; original research target')

def world_release_target(null,harm,canaries,structural_null=False):
    if null.host_ids!=harm.host_ids or not np.array_equal(null.times,harm.times):raise ValueError('Paired world grids differ')
    ids=[harm.host_ids.index(h) for h in canaries];obs=null.observed[:,ids]&null.fresh[:,ids]&harm.observed[:,ids]&harm.fresh[:,ids]
    delta=np.where(obs,harm.y[:,ids]-null.y[:,ids],np.nan);ev=interval_event(np.isfinite(delta)&(delta>KAPPA))
    unknown=int((~obs[60:]).any(1).sum())
    status='structural_neutral_release_null' if structural_null else 'defined_positive' if ev['has_event'] else 'partially_unknown' if unknown else 'defined_no_qualifying_event'
    return ev,dict(target_id='offline-paired-completion-logmean-D15-v1',target_unknown_windows=unknown,target_status=status,nature='offline same-exogenous paired completion statistic; NOT an observed online counterfactual',structural_null=bool(structural_null)),delta

def world_infrastructure_target(private,public):
    index={h:i for i,h in enumerate(public.host_ids)};ti={float(t):i for i,t in enumerate(public.times)};active=np.zeros_like(public.observed)
    for row in private['records']:
        if row['fault_type']:active[ti[float(row['event_time'])],index[row['host_id']]]=True
    return interval_event(active,1),dict(target_id='operator-infrastructure-window-v1',target_unknown_windows=0,target_status='defined',nature='operator targeted infrastructure/shared-disturbance intervals; not release attribution')

def first_crossing(output,threshold):
    hits=np.flatnonzero(output['eligible']&np.isfinite(output['score'])&(output['score']>threshold))
    return int(hits[0]) if len(hits) else None

def evaluate(output,threshold,event,target,target_hosts,research=False):
    alarm=first_crossing(output,threshold);T=len(output['score']);result=classify(alarm,event,T)
    if target['target_status']=='partially_unknown' and not event['has_event']:result.update(status='unverifiable_target',kind='unknown',capped=np.nan)
    prob=output['host_rank'] if output['output_kind']=='conditional_gaussian_posterior' else None
    adapter=DetectorOutput('offline',output['score'],output['eligible'],output['host_rank'],prob)
    loc=auc=fresh_loc=None;reason='no qualifying event';fresh=False;affected=[target_hosts[i] for i in event['affected']]
    if event['has_event']:
        if any(h not in output['host_ids'] for h in affected):reason='target includes hosts outside monitored cohort'
        elif event['onset']+30>=T:reason='insufficient follow-up for onset+30'
        else:
            mapped={**event,'affected':[output['host_ids'].index(h) for h in affected]};fresh=bool(output['eligible'][event['onset']+30])
            canonical=localization(adapter,mapped,landmark=30,topk=3,cutoff=3);fresh_loc=canonical if fresh else None
            loc=canonical if research or fresh else None;auc=host_auc(adapter,mapped,landmark=30) if research or fresh else None
            reason='fresh landmark' if fresh else 'prediction-only landmark'
    start=int(np.searchsorted(output['times'],output['exposure_time']));count=int(output['eligible'][start:].sum());horizon=T-start
    return {**result,**target,'alarm_index':alarm,'onset_index':event['onset'],'eligible_windows':count,'horizon_windows':horizon,'abstention_fraction':1-count/max(1,horizon),'no_eligible_data':count==0,'localization_time_index':event['onset']+30 if event['has_event'] else None,'localization_status':reason,'localization_input_fresh':fresh,'top3_recall':loc['top3_recall'] if loc else None,'fresh_top3_recall':fresh_loc['top3_recall'] if fresh_loc else None,'localization_precision':loc['cut_precision'] if loc else None,'localization_recall':loc['cut_recall'] if loc else None,'host_auc':auc,'brier':brier(adapter,event,start) if research and prob is not None else None,'unmonitored_affected_hosts':sum(h not in output['host_ids'] for h in affected),'probability_contract':'conditional marginal Gaussian risk' if prob is not None else 'classical statistic; no posterior'}

def interference(null,harm,nm,hm,canaries):
    controls=[h for h in harm.host_ids if h not in canaries];ids=[harm.host_ids.index(h) for h in controls];mask=null.observed[:,ids]&harm.observed[:,ids]
    diff=np.where(mask,harm.y[:,ids]-null.y[:,ids],np.nan);a={(r['tick'],r['host_id']):r for r in nm['resource_hosts']};b={(r['tick'],r['host_id']):r for r in hm['resource_hosts']}
    routing=sum(abs(a[k]['routed_requests']-b[k]['routed_requests']) for k in a if k[1] in controls);queues=sum(a[k]['queue_end']!=b[k]['queue_end'] for k in a if k[1] in controls)
    delta=float(np.nanmax(np.abs(diff))) if mask.any() else None
    return dict(exogenous_uniforms_identical=nm['exogenous']==hm['exogenous'],noncanary_max_abs_log_latency_delta=delta,noncanary_routing_request_difference=int(routing),noncanary_queue_divergence_windows=int(queues),canary_queue_divergence_windows=int(sum(a[k]['queue_end']!=b[k]['queue_end'] for k in a if k[1] in canaries)),observed_cross_host_interference=bool(routing or queues or delta is not None and delta>1e-12),additive_identity_required=False,online_counterfactual_observed=False,coupling_contract='fixed cohort routing and local queues; rollback can restart whole service')
