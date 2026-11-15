"""Algebraic public-metric acceptance fixture, not physical-world or SSM performance."""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import numpy as np
from .seeds import seed_for
from .telemetry import CausalWindowStore,PublicRecord
from .public_adjustment import (HealthyDevelopment,AdjustmentPolicy,fit_development,
    panel_from_time_slice,serial,FrozenAdjustment)


def generate_public(seed,run_id,monitoring=False):
    rng=np.random.default_rng(seed);T=120;N=10
    x=rng.normal(2,.3,(T,N));f=rng.normal(0,.02,T)
    y=5+.2*(x-2)+np.arange(1,N+1)[None]/5*f[:,None]+rng.normal(0,.005,(T,N))
    if monitoring:
        y[80:,0]+=.04;y[80:,5]+=.04
        y[100,1:5]+=.20 # Deliberate control challenge; labels remain outside inference.
    roster=[dict(host_id=f'h{i}',rack_id='a' if i<5 else 'b',class_id=0,service_id='fixture-service',replica_id=f'r{i}') for i in range(N)]
    store=CausalWindowStore(run_id,roster,interval_seconds=60)
    for t in range(T):
        now=(t+1)*60
        for j,meta in enumerate(roster):
            missing=monitoring and ((t==97 and j in (1,2)) or (t==98 and j==0))
            exposed=monitoring and (j in (0,5) and t>=80 or j==1 and t==96)
            lat=float(np.exp(y[t,j]));log=float(y[t,j]);n=0 if missing else 100
            row=PublicRecord(f'{t}-{j}',run_id,**meta,release_id='candidate-v2' if exposed else 'baseline-v1',exposed=exposed,
                event_time=now,arrival_time=now,interval_seconds=60,request_count=n,latency_ms=None if missing else lat,
                workload=None if missing else float(np.expm1(x[t,j])),latency_sum_ms=n*lat,latency_sum_sq_ms2=n*lat*lat,
                log_latency_sum=n*log,log_latency_sum_sq=n*log*log,observed=not missing,latency_observed=not missing,
                workload_observed=not missing,exposure_observed=not missing)
            store.ingest(row,now)
        store.decide(now)
    return store.time_slice(T*60)


def export_fixture(directory):
    directory=Path(directory);public=directory/'public';public.mkdir(parents=True,exist_ok=True)
    dev=generate_public(seed_for('world_dev',0),'adjustment-dev')
    target=generate_public(seed_for('world_smoke',0),'adjustment-monitoring',True)
    for name,data in (('healthy_development_slice',dev),('monitoring_slice',target)):
        (public/f'{name}.json').write_text(json.dumps(data,indent=2)+'\n')
    dp=panel_from_time_slice(dev,'fixture-service');tp=panel_from_time_slice(target,'fixture-service')
    results={};models={};states={}
    for rank in (0,1):
        policy=AdjustmentPolicy(**json.loads((Path(__file__).resolve().parents[1]/f'configs/rack_adjustment_rank{rank}.json').read_text()))
        model=fit_development([HealthyDevelopment(dp,'development',True,'algebraic-public-fixture-v1')],['h0','h5'],policy)
        model.save(directory/f'model_rank{rank}.json')
        state=model.prepare(tp,4860);out=state.transform(tp)
        (directory/f'adjusted_rank{rank}.json').write_text(json.dumps(serial(out),indent=2)+'\n')
        models[rank]=model;results[rank]=out;states[rank]=state
    r=results[1]
    future=tp.y.copy();future[110:]+=5
    changed=replace(tp,y=future);after=models[1].prepare(changed,4860).transform(changed)
    checks={'development_only_lineage':all(m.to_dict()['development_lineage'][0]['role']=='development' for m in models.values()),
        'pre_loading_counts':states[1].pre_counts==(80,80),'one_shared_reference':r['reference_subtractions']==1,
        'shared_covariance_nondiagonal':bool(np.any(np.abs(r['shared_reference_covariance'][:,0,1])>0)),
        'rack_control_shortfall_masks':not bool(r['eligible'][97]) and r['fresh_control_counts']['a'][97]==2,
        'eighty_percent_rule_masks':not bool(r['eligible'][98]),
        'exposed_control_excluded':r['fresh_control_counts']['a'][96]==3 and not bool(r['control_mask'][96,1]),
        'future_perturbation':bool(np.array_equal(r['residuals'][:110],after['residuals'][:110],equal_nan=True)),
        'rank_zero_has_no_reference':bool(np.all(results[0]['control_estimation_uncertainty']==0) and results[0]['reference_subtractions']==0),
        'contamination_challenge_explicit':'plain_weighted_projection_not_robust' in r['challenges'],
        'frozen_artifact_roundtrip':all(FrozenAdjustment.load(directory/f'model_rank{k}.json').to_dict()==m.to_dict() for k,m in models.items())}
    evaluator=directory/'evaluator';evaluator.mkdir(exist_ok=True)
    (evaluator/'fixture_recipe.json').write_text(json.dumps({'evaluator_only':True,'fixture_id':'algebraic-public-fixture-v1',
        'not_a_benchmark':True,'control_perturbation_window_index':100,'canary_offset_after_index':80,
        'development_seed':seed_for('world_dev',0),'smoke_seed':seed_for('world_smoke',0)},indent=2)+'\n')
    checks=serial(checks)
    result={'fixture_only':True,'checks':checks,'passed':all(checks.values()),'detector_connected':False}
    (directory/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/control_adjustment')
    result=export_fixture(p.parse_args().out);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
