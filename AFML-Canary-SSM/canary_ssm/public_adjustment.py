"""Development-frozen workload/factor adjustment using public causal windows only."""
from dataclasses import dataclass,asdict
import copy
import hashlib
import json
from pathlib import Path
import numpy as np

from .factor import (_ols_host,fit_rank_one_controls,project_rank_one_controls,reference_covariance,
                     MIN_PRE_OBS,MIN_CONTROLS_PER_CLASS,MIN_CANARY_FRAC)
from .preprocess import fit_ar_class
from .telemetry import digest,identifier,integer

FEATURE_ID='public-logmean-log1pworkload-v1'
MODEL_ID='development-frozen-control-adjustment-v1'


def serial(value):
    if isinstance(value,np.ndarray):return serial(value.tolist())
    if isinstance(value,(float,np.floating)) and not np.isfinite(value):return None
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:serial(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [serial(v) for v in value]
    return value


@dataclass(frozen=True)
class AdjustmentPolicy:
    policy_id:str='research-eligibility-v1'
    group_by:str='class_id'
    factor_rank:int=1
    min_canary_fraction:float=MIN_CANARY_FRAC
    min_controls:int=MIN_CONTROLS_PER_CLASS
    min_pre_observations:int=MIN_PRE_OBS
    deviation_reason:str=''

    def __post_init__(self):
        if self.group_by not in ('class_id','rack_id') or type(self.factor_rank) is not int or self.factor_rank not in (0,1):
            raise ValueError('Use class/rack grouping and factor rank 0 or 1')
        if type(self.min_controls) is not int or self.min_controls<1 or type(self.min_pre_observations) is not int or self.min_pre_observations<1:
            raise ValueError('Invalid control/pre-observation counts')
        if type(self.min_canary_fraction) not in (int,float) or not 0<self.min_canary_fraction<=1:
            raise ValueError('Invalid canary fraction')
        changed=self.min_canary_fraction!=MIN_CANARY_FRAC or self.min_controls!=MIN_CONTROLS_PER_CLASS or self.min_pre_observations!=MIN_PRE_OBS
        if self.policy_id=='research-eligibility-v1':
            if changed or self.group_by!='class_id':raise ValueError('Research policy defaults are frozen')
        elif not self.policy_id.startswith('demo-') or not self.deviation_reason.strip():
            raise ValueError('A separately versioned demo policy needs an explicit reason')


@dataclass(frozen=True)
class PublicPanel:
    run_id:str
    host_ids:tuple
    rack_ids:tuple
    class_ids:tuple
    times:np.ndarray
    y:np.ndarray
    x:np.ndarray
    observed:np.ndarray
    fresh:np.ndarray
    exposed:np.ndarray
    exposure_known:np.ndarray
    feature_id:str=FEATURE_ID
    epoch:int=0
    decision_times:np.ndarray|None=None

    def __post_init__(self):
        for name in ('host_ids','rack_ids','class_ids'):object.__setattr__(self,name,tuple(getattr(self,name)))
        n=len(self.host_ids)
        identifier(self.run_id,'run_id');integer(self.epoch,'epoch')
        for h in self.host_ids:identifier(h,'host_id')
        for r in self.rack_ids:identifier(r,'rack_id')
        for c in self.class_ids:integer(c,'class_id')
        if not 1<=n<=256 or len(set(self.host_ids))!=n or len(self.rack_ids)!=n or len(self.class_ids)!=n:
            raise ValueError('Invalid public host roster')
        times=np.array(self.times,dtype=float,copy=True)
        if times.ndim!=1 or not 1<=len(times)<=10000 or not np.isfinite(times).all() or (np.diff(times)<=0).any():
            raise ValueError('Times must be finite and strictly increasing')
        if np.any(times<60) or not np.allclose(times/60,np.round(times/60),rtol=0,atol=1e-9) or not np.allclose(np.diff(times),60,rtol=0,atol=1e-9):
            raise ValueError('Use a complete minute grid with explicit missing rows; never compact gaps')
        times.setflags(write=False);object.__setattr__(self,'times',times)
        deadlines=np.array(times if self.decision_times is None else self.decision_times,dtype=float,copy=True)
        if deadlines.shape!=times.shape or not np.isfinite(deadlines).all() or np.any(deadlines<times) or (np.diff(deadlines)<=0).any():
            raise ValueError('Invalid decision-time availability grid')
        deadlines.setflags(write=False);object.__setattr__(self,'decision_times',deadlines)
        for name in ('y','x','observed','fresh','exposed','exposure_known'):
            original=np.asarray(getattr(self,name))
            if name not in ('y','x') and original.dtype.kind!='b':raise ValueError('Observation masks must be boolean')
            value=np.array(original,dtype=float if name in ('y','x') else bool,copy=True)
            if value.shape!=(len(times),n):raise ValueError('Panel shape mismatch')
            value.setflags(write=False);object.__setattr__(self,name,value)
        if np.any(self.observed & (~np.isfinite(self.y)|~np.isfinite(self.x))):raise ValueError('Observed values must be finite')
        if self.feature_id!=FEATURE_ID:raise ValueError('Wrong feature convention')

    def groups(self,policy):
        return tuple(str(x) for x in (self.class_ids if policy.group_by=='class_id' else self.rack_ids))

    def fingerprint(self):
        return digest(serial({'run_id':self.run_id,'epoch':self.epoch,'hosts':self.host_ids,'racks':self.rack_ids,'classes':self.class_ids,
            'times':self.times,'decision_times':self.decision_times,'y':self.y,'x':self.x,'observed':self.observed,'fresh':self.fresh,
            'exposed':self.exposed,'exposure_known':self.exposure_known,'feature_id':self.feature_id}))


def panel_from_time_slice(sliced,service_id):
    """Only a committed public prefix, with one replica per host for the requested service."""
    rows=sliced.get('windows')
    if not isinstance(rows,list) or not rows or sliced.get('input_sha256')!=digest(rows):
        raise ValueError('Expected a complete committed public slice with matching input hash')
    forbidden={'fault_type','fault_ids','true_affected','injected_latent_effect','injected_mechanisms','severity'}
    if any(forbidden & r.keys() for r in rows):raise ValueError('Evaluator labels are not public input')
    if any(r['run_id']!=sliced['run_id'] or r['epoch']!=sliced.get('epoch',0) for r in rows):raise ValueError('Mixed run or epoch in slice')
    if any(r['decision_time']>sliced['decision_time'] for r in rows):raise ValueError('Future window in causal slice')
    selected=[r for r in rows if r['service_id']==service_id]
    hosts=sorted({r['host_id'] for r in selected});times=sorted({r['event_time'] for r in rows})
    deadlines={}
    for r in rows:
        if r['event_time'] in deadlines and deadlines[r['event_time']]!=r['decision_time']:raise ValueError('Mixed deadline policies in one panel')
        deadlines[r['event_time']]=r['decision_time']
    if not hosts:raise ValueError('No requested service observations')
    index={h:i for i,h in enumerate(hosts)};ti={t:i for i,t in enumerate(times)}
    shape=(len(times),len(hosts));y=np.full(shape,np.nan);x=y.copy()
    obs=np.zeros(shape,bool);fresh=obs.copy();exposed=obs.copy();known=obs.copy()
    roster={};seen=set();replicas={}
    host_windows={}
    for r in rows:host_windows.setdefault((r['event_time'],r['host_id']),[]).append(r)
    for r in selected:
        h=r['host_id'];key=(r['event_time'],h)
        if key in seen:raise ValueError('Aggregate multiple same-service replicas per host before adjustment')
        seen.add(key)
        parent=(r['rack_id'],r['class_id']);replicas.setdefault(h,r['replica_id'])
        if h in roster and roster[h]!=parent or replicas[h]!=r['replica_id']:raise ValueError('Placement changed within panel')
        roster[h]=parent;a,b=ti[r['event_time']],index[h]
        context=host_windows[key]
        exposed[a,b]=any(z.get('exposed') is True for z in context)
        known[a,b]=all(z.get('exposure_observed') is True and not z.get('mixed_exposure') for z in context)
        usable=r.get('observed') is True and r.get('latency_observed') is True and r.get('workload_observed') is True
        fresh[a,b]=not r.get('carried_forward',False)
        if usable and r.get('log_latency_mean') is not None and r.get('workload') is not None:
            y[a,b]=r['log_latency_mean'];x[a,b]=np.log1p(r['workload']);obs[a,b]=True
    return PublicPanel(sliced['run_id'],tuple(hosts),tuple(roster[h][0] for h in hosts),tuple(roster[h][1] for h in hosts),
        np.array(times),y,x,obs,fresh,exposed,known,epoch=sliced.get('epoch',0),decision_times=np.array([deadlines[t] for t in times]))


@dataclass(frozen=True)
class HealthyDevelopment:
    panel:PublicPanel
    role:str
    declared_healthy:bool
    provenance_id:str

    def validate(self):
        if self.role!='development' or self.declared_healthy is not True or not self.provenance_id:
            raise ValueError('Fit only explicitly declared healthy development data')
        if np.any(self.panel.exposed):raise ValueError('Healthy development cannot include exposed hosts')
        return self


class FrozenAdjustment:
    def __init__(self,payload):
        self._data=copy.deepcopy(payload)
        if payload.get('model_id')!=MODEL_ID:raise ValueError('Wrong adjustment model version')
        self._policy=AdjustmentPolicy(**payload['policy'])
        n=len(payload['host_ids'])
        if n<1 or len(set(payload['host_ids']))!=n or not payload['canary_ids'] or len(set(payload['canary_ids']))!=len(payload['canary_ids']) or any(h not in payload['host_ids'] for h in payload['canary_ids']):
            raise ValueError('Invalid frozen model host/cohort metadata')
        for name in ('groups','rack_ids','class_ids','mu','beta','loadings','control_variance','scales','workload_support'):
            if len(payload[name])!=n:raise ValueError('Frozen parameter dimensions differ')
        for name in ('mu','beta','loadings','control_variance','scales'):
            if not np.isfinite(np.array(payload[name],dtype=float)).all():raise ValueError('Nonfinite frozen parameters')
        if min(payload['control_variance'])<=0 or min(payload['scales'])<=0 or not np.isfinite(payload['x_center']):raise ValueError('Invalid scales/center')
        for group in set(payload['groups']):
            noise=payload['noise'][group]
            if not all(np.isfinite(noise[k]) for k in ('phi','q','v')) or not -1<noise['phi']<1 or noise['q']<=0 or noise['v']<0:
                raise ValueError('Invalid frozen noise parameters')

    @property
    def policy(self):return self._policy

    def to_dict(self):return copy.deepcopy(self._data)
    def save(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        data=serial(self._data);data['artifact_sha256']=digest(data)
        path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text());expected=data.pop('artifact_sha256',None)
        if expected!=digest(data):raise ValueError('Frozen model hash mismatch')
        return cls(data)

    def _validate(self,panel):
        d=self._data
        if tuple(d['host_ids'])!=panel.host_ids or tuple(d['groups'])!=panel.groups(self.policy) or panel.feature_id!=d['feature_id'] or tuple(d['rack_ids'])!=panel.rack_ids or tuple(d['class_ids'])!=panel.class_ids:
            raise ValueError('Panel roster/group/features do not match frozen development model')

    def _controls(self,panel):
        self._validate(panel);d=self._data
        c=panel.y-np.array(d['mu'])[None]-np.array(d['beta'])[None]*(panel.x-d['x_center'])
        ok=panel.observed & panel.fresh & panel.exposure_known
        ctl=np.array([h not in d['canary_ids'] for h in panel.host_ids])
        current=ok & ~panel.exposed & ctl[None]
        if self.policy.factor_rank==0:
            return c,ok,current,np.zeros(len(panel.times)),np.zeros(len(panel.times)),np.ones(len(panel.times),bool)
        f,U,valid=project_rank_one_controls(np.where(current,c,np.nan),np.array(d['loadings']),np.array(d['control_variance']))
        valid &= bool(d['factor_identified'])
        return c,ok,current,f,U,valid

    def prepare(self,pre_panel,exposure_time):
        if type(exposure_time) not in (int,float) or not np.isfinite(exposure_time) or exposure_time<0:raise ValueError('Invalid exposure boundary')
        c,ok,ctl,f,U,valid=self._controls(pre_panel);d=self._data
        ids=[pre_panel.host_ids.index(h) for h in d['canary_ids']]
        lam=[];counts=[];fallback=[];cuts=[]
        for j in ids:
            actual=pre_panel.times[pre_panel.exposed[:,j]]
            cutoff=min(exposure_time,float(actual[0])) if len(actual) else exposure_time
            m=(pre_panel.times<cutoff)&(pre_panel.decision_times<=cutoff)&ok[:,j]&~pre_panel.exposed[:,j]&valid&np.isfinite(f)
            group=pre_panel.groups(self.policy)[j]
            group_indices=[k for k,g in enumerate(pre_panel.groups(self.policy)) if g==group]
            m &= ctl[:,group_indices].sum(1)>=self.policy.min_controls
            counts.append(int(m.sum()));cuts.append(float(cutoff))
            enough=m.sum()>=self.policy.min_pre_observations and np.sum(f[m]**2)>=1e-8
            lam.append(float(np.sum(f[m]*c[m,j])/np.sum(f[m]**2)) if self.policy.factor_rank and enough else d['loadings'][j] if self.policy.factor_rank else 0.)
            fallback.append(bool(self.policy.factor_rank and not enough))
        return PreparedAdjustment(self,tuple(lam),tuple(counts),tuple(fallback),tuple(cuts),float(exposure_time),pre_panel.run_id,pre_panel.epoch)


def fit_development(batches,canary_ids,policy=AdjustmentPolicy()):
    if not batches:raise ValueError('Healthy development data required')
    for batch in batches:batch.validate()
    panel=batches[0].panel
    if not canary_ids or len(set(canary_ids))!=len(canary_ids) or any(h not in panel.host_ids for h in canary_ids):raise ValueError('Invalid canary roster')
    groups=panel.groups(policy)
    for b in batches:
        if b.panel.host_ids!=panel.host_ids or b.panel.groups(policy)!=groups:raise ValueError('Development roster mismatch')
    y=np.concatenate([b.panel.y for b in batches]);x=np.concatenate([b.panel.x for b in batches])
    ok=np.concatenate([b.panel.observed & b.panel.fresh & b.panel.exposure_known & ~b.panel.exposed for b in batches])
    if np.any(ok.sum(0)<10):raise ValueError('Each host needs at least 10 fresh healthy development windows')
    center=float(np.mean(x[ok]));mu=[];beta=[];support=[];reg_flags=[]
    for j in range(len(groups)):
        m=ok[:,j];xx=x[:,j]-center
        variable=np.ptp(xx[m])>1e-10
        coef=_ols_host(y[:,j],xx,m) if variable else (np.mean(y[m,j]),0.)
        mu.append(float(coef[0]));beta.append(float(coef[1]));support.append([float(np.min(x[m,j])),float(np.max(x[m,j]))])
        reg_flags.append('ok' if variable else 'workload_not_identified')
    c=np.where(ok,y-np.array(mu)[None]-np.array(beta)[None]*(x-center),np.nan)
    control_indices=[i for i,h in enumerate(panel.host_ids) if h not in canary_ids]
    if len(control_indices)<1:raise ValueError('Independent controls are required')
    n=len(groups);loadings=np.zeros(n);variance=np.ones(n)*1e-8
    if policy.factor_rank:
        lc,vc,_=fit_rank_one_controls(c[:,control_indices]);loadings[control_indices]=lc;variance[control_indices]=vc
        f,U,valid=project_rank_one_controls(c[:,control_indices],lc,vc)
        identified=bool(np.sum(lc**2)>1e-12 and valid.any())
        for j,h in enumerate(panel.host_ids):
            if h in canary_ids:
                m=ok[:,j]&valid
                loadings[j]=np.sum(c[m,j]*f[m])/np.sum(f[m]**2) if m.any() and np.sum(f[m]**2)>1e-8 else np.median(lc)
    else:f=np.zeros(len(c));U=np.zeros(len(c));identified=True
    # Leave each development control out of its own reference when fitting scales/noise.
    r=c.copy();extra=np.zeros_like(c)
    for j in range(n):
        if policy.factor_rank and identified:
            controls=c[:,control_indices].copy()
            if j in control_indices:controls[:,control_indices.index(j)]=np.nan
            fj,uj,good=project_rank_one_controls(controls,loadings[control_indices],variance[control_indices])
            r[:,j]=np.where(good,c[:,j]-loadings[j]*fj,np.nan)
            extra[:,j]=np.where(good,loadings[j]**2*uj,0.)
    scales=np.maximum(np.nanstd(r,axis=0),1e-6)
    noise={};diagnostics={};fit_ok=True
    for group in sorted(set(groups)):
        ids=[i for i,g in enumerate(groups) if g==group];series=[];xs=[];offset=0
        for batch in batches:
            stop=offset+len(batch.panel.times)
            series.extend(r[offset:stop,j] for j in ids);xs.extend(extra[offset:stop,j] for j in ids);offset=stop
        # Padding retains gaps and prevents AR transitions between separate development runs.
        length=max(map(len,series));R=np.full((len(series),length),np.nan);X=np.zeros_like(R)
        for k,(rr,xx) in enumerate(zip(series,xs)):R[k,:len(rr)]=rr;X[k,:len(xx)]=xx
        if not np.isfinite(R).any():raise ValueError('No usable development residuals for noise fit')
        p,rec=fit_ar_class(R,X,fix_v=True);best=min(rec,key=lambda z:z['nll']);fit_ok &= bool(best['success'])
        noise[group]={'phi':float(p[0]),'q':float(np.exp(p[1])),'v':float(np.exp(p[2]))}
        diagnostics[group]={'fits':rec,'success':bool(best['success']),'boundary_hit':bool(best['boundary_hit'])}
    data={'model_id':MODEL_ID,'feature_id':panel.feature_id,'policy':asdict(policy),'host_ids':list(panel.host_ids),
        'rack_ids':list(panel.rack_ids),'class_ids':list(panel.class_ids),
        'groups':list(groups),'canary_ids':list(canary_ids),'x_center':center,'mu':mu,'beta':beta,
        'loadings':loadings.tolist(),'control_variance':variance.tolist(),'scales':scales.tolist(),
        'noise':noise,'noise_diagnostics':diagnostics,'noise_fit_ok':bool(fit_ok),'factor_identified':identified,
        'development_control_counts':{g:sum(groups[j]==g for j in control_indices) for g in sorted(set(groups))},
        'workload_support':support,'regression_flags':reg_flags,
        'development_missing_control_entries':int((~ok[:,control_indices]).sum()),
        'development_lineage':[{'provenance_id':b.provenance_id,'role':b.role,'healthy_attestation':True,'public_sha256':b.panel.fingerprint()} for b in batches],
        'challenges':['background_control_contamination_possible','plain_weighted_projection_not_robust','frozen_regression_parameter_uncertainty_not_propagated','canary_loading_estimation_uncertainty_not_propagated']}
    return FrozenAdjustment(data)


@dataclass(frozen=True)
class PreparedAdjustment:
    model:FrozenAdjustment
    loadings:tuple
    pre_counts:tuple
    fallback:tuple
    cutoffs:tuple
    exposure_time:float
    run_id:str
    epoch:int

    def transform(self,panel):
        if panel.run_id!=self.run_id or panel.epoch!=self.epoch:raise ValueError('Prepare loadings separately for each run/epoch')
        c,ok,controls,f,U,factor_ok=self.model._controls(panel);d=self.model._data;policy=self.model.policy
        ids=[panel.host_ids.index(h) for h in d['canary_ids']];groups=panel.groups(policy)
        lam=np.array(self.loadings);r=c[:,ids]-lam[None]*np.where(np.isfinite(f),f,np.nan)[:,None]
        masks=ok[:,ids]&np.isfinite(r);r=np.where(masks,r,np.nan)
        if len(panel.times)*len(ids)**2>2_000_000:raise ValueError('Transform covariance budget exceeded; use smaller committed slices')
        shared=np.stack([reference_covariance(lam,u) if np.isfinite(u) else np.full((len(ids),len(ids)),np.nan) for u in U])
        white=np.array([d['noise'][groups[j]]['v'] for j in ids])
        measurement=shared+np.diag(white**2)[None]
        counts={g:controls[:,[j for j,x in enumerate(groups) if x==g]].sum(1) for g in sorted({groups[j] for j in ids})}
        fraction=masks.mean(1);eligible=fraction>=policy.min_canary_fraction
        for count in counts.values():eligible &= count>=policy.min_controls
        eligible &= factor_ok & bool(d['noise_fit_ok'])
        availability=eligible.copy()
        eligible &= panel.times>=self.exposure_time
        flags=[];overlap={g:[] for g in counts}
        for t in range(len(panel.times)):
            row=[]
            if panel.times[t]<self.exposure_time:row.append('pre_exposure_diagnostic_only')
            if any(cut<self.exposure_time for cut in self.cutoffs):row.append('observed_exposure_before_declared_boundary')
            row.extend('development_workload_not_identified:'+h for h,flag in zip(d['host_ids'],d.get('regression_flags',[])) if flag!='ok')
            if any(z.get('boundary_hit') for z in d.get('noise_diagnostics',{}).values()):row.append('development_noise_boundary')
            if fraction[t]<policy.min_canary_fraction:row.append('insufficient_canary_coverage')
            if not factor_ok[t]:row.append('factor_not_identified_or_no_fresh_information')
            if not d['noise_fit_ok']:row.append('development_noise_fit_failed')
            for g,count in counts.items():
                if count[t]<policy.min_controls:row.append('insufficient_fresh_controls:'+g)
                ctl=[j for j,x in enumerate(groups) if x==g and controls[t,j]]
                can=[j for j in ids if groups[j]==g and ok[t,j]]
                supported=bool(ctl and can and min(panel.x[t,can])<=max(panel.x[t,ctl]) and max(panel.x[t,can])>=min(panel.x[t,ctl]))
                overlap[g].append(supported)
                if not supported:row.append('no_current_workload_support_overlap:'+g)
            if any(self.fallback):row.append('development_loading_fallback')
            if any(ok[t,j] and not d['workload_support'][j][0]<=panel.x[t,j]<=d['workload_support'][j][1] for j in range(len(groups))):
                row.append('workload_extrapolation')
            flags.append(row)
        return {'model_id':MODEL_ID,'policy':asdict(policy),'run_id':panel.run_id,'event_times':panel.times.copy(),
            'decision_times':panel.decision_times.copy(),
            'feature_id':panel.feature_id,'exposure_time':self.exposure_time,'after_exposure':panel.times>=self.exposure_time,
            'canary_ids':list(d['canary_ids']),'residuals':r,'observed':masks,'eligible':eligible,'availability_eligible':availability,
            'canary_exposed':panel.exposed[:,ids].copy(),'canary_exposure_known':panel.exposure_known[:,ids].copy(),
            'canary_coverage':fraction,'fresh_control_counts':counts,'workload_support_overlap':overlap,
            'control_mask':controls,'workload_residuals':np.where(ok,c,np.nan),
            'factor':f,'control_estimation_uncertainty':U,'canary_loadings':lam,
            'shared_reference_covariance':shared,'measurement_covariance':measurement,
            'scales':np.array(d['scales'])[ids],'noise':copy.deepcopy(d['noise']),
            'development_noise_diagnostics':copy.deepcopy(d.get('noise_diagnostics',{})),
            'development_missing_control_entries':d.get('development_missing_control_entries',0),
            'pre_observations':list(self.pre_counts),'loading_fallback':list(self.fallback),'loading_cutoffs':list(self.cutoffs),
            'quality_flags':flags,'challenges':copy.deepcopy(d['challenges']),
            'reference_subtractions':policy.factor_rank,'covariance_units':'log_latency_squared',
            'covariance_contract':'measurement = diag(v^2) + outer(lambda,lambda)*U; AR noise stays separate; add shared term once'}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    fit=commands.add_parser('fit');fit.add_argument('--slice',required=True);fit.add_argument('--service-id',required=True)
    fit.add_argument('--canaries',nargs='+',required=True);fit.add_argument('--role',choices=['development'],required=True)
    fit.add_argument('--healthy',action='store_true');fit.add_argument('--provenance-id',required=True)
    fit.add_argument('--policy-json');fit.add_argument('--out',required=True)
    apply=commands.add_parser('apply');apply.add_argument('--slice',required=True);apply.add_argument('--service-id',required=True)
    apply.add_argument('--model',required=True);apply.add_argument('--exposure-time',type=float,required=True);apply.add_argument('--out',required=True)
    a=parser.parse_args()
    try:
        panel=panel_from_time_slice(json.loads(Path(a.slice).read_text()),a.service_id)
        if a.command=='fit':
            policy=AdjustmentPolicy(**json.loads(Path(a.policy_json).read_text())) if a.policy_json else AdjustmentPolicy()
            model=fit_development([HealthyDevelopment(panel,a.role,a.healthy,a.provenance_id)],a.canaries,policy)
            model.save(a.out)
        else:
            model=FrozenAdjustment.load(a.model);result=model.prepare(panel,a.exposure_time).transform(panel)
            path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(serial(result),indent=2,allow_nan=False)+'\n')
        print(json.dumps({'output':a.out,'model_id':MODEL_ID,'detector_connected':False}))
    except (ValueError,KeyError,OSError) as exc:parser.error(str(exc))


if __name__=='__main__':main()
