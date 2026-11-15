from dataclasses import replace
import ast
import json
from pathlib import Path

import numpy as np
import pytest

from canary_ssm import seeds
from canary_ssm.engine import SimulationEngine
from canary_ssm.scenario_registry import (PairSpec,ROLES,GENERATORS,WORLD_FAMILIES,WORLD_GENERATOR_ID,
    ADDITIVE_GENERATOR_ID,register_bundles,registry_manifest,validate_registry,select_members)
from canary_ssm.scenario_bundles import (run_world_member,export_world_pair,export_statistical_pair,
    statistical_recipe,world_recipe)
from canary_ssm.simulate import simulate,SimConfig
from canary_ssm.world_evaluator import OperatorLabel,classify,run_handlabels

ROOT=Path(__file__).resolve().parents[1]


def pair(family='host_fault',role='smoke',generator=WORLD_GENERATOR_ID):
    return PairSpec.register(generator,role,family)


def test_disjoint_seed_and_scenario_bundles_and_legacy_bases_preserved():
    registry=register_bundles(2)
    assert validate_registry(registry)
    assert len({p.pair_id for p in registry})==len(registry)
    assert len({p.seed for p in registry})==len(registry)
    for a in ROLES:
        for b in ROLES:
            if a==b:continue
            assert {p.seed for p in registry if p.role==a}.isdisjoint(p.seed for p in registry if p.role==b)
            assert {p.run_id(m) for p in registry if p.role==a for m in p.members}.isdisjoint(p.run_id(m) for p in registry if p.role==b for m in p.members)
    assert seeds.seed_for('smoke',0)==10000 and seeds.seed_for('dev',0)==1000000
    assert seeds.seed_for('calibration',0)==2000000 and seeds.seed_for('test',0)==4000000
    seeds.assert_disjoint()
    manifest=registry_manifest()
    assert manifest==registry_manifest() and manifest['roles']['final-test']['allowed_uses']==['evaluate']
    assert len({p.generator_id for p in registry})==2
    assert all(p.seed>=34000000 for p in registry if p.generator_id==ADDITIVE_GENERATOR_ID)


def test_pairs_cannot_be_split_moved_or_reused():
    p=pair()
    for changed in (replace(p,role='development'),replace(p,members=('null',)),replace(p,seed=p.seed+1),replace(p,generator_id=ADDITIVE_GENERATOR_ID)):
        with pytest.raises(ValueError):changed.validate()
    with pytest.raises(ValueError):validate_registry([p,p])
    with pytest.raises(ValueError):pair(role='invalid')
    with pytest.raises(ValueError):PairSpec.register(WORLD_GENERATOR_ID,'smoke','host_fault',True)


def test_stage_consumers_enforce_roles_and_null_only_thresholds():
    ps=register_bundles()
    for role,use in [('smoke','debug'),('development','fit'),('development','tune'),
                     ('threshold-calibration','threshold'),('null-validation','audit'),('final-test','evaluate')]:
        rows=select_members(ps,role,use)
        assert rows and all(r['role']==role for r in rows)
        if role in ('threshold-calibration','null-validation'):assert all(r['member']=='null' for r in rows)
    for role,use in [('null-validation','fit'),('final-test','tune'),('development','threshold'),('threshold-calibration','evaluate')]:
        with pytest.raises(ValueError):select_members(ps,role,use)
    with pytest.raises(ValueError):select_members(ps,'threshold-calibration','threshold',member='harm')


@pytest.mark.parametrize('family',WORLD_FAMILIES)
def test_world_pairs_share_exogenous_inputs_but_need_no_additive_equality(family):
    p=pair(family);a=run_world_member(p,'null');b=run_world_member(p,'harm')
    assert list(a.resource_model.exogenous_trace)==list(b.resource_model.exogenous_trace)
    for stream in ('workload','faults','host_noise','telemetry_loss'):
        assert a.artifact()['rng_states'][stream]==b.artifact()['rng_states'][stream]
    assert (a.resource_model.trace()==b.resource_model.trace()) == (family=='healthy')
    before=lambda e:[r for r in e.resource_model.host_trace if r['tick']<13]
    assert before(a)==before(b)
    assert SimulationEngine.replay(b.artifact()).artifact()==b.artifact()
    assert all(r.release_id=='healthy-v1' for r in b.world.replicas) if family not in ('persistent_degradation',) else any(r.release_id=='sample-slow-v2' for r in b.world.replicas)


def test_crash_routing_changes_do_not_shift_future_arrivals_and_surge_changes_rate_only():
    for family in ('host_fault','shared_demand_surge'):
        p=pair(family);a=run_world_member(p,'null');b=run_world_member(p,'harm')
        aa=list(a.resource_model.service_trace);bb=list(b.resource_model.service_trace)
        if family=='host_fault':
            assert [r['arrivals'] for r in aa]==[r['arrivals'] for r in bb]
            assert a.artifact()['rng_states']['routing']!=b.artifact()['rng_states']['routing']
        else:
            assert [r['arrivals'] for r in aa][12:18]!=[r['arrivals'] for r in bb][12:18]
            assert [r['arrivals'] for r in aa][18:]==[r['arrivals'] for r in bb][18:]
        # Common random uniforms, not equal outcomes under different rates/routing.
        assert list(a.resource_model.exogenous_trace)==list(b.resource_model.exogenous_trace)


def test_rack_fault_changes_only_descendant_network_capacity():
    e=run_world_member(pair('rack_fault'),'harm')
    rows=[r for r in e.resource_model.host_trace if 13<=r['tick']<19]
    assert all(r['network_capacity_mbps']==pytest.approx(10 if r['rack_id']=='rack-a' else 100) for r in rows)
    assert all(r['network_capacity_mbps']==100 for r in e.resource_model.last_hosts)


def test_pair_export_stores_private_labels_and_opaque_public_ids(tmp_path):
    p=pair('host_fault');result=export_world_pair(p,tmp_path)
    assert result['passed'] and not result['additive_equality_required'] and result['endogenous_divergence']
    for member in p.members:
        directory=tmp_path/member
        assert all((directory/n).exists() for n in ('config.json','commands.json','manifest.json','run.json','exogenous.json','public/records.jsonl','evaluator/truth.jsonl','evaluator/intervention_label.json'))
        manifest=json.loads((directory/'manifest.json').read_text())
        assert manifest['pair']['role']==p.role and manifest['pair']['pair_id']==p.pair_id
        rows=[json.loads(line) for line in (directory/'public/records.jsonl').read_text().splitlines()]
        assert all(r['run_id'].startswith('run-') and 'host_fault' not in r['run_id'] and member not in r['run_id'] for r in rows)
        assert all(not ({'fault_type','true_affected','injected_latent_effect','role','member','seed'} & r.keys()) for r in rows)
    assert json.loads((tmp_path/'null/manifest.json').read_text())['exogenous_sha256']==json.loads((tmp_path/'harm/manifest.json').read_text())['exogenous_sha256']


@pytest.mark.parametrize('family',GENERATORS[ADDITIVE_GENERATOR_ID])
def test_original_statistical_pair_is_additive_and_has_different_generator_id(family):
    p=pair(family,generator=ADDITIVE_GENERATOR_ID);cfg=statistical_recipe(family)
    n,nt=simulate(cfg,p.seed,False);h,ht=simulate(cfg,p.seed,True)
    assert np.allclose((h.y-n.y)[h.observed],(ht.a+ht.spill)[h.observed],rtol=0,atol=1e-12)
    for x,y in ((n.x,h.x),(nt.factor,ht.factor),(nt.noise,ht.noise),(n.observed,h.observed),(n.decision_obs,h.decision_obs)):
        assert np.array_equal(x,y)
    assert p.generator_id!=WORLD_GENERATOR_ID


def test_statistical_stress_pair_preserves_spill_and_missing_masks_exactly(tmp_path):
    p=pair('additive_recovery',generator=ADDITIVE_GENERATOR_ID)
    cfg=replace(statistical_recipe(p.family),contam_frac=.5,heavy_tail_df=5,missing_rate=.1,late_frac=.1,label_error=.5)
    n,nt=simulate(cfg,p.seed,False);h,ht=simulate(cfg,p.seed,True)
    m=h.observed
    assert np.array_equal(m,n.observed) and np.array_equal(h.decision_obs,n.decision_obs)
    assert np.allclose((h.y-n.y)[m],(ht.a+ht.spill)[m],atol=1e-12,rtol=0)
    assert export_statistical_pair(p,tmp_path)['passed']
    from canary_ssm.simulate import Truth
    assert Truth.load(tmp_path/'null/evaluator/truth.npz').pair_id==p.seed
    assert Truth.load(tmp_path/'harm/evaluator/truth.npz').pair_id==p.seed
    with pytest.raises(ValueError):export_statistical_pair(pair(),tmp_path/'bad')


def test_hand_labeled_outcomes_and_boundary_cases(tmp_path):
    assert run_handlabels(tmp_path)['passed']
    rows=json.loads((ROOT/'configs/world_evaluator_handlabels.json').read_text())['cases']
    for case in rows:
        out=classify(OperatorLabel(**case['label']),case['alarm_time'],case.get('eligible_decisions',1),case.get('minimum_followup',30))
        assert all(out[k]==v for k,v in case['expected'].items())
    assert classify(OperatorLabel(60,120,180),60)['status']=='success'
    assert classify(OperatorLabel(60,120,180),120)['status']=='after_recovery'
    # The same alarm can fail if the label moves: the evaluator is able to fail.
    assert classify(OperatorLabel(100,120,180),60)['status']=='premature'


@pytest.mark.parametrize('label,alarm,eligible',[(OperatorLabel(None,None,180),181,1),
    (OperatorLabel(60,None,180),False,1),(OperatorLabel(60,120,180),90,0)])
def test_invalid_evaluator_inputs(label,alarm,eligible):
    with pytest.raises(ValueError):classify(label,alarm,eligible)


def test_inference_and_public_receiver_do_not_import_bundle_or_evaluator_paths():
    for name in ('factor','preprocess','kalman','hierarchy','baselines','decision','telemetry','telemetry_transport'):
        tree=ast.parse((ROOT/f'canary_ssm/{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not any(s in (node.module or '') for s in ('scenario_bundles','world_evaluator'))


def test_export_verification_rejects_role_moves_and_modified_data(tmp_path):
    from canary_ssm.scenario_bundles import verify_member
    p=pair('healthy');export_world_pair(p,tmp_path)
    out=tmp_path/'null'
    assert verify_member(out)
    path=out/'manifest.json';original=path.read_text();m=json.loads(original)
    m['pair']['role']='final-test';path.write_text(json.dumps(m))
    with pytest.raises(ValueError):verify_member(out)
    path.write_text(original)
    data=out/'public/records.jsonl';data.write_text(data.read_text()+'\n')
    with pytest.raises(ValueError):verify_member(out)


def test_transport_randomness_is_shared_without_requiring_latency_masks_equal():
    from canary_ssm.telemetry_transport import TelemetryConfig
    p=pair('host_fault');cfg,_,recipe=world_recipe(p)
    cfg=replace(cfg,telemetry=TelemetryConfig(enabled=True,missing_probability=.2,
        duplicate_probability=.3,delay_min_ticks=0,delay_max_ticks=2))
    a=SimulationEngine(cfg,run_id='opaque-a');b=SimulationEngine(cfg,run_id='opaque-b')
    b.operations_command('fault',recipe['fault']|{'seed':p.seed})
    for e in (a,b):e.step(48)
    keys=lambda e:[(r['replica_id'],r['event_time'],r['arrival_time']) for r in e.telemetry.store.received]
    assert keys(a)==keys(b)
    assert a.artifact()['rng_states']['telemetry_loss']==b.artifact()['rng_states']['telemetry_loss']
    assert list(a.resource_model.exogenous_trace)==list(b.resource_model.exogenous_trace)
    public=json.dumps(b.telemetry.public_artifact())
    assert 'arrival_uniforms' not in public and 'shared_traffic_uniform' not in public
