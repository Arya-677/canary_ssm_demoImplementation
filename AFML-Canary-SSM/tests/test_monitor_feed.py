import ast
import copy
import json
import math
import threading
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

import numpy as np
import pytest

from canary_ssm.monitor_feed import DetectorFeed,ROOT,risk,seal,validate
from canary_ssm.dashboard import WorldController,make_server,ApiError
from canary_ssm.engine import load_engine_config
from canary_ssm.monitor_stream import stream


class Clock:
    value=1000.
    def __call__(self):return self.value


@pytest.fixture
def artifact():return json.loads((ROOT/'demo-01.json').read_text())


@pytest.fixture
def feed(artifact):return DetectorFeed(artifact['host_roster'],Clock())


def test_risk_hand_values_and_degenerate_distribution():
    k=math.log(1.02)
    assert risk(k,.04)==.5
    assert risk(k+.2,.04)==pytest.approx(.8413447460685429)
    assert risk(k-.2,.04)==pytest.approx(.15865525393145707)
    assert risk(k,0)==0 and risk(k+.001,0)==1
    assert risk(None,None) is None


def test_saved_same_replay_full_covariance_risk_and_interval(feed,artifact):
    feed.command('monitor_load',{'artifact':artifact});snapshot=feed.snapshot()
    assert snapshot['calibration']=='UNCALIBRATED' and snapshot['policy'] is None
    assert 'not a joint release probability' in snapshot['release_score_label']
    f=artifact['frames'][-1];row=snapshot['rows'][-1]
    for mid,p in f['methods'].items():
        variance=p['covariance'][0][0];value=row['methods'][mid]
        assert value['risk']==pytest.approx(risk(p['mean'][0],variance))
        assert value['upper']-value['lower']==pytest.approx(2*1.959963984540054*np.sqrt(variance))
        assert value['release_score']==max(risk(mu,p['covariance'][j][j]) for j,mu in enumerate(p['mean']))
    assert set(f['methods'])=={'independent','strong','weak'}
    assert artifact['methods'][1]['version']!=artifact['methods'][2]['version']
    assert not np.allclose(f['methods']['strong']['covariance'],np.diag(np.diag(f['methods']['strong']['covariance'])))


def test_coverage_preperiod_and_prediction_are_not_healthy(feed,artifact):
    feed.command('monitor_load',{'artifact':artifact})
    feed.command('monitor_seek',{'index':20});assert feed.snapshot()['status']=='pre_exposure'
    feed.command('monitor_seek',{'index':90});s=feed.snapshot();assert s['status']=='insufficient_data'
    assert all(p['release_score'] is None for p in s['rows'][-1]['methods'].values())
    feed.command('monitor_seek',{'index':139});assert feed.snapshot()['status']=='observations_available'
    assert 'healthy' not in str(feed.snapshot()).lower()


def test_stream_prefix_is_immutable_duplicates_late_frames_rejected_stale_distinct(feed,artifact):
    metadata={k:v for k,v in artifact.items() if k not in ('frames','artifact_sha256')};metadata['source_kind']='external-detector-stream'
    feed.command('monitor_begin',{'metadata':metadata});assert feed.snapshot()['status']=='waiting_for_frames'
    frame=artifact['frames'][100]
    feed.command('monitor_append',{'frame':frame});before=copy.deepcopy(feed.snapshot()['rows'])
    assert feed.command('monitor_append',{'frame':frame})['status']=='duplicate_ignored'
    feed.command('monitor_append',{'frame':artifact['frames'][101]})
    assert feed.snapshot()['rows'][:-1]==before
    with pytest.raises(ValueError):feed.command('monitor_append',{'frame':frame})
    modified=copy.deepcopy(artifact['frames'][101]);modified['residual'][0]+=1
    with pytest.raises(ValueError):feed.command('monitor_append',{'frame':modified})
    feed.clock.value+=6;assert feed.snapshot()['status']=='stale_stream'
    feed.command('monitor_append',{'frame':artifact['frames'][102]});assert feed.snapshot()['status']=='observations_available'


def test_backend_playback_get_read_only_host_identity_and_reset(feed,artifact):
    feed.command('monitor_load',{'artifact':artifact});feed.command('monitor_seek',{'index':100})
    original=copy.deepcopy(feed.artifact)
    for _ in range(3):feed.snapshot(artifact['host_roster'][2]['host_id'])
    assert feed.artifact==original and feed.cursor==100
    feed.command('monitor_play',{});feed.clock.value+=1;feed.advance();assert feed.cursor==101
    feed.command('monitor_pause',{});feed.clock.value+=10;feed.advance();assert feed.cursor==101
    with pytest.raises(ValueError):feed.snapshot('frontend-tile-0')


@pytest.mark.parametrize('mutation',['checksum','truth','orphan','parent','future','negative_cov','wrong_components','fresh_missing','extra_policy'])
def test_bad_saved_artifacts_rejected_without_replacing_feed(feed,artifact,mutation):
    feed.command('monitor_load',{'artifact':artifact});a=copy.deepcopy(artifact)
    if mutation=='checksum':a['version']='tampered'
    if mutation=='truth':a['frames'][0]['fault_type']='cpu_throttle'
    if mutation=='orphan':a['host_roster'][0]['host_id']='unknown-host'
    if mutation=='parent':a['host_roster'][0]['rack_id']='wrong-rack'
    if mutation=='future':a['frames'][100]['decision_time']=0
    if mutation=='negative_cov':a['frames'][100]['methods']['strong']['covariance'][0][0]=-.1
    if mutation=='wrong_components':a['frames'][100]['methods']['strong']['group'][0]+=1
    if mutation=='fresh_missing':a['frames'][100]['latency_ms'][0]=None
    if mutation=='extra_policy':a['calibrated']=True
    if mutation!='checksum':a=seal(a)
    with pytest.raises((ValueError,TypeError,KeyError)):feed.command('monitor_load',{'artifact':a})
    assert feed.artifact==artifact


def cmd(c,name,args=None):
    return c.command({'command_id':'t-'+str(c.outcome_sequence),'run_id':c.run_id,'epoch':c.epoch,'command':name,**({'args':args} if args is not None else {})})


def test_controller_monitor_commands_do_not_move_world_deadline_persist_replay(tmp_path,artifact):
    clock=Clock();config=load_engine_config(Path(__file__).resolve().parents[1]/'configs/world_recovery.yaml')
    c=WorldController(config,monotonic=clock,state_dir=tmp_path)
    cmd(c,'start');deadline=c._next_tick;world=c.engine.artifact()
    cmd(c,'monitor_load',{'artifact':artifact});cmd(c,'monitor_seek',{'index':100})
    assert c.engine.artifact()==world and c._next_tick==deadline
    cmd(c,'pause');saved=c.export_run();c.close()
    restored=WorldController(config,state_dir=tmp_path)
    assert restored.detector_feed.cursor==100 and restored.detector_feed.artifact==artifact
    cmd(restored,'load_run',{'run':saved});assert restored.detector_feed.artifact==artifact
    cmd(restored,'monitor_seek',{'index':110});assert restored.read_only
    cmd(restored,'reset');assert not restored.detector_feed.snapshot()['connected'];restored.close()


def test_http_saved_stream_truth_gate_and_no_world_inference_claim(artifact):
    config=load_engine_config(Path(__file__).resolve().parents[1]/'configs/world_recovery.yaml')
    c=WorldController(config);server=make_server(c,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        def get(path):
            with urlopen(base+path) as r:return json.load(r)
        assert not get('/api/detectors')['connected']
        result=stream(artifact,base,100,103,0);assert result['frames_sent']==3
        snapshot=get('/api/detectors');assert snapshot['mode']=='stream' and len(snapshot['rows'])==3
        assert c.engine.tick==0 and get('/api/state')['detector_status']=='DETECTOR NOT CONNECTED'
        exported=get('/api/detectors/export');assert len(exported['frames'])==3
        assert all('fault_type' not in f for f in exported['frames'])
        with pytest.raises(HTTPError) as err:get('/api/detectors/evaluator')
        assert err.value.code==403
        assert get('/api/detectors/evaluator?developer=1')['evaluator_only']
        assert 'recipe' not in snapshot and 'targets' not in snapshot
    finally:server.shutdown();server.server_close();c.close();thread.join()


def test_public_adapter_has_no_evaluator_imports():
    root=Path(__file__).resolve().parents[1]/'canary_ssm'
    for name in ('monitor_feed','public_filter','public_hierarchy','public_adjustment'):
        for node in ast.walk(ast.parse((root/(name+'.py')).read_text())):
            modules=[node.module or ''] if isinstance(node,ast.ImportFrom) else [n.name for n in node.names] if isinstance(node,ast.Import) else []
            assert not any(any(s in m for s in ('truth','simulate','metrics','evaluator','scenario')) for m in modules)


def test_matching_world_stream_is_explicit_and_future_frame_is_rejected(artifact):
    config=load_engine_config(Path(__file__).resolve().parents[1]/'configs/world_recovery.yaml')
    c=WorldController(config)
    metadata={k:v for k,v in artifact.items() if k not in ('frames','artifact_sha256')}
    metadata.update(run_id=c.run_id,source_kind='external-detector-stream')
    cmd(c,'monitor_begin',{'metadata':metadata})
    assert c.packet()['detector_status']=='UNCALIBRATED DETECTOR STREAM'
    with pytest.raises(ApiError,match='future'):cmd(c,'monitor_append',{'frame':artifact['frames'][100]})
    assert c.engine.tick==0 and c.detector_feed.cursor==-1
    cmd(c,'reset');assert c.packet()['detector_status']=='DETECTOR NOT CONNECTED';c.close()


def test_versioned_demonstrations_share_prefix_and_separate_truth():
    samples=[json.loads((ROOT/f'demo-{i:02}.json').read_text()) for i in range(1,5)]
    assert len({a['replay_id'] for a in samples})==4
    assert all(a['frames'][:80]==samples[0]['frames'][:80] for a in samples)
    assert all([m['method_id'] for m in a['methods']]==['independent','weak','strong'] for a in samples)
    assert all(a['source_kind']=='simulated-metrics-replay' for a in samples)
    assert all('scenario' not in a and 'targets' not in a for a in samples)
    assert (ROOT/'evaluator/recipes.json').exists()
