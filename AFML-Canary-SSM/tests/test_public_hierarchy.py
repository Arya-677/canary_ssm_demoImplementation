import ast
import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy.linalg import block_diag
from scipy.stats import norm

from canary_ssm.hierarchy import EffectParams, build_model, class_structure
from canary_ssm.public_filter import Observations, GaussianEffects
from canary_ssm.public_hierarchy import GroupedParams,grouped_structure,GroupedGaussianEffects
from canary_ssm.public_hierarchy import run_hierarchy
from canary_ssm.public_adjustment import FrozenAdjustment


def data(n=3):
    times=np.array([60,120,180,300.])
    return Observations(times,times,np.arange(4*n).reshape(4,n)*.01,
        np.ones((4,n),bool),np.ones(4,bool),times>=120,
        np.tile(np.eye(n)*.2+np.ones((n,n))*.03,(4,1,1)),
        np.full(n,.5),np.full(n,.01),np.ones(n),tuple('h'+str(i) for i in range(n)),120.,'run')


def test_basis_shapes_noncontiguous_groups_singleton_and_stable_order():
    hosts=('h3','h1','h2','h0','h4')
    st=grouped_structure(hosts,('r2','r1','r2','r1','r0'),'rack_id')
    assert st.host_ids==hosts and st.group_ids==('r0','r1','r2')
    assert st.C.shape==(5,3) and st.B.shape==(5,2)
    np.testing.assert_allclose(st.C.T@st.B,0,atol=1e-14)
    np.testing.assert_allclose(st.B.T@st.B,np.eye(2),atol=1e-14)
    np.testing.assert_array_equal(st.B[4],np.zeros(2))
    np.testing.assert_array_equal(st.C.sum(1),np.ones(5))
    st2=grouped_structure(hosts,('r2','r1','r2','r1','r0'),'rack_id')
    np.testing.assert_array_equal(st.B,st2.B)


def test_class_default_basis_and_matrices_match_research_model():
    labels=(1,0,1);st=grouped_structure(('h0','h1','h2'),labels)
    C,B=class_structure(np.array(labels))
    np.testing.assert_array_equal(st.C,C);np.testing.assert_array_equal(st.B,B)
    oldM,rho,sd=build_model(EffectParams(kind='hier'),np.array(labels))
    out=GroupedGaussianEffects(st).run(data())
    np.testing.assert_array_equal(out['effect_map'],oldM)
    np.testing.assert_allclose(out['state_transition'],block_diag(np.diag(rho),.5*np.eye(3)))
    np.testing.assert_allclose(out['process_covariance'],block_diag(np.diag(sd*sd),.01**2*np.eye(3)))
    assert out['group_by']=='class_id' and out['group_effect_label']=='class_effect'


def test_induced_prior_and_dynamics_are_the_declared_group_host_model():
    p=GroupedParams(group_by='rack_id',variant_id='demo-rack-host-v1',rho_g=.9,rho_h=.6,
        sd_g=.1,sd_h=.03,prior_group_sd=.4,prior_deviation_sd=.2)
    st=grouped_structure(('h0','h1','h2'),('r0','r0','r1'),'rack_id')
    out=GroupedGaussianEffects(st,p).run(data());C,B=st.C,st.B
    expected=.4**2*C@C.T+.2**2*B@B.T
    np.testing.assert_allclose(out['induced_effect_prior_covariance'],expected)
    np.testing.assert_allclose(expected,[[.18,.14,0],[.14,.18,0],[0,0,.16]],atol=1e-14)
    np.testing.assert_allclose(out['state_transition'],np.diag([.9,.9,.6,.5,.5,.5]))
    np.testing.assert_allclose(out['observation_map'],np.hstack([C,B,np.eye(3)]))
    np.testing.assert_allclose(out['effect_risk_map'],np.hstack([C,B,np.zeros((3,3))]))
    np.testing.assert_allclose(out['induced_effect_innovation_covariance'],.1**2*C@C.T+.03**2*B@B.T)


def test_full_joint_posterior_matches_independent_conditional_reference():
    D=data();st=grouped_structure(D.host_ids,(0,0,1));p=GroupedParams(rho_g=.8,rho_h=.3,
        sd_g=.03,sd_h=.01,prior_group_sd=.2,prior_deviation_sd=.07)
    out=GroupedGaussianEffects(st,p).run(D)
    n=3;C,B=st.C,st.B;H=np.hstack([C,B,np.eye(n)]);A=np.hstack([C,B,np.zeros((n,n))])
    # Independently condition the carried-noise prior with a covariance downdate.
    m=out['prior_at_exposure']['mean'].copy();P=out['prior_at_exposure']['covariance'].copy()
    F=out['state_transition'];Q=out['process_covariance']
    for t,gap in [(1,0),(2,1),(3,2)]:
        for _ in range(gap):m=F@m;P=F@P@F.T+Q
        gain=P@H.T@np.linalg.inv(H@P@H.T+D.V[t]);m=m+gain@(D.residuals[t]-H@m);P=P-gain@H@P
        np.testing.assert_allclose(out['posterior_state_mean'][t],m,atol=1e-12)
        np.testing.assert_allclose(out['posterior_state_covariance'][t],P,atol=1e-12)
        np.testing.assert_allclose(out['total_host_effect_covariance'][t],A@P@A.T,atol=1e-12)
    assert np.any(np.abs(out['posterior_state_covariance'][1,:3,3:])>1e-12)


def test_component_outputs_reconstruct_total_with_cross_covariance():
    st=grouped_structure(('h0','h1','h2'),(0,0,1));out=GroupedGaussianEffects(st).run(data())
    total=out['host_group_effect_mean']+out['host_deviation_mean']
    np.testing.assert_allclose(total,out['total_host_effect_mean'],equal_nan=True)
    cross=np.einsum('ig,tgj->tij',st.C,out['group_deviation_cross_covariance'])
    reconstructed=out['host_group_effect_covariance']+out['host_deviation_covariance']+cross+cross.transpose(0,2,1)
    np.testing.assert_allclose(reconstructed,out['total_host_effect_covariance'],equal_nan=True,atol=1e-12)
    np.testing.assert_allclose(out['host_deviation_mean'][1:,2],0,atol=1e-14)
    np.testing.assert_allclose(np.einsum('gi,ti->tg',st.C.T,out['host_deviation_mean'][1:]),0,atol=1e-14)


@pytest.mark.parametrize('n',[1,3])
def test_all_singletons_have_empty_basis_and_zero_deviation(n):
    D=data(n);st=grouped_structure(D.host_ids,tuple(range(n)))
    out=GroupedGaussianEffects(st).run(D)
    assert st.B.shape==(n,0)
    assert np.isnan(out['host_deviation_mean'][0]).all()
    np.testing.assert_array_equal(out['host_deviation_mean'][1:],np.zeros((3,n)))
    np.testing.assert_array_equal(out['host_deviation_covariance'][1:],np.zeros((3,n,n)))


def test_priors_create_real_pooling_without_shared_measurement_noise():
    D=data(2);r=np.zeros((4,2));r[1]=[1,0]
    D=replace(D,residuals=r,V=np.tile(.5*np.eye(2),(4,1,1)))
    st=grouped_structure(D.host_ids,(0,0))
    p=GroupedParams(prior_group_sd=1,prior_deviation_sd=.2)
    hier=GroupedGaussianEffects(st,p).run(D)
    # Match each independent host's marginal prior variance = 1 + .04/2.
    indep=GaussianEffects(EffectParams(kind='indep',prior_sd=np.sqrt(1.02))).run(D)
    assert indep['host_effect_mean'][1,1]==pytest.approx(0,abs=1e-14)
    assert hier['host_effect_mean'][1,1]>.1
    assert hier['host_effect_mean'][1,0]<indep['host_effect_mean'][1,0]
    assert hier['host_effect_covariance'][1,0,1]>0


def test_group_and_deviation_dynamics_have_distinct_predictive_effects():
    D=data(2);r=np.zeros((4,2));r[1]=[1,.1];mask=D.observed.copy();mask[2:]=False
    D=replace(D,residuals=r,observed=mask)
    st=grouped_structure(D.host_ids,(0,0));p=GroupedParams(rho_g=.9,rho_h=.3)
    out=GroupedGaussianEffects(st,p).run(D)
    np.testing.assert_allclose(out['group_effect_mean'][2],.9*out['group_effect_mean'][1])
    np.testing.assert_allclose(out['host_deviation_mean'][2],.3*out['host_deviation_mean'][1])
    assert abs(out['host_deviation_mean'][1,0])>0


def test_host_permutation_preserves_host_space_inference_and_output_identity():
    D=data(3);labels=(0,1,0);st=grouped_structure(D.host_ids,labels)
    a=GroupedGaussianEffects(st).run(D);perm=np.array([2,0,1]);inv=np.argsort(perm)
    E=replace(D,host_ids=tuple(D.host_ids[j] for j in perm),residuals=D.residuals[:,perm],observed=D.observed[:,perm],
        V=D.V[:,perm][:,:,perm],phi=D.phi[perm],q=D.q[perm],scales=D.scales[perm])
    b=GroupedGaussianEffects(grouped_structure(E.host_ids,tuple(labels[j] for j in perm))).run(E)
    np.testing.assert_allclose(a['total_host_effect_mean'],b['total_host_effect_mean'][:,inv],equal_nan=True,atol=1e-12)
    np.testing.assert_allclose(a['total_host_effect_covariance'],b['total_host_effect_covariance'][:,inv][:,:,inv],equal_nan=True,atol=1e-12)
    with pytest.raises(ValueError):GroupedGaussianEffects(st).run(E)


def test_AR_noise_is_excluded_from_effect_risk_and_full_covariance_retained():
    D=data();out=GroupedGaussianEffects(grouped_structure(D.host_ids,(0,0,1))).run(D)
    A=out['effect_risk_map'];H=out['observation_map'];P=out['posterior_state_covariance'][1]
    assert np.all(A[:,3:]==0) and np.all(H[:,3:]==np.eye(3))
    expected=norm.sf((out['kappa']-out['total_host_effect_mean'][1])/np.sqrt(np.diag(A@P@A.T)))
    np.testing.assert_allclose(out['host_probability'][1],expected)
    assert not np.allclose(A@P@A.T,H@P@H.T,atol=1e-12)
    perturb=out['posterior_state_mean'][1].copy();perturb[3:]+=100
    np.testing.assert_allclose(A@perturb,out['total_host_effect_mean'][1])


def test_future_perturbations_do_not_change_past_hierarchy():
    D=data();st=grouped_structure(D.host_ids,(0,0,1));a=GroupedGaussianEffects(st).run(D)
    changed=D.residuals.copy();changed[-1]+=100;b=GroupedGaussianEffects(st).run(replace(D,residuals=changed))
    for key in ('host_probability','total_host_effect_mean','group_effect_mean','host_deviation_mean','posterior_state_covariance'):
        np.testing.assert_array_equal(a[key][:-1],b[key][:-1])


def test_invalid_rosters_and_implicit_rack_variant_rejected():
    for hosts,labels,group in [(('h0','h0'),(0,0),'class_id'),(('h0',),(0,1),'class_id'),(('h0',),(0,),'rack_id')]:
        with pytest.raises(ValueError):grouped_structure(hosts,labels,group)
    with pytest.raises(ValueError):GroupedParams(group_by='rack_id')
    with pytest.raises(ValueError):GroupedParams(sd_h=-1)
    with pytest.raises(ValueError):GroupedGaussianEffects(grouped_structure(('h0',),(0,)),GroupedParams(group_by='rack_id',variant_id='demo-rack-host-v1'))


def test_new_detector_modules_do_not_import_evaluator_truth():
    root=Path(__file__).resolve().parents[1]/'canary_ssm'
    for name in ('public_hierarchy','public_filter'):
        tree=ast.parse((root/(name+'.py')).read_text())
        for node in ast.walk(tree):
            modules=[node.module or ''] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names] if isinstance(node,ast.Import) else []
            assert not any(any(s in m for s in ('truth','simulate','metrics','evaluator','scenario')) for m in modules)


def test_public_adapter_selects_frozen_rack_metadata_and_rejects_group_mismatch():
    root=Path(__file__).resolve().parents[1]/'examples/control_adjustment'
    a=json.loads((root/'adjusted_rank1.json').read_text());m=FrozenAdjustment.load(root/'model_rank1.json')
    with pytest.raises(ValueError):run_hierarchy(a,m)  # class grouping cannot reuse rack control gates
    out=run_hierarchy(a,m,GroupedParams(group_by='rack_id',variant_id='demo-rack-host-v1'))
    assert out['output']['host_ids']==a['canary_ids']
    assert out['output']['host_group_ids']==['a','b']
    assert out['output']['B'].shape==(2,0)


def test_diagonal_hierarchical_prior_and_dynamics_are_an_unpooled_negative_control():
    from canary_ssm.hierarchy_fixture import pooling_examples
    _,hier,indep,unpooled=pooling_examples()
    np.testing.assert_allclose(unpooled['host_effect_mean'],indep['host_effect_mean'],atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(unpooled['host_effect_covariance'],indep['host_effect_covariance'],atol=1e-12,equal_nan=True)
    assert hier['host_effect_mean'][1,1]>.1


def test_distinct_dynamics_create_pooling_from_diagonal_initial_host_prior():
    D=data(2);r=np.zeros((4,2));r[2]=[1,0]
    D=replace(D,residuals=r,V=np.tile(.5*np.eye(2),(4,1,1)))
    st=grouped_structure(D.host_ids,(0,0))
    p=GroupedParams(prior_group_sd=float(np.sqrt(.51)),prior_deviation_sd=float(np.sqrt(1.02)),
        sd_g=float(.005/np.sqrt(2)),sd_h=.005,rho_g=.9,rho_h=.3)
    out=GroupedGaussianEffects(st,p).run(D)
    np.testing.assert_allclose(out['induced_effect_prior_covariance'],1.02*np.eye(2),atol=1e-14)
    assert abs(out['host_effect_mean'][1,1])<1e-14
    assert out['host_effect_mean'][2,1]>.05
