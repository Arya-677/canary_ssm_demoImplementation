import ast
import base64
import copy
import json
from dataclasses import FrozenInstanceError,replace
from pathlib import Path

import numpy as np
import pytest

from canary_ssm.releases import ReleaseRegistry,example_payloads,behavior_manifest,digest
from canary_ssm.resources import ResourceModel,ResourceConfig,ServiceWorkload
from canary_ssm.topology import Topology,DataCenter,Rack,Host,HostCapacity,ServiceReplica
from canary_ssm.engine import SimulationEngine,load_engine_config
from canary_ssm.telemetry import digest as public_digest
from canary_ssm.public_adjustment import panel_from_time_slice

ROOT=Path(__file__).resolve().parents[1]


def test_immutable_examples_hash_canonicalization_versions_and_retry():
    registry=ReleaseRegistry(['demo-service']);a,b=example_payloads()
    first=registry.register(a,3);second=registry.register(b,4)
    assert first.version=='1.0.0' and second.version=='1.1.0' and first.content_hash!=second.content_hash
    assert len(first.content_hash)==64 and first.creation.created_tick==3
    assert registry.register(a,99)==first
    with pytest.raises(FrozenInstanceError):first.version='2.0.0'
    with pytest.raises(FrozenInstanceError):second.behavior.error_probability=0
    copy_record=second.to_dict();copy_record['behavior_manifest']['profiles'].clear()
    assert registry.get(second.release_id).to_dict()['behavior_manifest']['profiles']
    reversed_profiles=copy.deepcopy(b);reversed_profiles['behavior_manifest']['profiles'].reverse()
    assert registry.register(reversed_profiles,100)==second
    changed=copy.deepcopy(a);changed['version']='2.0.0'
    with pytest.raises(ValueError,match='Immutable'):registry.register(changed,4)
    changed=copy.deepcopy(a);changed['release_id']='another'
    with pytest.raises(ValueError,match='version'):registry.register(changed,4)
    assert len(registry.records())==2


@pytest.mark.parametrize('manifest',[
    {'schema_version':True,'profiles':[{'kind':'healthy'}]},
    {'schema_version':2,'profiles':[{'kind':'healthy'}]},
    {'schema_version':1,'profiles':[]},
    {'schema_version':1,'profiles':[{'kind':'healthy'},{'kind':'extra_cpu_work','work_multiplier':2}]},
    {'schema_version':1,'profiles':[{'kind':'extra_cpu_work','work_multiplier':17}]},
    {'schema_version':1,'profiles':[{'kind':'retained_memory_leak','retained_mb_per_completion':-1}]},
    {'schema_version':1,'profiles':[{'kind':'increased_error_probability','error_probability':1.01}]},
    {'schema_version':1,'profiles':[{'kind':'increased_error_probability','error_probability':True}]},
    {'schema_version':1,'profiles':[{'kind':'slower_response','response_delay_ms':float('nan')}]},
    {'schema_version':1,'profiles':[{'kind':'slower_response','response_delay_ms':300001}]},
    {'schema_version':1,'profiles':[{'kind':'extra_cpu_work','work_multiplier':2},{'kind':'extra_cpu_work','work_multiplier':3}]},
    {'schema_version':1,'profiles':[{'kind':'execute_source','command':'python x.py'}]},
    {'schema_version':1,'profiles':[{'kind':'healthy','code':'print(1)'}]},
])
def test_invalid_manifests_rejected(manifest):
    registry=ReleaseRegistry(['demo-service']);p=example_payloads()[0];p['behavior_manifest']=manifest
    with pytest.raises(ValueError):registry.register(p,0)
    assert registry.records()==()


@pytest.mark.parametrize('field,value',[('schema_version',2),('service_id','orphan'),('version','latest'),('content_hash','wrong'),('creation_metadata',{'author':'x','created_tick':7}),('creation_metadata',{'author':'x','created_at':'2026-11-14'})])
def test_invalid_registration_is_transactional(field,value):
    registry=ReleaseRegistry(['demo-service']);p=example_payloads()[0];p[field]=value
    with pytest.raises(ValueError):registry.register(p,0)
    assert not registry.records() and not registry.source_attachments()


def test_attachment_hashes_inert_source_and_metadata_immutability(tmp_path):
    p=example_payloads()[0];sentinel=tmp_path/'executed'
    content=f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')".encode()
    p['source_attachment']={'filename':'memory-leak.py','content_base64':base64.b64encode(content).decode()}
    registry=ReleaseRegistry(['demo-service']);r=registry.register(p,0)
    assert not sentinel.exists() and not r.to_dict()['executed']
    assert r.content_hash!=example_payloads()[0].get('content_hash')
    expected=digest({'behavior_manifest':json.loads(r.manifest_json),'source_sha256':r.attachment.sha256})
    assert r.content_hash==expected
    sources=registry.source_attachments();sources.clear();assert registry.source_attachments()
    p['source_attachment']['filename']='renamed.py'
    with pytest.raises(ValueError,match='Immutable'):registry.register(p,0)


def tiny_model():
    world=Topology((DataCenter('dc'),),(Rack('rack','dc'),),
        (Host('host','rack','dc',0,HostCapacity(1,100,100,100)),),
        (ServiceReplica('service','replica','host','baseline'),))
    cfg=ResourceConfig((ServiceWorkload('service',1,work_core_seconds=1,queue_limit=4,baseline_memory_mb=2,temporary_mb_per_request=3),),host_baseline_memory_mb=1,shared_jitter=0)
    return world,ResourceModel(cfg,world,1,release_seed=10000)


class Arrivals:
    def __init__(self,n):self.n=n
    def random(self):return .5
    def poisson(self,_):return self.n
    def multinomial(self,n,p):return np.array([n])


def tick(model,world,t,n):
    model.route(world,t,Arrivals(n));return model.update(world,t)


def test_delay_is_not_cpu_work_and_preserves_queue_memory_latency_conservation():
    world,m=tiny_model();m.response_delays_ms['replica']=1500
    world=tick(m,world,1,1)
    assert m.last_hosts[0]['processed']==1 and m.last_hosts[0]['completed']==0
    assert m.pending_count['replica']==1 and m.queued['replica']==0
    assert m.last_hosts[0]['memory_temporary_mb']==3 and m.last_hosts[0]['cpu_cores']==1
    world=tick(m,world,2,0);assert m.last_hosts[0]['cpu_cores']==0 and not m.completed_batches
    world=tick(m,world,3,0)
    assert m.last_hosts[0]['completed']==1 and m.completed_batches[0]['latency_ms']==3000
    assert m.last_hosts[0]['memory_temporary_mb']==0
    for row in m.service_trace:
        assert row['queue_start']+row['accepted']==row['queue_end']+row['completed']+row['dropped_unavailable_queued']+row['dropped_restart']


def test_errors_cpu_and_leak_compose_and_are_bounded():
    world,m=tiny_model();m.profiles['replica']=replace(m.profiles['replica'],work_core_seconds=2)
    m.error_probabilities['replica']=1.;m.retention_rates['replica']=64.
    world=tick(m,world,1,2);assert m.last_hosts[0]['processed']==0
    world=tick(m,world,2,0)
    row=m.last_hosts[0];assert row['processed']==row['completed']==row['errors']==1 and row['succeeded']==0
    assert row['memory_retained_mb']==64 and row['memory_mb']<=100
    world=tick(m,world,3,0);world=tick(m,world,4,0)
    assert m.last_hosts[0]['retention_blocked_mb']>0 and m.last_hosts[0]['memory_mb']<=100


def test_pending_response_limit_restart_and_unavailable_drop():
    world,m=tiny_model();m.response_delays_ms['replica']=10000
    for t in range(1,7):world=tick(m,world,t,4)
    assert m.pending_count['replica']+m.queued['replica']<=4
    assert m.last_hosts[0]['dropped_queue']>0
    pending=m.pending_count['replica'];m.restart('replica');assert m.restart_drops['replica']>=pending and m.pending_count['replica']==0
    world=tick(m,world,7,1);m.unavailable_hosts={'host'};world=tick(m,world,8,0)
    assert m.last_hosts[0]['dropped_unavailable_queued']>0 and m.pending_count['replica']==0


def test_registry_survives_reset_and_replay_source_never_runs():
    e=SimulationEngine(load_engine_config(ROOT/'configs/world_console.yaml'))
    p=example_payloads()[1];p.update(release_id='opaque-new',version='2.0.0')
    r=e.operations_command('register_release',{'release':p});e.step(1);e.reset()
    assert e.demo.registry.get(r['release_id']).to_dict()['version']=='2.0.0'
    plan=e.operations_command('preview',{'release_id':r['release_id']});e.operations_command('deploy',{'plan_id':plan['plan_id']});e.step(8)
    assert e.snapshot()['deployment']['release_metadata']['content_hash']==r['content_hash']
    assert 'behavior_manifest' not in json.dumps(e.snapshot()) and 'error_probability' not in json.dumps(e.snapshot())
    assert all('pending_responses' not in r and 'pending_response_count' in r for r in e.snapshot()['resources']['replicas'])
    assert SimulationEngine.replay(e.artifact()).artifact()==e.artifact()


def test_release_label_is_not_a_detector_feature():
    root=ROOT/'examples/control_adjustment/public';original=json.loads((root/'monitoring_slice.json').read_text());changed=copy.deepcopy(original)
    for window in changed['windows']:
        if window.get('release_id') is not None:window['release_id']='memory-leak-name-only'
    changed['input_sha256']=public_digest(changed['windows'])
    a=panel_from_time_slice(original,'fixture-service');b=panel_from_time_slice(changed,'fixture-service')
    for name in ('y','x','observed','fresh','exposed','exposure_known'):
        np.testing.assert_array_equal(getattr(a,name),getattr(b,name))


def test_inference_import_boundary_excludes_release_manifest():
    for name in ('factor','preprocess','public_adjustment','public_filter','public_hierarchy','nested_hierarchy','monitor_feed'):
        tree=ast.parse((ROOT/'canary_ssm'/f'{name}.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):assert not any(s in (node.module or '') for s in ('releases','operations','evaluator','simulate'))
