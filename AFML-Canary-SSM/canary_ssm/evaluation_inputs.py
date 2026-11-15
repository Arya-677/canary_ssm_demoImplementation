"""Offline study producers; public inputs and evaluator-only truth are separate."""
from dataclasses import asdict, replace
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from .engine import SimulationEngine, load_engine_config
from .simulate import SimConfig, simulate
from .public_adjustment import PublicPanel, panel_from_time_slice
from .scenario_registry import WORLD_GENERATOR_ID, ADDITIVE_GENERATOR_ID
from .seeds import seed_for

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=('healthy','shared_surge','host_fault','rack_outage','broad_release_harm','transient_harm',
 'memory_retention_no_latency','memory_retention_latency','contaminated_controls','missing_telemetry','recovery')
NULL_MIX=('healthy','shared_surge','host_fault','rack_outage','contaminated_controls','missing_telemetry')
PURPOSES={'development':'dev','threshold-calibration':'calibration','null-validation':'null_validation','final-test':'test','smoke':'smoke'}

def identity(generator,role,index,scenario='healthy'):
    if generator not in ('research','world') or role not in PURPOSES or scenario not in SCENARIOS:raise ValueError('Unknown generator/role/scenario')
    seed=seed_for(('additive_' if generator=='research' else 'world_')+PURPOSES[role],index,34+SCENARIOS.index(scenario))
    return seed,('r-' if generator=='research' else 'w-')+hashlib.sha256(str(seed).encode()).hexdigest()[:24]

def mixture_case(seed):
    return NULL_MIX[int(hashlib.sha256(('evaluation-null-mixture:'+str(seed)).encode()).hexdigest(),16)%len(NULL_MIX)]

def research_recipe(scenario,member):
    c=SimConfig(n_hosts=20,n_canary=8,n_classes=2,t_pre=180,t_post=120,shock=0.,n_affected=0,effect_pct=0.)
    if scenario=='shared_surge':c=replace(c,workload_step=float(np.log(1.4)),shock=float(np.log(1.15)))
    if scenario in ('host_fault','contaminated_controls'):c=replace(c,contam_frac=.25 if scenario=='host_fault' else .5,contam_scale=1.,effect_pct=6.,duration=45)
    if scenario=='rack_outage':c=replace(c,burst_len=30)
    if scenario=='missing_telemetry':c=replace(c,missing_rate=.2,late_frac=.15)
    if scenario in ('broad_release_harm','transient_harm','recovery') and member=='harm':
        c=replace(c,n_affected=8 if scenario=='broad_release_harm' else 1,effect_pct=3.,duration=5 if scenario=='transient_harm' else 35 if scenario=='recovery' else 120,onset_delay=5)
    return c

def research_member(seed,run_id,scenario,member,healthy_fit=False):
    c=research_recipe('healthy' if healthy_fit else scenario,member)
    p,t=simulate(c,seed,harm=True,rollout_id=run_id,pair_id=seed);p.meta={'late_delay':c.late_delay}
    return p,t,dict(generator_id=ADDITIVE_GENERATOR_ID,config=asdict(c),seed=seed,commands=[dict(command='original-additive-simulate',seed=seed)],rack_ids=['rack-'+str(i//2) for i in range(8)]+['rack-'+str(i//3) for i in range(12)],physical_mechanism_supported=scenario not in ('host_fault','rack_outage','memory_retention_no_latency','memory_retention_latency'))

def world_config(seed,scenario):
    c=load_engine_config(ROOT/'configs/world_policy_v1.yaml')
    service=replace(c.resources.services[0],temporary_mb_per_request=.1)
    resources=replace(c.resources,services=(service,),paired_exogenous=True)
    telemetry=replace(c.telemetry,missing_window_probability=.2,duplicate_probability=.1,delay_max_ticks=2) if scenario=='missing_telemetry' else c.telemetry
    return replace(c,seed=seed,resources=resources,telemetry=telemetry)

def world_member(seed,run_id,scenario,member,healthy_fit=False):
    c=world_config(seed,'healthy' if healthy_fit else scenario);e=SimulationEngine(c,run_id=run_id)
    profiles=[{'kind':'healthy'}]
    if member=='harm' and not healthy_fit:
        if scenario in ('broad_release_harm','transient_harm','recovery'):profiles=[{'kind':'slower_response','response_delay_ms':100.}]
        if scenario.startswith('memory_retention'):profiles=[{'kind':'process_memory','retained_mb_per_request':.005 if scenario.endswith('no_latency') else .02,'background_mb_per_second':0. if scenario.endswith('no_latency') else 1.,'retained_limit_mb':6800.}]
    release=dict(schema_version=1,release_id='candidate-v1',service_id='demo-service',version='7.0.0',creation_metadata={'author':'offline-evaluator'},behavior_manifest={'schema_version':1,'profiles':profiles})
    e.operations_command('register_release',{'release':release})
    r=e.operations_command('rollout_create',dict(release_id='candidate-v1',per_rack=2,canary_fraction=.4,baseline_seconds=3600,monitoring_seconds=3600))
    rid=r['rollout_id'];e.operations_command('rollout_baseline',{'rollout_id':rid});e.step(60)
    if not healthy_fit:e.operations_command('rollout_expose',{'rollout_id':rid})
    for tick in range(61,121):
        if tick==65 and not healthy_fit:
            faults=[]
            if scenario=='host_fault':faults=[('cpu_throttle','host',r['canaries'][0],.7)]
            if scenario=='rack_outage':faults=[('service_crash','rack','rack-01',.95)]
            if scenario=='shared_surge':faults=[('demand_surge','world','world',.8)]
            if scenario=='contaminated_controls':faults=[('cpu_throttle','host',h,.7) for h in r['controls'][:4]]
            for j,(kind,scope,target,severity) in enumerate(faults):e.operations_command('fault',dict(fault_id='background-'+str(j),kind=kind,scope=scope,target=target,duration=20,severity=severity,seed=seed))
        if tick==(70 if scenario=='transient_harm' else 95 if scenario=='recovery' else -1) and not healthy_fit:e.operations_command('rollout_rollback',{'rollout_id':rid})
        e.step()
    sliced=e.telemetry.store.time_slice(7200.);p=panel_from_time_slice(sliced,'demo-service')
    return p,e.telemetry_evaluator.artifact(),dict(generator_id=WORLD_GENERATOR_ID,config=c.to_dict(),seed=seed,commands=e.log,canaries=r['canaries'],controls=r['controls'],public_slice=sliced,exogenous=list(e.resource_model.exogenous_trace),resource_hosts=list(e.resource_model.host_trace),release_profiles=profiles,structural_release_null=profiles==[{'kind':'healthy'}],physical_mechanism_supported=True)

def generate(generator,role,index,scenario='healthy',member='harm',healthy_fit=False,seed_scenario=None):
    if role=='final-test':raise ValueError('Final-test inputs are sealed; use verified evaluator access')
    seed,_=identity(generator,role,index,seed_scenario or scenario)
    return generate_registered(generator,seed,('r-' if generator=='research' else 'w-')+hashlib.sha256((str(seed)+':'+member).encode()).hexdigest()[:24],scenario,member,healthy_fit)

def generate_registered(generator,seed,run_id,scenario,member,healthy_fit=False):
    return (research_member if generator=='research' else world_member)(seed,run_id,scenario,member,healthy_fit)

def save_public(generator,p,path):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    if generator=='research':p.save_npz(path/'input.npz');return
    np.savez_compressed(path/'input.npz',run_id=p.run_id,host_ids=p.host_ids,rack_ids=p.rack_ids,class_ids=p.class_ids,times=p.times,y=p.y,x=p.x,observed=p.observed,fresh=p.fresh,exposed=p.exposed,exposure_known=p.exposure_known,decision_times=p.decision_times,epoch=p.epoch)

def load_public(generator,path):
    if generator=='research':
        from .schema import Rollout
        return Rollout.load_npz(Path(path)/'input.npz')
    with np.load(Path(path)/'input.npz',allow_pickle=False) as z:return PublicPanel(str(z['run_id']),tuple(z['host_ids'].tolist()),tuple(z['rack_ids'].tolist()),tuple(z['class_ids'].tolist()),z['times'],z['y'],z['x'],z['observed'],z['fresh'],z['exposed'],z['exposure_known'],decision_times=z['decision_times'],epoch=int(z['epoch']))

def save_bundle(generator,p,truth,meta,directory,keep_raw=False):
    out=Path(directory);save_public(generator,p,out/'public');private=out/'evaluator';private.mkdir(exist_ok=True)
    if generator=='research':truth.save(private/'truth.npz')
    else:
        with gzip.open(private/'truth.json.gz','wt') as f:json.dump(truth,f,allow_nan=False)
    metadata={k:v for k,v in meta.items() if k not in ('public_slice','resource_hosts','exogenous')}
    (private/'producer.json').write_text(json.dumps(metadata,allow_nan=False)+'\n')
    if generator=='world' and keep_raw:
        for name,data in [('public/committed_slice.json.gz',meta['public_slice']),('public/resource_hosts.json.gz',meta['resource_hosts']),('evaluator/exogenous.json.gz',meta['exogenous'])]:
            with gzip.open(out/name,'wt') as f:json.dump(data,f,allow_nan=False)
