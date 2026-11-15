"""Hand-ordered policy/reference/controller contract tests; not world benchmarks."""
import copy,json,math,ast
from dataclasses import replace
from pathlib import Path
import pytest
from canary_ssm.first_crossing import protocol,rule,LatchedFirstCrossing
from canary_ssm.policy_artifacts import freeze_development,calibrate,validate_nulls,validated_attachment,ordered_threshold,seal
from canary_ssm.policy_control import world_simulator,world_protocol
from canary_ssm.public_adjustment import FrozenAdjustment
from canary_ssm.hierarchy import EffectParams
from canary_ssm.engine import SimulationEngine,EngineConfig
from canary_ssm.resources import ResourceConfig,ServiceWorkload
from canary_ssm.topology import Topology,DataCenter,Rack,Host,HostCapacity,ServiceReplica
from canary_ssm.seeds import seed_for
ROOT=Path(__file__).resolve().parents[1]


def proto(H=2):return protocol(['h0','h5'],['h1','h2','h3','h4','h6','h7','h8','h9'],{'rack:a':['h1','h2','h3','h4'],'rack:b':['h6','h7','h8','h9']},horizon_windows=H)
def observation(i=0,score=-9,p=None):
    p=p or proto();return {'window_index':i,'event_time':3660+i*60,'decision_time':3660+i*60,'score':score,'available':True,'fresh_canaries':list(p['canaries']),'fresh_controls':copy.deepcopy(p['groups']),'exposed_hosts':list(p['canaries']),'quality_flags':[],'input_sha256':'a'*64}
def frozen(simulator=None,H=2,settings=None):
    model=FrozenAdjustment.load(ROOT/'examples/control_adjustment/model_rank1.json').to_dict()
    return freeze_development(model,vars(EffectParams(kind='indep')),simulator or {'generator_id':'unit-score-contract-v1'},proto(H),[{'run_id':'unit-dev','seed':seed_for('world_dev',1000,22),'role':'development','declared_healthy':True,'public_sha256':model['development_lineage'][0]['public_sha256']}],settings)
def trace(f,index,role,score=-9,none=False):
    purpose='world_calibration' if role=='threshold-calibration' else 'world_null_validation'
    rows=[observation(i,score,f['protocol']) for i in range(f['protocol']['horizon_windows'])]
    if none:
        for r in rows:r.update(score=None,fresh_canaries=[],available=False)
    return {'run_id':role+'-'+str(index),'seed':seed_for(purpose,index,22),'role':role,'declared_null':True,'hashes':f['hashes'],'freeze_hash':f['freeze_hash'],'exposure_time':3660,'records':rows}


def test_exact_rank_476_strict_ties_and_infinity():
    assert ordered_threshold(list(range(-500,0)),.05)=={'B':500,'k':476,'alpha':.05,'threshold':-25.,'ties_at_threshold':1}
    assert ordered_threshold([-1]*10,.05)['threshold']=='+inf'
    state=LatchedFirstCrossing(proto(),rule(2),-1,exposure_time=3660)
    assert state.observe(observation(score=-1))['state']=='HOLD'
    assert state.observe(observation(1,-.99))['first_crossing']['window_index']==1


def test_latch_missing_controls_exposure_quality_and_immutable_decisions():
    state=LatchedFirstCrossing(proto(3),rule(3),-1,exposure_time=3660)
    r=observation(score=-.1,p=proto(3));r['fresh_controls']['rack:a']=['h1','h2','h3'];r['exposed_hosts'].append('h1')
    assert state.observe(r)['state']=='HOLD'
    crossing=observation(1,-.1,proto(3));assert state.observe(crossing)['state']=='ALARM_LATCHED'
    missing=observation(2,None,proto(3));missing['fresh_canaries']=[]
    assert state.observe(missing)['state']=='ALARM_LATCHED' and state.first_crossing['window_index']==1
    assert state.observe(missing)['duplicate']
    changed=copy.deepcopy(crossing);changed['score']=-10
    with pytest.raises(ValueError,match='immutable'):state.observe(changed)


def test_no_data_never_promotes_and_healthy_budget_is_explicit():
    f=frozen();p=calibrate(f,[trace(f,i,'threshold-calibration',none=True) for i in range(20)])
    assert p['no_eligible_nulls']==20 and p['calibration']['threshold']=='-inf' and p['status']=='INSUFFICIENT_ELIGIBLE_CALIBRATION'
    state=LatchedFirstCrossing(proto(),rule(2),-1,exposure_time=3660)
    for i in range(2):state.observe({**observation(i,None),'available':False})
    assert not state.snapshot()['healthy_ready']
    healthy=LatchedFirstCrossing(proto(),rule(2),-1,exposure_time=3660)
    assert not healthy.observe(observation())['healthy_ready']
    assert healthy.observe(observation(1))['healthy_ready']


@pytest.mark.parametrize('mutation', ['role','seed','hashes','short','future','quality'])
def test_invalid_or_ineligible_calibration_inputs(mutation):
    f=frozen();traces=[trace(f,i,'threshold-calibration') for i in range(20)]
    if mutation=='role':traces[0]['role']='development'
    elif mutation=='seed':traces[0]['seed']=traces[1]['seed']
    elif mutation=='hashes':traces[0]['hashes']={**f['hashes'],'model_hash':'0'*64}
    elif mutation=='short':traces[0]['records'].pop()
    elif mutation=='future':traces[0]['records'][0]['decision_time']=999999
    else:traces[0]['records'][0]['quality_flags']=['development_noise_fit_failed']
    if mutation in ('future','quality'):
        # Deadlines are checked for increasing causality; quality masks data.
        if mutation=='future':
            with pytest.raises(ValueError):calibrate(f,traces)
        else:assert calibrate(f,traces)['calibration_lineage'][0]['eligible_windows']==1
    else:
        with pytest.raises(ValueError):calibrate(f,traces)


def test_five_hashes_frozen_roles_validation_intervals_and_no_retune():
    f=frozen();p=calibrate(f,[trace(f,i,'threshold-calibration',-10+i/500*9) for i in range(500)])
    original=copy.deepcopy(p);v=validate_nulls(p,[trace(f,i,'null-validation',-.1 if i<25 else -9) for i in range(500)])
    assert p==original and p['calibration']['k']==476
    assert v['rates']['release_alarm']['events']==25 and v['rates']['release_alarm']['exact_binomial_95_interval'][0]<.05<v['rates']['release_alarm']['exact_binomial_95_interval'][1]
    assert v['gate']['status']=='INSUFFICIENT_DATA'
    with pytest.raises(ValueError):validated_attachment(p,v)
    reused=trace(f,0,'null-validation');reused['seed']=p['calibration_lineage'][0]['seed']
    with pytest.raises(ValueError):validate_nulls(p,[reused])
    f['effect_settings']['sd_g']=999
    with pytest.raises(ValueError):calibrate(f,[])


def test_combined_policy_false_alerts_count_union_separately():
    f=frozen(settings=rule(2,resource_guardrails='observed_pause'));p=calibrate(f,[trace(f,i,'threshold-calibration',-10+i/500*9) for i in range(500)])
    rows=[trace(f,i,'null-validation',-.1 if i<10 else -9) for i in range(100)]
    for i in range(5,25):rows[i]['advisories']=[{'kind':'platform' if i<15 else 'resource','source':'observed_metrics','window_index':0,'evidence_hash':'b'*64}]
    v=validate_nulls(p,rows)
    assert v['rates']['release_alarm']['events']==10 and v['rates']['platform_pause']['events']==10 and v['rates']['resource_pause']['events']==10
    assert v['rates']['combined_action']['events']==25


def world():
    hosts=tuple(Host('h'+str(i),'a' if i<5 else 'b','dc',0,HostCapacity(1,1000,1000,1000)) for i in range(10))
    topology=Topology((DataCenter('dc'),),(Rack('a','dc'),Rack('b','dc')),hosts,tuple(ServiceReplica('demo-service','replica-'+h.host_id,h.host_id,'baseline') for h in hosts))
    return SimulationEngine(EngineConfig(topology,seed=seed_for('world_smoke',1000,22),tick_seconds=60,resources=ResourceConfig((ServiceWorkload('demo-service',10),)),demo=True),run_id='unit-controller-contract')

@pytest.fixture(scope='module')
def artifact_pair():
    # Hand-authored null score fixtures exercise validation/controller plumbing;
    # they are not saved as world calibration results or a deployable benchmark.
    e=world();r=e.operations_command('rollout_create',{'release_id':'release-001','baseline_seconds':3600,'monitoring_seconds':120})
    f=frozen(world_simulator(e));assert world_protocol(e,r,'rack_id')==f['protocol']
    p=calibrate(f,[trace(f,i,'threshold-calibration',-10+i/2000*9) for i in range(2000)])
    v=validate_nulls(p,[trace(f,i,'null-validation',-.1 if i<100 else -9) for i in range(2000)])
    assert v['gate']['status']=='PASS';return p,v

def setup_bound(pair,auto=False):
    e=world();r=e.operations_command('rollout_create',{'release_id':'release-001','baseline_seconds':3600,'monitoring_seconds':120});rid=r['rollout_id'];p,v=pair
    e.operations_command('policy_attach',{'rollout_id':rid,'policy':p,'validation':v,'auto_rollback':auto})
    e.operations_command('rollout_baseline',{'rollout_id':rid});e.step(60);e.operations_command('rollout_expose',{'rollout_id':rid});e.step()
    return e,r

def send_observation(e,r,p,record):return e.operations_command('policy_observe',{'rollout_id':r['rollout_id'],'run_id':e.run_id,'monitoring_epoch':r['monitoring_epoch'],'hashes':{**p['frozen']['hashes'],'policy_hash':p['policy_hash']},'record':record})

def test_controller_auto_pause_manual_rollback_and_replay(artifact_pair):
    e,r=setup_bound(artifact_pair);p,v=artifact_pair
    with pytest.raises(ValueError):e.operations_command('rollout_promote',{'rollout_id':r['rollout_id']})
    send_observation(e,r,p,observation(score=-.1));e.step();assert e.rollouts.latest(r['service_id'])['state']=='PAUSED'
    assert e.rollouts.transition_log()[-1]['reason']=='release_regression_alarm'
    with pytest.raises(ValueError):e.operations_command('rollout_resume',{'rollout_id':r['rollout_id']})
    e.operations_command('rollout_rollback',{'rollout_id':r['rollout_id']});e.step();assert e.rollouts.latest(r['service_id'])['state']=='ROLLED_BACK'
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()


def test_opt_in_auto_rollback_is_two_distinct_transitions(artifact_pair):
    e,r=setup_bound(artifact_pair,True);send_observation(e,r,artifact_pair[0],observation(score=-.1));e.step()
    assert e.rollouts.latest(r['service_id'])['state']=='PAUSED';e.step()
    assert e.rollouts.latest(r['service_id'])['state']=='ROLLED_BACK'
    assert e.rollouts.transition_log()[-1]['reason']=='opt_in_release_alarm_auto_rollback'


def test_completed_budget_promotes_but_future_or_wrong_hash_holds(artifact_pair):
    e,r=setup_bound(artifact_pair);p,_=artifact_pair
    before=e.artifact()
    with pytest.raises(ValueError):send_observation(e,r,p,observation(1))
    assert e.artifact()==before
    send_observation(e,r,p,observation());e.step();send_observation(e,r,p,observation(1))
    e.operations_command('rollout_promote',{'rollout_id':r['rollout_id']});e.step();assert e.rollouts.latest(r['service_id'])['state']=='PROMOTED'


def test_platform_incident_has_separate_reason_and_no_release_auto_rollback(artifact_pair):
    e,r=setup_bound(artifact_pair,True)
    e.operations_command('policy_advisory',{'rollout_id':r['rollout_id'],'kind':'platform','source':'observed_metrics','evidence_hash':'b'*64,'decision_time':3660,'represented_groups':['rack:a','rack:b']});e.step(2)
    assert e.rollouts.latest(r['service_id'])['state']=='PAUSED'
    assert 'shared_platform_incident' in [x['reason'] for x in e.rollouts.transition_log()]
    assert 'release_regression_alarm' not in e.policy_controller.snapshot()['bindings'][0]['blocked_reasons']


def test_policy_code_never_imports_truth_evaluator_or_metrics():
    for name in ('first_crossing','policy_artifacts','policy_control','policy_public'):
        for node in ast.walk(ast.parse((ROOT/'canary_ssm'/f'{name}.py').read_text())):
            modules=[node.module or ''] if isinstance(node,ast.ImportFrom) else [n.name for n in node.names] if isinstance(node,ast.Import) else []
            assert not any(any(x in m for x in ('simulate','metrics','evaluator','faults')) for m in modules)


def test_resume_queued_before_alarm_is_cancelled_at_application(artifact_pair):
    e,r=setup_bound(artifact_pair);p,_=artifact_pair;rid=r['rollout_id']
    e.operations_command('rollout_pause',{'rollout_id':rid});e.step()
    e.operations_command('rollout_resume',{'rollout_id':rid})
    send_observation(e,r,p,observation(1,-.1));length=len(e.rollouts.transition_log());e.step()
    assert e.rollouts.latest(r['service_id'])['state']=='PAUSED'
    assert not any(x['to_state']=='CANARY' for x in e.rollouts.transition_log()[length:])
    assert any(x['reason']=='queued_action_cancelled_by_latch' for x in e.policy_controller.log)


def test_invalid_hash_and_reset_do_not_revise_old_policy_state(artifact_pair):
    e,r=setup_bound(artifact_pair);p,_=artifact_pair;before=e.artifact()
    bad=copy.deepcopy(p);bad['policy_hash']='0'*64
    with pytest.raises(ValueError):send_observation(e,r,bad,observation())
    assert e.artifact()==before
    send_observation(e,r,p,observation(score=-.1));e.reset()
    assert not e.policy_controller.snapshot()['bindings'][0]['active']
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()


def test_grouped_settings_are_separate_frozen_model_hashes():
    from dataclasses import asdict
    from canary_ssm.public_hierarchy import GroupedParams
    base=frozen();params={'kind':'grouped',**asdict(GroupedParams(group_by='rack_id',variant_id='demo-rack-host-v1'))}
    grouped=freeze_development(base['preprocessing_model'],params,base['simulator'],base['protocol'],base['development'],base['rule'])
    assert grouped['hashes']['model_hash']!=base['hashes']['model_hash']
    assert grouped['hashes']['preprocessing_hash']==base['hashes']['preprocessing_hash']


def test_default_resource_guardrail_is_separate_and_disabled(artifact_pair):
    e,r=setup_bound(artifact_pair,True);before=e.artifact()
    with pytest.raises(ValueError,match='separately disabled'):
        e.operations_command('policy_advisory',{'rollout_id':r['rollout_id'],'kind':'resource','source':'observed_metrics','evidence_hash':'b'*64,'decision_time':3660,'represented_groups':[]})
    assert e.artifact()==before


def test_new_order_statistic_agrees_with_existing_research_calibrator():
    import numpy as np
    from canary_ssm.decision import calibrate_threshold
    rng=np.random.default_rng(seed_for('world_smoke',4321,22))
    for B in (19,500,2000):
        values=rng.normal(-3,.5,B);old=calibrate_threshold(values,.05);new=ordered_threshold(values.tolist(),.05)
        assert new['k']==old['k'] and new['threshold']==old['threshold']


def test_simulator_binding_varies_by_baseline_but_not_independent_seed():
    a=world();b=world();b.config=replace(b.config,seed=b.config.seed+1)
    assert world_simulator(a)==world_simulator(b)
    r=a.operations_command('rollout_create',{'release_id':'release-002','baseline_seconds':3600,'monitoring_seconds':120})
    a.operations_command('rollout_baseline',{'rollout_id':r['rollout_id']});a.step(60);a.operations_command('rollout_expose',{'rollout_id':r['rollout_id']});a.step();a.operations_command('rollout_promote',{'rollout_id':r['rollout_id']});a.step()
    assert world_simulator(a)!=world_simulator(b)


def test_browser_json_integral_float_roundtrip_preserves_policy_hash(artifact_pair):
    from canary_ssm.policy_hash import canonical
    p,v=artifact_pair
    # Semantic normalization reproduces browser JSON's integer conversion.
    after=canonical(json.loads(json.dumps(p)));receipt=canonical(json.loads(json.dumps(v)))
    assert after['policy_hash']==p['policy_hash']
    assert validated_attachment(after,receipt)['policy_hash']==p['policy_hash']


def test_changed_world_configuration_cannot_use_prior_calibration(artifact_pair):
    e=world();resources=replace(e.config.resources,services=(replace(e.config.resources.services[0],arrival_rate_rps=20),))
    other=SimulationEngine(replace(e.config,resources=resources),run_id='changed-world-contract');r=other.operations_command('rollout_create',{'release_id':'release-001','baseline_seconds':3600,'monitoring_seconds':120});before=other.artifact()
    with pytest.raises(ValueError,match='incompatible'):
        other.operations_command('policy_attach',{'rollout_id':r['rollout_id'],'policy':artifact_pair[0],'validation':artifact_pair[1]})
    assert other.artifact()==before


def test_raw_saved_run_text_preserves_policy_and_rng_values(artifact_pair):
    from canary_ssm.dashboard import WorldController
    e,r=setup_bound(artifact_pair);send_observation(e,r,artifact_pair[0],observation(score=-.1));e.step()
    c=WorldController(e.config,run_id=e.run_id);c.engine=e;saved=json.dumps(c.export_run());other=WorldController(e.config)
    other.command({'command_id':'raw-replay','run_id':other.run_id,'epoch':other.epoch,'command':'load_run','args':{'run':saved}})
    assert other.read_only and other.engine.snapshot()==e.snapshot()
    assert other.engine.rngs['workload'].bit_generator.state==e.rngs['workload'].bit_generator.state
    c.close();other.close()


def test_extended_baseline_cannot_silently_reuse_fixed_protocol(artifact_pair):
    e=world();r=e.operations_command('rollout_create',{'release_id':'release-001','baseline_seconds':3600,'monitoring_seconds':120});rid=r['rollout_id']
    e.operations_command('policy_attach',{'rollout_id':rid,'policy':artifact_pair[0],'validation':artifact_pair[1]});e.operations_command('rollout_baseline',{'rollout_id':rid});e.step(61)
    with pytest.raises(ValueError,match='exact frozen baseline'):
        e.operations_command('rollout_expose',{'rollout_id':rid})
    assert e.rollouts.latest(r['service_id'])['exposure_tick'] is None


def test_observed_incident_after_exposure_does_not_wait_for_latency_window(artifact_pair):
    e,r=setup_bound(artifact_pair)
    e.operations_command('policy_advisory',{'rollout_id':r['rollout_id'],'kind':'platform','source':'observed_metrics','evidence_hash':'b'*64,'decision_time':3601,'represented_groups':['rack:a','rack:b']});e.step()
    assert e.rollouts.latest(r['service_id'])['state']=='PAUSED'
    assert e.policy_controller.snapshot()['bindings'][0]['decision']['state']=='HOLD'


def test_opt_in_resource_guardrail_uses_observations_and_never_release_rollback():
    e=world();f=frozen(world_simulator(e),settings=rule(2,resource_guardrails='observed_pause'))
    p=calibrate(f,[trace(f,i,'threshold-calibration',-10+i/2000*9) for i in range(2000)])
    v=validate_nulls(p,[trace(f,i,'null-validation',-.1 if i<100 else -9) for i in range(2000)])
    e,r=setup_bound((p,v),True)
    # The injection affects physical memory; the guard consumes only the emitted
    # resource observations. No injection ID/type is passed to the policy.
    e.operations_command('fault',{'kind':'memory_pressure','scope':'host','target':'h0','severity':.9,'duration':3});e.step(3)
    assert e.rollouts.latest(r['service_id'])['state']=='PAUSED'
    reasons=e.policy_controller.snapshot()['bindings'][0]['blocked_reasons']
    assert reasons==['resource_health_guardrail']
    assert 'resource_health_guardrail' in [x['reason'] for x in e.rollouts.transition_log()]
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()
