import ast
import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from canary_ssm.public_filter import Observations
from canary_ssm.public_adjustment import FrozenAdjustment
from canary_ssm.nested_hierarchy import (NestedParams,nested_structure,NestedGaussianEffects,run_nested)


def data(n=6):
    times=np.array([60.,120.,180.,300.])
    return Observations(times,times,np.sin(np.arange(4*n).reshape(4,n))*.1,
        np.ones((4,n),bool),np.ones(4,bool),times>=120,
        np.tile(np.eye(n)*.2+np.ones((n,n))*.01,(4,1,1)),np.full(n,.5),np.full(n,.02),
        np.ones(n),tuple('h'+str(j) for j in range(n)),120.,'nested-check')


def test_unequal_racks_orthogonal_complete_basis_and_weighted_constraint():
    st=nested_structure(('h2','h0','h4','h1','h3','h5'),('b','a','c','a','b','a'))
    n,G=st.C.shape
    assert st.host_ids==('h2','h0','h4','h1','h3','h5')
    np.testing.assert_array_equal(st.counts,[3,2,1])
    assert st.R.shape==(6,2) and st.B.shape==(6,3)
    np.testing.assert_allclose(np.ones(n)@st.R,0,atol=1e-14)
    np.testing.assert_allclose(st.R.T@st.R,np.eye(G-1),atol=1e-14)
    np.testing.assert_allclose(st.C.T@st.B,0,atol=1e-14)
    np.testing.assert_allclose(st.R.T@st.B,0,atol=1e-14)
    np.testing.assert_allclose(st.B.T@st.B,np.eye(n-G),atol=1e-14)
    np.testing.assert_allclose(st.C@st.rack_map,st.R,atol=1e-14)
    np.testing.assert_allclose(st.counts@st.rack_map,0,atol=1e-14)
    assert np.linalg.matrix_rank(np.hstack([np.ones((n,1)),st.R,st.B]))==n
    np.testing.assert_array_equal(st.R,nested_structure(st.host_ids,st.rack_ids).R)


def test_two_unequal_racks_have_hand_computed_host_contrast():
    st=nested_structure(('h0','h1','h2'),('a','a','b'))
    np.testing.assert_allclose(st.R[:,0],np.array([-1,-1,2])/np.sqrt(6),atol=1e-14)
    assert abs(st.rack_map[:,0].mean())>.1  # constraint is host weighted, not equal rack means


@pytest.mark.parametrize('racks',[('a',),('a','a','a'),('a','b','c'),('a','a','b')])
def test_single_rack_singleton_and_all_singleton_edges(racks):
    D=data(len(racks));st=nested_structure(D.host_ids,racks)
    out=NestedGaussianEffects(st,NestedParams(enabled=True)).run(D)
    n,G=st.C.shape
    assert st.R.shape==(n,G-1) and st.B.shape==(n,n-G)
    assert out['posterior_state_covariance'].shape==(4,2*n,2*n)
    if G==1:
        np.testing.assert_array_equal(out['rack_effect_mean'][1:],np.zeros((3,1)))
        np.testing.assert_array_equal(out['rack_effect_covariance'][1:],np.zeros((3,1,1)))
    if n==G:
        np.testing.assert_array_equal(out['components']['host']['host_mean'][1:],np.zeros((3,n)))
    assert np.isnan(out['components']['rack']['host_mean'][0]).all()


def test_declared_prior_and_noise_matrices_match_projector_formula():
    D=data();st=nested_structure(D.host_ids,('a','a','a','b','b','c'))
    p=NestedParams(enabled=True,prior_global_sd=.1,prior_rack_sd=.2,prior_host_sd=.3,
        sd_global=.01,sd_rack=.02,sd_host=.03,rho_global=.95,rho_rack=.8,rho_host=.6)
    out=NestedGaussianEffects(st,p).run(D)
    rack_projection=(st.C/st.counts[None])@st.C.T;J=np.ones((6,6))
    prior=.1**2*J+.2**2*(rack_projection-J/6)+.3**2*(np.eye(6)-rack_projection)
    process=.01**2*J+.02**2*(rack_projection-J/6)+.03**2*(np.eye(6)-rack_projection)
    np.testing.assert_allclose(out['induced_effect_prior_covariance'],prior,atol=1e-14)
    np.testing.assert_allclose(out['induced_effect_innovation_covariance'],process,atol=1e-14)
    np.testing.assert_allclose(out['state_transition'],np.diag([.95,.8,.8,.6,.6,.6]+[.5]*6))
    H=np.hstack([np.ones((6,1)),st.R,st.B,np.eye(6)])
    np.testing.assert_allclose(out['observation_map'],H)
    np.testing.assert_allclose(out['effect_risk_map'][:,6:],0)
    np.testing.assert_allclose(np.diag(out['process_covariance'])[-6:],.02**2)


def test_full_joint_filter_matches_independent_gaussian_conditioning():
    D=data();mask=D.observed.copy();mask[2,1]=False;D=replace(D,observed=mask)
    out=NestedGaussianEffects(nested_structure(D.host_ids,('a','a','a','b','b','c')),NestedParams(enabled=True)).run(D)
    m=out['prior_at_exposure']['mean'].copy();P=out['prior_at_exposure']['covariance'].copy()
    F=out['state_transition'];Q=out['process_covariance'];H=out['observation_map']
    for t,gap in [(1,0),(2,1),(3,2)]:
        for _ in range(gap):m=F@m;P=F@P@F.T+Q
        idx=np.flatnonzero(D.use[t]);h=H[idx];v=D.V[t][np.ix_(idx,idx)]
        gain=P@h.T@np.linalg.inv(h@P@h.T+v)
        m=m+gain@(D.residuals[t,idx]-h@m);P=P-gain@h@P
        np.testing.assert_allclose(out['posterior_state_mean'][t],m,atol=1e-12)
        np.testing.assert_allclose(out['posterior_state_covariance'][t],P,atol=1e-12)
    assert np.any(np.abs(out['posterior_state_covariance'][1,:6,6:])>1e-12)


def test_components_reconstruct_total_covariance_with_all_cross_terms():
    D=data();mask=D.observed.copy();mask[2,1]=False;D=replace(D,observed=mask)
    st=nested_structure(D.host_ids,('a','a','a','b','b','c'))
    out=NestedGaussianEffects(st,NestedParams(enabled=True)).run(D)
    mean=sum(v['host_mean'] for v in out['components'].values())
    covariance=sum(v['host_covariance'] for v in out['components'].values())
    for cross in out['component_cross_covariances'].values():covariance=covariance+cross+cross.transpose(0,2,1)
    np.testing.assert_allclose(mean,out['total_host_effect_mean'],equal_nan=True,atol=1e-12)
    np.testing.assert_allclose(covariance,out['total_host_effect_covariance'],equal_nan=True,atol=1e-12)
    np.testing.assert_allclose(out['rack_effect_mean'][1:]@st.counts,0,atol=1e-14)
    np.testing.assert_allclose(np.einsum('gi,ti->tg',st.C.T,out['components']['host']['host_mean'][1:]),0,atol=1e-14)
    assert np.any(np.abs(out['component_cross_covariances']['global_rack'][1:])>1e-12)


def test_risk_uses_total_release_effect_and_excludes_AR_noise():
    D=data();out=NestedGaussianEffects(nested_structure(D.host_ids,('a','a','a','b','b','c')),NestedParams(enabled=True)).run(D)
    A=out['effect_risk_map'];P=out['posterior_state_covariance'][1];m=out['posterior_state_mean'][1]
    expected=norm.sf((out['kappa']-A@m)/np.sqrt(np.diag(A@P@A.T)))
    np.testing.assert_allclose(out['host_probability'][1],expected)
    changed=m.copy();changed[6:]+=100
    np.testing.assert_allclose(A@changed,A@m)


def test_roster_permutation_is_invariant_in_host_space():
    D=data();racks=('a','a','a','b','b','c');p=NestedParams(enabled=True)
    a=NestedGaussianEffects(nested_structure(D.host_ids,racks),p).run(D)
    order=np.array([5,2,0,4,1,3]);inverse=np.argsort(order)
    E=replace(D,host_ids=tuple(D.host_ids[j] for j in order),residuals=D.residuals[:,order],observed=D.observed[:,order],
        V=D.V[:,order][:,:,order],phi=D.phi[order],q=D.q[order],scales=D.scales[order])
    b=NestedGaussianEffects(nested_structure(E.host_ids,tuple(racks[j] for j in order)),p).run(E)
    np.testing.assert_allclose(a['total_host_effect_mean'],b['total_host_effect_mean'][:,inverse],equal_nan=True,atol=1e-12)
    np.testing.assert_allclose(a['total_host_effect_covariance'],b['total_host_effect_covariance'][:,inverse][:,:,inverse],equal_nan=True,atol=1e-12)


def test_future_perturbations_leave_past_components_unchanged():
    D=data();st=nested_structure(D.host_ids,('a','a','a','b','b','c'));p=NestedParams(enabled=True)
    a=NestedGaussianEffects(st,p).run(D);y=D.residuals.copy();y[-1]+=100
    b=NestedGaussianEffects(st,p).run(replace(D,residuals=y))
    for name in ('global_effect_mean','rack_effect_mean','total_host_effect_mean','posterior_state_covariance'):
        np.testing.assert_array_equal(a[name][:-1],b[name][:-1])


def test_opt_in_and_new_selection_calibration_are_required():
    D=data();st=nested_structure(D.host_ids,('a','a','a','b','b','c'))
    with pytest.raises(ValueError):NestedGaussianEffects(st)
    out=NestedGaussianEffects(st,NestedParams(enabled=True)).run(D)
    assert out['development_selection_required'] and out['calibration_required']
    assert not out['decision_eligible'].any() and out['inference_use']=='diagnostic_only'
    assert 'score' not in out and 'diagnostic_score' in out
    with pytest.raises(TypeError):NestedParams(enabled=True,threshold=.5)
    with pytest.raises(TypeError):NestedParams(enabled=True,development_selection_required=False)


def test_public_adapter_requires_rack_policy_and_separate_protocol_fingerprint():
    root=Path(__file__).resolve().parents[1]/'examples/grouped_hierarchy'
    a=json.loads((root/'adjusted_rack.json').read_text());m=FrozenAdjustment.load(root/'model_rack.json')
    out=run_nested(a,m,NestedParams(enabled=True))
    assert out['protocol']['variant_id']=='nested-global-rack-host-v1'
    assert len(out['protocol_fingerprint'])==64 and out['thresholds'] is None and out['alarms'] is None
    changed=run_nested(a,m,NestedParams(enabled=True,rho_global=.8))
    assert out['protocol_fingerprint']!=changed['protocol_fingerprint']
    with pytest.raises(ValueError):run_nested(a,m)
    c=json.loads((root/'adjusted_class.json').read_text());cm=FrozenAdjustment.load(root/'model_class.json')
    with pytest.raises(ValueError):run_nested(c,cm,NestedParams(enabled=True))


def test_invalid_crossed_configuration_not_silently_stacked():
    with pytest.raises(ValueError):NestedParams(enabled=True,group_by='class_id')
    with pytest.raises(TypeError):NestedParams(enabled=True,levels=['global','rack_id','class_id','host_id'])
    with pytest.raises(ValueError):NestedParams(enabled=True,prior_rack_sd=0)
    with pytest.raises(ValueError):NestedParams(enabled=True,rho_host=2)
    with pytest.raises(ValueError):nested_structure(('h0','h0'),('a','b'))


def test_nested_detector_does_not_import_generator_or_evaluator():
    path=Path(__file__).resolve().parents[1]/'canary_ssm/nested_hierarchy.py'
    for node in ast.walk(ast.parse(path.read_text())):
        modules=[node.module or ''] if isinstance(node,ast.ImportFrom) else [n.name for n in node.names] if isinstance(node,ast.Import) else []
        assert not any(any(s in m for s in ('simulate','truth','metrics','evaluator','scenario')) for m in modules)
