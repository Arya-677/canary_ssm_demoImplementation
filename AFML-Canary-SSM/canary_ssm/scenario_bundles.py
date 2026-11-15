"""Tiny paired scenario exports. Manifests/truth are not inference inputs."""
from dataclasses import replace,asdict
import hashlib
import csv
import json
from pathlib import Path

import numpy as np

from .configuration import read_yaml_mapping
from .engine import SimulationEngine,load_engine_config
from .scenario_registry import (PairSpec,WORLD_GENERATOR_ID,ADDITIVE_GENERATOR_ID,
    ROLES,GENERATORS,register_bundles,registry_manifest,validate_registry)
from .seeds import REGISTRY_VERSION

ROOT=Path(__file__).resolve().parents[1]


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def world_recipe(pair,catalog_path=None):
    pair.validate()
    if pair.generator_id!=WORLD_GENERATOR_ID:raise ValueError('Wrong generator for resource-world recipe')
    path=Path(catalog_path or ROOT/'configs/world_scenario_catalog.yaml')
    catalog=read_yaml_mapping(path)
    if catalog.get('generator_id')!=WORLD_GENERATOR_ID or pair.family not in catalog.get('scenarios',{}):
        raise ValueError('Wrong world catalog generator/family')
    cfg=load_engine_config(path.parent/catalog['base_config_file'])
    cfg=replace(cfg,seed=pair.seed)
    if not cfg.resources.paired_exogenous:raise ValueError('World pairs require paired_exogenous configuration')
    ticks=catalog['ticks']
    if type(ticks) is not int or not 1<=ticks<=1000:raise ValueError('Tiny scenario horizon must be 1–1000 ticks')
    return cfg,ticks,catalog['scenarios'][pair.family]


def run_world_member(pair,member,catalog_path=None):
    run_id=pair.run_id(member);cfg,ticks,recipe=world_recipe(pair,catalog_path)
    e=SimulationEngine(cfg,run_id=run_id)
    for tick in range(1,ticks+1):
        if member=='harm':
            if recipe['intervention']=='platform' and tick==recipe['fault']['start_tick']:
                e.operations_command('fault',recipe['fault']|{'seed':pair.seed,'fault_id':f'scenario-{pair.pair_id}'})
            elif recipe['intervention']=='release':
                if tick==recipe['deploy_tick']:
                    plan=e.operations_command('preview',{'release_id':recipe['release_id'],'per_rack':1})
                    e.operations_command('deploy',{'plan_id':plan['plan_id']})
                if tick==recipe.get('rollback_tick'):
                    e.operations_command('rollback',{})
        e.step()
    return e


def intervention_label(pair,member,cfg,ticks,recipe):
    active=member=='harm' and recipe['intervention']!='none'
    onset=None;recovery=None
    if active:
        if recipe['intervention']=='platform':
            onset=(recipe['fault']['start_tick']-1)*cfg.tick_seconds
            recovery=(recipe['fault']['start_tick']+recipe['fault']['duration']-1)*cfg.tick_seconds
        else:
            onset=(recipe['deploy_tick']-1)*cfg.tick_seconds
            if 'rollback_tick' in recipe:recovery=(recipe['rollback_tick']-1)*cfg.tick_seconds
    return {'evaluator_only':True,'label_id':'operator-intervention-v1',
        'definition':'Scheduled intervention interval, not a measured harm threshold or research qualifying event',
        'onset':onset,'recovery':recovery,'horizon':ticks*cfg.tick_seconds,
        'intervention_kind':recipe['intervention'] if active else 'none',
        'right_censored':active and recovery is None}


def export_world_pair(pair,directory):
    pair.validate();directory=Path(directory);cfg,ticks,recipe=world_recipe(pair)
    runs={m:run_world_member(pair,m) for m in pair.members}
    a,b=runs['null'],runs['harm']
    onset=recipe.get('deploy_tick',recipe.get('fault',{}).get('start_tick',ticks+1))
    before=lambda e:[r for r in e.resource_model.host_trace if r['tick']<onset]
    exogenous=[list(e.resource_model.exogenous_trace) for e in runs.values()]
    checks={'same_exogenous_uniforms':exogenous[0]==exogenous[1],
        'same_exogenous_rng_state':all(a.artifact()['rng_states'][n]==b.artifact()['rng_states'][n]
                                      for n in ('workload','faults','host_noise','telemetry_loss')),
        'same_pre_intervention_resources':before(a)==before(b),
        'paired_exogenous_enabled':a.config.resources.paired_exogenous and b.config.resources.paired_exogenous,
        'pair_one_role':pair.validate()==pair and len({pair.run_id(m) for m in pair.members})==2,
        'verified_replay':all(SimulationEngine.replay(e.artifact()).artifact()==e.artifact() for e in runs.values())}
    diverged=a.resource_model.trace()!=b.resource_model.trace()
    checks['expected_resource_behavior']=not diverged if recipe['intervention']=='none' else diverged
    members={}
    for member,e in runs.items():
        out=directory/member
        e.export_telemetry(out)
        e.export_traces(out/'public/resource_trace')
        e.save(out/'run.json')
        write_json(out/'config.json',e.config.to_dict())
        write_json(out/'commands.json',e.log)
        write_json(out/'exogenous.json',list(e.resource_model.exogenous_trace))
        write_json(out/'evaluator/intervention_label.json',intervention_label(pair,member,cfg,ticks,recipe))
        manifest={'generator_id':WORLD_GENERATOR_ID,'pairing':'shared exogenous uniforms; endogenous routing/queues may diverge',
            'pair':pair.to_dict(),'member':member,'scenario_id':pair.run_id(member),
            'seed':pair.seed,'seed_registry_version':REGISTRY_VERSION,'config_sha256':file_hash(out/'config.json'),
            'command_log_sha256':file_hash(out/'commands.json'),'run_sha256':file_hash(out/'run.json'),
            'exogenous_sha256':file_hash(out/'exogenous.json'),'public_directory':'public','truth_directory':'evaluator',
            'data_sha256':{str(p.relative_to(out)):file_hash(p) for folder in ('public','evaluator') for p in sorted((out/folder).rglob('*')) if p.is_file()},
            'source_sha256':file_hash(__file__),'catalog_sha256':file_hash(ROOT/'configs/world_scenario_catalog.yaml'),
            'detector_status':'DETECTOR NOT CONNECTED'}
        write_json(out/'manifest.json',manifest);members[member]=manifest
    result={'pair_id':pair.pair_id,'family':pair.family,'role':pair.role,'generator_id':WORLD_GENERATOR_ID,
        'checks':checks,'passed':all(checks.values()),'endogenous_divergence':diverged,
        'additive_equality_required':False}
    write_json(directory/'checks.json',result)
    write_json(directory/'pair.json',{'pair':pair.to_dict(),'members':members})
    return result


def statistical_recipe(family):
    from .simulate import SimConfig
    if family not in GENERATORS[ADDITIVE_GENERATOR_ID]:raise ValueError('Unknown additive family')
    return SimConfig(family=family,n_hosts=10,n_canary=2,n_classes=2,t_pre=60,t_post=60,
        n_affected=1,duration={'additive_baseline':30,'additive_transient':5,'additive_persistent':60,'additive_recovery':20}[family],
        effect_pct=0 if family=='additive_baseline' else 3,decay_len=10 if family=='additive_recovery' else 0)


def export_statistical_pair(pair,directory):
    from .simulate import simulate
    pair.validate()
    if pair.generator_id!=ADDITIVE_GENERATOR_ID:raise ValueError('Wrong generator for additive recipe')
    directory=Path(directory);cfg=statistical_recipe(pair.family)
    generated={m:simulate(cfg,pair.seed,harm=m=='harm',rollout_id=pair.run_id(m),pair_id=pair.seed) for m in pair.members}
    null,nt=generated['null'];harm,ht=generated['harm']
    observed=harm.observed & null.observed
    error=(harm.y-null.y-ht.a-ht.spill)[observed]
    residual=float(np.max(np.abs(error))) if error.size else 0.0
    checks={'exact_additive_identity_to_float_precision':residual<=1e-12,
        'same_workload':np.array_equal(null.x,harm.x),'same_factor':np.array_equal(nt.factor,ht.factor),
        'same_noise':np.array_equal(nt.noise,ht.noise),'same_observed_mask':np.array_equal(null.observed,harm.observed),
        'same_arrival_masks':np.array_equal(null.decision_obs,harm.decision_obs),
        'same_request_counts':np.array_equal(null.request_count,harm.request_count)}
    for member,(roll,truth) in generated.items():
        out=directory/member;public=out/'public';private=out/'evaluator'
        public.mkdir(parents=True,exist_ok=True);private.mkdir(parents=True,exist_ok=True)
        roll.to_telemetry().to_csv(public/'records.csv',index=False)
        roll.save_npz(public/'rollout.npz');truth.save(private/'truth.npz')
        write_json(public/'metadata.json',roll.metadata())
        write_json(out/'config.json',asdict(cfg))
        write_json(out/'commands.json',[{'command':'simulate','seed':pair.seed,'harm':member=='harm'}])
        write_json(out/'manifest.json',{'generator_id':ADDITIVE_GENERATOR_ID,'pair':pair.to_dict(),'member':member,
            'scenario_id':pair.run_id(member),'seed':pair.seed,'seed_registry_version':REGISTRY_VERSION,
            'legacy_numeric_pair_id':pair.seed,
            'config_sha256':file_hash(out/'config.json'),'command_log_sha256':file_hash(out/'commands.json'),
            'simulate_sha256':file_hash(ROOT/'canary_ssm/simulate.py'),
            'data_sha256':{str(p.relative_to(out)):file_hash(p) for folder in ('public','evaluator') for p in sorted((out/folder).rglob('*')) if p.is_file()},
            'public_directory':'public','truth_directory':'evaluator'})
    result={'pair_id':pair.pair_id,'family':pair.family,'role':pair.role,'generator_id':ADDITIVE_GENERATOR_ID,
        'checks':checks,'passed':all(checks.values()),'max_abs_additive_residual':residual,'additive_equality_required':True}
    write_json(directory/'checks.json',result);return result


def export_suite(directory,role='smoke',pairs_per_family=1,include_statistical=True):
    if role not in ROLES:raise ValueError('Unknown scenario role')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    pairs=register_bundles(pairs_per_family);validate_registry(pairs)
    write_json(directory/'registry.json',registry_manifest(pairs_per_family))
    results=[]
    for pair in pairs:
        if pair.role!=role or (pair.generator_id==ADDITIVE_GENERATOR_ID and not include_statistical):continue
        out=directory/role/pair.generator_id/pair.family/f'pair-{pair.index:03d}'
        result=export_world_pair(pair,out) if pair.generator_id==WORLD_GENERATOR_ID else export_statistical_pair(pair,out)
        results.append(result)
    summary={'role_materialized':role,'registered_roles':list(ROLES),'results':results,
             'passed':all(r['passed'] for r in results),'note':'Functional pairing checks only; no detector/calibration/final-test performance is evaluated'}
    write_json(directory/'checks.json',summary)
    with (directory/'summary.csv').open('w',newline='') as stream:
        columns=['generator_id','role','family','pair_id','passed','additive_equality_required','endogenous_divergence','max_abs_additive_residual']
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        writer.writerows({k:r.get(k) for k in columns} for r in results)
    return summary


def verify_member(directory):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    pair=PairSpec.from_dict(manifest['pair'])
    if manifest['generator_id']!=pair.generator_id or manifest['scenario_id']!=pair.run_id(manifest['member']) or manifest['seed']!=pair.seed:
        raise ValueError('Member moved between roles, pairs or generators')
    for relative,key in (('config.json','config_sha256'),('commands.json','command_log_sha256'),('run.json','run_sha256'),('exogenous.json','exogenous_sha256')):
        if key in manifest and file_hash(directory/relative)!=manifest[key]:
            raise ValueError('Run configuration, commands or replay hash mismatch')
    for relative,expected in manifest['data_sha256'].items():
        path=(directory/relative).resolve()
        if directory not in path.parents or file_hash(path)!=expected:
            raise ValueError('Export data hash mismatch or unsafe path')
    metadata=json.loads((directory/'public/metadata.json').read_text())
    if metadata.get('run_id',metadata.get('rollout_id'))!=manifest['scenario_id']:
        raise ValueError('Public run identity mismatch')
    return True
