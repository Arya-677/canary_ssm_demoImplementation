"""Unified streaming detector update interface (handbook Sections 6, 7, 8).

Wraps:
- EWMA (`adj_ewma`)
- CUSUM (`adj_cusum`)
- Top-K CUSUM (`topk_cusum`)
- Independent host SSM (`indep_ssm`)
- Complete pooling SSM (`pooled_ssm`)
- Hierarchical SSM (`hier_ssm`)

Behind ONE uniform, causal online update interface:
    step(tick, r_t, obs_mask_t, V_t, eligible) -> DetectorStepResult

Key Invariants:
1. Causal streaming parity: Stepping tick-by-tick produces results identical to batch run(adj).
2. Consistent observations & masks: All detectors consume the same adjusted residuals r_it,
   sigma_i, and observation masks.
3. Pre-period carryover: SSMs track AR noise during pre-period and carry (m, P) into rollout.
4. Nonzero proper effect prior: Initialized at exposure t0 with variance prior_sd^2.
5. Pooled covariance propagation: Complete pooling SSM correctly propagates P_theta,
   cross-covariance P_{theta, e}, and observation noise via Joseph-form updates.
6. Separation of scores and thresholds: Detectors output raw release scores; threshold
   calibration is performed separately in decision.py without tuning on test scenarios.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from scipy.linalg import block_diag
from scipy.stats import norm

from .baselines import DetectorOutput
from .factor import Adjusted
from .hierarchy import EffectParams, build_model, class_structure, effect_prior_variance
from .kalman import KalmanFilter
from .preprocess import Nuisance
from .schema import KAPPA


@dataclass
class DetectorStepResult:
    """Output of a single discrete tick update from any detector."""
    tick: int
    score: float                         # Release score (NaN before t0 or when ineligible)
    host_scores: np.ndarray              # (nc,) host-level score / accumulator
    host_probs: np.ndarray | None = None # (nc,) Pr(a_it > kappa) for SSMs
    eligible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    class_effects: np.ndarray | None = None      # (G,) class effect posterior means theta
    host_deviations: np.ndarray | None = None    # (nc,) within-class local deviations B b
    effect_cov: np.ndarray | None = None         # (nc, nc) full posterior covariance L P L^T


class StreamingDetector(ABC):
    """Abstract base class for streaming online release detectors."""

    def __init__(self, name: str, t0: int, n_canaries: int):
        self.name = name
        self.t0 = t0
        self.nc = n_canaries

    @abstractmethod
    def reset(self) -> None:
        """Reset internal accumulator / filter state."""
        ...

    @abstractmethod
    def step(
        self,
        tick: int,
        r_t: np.ndarray,
        obs_mask: np.ndarray,
        V_t: np.ndarray | None = None,
        eligible: bool = True,
    ) -> DetectorStepResult:
        """Process one discrete time slice at `tick`."""
        ...

    def run(self, adj: Adjusted) -> DetectorOutput:
        """Run detector across full batch of Adjusted data, matching step() exactly."""
        self.reset()
        T = adj.r.shape[0]
        scores = np.full(T, np.nan)
        host_scores = np.full((T, self.nc), np.nan)
        host_probs = np.full((T, self.nc), np.nan) if isinstance(self, StreamingSSMDetector) else None

        # Diagnostic hierarchical outputs (SSMs only)
        if isinstance(self, StreamingSSMDetector) and hasattr(self, "C") and getattr(self, "C").ndim == 2:
            G = self.C.shape[1]
            class_effects = np.full((T, G), np.nan)
            host_deviations = np.full((T, self.nc), np.nan)
            effect_cov = np.full((T, self.nc, self.nc), np.nan)
        else:
            class_effects = None
            host_deviations = None
            effect_cov = None

        for t in range(T):
            V_t = None
            if hasattr(adj, "cov_U") and adj.cov_U is not None:
                V_t = adj.cov_U[t]
            elif hasattr(adj, "U") and np.isfinite(adj.U[t]):
                V_t = np.outer(adj.lam, adj.lam) * adj.U[t]

            res = self.step(
                tick=t,
                r_t=adj.r[t],
                obs_mask=adj.obs[t],
                V_t=V_t,
                eligible=bool(adj.elig[t]),
            )
            scores[t] = res.score
            host_scores[t] = res.host_scores
            if host_probs is not None and res.host_probs is not None:
                host_probs[t] = res.host_probs
            if class_effects is not None and res.class_effects is not None:
                class_effects[t] = res.class_effects
            if host_deviations is not None and res.host_deviations is not None:
                host_deviations[t] = res.host_deviations
            if effect_cov is not None and res.effect_cov is not None:
                effect_cov[t] = res.effect_cov

        return DetectorOutput(
            method=self.name,
            score=scores,
            elig=adj.elig,
            host_score=host_scores,
            host_prob=host_probs,
            params=getattr(self, "params", {}),
            class_effects=class_effects,
            host_deviations=host_deviations,
            effect_cov=effect_cov,
        )


class OnlineEWMA(StreamingDetector):
    """Streaming Exponentially Weighted Moving Average on standardized residuals."""

    def __init__(self, t0: int, n_canaries: int, sigma: np.ndarray, alpha: float = 0.2):
        super().__init__("adj_ewma", t0, n_canaries)
        self.alpha = float(alpha)
        self.sigma = np.asarray(sigma, float)
        self.params = {"alpha": self.alpha}
        self.reset()

    def reset(self) -> None:
        self.S = np.zeros(self.nc)
        self._pre_history: list[np.ndarray] = []
        self._scale: np.ndarray = np.ones(self.nc)
        self._pre_scale_computed = False

    def step(
        self,
        tick: int,
        r_t: np.ndarray,
        obs_mask: np.ndarray,
        V_t: np.ndarray | None = None,
        eligible: bool = True,
    ) -> DetectorStepResult:
        z = r_t / self.sigma
        ok = obs_mask & np.isfinite(z)

        if tick < self.t0:
            # Pre-period warm-up
            self.S[ok] = self.alpha * z[ok] + (1.0 - self.alpha) * self.S[ok]
            self._pre_history.append(self.S.copy())
            return DetectorStepResult(
                tick=tick,
                score=np.nan,
                host_scores=np.full(self.nc, np.nan),
                eligible=eligible,
            )

        # First tick of rollout: freeze pre-period EWMA scale and reset accumulator
        if not self._pre_scale_computed:
            if len(self._pre_history) > 20:
                pre_arr = np.array(self._pre_history)
                self._scale = np.maximum(np.nanstd(pre_arr[20:], axis=0), 1e-6)
            else:
                self._scale = np.ones(self.nc)
            self._pre_scale_computed = True
            self.S = np.zeros(self.nc)

        # Rollout update
        self.S[ok] = self.alpha * z[ok] + (1.0 - self.alpha) * self.S[ok]
        host = self.S / self._scale
        score = float(np.nanmax(host)) if eligible else np.nan

        return DetectorStepResult(
            tick=tick,
            score=score,
            host_scores=host.copy(),
            eligible=eligible,
        )


class OnlineCUSUM(StreamingDetector):
    """Streaming Tabular Cumulative Sum on standardized residuals."""

    def __init__(self, t0: int, n_canaries: int, sigma: np.ndarray, k: float = 0.25):
        super().__init__("adj_cusum", t0, n_canaries)
        self.k = float(k)
        self.sigma = np.asarray(sigma, float)
        self.params = {"k": self.k}
        self.reset()

    def reset(self) -> None:
        self.C = np.zeros(self.nc)

    def step(
        self,
        tick: int,
        r_t: np.ndarray,
        obs_mask: np.ndarray,
        V_t: np.ndarray | None = None,
        eligible: bool = True,
    ) -> DetectorStepResult:
        if tick < self.t0:
            return DetectorStepResult(
                tick=tick,
                score=np.nan,
                host_scores=np.full(self.nc, np.nan),
                eligible=eligible,
            )

        z = r_t / self.sigma
        ok = obs_mask & np.isfinite(z)
        self.C[ok] = np.maximum(0.0, self.C[ok] + z[ok] - self.k)

        score = float(np.nanmax(self.C)) if eligible else np.nan
        return DetectorStepResult(
            tick=tick,
            score=score,
            host_scores=self.C.copy(),
            eligible=eligible,
        )


class OnlineTopKCUSUM(StreamingDetector):
    """Streaming Top-K CUSUM: sums the K largest host CUSUM accumulators."""

    def __init__(self, t0: int, n_canaries: int, sigma: np.ndarray, K: int = 3, k: float = 0.25):
        super().__init__("topk_cusum", t0, n_canaries)
        self.K = int(K)
        self.k = float(k)
        self.sigma = np.asarray(sigma, float)
        self.params = {"K": self.K, "k": self.k}
        self.reset()

    def reset(self) -> None:
        self.C = np.zeros(self.nc)

    def step(
        self,
        tick: int,
        r_t: np.ndarray,
        obs_mask: np.ndarray,
        V_t: np.ndarray | None = None,
        eligible: bool = True,
    ) -> DetectorStepResult:
        if tick < self.t0:
            return DetectorStepResult(
                tick=tick,
                score=np.nan,
                host_scores=np.full(self.nc, np.nan),
                eligible=eligible,
            )

        z = r_t / self.sigma
        ok = obs_mask & np.isfinite(z)
        self.C[ok] = np.maximum(0.0, self.C[ok] + z[ok] - self.k)

        sorted_c = np.sort(np.nan_to_num(self.C, nan=0.0))[::-1]
        score = float(np.sum(sorted_c[:self.K])) if eligible else np.nan

        return DetectorStepResult(
            tick=tick,
            score=score,
            host_scores=self.C.copy(),
            eligible=eligible,
        )


class StreamingSSMDetector(StreamingDetector):
    """Generic base class for streaming State-Space Model detectors.

    Handles pre-period AR noise tracking and proper rollout effect prior initialization.
    Supports complete pooling, independent, and hierarchical state representations.
    """

    def __init__(
        self,
        name: str,
        kind: str,
        nuis: Nuisance,
        params: EffectParams,
        t0: int,
        class_id: np.ndarray,
        lam: np.ndarray,
        sigma: np.ndarray,
        kappa: float = KAPPA,
    ):
        super().__init__(name, t0, len(class_id))
        self.kind = kind
        self.nuis = nuis
        self.params_obj = params
        self.class_id = np.asarray(class_id, int)
        self.lam = np.asarray(lam, float)
        self.sigma = np.asarray(sigma, float)
        self.kappa = float(kappa)
        self.params = {"kind": kind, "rho_g": params.rho_g, "sd_g": params.sd_g, "prior_sd": params.prior_sd}

        p_copy = EffectParams(**{**params.__dict__, "kind": kind})
        self.params_obj = p_copy
        self.L, self.rho, self.sd = build_model(p_copy, self.class_id)
        self.d = self.L.shape[1]
        if self.kind == "hier":
            self.C, self.B = class_structure(self.class_id)
        elif self.kind == "pooled":
            self.C = np.ones((self.nc, 1), dtype=float)
            self.B = np.zeros((self.nc, 0), dtype=float)
        else: # indep
            self.C = np.eye(self.nc, dtype=float)
            self.B = np.zeros((self.nc, 0), dtype=float)

        # AR noise parameters per canary class
        self.phi = np.array([nuis.phi_e[g] for g in self.class_id])
        self.qe = np.array([nuis.q_e[g] for g in self.class_id])
        self.vv = np.array([nuis.v[g] for g in self.class_id])

        self.reset()

    def reset(self) -> None:
        # Pre-period filter: noise-only AR(1) state
        self.kn = KalmanFilter(
            np.diag(self.phi),
            np.diag(self.qe ** 2),
            np.zeros(self.nc),
            np.diag(self.qe ** 2 / (1.0 - self.phi ** 2)),
        )
        self.I_n = np.eye(self.nc)

        # Rollout filter state (initialized at t0)
        self.kf: KalmanFilter | None = None
        self.H = np.hstack([self.L, np.eye(self.nc)])
        self.Lfull = np.hstack([self.L, np.zeros((self.nc, self.nc))])

    def _V(self, V_t: np.ndarray | None) -> np.ndarray:
        if V_t is not None and np.isfinite(V_t).all():
            return np.diag(self.vv ** 2) + V_t
        return np.diag(self.vv ** 2)

    def step(
        self,
        tick: int,
        r_t: np.ndarray,
        obs_mask: np.ndarray,
        V_t: np.ndarray | None = None,
        eligible: bool = True,
    ) -> DetectorStepResult:
        R = r_t.copy()
        if self.params_obj.huber_c > 0:
            clip_val = self.params_obj.huber_c * self.sigma
            R = np.clip(R, -clip_val, clip_val)

        # -------------------------------------------------------------
        # Phase 1: Pre-period (tick < t0)
        # -------------------------------------------------------------
        if tick < self.t0:
            use = obs_mask & eligible & np.isfinite(R)
            if use.any():
                idx = np.flatnonzero(use)
                V = self._V(V_t)
                self.kn.step(R[idx], self.I_n[idx], V[np.ix_(idx, idx)])
            else:
                self.kn.step()

            return DetectorStepResult(
                tick=tick,
                score=np.nan,
                host_scores=np.full(self.nc, np.nan),
                host_probs=np.full(self.nc, np.nan),
                eligible=eligible,
            )

        # -------------------------------------------------------------
        # Phase 2: Rollout Transition (at tick == t0)
        # -------------------------------------------------------------
        if self.kf is None:
            # Carry pre-period noise state kn.m and covariance kn.P
            # Initialize proper nonzero effect prior with variance prior_sd^2
            F = block_diag(np.diag(self.rho), np.diag(self.phi))
            Q = block_diag(np.diag(self.sd ** 2), np.diag(self.qe ** 2))
            m0 = np.r_[np.zeros(self.d), self.kn.m]
            p0_eff = effect_prior_variance(self.params_obj, self.class_id)
            P0 = block_diag(np.diag(p0_eff), self.kn.P)
            self.kf = KalmanFilter(F, Q, m0, P0)

        # -------------------------------------------------------------
        # Phase 3: Rollout Step (tick >= t0)
        # -------------------------------------------------------------
        use = obs_mask & eligible & np.isfinite(R)
        if use.any():
            idx = np.flatnonzero(use)
            V = self._V(V_t)
            self.kf.step(R[idx], self.H[idx], V[np.ix_(idx, idx)])
        else:
            self.kf.step()

        # Compute host effect posterior means and variances
        am = self.Lfull @ self.kf.m
        cov_mat = self.L @ self.kf.P[:self.d, :self.d] @ self.L.T
        av = np.maximum(np.diag(cov_mat), 1e-18)
        zz = (self.kappa - am) / np.sqrt(av)

        host_probs = norm.sf(zz)
        # Release score = log max-host risk: monotone in max-host risk, avoids underflow
        score = float(np.nanmax(norm.logsf(zz))) if eligible else np.nan

        G = self.C.shape[1]
        if self.kind == "hier":
            class_effects = self.kf.m[:G].copy()
            if self.B.shape[1] > 0:
                host_deviations = (self.B @ self.kf.m[G:self.d]).copy()
            else:
                host_deviations = np.zeros(self.nc)
        elif self.kind == "pooled":
            class_effects = self.kf.m[0:1].copy()
            host_deviations = np.zeros(self.nc)
        elif self.kind == "indep":
            class_effects = self.kf.m[:self.nc].copy()
            host_deviations = np.zeros(self.nc)
        else:
            class_effects = None
            host_deviations = None

        return DetectorStepResult(
            tick=tick,
            score=score,
            host_scores=am.copy(),
            host_probs=host_probs,
            eligible=eligible,
            metadata={"min_eig": self.kf.min_eig_seen, "floor_events": self.kf.floor_events},
            class_effects=class_effects,
            host_deviations=host_deviations,
            effect_cov=cov_mat,
        )


class OnlineIndependentSSM(StreamingSSMDetector):
    """Streaming Independent Host SSM (one effect state per canary, no cross-canary pooling)."""

    def __init__(
        self,
        nuis: Nuisance,
        params: EffectParams,
        t0: int,
        class_id: np.ndarray,
        lam: np.ndarray,
        sigma: np.ndarray,
        kappa: float = KAPPA,
    ):
        super().__init__("indep_ssm", "indep", nuis, params, t0, class_id, lam, sigma, kappa)


class OnlinePooledSSM(StreamingSSMDetector):
    """Streaming Complete Pooling SSM (single release effect theta shared across all canaries).

    Propagates pooled release variance P_theta and cross-covariances correctly.
    """

    def __init__(
        self,
        nuis: Nuisance,
        params: EffectParams,
        t0: int,
        class_id: np.ndarray,
        lam: np.ndarray,
        sigma: np.ndarray,
        kappa: float = KAPPA,
    ):
        super().__init__("pooled_ssm", "pooled", nuis, params, t0, class_id, lam, sigma, kappa)


class OnlineHierarchicalSSM(StreamingSSMDetector):
    """Streaming Hierarchical Effect SSM (class effects + sum-zero local host deviations)."""

    def __init__(
        self,
        nuis: Nuisance,
        params: EffectParams,
        t0: int,
        class_id: np.ndarray,
        lam: np.ndarray,
        sigma: np.ndarray,
        kappa: float = KAPPA,
    ):
        super().__init__("hier_ssm", "hier", nuis, params, t0, class_id, lam, sigma, kappa)


def create_streaming_detector(
    name: str,
    t0: int,
    class_id: np.ndarray,
    sigma: np.ndarray,
    lam: np.ndarray | None = None,
    nuis: Nuisance | None = None,
    params: EffectParams | None = None,
    **kwargs: Any,
) -> StreamingDetector:
    """Unified factory instantiating any supported streaming detector behind one interface."""
    nc = len(class_id)
    if lam is None:
        lam = np.ones(nc)
    if params is None:
        params = EffectParams()

    known_baselines = ("adj_ewma", "ewma", "adj_cusum", "cusum", "topk_cusum", "topk")
    known_ssms = ("indep_ssm", "indep", "pooled_ssm", "pooled", "hier_ssm", "hier")

    if name not in known_baselines and name not in known_ssms:
        raise ValueError(f"Unknown detector name: '{name}'. Supported: adj_ewma, adj_cusum, topk_cusum, indep_ssm, pooled_ssm, hier_ssm")

    if name in ("adj_ewma", "ewma"):
        alpha = float(kwargs.get("alpha", 0.2))
        return OnlineEWMA(t0=t0, n_canaries=nc, sigma=sigma, alpha=alpha)

    if name in ("adj_cusum", "cusum"):
        k = float(kwargs.get("k", 0.25))
        return OnlineCUSUM(t0=t0, n_canaries=nc, sigma=sigma, k=k)

    if name in ("topk_cusum", "topk"):
        k = float(kwargs.get("k", 0.25))
        K = int(kwargs.get("K", 3))
        return OnlineTopKCUSUM(t0=t0, n_canaries=nc, sigma=sigma, K=K, k=k)

    if nuis is None:
        raise ValueError(f"SSM detector '{name}' requires fitted Nuisance object")

    if name in ("indep_ssm", "indep"):
        return OnlineIndependentSSM(nuis, params, t0, class_id, lam, sigma)

    if name in ("pooled_ssm", "pooled"):
        return OnlinePooledSSM(nuis, params, t0, class_id, lam, sigma)

    if name in ("hier_ssm", "hier"):
        return OnlineHierarchicalSSM(nuis, params, t0, class_id, lam, sigma)
