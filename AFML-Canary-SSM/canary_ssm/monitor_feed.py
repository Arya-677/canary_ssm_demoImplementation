"""Public detector-output adapter and backend playback; never consumes evaluator truth."""
import copy
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy.stats import norm

from .telemetry import digest,identifier

FORMAT='detector-monitor-v1'
KAPPA=math.log(1.02)
ROOT=Path(__file__).resolve().parents[1]/'examples/detector_dashboard'


def risk(mean,variance):
    if mean is None or variance is None:return None
    if variance==0:return float(mean>KAPPA)
    return float(norm.sf((KAPPA-mean)/math.sqrt(variance)))


def seal(artifact):
    result=copy.deepcopy(artifact);result.pop('artifact_sha256',None)
    result['artifact_sha256']=digest(result)
    return result


def validate(artifact,roster):
    """Strict bounded schema: posterior covariance enters once; risk computed here."""
    a=copy.deepcopy(artifact)
    fields={'format','artifact_id','version','replay_id','run_id','source_kind','host_roster','methods','exposure_time','simulated','frames','artifact_sha256'}
    if not isinstance(a,dict) or set(a)!=fields or a['format']!=FORMAT or a['simulated'] is not True:
        raise ValueError('Unsupported public detector artifact')
    expected=a.pop('artifact_sha256')
    if expected!=digest(a):raise ValueError('Detector artifact checksum mismatch')
    a['artifact_sha256']=expected
    for name in ('artifact_id','version','replay_id','run_id'):identifier(a[name],name)
    if a['source_kind'] not in ('simulated-metrics-replay','external-detector-stream'):
        raise ValueError('Declare replay or external detector stream')
    known={r['host_id']:r['rack_id'] for r in roster}
    hosts=a['host_roster'];n=len(hosts)
    if not 1<=n<=128 or len({h['host_id'] for h in hosts})!=n:raise ValueError('Invalid host roster')
    if any(set(h)!={'host_id','rack_id'} or known.get(h['host_id'])!=h['rack_id'] for h in hosts):
        raise ValueError('Detector IDs/parentage must match backend stable host IDs')
    methods=a['methods'];ids=[m['method_id'] for m in methods]
    if not 1<=len(methods)<=4 or len(set(ids))!=len(ids):raise ValueError('Invalid method roster')
    for m in methods:
        if set(m)!={'method_id','version','kind','settings'} or m['kind'] not in ('independent','hierarchical'):
            raise ValueError('Only declared posterior methods are accepted')
        identifier(m['method_id'],'method_id');identifier(m['version'],'method version')
        if not isinstance(m['settings'],dict) or set(m['settings'])-{'rho_g','rho_h','sd_g','sd_h','prior_group_sd','prior_deviation_sd','prior_sd'}:
            raise ValueError('Unrecognized method settings')
        if not all(type(v) in (int,float) and math.isfinite(v) for v in m['settings'].values()):raise ValueError('Invalid settings')
        for key,value in m['settings'].items():
            if key.startswith('rho_') and abs(value)>1 or key.startswith('sd_') and value<0 or key.startswith('prior_') and value<=0:raise ValueError('Invalid declared dynamics or prior')
    if type(a['exposure_time']) not in (int,float) or not math.isfinite(a['exposure_time']) or a['exposure_time']<0:raise ValueError('Invalid exposure')
    frames=a['frames']
    if not isinstance(frames,list) or len(frames)>1000 or len(frames)*n*n*len(ids)>1_000_000:
        raise ValueError('Detector history budget exceeded')
    last=last_decision=-1
    for f in frames:
        if set(f)!={'event_time','decision_time','input_sha256','observed','eligible','latency_ms','residual','quality_flags','methods'}:
            raise ValueError('Unknown frame fields; evaluator truth is not public')
        t,d=f['event_time'],f['decision_time']
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (t,d)) or t<=last or d<=last_decision or d<t:
            raise ValueError('Frames must be an ordered causal prefix')
        if not isinstance(f['input_sha256'],str) or len(f['input_sha256'])!=64:raise ValueError('Input lineage hash required')
        if type(f['eligible']) is not bool or len(f['observed'])!=n or any(type(v) is not bool for v in f['observed']):raise ValueError('Invalid masks')
        if f['eligible'] and sum(f['observed'])/n<.8:raise ValueError('Eligible frames require at least 80% observed canaries')
        if not isinstance(f['quality_flags'],list) or len(f['quality_flags'])>100 or any(not isinstance(v,str) or len(v)>160 for v in f['quality_flags']):raise ValueError('Invalid quality flags')
        for field in ('latency_ms','residual'):
            if len(f[field])!=n or any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in f[field]):raise ValueError('Invalid public values')
        if any(ok and (lat is None or residual is None) for ok,lat,residual in zip(f['observed'],f['latency_ms'],f['residual'])):raise ValueError('Fresh observations require latency and residual')
        if any(v is not None and v<=0 for v in f['latency_ms']):raise ValueError('Latency must be positive')
        if set(f['methods'])!=set(ids):raise ValueError('Same method outputs required for each replay minute')
        for mid in ids:
            p=f['methods'][mid]
            if set(p)!={'mean','covariance','group','deviation'}:raise ValueError('Invalid posterior fields')
            for field in ('mean','group','deviation'):
                if len(p[field])!=n or any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in p[field]):raise ValueError('Invalid component vector')
            if p['covariance'] is None:
                if any(v is not None for v in p['mean']):raise ValueError('Mean needs posterior covariance')
            else:
                cov=np.array(p['covariance'],float)
                if cov.shape!=(n,n) or not np.isfinite(cov).all() or not np.allclose(cov,cov.T,atol=1e-12) or np.linalg.eigvalsh(cov).min()<-1e-12 or np.any(np.diag(cov)<0) or any(v is None for v in p['mean']):raise ValueError('Full PSD effect covariance required')
                if t<a['exposure_time']:raise ValueError('Effect posterior cannot precede exposure')
                if next(m for m in methods if m['method_id']==mid)['kind']=='hierarchical':
                    if any(g is None or b is None or not math.isclose(mu,g+b,abs_tol=1e-9) for mu,g,b in zip(p['mean'],p['group'],p['deviation'])):raise ValueError('Group and deviation must reconstruct total effect')
        last,last_decision=t,d
    return a


class DetectorFeed:
    def __init__(self,roster,monotonic=time.monotonic):
        self.roster=roster;self.clock=monotonic;self.artifact=None;self.cursor=-1
        self.playing=False;self.speed=1.;self.next_at=None;self.last_received=None;self.mode='disconnected'

    def catalog(self):
        p=ROOT/'index.json'
        return json.loads(p.read_text()) if p.exists() else []

    def command(self,command,args):
        if not isinstance(args,dict):raise ValueError('Detector command args must be an object')
        if command=='monitor_load':
            if set(args)=={'sample_id'}:
                sample=next((s for s in self.catalog() if s['sample_id']==args['sample_id']),None)
                if sample is None:raise ValueError('Unknown detector sample')
                artifact=json.loads((ROOT/(sample['sample_id']+'.json')).read_text())
            elif set(args)=={'artifact'}:artifact=args['artifact']
            else:raise ValueError('Provide one sample_id or saved artifact')
            candidate=validate(artifact,self.roster)
            if not candidate['frames']:raise ValueError('Saved detector recording has no frames')
            self.artifact=candidate;self.cursor=len(candidate['frames'])-1;self.mode='recorded'
            self.playing=False;self.next_at=None;self.last_received=self.clock()
        elif command=='monitor_begin':
            if set(args)!={'metadata'}:raise ValueError('Provide stream metadata')
            candidate=validate(seal({**args['metadata'],'frames':[]}),self.roster)
            if candidate['source_kind']!='external-detector-stream':raise ValueError('Stream must declare its external source')
            self.artifact=candidate;self.cursor=-1;self.mode='stream';self.playing=False;self.last_received=self.clock()
        elif command=='monitor_append':
            if set(args)!={'frame'} or self.mode!='stream' or not self.artifact:raise ValueError('Begin a detector stream before appending')
            frame=args['frame'];frames=self.artifact['frames']
            if frames and frame==frames[-1]:return {'status':'duplicate_ignored'}
            candidate=seal({**self.artifact,'frames':frames+[frame]})
            self.artifact=validate(candidate,self.roster);self.cursor=len(self.artifact['frames'])-1;self.last_received=self.clock()
        else:
            if self.artifact is None or self.mode!='recorded':raise ValueError('Load a detector recording first')
            if command=='monitor_seek' and set(args)=={'index'} and type(args['index']) is int and 0<=args['index']<len(self.artifact['frames']):
                self.cursor=args['index'];self.playing=False
            elif command=='monitor_play' and not args:
                if self.cursor==len(self.artifact['frames'])-1:self.cursor=0
                self.playing=True;self.next_at=self.clock()+1/self.speed
            elif command=='monitor_pause' and not args:self.playing=False
            elif command=='monitor_speed' and set(args)=={'speed'} and type(args['speed']) in (int,float) and args['speed'] in (.5,1,2,4,8):self.speed=float(args['speed'])
            else:raise ValueError('Invalid detector playback command')
        return {'status':'applied','mode':self.mode,'cursor':self.cursor}

    def advance(self):
        if self.playing and self.next_at is not None and self.clock()>=self.next_at:
            self.cursor=min(self.cursor+1,len(self.artifact['frames'])-1)
            self.playing=self.cursor<len(self.artifact['frames'])-1;self.next_at=self.clock()+1/self.speed

    def snapshot(self,host_id=None):
        if self.artifact is None:return {'connected':False,'status':'DETECTOR NOT CONNECTED','catalog':self.catalog()}
        a=self.artifact;ids=[h['host_id'] for h in a['host_roster']]
        if host_id is not None and host_id not in ids:raise ValueError('Host is not monitored in this detector run')
        j=ids.index(host_id) if host_id else 0;host_id=ids[j]
        frames=a['frames'][:self.cursor+1];rows=[]
        for f in frames[-240:]:
            row={k:f[k] for k in ('event_time','decision_time','eligible','quality_flags')}
            row.update(observed=f['observed'][j],latency_ms=f['latency_ms'][j],residual=f['residual'][j],methods={})
            for mid,p in f['methods'].items():
                mean=p['mean'][j];var=p['covariance'][j][j] if p['covariance'] is not None else None
                sd=math.sqrt(max(0,var)) if var is not None else None
                host_risks=[risk(mu,p['covariance'][k][k]) for k,mu in enumerate(p['mean'])] if p['covariance'] is not None else []
                row['methods'][mid]={'mean':mean,'variance':var,'lower':mean-1.959963984540054*sd if sd is not None else None,
                    'upper':mean+1.959963984540054*sd if sd is not None else None,'risk':risk(mean,var),
                    'group':p['group'][j],'deviation':p['deviation'][j],
                    'release_score':max(host_risks) if host_risks and f['eligible'] else None}
            rows.append(row)
        state='waiting_for_frames'
        if rows:
            last=rows[-1]
            state='pre_exposure' if last['event_time']<a['exposure_time'] else 'observations_available' if last['eligible'] and last['observed'] else 'insufficient_data'
        age=self.clock()-self.last_received if self.last_received is not None else None
        if self.mode=='stream' and age is not None and age>5:state='stale_stream'
        metadata={k:copy.deepcopy(v) for k,v in a.items() if k!='frames'}
        return {'connected':True,'status':state,'mode':self.mode,'calibration':'UNCALIBRATED','policy':None,
            'host_id':host_id,'metadata':metadata,'cursor':self.cursor,'frame_count':len(a['frames']),
            'playing':self.playing,'speed':self.speed,'receipt_age_seconds':age,'rows':rows,
            'kappa':KAPPA,'catalog':self.catalog(),'release_score_label':'Maximum host risk · release score; not a joint release probability'}
