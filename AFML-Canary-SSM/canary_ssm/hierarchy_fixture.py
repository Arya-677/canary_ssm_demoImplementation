"""Saved class/rack hierarchy and analytic pooling checks; no detection benchmark."""
import argparse
import csv
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy

from .public_adjustment import (AdjustmentPolicy,HealthyDevelopment,fit_development,
    panel_from_time_slice,serial)
from .public_filter import Observations,GaussianEffects
from .hierarchy import EffectParams
from .public_hierarchy import GroupedParams,grouped_structure,GroupedGaussianEffects,run_hierarchy
from .telemetry import CausalWindowStore,PublicRecord,digest


def monitoring_slice(source):
    """Re-emit saved algebraic metrics with an explicit four-host release cohort."""
    panel=panel_from_time_slice(source,'fixture-service')
    roster=[{'host_id':h,'rack_id':panel.rack_ids[j],'class_id':panel.class_ids[j],
        'service_id':'fixture-service','replica_id':'r'+h[1:]} for j,h in enumerate(panel.host_ids)]
    store=CausalWindowStore('hierarchy-monitoring',roster,interval_seconds=60)
    cohort={'h0','h1','h5','h6'}
    for t,now in enumerate(panel.times):
        now=float(now)
        for j,meta in enumerate(roster):
            usable=bool(panel.observed[t,j]);n=100 if usable else 0
            log=float(panel.y[t,j]) if usable else 0.;lat=float(np.exp(log)) if usable else 0.
            exposed=meta['host_id'] in cohort and t>=80
            row=PublicRecord(f'{t}-{j}',store.run_id,**meta,
                release_id='candidate-v2' if exposed else 'baseline-v1',exposed=exposed,
                event_time=float(now),arrival_time=float(now),interval_seconds=60,request_count=n,
                latency_ms=lat if usable else None,workload=float(np.expm1(panel.x[t,j])) if usable else None,
                latency_sum_ms=n*lat,latency_sum_sq_ms2=n*lat*lat,
                log_latency_sum=n*log,log_latency_sum_sq=n*log*log,
                observed=usable,latency_observed=usable,workload_observed=usable,exposure_observed=usable)
            store.ingest(row,now)
        store.decide(now)
    return store.time_slice(float(panel.times[-1]))


def pooling_examples():
    times=np.array([60.,120.,180.]);r=np.array([[0.,0.],[1.,0.],[0.,0.]])
    observed=np.ones((3,2),bool);observed[2]=False
    data=Observations(times,times,r,observed,np.ones(3,bool),times>=120,
        np.tile(.5*np.eye(2),(3,1,1)),[.5,.5],[.01,.01],[1.,1.],('h0','h1'),120.,'analytic-pooling')
    structure=grouped_structure(data.host_ids,(0,0))
    settings=GroupedParams(prior_group_sd=1.,prior_deviation_sd=.2,rho_g=.9,rho_h=.3)
    hierarchical=GroupedGaussianEffects(structure,settings).run(data)
    independent=GaussianEffects(EffectParams(kind='indep',prior_sd=np.sqrt(1.02))).run(data)
    # A negative control: equal group-size-scaled prior/process covariance and
    # identical dynamics give diagonal induced host covariance (no pooling).
    unpooled_settings=GroupedParams(prior_group_sd=float(np.sqrt(.51)),prior_deviation_sd=float(np.sqrt(1.02)),
        sd_g=float(.005/np.sqrt(2)),sd_h=.005,rho_g=.95,rho_h=.95)
    unpooled=GroupedGaussianEffects(structure,unpooled_settings).run(data)
    rows=[]
    for name,out in [('hierarchical',hierarchical),('independent',independent),('diagonal_hierarchy',unpooled)]:
        for t in (1,2):
            for j,h in enumerate(data.host_ids):rows.append([name,int(times[t]),h,float(out['host_effect_mean'][t,j]),float(out['host_effect_covariance'][t,j,j])])
    return rows,hierarchical,independent,unpooled


def export_fixture(directory):
    started=time.perf_counter();out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1];source=root/'examples/control_adjustment/public'
    dev=json.loads((source/'healthy_development_slice.json').read_text())
    target=monitoring_slice(json.loads((source/'monitoring_slice.json').read_text()))
    (out/'public').mkdir(exist_ok=True)
    (out/'public/monitoring_slice.json').write_text(json.dumps(target,indent=2)+'\n')
    dp=panel_from_time_slice(dev,'fixture-service');tp=panel_from_time_slice(target,'fixture-service')
    results={}
    for group in ('class_id','rack_id'):
        name='rack' if group=='rack_id' else 'class'
        policy=AdjustmentPolicy(**json.loads((root/'configs/rack_adjustment_rank1.json').read_text())) if name=='rack' else AdjustmentPolicy()
        model=fit_development([HealthyDevelopment(dp,'development',True,'algebraic-public-fixture-v1')],['h0','h1','h5','h6'],policy)
        adjusted=model.prepare(tp,4860).transform(tp)
        settings=GroupedParams(**json.loads((root/f'configs/hierarchy_{name}.json').read_text()))
        result=run_hierarchy(adjusted,model,settings);results[name]=result
        model.save(out/f'model_{name}.json')
        (out/f'adjusted_{name}.json').write_text(json.dumps(serial(adjusted),indent=2,allow_nan=False)+'\n')
        (out/f'hierarchy_{name}.json').write_text(json.dumps(serial(result),indent=2,allow_nan=False)+'\n')
    rows,hier,indep,unpooled=pooling_examples()
    with (out/'pooling.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['model','event_time','host_id','effect_mean','effect_variance']);w.writerows(rows)
    checks={
        'basis_identities':all(np.allclose(x['output']['C'].T@x['output']['B'],0,atol=1e-12) and np.allclose(x['output']['B'].T@x['output']['B'],np.eye(x['output']['B'].shape[1]),atol=1e-12) for x in results.values()),
        'nonempty_rack_deviations':results['rack']['output']['B'].shape==(4,2),
        'stable_cohort_order':results['rack']['output']['host_ids']==['h0','h1','h5','h6'],
        'peer_borrowing_without_shared_white_noise':bool(hier['host_effect_mean'][1,1]>.1 and abs(indep['host_effect_mean'][1,1])<1e-12),
        'diagonal_prior_dynamics_remove_pooling':bool(np.allclose(unpooled['host_effect_mean'],indep['host_effect_mean'],atol=1e-12,equal_nan=True)),
        'different_group_local_dynamics':bool(np.allclose(hier['group_effect_mean'][2],.9*hier['group_effect_mean'][1]) and np.allclose(hier['host_deviation_mean'][2],.3*hier['host_deviation_mean'][1])),
        'effect_risk_excludes_noise':all(np.all(x['output']['effect_risk_map'][:,4:]==0) for x in results.values()),
        'no_thresholds':all(x['thresholds'] is None and x['alarms'] is None for x in results.values())}
    manifest={'fixture_id':'constrained-hierarchy-acceptance-v1','acceptance_only':True,'checks':checks,'passed':all(checks.values()),
        'input_hashes':{'development':digest(dev),'monitoring':digest(target)},'new_random_seeds':[],
        'settings':{name:x['output']['settings'] for name,x in results.items()},
        'source_hashes':{n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ('hierarchy.py','public_filter.py','public_hierarchy.py','hierarchy_fixture.py')},
        'git_commit':None,'source_kind':'extracted_archive','versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
        'machine':{'system':platform.system(),'architecture':platform.machine()},'elapsed_seconds':time.perf_counter()-started,
        'failures':[k for k,v in checks.items() if not v],'dashboard_connected':False}
    manifest['configuration_sha256']=digest(manifest['settings'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/grouped_hierarchy')
    result=export_fixture(p.parse_args().out);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
