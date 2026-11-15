"""Execute the real dashboard/API -> public scorer -> controller -> replay path."""
import argparse
import json
import threading
import shutil
from dataclasses import replace
from pathlib import Path

from .dashboard import WorldController, make_server
from .engine import SimulationEngine, load_engine_config
from .policy_fixture import write
from .seeds import seed_for
from .world_policy_fixture import CONFIG, FAMILY, BASELINE, HORIZON
from .world_policy_live import PublicPolicyPump


def export_demo(directory):
    root = Path(directory)
    policy = json.loads((root/'policy.json').read_text())
    validation = json.loads((root/'validation.json').read_text())
    results = {}
    slow = dict(schema_version=1,release_id='release-003',service_id='demo-service',version='1.2.0',
        creation_metadata={'author':'physical-smoke-fixture','created_at':'2026-11-15T00:00:00Z','description':'Declared simulation only; no source execution'},
        behavior_manifest={'schema_version':1,'profiles':[{'kind':'slower_response','response_delay_ms':120000}]})
    write(root/'demo_release.json',slow)
    # Predeclared smoke bundle, never calibration or utility/power evaluation.
    # Keep every HOLD/miss; show an alarm replay only if actual eligible data crosses.
    cases = [('healthy','release-001'),('combined_hold','release-002')]+[('slow_'+str(j),'release-003') for j in range(8)]
    for i, (name, release) in enumerate(cases):
        ctrl = WorldController(replace(load_engine_config(CONFIG),seed=seed_for('world_smoke',3+i,FAMILY)),
            run_id='physical-policy-http-'+name)
        server = make_server(ctrl,0)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        pump = PublicPolicyPump(policy,'http://127.0.0.1:'+str(server.server_port))
        def command(name,args=None):
            return pump.command(pump.get('/api/state'),name,args)
        target = root/('http_'+name)
        target.mkdir(exist_ok=True)
        try:
            if release=='release-003':
                command('register_release',{'release':slow})
            command('rollout_create',dict(release_id=release,baseline_seconds=BASELINE,monitoring_seconds=HORIZON*60))
            r = pump.get('/api/state')['snapshot']['rollout']['rollouts'][-1]
            rid = r['rollout_id']
            command('policy_attach',dict(rollout_id=rid,policy=policy,validation=validation,auto_rollback=False))
            waiting = pump.poll_once()
            command('rollout_baseline',{'rollout_id':rid})
            for _ in range(60):
                command('step')
            command('rollout_expose',{'rollout_id':rid})
            emitted = []
            for _ in range(HORIZON):
                command('step')
                before_poll_tick = pump.get('/api/state')['snapshot']['tick']
                emitted.append(pump.poll_once())
                duplicate = pump.poll_once()
                assert duplicate['emitted']==0
                assert pump.get('/api/state')['snapshot']['tick']==before_poll_tick
                b = pump.get('/api/state')['snapshot']['release_policy']['bindings'][-1]
                if b['decision']['state']=='ALARM_LATCHED':
                    command('step')
                    break
            state = pump.get('/api/state')
            row = state['snapshot']['rollout']['rollouts'][-1]
            paused = row['state']=='PAUSED'
            if paused:
                command('rollout_rollback',{'rollout_id':rid})
                command('step')
            saved = pump.get('/api/run')
            write(target/'session.json',saved)
            write(target/'detector.json',pump.get('/api/detectors/export'))
            write(target/'public_slice.json',pump.get('/api/telemetry?decision_time='+str(ctrl.engine.tick*60)))
            write(target/'command_outcomes.json',saved['outcomes'])
            # Truth is isolated as evaluator data and was never requested by pump.
            write(target/'evaluator_truth.json',pump.get('/api/fault-lab?developer=1'))
            results[name] = dict(public_poll_did_not_advance_world=True,duplicate_poll_emits_nothing=True,
                waiting_state=waiting['state'],observations_emitted=sum(x['emitted'] for x in emitted),
                automatic_pause=paused,manual_rollback=paused,
                final_state=ctrl.engine.rollouts.latest('demo-service')['state'],
                replay_identical=SimulationEngine.replay(saved['engine']).artifact()==saved['engine'],
                detector_frames=len(pump.get('/api/detectors/export')['frames']),
                policy_hash=policy['policy_hash'])
        finally:
            server.shutdown()
            server.server_close()
            ctrl.close()
            thread.join(timeout=3)
    results['alarm_example'] = next((name for name,_ in cases if name.startswith('slow_') and results[name]['automatic_pause']),None)
    if results['alarm_example']:
        shutil.copytree(root/('http_'+results['alarm_example']),root/'http_alarm',dirs_exist_ok=True)
    results['passed'] = (all(results[n]['replay_identical'] for n,_ in cases) and
        not results['healthy']['automatic_pause'] and results['alarm_example'] is not None and
        results[results['alarm_example']]['final_state']=='ROLLED_BACK')
    results['scope'] = 'Predeclared healthy, combined behavior and eight strong delay smoke seeds; all outcomes retained. Alarm replay aliases the first eligible crossing, not a power estimate.'
    write(root/'http_demo_checks.json',results)
    return results


if __name__=='__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',default='examples/world_policy')
    a = ap.parse_args()
    result = export_demo(a.out)
    print(json.dumps(result,indent=2))
    raise SystemExit(not result['passed'])
