"""Hand-computed allocation/lifetime checks independent of stochastic fixtures."""
import ast
import copy
import json
from dataclasses import replace
from pathlib import Path
import pytest
from canary_ssm.resources import ResourceModel,ResourceConfig,ServiceWorkload
from canary_ssm.topology import DataCenter,Rack,Host,HostCapacity,ServiceReplica,Topology
from canary_ssm.releases import behavior_manifest,ReleaseRegistry,memory_example_payloads
from canary_ssm.resource_health import summarize,ResourceHealthPolicy
from canary_ssm.engine import SimulationEngine,load_engine_config
ROOT=Path(__file__).resolve().parents[1]

class Arrivals:
    def __init__(self,n):self.n=n
    def random(self):return .5
    def poisson(self,mean):return self.n
    def multinomial(self,n,p):return [n]

def model(memory=100,rate=2,background=0,limit=None,dt=1):
    w=Topology((DataCenter('dc'),),(Rack('rack','dc'),),(Host('host','rack','dc',0,HostCapacity(1,memory,100,100)),),(ServiceReplica('service','replica','host','base'),))
    m=ResourceModel(ResourceConfig((ServiceWorkload('service',1,work_core_seconds=1,queue_limit=20,baseline_memory_mb=2,temporary_mb_per_request=3),),host_baseline_memory_mb=1,shared_jitter=0),w,dt)
    _,b=behavior_manifest({'schema_version':1,'profiles':[{'kind':'process_memory','retained_mb_per_request':rate,'background_mb_per_second':background,'retained_limit_mb':limit}]})
    m.configure_behavior('replica',b);return m.initial_world(w),m

def tick(w,m,t,n):m.route(w,t,Arrivals(n));return m.update(w,t)

def test_units_request_retention_and_temporary_reclamation():
    w,m=model();w=tick(w,m,1,1)
    r=m.last_hosts[0];assert r['memory_baseline_mb']==3 and r['memory_temporary_mb']==0
    assert r['memory_retained_mb']==2 and r['memory_mb']==5 and r['memory_headroom_mb']==95
    assert r['retained_added_mb_per_request']==2 and r['sampled_latency_mean_ms']==1000
    w=tick(w,m,2,0);assert m.retained['replica']==2 and m.last_hosts[0]['retained_added_mb_per_request'] is None

def test_background_units_and_cache_plateau_and_no_auto_free():
    w,m=model(rate=2,background=.5,limit=5,dt=2)
    w=tick(w,m,1,1);assert m.retained['replica']==3 # one request*2 MB + 2 seconds*.5 MB/s
    w=tick(w,m,2,1);assert m.retained['replica']==5
    w=tick(w,m,3,0);assert m.retained['replica']==5
    _,healthy=behavior_manifest({'schema_version':1,'profiles':[{'kind':'healthy'}]});m.configure_behavior('replica',healthy)
    w=tick(w,m,4,0);assert m.retained['replica']==5 # switching future behavior alone never frees existing allocations
    m.restart('replica',tick=5);assert m.retained['replica']==0 and m.process_restarts['replica']==1
    assert m.process_events[-1]['reclaimed_retained_mb']==5

def test_retention_without_latency_harm_then_pressure_slowdown():
    w,m=model(rate=1)
    for t in range(1,11):w=tick(w,m,t,1)
    assert all(r['sampled_latency_mean_ms']==1000 and r['pressure_slowdown_factor']==1 for r in m.host_trace)
    m.retained['replica']=80
    w=tick(w,m,11,1);r=m.last_hosts[0]
    assert r['pressure_slowdown_factor']==pytest.approx(.76) # occupancy=(3+80+3)/100=.86; 1-4*(.86-.8)
    assert r['processed']==0 and r['latency_proxy_ms']>1000
    w=tick(w,m,12,0);assert m.last_hosts[0]['sampled_latency_mean_ms']==2000

def test_oom_ends_process_reclaims_heap_and_stays_down_until_restart():
    w,m=model(memory=10,rate=8)
    m.profiles['replica']=replace(m.profiles['replica'],work_core_seconds=.5) # .6 core-seconds at 90% occupancy completes one request
    w=tick(w,m,1,2);r=m.last_hosts[0]
    assert r['processed']==r['completed']==1 and r['dropped_oom']==1
    assert r['process_state']=='OOM' and r['oom_count']==1 and r['latency_proxy_ms'] is None
    assert m.retained['replica']==0 and m.queued['replica']==0 and m.pending_count['replica']==0
    assert r['queue_start']+r['accepted']==r['queue_end']+r['completed']+r['dropped_oom']
    w=tick(w,m,2,1);assert m.last_services[0]['dropped_unavailable_routes']==1 and m.process_states['replica']=='OOM'
    m.restart('replica',tick=3);assert m.process_states['replica']=='RUNNING'
    assert m.process_restarts['replica']==1 and m.process_events[-1]['kind']=='RESTART'

def test_delayed_requests_hold_temporary_memory_until_response_or_oom():
    w,m=model(rate=0,background=0);m.response_delays_ms['replica']=2000
    w=tick(w,m,1,1);assert m.last_hosts[0]['memory_temporary_mb']==3
    w=tick(w,m,2,0);assert m.last_hosts[0]['memory_temporary_mb']==3
    w=tick(w,m,3,0);assert m.last_hosts[0]['memory_temporary_mb']==0
    assert m.last_hosts[0]['sampled_latency_mean_ms']==3000

def test_idle_background_allocations_trigger_oom_without_requests():
    w,m=model(memory=10,rate=0,background=4)
    w=tick(w,m,1,0);assert m.retained['replica']==4
    w=tick(w,m,2,0);assert m.process_states['replica']=='OOM' and m.last_hosts[0]['oom_count']==1
    assert m.process_events[-1]['reclaimed_retained_mb']==4

@pytest.mark.parametrize('fields',[{'retained_mb_per_request':-1},{'background_mb_per_second':float('inf')},{'retained_limit_mb':-1},{'retained_mb_per_request':True},{'unknown':1}])
def test_bad_memory_parameters_are_rejected(fields):
    with pytest.raises(ValueError):behavior_manifest({'schema_version':1,'profiles':[{'kind':'process_memory','retained_mb_per_request':1,**fields}]})

def test_memory_model_composition_and_immutable_versions():
    r=ReleaseRegistry(['service'])
    for p in memory_example_payloads('service'):r.register(p,0)
    assert len(r.records())==2
    with pytest.raises(ValueError):behavior_manifest({'schema_version':1,'profiles':[{'kind':'process_memory','retained_mb_per_request':1},{'kind':'retained_memory_leak','retained_mb_per_completion':1}]})

def test_advisory_is_causal_does_not_bridge_restarts_and_warns_for_cache_warmup():
    w,m=model(memory=10000,rate=1)
    for t in range(1,11):w=tick(w,m,t,5)
    policy=ResourceHealthPolicy(minimum_processed=5)
    a=summarize(m.host_trace,10,policy)['advisories'][0]
    assert 'observed_memory_growth_warning' in a['flags'] and a['latency_detector_decision'] is None and a['automatic_action'] is None
    changed=copy.deepcopy(list(m.host_trace));future=copy.deepcopy(changed[-1]);future.update(simulated_seconds=999,memory_retained_mb=99999);changed.append(future)
    assert summarize(changed,10,policy)['advisories'][0]==a
    m.restart('replica',tick=11);w=tick(w,m,11,0)
    a=summarize(m.host_trace,11,policy)['advisories'][0];assert a['status']=='insufficient_data' and a['growth_mb_per_request'] is None
    assert summarize(m.host_trace,12,policy)['advisories'][0]['status']=='stale'

def test_restart_command_is_validated_deferred_and_replayable():
    e=SimulationEngine(load_engine_config(ROOT/'configs/world_console.yaml'),run_id='memory-restart-test')
    rid=e.world.replicas[0].replica_id
    with pytest.raises(ValueError):e.operations_command('restart_process',{'replica_id':'orphan'})
    e.operations_command('restart_process',{'replica_id':rid});assert e.resource_model.process_restarts[rid]==0
    e.step();assert e.resource_model.process_restarts[rid]==1
    assert e.resource_model.process_events[-1]['reason']=='manual_restart'
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()

def test_resource_advisory_has_no_inference_truth_dependencies():
    imports=[]
    for n in ast.walk(ast.parse((ROOT/'canary_ssm/resource_health.py').read_text())):
        if isinstance(n,ast.ImportFrom):imports.append(n.module or '')
        elif isinstance(n,ast.Import):imports.extend(x.name for x in n.names)
    assert not any(any(v in x for v in ('truth','fault','simulate','evaluator','kalman','hierarchy','decision')) for x in imports)

def test_oom_discards_delayed_response_and_accounts_pending_memory():
    w,m=model(memory=10,rate=8);m.response_delays_ms['replica']=10000
    w=tick(w,m,1,1);r=m.last_hosts[0]
    assert r['processed']==1 and r['completed']==0 and r['dropped_oom']==1
    assert r['memory_temporary_mb']==0 and m.pending_count['replica']==0
    assert not m.pending_responses['replica'] and m.process_states['replica']=='OOM'

def test_restart_initial_heap_allocation_can_fail_without_exceeding_capacity():
    w,m=model(memory=10,rate=0)
    m.services['service']=replace(m.services['service'],initial_retained_memory_mb=5)
    m.platform_memory['host']=6 # baseline 3 + platform 6 leaves 1 MB, less than required startup heap 5
    m.restart('replica',tick=1)
    assert m.process_states['replica']=='OOM' and m.retained['replica']==0
    assert m.process_restarts['replica']==1 and m.reserved_memory('host')==9
    assert m.process_events[-1]['reason']=='restart_initial_allocation_failed'

def test_disabling_future_retention_does_not_remove_existing_heap_pressure():
    w,m=model(rate=0);m.retained['replica']=80
    _,b=behavior_manifest({'schema_version':1,'profiles':[{'kind':'healthy'}]});m.configure_behavior('replica',b)
    w=tick(w,m,1,1)
    assert m.retained['replica']==80 and m.last_hosts[0]['pressure_slowdown_factor']==pytest.approx(.76)

def test_low_request_count_and_unavailable_metrics_are_insufficient_not_clear():
    w,m=model(rate=1)
    for t in range(1,8):w=tick(w,m,t,1)
    a=summarize(m.host_trace,7)['advisories'][0]
    assert a['status']=='insufficient_data' and 'insufficient_request_count' in a['flags']
    m.unavailable_hosts={'host'};w=tick(w,m,8,0)
    a=summarize(m.host_trace,8)['advisories'][0]
    assert a['status']=='insufficient_data' and 'unavailable_resource_data' in a['flags']
