"""Opt-in diagnostic global/rack/host Gaussian effects; new selection/calibration required."""
from dataclasses import dataclass,asdict
import json
from pathlib import Path

import numpy as np

from .hierarchy import EffectParams
from .public_filter import GaussianEffects,observations_from_adjustment
from .public_hierarchy import grouped_structure
from .public_adjustment import FrozenAdjustment,serial
from .schema import KAPPA
from .telemetry import digest

VARIANT_ID='nested-global-rack-host-v1'


@dataclass(frozen=True)
class NestedParams:
    enabled: bool=False
    variant_id: str=VARIANT_ID
    group_by: str='rack_id'
    rho_global: float=.95
    rho_rack: float=.9
    rho_host: float=.8
    sd_global: float=.005
    sd_rack: float=.003
    sd_host: float=.002
    prior_global_sd: float=.03
    prior_rack_sd: float=.02
    prior_host_sd: float=.01

    def __post_init__(self):
        if type(self.enabled) is not bool or self.variant_id!=VARIANT_ID or self.group_by!='rack_id':
            raise ValueError('Use the separately versioned explicit rack nested configuration')
        for name,value in asdict(self).items():
            if name.startswith(('rho_','sd_','prior_')):
                if type(value) not in (int,float) or not np.isfinite(value):raise ValueError('Finite explicit level parameters required')
                if name.startswith('rho_') and abs(value)>1:raise ValueError('Invalid persistence')
                if name.startswith('sd_') and value<0:raise ValueError('Negative innovation SD')
                if name.startswith('prior_') and value<=0:raise ValueError('Proper level prior required')


@dataclass(frozen=True)
class NestedStructure:
    host_ids: tuple
    rack_ids: tuple
    represented_racks: tuple
    counts: np.ndarray
    C: np.ndarray
    R: np.ndarray
    B: np.ndarray
    rack_map: np.ndarray


def nested_structure(host_ids,rack_ids):
    """Deterministic weighted Householder contrasts in rack-constant host space."""
    st=grouped_structure(host_ids,rack_ids,'rack_id');C,B=st.C,st.B
    counts=C.sum(0);n,G=C.shape
    # Z is an orthonormal rack-incidence map; w is the normalized host all-ones
    # vector expressed in these coordinates. Householder sends w to e_last.
    Z=C/np.sqrt(counts)[None];w=np.sqrt(counts/n)
    if G==1:R=np.zeros((n,0))
    else:
        v=w.copy();v[-1]-=1
        householder=np.eye(G)-2*np.outer(v,v)/(v@v)
        R=Z@householder[:,:G-1]
    rack_map=(C.T@R)/counts[:,None]
    for a in (counts,R,rack_map):a.setflags(write=False)
    return NestedStructure(st.host_ids,st.labels,st.group_ids,counts,C,R,B,rack_map)


class NestedGaussianEffects(GaussianEffects):
    def __init__(self,structure,settings=NestedParams(),kappa=KAPPA):
        if not settings.enabled:raise ValueError('Nested variant is disabled; explicit configuration opt-in required')
        if not np.isfinite(kappa):raise ValueError('Finite harm boundary required')
        self.structure=structure;self.settings=settings;self.kappa=float(kappa)
        self.params=EffectParams(kind='nested',rho_g=settings.rho_global,sd_g=settings.sd_global,
            prior_sd=settings.prior_global_sd)

    def run(self,data):
        st=self.structure;p=self.settings;n,G=st.C.shape
        if tuple(data.host_ids)!=st.host_ids:raise ValueError('Nested structure requires the frozen host order')
        if len(data.times)*n*n>1_000_000:raise ValueError('Nested component covariance budget exceeded')
        M=np.hstack([np.ones((n,1)),st.R,st.B])
        rho=np.r_[p.rho_global,np.full(G-1,p.rho_rack),np.full(n-G,p.rho_host)]
        sd=np.r_[p.sd_global,np.full(G-1,p.sd_rack),np.full(n-G,p.sd_host)]
        prior_sd=np.r_[p.prior_global_sd,np.full(G-1,p.prior_rack_sd),np.full(n-G,p.prior_host_sd)]
        prior=np.diag(prior_sd**2)
        result=self._run_model(data,M,rho,sd,prior,retain_state=True)
        m=result['posterior_state_mean'];P=result['posterior_state_covariance']
        maps={
            'global':np.hstack([np.ones((n,1)),np.zeros((n,2*n-1))]),
            'rack':np.hstack([np.zeros((n,1)),st.R,np.zeros((n,2*n-G))]),
            'host':np.hstack([np.zeros((n,G)),st.B,np.zeros((n,n))])}
        pre=data.times<data.exposure_time
        components={};cross={}
        for name,A in maps.items():
            mean=np.einsum('ij,tj->ti',A,m)
            cov=np.einsum('ij,tjk,lk->til',A,P,A)
            mean[pre]=np.nan;cov[pre]=np.nan
            components[name]={'host_mean':mean,'host_covariance':cov}
        names=list(maps)
        for i,name in enumerate(names):
            for other in names[i+1:]:
                cross[name+'_'+other]=np.einsum('ij,tjk,lk->til',maps[name],P,maps[other])
        rack_A=np.hstack([np.zeros((G,1)),st.rack_map,np.zeros((G,2*n-G))])
        rack_mean=np.einsum('ij,tj->ti',rack_A,m)
        rack_cov=np.einsum('ij,tjk,lk->til',rack_A,P,rack_A)
        rack_mean[pre]=np.nan;rack_cov[pre]=np.nan
        observation_eligible=result.pop('eligible');diagnostic_score=result.pop('score')
        result.update({'variant_id':VARIANT_ID,'settings':asdict(p),'parameters':asdict(p),
            'host_ids':list(st.host_ids),'host_rack_ids':list(st.rack_ids),'rack_ids':list(st.represented_racks),
            'rack_host_counts':st.counts,'C':st.C,'R':st.R,'B':st.B,'rack_coordinate_map':st.rack_map,
            'state_layout':{'global':[0,1],'rack_coordinates':[1,G],'host_coordinates':[G,n],'AR_noise':[n,2*n]},
            'global_effect_mean':m[:,0],'global_effect_variance':P[:,0,0],
            'rack_effect_mean':rack_mean,'rack_effect_covariance':rack_cov,
            'components':components,'component_cross_covariances':cross,'component_maps':maps,
            'total_host_effect_mean':result['host_effect_mean'],'total_host_effect_covariance':result['host_effect_covariance'],
            'effect_coordinate_covariance':P[:,:n,:n],
            'induced_effect_prior_covariance':M@prior@M.T,
            'induced_effect_innovation_covariance':M@np.diag(sd**2)@M.T,
            'diagnostic_score':diagnostic_score,'observation_eligible':observation_eligible,
            'decision_eligible':np.zeros(len(data.times),bool),
            'development_selection_required':True,'calibration_required':True,
            'validation_status':'unselected_uncalibrated','inference_use':'diagnostic_only',
            'risk_excludes_AR_noise':True,
            'global_effect_interpretation':'release-associated residual component; not the control workload factor; not causal attribution'})
        return result


def run_nested(adjusted,model,settings=NestedParams()):
    if not settings.enabled:raise ValueError('Nested variant requires explicit enabled configuration')
    if model.policy.group_by!='rack_id':raise ValueError('Nested rack variant requires per-rack control eligibility')
    data=observations_from_adjustment(adjusted,model);d=model.to_dict()
    racks=[d['rack_ids'][d['host_ids'].index(h)] for h in data.host_ids]
    st=nested_structure(data.host_ids,racks)
    output=NestedGaussianEffects(st,settings).run(data)
    protocol={'variant_id':VARIANT_ID,'settings':asdict(settings),'nuisance_model_sha256':digest(d),
        'host_ids':list(data.host_ids),'rack_ids':racks,'R':serial(st.R),'B':serial(st.B)}
    return {'pipeline_id':VARIANT_ID,'protocol_fingerprint':digest(protocol),'protocol':protocol,
        'run_id':data.run_id,'event_times':data.times,'decision_times':data.decision_times,
        'input_sha256':digest(serial(adjusted)),'used_observations':data.use,'output':output,
        'thresholds':None,'alarms':None,'dashboard_connected':False,
        'development_selection_required':True,'calibration_required':True,
        'quality_flags':adjusted.get('quality_flags',[]),'challenges':adjusted.get('challenges',[]),
        'limitations':['crossed_class_rack_effects_require_separate_model','conditional_on_fixed_parameters',
            'global_residual_effect_not_control_workload_factor','unselected_uncalibrated_diagnostic_only']}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',required=True);parser.add_argument('--model',required=True)
    parser.add_argument('--adjusted',required=True);parser.add_argument('--out',required=True)
    a=parser.parse_args()
    try:
        settings=NestedParams(**json.loads(Path(a.settings).read_text()))
        result=run_nested(json.loads(Path(a.adjusted).read_text()),FrozenAdjustment.load(a.model),settings)
        target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(serial(result),indent=2,allow_nan=False)+'\n')
        print(json.dumps({'output':str(target),'variant_id':VARIANT_ID,'validation_status':'unselected_uncalibrated'}))
    except (ValueError,TypeError,KeyError,OSError) as exc:parser.error(str(exc))


if __name__=='__main__':main()
