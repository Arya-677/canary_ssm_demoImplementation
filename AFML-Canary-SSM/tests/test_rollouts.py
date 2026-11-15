"""Fixed-cohort acceptance tests; numeric routing checks are request-accounting identities."""
import copy
import json
from dataclasses import replace
from pathlib import Path
import pytest
from canary_ssm.engine import SimulationEngine,load_engine_config
from canary_ssm.rollouts import select_cohort
from canary_ssm.telemetry import digest
from canary_ssm.dashboard import WorldController,ApiError
ROOT=Path(__file__).resolve().parents[1]

def engine():return SimulationEngine(load_engine_config(ROOT/'configs/world_console.yaml'),run_id='rollout-test')
def create(e,**kw):return e.operations_command('rollout_create',{'release_id':'release-002','baseline_seconds':2,'monitoring_seconds':10,**kw})
def act(e,r,action):return e.operations_command('rollout_'+action,{'rollout_id':r['rollout_id']})
def current(e,r):return e.rollouts.latest(r['service_id'])
def exposed():
    e=engine();r=create(e);act(e,r,'baseline');e.step(2);act(e,r,'expose');e.step();return e,r

def test_cohort_covers_crossed_axes_and_retains_three_controls():
    e=engine();r=create(e);C,K=set(r['canaries']),set(r['controls'])
    assert len(C)==4 and len(K)==16 and not C&K
    for g,m in r['groups'].items():assert set(m['canaries'])<=C and len(m['canaries'])>=1 and len(m['controls'])>=3
    assert any(g.startswith('class:') for g in r['groups'])
    r['canaries'].clear();assert len(e.rollouts.records()[0]['canaries'])==4
    with pytest.raises(ValueError):select_cohort(e.world,r['service_id'],unavailable=K)
    with pytest.raises(ValueError):create(e)

def test_invalid_commands_are_transactional_and_no_premature_exposure():
    e=engine();r=create(e);a=e.artifact()
    for action,args in [('rollout_promote',{'rollout_id':r['rollout_id']}),('rollout_pause',{'rollout_id':r['rollout_id']}),('rollout_expose',{'rollout_id':r['rollout_id']}),('rollout_baseline',{'rollout_id':r['rollout_id'],'canary_fraction':.5})]:
        with pytest.raises(ValueError):e.operations_command(action,args)
        assert e.artifact()==a
    act(e,r,'baseline')
    with pytest.raises(ValueError):act(e,r,'expose')
    e.step()
    with pytest.raises(ValueError):act(e,r,'expose')
    e.step();assert not e.rollouts.exposed_replicas()
    assert not current(e,r)['evaluation_active']
    act(e,r,'expose');e.step();assert current(e,r)['state']=='CANARY'
    assert current(e,r)['first_decision_time']==120 and not current(e,r)['alerts_enabled']

def test_fixed_fraction_pause_and_unavailable_slots_do_not_redistribute():
    e,r=exposed();before=e.resource_model.fixed_routes.copy();act(e,r,'pause');e.step(2)
    assert current(e,r)['state']=='PAUSED' and current(e,r)['evaluation_active']
    assert e.resource_model.fixed_routes==before
    C=set(r['canaries']);model=e.resource_model;model.unavailable_hosts=set(C)
    # Call router directly: platform fault plumbing intentionally not involved.
    result=model.route(e.world,e.tick+1,e.rngs['workload']);row=result['services'][0]
    assert row['canary_requested']>0
    assert row['dropped_unavailable_routes']==row['canary_requested']
    assert row['canary_requested']+row['control_requested']==row['arrivals']-row['dropped_arrival_limit']
    assert row['accepted']+row['dropped_queue']+row['dropped_memory']+row['dropped_unavailable_routes']==row['arrivals']
    assert all(model.routed_by_replica[x.replica_id]>0 for x in e.world.replicas if x.host_id in C)

def test_routing_expected_fraction_and_versions_side_by_side():
    e=engine();r=create(e,canary_fraction=.35,monitoring_seconds=1000);act(e,r,'baseline');e.step(2);act(e,r,'expose');e.step(100)
    rows=e.resource_model.service_trace;C=sum(x['canary_requested'] for x in rows);total=sum(x['arrivals']-x['dropped_arrival_limit'] for x in rows)
    assert abs(C/total-.35)<.02
    for x in e.world.replicas:assert x.release_id==(r['release_id'] if x.host_id in r['canaries'] else r['baseline_versions'][x.replica_id])

def test_pause_resume_and_horizon_are_same_epoch_and_fixed_traffic():
    e,r=exposed();act(e,r,'pause');e.step();act(e,r,'resume');e.step()
    assert current(e,r)['monitoring_epoch']==r['monitoring_epoch']
    e.step(10);assert current(e,r)['state']=='PAUSED' and not current(e,r)['evaluation_active']
    assert r['service_id'] in e.resource_model.fixed_routes
    with pytest.raises(ValueError):act(e,r,'resume')
    act(e,r,'promote');e.step();assert current(e,r)['state']=='PROMOTED'
    assert not e.resource_model.fixed_routes
    assert all(x.release_id==r['release_id'] for x in e.world.replicas)
    act(e,r,'rollback');e.step()
    assert {x.replica_id:x.release_id for x in e.world.replicas}==r['baseline_versions']

def test_rollback_restarts_every_service_replica_and_accounts_queue_drops():
    e,r=exposed();model=e.resource_model
    for rid in model.retained:model.retained[rid]=7
    queued=sum(model.queued.values())+sum(model.pending_count.values())
    act(e,r,'rollback');e.step()
    assert not model.fixed_routes and all(v==0 for v in model.retained.values())
    assert sum(x['dropped_restart'] for x in model.last_services)==queued
    assert all(model.error_probabilities[x.replica_id]==0 for x in e.world.replicas)
    assert not e.rollouts.exposed_replicas()

def test_failed_is_manual_truth_independent_and_rollback_is_valid():
    e,r=exposed();act(e,r,'fail');e.step();assert current(e,r)['state']=='FAILED'
    assert not current(e,r)['evaluation_active']
    act(e,r,'rollback');e.step();assert current(e,r)['state']=='ROLLED_BACK'
    source=(ROOT/'canary_ssm/rollouts.py').read_text()
    assert 'developer_truth' not in source and 'faults' not in source and 'evaluator' not in source

def test_log_hash_chain_replay_reset_and_new_epoch():
    e,r=exposed();act(e,r,'pause');e.step();old=e.rollouts.transition_log();e.reset()
    log=e.rollouts.transition_log();assert log[:len(old)]==old and log[-1]['reason'].startswith('world_reset')
    for i,row in enumerate(log):
        assert row['sequence']==i and row['previous_hash']==(log[i-1]['entry_hash'] if i else None)
        assert row['entry_hash']==digest({k:v for k,v in row.items() if k!='entry_hash'})
    r2=create(e);assert r2['monitoring_epoch']>r['monitoring_epoch']
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()
    tampered=copy.deepcopy(e.artifact());tampered['rollout_state']['transitions'][0]['reason']='edited'
    with pytest.raises(ValueError):SimulationEngine.replay(tampered)

def test_promoted_baseline_requires_new_candidate_and_new_epoch():
    e,r=exposed();act(e,r,'promote');e.step()
    with pytest.raises(ValueError):create(e)
    r2=create(e,release_id='release-001');assert r2['monitoring_epoch']==2
    assert set(r2['baseline_versions'].values())=={'release-002'}

def test_pre_exposure_current_run_detector_stream_rejected():
    c=WorldController(load_engine_config(ROOT/'configs/world_console.yaml'));r=create(c.engine)
    metadata={'run_id':c.run_id,'host_roster':[{'host_id':h,'rack_id':next(x.rack_id for x in c.engine.world.hosts if x.host_id==h)} for h in r['canaries']]}
    payload={'command_id':'early','run_id':c.run_id,'epoch':0,'command':'monitor_begin','args':{'metadata':metadata}}
    with pytest.raises(ApiError,match='not active'):c.command(payload)
    assert c.packet()['detector_status']=='DETECTOR NOT CONNECTED';c.close()

def test_stream_accepts_full_exposed_window_and_rejects_closed_epoch():
    config=load_engine_config(ROOT/'configs/world_console.yaml')
    c=WorldController(config);e=c.engine;r=create(e,baseline_seconds=2,monitoring_seconds=300)
    act(e,r,'baseline');e.step(2);act(e,r,'expose');e.step(118);r=current(e,r)
    roster=[{'host_id':h,'rack_id':next(x.rack_id for x in e.world.hosts if x.host_id==h)} for h in r['canaries']]
    metadata={'format':'public-detector-output-v1','artifact_id':'test-stream','version':'v1','replay_id':'test-replay','run_id':c.run_id,'source_kind':'external-detector-stream','host_roster':roster,'methods':[{'method_id':'independent','version':'v1','kind':'independent','settings':{}}],'exposure_time':120,'simulated':True}
    from canary_ssm.monitor_feed import FORMAT
    metadata['format']=FORMAT
    def cmd(name,args):return c.command({'command_id':str(c.revision)+name,'run_id':c.run_id,'epoch':c.epoch,'command':name,'args':args})
    cmd('monitor_begin',{'metadata':metadata})
    frame={'event_time':120,'decision_time':120,'input_sha256':'a'*64,'observed':[True]*4,'eligible':True,'latency_ms':[100]*4,'residual':[0]*4,'quality_flags':[],
        'methods':{'independent':{'mean':[0]*4,'covariance':[[.1 if i==j else 0 for j in range(4)] for i in range(4)],'group':[None]*4,'deviation':[None]*4}}}
    cmd('monitor_append',{'frame':frame});assert c.detector_feed.cursor==0
    bad=copy.deepcopy(frame);bad.update(event_time=60,decision_time=121)
    e.step()
    with pytest.raises(ApiError,match='outside'):cmd('monitor_append',{'frame':bad})
    act(e,r,'promote');e.step();bad.update(event_time=121,decision_time=121)
    with pytest.raises(ApiError,match='not active'):cmd('monitor_append',{'frame':bad})
    c.close()

def test_reset_releases_reservations_and_legacy_commands_work_again():
    e,r=exposed();e.reset()
    plan=e.operations_command('preview',{'release_id':'release-002'})
    e.operations_command('deploy',{'plan_id':plan['plan_id']});e.step()
    assert e.demo.deployment['status']=='canary'
    assert e.rollouts.transition_log()[-1]['reason']=='world_reset_restores_initial_world'
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()
