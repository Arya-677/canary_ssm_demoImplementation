"""Typed policy observations from the existing public adjustment/Gaussian pipeline."""
import math
import numpy as np
from .public_adjustment import serial
from .telemetry import digest


def policy_records(panel,adjusted,data,output,p):
    host_index={h:i for i,h in enumerate(panel.host_ids)};records=[]
    for t in np.flatnonzero(data.times>=data.exposure_time)[:p['horizon_windows']]:
        score=float(output['score'][t]);controls={g:[h for h in ids if adjusted['control_mask'][t,host_index[h]]] for g,ids in p['groups'].items()}
        records.append({'window_index':len(records),'event_time':float(data.times[t]),'decision_time':float(data.decision_times[t]),
            'score':score if math.isfinite(score) else None,'available':bool(data.available[t]),
            'fresh_canaries':[h for h,ok in zip(data.host_ids,data.observed[t]) if ok], 'fresh_controls':controls,
            'exposed_hosts':[h for h in panel.host_ids if panel.exposed[t,host_index[h]]],
            'quality_flags':list(adjusted['quality_flags'][t]),
            'input_sha256':digest(serial({'residual':adjusted['residuals'][t],'covariance':adjusted['measurement_covariance'][t],'observed':adjusted['observed'][t],'controls':adjusted['control_mask'][t]}))})
    return records


def score_slice(policy,sliced,service_id,exposure_time):
    """Reuse frozen preprocessing and the common Gaussian engine on public windows."""
    from .policy_artifacts import validate_policy
    from .public_adjustment import FrozenAdjustment,panel_from_time_slice
    from .public_filter import observations_from_adjustment,GaussianEffects
    from .hierarchy import EffectParams
    p=validate_policy(policy);f=p['frozen']
    if exposure_time!=f['protocol']['baseline_seconds']+60:raise ValueError('Exposure differs from the frozen protocol')
    model=FrozenAdjustment(f['preprocessing_model'])
    panel=panel_from_time_slice(sliced,service_id);adjusted=model.prepare(panel,exposure_time).transform(panel)
    data=observations_from_adjustment(serial(adjusted),model);settings=f['effect_settings']
    if settings.get('kind')=='grouped':
        from .public_hierarchy import GroupedParams,GroupedGaussianEffects,grouped_structure
        params=GroupedParams(**{k:v for k,v in settings.items() if k!='kind'});payload=model.to_dict();indices=[payload['host_ids'].index(h) for h in data.host_ids]
        labels=[payload['rack_ids'][i] if params.group_by=='rack_id' else payload['class_ids'][i] for i in indices]
        output=GroupedGaussianEffects(grouped_structure(data.host_ids,labels,params.group_by),params).run(data)
    else:output=GaussianEffects(EffectParams(**settings)).run(data)
    return {'run_id':panel.run_id,'hashes':{**f['hashes'],'policy_hash':p['policy_hash']},'records':policy_records(panel,adjusted,data,output,f['protocol'])}


def main():
    import argparse,json
    from pathlib import Path
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--policy',required=True);ap.add_argument('--slice',required=True);ap.add_argument('--service-id',required=True);ap.add_argument('--exposure-time',type=float,required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args();result=score_slice(json.loads(Path(a.policy).read_text()),json.loads(Path(a.slice).read_text()),a.service_id,a.exposure_time);Path(a.out).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({'run_id':result['run_id'],'records':len(result['records']),'output':a.out}))
if __name__=='__main__':main()
