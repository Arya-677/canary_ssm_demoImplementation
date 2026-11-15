"""Joint constrained Gaussian class/host and explicit rack/host demo hierarchy."""
from dataclasses import dataclass, asdict
import json
from pathlib import Path

import numpy as np

from .hierarchy import class_structure, EffectParams
from .public_filter import GaussianEffects, observations_from_adjustment
from .public_adjustment import FrozenAdjustment, serial
from .schema import KAPPA
from .telemetry import identifier, integer, digest


@dataclass(frozen=True)
class GroupedParams:
    group_by: str = 'class_id'
    variant_id: str = 'public-class-host-v1'
    rho_g: float = .95
    rho_h: float = .95
    sd_g: float = .005
    sd_h: float = .005
    prior_group_sd: float = .03
    prior_deviation_sd: float = .03

    def __post_init__(self):
        if (self.group_by,self.variant_id) not in (('class_id','public-class-host-v1'),('rack_id','demo-rack-host-v1')):
            raise ValueError('Declare the class research-compatible or explicit rack demo variant')
        values = [self.rho_g,self.rho_h,self.sd_g,self.sd_h,self.prior_group_sd,self.prior_deviation_sd]
        if not all(type(x) in (int,float) and np.isfinite(x) for x in values):
            raise ValueError('Finite dynamics and prior SDs are required')
        if abs(self.rho_g)>1 or abs(self.rho_h)>1 or min(self.sd_g,self.sd_h)<0 or min(self.prior_group_sd,self.prior_deviation_sd)<=0:
            raise ValueError('Invalid grouped dynamics or proper priors')


@dataclass(frozen=True)
class GroupStructure:
    host_ids: tuple
    labels: tuple
    group_ids: tuple
    group_by: str
    C: np.ndarray
    B: np.ndarray


def grouped_structure(host_ids, labels, group_by='class_id'):
    """Preserve supplied host order, sorted group columns; reuse research basis."""
    host_ids,labels=tuple(host_ids),tuple(labels)
    if group_by not in ('class_id','rack_id') or not 1<=len(host_ids)<=128 or len(labels)!=len(host_ids) or len(set(host_ids))!=len(host_ids):
        raise ValueError('Invalid fixed host/group roster')
    for h in host_ids:identifier(h,'host_id')
    for g in labels:
        if group_by=='rack_id':identifier(g,'rack_id')
        else:integer(g,'class_id')
    C,B=class_structure(np.asarray(labels))
    n=len(host_ids);group_ids=tuple(sorted(set(labels)));G=len(group_ids)
    if B.shape!=(n,n-G) or not np.allclose(C.T@B,0,atol=1e-12) or not np.allclose(B.T@B,np.eye(n-G),atol=1e-12):
        raise ValueError('Invalid orthonormal sum-zero basis')
    C.setflags(write=False);B.setflags(write=False)
    return GroupStructure(host_ids,labels,group_ids,group_by,C,B)


class GroupedGaussianEffects(GaussianEffects):
    def __init__(self, structure, settings=GroupedParams(), kappa=KAPPA):
        if not np.isfinite(kappa):raise ValueError('Finite harm boundary required')
        if structure.group_by!=settings.group_by:raise ValueError('Structure grouping conflicts with settings')
        self.structure=structure;self.settings=settings;self.kappa=float(kappa)
        # The inherited joint engine consumes these declared dynamics; no list
        # of per-host filters, surrogate posteriors or noise in the risk map.
        self.params=EffectParams(kind='hier',rho_g=settings.rho_g,rho_h=settings.rho_h,
            sd_g=settings.sd_g,sd_h_ratio=settings.sd_h/settings.sd_g if settings.sd_g else 0,
            prior_sd=settings.prior_group_sd)

    def run(self,data):
        st=self.structure;p=self.settings
        if tuple(data.host_ids)!=st.host_ids:raise ValueError('Stable host order must match the declared structure')
        C,B=st.C,st.B;n,G=C.shape;d=B.shape[1]
        M=np.hstack([C,B])
        rho=np.r_[np.full(G,p.rho_g),np.full(d,p.rho_h)]
        sd=np.r_[np.full(G,p.sd_g),np.full(d,p.sd_h)]
        prior=np.diag(np.r_[np.full(G,p.prior_group_sd**2),np.full(d,p.prior_deviation_sd**2)])
        result=self._run_model(data,M,rho,sd,prior,retain_state=True)
        m=result['posterior_state_mean'];P=result['posterior_state_covariance']
        theta=m[:,:G];b=m[:,G:n]
        group_host=np.einsum('ig,tg->ti',C,theta)
        deviation=np.einsum('ij,tj->ti',B,b)
        group_cov=P[:,:G,:G];b_cov=P[:,G:n,G:n]
        group_host_cov=np.einsum('ig,tgh,jh->tij',C,group_cov,C)
        deviation_cov=np.einsum('ik,tkl,jl->tij',B,b_cov,B)
        cross=np.einsum('tgk,ik->tgi',P[:,:G,G:n],B)
        pre=data.times<data.exposure_time
        deviation[pre]=np.nan;deviation_cov[pre]=np.nan;cross[pre]=np.nan
        result.update({'group_by':p.group_by,'variant_id':p.variant_id,'parameters':asdict(p),
            'settings':asdict(p),'host_ids':list(st.host_ids),'group_ids':list(st.group_ids),
            'host_group_ids':list(st.labels),'C':C,'B':B,
            'state_layout':{'theta':[0,G],'b':[G,n],'e':[n,2*n]},
            'group_effect_mean':theta,'group_effect_covariance':group_cov,
            'host_group_effect_mean':group_host,'host_group_effect_covariance':group_host_cov,
            'host_deviation_mean':deviation,'host_deviation_covariance':deviation_cov,
            'group_deviation_cross_covariance':cross,
            'effect_coordinate_covariance':P[:,:n,:n],
            'total_host_effect_mean':result['host_effect_mean'],
            'total_host_effect_covariance':result['host_effect_covariance'],
            'induced_effect_prior_covariance':M@prior@M.T,
            'induced_effect_innovation_covariance':M@np.diag(sd*sd)@M.T,
            'group_effect_label':'rack_effect' if p.group_by=='rack_id' else 'class_effect',
            'risk_excludes_AR_noise':True})
        return result


def run_hierarchy(adjusted,model,settings=GroupedParams()):
    data=observations_from_adjustment(adjusted,model);d=model.to_dict()
    if model.policy.group_by!=settings.group_by:
        raise ValueError('Adjustment control eligibility must use the same represented groups')
    indices=[d['host_ids'].index(h) for h in data.host_ids]
    labels=[d['rack_ids' if settings.group_by=='rack_id' else 'class_ids'][i] for i in indices]
    structure=grouped_structure(data.host_ids,labels,settings.group_by)
    result=GroupedGaussianEffects(structure,settings).run(data)
    return {'pipeline_id':'public-constrained-hierarchy-v1','run_id':data.run_id,
        'event_times':data.times,'decision_times':data.decision_times,
        'input_sha256':digest(serial(adjusted)),'used_observations':data.use,
        'output':result,'thresholds':None,'alarms':None,'dashboard_connected':False,
        'quality_flags':adjusted.get('quality_flags',[]),'challenges':adjusted.get('challenges',[])}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True);p.add_argument('--adjusted',required=True)
    p.add_argument('--group-by',choices=['class_id','rack_id'],default='class_id')
    p.add_argument('--settings');p.add_argument('--out',required=True);a=p.parse_args()
    try:
        settings=GroupedParams(**json.loads(Path(a.settings).read_text())) if a.settings else GroupedParams(
            group_by=a.group_by,variant_id='demo-rack-host-v1' if a.group_by=='rack_id' else 'public-class-host-v1')
        if settings.group_by!=a.group_by:raise ValueError('CLI grouping conflicts with settings')
        result=run_hierarchy(json.loads(Path(a.adjusted).read_text()),FrozenAdjustment.load(a.model),settings)
        target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(serial(result),indent=2,allow_nan=False)+'\n')
        print(json.dumps({'output':str(target),'variant_id':settings.variant_id,'calibrated':False}))
    except (ValueError,KeyError,OSError) as exc:p.error(str(exc))


if __name__=='__main__':main()
