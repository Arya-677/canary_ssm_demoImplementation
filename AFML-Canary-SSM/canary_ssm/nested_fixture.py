"""Deterministic nested-basis/uncertainty checks, not development selection or calibration."""
import argparse
import csv
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy

from .nested_hierarchy import NestedParams,nested_structure,NestedGaussianEffects,run_nested
from .public_filter import Observations
from .public_adjustment import FrozenAdjustment,serial
from .telemetry import digest


def analytic_case(racks):
    n=len(racks);times=np.array([60.,120.,180.,240.])
    residuals=np.cos(np.arange(4*n).reshape(4,n))*.08
    observed=np.ones((4,n),bool)
    if n>1:observed[2,0]=False
    return Observations(times,times,residuals,observed,np.ones(4,bool),times>=120,
        np.tile(np.diag(np.linspace(.1,.3,n))+.01*np.ones((n,n)),(4,1,1)),
        np.full(n,.5),np.full(n,.02),np.ones(n),tuple(f'h{i}' for i in range(n)),120.,'nested-analytic')


def export_fixture(directory):
    started=time.perf_counter();out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    settings=NestedParams(**json.loads((root/'configs/hierarchy_nested_v1.json').read_text()))
    checks={};basis_rows=[];outputs={}
    for name,racks in [('unequal',('a','a','a','b','b','c')),('single_rack',('a','a','a')),
                       ('singletons',('a','b','c')),('one_host',('a',))]:
        data=analytic_case(racks);st=nested_structure(data.host_ids,racks)
        result=NestedGaussianEffects(st,settings).run(data);outputs[name]=result
        (out/f'{name}.json').write_text(json.dumps(serial(result),indent=2,allow_nan=False)+'\n')
        n,G=st.C.shape
        metrics={'ones_R':float(np.max(np.abs(np.ones(n)@st.R),initial=0)),
            'R_orthonormal':float(np.max(np.abs(st.R.T@st.R-np.eye(G-1)),initial=0)),
            'within_rack_sum':float(np.max(np.abs(st.C.T@st.B),initial=0)),
            'R_B':float(np.max(np.abs(st.R.T@st.B),initial=0)),
            'weighted_rack_mean':float(np.max(np.abs(st.counts@st.rack_map),initial=0))}
        for metric,value in metrics.items():basis_rows.append([name,n,G,metric,value])
        checks['basis_'+name]=all(v<1e-12 for v in metrics.values())
        mean=sum(v['host_mean'] for v in result['components'].values())
        cov=sum(v['host_covariance'] for v in result['components'].values())
        for cross in result['component_cross_covariances'].values():cov=cov+cross+cross.transpose(0,2,1)
        checks['reconstruction_'+name]=bool(np.allclose(mean,result['total_host_effect_mean'],atol=1e-12,equal_nan=True) and np.allclose(cov,result['total_host_effect_covariance'],atol=1e-12,equal_nan=True))
    with (out/'basis_checks.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['case','n_hosts','n_racks','metric','absolute_error']);w.writerows(basis_rows)
    with (out/'components.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['event_time','host_id','component','mean','variance'])
        result=outputs['unequal']
        for t,now in enumerate(analytic_case(('a','a','a','b','b','c')).times):
            if now<120:continue
            for j in range(6):
                for name,value in result['components'].items():w.writerow([int(now),f'h{j}',name,float(value['host_mean'][t,j]),float(value['host_covariance'][t,j,j])])
                w.writerow([int(now),f'h{j}','total',float(result['total_host_effect_mean'][t,j]),float(result['total_host_effect_covariance'][t,j,j])])
    source=root/'examples/grouped_hierarchy'
    adjusted=json.loads((source/'adjusted_rack.json').read_text());model=FrozenAdjustment.load(source/'model_rack.json')
    public=run_nested(adjusted,model,settings)
    (out/'public_nested.json').write_text(json.dumps(serial(public),indent=2,allow_nan=False)+'\n')
    checks['diagnostic_only']=not bool(public['output']['decision_eligible'].any()) and public['thresholds'] is None and public['alarms'] is None
    checks['separate_new_protocol']=public['development_selection_required'] and public['calibration_required'] and public['pipeline_id']=='nested-global-rack-host-v1'
    checks['noise_excluded_from_risk']=all(np.all(result['effect_risk_map'][:,len(result['host_ids']):]==0) for result in outputs.values())
    manifest={'fixture_id':'nested-gaussian-acceptance-v1','acceptance_only':True,'new_random_seeds':[],
        'checks':checks,'passed':all(checks.values()),'configuration':serial(settings.__dict__),
        'configuration_sha256':digest(settings.__dict__),'public_input_sha256':digest(adjusted),
        'protocol_fingerprint':public['protocol_fingerprint'],'git_commit':None,'source_kind':'extracted_archive',
        'source_hashes':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('nested_hierarchy.py','nested_fixture.py','public_filter.py')},
        'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
        'machine':{'system':platform.system(),'architecture':platform.machine()},'elapsed_seconds':time.perf_counter()-started,
        'failures':[k for k,v in checks.items() if not v],'development_selection_performed':False,'calibration_performed':False}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',default='examples/nested_hierarchy')
    result=export_fixture(parser.parse_args().out);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
