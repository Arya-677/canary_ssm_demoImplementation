"""Development-only process-memory acceptance scenarios; never a detector benchmark."""
import argparse,csv,json,hashlib
from pathlib import Path
from .engine import EngineConfig,SimulationEngine
from .resources import ResourceConfig,ServiceWorkload
from .topology import Topology,DataCenter,Rack,Host,HostCapacity,ServiceReplica
from .telemetry_transport import TelemetryConfig
from .seeds import seed_for,REGISTRY_VERSION
from .resource_health import summarize

CASES={
    'cache_plateau':{'capacity':256,'rate':.5,'limit':40.,'arrivals':16.,'work':.05},
    'retention_no_latency_harm':{'capacity':100000,'rate':2.,'limit':None,'arrivals':16.,'work':.05},
    'pressure_latency_harm':{'capacity':128,'rate':2.,'limit':110.,'arrivals':32.,'work':.1},
    'oom':{'capacity':128,'rate':4.,'limit':None,'arrivals':32.,'work':.1},
    'recovery':{'capacity':128,'rate':4.,'limit':None,'arrivals':32.,'work':.05},
}

def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

def plot(csv_path,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd
    df=pd.read_csv(csv_path);df=df[df.host_id=='host-1']
    fig,axes=plt.subplots(4,1,figsize=(10,9),sharex=True,layout='constrained')
    axes[0].plot(df.simulated_seconds,df.memory_mb,label='Used MB');axes[0].plot(df.simulated_seconds,df.memory_headroom_mb,label='Headroom MB');axes[0].plot(df.simulated_seconds,df.memory_retained_mb,label='Retained MB')
    axes[1].plot(df.simulated_seconds,df.retained_added_mb_per_request,label='Allocated retained MB / processed request')
    axes[2].plot(df.simulated_seconds,df.sampled_latency_mean_ms,label='Request-sample mean latency (ms)');axes[2].plot(df.simulated_seconds,df.latency_proxy_ms,label='Analytical latency proxy (ms)')
    axes[3].step(df.simulated_seconds,df.process_restart_count,label='Process restarts');axes[3].step(df.simulated_seconds,df.oom_count,label='OOM exits')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[-1].set_xlabel('Simulated seconds');fig.suptitle(out.parent.name+' · simulated development fixture');fig.savefig(out,dpi=120);plt.close(fig)


def export_fixture(directory):
    out=Path(directory);results={};summary=[]
    for index,(name,case) in enumerate(CASES.items()):
        topology=Topology((DataCenter('dc'),),(Rack('rack','dc'),),tuple(Host(f'host-{i}','rack','dc',0,HostCapacity(1,case['capacity'],1000,1000)) for i in range(1,5)),tuple(ServiceReplica('service',f'replica-{i}',f'host-{i}','baseline') for i in range(1,5)))
        config=EngineConfig(topology,seed=seed_for('world_dev',index,20),resources=ResourceConfig((ServiceWorkload('service',case['arrivals'],work_core_seconds=case['work'],queue_limit=300,baseline_memory_mb=2,temporary_mb_per_request=.05),),host_baseline_memory_mb=1,shared_jitter=0),demo=True,telemetry=TelemetryConfig(enabled=True))
        e=SimulationEngine(config,run_id=f'memory-development-{index+1}')
        e.step(5)
        payload={'schema_version':1,'release_id':'candidate','service_id':'service','version':'3.0.0','creation_metadata':{'author':'development-fixture'},'behavior_manifest':{'schema_version':1,'profiles':[{'kind':'process_memory','retained_mb_per_request':case['rate'],'background_mb_per_second':0.,'retained_limit_mb':case['limit']}]}}
        e.operations_command('register_release',{'release':payload});plan=e.operations_command('preview',{'release_id':'candidate'});e.operations_command('deploy',{'plan_id':plan['plan_id']});e.step(60)
        if name=='recovery':e.operations_command('rollback',{});e.step(20)
        else:e.step(20)
        rows=[r for r in e.resource_model.host_trace if r['host_id']=='host-1'];exposed=[r for r in rows if r['tick']>=6]
        checks={'bounded_usage':all(0<=r['memory_mb']<=r['memory_capacity_mb'] and 0<=r['memory_peak_mb']<=r['memory_capacity_mb'] for r in rows),
            'queue_conservation':all(r['queue_start']+r['accepted']==r['queue_end']+r['completed']+r['dropped_restart']+r['dropped_unavailable_queued']+r['dropped_oom'] for r in e.resource_model.service_trace),
            'verified_replay':SimulationEngine.replay(e.artifact()).artifact()==e.artifact()}
        advisory_trace=[summarize(rows,r['simulated_seconds'],config.resources.health_policy)['advisories'][0] for r in rows]
        if name=='cache_plateau':checks.update(plateau=all(r['memory_retained_mb']==40 and r['request_retained_added_mb']==0 for r in rows[-10:]),no_oom=rows[-1]['oom_count']==0,warning_clears_at_plateau='observed_memory_growth_warning' not in advisory_trace[-1]['flags'])
        elif name=='retention_no_latency_harm':checks.update(growing=rows[-1]['memory_retained_mb']>rows[5]['memory_retained_mb'],no_latency_harm=all(r['sampled_latency_mean_ms']==1000 for r in exposed if r['completed']),no_pressure=all(r['pressure_slowdown_factor']==1 for r in exposed),observed_warning='observed_memory_growth_warning' in advisory_trace[-1]['flags'])
        elif name=='pressure_latency_harm':checks.update(pressure=any(r['pressure_slowdown_factor']<1 for r in exposed),latency_harm=any((r['sampled_latency_mean_ms'] or 0)>1000 for r in exposed),no_oom=rows[-1]['oom_count']==0)
        elif name=='oom':checks.update(oom_exit=rows[-1]['oom_count']>0,stays_down=rows[-1]['process_state']=='OOM',heap_freed_on_exit=rows[-1]['memory_retained_mb']==0)
        else:checks.update(oom_before_recovery=any(r['oom_count']>0 for r in rows),rollback_restart=rows[-1]['process_restart_count']==2,recovered=rows[-1]['process_state']=='RUNNING' and rows[-1]['memory_retained_mb']==0,latency_recovered=all(r['sampled_latency_mean_ms']==1000 for r in rows[-10:] if r['completed']))
        target=out/name;e.export_traces(target/'public/resource_trace');e.export_telemetry(target);e.save(target/'private/run.json')
        write(target/'public/resource_health.json',advisory_trace)
        write(target/'config.json',config.to_dict());write(target/'commands.json',e.log);write(target/'snapshot.json',e.snapshot())
        write(target/'evaluator/expectation.json',{'evaluator_only':True,'scenario':name,'definition':'Authored mechanism/expected qualitative outcome, never an inference input','expected':case})
        write(target/'manifest.json',{'generator_id':'resource-world-process-memory-v1','role':'development','seed':config.seed,'seed_registry_version':REGISTRY_VERSION,'seed_purpose':'world_dev','seed_family_index':20,'config_sha256':hashlib.sha256(json.dumps(config.to_dict(),sort_keys=True).encode()).hexdigest(),'simulated':True,'detector_status':'DETECTOR NOT CONNECTED','acceptance_only':True})
        plot(target/'public/resource_trace/hosts.csv',target/'memory_trace.png')
        results[name]={'checks':checks,'passed':all(checks.values())}
        summary.append({'scenario':name,'processed':sum(r['processed'] for r in exposed),'final_retained_mb':rows[-1]['memory_retained_mb'],'minimum_headroom_mb':min(r['memory_headroom_mb'] for r in exposed),'maximum_sampled_mean_ms':max([r['sampled_latency_mean_ms'] or 0 for r in exposed]),'oom_exits':rows[-1]['oom_count'],'restarts':rows[-1]['process_restart_count'],'acceptance_pass':all(checks.values())})
    with (out/'summary.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    result={'generator_id':'resource-world-process-memory-v1','role':'development','results':results,'passed':all(r['passed'] for r in results.values()),'not_a_detector_benchmark':True};write(out/'checks.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',default='examples/process_memory');r=export_fixture(p.parse_args().out);print(json.dumps(r,indent=2));raise SystemExit(not r['passed'])
