"""Freeze development lineage, calibrate null maxima, audit independent nulls. No inference truth."""
import copy,math,hashlib,json
import numpy as np
import scipy
from pathlib import Path
from decimal import Decimal,ROUND_CEILING
from scipy.stats import beta,betabinom
from .telemetry import identifier
from .policy_hash import digest
from .first_crossing import HASH_KEYS,hash_value,rule,validate_rule,validate_protocol,eligibility,LatchedFirstCrossing,encode_threshold,decode_threshold

ROOT=Path(__file__).parent


def sources(names):return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}

def seal(value,key):
    result=copy.deepcopy(value);result.pop(key,None);result[key]=digest(result);return result

def checked(value,key):
    result=copy.deepcopy(value);expected=result.pop(key,None)
    if expected!=digest(result):raise ValueError('Artifact content hash mismatch: '+key)
    return copy.deepcopy(value)

def identities(rows,role):
    ids=[];seeds=[]
    for r in rows:
        if r['role']!=role:raise ValueError('Data roles may not mix')
        identifier(r['run_id'],'run_id')
        if type(r['seed']) is not int or r['seed']<0:raise ValueError('Require registered independent seed provenance')
        ids.append(r['run_id']);seeds.append(r['seed'])
    if not rows or len(set(ids))!=len(ids) or len(set(seeds))!=len(seeds):raise ValueError('Require independent rollout IDs and seeds')
    return set(ids),set(seeds)

def freeze_development(preprocessing_model,effect_settings,simulator,p,development,settings=None):
    validate_protocol(p);identities(development,'development')
    if any(r.get('declared_healthy') is not True for r in development):raise ValueError('Freeze only healthy development data')
    if not preprocessing_model.get('development_lineage') or any(x['role']!='development' or x.get('healthy_attestation') is not True for x in preprocessing_model['development_lineage']):raise ValueError('Preprocessing must be fitted on development only')
    from .public_adjustment import FrozenAdjustment
    from .public_filter import GaussianEffects
    from .hierarchy import EffectParams
    model=FrozenAdjustment(preprocessing_model)
    if effect_settings.get('kind')=='grouped':
        from .public_hierarchy import GroupedParams,GroupedGaussianEffects,grouped_structure
        params=GroupedParams(**{k:v for k,v in effect_settings.items() if k!='kind'})
        if params.group_by!=p['group_by']:raise ValueError('Grouped model and preprocessing grouping differ')
        data=model.to_dict();indices=[data['host_ids'].index(h) for h in data['canary_ids']]
        labels=[data['rack_ids'][i] if p['group_by']=='rack_id' else data['class_ids'][i] for i in indices]
        GroupedGaussianEffects(grouped_structure(data['canary_ids'],labels,p['group_by']),params)
    else:GaussianEffects(EffectParams(**effect_settings))
    if sorted(model.to_dict()['canary_ids'])!=sorted(p['canaries']) or model.policy.group_by!=p['group_by']:raise ValueError('Frozen preprocessing cohort/grouping differs')
    payload=model.to_dict();index={h:i for i,h in enumerate(payload['host_ids'])}
    if any(h not in index for h in p['canaries']+p['controls']):raise ValueError('Protocol host outside fitted preprocessing roster')
    def group(h):return ('rack:'+str(payload['rack_ids'][index[h]])) if p['group_by']=='rack_id' else ('class:'+str(payload['class_ids'][index[h]]))
    expected_groups={g:sorted(h for h in p['controls'] if group(h)==g) for g in {group(h) for h in p['canaries']}}
    if p['groups']!=expected_groups:raise ValueError('Require controls in every represented fitted group')
    if not model.to_dict().get('noise_fit_ok'):raise ValueError('Healthy AR noise fitting failed; freeze cannot hide fit failures')
    fit_ids={x['public_sha256'] for x in preprocessing_model['development_lineage']}
    if {x.get('public_sha256') for x in development}!=fit_ids:raise ValueError('Development provenance does not match frozen fit inputs')
    settings=copy.deepcopy(settings or rule(p['horizon_windows']));validate_rule(settings,p['horizon_windows'])
    payload={'versions':{'numpy':np.__version__,'scipy':scipy.__version__},'format':'frozen-policy-inputs-v1','preprocessing_model':copy.deepcopy(preprocessing_model),'effect_settings':copy.deepcopy(effect_settings),
        'simulator':copy.deepcopy(simulator),'protocol':copy.deepcopy(p),'rule':settings,'development':copy.deepcopy(development),
        'selection':'Predeclared effect settings; healthy-development preprocessing/AR fit only; no calibration or validation selection',
        'sources':{'model':sources(['public_filter.py','public_hierarchy.py','kalman.py','hierarchy.py','schema.py']),
                   'preprocessing':sources(['public_adjustment.py','preprocess.py','factor.py','policy_public.py']),
                   'policy':sources(['first_crossing.py','policy_artifacts.py','policy_control.py','policy_hash.py'])}}
    payload['hashes']={'model_hash':digest({'settings':effect_settings,'source':payload['sources']['model']}),
        'preprocessing_hash':digest({'fit':preprocessing_model,'source':payload['sources']['preprocessing']}),
        'simulator_hash':digest(simulator),'protocol_hash':digest({'configuration':p,'source':sources(['rollouts.py','first_crossing.py'])})}
    return seal(payload,'freeze_hash')

def validate_frozen(f):
    checked(f,'freeze_hash')
    if f['format']!='frozen-policy-inputs-v1':raise ValueError('Wrong frozen bundle')
    expected=freeze_development(f['preprocessing_model'],f['effect_settings'],f['simulator'],f['protocol'],f['development'],f['rule'])
    if expected!=f:raise ValueError('Frozen settings, lineage or source hashes changed')
    return copy.deepcopy(f)

def ordered_threshold(maxima,alpha=.05):
    if type(alpha) not in (int,float) or not math.isfinite(alpha) or not 0<alpha<1 or not maxima:raise ValueError('Require nonempty maxima and alpha in (0,1)')
    if any(math.isnan(float(x)) or float(x)==math.inf for x in maxima):raise ValueError('Maxima must be finite or no-data -infinity')
    B=len(maxima);k=int((Decimal(B+1)*(Decimal(1)-Decimal(str(alpha)))).to_integral_value(rounding=ROUND_CEILING))
    threshold=math.inf if k>B else sorted(maxima)[k-1]
    return {'B':B,'k':k,'alpha':float(alpha),'threshold':encode_threshold(threshold),'ties_at_threshold':sum(x==threshold for x in maxima)}

def full_trace(trace,frozen):
    if trace.get('declared_null') is not True:raise ValueError('Null calibration/validation requires declared null rollout provenance')
    if trace['hashes']!=frozen['hashes'] or trace.get('freeze_hash')!=frozen['freeze_hash']:raise ValueError('Incompatible model/preprocessing/simulator/protocol hashes')
    if trace['exposure_time']!=frozen['protocol']['baseline_seconds']+60:raise ValueError('Trace exposure differs from frozen fresh-run protocol')
    H=frozen['protocol']['horizon_windows'];records=trace['records']
    if len(records)!=H or [r['window_index'] for r in records]!=list(range(H)):raise ValueError('Use the complete frozen horizon, including missing minutes')
    state=LatchedFirstCrossing(frozen['protocol'],frozen['rule'],'+inf',exposure_time=trace['exposure_time'])
    for r in records:state.observe(r)
    return state.maximum,len(state.eligible_windows)

def no_overlap(left,right):
    if left[0]&right[0] or left[1]&right[1]:raise ValueError('Development/calibration/validation IDs and seeds must be disjoint')

def calibrate(frozen,traces):
    f=validate_frozen(frozen);cal_ids=identities(traces,'threshold-calibration');dev_ids=identities(f['development'],'development');no_overlap(dev_ids,cal_ids)
    maxima=[];lineage=[]
    for t in traces:
        m,n=full_trace(t,f);maxima.append(m);lineage.append({'run_id':t['run_id'],'seed':t['seed'],'role':t['role'],'maximum':encode_threshold(m),'eligible_windows':n,'trace_hash':digest(t)})
    threshold=ordered_threshold(maxima,f['rule']['alpha']);B,k=threshold['B'],threshold['k']
    interval=[0.,0.] if k>B else [float(beta.ppf(.025,B+1-k,k)),float(beta.ppf(.975,B+1-k,k))]
    status='CALIBRATED' if math.isfinite(decode_threshold(threshold['threshold'])) else 'INSUFFICIENT_ELIGIBLE_CALIBRATION'
    return seal({'format':'latched-release-policy-v1','frozen':f,'calibration':threshold,'calibration_lineage':lineage,
        'no_eligible_nulls':sum(n['eligible_windows']==0 for n in lineage),'status':status,
        'threshold_tail_probability_interval':interval,'interval_assumption':'Exact Beta quantiles for continuous iid null maxima; ties/no-data mass make this a diagnostic, not a conditional eligibility guarantee',
        'guarantee':'Marginal new-rollout false crossing bound under exchangeable independent null rollouts and the identical frozen horizon/eligibility/score pipeline; strict inequality and ties are conservative'},'policy_hash')

def validate_policy(p):
    checked(p,'policy_hash');f=validate_frozen(p['frozen'])
    if p['format']!='latched-release-policy-v1':raise ValueError('Wrong policy format')
    identities(p['calibration_lineage'],'threshold-calibration');no_overlap(identities(f['development'],'development'),identities(p['calibration_lineage'],'threshold-calibration'))
    expected=ordered_threshold([decode_threshold(x['maximum']) for x in p['calibration_lineage']],f['rule']['alpha'])
    if expected!=p['calibration']:raise ValueError('Calibrated threshold is not the fixed order statistic')
    status='CALIBRATED' if math.isfinite(decode_threshold(expected['threshold'])) else 'INSUFFICIENT_ELIGIBLE_CALIBRATION'
    if p['status']!=status or p['no_eligible_nulls']!=sum(x['eligible_windows']==0 for x in p['calibration_lineage']):raise ValueError('Calibration status/coverage mismatch')
    return copy.deepcopy(p)

def binomial_interval(k,n):return [0. if not k else float(beta.ppf(.025,k,n-k+1)),1. if k==n else float(beta.ppf(.975,k+1,n-k))]

def advisory_kinds(trace,f):
    result=set()
    for a in trace.get('advisories',[]):
        if set(a)!={'kind','window_index','source','evidence_hash'} or a['source']!='observed_metrics' or a['kind'] not in ('platform','resource') or type(a['window_index']) is not int or not 0<=a['window_index']<f['protocol']['horizon_windows']:raise ValueError('Advisories must be observed, in-horizon evidence; never injection labels')
        hash_value(a['evidence_hash'])
        if a['kind']=='platform' and f['rule']['platform_incidents']=='pause_only' or a['kind']=='resource' and f['rule']['resource_guardrails']=='observed_pause':result.add(a['kind'])
    return result

def validate_nulls(policy,traces):
    p=validate_policy(policy);f=p['frozen'];val_ids=identities(traces,'null-validation')
    no_overlap(val_ids,identities(f['development'],'development'));no_overlap(val_ids,identities(p['calibration_lineage'],'threshold-calibration'))
    outcomes=[]
    for t in traces:
        m,n=full_trace(t,f);state=LatchedFirstCrossing(f['protocol'],f['rule'],p['calibration']['threshold'],exposure_time=t['exposure_time'])
        for r in t['records']:state.observe(r)
        kinds=advisory_kinds(t,f);release=state.first_crossing is not None
        outcomes.append({'run_id':t['run_id'],'seed':t['seed'],'role':t['role'],'eligible_windows':n,'release_alarm':release,'platform_pause':'platform' in kinds,'resource_pause':'resource' in kinds,'combined_action':release or bool(kinds),'trace_hash':digest(t)})
    n=len(outcomes);eligible_rows=[x for x in outcomes if x['eligible_windows']>0];eligible_alarms=sum(x['release_alarm'] for x in eligible_rows);rates={}
    for name in ('release_alarm','platform_pause','resource_pause','combined_action'):
        count=sum(r[name] for r in outcomes);rates[name]={'events':count,'n':n,'rate':count/n,'exact_binomial_95_interval':binomial_interval(count,n)}
    B,k=p['calibration']['B'],p['calibration']['k'];count=rates['release_alarm']['events']
    pvalue=None if k>B else float(min(1.,2*min(betabinom.cdf(count,n,B+1-k,k),betabinom.sf(count-1,n,B+1-k,k))))
    gate='INSUFFICIENT_DATA' if B<2000 or n<2000 or p['status']!='CALIBRATED' else 'PASS' if pvalue is not None and pvalue>=.01 and count/n<=.075 else 'FAIL'
    return seal({'format':'latched-policy-null-validation-v1','policy_hash':p['policy_hash'],'frozen_hash':f['freeze_hash'],'outcomes':outcomes,'rates':rates,
        'no_eligible_nulls':sum(r['eligible_windows']==0 for r in outcomes),'eligible_rollouts':len(eligible_rows),
        'conditional_on_any_eligible':{'events':eligible_alarms,'n':len(eligible_rows),'rate':eligible_alarms/len(eligible_rows) if eligible_rows else None,'exact_binomial_95_interval':binomial_interval(eligible_alarms,len(eligible_rows)) if eligible_rows else None,'nominal_alpha_guarantee':False},'no_retuning':True,'gate':{'status':gate,'minimum_B':2000,'minimum_n':2000,'bb_pvalue_two_sided':pvalue,'rejection_level':.01,'maximum_empirical_release_rate':.075,'note':'G2-style conditional diagnostic; Beta-Binomial continuity/exchangeability assumptions are explicit. Combined action FAR is reported separately and is not controlled at release alpha.'}},'validation_hash')

def validated_attachment(policy,validation):
    p=validate_policy(policy);checked(validation,'validation_hash')
    if validation['policy_hash']!=p['policy_hash'] or validation['frozen_hash']!=p['frozen']['freeze_hash']:raise ValueError('Validation belongs to another frozen policy')
    # Recompute counts, independence and gate rather than trusting a supplied PASS label.
    outcomes=validation['outcomes'];ids=identities(outcomes,'null-validation');no_overlap(ids,identities(p['calibration_lineage'],'threshold-calibration'));no_overlap(ids,identities(p['frozen']['development'],'development'))
    for key in ('release_alarm','platform_pause','resource_pause','combined_action'):
        for row in outcomes:
            if any(type(row[k]) is not bool for k in ('release_alarm','platform_pause','resource_pause','combined_action')) or row['combined_action']!=(row['release_alarm'] or row['platform_pause'] or row['resource_pause']):raise ValueError('Invalid validation event ledger')
        count=sum(r[key] for r in outcomes);expected={'events':count,'n':len(outcomes),'rate':count/len(outcomes),'exact_binomial_95_interval':binomial_interval(count,len(outcomes))}
        if validation['rates'][key]!=expected:raise ValueError('Validation rate/uncertainty mismatch')
    B,k=p['calibration']['B'],p['calibration']['k'];n=len(outcomes);count=validation['rates']['release_alarm']['events']
    pv=None if k>B else float(min(1.,2*min(betabinom.cdf(count,n,B+1-k,k),betabinom.sf(count-1,n,B+1-k,k))))
    if B<2000 or n<2000 or p['status']!='CALIBRATED' or pv is None or pv<.01 or count/n>.075 or validation['gate']['status']!='PASS' or validation['gate']['bb_pvalue_two_sided']!=pv:raise ValueError('Independent validation gate is insufficient or failed; no automatic actions')
    return p


def main():
    import argparse
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    for name in ('calibrate','validate'):
        q=sub.add_parser(name);q.add_argument('--input',required=True);q.add_argument('--traces',required=True);q.add_argument('--out',required=True)
    a=ap.parse_args();data=json.loads(Path(a.input).read_text());traces=json.loads(Path(a.traces).read_text());result=calibrate(data,traces) if a.command=='calibrate' else validate_nulls(data,traces)
    Path(a.out).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({'output':a.out,'hash':result.get('policy_hash',result.get('validation_hash')),'status':result.get('status',result.get('gate'))}))
if __name__=='__main__':main()
