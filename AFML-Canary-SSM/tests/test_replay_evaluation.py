import ast
import gzip
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from canary_ssm.evaluation_inputs import generate,identity,save_bundle,load_public,SCENARIOS
from canary_ssm.evaluation_outcomes import research_target,world_release_target,interval_event,evaluate,interference,first_crossing
from canary_ssm.evaluation_scoring import fit_public,compare,COMMON_METHODS
from canary_ssm.public_adjustment import PublicPanel
from canary_ssm.schema import KAPPA
from canary_ssm.replay_evaluator import null_job,require_final,digest,write,source_hashes
from canary_ssm.policy_artifacts import ordered_threshold

def output(T=60):
    return dict(score=np.full(T,-2.),eligible=np.ones(T,bool),host_rank=np.tile([.9,1.,.2,.1],(T,1)),output_kind='conditional_gaussian_posterior',times=(np.arange(T)+1)*60.,host_ids=('h0','h1','h2','h3'),exposure_time=60.)

def test_strict_harm_boundary_and_minimum_duration():
    a=np.zeros((60,4));a[10:25,0]=KAPPA
    assert not research_target(SimpleNamespace(a=a),4)[0]['has_event']
    a[10:24,0]+=1e-8
    assert not research_target(SimpleNamespace(a=a),4)[0]['has_event']
    a[24,0]+=1e-8
    assert research_target(SimpleNamespace(a=a),4)[0]['intervals']==[(0,10,25)]

@pytest.mark.parametrize('alarm,status,capped',[(9,'premature',50),(10,'success',0),(24,'success',14),(25,'late_after_recovery',50),(None,'miss',50)])
def test_first_alarm_outcomes_hand_calculated(alarm,status,capped):
    a=np.zeros((60,4));a[10:25,0]=KAPPA+.001;ev,t=research_target(SimpleNamespace(a=a),4);o=output()
    if alarm is not None:o['score'][alarm:]=-.1
    r=evaluate(o,-1.,ev,t,o['host_ids'],True)
    assert r['status']==status and r['capped']==capped
    assert r['localization_time_index']==40 and r['top3_recall']==1

def test_abstention_keeps_capped_miss_and_original_prediction_localization():
    a=np.zeros((60,4));a[10:25,0]=KAPPA+.001;ev,t=research_target(SimpleNamespace(a=a),4);o=output();o['eligible'][:]=False
    r=evaluate(o,-1.,ev,t,o['host_ids'],True)
    assert r['status']=='miss' and r['capped']==50 and r['no_eligible_data']
    assert r['top3_recall']==1 and r['fresh_top3_recall'] is None

def test_threshold_and_ties_no_data_hand_example():
    assert ordered_threshold(list(range(500)),.05)['k']==476
    o=output();o['score'][:]=-.1
    assert first_crossing(o,-.1) is None
    o['eligible'][:]=False
    assert first_crossing(o,-1.) is None
    assert ordered_threshold([0.]*2,.05)['threshold']=='+inf'

def panel():
    y=np.zeros((120,4));mask=np.ones_like(y,bool)
    return PublicPanel('public-unit',('h0','h1','h2','h3'),('r','r','s','s'),(0,0,1,1),np.arange(1,121)*60.,y,y.copy(),mask,mask.copy(),np.zeros_like(mask),mask.copy())

def test_world_counterfactual_is_only_offline_and_missing_target_is_unknown():
    n=panel();y=n.y.copy();y[70:85,0]=KAPPA+.001;h=replace(n,y=y)
    ev,t,_=world_release_target(n,h,['h0']);assert ev['intervals']==[(0,70,85)] and 'NOT an observed online' in t['nature']
    obs=h.observed.copy();obs[76]=False
    ev,t,_=world_release_target(n,replace(h,observed=obs),['h0'])
    assert not ev['has_event'] and t['target_status']=='partially_unknown'

def test_world_interference_records_control_changes():
    n=panel();y=n.y.copy();y[:,1]=.1;h=replace(n,y=y)
    rr=[dict(tick=1,host_id=x,routed_requests=10,queue_end=0) for x in n.host_ids]
    result=interference(n,h,{'resource_hosts':rr,'exogenous':[.2]},{'resource_hosts':rr,'exogenous':[.2]},['h0'])
    assert result['observed_cross_host_interference'] and result['exogenous_uniforms_identical']
    assert not result['additive_identity_required'] and not result['online_counterfactual_observed']

def test_role_seeds_disjoint_pairs_stay_together_and_final_sealed():
    used=set()
    for role in ('development','threshold-calibration','null-validation','final-test','smoke'):
        for gen in ('research','world'):
            for scenario in SCENARIOS:
                seed,_=identity(gen,role,17000,scenario)
                assert seed not in used;used.add(seed)
    with pytest.raises(ValueError,match='Final-test'):generate('world','final-test',17000)

@pytest.mark.parametrize('role',['threshold-calibration','null-validation','final-test','smoke'])
def test_fit_rejects_other_data_roles(role):
    with pytest.raises(ValueError,match='development'):fit_public('research',[],[],role=role)

@pytest.fixture(scope='module')
def research():
    p,_,_=generate('research','development',17000,'healthy','null',healthy_fit=True)
    models=fit_public('research',[p],list('h'+str(i).zfill(2) for i in range(8)))
    p,t,m=generate('research','smoke',17000,'recovery','harm')
    return p,t,m,models

def test_identical_public_replay_all_methods_and_baselines_have_no_posterior(research):
    p,t,m,models=research;r=compare('research',p,models,{},m['rack_ids'])
    assert set(r)==set(COMMON_METHODS)
    for name,o in r.items():
        if name in ('adj_ewma','adj_cusum','topk_cusum'):assert o['mean'] is None and o['variance'] is None
        else:assert o['mean'].shape==(300,8)
    np.testing.assert_allclose(r['complete_pooling']['mean'][180:],np.repeat(r['complete_pooling']['mean'][180:,:1],8,axis=1))
    assert not np.allclose(r['weaker_pooling']['mean'][180:],r['stronger_pooling']['mean'][180:])

def test_future_or_truth_changes_cannot_change_earlier_scores(research):
    p,t,m,models=research;a=compare('research',p,models,{},m['rack_ids']);y=p.y.copy();y[220:]+=2
    b=compare('research',replace(p,y=y),models,{},m['rack_ids']);t.a[:]=123;c=compare('research',p,models,{},m['rack_ids'])
    for name in a:
        np.testing.assert_array_equal(a[name]['score'][:220],b[name]['score'][:220]);np.testing.assert_array_equal(a[name]['score'],c[name]['score'])

def test_original_additive_paired_identity_and_opaque_ids():
    n,nt,_=generate('research','smoke',17001,'recovery','null');h,ht,_=generate('research','smoke',17001,'recovery','harm');mask=n.observed&h.observed
    np.testing.assert_allclose((h.y-n.y-(ht.a-nt.a)-(ht.spill-nt.spill))[mask],0,atol=1e-12)
    assert 'harm' not in h.rollout_id and 'null' not in n.rollout_id

def test_world_public_roundtrip_truth_separate(tmp_path):
    p,t,m=generate('world','smoke',17000,'healthy','null',healthy_fit=True);save_bundle('world',p,t,m,tmp_path,True)
    assert load_public('world',tmp_path/'public').fingerprint()==p.fingerprint()
    assert (tmp_path/'evaluator/truth.json.gz').exists()
    with np.load(tmp_path/'public/input.npz') as z:assert not any('truth' in k or 'fault' in k for k in z.files)

def test_public_scorer_import_boundary():
    import canary_ssm.evaluation_scoring as s
    text=Path(s.__file__).read_text();tree=ast.parse(text)
    imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(x.split('.')[-1] in {'simulate','metrics','experiments','evaluation_inputs','evaluation_outcomes','replay_evaluator'} for x in imports)
    assert 'truth.npz' not in text

def test_null_cache_rejects_model_or_saved_score_tampering(tmp_path,research):
    models=research[3];settings={'independent':.003};job=('research','latent_effect','threshold-calibration',0,17005,str(tmp_path),models,settings)
    rows=null_job(job);assert null_job(job)==rows
    with pytest.raises(ValueError,match='modified'):null_job((*job[:-1],{'independent':.008}))
    with (tmp_path/'inputs/threshold-calibration/latent_effect/0/scores.npz').open('ab') as f:f.write(b'modified')
    with pytest.raises(ValueError,match='modified'):null_job(job)

def test_forged_final_gate_cannot_open_test_data(tmp_path):
    import scipy
    f=dict(sources=source_hashes(),versions={'numpy':np.__version__,'scipy':scipy.__version__},B=2000,n_validation=2000,gate='PASS')
    f['freeze_hash']=digest(f);write(tmp_path/'development_freeze.json',f)
    with pytest.raises(ValueError,match='per-family'):require_final(tmp_path)
    assert not (tmp_path/'final_test_access.json').exists()

def test_world_future_records_and_hidden_labels_never_change_earlier_scores():
    root=Path(__file__).resolve().parents[1]
    import json
    freeze=json.loads((root/'examples/evaluator_v2/development_freeze.json').read_text())
    p,t,m=generate('world','smoke',17010,'host_fault','harm');models=freeze['models']['world'];settings=freeze['settings']['world']
    a=compare('world',p,models,settings);y=p.y.copy();y[90:]+=5
    b=compare('world',replace(p,y=y),models,settings)
    for row in t['records']:row['fault_type']='private-only-perturbation'
    c=compare('world',p,models,settings)
    for name in a:
        np.testing.assert_array_equal(a[name]['score'][:90],b[name]['score'][:90]);np.testing.assert_array_equal(a[name]['score'],c[name]['score'])

def test_infrastructure_localization_does_not_discard_unmonitored_hosts():
    mask=np.zeros((60,5),bool);mask[10:30,4]=True;event=interval_event(mask,1);o=output()
    target=dict(target_id='operator-infrastructure-window-v1',target_status='defined',target_unknown_windows=0)
    row=evaluate(o,-1.,event,target,('h0','h1','h2','h3','unmonitored-control'))
    assert row['unmonitored_affected_hosts']==1 and row['top3_recall'] is None
    assert row['localization_status']=='target includes hosts outside monitored cohort'

def test_throughput_cannot_count_a_duplicate_command_as_a_simulation_step(tmp_path):
    import threading
    from canary_ssm.dashboard import WorldController,make_server
    from canary_ssm.engine import load_engine_config
    from canary_ssm.evaluation_performance import one_http_step
    root=Path(__file__).resolve().parents[1]
    c=WorldController(load_engine_config(root/'configs/world_recovery.yaml'),state_dir=tmp_path)
    server=make_server(c,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        origin='http://127.0.0.1:'+str(server.server_port)
        assert one_http_step(c,origin,'same-measurement-id')>0 and c.engine.tick==1
        with pytest.raises(AssertionError,match='No simulation tick'):one_http_step(c,origin,'same-measurement-id')
        assert c.engine.tick==1
    finally:server.shutdown();server.server_close();c.close();thread.join()

def test_compact_delivery_regenerates_scores_inputs_truth_and_command_log(tmp_path,research):
    import json,scipy
    from canary_ssm.evaluation_archive import describe,replay
    models=research[3];settings={name:.003 for name in COMMON_METHODS};offset=17007
    freeze=dict(sources=source_hashes(),versions={'numpy':np.__version__,'scipy':scipy.__version__},offset=offset,models={'research':models},settings={'research':settings});freeze['freeze_hash']=digest(freeze);write(tmp_path/'development_freeze.json',freeze)
    job=('research','latent_effect','null-validation',0,offset,str(tmp_path/'research'),models,settings);null_job(job)
    folder=tmp_path/'research/inputs/null-validation/latent_effect/0';describe(folder,'research')
    (folder/'public/input.npz').unlink();(folder/'evaluator/truth.npz').unlink()
    assert replay(tmp_path,'research','latent_effect','null-validation',0,True)['identical']
    assert (folder/'public/input.npz').exists() and (folder/'evaluator/truth.npz').exists()
    original=(folder/'evaluator/producer.json').read_text();(folder/'evaluator/producer.json').write_text(original+' ')
    with pytest.raises(ValueError,match='provenance modified'):replay(tmp_path,'research','latent_effect','null-validation',0)
