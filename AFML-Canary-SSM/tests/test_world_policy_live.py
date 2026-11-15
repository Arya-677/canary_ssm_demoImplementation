import ast
from pathlib import Path

import numpy as np
import pytest

from canary_ssm.world_policy_live import PublicPolicyPump, public_outputs
from canary_ssm.world_policy_fixture import simulate, FAMILY
from canary_ssm.seeds import seed_for
from canary_ssm.public_adjustment import AdjustmentPolicy, HealthyDevelopment, fit_development, serial
from canary_ssm.public_filter import GaussianEffects, observations_from_adjustment
from canary_ssm.policy_artifacts import freeze_development, calibrate
from canary_ssm.policy_control import world_protocol, world_simulator
from canary_ssm.policy_public import policy_records
from canary_ssm.first_crossing import rule
from canary_ssm.hierarchy import EffectParams
from canary_ssm.monitor_feed import validate


@pytest.fixture(scope='module')
def payload():
    e, r, sliced, panel = simulate(seed_for('world_smoke',12,FAMILY), 'public-producer-unit')
    seed = seed_for('world_smoke',13,FAMILY)
    _, _, _, dev = simulate(seed,'public-producer-unit-development',True)
    model = fit_development([HealthyDevelopment(dev,'development',True,'unit-dev')],r['canaries'],
        AdjustmentPolicy(policy_id='demo-live-unit-v1',group_by='rack_id',deviation_reason='Physical API unit fixture'))
    params = EffectParams(kind='indep')
    p = world_protocol(e,r,'rack_id')
    frozen = freeze_development(model.to_dict(),vars(params),world_simulator(e),p,
        [dict(run_id=dev.run_id,seed=seed,role='development',declared_healthy=True,public_sha256=dev.fingerprint())],rule(4))
    adjusted = model.prepare(panel,3660).transform(panel)
    data = observations_from_adjustment(serial(adjusted),model)
    output = GaussianEffects(params).run(data)
    trace = dict(run_id=panel.run_id,seed=e.config.seed,role='threshold-calibration',declared_null=True,
        hashes=frozen['hashes'],freeze_hash=frozen['freeze_hash'],exposure_time=3660.,
        records=policy_records(panel,adjusted,data,output,p),advisories=[])
    # One real numerical null supplies an intentionally insufficient test policy.
    # This fixture never pretends to be physical-world FAR qualification.
    return calibrate(frozen,[trace]), e, sliced, trace, output


def test_posterior_chart_and_policy_use_identical_actual_public_prefix(payload):
    policy, e, sliced, trace, output = payload
    scored, recording = public_outputs(policy,sliced)
    assert scored['records']==trace['records']
    validate(recording,e.world.snapshot()['hosts'])
    assert len(recording['frames'])==4
    last = recording['frames'][-1]
    np.testing.assert_array_equal(last['methods']['independent']['mean'],output['host_effect_mean'][-1])
    np.testing.assert_array_equal(last['methods']['independent']['covariance'],output['host_effect_covariance'][-1])
    assert last['latency_ms']==[next(w['latency_ms'] for w in sliced['windows'] if w['event_time']==3840 and w['host_id']==h['host_id']) for h in recording['host_roster']]


def test_read_only_polling_and_waiting_do_not_send_commands(payload):
    policy = payload[0]
    pump = PublicPolicyPump(policy)
    pump.get = lambda path: {'read_only':True}
    pump.command = lambda *args,**kwargs: pytest.fail('A read-only poll sent a command')
    assert pump.poll_once()['state']=='saved_replay_read_only'
    pump.get = lambda path: {'read_only':False,'snapshot':{}}
    assert pump.poll_once()['state']=='waiting_for_matching_attached_policy'


@pytest.mark.parametrize('url',['https://127.0.0.1','http://example.com','http://localhost/api','http://user@localhost','http://localhost/?x=1'])
def test_external_producer_rejects_nonlocal_origins(payload,url):
    with pytest.raises(ValueError):
        PublicPolicyPump(payload[0],url)


def test_live_producer_has_no_simulation_clock_or_truth_access():
    import canary_ssm.world_policy_live as live
    source = Path(live.__file__).read_text()
    tree = ast.parse(source)
    imports = [n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(x.split('.')[-1] in {'engine','simulate','metrics','telemetry_evaluator','monitor_evaluator','world_policy_fixture'} for x in imports)
    assert '/api/fault-lab' not in source
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('step','advance','_tick_once') for n in ast.walk(tree))


def test_api_clock_command_omits_operation_args(payload,monkeypatch):
    import io
    import json
    import canary_ssm.world_policy_live as live
    sent = []
    def fake_open(request,**kwargs):
        sent.append(json.loads(request.data))
        return io.BytesIO(b'{"status":"applied"}')
    monkeypatch.setattr(live,'urlopen',fake_open)
    pump = PublicPolicyPump(payload[0])
    pump.command({'run_id':'unit','epoch':0,'command_token':'unit-token'},'step')
    assert 'args' not in sent[0]
