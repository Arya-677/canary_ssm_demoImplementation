"""Physical-world policy integration checks; no fabricated calibration evidence."""
from dataclasses import replace

import numpy as np
import pytest

from canary_ssm.world_policy_fixture import simulate, FAMILY, BASELINE, HORIZON, export_fixture
from canary_ssm.seeds import seed_for
from canary_ssm.policy_control import world_protocol, world_simulator
from canary_ssm.public_adjustment import AdjustmentPolicy, HealthyDevelopment, fit_development, serial
from canary_ssm.public_filter import GaussianEffects, observations_from_adjustment
from canary_ssm.hierarchy import EffectParams


@pytest.fixture(scope='module')
def sample():
    return simulate(seed_for('world_smoke', 10, FAMILY), 'physical-unit-null')


def test_actual_world_clock_full_minutes_and_frozen_exposure(sample):
    e, r, sliced, panel = sample
    assert e.tick == 64
    np.testing.assert_array_equal(panel.times, np.arange(1,65)*60)
    assert not panel.exposed[:60].any()
    index = {h:i for i,h in enumerate(panel.host_ids)}
    assert panel.exposed[60:, [index[h] for h in r['canaries']]].all()
    assert not panel.exposed[:, [index[h] for h in r['controls']]].any()
    p = world_protocol(e, r, 'rack_id')
    assert p['baseline_seconds']==BASELINE and p['horizon_windows']==HORIZON
    assert len(p['groups'])==4 and all(len(v)>=3 for v in p['groups'].values())
    assert all(x['arrival_time']<=3840 for x in e.telemetry.public_artifact()['records'])


def test_real_requests_and_capacity_bounds(sample):
    e, r, _, panel = sample
    records = e.telemetry.public_artifact()['records']
    assert sum(x['request_count'] for x in records)>0
    assert panel.observed.all() and panel.fresh.all()
    assert np.std(panel.y)>0 and np.std(panel.x)>0
    assert all(0<=h.usage.cpu_cores<=h.capacity.cpu_cores==1 for h in e.world.hosts)
    assert all(0<=h.usage.memory_mb<=h.capacity.memory_mb==8192 for h in e.world.hosts)
    assert world_simulator(e)['generator_id']=='resource-world-scenarios-v1'
    # There is no injected fault schedule or behavior label in public samples.
    assert not any({'fault_type','true_affected','injected_effect'} & row.keys() for row in records)


def test_seed_and_ordered_commands_reproduce_public_inputs(sample):
    e, _, _, panel = sample
    other, _, _, again = simulate(seed_for('world_smoke',10,FAMILY), 'physical-unit-null')
    assert again.fingerprint()==panel.fingerprint()
    assert other.log==e.log
    assert other.telemetry.public_artifact()==e.telemetry.public_artifact()


def test_healthy_development_and_future_perturbation(sample):
    _, r, _, panel = sample
    _, _, _, dev = simulate(seed_for('world_smoke',11,FAMILY), 'physical-unit-development', True)
    assert len(dev.times)==120 and not dev.exposed.any()
    model = fit_development([HealthyDevelopment(dev,'development',True,'unit-development')], r['canaries'],
        AdjustmentPolicy(policy_id='demo-physical-unit-v1', group_by='rack_id', deviation_reason='Physical unit fixture'))
    changed = np.array(panel.y)
    changed[61:] += 4  # after the first monitoring decision, no earlier effect
    later = replace(panel,y=changed)
    outputs = []
    for p in (panel,later):
        a = model.prepare(p,3660).transform(p)
        d = observations_from_adjustment(serial(a),model)
        outputs.append(GaussianEffects(EffectParams(kind='indep')).run(d))
    np.testing.assert_array_equal(outputs[0]['score'][:61], outputs[1]['score'][:61])


@pytest.mark.parametrize('kwargs', [{'B':0},{'n_validation':0},{'workers':0},{'workers':5}])
def test_fixture_rejects_unbounded_or_empty_runs(tmp_path,kwargs):
    with pytest.raises(ValueError):
        export_fixture(tmp_path,**kwargs)


def test_registered_world_policy_roles_are_disjoint():
    roles = [set(seed_for(role,i,FAMILY) for i in range(2000)) for role in
             ('world_dev','world_calibration','world_null_validation','world_test','world_smoke')]
    assert len(set.union(*roles))==10000
