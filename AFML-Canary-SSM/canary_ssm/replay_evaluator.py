"""Offline role-separated replay study; final data are sealed behind computed gates."""
import argparse
import csv
import gzip
import hashlib
import json
import platform
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import scipy
from scipy.stats import betabinom
from .evaluation_inputs import SCENARIOS, identity, mixture_case, generate, generate_registered, save_bundle, load_public
from .evaluation_scoring import compare, fit_public, COMMON_METHODS, WORLD_METHODS
from .evaluation_outcomes import research_target, world_release_target, world_infrastructure_target, evaluate, interference
from .public_adjustment import serial
from .policy_artifacts import ordered_threshold
from .first_crossing import encode_threshold, decode_threshold
from .metrics import clopper_pearson

STUDY_ID='truth-separated-replay-v2-linux-rebuild'
ROOT=Path(__file__).resolve().parents[1]
SOURCES=('evaluation_inputs.py','evaluation_scoring.py','evaluation_outcomes.py','replay_evaluator.py','simulate.py','resources.py','engine.py','public_adjustment.py','public_filter.py','public_hierarchy.py','nested_hierarchy.py','preprocess.py','factor.py','kalman.py','baselines.py','schema.py','metrics.py','telemetry.py','telemetry_transport.py','telemetry_evaluator.py','rollouts.py','operations.py','faults.py','fault_scheduler.py','releases.py','resource_health.py','topology.py','seeds.py','policy_control.py','policy_artifacts.py','policy_public.py','policy_hash.py','first_crossing.py')

def digest(value):return hashlib.sha256(json.dumps(serial(value),sort_keys=True,allow_nan=False).encode()).hexdigest()
def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes():return {**{f:file_hash(Path(__file__).with_name(f)) for f in SOURCES},'configs/world_policy_v1.yaml':file_hash(ROOT/'configs/world_policy_v1.yaml')}
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(serial(value),indent=2,allow_nan=False)+'\n')
def table(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:'' if v is None or isinstance(v,float) and not np.isfinite(v) else v for k,v in r.items()} for r in rows])
def read_table(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))
def public_id(public):return getattr(public,'run_id',getattr(public,'rollout_id',None))
def public_fingerprint(generator,p):
    if generator=='world':return p.fingerprint()
    h=hashlib.sha256()
    for a in (p.y,p.x,p.observed,p.decision_obs,p.class_id,p.exposed,p.request_count):h.update(np.ascontiguousarray(a).tobytes())
    h.update(str(p.t0).encode());return h.hexdigest()
def save_scores(path,outputs,host_ranks=True):
    values={}
    for name,out in outputs.items():
        values[name+'__score']=out['score'];values[name+'__eligible']=out['eligible']
        if host_ranks:values[name+'__host_rank']=out['host_rank']
    np.savez_compressed(path,**values)

def pair(generator,role,index,scenario,directory,final_authorized=False):
    out={}
    for member in ('null','harm'):
        if role=='final-test':
            if not final_authorized:raise ValueError('Final-test inputs are sealed')
            seed,_=identity(generator,role,index,scenario);rid=('r-' if generator=='research' else 'w-')+hashlib.sha256((str(seed)+':'+member).encode()).hexdigest()[:24]
            p,t,m=generate_registered(generator,seed,rid,scenario,member)
        else:p,t,m=generate(generator,role,index,scenario,member)
        save_bundle(generator,p,t,m,Path(directory)/member,True);out[member]=(p,t,m)
    return out

def select_development(generator,out,offset):
    healthy=[];lineage=[]
    for i in range(3):
        p,t,m=generate(generator,'development',offset+i,'healthy','null',healthy_fit=True)
        save_bundle(generator,p,t,m,out/'inputs/fit'/str(i));healthy.append(p)
        canaries=m.get('canaries',[f'h{i:02}' for i in range(8)])
        lineage.append(dict(seed=m['seed'],run_id=public_id(p),public_sha256=public_fingerprint(generator,p),role='development'))
    models=fit_public(generator,healthy,canaries);write(out/'models.json',models)
    methods=COMMON_METHODS if generator=='research' else WORLD_METHODS
    losses={(name,sd):[0.,0] for name in methods if name not in ('adj_ewma','adj_cusum','topk_cusum') for sd in (.003,.008)};rows=[]
    for scenario in ('broad_release_harm','recovery','transient_harm') if generator=='research' else ('broad_release_harm','recovery','memory_retention_latency'):
        pp=pair(generator,'development',offset,scenario,out/'inputs/selection'/scenario);hp,ht,hm=pp['harm'];npub,nt,nm=pp['null']
        target=ht.a[:,:8] if generator=='research' else world_release_target(npub,hp,canaries)[2]
        for sd in (.003,.008):
            outputs=compare(generator,hp,models,{name:sd for name in methods},hm.get('rack_ids'))
            for name,r in outputs.items():
                if r['mean'] is None:continue
                mask=np.isfinite(target)&np.isfinite(r['mean'])&r['eligible'][:,None];loss=float(np.sum((r['mean'][mask]-target[mask])**2));n=int(mask.sum())
                losses[name,sd][0]+=loss;losses[name,sd][1]+=n;rows.append(dict(method=name,sd=sd,scenario=scenario,squared_error_sum=loss,eligible_host_windows=n,role='development',criterion='all-host-window squared error; no true affected count'))
        lineage.extend(dict(seed=m['seed'],run_id=public_id(p),public_sha256=public_fingerprint(generator,p),role='development') for p,t,m in pp.values())
    settings={};decisions=[]
    for name in methods:
        if name in ('adj_ewma','adj_cusum','topk_cusum'):settings[name]=.005;continue
        valid=[(s/n,sd) for (method,sd),(s,n) in losses.items() if method==name and n];settings[name]=min(valid)[1] if valid else .005
        decisions.append(dict(method=name,sd=settings[name],status='selected_on_development' if valid else 'no_eligible_data_predeclared_fallback'))
    table(out/'development_selection.csv',rows);write(out/'development_decisions.json',decisions)
    return models,settings,lineage

def null_job(job):
    generator,endpoint,role,i,offset,out,models,settings=job
    directory=Path(out)/'inputs'/role/endpoint/str(i);signature=digest(dict(sources=source_hashes(),models=models,settings=settings,generator=generator,endpoint=endpoint,role=role,index=i,offset=offset))
    cache=directory/'sample_rows.json'
    if cache.exists():
        c=json.loads(cache.read_text())
        if c['signature']!=signature or c['score_sha256']!=file_hash(directory/'scores.npz'):raise ValueError('Frozen cache modified')
        if c['public_file_sha256']!=file_hash(directory/'public/input.npz'):raise ValueError('Frozen public input modified')
        if c['truth_file_sha256']!=file_hash(directory/c['truth_path']):raise ValueError('Frozen evaluator input modified')
        return c['rows']
    index=offset+i+(3000 if endpoint=='infrastructure' else 0);seed,_=identity(generator,role,index,'healthy');scenario='healthy' if endpoint=='infrastructure' else mixture_case(seed)
    p,t,m=generate(generator,role,index,scenario,'null',seed_scenario='healthy');save_bundle(generator,p,t,m,directory)
    if generator=='research' and np.any(t.a):raise ValueError('Non-null calibration input')
    if generator=='world' and not m['structural_release_null']:raise ValueError('Nonneutral release in null calibration')
    outputs=compare(generator,p,models,settings,m.get('rack_ids'));save_scores(directory/'scores.npz',outputs,False);score_hash=file_hash(directory/'scores.npz');rows=[]
    for name,r in outputs.items():
        use=r['eligible']&np.isfinite(r['score']);value=float(np.max(r['score'][use])) if use.any() else -np.inf
        rows.append(dict(method=name,run_id=public_id(p),seed=seed,role=role,null_family=scenario,maximum=encode_threshold(value),eligible_windows=int(use.sum()),public_sha256=public_fingerprint(generator,p),sample_index=i,score_sha256=score_hash))
    truth_path='evaluator/truth.npz' if generator=='research' else 'evaluator/truth.json.gz'
    write(cache,dict(signature=signature,score_sha256=score_hash,public_file_sha256=file_hash(directory/'public/input.npz'),truth_file_sha256=file_hash(directory/truth_path),truth_path=truth_path,rows=rows))
    return rows

def null_samples(generator,endpoint,role,count,offset,out,models,settings,workers):
    rows=[];maxima={name:[] for name in settings};counts={name:[] for name in settings}
    jobs=((generator,endpoint,role,i,offset,str(out),models,settings) for i in range(count))
    with ProcessPoolExecutor(max_workers=min(workers,count)) as pool:
        for i,batch in enumerate(pool.map(null_job,jobs,chunksize=1)):
            rows.extend(batch)
            for r in batch:maxima[r['method']].append(decode_threshold(r['maximum']));counts[r['method']].append(r['eligible_windows'])
            if (i+1)%100==0:print(json.dumps(dict(generator=generator,endpoint=endpoint,role=role,completed=i+1,total=count)),flush=True)
    return rows,maxima,counts

def calibrate(generator,endpoint,out,models,settings,B,n,offset,freeze_hash,workers):
    rows,maxima,_=null_samples(generator,endpoint,'threshold-calibration',B,offset,out,models,settings,workers)
    policies={name:ordered_threshold(v,.05) for name,v in maxima.items()};bundle=dict(generator=generator,endpoint=endpoint,freeze_hash=freeze_hash,B=B,alpha=.05,policies=policies,horizon=120 if generator=='research' else 60,calibration_ledger_sha256=digest(rows),null_distribution='all-healthy platform-null' if endpoint=='infrastructure' else 'iid hash-selected uniform six-family mixture')
    bundle['policy_hash']=digest(bundle);write(out/(endpoint+'_policy.json'),bundle);table(out/(endpoint+'_calibration_maxima.csv'),rows)
    vr,vm,counts=null_samples(generator,endpoint,'null-validation',n,offset,out,models,settings,workers);table(out/(endpoint+'_validation_maxima.csv'),vr);validation=[]
    for name,values in vm.items():
        threshold=decode_threshold(policies[name]['threshold']);events=sum(v>threshold for v in values);lo,hi=clopper_pearson(events,n);k=policies[name]['k']
        pv=float(min(1.,2*min(betabinom.cdf(events,n,B+1-k,k),betabinom.sf(events-1,n,B+1-k,k)))) if k<=B else None
        gate='INSUFFICIENT' if min(B,n)<2000 or not np.isfinite(threshold) else 'PASS' if pv is not None and pv>=.01 and events/n<=.075 else 'FAIL'
        validation.append(dict(generator=generator,endpoint=endpoint,method=name,B=B,k=k,n=n,alerts=events,rate=events/n,ci_lower=lo,ci_upper=hi,no_eligible_nulls=sum(c==0 for c in counts[name]),eligible_rollouts=sum(c>0 for c in counts[name]),threshold=encode_threshold(threshold),bb_pvalue_two_sided=pv,gate=gate,role='null-validation',policy_hash=bundle['policy_hash'],no_retuning=True,calibration_threshold_ties=sum(v==threshold for v in maxima[name]),scope='mixture audit only; not per-family qualification' if endpoint!='infrastructure' else 'healthy platform null',continuity_assumption='Beta-binomial diagnostic assumes continuous maxima; strict ties remain conservative'))
    table(out/(endpoint+'_null_intervals.csv'),validation);receipt=dict(policy_hash=bundle['policy_hash'],rows=validation,validation_ledger_sha256=digest(vr));receipt['validation_hash']=digest(receipt);write(out/(endpoint+'_validation.json'),receipt)
    return bundle,validation

def scenario_rows(generator,role,out,models,settings,policies,validation,offset,final_authorized=False):
    rows=[];pairs=[];gates={(v['endpoint'],v['method']):v['gate'] for v in validation}
    for scenario in SCENARIOS:
        pp=pair(generator,role,offset,scenario,out/'inputs'/role/scenario,final_authorized);npub,nt,nm=pp['null'];hp,ht,hm=pp['harm']
        if generator=='research':
            mask=npub.observed&hp.observed;error=float(np.max(np.abs((hp.y-npub.y-(ht.a-nt.a)-(ht.spill-nt.spill))[mask])))
            if error>1e-12:raise ValueError('Original additive paired identity broken')
            pairs.append(dict(scenario=scenario,exact_additive_identity=True,max_abs_error=error))
        else:pairs.append(dict(scenario=scenario,**interference(npub,hp,nm,hm,hm['canaries'])))
        for member,(p,t,m) in pp.items():
            outputs=compare(generator,p,models,settings,m.get('rack_ids'));save_scores(out/'inputs'/role/scenario/member/'scores.npz',outputs)
            endpoints={}
            if generator=='research':endpoints['latent_effect']=(*research_target(t,8),list(next(iter(outputs.values()))['host_ids']))
            else:
                ev,target,_=world_release_target(npub,p,m['canaries'],m['structural_release_null']);endpoints['release_latency']=(ev,target,m['canaries'])
                ev,target=world_infrastructure_target(t,p);endpoints['infrastructure']=(ev,target,list(p.host_ids))
            for endpoint,(event,target,hosts) in endpoints.items():
                for name,r in outputs.items():
                    row=evaluate(r,decode_threshold(policies[endpoint]['policies'][name]['threshold']),event,target,hosts,generator=='research')
                    if generator=='research' and scenario.startswith('memory_retention'):row.update(status='not_supported_by_generator',kind='unsupported',capped=np.nan)
                    rows.append(dict(generator=generator,generator_id=m['generator_id'],role=role,scenario=scenario,member=member,run_id=public_id(p),seed=m['seed'],physical_mechanism_supported=m['physical_mechanism_supported'],endpoint=endpoint,method=name,calibration_gate=gates[endpoint,name],public_sha256=public_fingerprint(generator,p),**row))
    table(out/('research_results.csv' if generator=='research' else 'resource_world_results.csv'),rows);table(out/'pairing_and_interference.csv',pairs);return rows

def checked_freeze(root):
    f=json.loads((Path(root)/'development_freeze.json').read_text());expected=f.pop('freeze_hash')
    if digest(f)!=expected or f['sources']!=source_hashes():raise ValueError('Development/source freeze changed')
    if f['versions']['numpy']!=np.__version__ or f['versions']['scipy']!=scipy.__version__:raise ValueError('Frozen numerical runtime changed')
    return {**f,'freeze_hash':expected}

def run(directory,B=2000,n_validation=2000,offset=12000,workers=6,resume=False):
    if not 1<=B<=2000 or not 1<=n_validation<=2000 or not 11000<=offset<=15000 or offset+max(B,n_validation)+3000>20000 or not 1<=workers<=8:raise ValueError('Invalid study/registered seed budget')
    root=Path(directory)
    if resume:
        f=checked_freeze(root)
        if (f['B'],f['n_validation'],f['offset'])!=(B,n_validation,offset):raise ValueError('Resume cannot change frozen audit')
    else:
        if (root/'development_freeze.json').exists():raise ValueError('Study exists; verified resume required')
        models={};settings={};lineage={}
        for gen in ('research','world'):models[gen],settings[gen],lineage[gen]=select_development(gen,root/gen,offset)
        f=dict(study_id=STUDY_ID,B=B,n_validation=n_validation,offset=offset,models=models,settings=settings,development_lineage=lineage,sources=source_hashes(),versions={'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},development_selection_complete=True,final_test_opened=False)
        f['freeze_hash']=digest(f);write(root/'development_freeze.json',f)
        write(root/'final_test_lock.json',dict(freeze_hash=f['freeze_hash'],inputs_materialized=False,plan=[dict(generator=g,scenario=s,seed=identity(g,'final-test',offset,s)[0],members=['null','harm']) for g in ('research','world') for s in SCENARIOS],unlock='all computed qualification gates and raw content hashes; no retuning'))
    validation=[];counts={}
    for gen in ('research','world'):
        policies={};gv=[]
        for endpoint in ('latent_effect',) if gen=='research' else ('release_latency','infrastructure'):
            policies[endpoint],vv=calibrate(gen,endpoint,root/gen,f['models'][gen],f['settings'][gen],B,n_validation,offset,f['freeze_hash'],workers);validation+=vv;gv+=vv
        counts[gen]=len(scenario_rows(gen,'smoke',root/gen,f['models'][gen],f['settings'][gen],policies,gv,offset))
    table(root/'independent_null_intervals.csv',validation)
    from collections import Counter
    checks=dict(study_id=STUDY_ID,B=B,n_validation=n_validation,freeze_hash=f['freeze_hash'],gates=dict(Counter(v['gate'] for v in validation)),diagnostic_rows=counts,final_test_materialized=False,comparative_efficacy_claim=False)
    write(root/'checks.json',checks);return checks

def require_final(directory):
    root=Path(directory);f=checked_freeze(root)
    if min(f['B'],f['n_validation'])<2000:raise ValueError('Final access requires at least 2000 calibration and validation nulls')
    # This version deliberately never opens final data: the new mixture audit is
    # not the governing plan's per-family gate. Explicitly preserve that gap.
    raise ValueError('Final-test remains sealed: per-family qualification required; mixture audit is diagnostic only')

def replay_null(directory,generator,endpoint,role,index):
    import tempfile
    root=Path(directory);f=checked_freeze(root);saved=root/generator/'inputs'/role/endpoint/str(index)
    cache=json.loads((saved/'sample_rows.json').read_text())
    with tempfile.TemporaryDirectory(prefix='replay-null-') as tmp:
        job=(generator,endpoint,role,index,f['offset'],tmp,f['models'][generator],f['settings'][generator]);rows=null_job(job);new=Path(tmp)/'inputs'/role/endpoint/str(index)
        same=rows==cache['rows']
        # gzip header/NPZ timestamps need not be byte stable; compare semantic truth.
        path=cache['truth_path']
        if generator=='world':
            with gzip.open(saved/path,'rt') as a,gzip.open(new/path,'rt') as b:same &= json.load(a)==json.load(b)
        else:
            with np.load(saved/path) as a,np.load(new/path) as b:same &= all(np.array_equal(a[k],b[k],equal_nan=True) for k in a.files)
    return dict(generator=generator,endpoint=endpoint,role=role,index=index,identical=bool(same))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['run','check-final-lock','replay-null']);p.add_argument('--out',default='examples/evaluator_v2');p.add_argument('--B',type=int,default=2000);p.add_argument('--n-validation',type=int,default=2000);p.add_argument('--offset',type=int,default=12000);p.add_argument('--workers',type=int,default=6);p.add_argument('--resume',action='store_true');p.add_argument('--generator',choices=['research','world'],default='world');p.add_argument('--endpoint',default='release_latency');p.add_argument('--role',choices=['threshold-calibration','null-validation'],default='null-validation');p.add_argument('--index',type=int,default=0);a=p.parse_args()
    if a.command=='run':r=run(a.out,a.B,a.n_validation,a.offset,a.workers,a.resume)
    elif a.command=='replay-null':r=replay_null(a.out,a.generator,a.endpoint,a.role,a.index)
    else:
        try:require_final(a.out)
        except ValueError as e:r=dict(final_test_materialized=False,locked=True,reason=str(e))
    print(json.dumps(r,indent=2))

if __name__=='__main__':main()
