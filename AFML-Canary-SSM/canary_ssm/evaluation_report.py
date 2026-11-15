"""Figures and numerical prose are derived from saved CSV tables only."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .replay_evaluator import read_table,table,write
from .first_crossing import decode_threshold

def report(directory):
    root=Path(directory);out=root/'report';out.mkdir(exist_ok=True);gates=read_table(root/'independent_null_intervals.csv');outcomes=[];family=[];fits=[]
    table(out/'null_alert_intervals_with_eligibility.csv',[{**r,'conditional_eligible_alert_rate':int(r['alerts'])/int(r['eligible_rollouts']) if int(r['eligible_rollouts']) else None,'no_eligible_rollout_fraction':int(r['no_eligible_nulls'])/int(r['n']),'interval_scope':'pointwise exact interval over ALL independent null rollouts'} for r in gates])
    for generator in ('research','world'):
        rows=read_table(root/generator/('research_results.csv' if generator=='research' else 'resource_world_results.csv'));outcomes+=rows
        for endpoint in sorted({r['endpoint'] for r in gates if r['generator']==generator}):
            data=[r for r in gates if r['generator']==generator and r['endpoint']==endpoint];rate=np.array([float(r['rate']) for r in data]);lo=np.array([float(r['ci_lower']) for r in data]);hi=np.array([float(r['ci_upper']) for r in data]);y=np.arange(len(data))
            fig,ax=plt.subplots(figsize=(10,6));ax.errorbar(rate,y,xerr=np.stack([rate-lo,hi-rate]),fmt='o',capsize=3);ax.set_yticks(y,[r['method']+' ['+r['gate']+']' for r in data]);ax.invert_yaxis();ax.axvline(.05,color='brown',linestyle='--',label='nominal alpha .05');ax.legend();ax.set(xlabel='Independent null rollout alert rate (pointwise 95% exact interval)',title=f'{generator} / {endpoint}: frozen-policy diagnostic audit',xlim=(-.004,max(.08,float(hi.max())*1.08)));fig.tight_layout();fig.savefig(out/f'{generator}_{endpoint}_null_intervals.png',dpi=150);plt.close(fig)
            ledger=read_table(root/generator/(endpoint+'_validation_maxima.csv'));policy=json.loads((root/generator/(endpoint+'_policy.json')).read_text());by=defaultdict(list)
            for r in ledger:by[r['method'],r['null_family']].append(r)
            for (method,scenario),batch in by.items():
                threshold=decode_threshold(policy['policies'][method]['threshold']);alerts=sum(decode_threshold(r['maximum'])>threshold for r in batch)
                family.append(dict(generator=generator,endpoint=endpoint,method=method,null_family=scenario,n=len(batch),alerts=alerts,rate=alerts/len(batch),no_eligible=sum(int(r['eligible_windows'])==0 for r in batch),scope='diagnostic stratification; mixture threshold does not promise per-family rates'))
            real=[r for r in rows if r['endpoint']==endpoint and r['member']=='harm'];methods=list(dict.fromkeys(r['method'] for r in real));scenarios=list(dict.fromkeys(r['scenario'] for r in real));matrix=np.full((len(methods),len(scenarios)),np.nan)
            for r in real:matrix[methods.index(r['method']),scenarios.index(r['scenario'])]=float(r['abstention_fraction'])
            fig,ax=plt.subplots(figsize=(12,6));im=ax.imshow(matrix,aspect='auto',vmin=0,vmax=1,cmap='YlOrBr');ax.set_xticks(range(len(scenarios)),[s.replace('_',' ') for s in scenarios],rotation=55,ha='right');ax.set_yticks(range(len(methods)),methods);ax.set_title(f'{generator} / {endpoint}: smoke abstentions, one pair per scenario\nDiagnostic examples; no final-test efficacy estimate');fig.colorbar(im,ax=ax,label='Ineligible fraction of monitoring horizon');fig.tight_layout();fig.savefig(out/f'{generator}_{endpoint}_abstentions.png',dpi=150);plt.close(fig)
        def walk(value,path):
            if isinstance(value,dict):
                if any(k in value for k in ('success','boundary_hit','failure')):fits.append(dict(generator=generator,path=path,diagnostic_json=json.dumps(value,sort_keys=True)))
                for k,v in value.items():walk(v,path+'/'+k)
            elif isinstance(value,list):
                for i,v in enumerate(value):walk(v,path+'/'+str(i))
        walk(json.loads((root/generator/'models.json').read_text()),'models')
    table(out/'fit_diagnostics.csv',fits);table(out/'validation_by_null_family.csv',family)
    table(out/'abstentions.csv',[{k:r.get(k) for k in ('generator','endpoint','scenario','member','method','status','calibration_gate','eligible_windows','horizon_windows','abstention_fraction','no_eligible_data','target_unknown_windows','unmonitored_affected_hosts')} for r in outcomes])
    counts=Counter((r['generator'],r['endpoint'],r['method'],r['status']) for r in outcomes)
    table(out/'smoke_status_counts.csv',[dict(generator=g,endpoint=e,method=m,status=s,count=n,scope='smoke examples only') for (g,e,m,s),n in sorted(counts.items())])
    perf=root/'performance'
    if (perf/'method_runtime_memory.csv').exists():
        rows=[r for r in read_table(perf/'method_runtime_memory.csv') if r['component']=='method replay'];fig,axes=plt.subplots(2,2,figsize=(12,9))
        for col,g in enumerate(('research','world')):
            batch=[r for r in rows if r['generator']==g];y=np.arange(len(batch))
            axes[0,col].barh(y,[float(r['amortized_ns_per_input_minute'])/1e6 for r in batch]);axes[1,col].barh(y,[float(r['tracked_allocation_peak_bytes'])/1024 for r in batch])
            for row in range(2):axes[row,col].set_yticks(y,[r['method'] for r in batch]);axes[row,col].invert_yaxis()
            axes[0,col].set(title=g,xlabel='Whole method replay / input minute (ms)');axes[1,col].set(xlabel='Separate traced peak allocation (KiB; not RSS)')
        fig.suptitle('Diagnostic timings under concurrent audit; not isolated capacity limits');fig.tight_layout();fig.savefig(out/'method_costs.png',dpi=150);plt.close(fig)
    summary=dict(gates=dict(Counter(r['gate'] for r in gates)),raw_outcome_rows=len(outcomes),status_counts=dict(Counter(r['status'] for r in outcomes)),final_test_materialized=(root/'final_test_access.json').exists(),figures_from_csv_only=True,comparative_efficacy_claim=False,original_shared_step_gate_closed=False)
    write(out/'summary.json',summary)
    lines=['# Saved-table evaluator report','', 'All numbers below and figures are generated from saved CSVs. Research and world targets stay separate; smoke examples are not efficacy estimates.','', '| Endpoint | Policies | PASS | FAIL | INSUFFICIENT |','| --- | ---: | ---: | ---: | ---: |']
    for gen,endpoint in sorted({(r['generator'],r['endpoint']) for r in gates}):
        c=Counter(r['gate'] for r in gates if r['generator']==gen and r['endpoint']==endpoint);lines.append(f'| {gen} / {endpoint} | {sum(c.values())} | {c["PASS"]} | {c["FAIL"]} | {c["INSUFFICIENT"]} |')
    lines+=['','| Diagnostic outcome | Rows |','| --- | ---: |']+[f'| {k} | {v} |' for k,v in sorted(summary['status_counts'].items())]
    lines+=['','Final inputs remain sealed: the new mixture audit does not replace the governing per-family gate. Tied/saturated-score failures, missing targets, premature alarms, capped misses and abstentions are retained. No validation retuning occurred.','', 'World release attribution is an offline same-exogenous paired completion-statistic target, not an observed online counterfactual. Infrastructure targets and policies are distinct. Completion latency alone can miss OOM/drop harm.','', 'See raw generator-specific results, `validation_by_null_family.csv`, `abstentions.csv`, and `fit_diagnostics.csv`. Performance scopes remain separate: update wall time, traced allocations, engine, HTTP/API, VM renderer and attempted real browser execution.']
    if (perf/'browser_checks.json').exists():lines+=['','Browser status: '+json.loads((perf/'browser_checks.json').read_text())['status']+'. Browser failure is not replaced by a VM FPS claim.']
    (out/'README.md').write_text('\n'.join(lines)+'\n');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',default='examples/evaluator_v2');a=p.parse_args();print(json.dumps(report(a.study),indent=2))
