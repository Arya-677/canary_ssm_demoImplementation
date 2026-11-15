"""Conditional Gaussian null calibration example; NOT resource-world calibration."""
import argparse,csv,json,time,hashlib,platform
from dataclasses import asdict
from pathlib import Path
import numpy as np
from .public_adjustment import PublicPanel,HealthyDevelopment,AdjustmentPolicy,fit_development,serial
from .public_filter import observations_from_adjustment,GaussianEffects
from .hierarchy import EffectParams
from .first_crossing import protocol,rule,decode_threshold
from .policy_artifacts import freeze_development,calibrate,validate_nulls,ordered_threshold,sources
from .policy_public import policy_records
from .seeds import seed_for,REGISTRY_VERSION
from .telemetry import digest


def panel(seed,run_id,H=4,development=False):
    rng=np.random.default_rng(seed);T=120 if development else 60+H;N=10
    x=rng.normal(2,.3,(T,N));f=rng.normal(0,.02,T)
    y=5+.2*(x-2)+np.arange(1,N+1)[None]/5*f[:,None]+rng.normal(0,.005,(T,N))
    ids=tuple('h'+str(i) for i in range(N));racks=tuple('a' if i<5 else 'b' for i in range(N));observed=np.ones((T,N),bool);exposed=np.zeros((T,N),bool)
    if not development:exposed[60:,[0,5]]=True
    return PublicPanel(run_id,ids,racks,tuple(0 for _ in ids),np.arange(1,T+1)*60.,y,x,observed,observed.copy(),exposed,observed.copy())


def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(serial(value),indent=2,allow_nan=False)+'\n')

def export_fixture(directory,B=2000,n_validation=2000,H=4):
    if type(B) is not int or type(n_validation) is not int or not 1<=B<=5000 or not 1<=n_validation<=5000:raise ValueError('Bounded fixture requires 1–5000 independent nulls per role')
    out=Path(directory);started=time.perf_counter();canaries=['h0','h5'];controls=['h'+str(i) for i in (1,2,3,4,6,7,8,9)]
    p=protocol(canaries,controls,{'rack:a':controls[:4],'rack:b':controls[4:]},horizon_windows=H)
    dev_seed=seed_for('world_dev',0,21);dev=panel(dev_seed,'policy-development',H,True)
    prep=fit_development([HealthyDevelopment(dev,'development',True,'policy-gaussian-development-v1')],canaries,
        AdjustmentPolicy(policy_id='demo-rack-policy-v1',group_by='rack_id',deviation_reason='Physical rack illustration; unchanged 80% / 3 / 60 eligibility'))
    params=EffectParams(kind='indep');settings=rule(H)
    simulator={'generator_id':'policy-conditional-gaussian-null-v1','configuration':{'H':H,'preperiod_minutes':60,'hosts':10,'canaries':canaries,'equations':'log latency=5+.2*(x-2)+loading*shared_factor+white_noise; no release effect','observed_masks':'all fresh in this numerical fixture'},'source_hashes':sources(['policy_fixture.py']),'numpy':np.__version__}
    frozen=freeze_development(prep.to_dict(),vars(params),simulator,p,[{'run_id':dev.run_id,'seed':dev_seed,'role':'development','declared_healthy':True,'public_sha256':dev.fingerprint()}],settings)
    write(out/'frozen.json',frozen);write(out/'development_fit.json',prep.to_dict())
    def generate(role,count):
        traces=[];purpose='world_calibration' if role=='threshold-calibration' else 'world_null_validation'
        for i in range(count):
            seed=seed_for(purpose,i,21 if role=='threshold-calibration' else 28);public=panel(seed,'policy-run-'+hashlib.sha256(str(seed).encode()).hexdigest()[:20],H)
            adjusted=prep.prepare(public,3660).transform(public);data=observations_from_adjustment(serial(adjusted),prep);output=GaussianEffects(params).run(data)
            traces.append({'run_id':public.run_id,'seed':seed,'role':role,'declared_null':True,'hashes':frozen['hashes'],'freeze_hash':frozen['freeze_hash'],'exposure_time':3660.,'records':policy_records(public,adjusted,data,output,p),'advisories':[]})
        return traces
    calibration=generate('threshold-calibration',B);policy=calibrate(frozen,calibration)
    # Validation is generated only after the frozen policy hash exists. No selection/retuning path.
    validation_traces=generate('null-validation',n_validation);validation=validate_nulls(policy,validation_traces)
    write(out/'calibration_nulls.json',calibration);write(out/'policy.json',policy);write(out/'validation_nulls.json',validation_traces);write(out/'validation.json',validation)
    with (out/'null_maxima.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['run_id','seed','role','maximum','eligible_windows','trace_hash']);w.writeheader();w.writerows(policy['calibration_lineage'])
    with (out/'validation_outcomes.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(validation['outcomes'][0]));w.writeheader();w.writerows(validation['outcomes'])
    with (out/'false_alerts.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['channel','events','n','rate','lower_95','upper_95'])
        for channel,stats in validation['rates'].items():w.writerow([channel,stats['events'],stats['n'],stats['rate'],*stats['exact_binomial_95_interval']])
    rank500=ordered_threshold([decode_threshold(x['maximum']) for x in policy['calibration_lineage'][:500]],.05) if B>=500 else None
    result={'fixture_id':'conditional-gaussian-first-crossing-v1','resource_world_compatible':False,'B':B,'n_validation':n_validation,'H':H,'role_separation':True,
        'checks':{'null_maxima_recomputed':len(policy['calibration_lineage'])==B,'k_476_example':rank500 is None or rank500['k']==476,'no_retuning':validation['no_retuning'] and validation['policy_hash']==policy['policy_hash'],
                  'eligibility_defaults':p['minimum_observed_canaries']==.8 and p['minimum_fresh_controls']==3,'combined_report_present':set(validation['rates'])=={'release_alarm','platform_pause','resource_pause','combined_action'}},
        'validation_gate':validation['gate'],'rank_500_example':rank500,'advisory_scope':'No independent platform/resource producer in this conditional latency generator. Extra channels have no events; their uncertainty intervals remain nonzero. Combined policy is not asserted controlled at alpha.',
        'seed_registry_version':REGISTRY_VERSION,'development_calibration_seed_family':21,'validation_seed_family':28,'elapsed_seconds':time.perf_counter()-started,'versions':{'python':platform.python_version(),'numpy':np.__version__},
        'not_a_resource_world_benchmark':True,'fit_failures_or_bounds':prep.to_dict()['noise_diagnostics']}
    result['passed']=all(result['checks'].values());write(out/'checks.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/first_crossing');p.add_argument('--B',type=int,default=2000);p.add_argument('--n-validation',type=int,default=2000);a=p.parse_args()
    r=export_fixture(a.out,a.B,a.n_validation);print(json.dumps({k:v for k,v in r.items() if k!='fit_failures_or_bounds'},indent=2));raise SystemExit(not r['passed'])
