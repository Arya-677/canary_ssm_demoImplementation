"""Public-only comparison path: no hidden truth or evaluator imports."""
import copy
from dataclasses import replace
import numpy as np
from scipy.optimize import minimize_scalar
from .preprocess import fit_nuisance, Nuisance, adjust_roll
from .factor import Adjusted
from .baselines import run_baseline
from .public_adjustment import HealthyDevelopment, AdjustmentPolicy, fit_development, FrozenAdjustment, serial
from .public_filter import Observations, observations_from_adjustment, GaussianEffects
from .hierarchy import EffectParams
from .public_hierarchy import GroupedParams, GroupedGaussianEffects, grouped_structure
from .nested_hierarchy import NestedParams, NestedGaussianEffects, nested_structure

COMMON_METHODS=('adj_ewma','adj_cusum','topk_cusum','independent','complete_pooling','class_host','factor_off','persistence_off','ar_off','weaker_pooling','stronger_pooling')
WORLD_METHODS=COMMON_METHODS+('rack_host','nested_global_rack_host')

def fit_public(generator,healthy,canaries,role='development'):
    if role!='development':raise ValueError('Fit only healthy development data')
    if generator=='research':return {key:fit_nuisance(healthy,factor_rank=rank,noise=noise,beta_mode='pooled_dev').to_dict() for key,rank,noise in [('base',1,'ar_only'),('factor_off',0,'ar_only'),('ar_off',1,'white')]}
    models={};batches=[HealthyDevelopment(p,'development',True,'study-healthy-'+str(i)) for i,p in enumerate(healthy)]
    for key,rank in [('base',1),('factor_off',0)]:
        policy=AdjustmentPolicy(policy_id='demo-evaluator-'+key+'-v2',group_by='rack_id',factor_rank=rank,deviation_reason='Physical rack study, original 80%/three-control/60-pre eligibility preserved')
        models[key]=fit_development(batches,canaries,policy).to_dict()
    base=FrozenAdjustment(models['base']);white=copy.deepcopy(models['base']);series={}
    for panel in healthy:
        adj=base.prepare(panel,float(panel.times[-1]+60)).transform(panel);ids=[panel.host_ids.index(h) for h in canaries]
        for j,i in enumerate(ids):series.setdefault(white['groups'][i],[]).append((adj['residuals'][:,j],adj['shared_reference_covariance'][:,j,j]))
    floor=1e-8;diag={};ok=True
    for group,rr in series.items():
        r=np.concatenate([a for a,b in rr]);extra=np.concatenate([b for a,b in rr]);mask=np.isfinite(r)&np.isfinite(extra);r,extra=r[mask],extra[mask]
        def loss(logsd):
            variance=np.exp(2*logsd)+extra+floor**2
            return float(.5*np.sum(np.log(variance)+r*r/variance))
        fit=minimize_scalar(loss,bounds=(-13.,2.),method='bounded');success=bool(fit.success and len(r)>0)
        white['noise'][group]={'phi':0.,'q':floor,'v':float(np.exp(fit.x))};diag[group]={'success':success,'boundary_hit':min(abs(fit.x+13),abs(fit.x-2))<1e-3,'nll':float(fit.fun),'bounds':[-13.,2.],'samples':len(r),'q_floor':floor};ok &= success
    white['preceding_ar_fit_diagnostics']=white['noise_diagnostics'];white['noise_diagnostics']=diag;white['noise_fit_ok']=ok;models['ar_off']=white
    return models

def adjusted_input(generator,public,model,racks=None):
    if generator=='research':
        nu=Nuisance(**model);a=adjust_roll(public,nu);n=len(public.canary_idx);T=public.T;groups=public.class_id[:n]
        V=np.array([np.diag(np.array(nu.v)[groups]**2)+np.outer(a.lam,a.lam)*max(0.,float(u)) for u in np.nan_to_num(a.U)])
        times=(np.arange(T)+1)*60.;hosts=tuple('h'+str(i).zfill(2) for i in range(n))
        data=Observations(times,times,a.r,a.obs,a.elig,a.elig&(np.arange(T)>=public.t0),V,np.array(nu.phi_e)[groups],np.array(nu.q_e)[groups],a.sigma,hosts,(public.t0+1)*60.,public.rollout_id)
        eligible=data.eligible.copy()
        fits=[min(d['fits'],key=lambda r:r['nll']) for d in nu.diagnostics.get('classes',[]) if d.get('fits')]
        if any(not f['success'] for f in fits):eligible[:]=False
        data=replace(data,eligible=eligible);a.elig=eligible
        return data,eligible,tuple(int(g) for g in groups),tuple(racks[:n]),a
    frozen=FrozenAdjustment(model);adj=frozen.prepare(public,3660.).transform(public);data=observations_from_adjustment(serial(adj),frozen)
    eligible=data.eligible & np.array([not f for f in adj['quality_flags']]);data=replace(data,eligible=eligible)
    idx=[public.host_ids.index(h) for h in data.host_ids];n=len(idx);T=len(data.times)
    a=Adjusted(np.where(data.use,data.residuals,np.nan),data.use,eligible,np.zeros(T),np.zeros(n),data.scales,np.full_like(data.residuals,np.nan),np.array([public.class_ids[i] for i in idx]),int(np.searchsorted(data.times,data.exposure_time)),np.zeros(n,bool),np.zeros(T))
    return data,eligible,tuple(int(public.class_ids[i]) for i in idx),tuple(public.rack_ids[i] for i in idx),a

def one_method(name,data,eligible,classes,racks,adj,sd=.005,grouping='class_id'):
    if name not in WORLD_METHODS:raise ValueError('Undeclared method')
    if name in ('adj_ewma','adj_cusum','topk_cusum'):
        out=run_baseline(name,adj,**({'K':3} if name=='topk_cusum' else {}))
        return dict(score=out.score,eligible=eligible,host_rank=out.host_score,mean=None,variance=None,output_kind='classical_statistic')
    if name in ('independent','complete_pooling'):out=GaussianEffects(EffectParams(kind='indep' if name=='independent' else 'pooled',sd_g=sd)).run(data)
    elif name=='nested_global_rack_host':out=NestedGaussianEffects(nested_structure(data.host_ids,racks),NestedParams(enabled=True,sd_global=sd)).run(data)
    else:
        by='class_id' if name=='class_host' else 'rack_id' if name=='rack_host' else grouping
        p=GroupedParams(group_by=by,variant_id='public-class-host-v1' if by=='class_id' else 'demo-rack-host-v1',sd_g=sd,sd_h=sd*(3 if name=='weaker_pooling' else .2 if name=='stronger_pooling' else 1),rho_g=0. if name=='persistence_off' else .95,rho_h=0. if name=='persistence_off' else .95)
        out=GroupedGaussianEffects(grouped_structure(data.host_ids,classes if by=='class_id' else racks,by),p).run(data)
    return dict(score=out.get('score',out.get('diagnostic_score')),eligible=eligible,host_rank=out['host_probability'],mean=out['host_effect_mean'],variance=np.diagonal(out['host_effect_covariance'],axis1=1,axis2=2),output_kind='conditional_gaussian_posterior')

def compare(generator,public,models,settings,racks=None):
    cache={};result={}
    for name in COMMON_METHODS if generator=='research' else WORLD_METHODS:
        key=name if name in ('factor_off','ar_off') else 'base'
        if key not in cache:cache[key]=adjusted_input(generator,public,models[key],racks)
        data,elig,classes,rs,adj=cache[key]
        out=one_method(name,data,elig,classes,rs,adj,float(settings.get(name,.005)),'rack_id' if generator=='world' else 'class_id')
        out.update(times=data.times,exposure_time=data.exposure_time,host_ids=data.host_ids);result[name]=out
    return result
