"""Tiny declared-release dynamics/immutability checks; not a detector benchmark."""
import argparse
import csv
import json
from pathlib import Path
from dataclasses import replace

from .engine import SimulationEngine,load_engine_config
from .releases import ReleaseRegistry,example_payloads
from .seeds import seed_for


def export_fixture(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    examples=example_payloads();registry=ReleaseRegistry(['demo-service'])
    for payload in examples:
        r=registry.register(payload,0)
        (out/f'{r.release_id}.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out/'immutable_records.json').write_text(json.dumps([r.to_dict() for r in registry.records()],indent=2)+'\n')
    cases={'healthy':[{'kind':'healthy'}],
        'cpu':[{'kind':'extra_cpu_work','work_multiplier':8}],
        'memory':[{'kind':'retained_memory_leak','retained_mb_per_completion':2}],
        'errors':[{'kind':'increased_error_probability','error_probability':1}],
        'delay':[{'kind':'slower_response','response_delay_ms':2000}],
        'composed':examples[1]['behavior_manifest']['profiles']}
    checks={};summary=[]
    for index,(name,profiles) in enumerate(cases.items()):
        config=load_engine_config(root/'configs/world_console.yaml')
        config=replace(config,seed=seed_for('world_smoke',200,2))
        e=SimulationEngine(config,run_id=f'release-fixture-{index+1}')
        payload={'schema_version':1,'release_id':f'release-case-{index+1}','service_id':e.demo.service_id,
            'version':f'2.0.{index}','creation_metadata':{'author':'acceptance-fixture'},'behavior_manifest':{'schema_version':1,'profiles':profiles}}
        e.operations_command('register_release',{'release':payload})
        plan=e.operations_command('preview',{'release_id':payload['release_id']});e.operations_command('deploy',{'plan_id':plan['plan_id']});e.step(8)
        rows=[row for row in e.resource_model.host_trace if row['host_id'] in plan['canaries']]
        target=out/name;target.mkdir(exist_ok=True);e.export_traces(target);e.save(target/'run.json')
        checks[name]=SimulationEngine.replay(e.artifact()).artifact()==e.artifact()
        if name=='errors':checks[name] &= sum(r['errors'] for r in rows)==sum(r['completed'] for r in rows)>0
        if name=='memory':checks[name] &= any(r['memory_retained_mb']>0 for r in rows)
        if name=='delay':checks[name] &= any(r['pending_response_count']>0 for r in rows)
        summary.append([name,len(rows),sum(r['processed'] for r in rows),sum(r['completed'] for r in rows),sum(r['errors'] for r in rows),max(r['memory_retained_mb'] for r in rows),max(r['pending_response_count'] for r in rows),bool(checks[name])])
    with (out/'summary.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['case','canary_host_rows','processed','responded','errors','max_retained_mb','max_pending_responses','acceptance_pass']);w.writerows(summary)
    result={'fixture_id':'declared-release-response-v1','checks':checks,'passed':all(checks.values()),'acceptance_only':True,'seed':seed_for('world_smoke',200,2),'executed_source':False}
    (out/'checks.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/release_registry')
    result=export_fixture(p.parse_args().out);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
