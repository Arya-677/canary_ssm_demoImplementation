"""Small command-driven dashboard replay; no SSM or calibration claim."""
import argparse
import json
from dataclasses import replace
from pathlib import Path

from .dashboard import WorldController
from .engine import SimulationEngine,load_engine_config
from .seeds import seed_for


def export_fixture(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    config=load_engine_config(Path(__file__).resolve().parents[1]/'configs/world_console.yaml')
    c=WorldController(replace(config,seed=seed_for('world_smoke',0,32)),run_id='integrated-console-example-v1')
    def command(name,args=None):
        payload=dict(command_id='demo-'+str(c.revision),run_id=c.run_id,epoch=c.epoch,command=name)
        if args is not None:payload['args']=args
        return c.command(payload).get('result')
    def step(n):
        for _ in range(n):command('step')
    def write(name,value):
        (out/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    try:
        release=dict(schema_version=1,release_id='console-retention-v1',service_id='demo-service',version='3.0.0',
            creation_metadata={'author':'integrated-fixture','description':'Declared simulation only; source not executed'},
            behavior_manifest={'schema_version':1,'profiles':[{'kind':'process_memory','retained_mb_per_request':.5,'background_mb_per_second':0,'retained_limit_mb':None}]})
        command('register_release',{'release':release});write('release_manifest.json',release)
        args=dict(release_id=release['release_id'],per_rack=1,canary_fraction=.2,baseline_seconds=60,monitoring_seconds=120)
        preview=command('rollout_preview',args);r=command('rollout_create',args)
        command('rollout_baseline',{'rollout_id':r['rollout_id']});step(60)
        command('rollout_expose',{'rollout_id':r['rollout_id']});step(1)
        command('fault',dict(kind='network_degradation',scope='rack',target='rack-02',duration=5,severity=.5,seed=seed_for('world_smoke',1,32)))
        step(12);command('rollout_pause',{'rollout_id':r['rollout_id']});step(11)
        paused=c.export_run();write('paused_session.json',paused);command('history_save',{})
        command('rollout_rollback',{'rollout_id':r['rollout_id']});step(36)
        recovered=c.export_run();write('recovered_session.json',recovered);command('history_save',{})
        write('backend_history.json',c.archive.list())
        write('public_console_evidence.json',c.packet()['console'])
        write('command_outcomes.json',c.outcomes)
        c.engine.export_telemetry(out)
        c.engine.export_traces(out)
        checks={'preview_matches_frozen_cohort':preview['canaries']==r['canaries'],
            'paused_example':paused['engine']['rollout_state']['rollouts'][-1]['state']=='PAUSED',
            'manual_rollback':recovered['engine']['rollout_state']['rollouts'][-1]['state']=='ROLLED_BACK',
            'paused_replay_identical':SimulationEngine.replay(paused['engine']).artifact()==paused['engine'],
            'recovered_replay_identical':SimulationEngine.replay(recovered['engine']).artifact()==recovered['engine'],
            'honest_detector_state':c.packet()['console']['context']['model_id']=='DETECTOR NOT CONNECTED'}
        result=dict(fixture_id='integrated-console-example-v1',checks=checks,passed=all(checks.values()),
            scope='Short manual workflow fixture; baseline is not a research-eligible detector preperiod. No inference or calibration results.')
        write('checks.json',result);return result
    finally:c.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/integrated_console')
    r=export_fixture(p.parse_args().out);print(json.dumps(r,indent=2));raise SystemExit(not r['passed'])
