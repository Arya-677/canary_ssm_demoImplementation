"""Resource-world null calibration and causal controller demo; never a detector module.

The bounded 60-second tick model processes real simulated request cohorts. It is
not the additive research generator. Settings are predeclared before calibration;
validation is an audit only and never selects settings or seeds.
"""
import argparse
import csv
import hashlib
import json
import platform
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import scipy

from .engine import SimulationEngine, load_engine_config
from .first_crossing import rule
from .hierarchy import EffectParams
from .policy_artifacts import calibrate, freeze_development, sources, validate_nulls
from .policy_control import world_protocol, world_simulator
from .policy_fixture import write
from .policy_public import policy_records, score_slice
from .public_adjustment import (AdjustmentPolicy, FrozenAdjustment,
    HealthyDevelopment, fit_development, panel_from_time_slice, serial)
from .public_filter import GaussianEffects, observations_from_adjustment
from .seeds import REGISTRY_VERSION, seed_for
from .telemetry import digest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/world_policy_v1.yaml'
FAMILY = 30
HORIZON = 4
BASELINE = 3600
_MODEL = _FROZEN = None


def world(seed, run_id, release_id='release-001'):
    e = SimulationEngine(replace(load_engine_config(CONFIG), seed=seed), run_id=run_id)
    r = e.operations_command('rollout_create', dict(release_id=release_id,
        baseline_seconds=BASELINE, monitoring_seconds=60*HORIZON))
    return e, r


def simulate(seed, run_id, development=False):
    e, r = world(seed, run_id)
    e.operations_command('rollout_baseline', {'rollout_id': r['rollout_id']})
    e.step(120 if development else 60)
    if not development:
        e.operations_command('rollout_expose', {'rollout_id': r['rollout_id']})
        e.step(HORIZON)
    sliced = e.telemetry.store.time_slice(e.tick*60)
    return e, r, sliced, panel_from_time_slice(sliced, 'demo-service')


def _initialize(model, frozen):
    global _MODEL, _FROZEN
    _MODEL, _FROZEN = FrozenAdjustment(model), frozen


def _null(job):
    role, i = job
    purpose = 'world_calibration' if role == 'threshold-calibration' else 'world_null_validation'
    seed = seed_for(purpose, i, FAMILY)
    run_id = 'physical-policy-' + hashlib.sha256(str(seed).encode()).hexdigest()[:20]
    e, _, _, panel = simulate(seed, run_id)
    adjusted = _MODEL.prepare(panel, BASELINE+60).transform(panel)
    data = observations_from_adjustment(serial(adjusted), _MODEL)
    output = GaussianEffects(EffectParams(**_FROZEN['effect_settings'])).run(data)
    trace = dict(run_id=run_id, seed=seed, role=role, declared_null=True,
        hashes=_FROZEN['hashes'], freeze_hash=_FROZEN['freeze_hash'], exposure_time=BASELINE+60.,
        records=policy_records(panel, adjusted, data, output, _FROZEN['protocol']), advisories=[])
    lineage = dict(run_id=run_id, seed=seed, role=role, public_sha256=panel.fingerprint(),
        ordered_command_event_log=e.log, public_telemetry_sha256=digest(e.telemetry.public_artifact()))
    return trace, lineage


def export_fixture(directory, B=2000, n_validation=2000, workers=4):
    if any(type(x) is not int or not 1 <= x <= 5000 for x in (B, n_validation)):
        raise ValueError('Use 1–5000 independent null rollouts per role')
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('Use 1–4 laptop-bounded workers')
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    dev_seed = seed_for('world_dev', 0, FAMILY)
    e, r, sliced, panel = simulate(dev_seed, 'physical-policy-development-v1', True)
    prep = fit_development([HealthyDevelopment(panel, 'development', True, 'physical-policy-development-v1')],
        r['canaries'], AdjustmentPolicy(policy_id='demo-world-rack-policy-v1', group_by='rack_id',
            deviation_reason='Explicit rack-grouped physical demo; unchanged 60/80%/3 eligibility'))
    p = world_protocol(e, r, 'rack_id')
    # Freeze before any calibration null is generated. No hyperparameter grid is
    # searched here; the existing independent effect defaults are predeclared.
    frozen = freeze_development(prep.to_dict(), vars(EffectParams(kind='indep')), world_simulator(e), p,
        [dict(run_id=panel.run_id, seed=dev_seed, role='development', declared_healthy=True,
              public_sha256=panel.fingerprint())], rule(HORIZON, platform_incidents='disabled'))
    write(out/'frozen.json', frozen)
    write(out/'development_fit.json', prep.to_dict())
    write(out/'development_public_slice.json', sliced)
    write(out/'world_config.json', e.config.to_dict())
    write(out/'development_commands.json', e.log)
    write(out/'preregistration.json', dict(format='physical-world-policy-v1',
        generator_id='resource-world-scenarios-v1', config_sha256=digest(load_engine_config(CONFIG).to_dict()),
        sources=sources(['world_policy_fixture.py']), seed_registry_version=REGISTRY_VERSION,
        seed_family=FAMILY, B=B, n_validation=n_validation, H=HORIZON,
        freeze_hash=frozen['freeze_hash'], selection='Healthy development fit only; effect defaults predeclared',
        scope='All-healthy no-release null, shared demand jitter, complete telemetry, four-minute horizon. '
              'No random platform faults, loss/delay, resource advisory or incident producer.',
        versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__)))

    def generate(role, count):
        traces, lineage = [], []
        with ProcessPoolExecutor(max_workers=workers, initializer=_initialize,
                initargs=(prep.to_dict(), frozen)) as pool:
            for i, (trace, row) in enumerate(pool.map(_null, ((role, i) for i in range(count)), chunksize=4)):
                traces.append(trace)
                lineage.append(row)
                if (i+1) % 100 == 0:
                    print(json.dumps(dict(role=role, completed=i+1, total=count)), flush=True)
        write(out/(role+'_world_lineage.json'), lineage)
        return traces

    calibration = generate('threshold-calibration', B)
    policy = calibrate(frozen, calibration)
    write(out/'calibration_nulls.json', calibration)
    write(out/'policy.json', policy)
    # Independent validation is generated only after the policy is frozen. A failed
    # gate is retained and cannot trigger a second selection/calibration attempt.
    validation_traces = generate('null-validation', n_validation)
    validation = validate_nulls(policy, validation_traces)
    write(out/'validation_nulls.json', validation_traces)
    write(out/'validation.json', validation)
    for name, rows in [('null_maxima', policy['calibration_lineage']),
                       ('validation_outcomes', validation['outcomes'])]:
        with (out/(name+'.csv')).open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    with (out/'false_alerts.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['channel','events','n','rate','lower_95','upper_95'])
        for channel, stats in validation['rates'].items():
            w.writerow([channel,stats['events'],stats['n'],stats['rate'],*stats['exact_binomial_95_interval']])
    result = dict(fixture_id='physical-world-first-crossing-v1', B=B, n_validation=n_validation,
        gate=validation['gate'], rates=validation['rates'], policy_hash=policy['policy_hash'],
        validation_hash=validation['validation_hash'], freeze_hash=frozen['freeze_hash'],
        no_retuning=validation['no_retuning'], noise_diagnostics=prep.to_dict()['noise_diagnostics'],
        resource_world_compatible=True, automatic_attachment_qualified=validation['gate']['status']=='PASS')
    write(out/'checks.json', result)
    return result


def verify_member(directory, role, index):
    """Regenerate a null from its saved seed/config/log and re-score public data."""
    out = Path(directory)
    frozen = json.loads((out/'frozen.json').read_text())
    model = json.loads((out/'development_fit.json').read_text())
    rows = json.loads((out/(role+'_world_lineage.json')).read_text())
    traces = json.loads((out/('calibration_nulls.json' if role=='threshold-calibration' else 'validation_nulls.json')).read_text())
    _initialize(model, frozen)
    trace, row = _null((role, index))
    return dict(role=role, index=index, seed=row['seed'], identical=trace==traces[index] and row==rows[index])


def controller_demo(directory):
    """Real public observations drive a compatible backend policy, then manual rollback."""
    out = Path(directory)
    policy = json.loads((out/'policy.json').read_text())
    validation = json.loads((out/'validation.json').read_text())
    results = {}
    for name, release in [('healthy','release-001'), ('candidate','release-002')]:
        target = out/('demo_'+name)
        target.mkdir(exist_ok=True)
        e, r = world(seed_for('world_smoke', 1 if name=='healthy' else 2, FAMILY),
                     'physical-policy-demo-'+name, release)
        rid = r['rollout_id']
        e.operations_command('policy_attach', dict(rollout_id=rid, policy=policy, validation=validation, auto_rollback=False))
        e.operations_command('rollout_baseline', {'rollout_id':rid})
        e.step(60)
        e.operations_command('rollout_expose', {'rollout_id':rid})
        emitted = []
        for _ in range(HORIZON):
            e.step()
            sliced = e.telemetry.store.time_slice(e.tick*60)
            scored = score_slice(policy, sliced, 'demo-service', BASELINE+60)
            record = scored['records'][-1]
            outcome = e.operations_command('policy_observe', dict(rollout_id=rid,
                record=record, hashes=scored['hashes'], run_id=e.run_id, monitoring_epoch=r['monitoring_epoch']))
            emitted.append(dict(record=record, outcome=outcome))
            if outcome['first_crossing']:
                e.step()  # queued automatic PAUSE applies at the next simulated tick
                break
        before = e.rollouts.latest('demo-service')['state']
        automatic_pause = before=='PAUSED'
        if automatic_pause:
            e.operations_command('rollout_rollback', {'rollout_id':rid})
            e.step()
        e.export_traces(target)
        e.export_telemetry(target)  # injected truth is saved separately by this exporter
        e.save(target/'run.json')
        write(target/'policy_observations.json', emitted)
        write(target/'public_slice.json', e.telemetry.store.time_slice(e.tick*60))
        results[name] = dict(automatic_pause=automatic_pause, state_before_manual_action=before,
            final_state=e.rollouts.latest('demo-service')['state'], auto_rollback=False,
            replay_identical=SimulationEngine.replay(e.artifact()).artifact()==e.artifact())
    write(out/'controller_demo.json', results)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['calibrate','demo','verify'])
    ap.add_argument('--out', default='examples/world_policy')
    ap.add_argument('--B', type=int, default=2000)
    ap.add_argument('--n-validation', type=int, default=2000)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--role', choices=['threshold-calibration','null-validation'], default='threshold-calibration')
    ap.add_argument('--index', type=int, default=0)
    a = ap.parse_args()
    result = (export_fixture(a.out,a.B,a.n_validation,a.workers) if a.command=='calibrate' else
              controller_demo(a.out) if a.command=='demo' else verify_member(a.out,a.role,a.index))
    print(json.dumps(result, indent=2))


if __name__=='__main__':
    main()
