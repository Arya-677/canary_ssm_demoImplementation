"""Algebraic dashboard traces, using actual Gaussian fits; not detector benchmarks."""
import csv
import hashlib
import json
import time
import platform
from dataclasses import asdict
from pathlib import Path

import numpy as np
import scipy

from .engine import load_engine_config
from .seeds import seed_for
from .public_adjustment import PublicPanel,HealthyDevelopment,AdjustmentPolicy,fit_development,serial
from .public_filter import observations_from_adjustment,GaussianEffects
from .public_hierarchy import grouped_structure,GroupedGaussianEffects,GroupedParams
from .hierarchy import EffectParams
from .monitor_feed import seal,validate,ROOT
from .telemetry import digest


def export_fixture(directory=ROOT):
    started=time.perf_counter();out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    topology=load_engine_config(root/'configs/world_recovery.yaml').topology
    # The world fixture, not frontend tile positions, owns stable IDs/parentage.
    hosts=topology.hosts if hasattr(topology,'hosts') else None
    if hosts is None:
        from .topology import load_topology
        hosts=load_topology(root/'configs/world_interactive.yaml').hosts
    ids=tuple(h.host_id for h in hosts);racks=tuple(h.rack_id for h in hosts);classes=tuple(h.class_id for h in hosts)
    n=len(ids);T=140;times=np.arange(1,T+1,dtype=float)*60
    canaries=[h for rack in sorted(set(racks)) for h in [ids[j] for j,r in enumerate(racks) if r==rack][:2]]
    ci=[ids.index(h) for h in canaries]
    seed_dev=seed_for('world_dev',100,1);seed_smoke=seed_for('world_smoke',100,1)
    def values(seed):
        rng=np.random.default_rng(seed);x=rng.normal(2,.3,(T,n));f=rng.normal(0,.02,T)
        y=5+.15*(x-2)+np.linspace(.7,1.3,n)[None]*f[:,None]+rng.normal(0,.006,(T,n))
        return x,y
    def panel(x,y,run_id,monitor=False):
        observed=np.ones((T,n),bool);exposed=np.zeros((T,n),bool)
        if monitor:
            exposed[80:,ci]=True;observed[90,ci[:2]]=False
            controls=[j for j,r in enumerate(racks) if r==racks[ci[0]] and j not in ci]
            observed[91,controls[:2]]=False
        return PublicPanel(run_id,ids,racks,classes,times,y,x,observed,observed.copy(),exposed,observed.copy())
    dx,dy=values(seed_dev);dev=panel(dx,dy,'dashboard-development')
    policy=AdjustmentPolicy(policy_id='demo-rack-dashboard-v1',group_by='rack_id',deviation_reason='Rack eligibility with unchanged research 80% / 3 / 60 defaults')
    model=fit_development([HealthyDevelopment(dev,'development',True,'dashboard-development-v1')],canaries,policy)
    model.save(out/'nuisance_model.json')
    mx,my=values(seed_smoke);catalog=[];recipes=[];checks={};summary=[]
    settings={
        'weak':GroupedParams(group_by='rack_id',variant_id='demo-rack-host-v1',prior_group_sd=.025,prior_deviation_sd=.03,sd_g=.003,sd_h=.004),
        'strong':GroupedParams(group_by='rack_id',variant_id='demo-rack-host-v1',prior_group_sd=.04,prior_deviation_sd=.01,sd_g=.006,sd_h=.001)}
    for index,name in enumerate(('host-local','group-wide','shared-shock','recovery'),1):
        y=my.copy();target=ci[:1] if name in ('host-local','recovery') else [j for j in ci if racks[j]==racks[ci[0]]] if name=='group-wide' else list(range(n))
        start,stop=95,(115 if name=='recovery' else 125 if name=='shared-shock' else T)
        y[start:stop,target]+=.065
        run_id=f'detector-replay-{index:02}';p=panel(mx,y,run_id,True)
        adjusted=model.prepare(p,4860).transform(p);data=observations_from_adjustment(serial(adjusted),model)
        structure=grouped_structure(data.host_ids,[racks[ids.index(h)] for h in data.host_ids],'rack_id')
        outputs={'independent':GaussianEffects(EffectParams(kind='indep')).run(data)}
        outputs.update({key:GroupedGaussianEffects(structure,value).run(data) for key,value in settings.items()})
        methods=[{'method_id':'independent','version':'independent-dashboard-v1','kind':'independent','settings':{'rho_g':.95,'sd_g':.005,'prior_sd':.03}}]
        methods.extend({'method_id':key,'version':f'{key}-pooling-dashboard-v1','kind':'hierarchical','settings':{k:v for k,v in asdict(value).items() if k not in ('group_by','variant_id')}} for key,value in settings.items())
        frames=[]
        for t,now in enumerate(times):
            methods_frame={}
            for key,value in outputs.items():
                valid=np.isfinite(value['host_effect_mean'][t]).all()
                methods_frame[key]={'mean':serial(value['host_effect_mean'][t]),'covariance':serial(value['host_effect_covariance'][t]) if valid else None,
                    'group':serial(value['host_group_effect_mean'][t]) if key!='independent' else [None]*len(ci),
                    'deviation':serial(value['host_deviation_mean'][t]) if key!='independent' else [None]*len(ci)}
            frames.append({'event_time':float(now),'decision_time':float(data.decision_times[t]),
                'input_sha256':digest(serial({'window':t,'residuals':adjusted['residuals'][t],'V':adjusted['measurement_covariance'][t],'observed':adjusted['observed'][t]})),
                'observed':serial(data.observed[t]),'eligible':bool(data.eligible[t]),
                'latency_ms':[float(np.exp(y[t,j])) if p.observed[t,j] else None for j in ci],
                'residual':serial(adjusted['residuals'][t]),'quality_flags':adjusted['quality_flags'][t],'methods':methods_frame})
        artifact=seal({'format':'detector-monitor-v1','artifact_id':f'demo-{index:02}','version':'dashboard-traces-v1','replay_id':run_id,'run_id':run_id,
            'source_kind':'simulated-metrics-replay','host_roster':[{'host_id':h,'rack_id':racks[ids.index(h)]} for h in canaries],
            'methods':methods,'exposure_time':4860,'simulated':True,'frames':frames})
        validate(artifact,[{'host_id':h.host_id,'rack_id':h.rack_id} for h in hosts])
        (out/f'demo-{index:02}.json').write_text(json.dumps(artifact,separators=(',',':'),allow_nan=False)+'\n')
        catalog.append({'sample_id':f'demo-{index:02}','label':name.replace('-',' ').title()+' · algebraic demo','artifact_id':artifact['artifact_id']})
        recipes.append({'artifact_id':artifact['artifact_id'],'scenario':name,'targets':[ids[j] for j in target],
            'start_time':float(times[start]),'end_time_exclusive':float(times[stop]) if stop<T else None,'log_latency_offset':.065})
        checks[name]=all(np.isfinite(o['host_effect_mean'][100]).all() for o in outputs.values()) and not data.eligible[90] and not data.eligible[91]
        summary.append([artifact['artifact_id'],name,len(frames),len(canaries),int(data.eligible.sum()),bool(checks[name])])
    with (out/'pooling_settings.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['setting','prior_pair_covariance','prior_host_variance','prior_pair_correlation','innovation_pair_covariance'])
        correlations=[]
        for key,value in settings.items():
            g=value.prior_group_sd**2;h=value.prior_deviation_sd**2;cov=g-h/2;var=g+h/2
            innovation=value.sd_g**2-value.sd_h**2/2
            w.writerow([key,cov,var,cov/var,innovation]);correlations.append(cov/var)
        checks['positive_and_ordered_pooling']=bool(0<correlations[0]<correlations[1]<1)
    (out/'index.json').write_text(json.dumps(catalog,indent=2)+'\n')
    (out/'evaluator').mkdir(exist_ok=True)
    (out/'evaluator/recipes.json').write_text(json.dumps({'evaluator_only':True,'not_a_benchmark':True,'generator_id':'dashboard-algebraic-latency-v1','recipes':recipes},indent=2)+'\n')
    with (out/'summary.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['artifact_id','authored_demo','frames','monitored_hosts','eligible_minutes','acceptance_pass']);w.writerows(summary)
    result={'generator_id':'dashboard-algebraic-latency-v1','checks':serial(checks),'passed':all(checks.values()),'acceptance_only':True,
        'seeds':{'development':seed_dev,'smoke':seed_smoke},'roles':{'fit':'development','display':'smoke'},'configuration_sha256':digest(methods),
        'development_selection_performed':False,'calibration_performed':False,
        'source_hashes':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('detector_dashboard_fixture.py','public_adjustment.py','public_filter.py','public_hierarchy.py','monitor_feed.py')},
        'git_commit':None,'source_kind':'extracted_archive','machine':{'system':platform.system(),'architecture':platform.machine()},'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},'elapsed_seconds':time.perf_counter()-started}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default=str(ROOT));a=p.parse_args()
    print(json.dumps(export_fixture(a.out),indent=2))
