import ast
import copy
from dataclasses import replace
from collections import deque
import json
import math
from pathlib import Path
import threading
from urllib.request import urlopen
from urllib.error import HTTPError

import pytest

from canary_ssm.telemetry import PublicRecord, CausalWindowStore
from canary_ssm.telemetry_transport import TelemetryConfig
from canary_ssm.engine import SimulationEngine,load_engine_config
from canary_ssm.dashboard import WorldController,make_server
from canary_ssm.resources import TrafficLevel

ROOT=Path(__file__).resolve().parents[1]
ROSTER=[dict(host_id='host',rack_id='rack',class_id=0,service_id='service',replica_id='replica')]


def record(at=30,latency=10,n=2,**changes):
    row=dict(record_id=f'r-{at}',run_id='run',host_id='host',rack_id='rack',class_id=0,
        service_id='service',replica_id='replica',release_id='v1',exposed=False,event_time=at,
        arrival_time=at,interval_seconds=30,request_count=n,latency_ms=latency,workload=1,
        latency_sum_ms=n*latency,latency_sum_sq_ms2=n*latency**2,
        log_latency_sum=n*math.log(latency),log_latency_sum_sq=n*math.log(latency)**2,latency_observed=True)
    return PublicRecord(**(row|changes))


def store(**changes):return CausalWindowStore('run',ROSTER,interval_seconds=30,**changes)


def engine(telemetry=None):
    cfg=load_engine_config(ROOT/'configs/world_console.yaml')
    return SimulationEngine(replace(cfg,telemetry=telemetry or TelemetryConfig(enabled=True)),run_id='test-run')


def test_hand_computed_request_weighted_sufficient_statistics_and_boundary():
    s=store();s.ingest(record(),30);s.ingest(record(60,20,3,workload=3),60)
    row=s.time_slice(60)['windows'][0]
    assert row['request_count']==5 and row['latency_sum_ms']==80 and row['latency_sum_sq_ms2']==1400
    assert row['latency_ms']==16
    assert row['log_latency_mean']==pytest.approx((2*math.log(10)+3*math.log(20))/5)
    assert row['workload']==2 and row['workload_integral']==120 and row['workload_seconds']==60
    assert row['coverage']==1 and row['observed'] and row['window_index']==0
    assert record(60).window==0 and record(90).window==1


def test_duplicates_new_ids_and_conflicts_first_received_wins():
    s=store();first=record();s.ingest(first,30)
    assert s.ingest(replace(first,arrival_time=31),31)=='duplicates'
    assert s.ingest(replace(first,record_id='retry',arrival_time=32),32)=='duplicates'
    assert s.ingest(record(latency=999,arrival_time=33),33)=='conflicts'
    s.ingest(record(60),60)
    row=s.time_slice(60)['windows'][0]
    assert row['latency_ms']==10 and row['request_count']==4 and row['received_ticks']==2
    assert s.counters['duplicates']==2 and s.counters['conflicts']==1


def test_late_data_and_future_values_cannot_revise_inputs_or_scores():
    s=store();s.ingest(record(),30);s.ingest(record(60),60)
    score=lambda data:sum(r['latency_ms'] or 0 for r in data['windows'] if r['observed'])
    frozen=s.time_slice(60);old=s.score_once(60,score)
    assert s.ingest(record(30,10000,record_id='conflicting-late',arrival_time=70),70)=='conflicts'
    s.ingest(record(90,1000000),90);s.ingest(record(120,2000000),120)
    s.decide(120)
    assert s.time_slice(60)==frozen and s.score_once(60,lambda _: (_ for _ in ()).throw(AssertionError('must not rescore')))==old
    mutated=s.time_slice(60);mutated['windows'][0]['latency_ms']=999
    assert s.time_slice(60)==frozen


def test_receiver_stamps_backdated_data_and_missing_windows_stay_missing():
    s=store();s.decide(60)
    assert s.ingest(record(arrival_time=30),70)=='late'
    assert s.received[0]['arrival_time']==70
    assert s.time_slice(60)['windows'][0]['latency_ms'] is None
    s.decide(120)
    assert all(not r['observed'] and r['request_count']==0 and r['coverage']==0 for r in s.windows)
    with pytest.raises(ValueError,match='monotonic'):s.decide(90)
    with pytest.raises(ValueError):s.ingest(record(150),140)


def test_grace_deadline_accepts_exact_arrival_and_freezes_afterward():
    s=store(decision_delay_seconds=30)
    s.ingest(record(arrival_time=60),60)
    s.ingest(record(60,20,3,arrival_time=90),90)
    row=s.time_slice(90)['windows'][0]
    assert row['observed'] and row['latency_ms']==16 and row['decision_time']==90
    s.ingest(replace(record(60,20,3),arrival_time=91),91)
    assert s.time_slice(90)['windows'][0]==row


def test_carried_values_and_mixed_exposure_never_look_fresh():
    stale=record(observed=False,carried_forward=True,latency_observed=False,workload_observed=False,
        exposure_observed=False,latency_sum_ms=0,latency_sum_sq_ms2=0,log_latency_sum=0,log_latency_sum_sq=0)
    s=store();s.ingest(stale,30);s.ingest(record(60),60)
    row=s.time_slice(60)['windows'][0]
    assert row['coverage']==.5 and not row['observed'] and not row['workload_observed']
    mixed=store();mixed.ingest(record(),30);mixed.ingest(record(60,release_id='v2',exposed=True),60)
    row=mixed.time_slice(60)['windows'][0]
    assert row['mixed_exposure'] and not row['exposure_observed'] and not row['observed']
    assert row['release_id'] is None and row['release_ids']==['v1','v2']


@pytest.mark.parametrize('changes',[{'arrival_time':1},{'request_count':True},{'event_time':31},
    {'interval_seconds':7},{'latency_ms':float('nan')},{'latency_sum_ms':1},{'latency_sum_sq_ms2':1},
    {'log_latency_sum_sq':0},{'workload':None},{'carried_forward':True},{'observed':False},{'class_id':-1}])
def test_public_validation(changes):
    with pytest.raises(ValueError):record(**changes)


@pytest.mark.parametrize('field',['fault_type','true_affected','injected_latent_effect','fault_id','severity'])
def test_truth_fields_are_rejected_from_public_contract(field):
    with pytest.raises(ValueError,match='public fields'):PublicRecord.from_dict(record().to_dict()|{field:'hidden'})


@pytest.mark.parametrize('changes',[{'enabled':1},{'missing_probability':1.1},{'delay_min_ticks':True},
    {'delay_max_ticks':-1},{'drop_windows':[1,1]},{'late_windows':[-1]},{'minimum_coverage':0},{'unknown':3}])
def test_transport_configuration_validation(changes):
    with pytest.raises(ValueError):TelemetryConfig.from_dict(changes)


def test_complete_transport_duplicate_delay_missing_recovery_and_replay():
    e=engine(TelemetryConfig(enabled=True,duplicate_probability=1,drop_windows=(1,),late_windows=(0,),late_delay_ticks=80))
    e.step(180)
    rows=e.telemetry.store.windows
    assert all(not r['observed'] and r['latency_ms'] is None for r in rows if r['window_index'] in (0,1))
    assert all(r['observed'] for r in rows if r['window_index']==2)
    assert e.telemetry.store.counters['duplicates']>0 and e.telemetry.store.counters['late']>0
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()
    first=e.telemetry.store.time_slice(60)
    e.step(60)
    assert e.telemetry.store.time_slice(60)==first


def test_transport_is_independent_from_workload_and_delayed_duplicates_do_not_change_windows():
    plain=engine();dupes=engine(TelemetryConfig(enabled=True,duplicate_probability=1))
    disabled=engine(TelemetryConfig(enabled=False))
    for e in (plain,dupes,disabled):e.step(120)
    assert plain.resource_model.trace()==dupes.resource_model.trace()==disabled.resource_model.trace()
    assert plain.telemetry.store.windows==dupes.telemetry.store.windows
    for stream in ('workload','faults','host_noise'):
        assert plain.artifact()['rng_states'][stream]==disabled.artifact()['rng_states'][stream]


def test_future_traffic_perturbations_leave_earlier_decisions_and_callback_scores_identical():
    a=engine();cfg=a.config
    changed=replace(cfg,resources=replace(cfg.resources,traffic=(TrafficLevel(121,20),)))
    b=SimulationEngine(changed,run_id='test-run')
    for e in (a,b):e.step(120)
    for t in (60,120):assert a.telemetry.store.time_slice(t)==b.telemetry.store.time_slice(t)
    score=lambda d:sum(r['latency_sum_ms'] for r in d['windows'] if r['observed'])
    earlier=[a.telemetry.store.score_once(120,score),b.telemetry.store.score_once(120,score)]
    assert earlier[0]==earlier[1]
    for e in (a,b):e.step(60)
    assert a.telemetry.store.time_slice(120)==b.telemetry.store.time_slice(120)
    assert a.telemetry.store.score_once(120,score)==earlier[0]
    assert a.telemetry.store.windows[-20:]!=b.telemetry.store.windows[-20:]


def test_completed_request_latency_comes_from_fifo_cohorts_not_proxy():
    e=engine();model=e.resource_model;rid=next(iter(model.replicas));work=model.services[model.replicas[rid].service_id].work_core_seconds
    model.queues[rid]=deque([(1,2),(2,1)]);model.queued[rid]=3
    assert model._consume(rid,3*work,2)==3
    assert [(r['request_count'],r['latency_ms']) for r in model.completed_batches]==[(2,2000),(1,1000)]


def test_fault_truth_is_separate_and_release_exposure_is_public(tmp_path):
    e=engine()
    plan=e.operations_command('preview',{'release_id':'sample-leak-v2'})
    e.operations_command('deploy',{'plan_id':plan['plan_id']})
    e.operations_command('fault',{'kind':'cpu_throttle','scope':'host','target':'host-01-01','duration':3})
    e.step(4);e.export_telemetry(tmp_path)
    public=e.telemetry.public_artifact();truth=e.telemetry_evaluator.artifact()
    assert all(key not in json.dumps(public) for key in ('fault_type','true_affected','injected_latent_effect','cpu_throttle'))
    assert any(r['fault_type']==['cpu_throttle'] and r['true_affected'] for r in truth['records'])
    assert all(r['injected_latent_effect'] is None for r in truth['records'])
    assert any(r['exposed'] and r['release_id']=='sample-leak-v2' for r in public['records'])
    assert (tmp_path/'public/records.jsonl').exists() and (tmp_path/'evaluator/truth.jsonl').exists()
    old_ids={r['record_id'] for r in public['records']};e.reset();e.step()
    assert e.telemetry_epoch==1 and old_ids.isdisjoint(r['record_id'] for r in e.telemetry.store.received)


def test_capacity_limits_and_conflicting_placement():
    s=store(max_records=1,max_windows=1);s.ingest(record(),30)
    assert s.ingest(record(60),60)=='capacity_drops'
    assert s.ingest(record(90),90)=='capacity_drops'
    assert len(s.time_slice(120)['windows'])==1
    with pytest.raises(ValueError):store().ingest(record(host_id='orphan'),30)


def test_persistence_and_public_api_committed_decisions_only(tmp_path):
    c=WorldController(engine().config,run_id='api-run',state_dir=tmp_path)
    c.engine.step(60);c.close()
    restored=WorldController(engine().config,state_dir=tmp_path)
    assert restored.engine.artifact()==c.engine.artifact()
    server=make_server(restored,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/api/telemetry') as response:data=json.load(response)
        assert data['enabled'] and data['records'][0]['run_id']=='api-run'
        assert all(k not in json.dumps(data) for k in ('fault_type','true_affected','injected_latent_effect'))
        with urlopen(base+'/api/telemetry?decision_time=60') as response:frozen=json.load(response)
        assert frozen==restored.engine.telemetry.store.time_slice(60)
        before=restored.engine.tick
        with pytest.raises(HTTPError):urlopen(base+'/api/telemetry?decision_time=120')
        assert restored.engine.tick==before
    finally:server.shutdown();server.server_close();thread.join(timeout=2);restored.close()


def test_new_public_modules_cannot_import_truth_or_scheduler():
    forbidden=('simulate','metrics','telemetry_evaluator','operations','fault_scheduler','faults')
    for name in ('telemetry','telemetry_transport','factor','preprocess','baselines','baselines_extra','kalman','hierarchy','decision'):
        tree=ast.parse((ROOT/f'canary_ssm/{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):assert not any(x in (node.module or '') for x in forbidden)
            if isinstance(node,ast.Import):assert not any(any(x in n.name for x in forbidden) for n in node.names)


def test_offline_causal_slice_filters_future_payloads_before_validation():
    from canary_ssm.telemetry import causal_time_slice
    prefix=[record().to_dict(),record(60).to_dict()]
    future=record(90).to_dict();future['latency_ms']=float('nan')
    late=record(arrival_time=100).to_dict();late['true_affected']=True
    first=causal_time_slice(prefix,'run',ROSTER,60,interval_seconds=30)
    changed=causal_time_slice(prefix+[future,late],'run',ROSTER,60,interval_seconds=30)
    assert first==changed and first['windows'][0]['observed']


def test_offline_slice_late_records_do_not_reopen_earlier_windows():
    from canary_ssm.telemetry import causal_time_slice
    data=[record(arrival_time=70),record(60),record(90),record(120)]
    sliced=causal_time_slice(data,'run',ROSTER,120,interval_seconds=30)
    assert sliced['windows'][0]['coverage']==.5 and not sliced['windows'][0]['observed']
    assert sliced['windows'][1]['coverage']==1 and sliced['windows'][1]['observed']
