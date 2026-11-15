"""Small deterministic lifecycle acceptance runs. No calibrated detector or benchmark."""
import argparse
import json
from pathlib import Path
from .engine import SimulationEngine,load_engine_config


def export_fixture(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True);checks={}
    for ending in ('rollback','promote','fail'):
        e=SimulationEngine(load_engine_config(Path(__file__).resolve().parents[1]/'configs/world_console.yaml'),run_id='fixed-rollout-'+ending)
        r=e.operations_command('rollout_create',{'release_id':'release-002','baseline_seconds':2,'monitoring_seconds':10})
        def action(a):return e.operations_command('rollout_'+a,{'rollout_id':r['rollout_id']})
        action('baseline');e.step(2);action('expose');e.step(2);action('pause');e.step(2);action('resume');e.step(2)
        action(ending);e.step()
        if ending=='fail':action('rollback');e.step()
        target=out/ending;target.mkdir(exist_ok=True);e.export_traces(target);e.export_telemetry(target);e.save(target/'run.json')
        (target/'rollouts.json').write_text(json.dumps(e.rollouts.snapshot(),indent=2)+'\n')
        checks[ending+'_verified_replay']=SimulationEngine.replay(e.artifact()).artifact()==e.artifact()
        expected='PROMOTED' if ending=='promote' else 'ROLLED_BACK'
        checks[ending+'_terminal_state']=e.rollouts.latest(r['service_id'])['state']==expected
        checks[ending+'_no_automatic_alert']=not any(x['alerts_enabled'] for x in e.rollouts.records())
    result={'fixture_id':'fixed-cohort-rack-class-v1','checks':checks,'passed':all(checks.values()),
        'acceptance_only':True,'note':'Short baseline/horizon exercises lifecycle only; no full-window detector score or calibration is claimed.'}
    (out/'checks.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/rollouts')
    result=export_fixture(p.parse_args().out);print(json.dumps(result,indent=2));raise SystemExit(not result['passed'])
