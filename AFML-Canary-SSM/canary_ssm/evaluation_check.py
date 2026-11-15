"""Rebuild audit thresholds/gates from saved minute scores; no truth join or tuning."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.stats import betabinom
from .replay_evaluator import checked_freeze,digest,file_hash,read_table,write
from .policy_artifacts import ordered_threshold
from .first_crossing import decode_threshold
from .metrics import clopper_pearson
from .evaluation_inputs import identity,mixture_case


def check(directory):
    root=Path(directory);f=checked_freeze(root);seen={};summary=[];all_validation=[]
    for generator in ('research','world'):
        models=json.loads((root/generator/'models.json').read_text())
        if models!=f['models'][generator]:raise ValueError('Model file differs from development freeze')
        for endpoint in ('latent_effect',) if generator=='research' else ('release_latency','infrastructure'):
            values={};counts={};ledgers={}
            for role,count,suffix in [('threshold-calibration',f['B'],'calibration'),('null-validation',f['n_validation'],'validation')]:
                maxima={name:[] for name in f['settings'][generator]};eligible={name:[] for name in maxima};ledger=[]
                for index in range(count):
                    folder=root/generator/'inputs'/role/endpoint/str(index);cache=json.loads((folder/'sample_rows.json').read_text())
                    if file_hash(folder/'scores.npz')!=cache['score_sha256']:raise ValueError('Score artifact modified')
                    signature=digest(dict(sources=f['sources'],models=f['models'][generator],settings=f['settings'][generator],generator=generator,endpoint=endpoint,role=role,index=index,offset=f['offset']))
                    if cache['signature']!=signature:raise ValueError('Cache is not bound to frozen source/settings')
                    seed,_=identity(generator,role,f['offset']+index+(3000 if endpoint=='infrastructure' else 0),'healthy');key=(generator,endpoint,role)
                    if seed in seen and seen[seed]!=key:raise ValueError('Seed crossed generator/endpoint/role')
                    if seed in {x['seed'] for vv in f['development_lineage'].values() for x in vv}:raise ValueError('Null seed reused development')
                    seen[seed]=key
                    with np.load(folder/'scores.npz',allow_pickle=False) as scores:
                        for row in cache['rows']:
                            name=row['method'];score=scores[name+'__score'];mask=scores[name+'__eligible']&np.isfinite(score);maximum=float(np.max(score[mask])) if mask.any() else -np.inf
                            if maximum!=decode_threshold(row['maximum']) or int(mask.sum())!=row['eligible_windows'] or row['seed']!=seed or row['role']!=role:raise ValueError('Saved maximum/mask/role differs from raw scores')
                            if row['null_family']!=('healthy' if endpoint=='infrastructure' else mixture_case(seed)):raise ValueError('Null family differs from frozen hash-mixture rule')
                            maxima[name].append(maximum);eligible[name].append(int(mask.sum()))
                    ledger+=cache['rows']
                saved=read_table(root/generator/(endpoint+'_'+suffix+'_maxima.csv'))
                if len(saved)!=len(ledger):raise ValueError('Raw ledger row count differs')
                for expected,actual in zip(ledger,saved):
                    if any(str(v)!=actual[k] for k,v in expected.items()):raise ValueError('Raw maxima CSV differs from per-minute-score cache')
                values[role]=maxima;counts[role]=eligible;ledgers[role]=ledger
            policy=json.loads((root/generator/(endpoint+'_policy.json')).read_text());body={k:v for k,v in policy.items() if k!='policy_hash'}
            if digest(body)!=policy['policy_hash'] or policy['freeze_hash']!=f['freeze_hash']:raise ValueError('Policy hash/freeze mismatch')
            if digest(ledgers['threshold-calibration'])!=policy['calibration_ledger_sha256']:raise ValueError('Calibration ledger changed')
            receipt=json.loads((root/generator/(endpoint+'_validation.json')).read_text());body={k:v for k,v in receipt.items() if k!='validation_hash'}
            if digest(body)!=receipt['validation_hash'] or digest(ledgers['null-validation'])!=receipt['validation_ledger_sha256']:raise ValueError('Independent validation receipt changed')
            csvrows=read_table(root/generator/(endpoint+'_null_intervals.csv'));all_validation+=receipt['rows']
            if len(csvrows)!=len(receipt['rows']) or len(receipt['rows'])!=len(f['settings'][generator]):raise ValueError('Validation row count differs')
            for row,actual in zip(receipt['rows'],csvrows):
                name=row['method'];ordered=ordered_threshold(values['threshold-calibration'][name],.05)
                if ordered!=policy['policies'][name]:raise ValueError('Ordered threshold differs from raw null maxima')
                threshold=decode_threshold(ordered['threshold']);events=sum(v>threshold for v in values['null-validation'][name]);n=f['n_validation'];B=f['B'];k=ordered['k'];lo,hi=clopper_pearson(events,n)
                pv=float(min(1.,2*min(betabinom.cdf(events,n,B+1-k,k),betabinom.sf(events-1,n,B+1-k,k)))) if k<=B else None
                gate='INSUFFICIENT' if min(B,n)<2000 or not np.isfinite(threshold) else 'PASS' if pv is not None and pv>=.01 and events/n<=.075 else 'FAIL'
                if (row['alerts'],row['gate'],row['ci_lower'],row['ci_upper'],row['rate'],row['bb_pvalue_two_sided'])!=(events,gate,lo,hi,events/n,pv):raise ValueError('Computed validation gate/interval differs')
                if row['no_eligible_nulls']!=sum(c==0 for c in counts['null-validation'][name]) or row['eligible_rollouts']!=sum(c>0 for c in counts['null-validation'][name]):raise ValueError('Abstention count differs from raw masks')
                for key,value in row.items():
                    if ('' if value is None else str(value))!=actual[key]:raise ValueError('Validation CSV differs from sealed receipt')
            summary.append(dict(generator=generator,endpoint=endpoint,methods=len(policy['policies']),B=f['B'],n=f['n_validation'],recomputed_from_raw_minute_scores=True))
    combined=read_table(root/'independent_null_intervals.csv')
    if len(combined)!=len(all_validation):raise ValueError('Combined validation table row count differs')
    for row,actual in zip(all_validation,combined):
        if any(('' if v is None else str(v))!=actual[k] for k,v in row.items()):raise ValueError('Combined table differs from sealed receipts')
    if (root/'final_test_access.json').exists() or json.loads((root/'final_test_lock.json').read_text())['inputs_materialized']:raise ValueError('Sealed final inputs were opened')
    result=dict(verified=True,endpoints=summary,independent_null_rollouts=len(seen),frozen_sources_match=True,thresholds_and_gates_recomputed=True,final_test_materialized=False)
    write(root/'verified_raw_artifacts.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',default='examples/evaluator_v2');a=p.parse_args();print(json.dumps(check(a.study),indent=2))
