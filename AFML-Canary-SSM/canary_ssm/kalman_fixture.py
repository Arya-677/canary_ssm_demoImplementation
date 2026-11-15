"""Numerical acceptance fixtures and uncalibrated public comparisons; no benchmarks."""
import argparse
import csv
import json
import hashlib
import platform
import time
import scipy
from pathlib import Path
import numpy as np

from .kalman import KalmanFilter
from .public_filter import run_comparison
from .public_adjustment import FrozenAdjustment, serial
from .telemetry import digest


def export_fixture(directory, adjustment_directory=None):
    started=time.perf_counter()
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    source=Path(adjustment_directory or Path(__file__).resolve().parents[1]/'examples/control_adjustment')
    rows=[]
    k=KalmanFilter(np.eye(1),np.array([[.1]]),np.zeros(1),np.eye(1))
    for step,(mean,cov) in enumerate(((.6875,.34375),(126/151,71/302)),1):
        k.step(np.ones(1),np.eye(1),np.array([[.5]]))
        rows.extend([('scalar',step,'mean',float(k.m[0]),mean),('scalar',step,'covariance',float(k.P[0,0]),cov)])
    F=np.array([[.9,.2],[0,.8]]);Q=np.array([[.1,.02],[.02,.2]])
    m=np.array([.2,-.1]);P=np.array([[1.,.3],[.3,.7]])
    H=np.array([[1.,2.],[-1.,.5]]);V=np.array([[.4,.1],[.1,.6]]);y=np.array([.5,-.2])
    prior=F@P@F.T+Q;prior_m=F@m
    # Independent information-form reference, rather than Joseph update.
    expected_cov=np.linalg.inv(np.linalg.inv(prior)+H.T@np.linalg.inv(V)@H)
    expected_mean=expected_cov@(np.linalg.solve(prior,prior_m)+H.T@np.linalg.solve(V,y))
    k=KalmanFilter(F,Q,m,P);k.step(y,H,V)
    for j in range(2):
        rows.append(('multivariate',1,f'mean_{j}',float(k.m[j]),float(expected_mean[j])))
        for z in range(2):rows.append(('multivariate',1,f'covariance_{j}_{z}',float(k.P[j,z]),float(expected_cov[j,z])))
    with (out/'numerical_checks.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['case','step','quantity','actual','reference','absolute_error'])
        w.writerows((*row,abs(row[-2]-row[-1])) for row in rows)
    comparisons={};inputs={}
    for rank in (0,1):
        adjusted=json.loads((source/f'adjusted_rank{rank}.json').read_text())
        model=FrozenAdjustment.load(source/f'model_rank{rank}.json')
        comparison=run_comparison(adjusted,model);comparisons[rank]=comparison
        (out/f'comparison_rank{rank}.json').write_text(json.dumps(serial(comparison),indent=2,allow_nan=False)+'\n')
        inputs[f'adjusted_rank{rank}']=digest(adjusted)
        inputs[f'model_rank{rank}']=digest(model.to_dict())
    checks={'scalar_and_multivariate_reference':all(abs(row[-2]-row[-1])<1e-12 for row in rows),
        'no_pre_exposure_effects':all(np.isnan(v['host_effect_mean'][:80]).all() for c in comparisons.values() for k,v in c['outputs'].items() if k.endswith('_ssm')),
        'full_canary_covariance':bool(np.any(np.abs(comparisons[1]['outputs']['indep_ssm']['host_effect_covariance'][80:,0,1])>1e-12)),
        'pooled_map':bool(np.array_equal(comparisons[1]['outputs']['pooled_ssm']['effect_map'],np.ones((2,1)))),
        'honest_baselines':all(v['host_probability'] is None and v['posterior'] is None for c in comparisons.values() for k,v in c['outputs'].items() if not k.endswith('_ssm')),
        'uncalibrated':all(c['thresholds'] is None and c['alarms'] is None for c in comparisons.values())}
    manifest={'fixture_id':'public-gaussian-acceptance-v1','acceptance_only':True,'new_random_seeds':[],
        'input_hashes':inputs,'checks':checks,'passed':all(checks.values()),'dashboard_connected':False,
        'git_commit':None,'source_kind':'extracted_archive','elapsed_seconds':time.perf_counter()-started,
        'configuration':{'effects':{k:v['parameters'] for k,v in comparisons[1]['outputs'].items() if k.endswith('_ssm')},
            'one_minute_seconds':60,'thresholds':None},
        'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
        'machine':{'system':platform.system(),'architecture':platform.machine()},
        'failures':[k for k,v in checks.items() if not v],
        'source_hashes':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('kalman.py','preprocess.py','public_filter.py','kalman_fixture.py')}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/kalman_engine')
    p.add_argument('--adjustment-directory');args=p.parse_args()
    result=export_fixture(args.out,args.adjustment_directory)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
