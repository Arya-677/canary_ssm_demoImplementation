import json
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from canary_ssm.dashboard import ApiError,WorldController,make_server
from canary_ssm.engine import load_engine_config,SimulationEngine

ROOT=Path(__file__).resolve().parents[1]


def command(c,name,args=None,cid=None):
    p=dict(command_id=cid or 'console-'+str(c.revision),run_id=c.run_id,epoch=c.epoch,command=name)
    if args is not None:p['args']=args
    return c.command(p)


@pytest.fixture
def controller(tmp_path):
    c=WorldController(load_engine_config(ROOT/'configs/world_console.yaml'),state_dir=tmp_path)
    yield c
    c.close()


def allocation(per_rack=1):
    return dict(release_id='release-001',per_rack=per_rack,canary_fraction=.35,baseline_seconds=2,monitoring_seconds=10)


def test_balanced_host_choice_preview_is_pure_and_matches_frozen_cohort(controller):
    before=controller.engine.artifact()
    p=command(controller,'rollout_preview',allocation())['result']
    assert controller.engine.artifact()==before
    assert len(p['canaries'])==4 and len(p['controls'])==16
    assert all(len(g['controls'])>=3 and g['canaries'] for g in p['groups'].values())
    larger=command(controller,'rollout_preview',allocation(2))['result']
    assert len(larger['canaries'])==8 and len(larger['controls'])==12
    r=command(controller,'rollout_create',allocation())['result']
    assert r['canaries']==p['canaries'] and r['cohort_sha256']==p['cohort_sha256']


@pytest.mark.parametrize('change',[{'per_rack':0},{'per_rack':3},{'canary_fraction':1},{'release_id':'unknown'},{'baseline_seconds':-1},{'host_ids':['orphan']}])
def test_preview_uses_real_backend_validation(controller,change):
    with pytest.raises(ApiError):
        command(controller,'rollout_preview',{**allocation(),**change})
    assert controller.engine.tick==0 and not controller.engine.rollouts.records()


def test_nominal_weights_versions_requests_and_pending_tick_are_backend_evidence(controller):
    r=command(controller,'rollout_create',allocation())['result']
    command(controller,'rollout_baseline',{'rollout_id':r['rollout_id']})
    assert controller.packet()['snapshot']['rollout']['rollouts'][0]['pending_action']=='rollout_baseline'
    assert controller.packet()['snapshot']['rollout']['rollouts'][0]['state']=='CREATED'
    command(controller,'step')
    rows=controller.packet()['console']['replicas']
    assert sum(x['nominal_traffic_fraction'] for x in rows)==pytest.approx(1)
    assert {x['nominal_traffic_fraction'] for x in rows if x['role']=='canary'}=={.0875}
    assert {x['nominal_traffic_fraction'] for x in rows if x['role']=='control'}=={.040625}
    assert all(x['release_id']=='release-healthy-v1' and x['version'] for x in rows)
    assert sum(x['routed_requests_last_tick'] for x in rows)==sum(controller.engine.resource_model.routed_by_replica.values())>0
    command(controller,'step')
    command(controller,'rollout_expose',{'rollout_id':r['rollout_id']});command(controller,'step')
    rows=controller.packet()['console']['replicas']
    assert all(x['release_id']=='release-001' for x in rows if x['role']=='canary')
    command(controller,'rollout_rollback',{'rollout_id':r['rollout_id']});command(controller,'step')
    assert all(x['release_id']=='release-healthy-v1' for x in controller.packet()['console']['replicas'])


def test_public_console_never_exposes_injected_fault_labels(controller):
    command(controller,'fault',dict(kind='cpu_throttle',scope='host',target='host-01-01',duration=2,severity=.8,seed=10000))
    command(controller,'step')
    public=controller.packet()['console']
    encoded=json.dumps(public)
    assert not any(x in encoded for x in ('injected_truth','true_affected','cpu_throttle','severity','fault_type'))
    assert public['context']['calibration_status']=='UNCALIBRATED'
    assert public['context']['model_id']=='DETECTOR NOT CONNECTED'
    assert public['context']['seed']==controller.engine.config.seed


def test_current_run_uncalibrated_stream_shows_actual_method_ids(controller):
    artifact=json.loads((ROOT/'examples/detector_dashboard/demo-01.json').read_text())
    metadata={k:v for k,v in artifact.items() if k not in ('frames','artifact_sha256')}
    metadata.update(run_id=controller.engine.run_id,source_kind='external-detector-stream')
    command(controller,'monitor_begin',{'metadata':metadata})
    context=controller.packet()['console']['context']
    assert context['calibration_status']=='UNCALIBRATED'
    assert context['policy_id'] is None
    assert 'DETECTOR NOT CONNECTED' not in context['model_id']
    assert all(m['method_id'] in context['model_id'] for m in metadata['methods'])


def test_backend_checkpoints_persist_and_replay_without_browser_summaries(controller):
    command(controller,'step');command(controller,'step')
    row=command(controller,'history_save',{})['result']
    saved=controller.archive.get(row['checkpoint_id'])
    assert saved['engine']==SimulationEngine.replay(saved['engine']).artifact()
    command(controller,'reset')
    assert controller.engine.tick==0 and len(controller.archive.list())>=1
    command(controller,'history_load',{'checkpoint_id':row['checkpoint_id']})
    assert controller.read_only and controller.engine.tick==2
    with pytest.raises(ApiError):command(controller,'rollout_preview',allocation())
    state_dir=controller.state_dir
    controller.close()
    restored=WorldController(load_engine_config(ROOT/'configs/world_console.yaml'),state_dir=state_dir)
    try:
        assert restored.run_id==controller.run_id and restored.read_only and restored.engine.tick==2
        assert any(x['checkpoint_id']==row['checkpoint_id'] for x in restored.archive.list())
    finally:restored.close()


def test_checkpoint_corruption_and_traversal_are_rejected(controller):
    row=command(controller,'history_save',{})['result']
    path=controller.state_dir/'runs'/(row['checkpoint_id']+'.json')
    path.write_text('{}')
    with pytest.raises(ApiError,match='hash mismatch'):command(controller,'history_load',{'checkpoint_id':row['checkpoint_id']})
    with pytest.raises(ApiError,match='Invalid checkpoint'):command(controller,'history_load',{'checkpoint_id':'../session'})
    assert controller.engine.tick==0


def test_imported_run_identity_matches_engine_after_refresh_and_reset(controller):
    source=WorldController(load_engine_config(ROOT/'configs/world_console.yaml'),run_id='imported-backend-run')
    try:
        command(source,'step')
        saved=source.export_run()
        command(controller,'load_run',{'run':saved})
        assert controller.packet()['run_id']==controller.engine.run_id=='imported-backend-run'
        command(controller,'reset')
        assert controller.packet()['run_id']==controller.engine.run_id=='imported-backend-run'
        controller.close()
        restored=WorldController(load_engine_config(ROOT/'configs/world_console.yaml'),state_dir=controller.state_dir)
        try:assert restored.packet()['run_id']==restored.engine.run_id=='imported-backend-run'
        finally:restored.close()
    finally:source.close()


def test_applied_command_is_not_reexecuted_after_receipt_cache_eviction_or_restart(controller):
    original=dict(command_id='durable-lost-step',run_id=controller.run_id,epoch=controller.epoch,command='step')
    controller.command(original)
    for i in range(260):
        controller.command(dict(command_id='speed-'+str(i),run_id=controller.run_id,epoch=controller.epoch,command='speed',speed=1))
    assert 'durable-lost-step' not in controller._receipts
    retry=controller.command(original)
    assert controller.engine.tick==1 and retry['status']=='applied'
    controller.close()
    restored=WorldController(load_engine_config(ROOT/'configs/world_console.yaml'),state_dir=controller.state_dir)
    try:
        assert restored.command(original)['status']=='applied'
        assert restored.engine.tick==1
        with pytest.raises(ApiError,match='different parameters'):
            restored.command({**original,'command':'reset'})
    finally:restored.close()


def test_lost_response_can_be_resolved_and_same_id_does_not_step_twice(controller):
    server=make_server(controller,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin='http://127.0.0.1:'+str(server.server_port)
    try:
        first=command(controller,'step',cid='lost-step')
        def get(path):
            with urlopen(origin+path) as response:return json.load(response)
        result=get('/api/commands?command_id=lost-step')
        assert result['known'] and result['receipt']==first
        assert command(controller,'step',cid='lost-step')==first and controller.engine.tick==1
        assert not get('/api/commands?command_id=not-received')['known']
        with pytest.raises(ApiError):command(controller,'bad',cid='rejected-command')
        rejected=get('/api/commands?command_id=rejected-command')
        assert rejected['known'] and rejected['receipt'] is None and rejected['outcome']['status']=='rejected'
        with urlopen(origin+'/api/state') as response:
            assert json.load(response)['run_id']==controller.run_id
        with urlopen(origin+'/api/state') as response:
            assert json.load(response)['snapshot']['tick']==1
    finally:server.shutdown();server.server_close();thread.join()
