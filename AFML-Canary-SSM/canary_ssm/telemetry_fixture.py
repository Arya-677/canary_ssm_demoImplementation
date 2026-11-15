"""Deterministic public telemetry, private evaluator labels and causal replay fixture."""
from pathlib import Path
import argparse
import json
from .engine import SimulationEngine,load_engine_config
from .telemetry import causal_time_slice


def export_fixture(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    cfg=load_engine_config(Path(__file__).resolve().parents[1]/'configs/world_telemetry.yaml')
    e=SimulationEngine(cfg,run_id='telemetry-fixture')
    e.operations_command('fault',{'fault_id':'fixture-cpu','kind':'cpu_throttle','scope':'host',
        'target':'host-01-01','start_tick':125,'duration':10,'severity':.75,'seed':10000})
    e.step(120)
    earlier=e.telemetry.store.time_slice(60)
    e.step(120)
    e.export_telemetry(directory)
    e.save(directory/'run.json')
    public=e.telemetry.public_artifact();rows=public['windows']
    roster=public['roster']
    offline=causal_time_slice(public['records'],e.run_id,roster,240,interval_seconds=cfg.tick_seconds)
    replay=SimulationEngine.replay(e.artifact())
    text=json.dumps(public)
    checks={
        'first_minute_late_and_masked':all(not r['observed'] and r['latency_ms'] is None for r in rows if r['window_index']==0),
        'second_minute_missing':all(r['coverage']==0 and not r['observed'] for r in rows if r['window_index']==1),
        'recovery_fresh':all(r['observed'] for r in rows if r['window_index']==3),
        'duplicates_deduplicated':e.telemetry.store.counters['duplicates']>0,
        'late_records_received_but_excluded':e.telemetry.store.counters['late']>0,
        'earlier_decision_unchanged':e.telemetry.store.time_slice(60)==earlier,
        'offline_online_inputs_equal':offline['windows']==rows,
        'no_truth_in_public':all(k not in text for k in ('fault_type','true_affected','injected_latent_effect','fixture-cpu')),
        'evaluator_labels_separate':any(r['true_affected'] and r['fault_type'] for r in e.telemetry_evaluator.rows),
        'replay':replay.artifact()==e.artifact(),
        'latency_statistics_consistent':all(r['request_count']==0 or abs(r['latency_ms']*r['request_count']-r['latency_sum_ms'])<1e-6 for r in rows)}
    result={'synthetic':True,'ticks':e.tick,'public_records':len(public['records']),'monitoring_rows':len(rows),
            'checks':checks,'passed':all(checks.values())}
    (directory/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='examples/public_telemetry')
    result=export_fixture(parser.parse_args().out)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
