"""Public-only external producer for the existing local dashboard API.

Never advances the world or reads Fault Lab/evaluator endpoints. The backend
owns the clock and validated policy actions. Polling can reconnect to its saved
observation count; duplicate command IDs make uncertain POST retries idempotent.
"""
import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import numpy as np

from .hierarchy import EffectParams
from .monitor_feed import seal
from .policy_artifacts import validate_policy
from .policy_public import policy_records
from .public_adjustment import FrozenAdjustment, panel_from_time_slice, serial
from .public_filter import GaussianEffects, observations_from_adjustment
from .telemetry import digest


def public_outputs(policy, sliced):
    p = validate_policy(policy)
    f = p['frozen']
    if f['effect_settings']['kind']!='indep':
        raise ValueError('This versioned producer supports the independent world-policy artifact only')
    model = FrozenAdjustment(f['preprocessing_model'])
    panel = panel_from_time_slice(sliced,'demo-service')
    exposure = f['protocol']['baseline_seconds']+60
    adjusted = model.prepare(panel,exposure).transform(panel)
    data = observations_from_adjustment(serial(adjusted),model)
    output = GaussianEffects(EffectParams(**f['effect_settings'])).run(data)
    records = policy_records(panel,adjusted,data,output,f['protocol'])
    raw = {(w['event_time'],w['host_id']):w['latency_ms'] for w in sliced['windows']
           if w['service_id']=='demo-service'}
    frames = []
    for record in records:
        t = int(np.searchsorted(data.times,record['event_time']))
        frames.append(dict(event_time=record['event_time'],decision_time=record['decision_time'],
            input_sha256=record['input_sha256'],observed=serial(data.observed[t]),
            eligible=bool(data.eligible[t]),latency_ms=[raw.get((record['event_time'],h)) for h in data.host_ids],
            residual=serial(data.residuals[t]),quality_flags=record['quality_flags'],
            methods={'independent':dict(mean=serial(output['host_effect_mean'][t]),
                covariance=serial(output['host_effect_covariance'][t]),group=[0.]*len(data.host_ids),
                deviation=serial(output['host_effect_mean'][t]))}))
    index = {h:i for i,h in enumerate(panel.host_ids)}
    artifact = seal(dict(format='detector-monitor-v1',artifact_id='physical-policy-'+p['policy_hash'][:16],
        version='physical-public-producer-v1',replay_id=panel.run_id,run_id=panel.run_id,
        source_kind='external-detector-stream',host_roster=[dict(host_id=h,rack_id=panel.rack_ids[index[h]]) for h in data.host_ids],
        methods=[dict(method_id='independent',version=p['policy_hash'],kind='independent',
            settings={'prior_sd':f['effect_settings']['prior_sd']})],
        exposure_time=exposure,simulated=True,frames=frames))
    return dict(run_id=panel.run_id,hashes={**f['hashes'],'policy_hash':p['policy_hash']},records=records), artifact


class PublicPolicyPump:
    def __init__(self, policy, url='http://127.0.0.1:8765'):
        parsed = urlsplit(url)
        if parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1') or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Use the local dashboard HTTP origin')
        self.policy = validate_policy(policy)
        self.url = url.rstrip('/')

    def get(self,path):
        with urlopen(self.url+path,timeout=15) as response:
            return json.load(response)

    def command(self,state,name,args=None,identity=None):
        payload = dict(command_id=identity or str(uuid.uuid4()),run_id=state['run_id'],
            epoch=state['epoch'],command=name)
        if args is not None:
            payload['args'] = args
        request = Request(self.url+'/api/commands',data=json.dumps(payload,allow_nan=False).encode(),
            headers={'Content-Type':'application/json','X-World-Token':state['command_token']},method='POST')
        with urlopen(request,timeout=30) as response:
            return json.load(response)

    def poll_once(self):
        state = self.get('/api/state')
        if state['read_only']:
            return {'state':'saved_replay_read_only','emitted':0}
        snapshot = state['snapshot']
        bindings = snapshot.get('release_policy',{}).get('bindings',[])
        binding = next((b for b in bindings if b['active'] and b['policy_hash']==self.policy['policy_hash']),None)
        if binding is None:
            return {'state':'waiting_for_matching_attached_policy','emitted':0}
        row = next(r for r in snapshot['rollout']['rollouts'] if r['rollout_id']==binding['rollout_id'])
        if not row['evaluation_active'] or row['exposure_tick'] is None:
            return {'state':'waiting_for_exposure_or_evaluation_closed','emitted':0}
        feed = self.get('/api/detectors')
        same_feed = feed.get('mode')=='stream' and feed.get('metadata',{}).get('run_id')==state['run_id'] and feed.get('metadata',{}).get('artifact_id')=='physical-policy-'+self.policy['policy_hash'][:16]
        frame_count = feed['frame_count'] if same_feed else 0
        first = min(binding['observations'],frame_count)
        now = snapshot['simulated_seconds']
        emitted = 0
        for i in range(first,self.policy['frozen']['protocol']['horizon_windows']):
            deadline = row['first_decision_time']+i*60
            if deadline>now:
                break
            sliced = self.get('/api/telemetry?decision_time='+str(deadline))
            scored, artifact = public_outputs(self.policy,sliced)
            record, frame = scored['records'][-1],artifact['frames'][-1]
            if not same_feed:
                self.command(state,'monitor_begin',{'metadata':{k:v for k,v in artifact.items() if k not in ('frames','artifact_sha256')}})
                same_feed = True
            identity = digest([state['run_id'],state['epoch'],row['monitoring_epoch'],self.policy['policy_hash'],i])
            self.command(state,'policy_observe',dict(rollout_id=row['rollout_id'],record=record,
                hashes=scored['hashes'],run_id=state['run_id'],monitoring_epoch=row['monitoring_epoch']),identity)
            self.command(state,'monitor_append',{'frame':frame},'frame-'+identity)
            emitted += 1
        return {'state':'connected','emitted':emitted,'run_id':state['run_id']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--policy',required=True)
    ap.add_argument('--url',default='http://127.0.0.1:8765')
    ap.add_argument('--interval',type=float,default=.5)
    ap.add_argument('--max-polls',type=int,default=0,help='0 continues until interrupted')
    a = ap.parse_args()
    if not .1<=a.interval<=5 or a.max_polls<0:
        ap.error('Use interval .1–5 seconds and nonnegative max-polls')
    pump = PublicPolicyPump(json.loads(Path(a.policy).read_text()),a.url)
    count = 0
    while not a.max_polls or count<a.max_polls:
        try:
            print(json.dumps(pump.poll_once()),flush=True)
        except (OSError,ValueError,KeyError) as exc:
            print(json.dumps({'state':'disconnected_or_rejected','error':str(exc)}),flush=True)
        count += 1
        if not a.max_polls or count<a.max_polls:
            time.sleep(a.interval)


if __name__=='__main__':
    main()
