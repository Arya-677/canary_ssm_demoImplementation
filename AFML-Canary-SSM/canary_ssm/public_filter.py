"""Uncalibrated Gaussian effects and existing baselines on frozen public adjustment."""
from dataclasses import dataclass
import copy
import json
from pathlib import Path

import numpy as np
from scipy.linalg import block_diag
from scipy.stats import norm

from .kalman import KalmanFilter
from .hierarchy import EffectParams, build_model
from .factor import Adjusted
from .baselines import run_baseline
from .public_adjustment import FrozenAdjustment, MODEL_ID, FEATURE_ID, serial
from .schema import KAPPA
from .telemetry import digest

PIPELINE_ID = 'public-gaussian-effects-v1'


def _bool(value, shape):
    a = np.asarray(value)
    if a.dtype.kind != 'b' or a.shape != shape:
        raise ValueError('Expected correctly shaped boolean masks')
    return a.copy()


@dataclass(frozen=True)
class Observations:
    """One minute unit; V is white measurement covariance, q is AR innovation SD."""
    times: np.ndarray
    decision_times: np.ndarray
    residuals: np.ndarray
    observed: np.ndarray
    available: np.ndarray
    eligible: np.ndarray
    V: np.ndarray
    phi: np.ndarray
    q: np.ndarray
    scales: np.ndarray
    host_ids: tuple
    exposure_time: float
    run_id: str

    def __post_init__(self):
        for name in ('times', 'decision_times', 'residuals', 'V', 'phi', 'q', 'scales'):
            a = np.array(getattr(self, name), float, copy=True)
            a.setflags(write=False)
            object.__setattr__(self, name, a)
        T, n = self.residuals.shape
        if not 1 <= n <= 128 or not 1 <= T <= 10000 or T*n*n > 2_000_000:
            raise ValueError('Observation budget exceeded')
        if len(self.host_ids) != n or len(set(self.host_ids)) != n:
            raise ValueError('Invalid host roster')
        for name, shape in [('observed', (T,n)), ('available', (T,)), ('eligible', (T,))]:
            a = _bool(getattr(self, name), shape); a.setflags(write=False)
            object.__setattr__(self, name, a)
        if self.times.shape != (T,) or not np.isfinite(self.times).all() or np.any(self.times < 60) or np.any(np.diff(self.times) <= 0) or not np.allclose(self.times/60, np.round(self.times/60), atol=1e-9, rtol=0):
            raise ValueError('Use increasing minute boundaries in simulated seconds')
        if self.decision_times.shape != (T,) or not np.isfinite(self.decision_times).all() or np.any(self.decision_times < self.times) or np.any(np.diff(self.decision_times) <= 0):
            raise ValueError('Invalid receipt deadlines')
        if not np.isfinite(self.exposure_time) or self.exposure_time < 60 or not np.isclose(self.exposure_time/60, round(self.exposure_time/60), atol=1e-9, rtol=0):
            raise ValueError('Exposure must be a declared minute boundary')
        if np.any(self.eligible & (~self.available | (self.times < self.exposure_time))):
            raise ValueError('Decision eligibility conflicts with availability/onset')
        if self.V.shape != (T,n,n):
            raise ValueError('Full white measurement covariance is required')
        for name in ('phi','q','scales'):
            if getattr(self,name).shape != (n,) or not np.isfinite(getattr(self,name)).all():
                raise ValueError('Invalid frozen noise/scales')
        if np.any(np.abs(self.phi) >= 1) or np.any(self.q <= 0) or np.any(self.scales <= 0):
            raise ValueError('Nonstationary AR noise or invalid SD')
        if np.any(self.observed & ~np.isfinite(self.residuals)):
            raise ValueError('Observed residuals must be finite')
        for t in np.flatnonzero(self.available):
            v = self.V[t]
            if not np.isfinite(v).all() or not np.allclose(v,v.T,atol=1e-12,rtol=0) or np.linalg.eigvalsh(v).min() < -1e-12:
                raise ValueError('Invalid white measurement covariance')

    @property
    def use(self):
        gate = np.where(self.times < self.exposure_time, self.available, self.eligible)
        gate &= (self.times >= self.exposure_time) | (self.decision_times <= self.exposure_time)
        return self.observed & gate[:,None]


def observations_from_adjustment(adjusted, model):
    """Validate a public adjustment contract; never recompute/subtract its reference."""
    d = model.to_dict()
    if adjusted.get('model_id') != MODEL_ID or adjusted.get('feature_id') != FEATURE_ID or adjusted.get('policy') != d['policy'] or adjusted.get('canary_ids') != d['canary_ids']:
        raise ValueError('Adjustment and frozen model do not match')
    if adjusted.get('reference_subtractions') != model.policy.factor_rank:
        raise ValueError('Unexpected reference subtraction contract')
    if adjusted.get('noise') != d['noise']:
        raise ValueError('Noise must remain frozen from healthy development')
    if any(float(c) < adjusted['exposure_time'] for c in adjusted['loading_cutoffs']):
        raise ValueError('Early observed exposure: prepare at the actual onset before filtering')
    groups = [d['groups'][d['host_ids'].index(h)] for h in d['canary_ids']]
    noise = [d['noise'][g] for g in groups]
    lam = np.asarray(adjusted['canary_loadings'],float)
    U = np.asarray(adjusted['control_estimation_uncertainty'],float)
    shared = U[:,None,None]*np.outer(lam,lam)[None]
    expected = shared + np.diag([v['v']**2 for v in noise])[None]
    V = np.asarray(adjusted['measurement_covariance'],float)
    if V.shape != expected.shape or not np.allclose(V,expected,atol=1e-12,rtol=1e-10,equal_nan=True):
        raise ValueError('Retain full shared covariance and add it exactly once')
    scales = np.array(d['scales'])[[d['host_ids'].index(h) for h in d['canary_ids']]]
    if not np.array_equal(scales,np.asarray(adjusted['scales'],float)):
        raise ValueError('Reporting scales must remain frozen')
    return Observations(adjusted['event_times'],adjusted['decision_times'],adjusted['residuals'],
        adjusted['observed'],adjusted['availability_eligible'],adjusted['eligible'],V,
        [v['phi'] for v in noise],[v['q'] for v in noise],scales,tuple(d['canary_ids']),
        float(adjusted['exposure_time']),adjusted['run_id'])


class GaussianEffects:
    """Independent/pooled effect maps share the existing linear Gaussian engine."""
    def __init__(self, params=None, kappa=KAPPA):
        self.params = copy.deepcopy(params or EffectParams(kind='indep'))
        p = self.params
        if p.kind not in ('indep','pooled') or p.huber_c != 0:
            raise ValueError('This exact Gaussian adapter supports independent or pooled effects')
        if not all(np.isfinite(x) for x in (p.rho_g,p.sd_g,p.prior_sd,kappa)) or abs(p.rho_g)>1 or p.sd_g<0 or p.prior_sd<=0:
            raise ValueError('Invalid declared effect parameters')
        self.kappa = float(kappa)

    def run(self, data):
        p = self.params; T,n = data.residuals.shape
        L,rho,sd = build_model(p,np.zeros(n,int)); d = L.shape[1]
        return self._run_model(data,L,rho,sd)

    def _run_model(self, data, L, rho, sd, prior_covariance=None, retain_state=False):
        """Shared joint engine; optional full-state output for grouped decomposition."""
        p = self.params; T,n = data.residuals.shape; d = L.shape[1]
        phi,q = data.phi,data.q
        kn = KalmanFilter(np.diag(phi),np.diag(q*q),np.zeros(n),np.diag(q*q/(1-phi*phi)))
        I = np.eye(n); use = data.use
        # Stationary AR initial state one minute before the first input row.
        last = min(float(data.times[0]-60), data.exposure_time)
        for t in np.flatnonzero(data.times < data.exposure_time):
            idx = np.flatnonzero(use[t]); gap = int(round((data.times[t]-last)/60))
            kn.step(data.residuals[t,idx] if len(idx) else None,I[idx],data.V[t][np.ix_(idx,idx)],gap)
            last = float(data.times[t])
        # Carry AR state to exposure. Effect prior exists only at exposure, with
        # exactly prior_sd^2 before that boundary's observation (no extra Q_a yet).
        if last > data.exposure_time:
            raise ValueError('Exposure precedes the supplied preperiod grid')
        kn.predict(int(round((data.exposure_time-last)/60)))
        F = block_diag(np.diag(rho),np.diag(phi))
        Q = block_diag(np.diag(sd*sd),np.diag(q*q))
        m0 = np.r_[np.zeros(d),kn.m]; P0 = block_diag(np.eye(d)*p.prior_sd**2 if prior_covariance is None else prior_covariance,kn.P)
        kf = KalmanFilter(F,Q,m0,P0)
        H = np.hstack([L,I]); A = np.hstack([L,np.zeros((n,n))])
        mean = np.full((T,n),np.nan); cov = np.full((T,n,n),np.nan)
        probs = np.full((T,n),np.nan); score = np.full(T,np.nan); updated = np.zeros(T,bool)
        if retain_state:
            if T*(d+n)**2 > 8_000_000:raise ValueError('Joint covariance budget exceeded')
            state_mean = np.full((T,d+n),np.nan)
            state_covariance = np.full((T,d+n,d+n),np.nan)
        last = data.exposure_time
        for t in np.flatnonzero(data.times >= data.exposure_time):
            gap = int(round((data.times[t]-last)/60)); idx = np.flatnonzero(use[t])
            kf.step(data.residuals[t,idx] if len(idx) else None,H[idx],data.V[t][np.ix_(idx,idx)],gap)
            mean[t] = A @ kf.m; cov[t] = A @ kf.P @ A.T
            if retain_state:
                state_mean[t] = kf.m; state_covariance[t] = kf.P
            zz = (self.kappa-mean[t])/np.sqrt(np.maximum(np.diag(cov[t]),1e-18))
            probs[t] = norm.sf(zz); updated[t] = bool(len(idx))
            if data.eligible[t] and len(idx):score[t] = np.max(norm.logsf(zz))
            last = float(data.times[t])
        result = {'method':p.kind+'_ssm','output_kind':'conditional_gaussian_posterior',
            'score':score,'eligible':data.eligible.copy(),'host_effect_mean':mean,
            'host_effect_covariance':cov,'host_probability':probs,'updated':updated,
            'effect_map':L,'state_transition':F,'process_covariance':Q,
            'prior_at_exposure':{'mean':m0,'covariance':P0,'event_time':data.exposure_time},
            'ar_stationary_initialization':not np.any((data.times<data.exposure_time)&use.any(1)),
            'min_eigenvalue_seen':kf.min_eig_seen,'covariance_floor_events':kf.floor_events,
            'score_contract':'log max-host Pr(effect > kappa); not Pr(any harmful); uncalibrated',
            'kappa':self.kappa,'parameters':vars(p),'calibrated':False}
        if retain_state:
            result.update({'posterior_state_mean':state_mean,'posterior_state_covariance':state_covariance,
                'observation_map':H,'effect_risk_map':A})
        return result


def run_comparison(adjusted, model, params=None):
    """All methods see exactly the same masked residuals; baselines have no posterior."""
    data = observations_from_adjustment(adjusted,model)
    base_params = copy.deepcopy(params or EffectParams(kind='indep'))
    outputs = {}
    for kind in ('indep','pooled'):
        p = copy.deepcopy(base_params); p.kind = kind
        outputs[kind+'_ssm'] = GaussianEffects(p).run(data)
    T,n = data.residuals.shape; t0 = int(np.searchsorted(data.times,data.exposure_time))
    r = np.where(data.use,data.residuals,np.nan)
    adj = Adjusted(r,data.use,data.eligible,np.zeros(T),np.zeros(n),data.scales,
        np.full_like(r,np.nan),np.zeros(n,int),t0,np.zeros(n,bool),np.zeros(T))
    for name in ('adj_ewma','adj_cusum','topk_cusum'):
        # Existing EWMA estimates its normalizer using pre[20:]; do not invent it
        # for short/empty histories and do not change the research implementation.
        enough = name != 'adj_ewma' or (t0>20 and np.all(np.isfinite(r[20:t0]).sum(0)>=2))
        out = run_baseline(name,adj) if enough else None
        outputs[name] = {'method':name,'output_kind':'sequential_statistic','calibrated':False,
            'score':np.where(data.eligible,out.score,np.nan) if out else np.full(T,np.nan),
            'eligible':data.eligible.copy() if enough else np.zeros(T,bool),
            'host_score':out.host_score if out else np.full((T,n),np.nan),
            'host_probability':None,'posterior':None,
            'parameters':out.params if out else {},
            'quality_flags':[] if enough else ['insufficient_preperiod_for_existing_ewma_normalizer']}
    return {'pipeline_id':PIPELINE_ID,'run_id':data.run_id,'host_ids':list(data.host_ids),
        'event_times':data.times,'decision_times':data.decision_times,
        'input_sha256':digest(serial(adjusted)),'used_observations':data.use,
        'outputs':outputs,'thresholds':None,'alarms':None,'dashboard_connected':False,
        'quality_flags':copy.deepcopy(adjusted.get('quality_flags',[])),
        'challenges':copy.deepcopy(adjusted.get('challenges',[])),
        'limitations':['conditional_on_fixed_parameters','no_threshold_calibration',
            'public_latency_model_adequacy_unverified','background_control_contamination_possible']}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True); p.add_argument('--adjusted',required=True)
    p.add_argument('--out',required=True); p.add_argument('--effect-params')
    a = p.parse_args()
    try:
        params = EffectParams(**json.loads(Path(a.effect_params).read_text())) if a.effect_params else None
        result = run_comparison(json.loads(Path(a.adjusted).read_text()),FrozenAdjustment.load(a.model),params)
        target = Path(a.out); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(serial(result),indent=2,allow_nan=False)+'\n')
        print(json.dumps({'output':str(target),'pipeline_id':PIPELINE_ID,'calibrated':False,'dashboard_connected':False}))
    except (ValueError,KeyError,OSError) as exc:
        p.error(str(exc))


if __name__ == '__main__':
    main()
