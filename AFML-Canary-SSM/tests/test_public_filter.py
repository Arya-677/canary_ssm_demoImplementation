"""Independent conditioning references; no simulator/evaluator input to inference."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import block_diag

from canary_ssm.kalman import KalmanFilter
from canary_ssm.preprocess import scalar_nll, fit_ar_class
from canary_ssm.public_filter import (Observations, GaussianEffects,
    observations_from_adjustment, run_comparison)
from canary_ssm.public_adjustment import FrozenAdjustment
from canary_ssm.hierarchy import EffectParams


def small(times=(60,120,180,240), exposure=180):
    times=np.array(times,float);T=len(times)
    return Observations(times,times,np.arange(T*2).reshape(T,2)/20,
        np.ones((T,2),bool),np.ones(T,bool),times>=exposure,
        np.tile([[.3,.12],[.12,.4]],(T,1,1)),[.7,.4],[.1,.2],
        [1.,1.],('a','b'),float(exposure),'run')


def replace(data,**kwargs):
    return Observations(**{**vars(data),**kwargs})


def conditioned(m,P,y,H,V):
    # Independent Gaussian conditional / covariance downdate, not Joseph code.
    gain=P@H.T@np.linalg.inv(H@P@H.T+V)
    return m+gain@(y-H@m),P-gain@H@P


def test_requested_scalar_exact_values_again():
    f=KalmanFilter(np.eye(1),np.array([[.1]]),np.zeros(1),np.eye(1))
    f.step(np.ones(1),np.eye(1),np.array([[.5]]))
    np.testing.assert_allclose([f.m[0],f.P[0,0]],[.6875,.34375],atol=1e-15)
    f.step(np.ones(1),np.eye(1),np.array([[.5]]))
    np.testing.assert_allclose([f.m[0],f.P[0,0]],[126/151,71/302],atol=1e-15)


def test_multivariate_information_form_subset_and_repeated_gap():
    F=np.array([[.9,.2],[0,.8]]);Q=np.array([[.1,.02],[.02,.2]])
    P=np.array([[1.,.3],[.3,.7]]);m=np.array([.2,-.1]);f=KalmanFilter(F,Q,m,P)
    H=np.array([[1.,2.],[-1.,.5]]);V=np.array([[.4,.1],[.1,.6]])
    for gap,idx,y in [(1,[0,1],[.5,-.2]),(3,[1],[.8]),(2,[],[])]:
        for _ in range(gap):m=F@m;P=F@P@F.T+Q
        if idx:m,P=conditioned(m,P,np.array(y),H[idx],V[np.ix_(idx,idx)])
        f.step(np.array(y) if idx else None,H[idx],V[np.ix_(idx,idx)],gap)
        np.testing.assert_allclose(f.m,m,atol=2e-14)
        np.testing.assert_allclose(f.P,P,atol=2e-14)
        assert np.linalg.eigvalsh(f.P).min()>0


def test_no_effect_likelihood_matches_common_engine_with_missing_and_white_X():
    R=np.array([[.1,np.nan,-.2,.3],[.4,.1,np.nan,np.nan]])
    X=np.array([[.1,.2,.3,.1],[.2,.1,.3,.2]])
    phi,q,v=.6,.12,.08;expected=0.
    for row,extra in zip(R,X):
        f=KalmanFilter(np.array([[phi]]),np.array([[q*q]]),np.zeros(1),np.array([[q*q/(1-phi*phi)]]))
        for t,y in enumerate(row):
            f.predict(0 if t==0 else 1)
            if np.isfinite(y):
                S=f.P[0,0]+v*v+extra[t];e=y-f.m[0]
                expected+=.5*(np.log(S)+e*e/S)
                f.update(np.array([y]),np.eye(1),np.array([[v*v+extra[t]]]))
    assert scalar_nll([phi,np.log(q),np.log(v)],R,X)==pytest.approx(expected,abs=1e-12)


def test_noise_fit_records_all_failures_bounds_and_white_floor(monkeypatch):
    def failed(fun,x0,**kw):
        x=np.array([kw['bounds'][0][0],kw['bounds'][1][0]])
        return SimpleNamespace(x=x,fun=2.,success=False,status=2,message='fixture failure',nit=1,nfev=3)
    monkeypatch.setattr('canary_ssm.preprocess.minimize',failed)
    p,rec=fit_ar_class(np.ones((2,4)),np.zeros((2,4)),fix_v=True)
    assert len(rec)==3 and all(not r['success'] and r['boundary_hit'] for r in rec)
    assert all(r['message']=='fixture failure' and r['status']==2 and r['bounds'] and r['white_sd_fixed']==1e-4 for r in rec)
    assert np.exp(p[2])==pytest.approx(1e-4)


@pytest.mark.parametrize('kind',['indep','pooled'])
def test_public_effects_match_independent_joint_conditioning_and_carry_AR(kind):
    data=small((60,120,180,360));mask=data.observed.copy();mask[3,0]=False
    data=replace(data,observed=mask)
    p=EffectParams(kind=kind,rho_g=.8,sd_g=.05,prior_sd=.3)
    out=GaussianEffects(p).run(data);n=2;phi=data.phi;q=data.q
    Fe=np.diag(phi);Qe=np.diag(q*q)
    m=np.zeros(n);P=np.diag(q*q/(1-phi*phi))
    for t in range(2):
        m=Fe@m;P=Fe@P@Fe.T+Qe
        m,P=conditioned(m,P,data.residuals[t],np.eye(2),data.V[t])
    m=Fe@m;P=Fe@P@Fe.T+Qe  # AR prediction to the exposure boundary
    L=np.eye(2) if kind=='indep' else np.ones((2,1));d=L.shape[1]
    jointm=np.r_[np.zeros(d),m];jointP=block_diag(np.eye(d)*.3**2,P)
    np.testing.assert_allclose(out['prior_at_exposure']['mean'],jointm)
    np.testing.assert_allclose(out['prior_at_exposure']['covariance'],jointP)
    assert np.isnan(out['host_effect_mean'][:2]).all()
    assert np.max(np.abs(m))>0  # distinguish carried noise from a stationary reset
    F=block_diag(.8*np.eye(d),Fe);Q=block_diag(.05**2*np.eye(d),Qe)
    H=np.hstack([L,np.eye(2)]);A=np.hstack([L,np.zeros((2,2))])
    for t,gap in [(2,0),(3,3)]:
        for _ in range(gap):jointm=F@jointm;jointP=F@jointP@F.T+Q
        idx=np.flatnonzero(data.use[t]);jointm,jointP=conditioned(jointm,jointP,data.residuals[t,idx],H[idx],data.V[t][np.ix_(idx,idx)])
        np.testing.assert_allclose(out['host_effect_mean'][t],A@jointm,atol=1e-12)
        np.testing.assert_allclose(out['host_effect_covariance'][t],A@jointP@A.T,atol=1e-12)
    if kind=='pooled':
        assert out['host_effect_mean'][3,0]==pytest.approx(out['host_effect_mean'][3,1])
    else:
        assert abs(out['host_effect_covariance'][2,0,1])>1e-8


def test_missing_and_ineligible_minutes_predict_only_no_score():
    data=small();elig=data.eligible.copy();elig[2:]=False
    data=replace(data,eligible=elig)
    out=GaussianEffects().run(data)
    assert not out['updated'][2:].any() and np.isnan(out['score']).all()
    assert np.isfinite(out['host_effect_mean'][2:]).all()


def test_late_preperiod_receipt_never_revises_exposure_AR_state():
    data=small();deadlines=data.decision_times.copy();deadlines[1]=200;deadlines[2]=220
    data=replace(data,decision_times=deadlines)
    changed=data.residuals.copy();changed[1]+=100
    a=GaussianEffects().run(data);b=GaussianEffects().run(replace(data,residuals=changed))
    assert not data.use[1].any()
    np.testing.assert_array_equal(a['prior_at_exposure']['mean'],b['prior_at_exposure']['mean'])
    np.testing.assert_allclose(a['score'],b['score'],equal_nan=True)


def test_no_preperiod_and_first_post_gap_has_exposure_prior():
    data=small((300,360),exposure=180)
    out=GaussianEffects().run(data)
    assert out['ar_stationary_initialization']
    assert out['prior_at_exposure']['event_time']==180
    np.testing.assert_allclose(np.diag(out['prior_at_exposure']['covariance'])[:2],.03**2)


@pytest.fixture
def artifact():
    r=Path(__file__).resolve().parents[1]/'examples/control_adjustment'
    return json.loads((r/'adjusted_rank1.json').read_text()),FrozenAdjustment.load(r/'model_rank1.json')


def test_comparators_share_masks_and_have_no_fake_posteriors(artifact):
    a,m=artifact;data=observations_from_adjustment(a,m);result=run_comparison(a,m)
    np.testing.assert_array_equal(result['used_observations'],data.use)
    assert result['thresholds'] is None and result['alarms'] is None
    for name in ('adj_ewma','adj_cusum','topk_cusum'):
        b=result['outputs'][name]
        assert b['posterior'] is None and b['host_probability'] is None
        assert b['output_kind']=='sequential_statistic'
        assert np.isnan(b['score'][~data.eligible]).all()
    # Independent hand CUSUM recurrence on the shared standardized input.
    C=np.zeros(2);t0=np.searchsorted(data.times,data.exposure_time)
    for t in range(t0,len(data.times)):
        ok=data.use[t];C[ok]=np.maximum(0,C[ok]+data.residuals[t,ok]/data.scales[ok]-.25)
        np.testing.assert_allclose(result['outputs']['adj_cusum']['host_score'][t],C)


def test_future_perturbation_preserves_all_methods(artifact):
    a,m=artifact;b=copy.deepcopy(a)
    for row in b['residuals'][110:]:
        for j,x in enumerate(row):
            if x is not None:row[j]+=5
    x=run_comparison(a,m);y=run_comparison(b,m)
    for name in x['outputs']:
        np.testing.assert_allclose(x['outputs'][name]['score'][:110],y['outputs'][name]['score'][:110],equal_nan=True)
    np.testing.assert_allclose(x['outputs']['indep_ssm']['host_effect_covariance'][:110],y['outputs']['indep_ssm']['host_effect_covariance'][:110],equal_nan=True)


@pytest.mark.parametrize('change',['diagonal','double','noise','reference','early'])
def test_adapter_rejects_changed_covariance_noise_reference_and_onset(artifact,change):
    a,m=artifact;a=copy.deepcopy(a)
    if change=='diagonal':a['measurement_covariance']=[np.diag(np.diag(v)).tolist() for v in np.asarray(a['measurement_covariance'],float)]
    if change=='double':a['measurement_covariance']=(np.asarray(a['measurement_covariance'],float)+np.asarray(a['shared_reference_covariance'],float)).tolist()
    if change=='noise':a['noise']['a']['q']*=2
    if change=='reference':a['reference_subtractions']=2
    if change=='early':a['loading_cutoffs'][0]=60
    with pytest.raises(ValueError):observations_from_adjustment(a,m)


def test_invalid_covariance_and_noise_and_time_rejected():
    data=small()
    for kwargs in ({'q':[0,.2]},{'phi':[1,.4]},{'times':[60,121,180,240]},
                   {'V':np.tile([[1.,2.],[2.,1.]],(4,1,1))}):
        with pytest.raises(ValueError):replace(data,**kwargs)


def test_detector_boundary_has_no_truth_imports():
    root=Path(__file__).resolve().parents[1]/'canary_ssm'
    for module in ('public_filter','public_adjustment','kalman','preprocess','hierarchy','baselines'):
        tree=ast.parse((root/(module+'.py')).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not any(s in (node.module or '') for s in ('simulate','truth','metrics','evaluator','scenario'))
            if isinstance(node,ast.Import):
                assert not any(any(s in n.name for s in ('simulate','truth','metrics','evaluator','scenario')) for n in node.names)
