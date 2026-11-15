from dataclasses import replace,asdict
import copy
import json
from pathlib import Path
import ast
import numpy as np
import pytest

from canary_ssm.public_adjustment import (PublicPanel,HealthyDevelopment,AdjustmentPolicy,
    FrozenAdjustment,fit_development,panel_from_time_slice,MODEL_ID,FEATURE_ID)
from canary_ssm.factor import MIN_CANARY_FRAC,MIN_CONTROLS_PER_CLASS,project_rank_one_controls
from canary_ssm.seeds import seed_for
from canary_ssm.telemetry import CausalWindowStore,PublicRecord,digest


@pytest.fixture(scope='module')
def panels():
    rng=np.random.default_rng(seed_for('world_dev',0));N=10;T=120
    def build(run):
        x=rng.normal(2,.3,(T,N));f=rng.normal(0,.02,T)
        y=5+.2*(x-2)+np.arange(1,N+1)[None]/5*f[:,None]+rng.normal(0,.005,(T,N))
        one=np.ones((T,N),bool);zero=~one
        return PublicPanel(run,tuple('h'+str(i) for i in range(N)),tuple('a' if i<5 else 'b' for i in range(N)),
            (0,)*N,np.arange(T)*60+60,y,x,one,one,zero,one)
    return build('dev'),build('target')


@pytest.fixture(scope='module')
def learned(panels):
    policy=AdjustmentPolicy('demo-rack-v1',group_by='rack_id',deviation_reason='Rack grouping with research 80%/3 thresholds')
    return fit_development([HealthyDevelopment(panels[0],'development',True,'declared-healthy-dev')],['h0','h5'],policy)


def tiny_model(canaries=2,rank=1,policy=None):
    n=canaries+3;ids=['c'+str(i) for i in range(canaries)]+['ref0','ref1','ref2']
    p=policy or AdjustmentPolicy(factor_rank=rank)
    data={'model_id':MODEL_ID,'feature_id':FEATURE_ID,'policy':asdict(p),'host_ids':ids,'rack_ids':['rack']*n,'class_ids':[0]*n,
        'groups':['0']*n,'canary_ids':ids[:canaries],'x_center':0,'mu':[0]*n,'beta':[0]*n,
        'loadings':list(range(2,2+canaries))+[1]*3,'control_variance':[4]*n,'scales':[2]*n,
        'noise':{'0':{'phi':.6,'q':.1,'v':.5}},'noise_fit_ok':True,'factor_identified':True,
        'workload_support':[[-10,10]]*n,'challenges':['background_control_contamination_possible','plain_weighted_projection_not_robust']}
    model=FrozenAdjustment(data)
    T=3;one=np.ones((T,n),bool);zero=~one
    values=np.tile(data['loadings'],(T,1)).astype(float)
    panel=PublicPanel('tiny',tuple(ids),('rack',)*n,(0,)*n,np.array([60,120,180]),values,np.zeros_like(values),one,one,zero,one)
    return model,panel


def test_hand_computed_projection_residual_and_full_shared_covariance_once():
    m,p=tiny_model();out=m.prepare(p,120).transform(p)
    assert np.allclose(out['factor'],1) and np.allclose(out['control_estimation_uncertainty'],4/3)
    assert np.allclose(out['residuals'],0) # subtract lambda*f exactly once, no second control mean
    assert out['reference_subtractions']==1
    expected=np.array([[4,6],[6,9]])*4/3
    assert np.allclose(out['shared_reference_covariance'][0],expected)
    assert out['shared_reference_covariance'][0,0,1]==pytest.approx(8)
    assert np.allclose(out['measurement_covariance'][0],expected+np.eye(2)*.25)
    assert np.linalg.eigvalsh(out['measurement_covariance'][0]).min()>0
    assert not out['control_mask'][:,:2].any()


def test_exposed_and_stale_controls_are_removed_and_uncertainty_increases():
    m,p=tiny_model();prepared=m.prepare(p,120)
    exposed=p.exposed.copy();exposed[2,2]=True
    changed=replace(p,exposed=exposed);out=prepared.transform(changed)
    assert not out['eligible'][2] and out['fresh_control_counts']['0'][2]==2
    assert out['control_estimation_uncertainty'][2]==pytest.approx(2)
    fresh=p.fresh.copy();fresh[2,2]=False
    assert not prepared.transform(replace(p,fresh=fresh))['eligible'][2]


def test_research_eighty_percent_and_three_controls_exact_boundaries():
    assert MIN_CANARY_FRAC==.8 and MIN_CONTROLS_PER_CLASS==3
    m,p=tiny_model(canaries=5);prepared=m.prepare(p,120)
    observed=p.observed.copy();observed[1,0]=False;observed[2,:2]=False
    out=prepared.transform(replace(p,observed=observed))
    assert out['canary_coverage'][1]==.8 and out['eligible'][1]
    assert out['canary_coverage'][2]==.6 and not out['eligible'][2]
    assert np.all(out['fresh_control_counts']['0']==3)


def test_policy_changes_require_versioned_demo_reason():
    with pytest.raises(ValueError):AdjustmentPolicy(min_controls=2)
    with pytest.raises(ValueError):AdjustmentPolicy('demo-small-v2',min_controls=2)
    policy=AdjustmentPolicy('demo-small-v2',min_controls=2,min_canary_fraction=.6,deviation_reason='Explicit small-demo ablation')
    m,p=tiny_model(policy=policy);ex=p.exposed.copy();ex[2,2]=True
    out=m.prepare(p,120).transform(replace(p,exposed=ex))
    assert out['eligible'][2] and out['policy']['min_controls']==2 and out['policy']['policy_id']=='demo-small-v2'


def test_rack_overlap_is_checked_per_monitored_rack_not_global(learned,panels):
    p=panels[1];prepared=learned.prepare(p,4860)
    fresh=p.fresh.copy();fresh[100,1:3]=False # rack a now has only two controls; rack b still has four
    out=prepared.transform(replace(p,fresh=fresh))
    assert out['fresh_control_counts']['a'][100]==2 and out['fresh_control_counts']['b'][100]==4
    assert not out['eligible'][100] and 'insufficient_fresh_controls:a' in out['quality_flags'][100]
    ex=p.exposed.copy();ex[101,1]=True
    out=prepared.transform(replace(p,exposed=ex))
    assert out['fresh_control_counts']['a'][101]==3 and out['eligible'][101]
    assert not out['control_mask'][101,1]


def test_development_coefficients_are_frozen_and_match_independent_ols(learned,panels):
    p=panels[0];d=learned.to_dict();center=p.x.mean()
    for j in range(len(p.host_ids)):
        design=np.column_stack([np.ones(len(p.times)),p.x[:,j]-center])
        independent=np.linalg.solve(design.T@design,design.T@p.y[:,j])
        assert np.allclose([d['mu'][j],d['beta'][j]],independent,atol=1e-10)
    assert d['development_lineage'][0]['role']=='development' and d['noise_fit_ok']
    assert all(s>0 for s in d['scales']) and all(g in d['noise'] for g in ('a','b'))
    assert d['development_control_counts']=={'a':4,'b':4}


@pytest.mark.parametrize('role',['smoke','threshold-calibration','null-validation','final-test'])
def test_no_other_data_role_can_fit(panels,role):
    with pytest.raises(ValueError):fit_development([HealthyDevelopment(panels[0],role,True,'bad-role')],['h0'])


def test_healthy_attestation_and_public_exposure_are_required(panels):
    p=panels[0]
    with pytest.raises(ValueError):fit_development([HealthyDevelopment(p,'development',False,'not-healthy')],['h0'])
    ex=p.exposed.copy();ex[0,1]=True
    with pytest.raises(ValueError):fit_development([HealthyDevelopment(replace(p,exposed=ex),'development',True,'exposed')],['h0'])


def test_pre_exposure_only_adaptation_and_future_perturbation(learned,panels):
    p=panels[1];state=learned.to_dict();a=learned.prepare(p,4860)
    yy=p.y.copy();xx=p.x.copy();yy[100:]+=10;xx[100:]+=30
    later=replace(p,y=yy,x=xx);b=learned.prepare(later,4860)
    assert a.loadings==b.loadings and a.pre_counts==b.pre_counts
    r1=a.transform(p);r2=b.transform(later)
    for key in ('residuals','factor','control_estimation_uncertainty','shared_reference_covariance','measurement_covariance','observed','eligible'):
        assert np.array_equal(r1[key][:100],r2[key][:100],equal_nan=True),key
    assert learned.to_dict()==state
    assert r1['noise']==r2['noise'] and np.array_equal(r1['scales'],r2['scales'])


def test_actual_early_exposure_caps_adaptation_and_fallback_is_explicit(learned,panels):
    p=panels[1];ex=p.exposed.copy();ex[50:,0]=True
    yy=p.y.copy();yy[50:,0]+=99
    state=learned.prepare(replace(p,exposed=ex,y=yy),4860)
    assert state.pre_counts[0]==50 and state.fallback[0]
    assert state.loadings[0]==learned.to_dict()['loadings'][0]
    assert state.cutoffs[0]==p.times[50]
    with pytest.raises(ValueError):state.transform(replace(p,run_id='other-run'))
    with pytest.raises(ValueError):state.transform(replace(p,epoch=1))


def test_rank_zero_is_workload_only_and_keeps_eligibility_defaults():
    m,p=tiny_model(rank=0);out=m.prepare(p,120).transform(p)
    assert np.allclose(out['residuals'],p.y[:,:2])
    assert np.all(out['factor']==0) and np.all(out['control_estimation_uncertainty']==0)
    assert np.all(out['shared_reference_covariance']==0) and out['reference_subtractions']==0
    ex=p.exposed.copy();ex[2,2]=True
    assert not m.prepare(p,120).transform(replace(p,exposed=ex))['eligible'][2]


def test_control_contamination_is_a_challenge_not_a_hidden_robust_estimator():
    m,p=tiny_model();y=p.y.copy();y[2,2:]+=9
    out=m.prepare(p,120).transform(replace(p,y=y))
    assert out['factor'][2]==pytest.approx(10)
    assert out['residuals'][2,0]==pytest.approx(-18) # contaminated reference can hide a positive signal
    assert 'plain_weighted_projection_not_robust' in out['challenges']
    assert 'background_control_contamination_possible' in out['challenges']
    assert not any('fault_type' in name for name in out)


def public_slice(extra_service=False):
    roster=[dict(host_id=f'h{i}',rack_id='rack',class_id=0,service_id='service',replica_id=f'r{i}') for i in range(5)]
    if extra_service:roster.append(dict(host_id='h2',rack_id='rack',class_id=0,service_id='other',replica_id='other-r'))
    s=CausalWindowStore('public',roster,interval_seconds=30)
    for time in (30,60):
        for meta in roster:
            row=PublicRecord(record_id=f"{meta['replica_id']}-{time}",run_id='public',**meta,release_id='v1',
                exposed=meta['service_id']=='other',event_time=time,arrival_time=time,interval_seconds=30,
                request_count=1,latency_ms=100,workload=10,latency_sum_ms=100,latency_sum_sq_ms2=10000,
                log_latency_sum=np.log(100).item(),log_latency_sum_sq=np.log(100).item()**2,latency_observed=True)
            s.ingest(row,time)
    return s.time_slice(60)


def test_public_slice_conversion_checks_hash_masks_and_host_wide_exposure():
    sliced=public_slice(True);p=panel_from_time_slice(sliced,'service')
    assert p.y.shape==(1,5) and p.exposed[0,2] and p.exposure_known[0,2]
    assert p.y[0,0]==pytest.approx(np.log(100)) and p.x[0,0]==pytest.approx(np.log1p(10))
    bad=copy.deepcopy(sliced);bad['windows'][0]['fault_type']='cpu_throttle';bad['input_sha256']=digest(bad['windows'])
    with pytest.raises(ValueError):panel_from_time_slice(bad,'service')
    bad=copy.deepcopy(sliced);bad['windows'][0]['run_id']='other';bad['input_sha256']=digest(bad['windows'])
    with pytest.raises(ValueError):panel_from_time_slice(bad,'service')
    bad=copy.deepcopy(sliced);bad['windows'][0]['log_latency_mean']=999
    with pytest.raises(ValueError):panel_from_time_slice(bad,'service')


def test_multiple_same_service_replicas_are_not_independent_controls():
    s=public_slice();row=copy.deepcopy(s['windows'][0]);row['replica_id']='duplicate';s['windows'].append(row);s['input_sha256']=digest(s['windows'])
    with pytest.raises(ValueError,match='multiple'):panel_from_time_slice(s,'service')


def test_frozen_artifact_hash_and_returned_parameter_copies(learned,tmp_path):
    path=tmp_path/'model.json';learned.save(path)
    assert FrozenAdjustment.load(path).to_dict()==learned.to_dict()
    copy_data=learned.to_dict();copy_data['mu'][0]=999
    assert learned.to_dict()['mu'][0]!=999
    changed=json.loads(path.read_text());changed['beta'][0]=999;path.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='hash'):FrozenAdjustment.load(path)
    with pytest.raises(AttributeError):learned.policy=AdjustmentPolicy()


def test_inference_paths_never_import_evaluator_or_generator_truth():
    root=Path(__file__).resolve().parents[1]/'canary_ssm'
    for name in ('public_adjustment','factor','preprocess','hierarchy','kalman','decision','telemetry','telemetry_transport'):
        tree=ast.parse((root/f'{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):assert not any(x in (node.module or '') for x in ('simulate','metrics','telemetry_evaluator','scenario_bundles','world_evaluator','fault_scheduler'))


def test_zero_factor_information_is_flagged_and_rank_zero_can_still_adjust():
    n=5;T=70;one=np.ones((T,n),bool);zero=~one
    p=PublicPanel('constant',tuple(f'h{i}' for i in range(n)),('rack',)*n,(0,)*n,
        np.arange(T)*60+60,np.ones((T,n))*5,np.ones((T,n))*2,one,one,zero,one)
    for rank in (0,1):
        m=fit_development([HealthyDevelopment(p,'development',True,'constant-healthy')],['h0','h1'],AdjustmentPolicy(factor_rank=rank))
        result=m.prepare(p,4200).transform(p)
        assert m.to_dict()['regression_flags']==['workload_not_identified']*5
        if rank:
            assert not m.to_dict()['factor_identified'] and not result['eligible'].any()
            assert 'factor_not_identified_or_no_fresh_information' in result['quality_flags'][0]
        else:
            assert np.allclose(result['residuals'],0) and np.all(result['control_estimation_uncertainty']==0)


def test_wrong_frozen_dimensions_or_covariance_parameters_are_rejected():
    model,p=tiny_model();d=model.to_dict();d['control_variance'][0]=-1
    with pytest.raises(ValueError):FrozenAdjustment(d)
    d=model.to_dict();d['scales'].pop()
    with pytest.raises(ValueError):FrozenAdjustment(d)


def test_pre_exposure_outputs_are_diagnostic_not_historical_decisions(learned,panels):
    p=panels[1];out=learned.prepare(p,4860).transform(p)
    assert not out['eligible'][:80].any() and out['availability_eligible'][:80].any()
    assert 'pre_exposure_diagnostic_only' in out['quality_flags'][0]
    with pytest.raises(ValueError):learned.prepare(p,-1)


def test_pre_loading_fit_does_not_borrow_missing_rack_support(learned,panels):
    p=panels[1];fresh=p.fresh.copy();fresh[:80,1:3]=False
    prepared=learned.prepare(replace(p,fresh=fresh),4860)
    assert prepared.pre_counts==(0,80) and prepared.fallback==(True,False)


def test_loading_adaptation_cannot_use_pre_event_data_that_arrives_after_freeze(learned,panels):
    p=panels[1];delayed=replace(p,decision_times=p.times+120)
    a=learned.prepare(delayed,4860)
    y=delayed.y.copy();y[79,0]+=99 # end=4800 but unavailable until 4920, after the freeze
    b=learned.prepare(replace(delayed,y=y),4860)
    assert a.pre_counts==(79,79) and a.loadings==b.loadings


def test_missing_minutes_cannot_be_compacted_in_noise_training(panels):
    p=panels[0];times=p.times.copy();times[50:]+=60
    with pytest.raises(ValueError,match='missing rows'):replace(p,times=times,decision_times=times)
