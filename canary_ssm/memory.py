"""Modeled Process Memory, Growth Channel & Operational Capacity Guardrails (Prompt 9).

Target Definition:
- Resource growth regression consistent with a leak profile, with a declared
  operationally meaningful growth/persistence boundary chosen on development.
- Epistemic boundary: It provides statistical evidence of abnormal, non-reclaimed
  resource growth, NOT mathematical proof of a source code bug.
- Does not label a leak merely because the simulator configured or named a fault MEMORY_LEAK.

Healthy Memory Dynamics:
- Healthy load-dependent memory scaling: memory expands under high request volume / demand
  and recedes when demand drops.
- Garbage collection (GC) cycles: periodic saw-tooth reclamation where temporary in-flight
  allocations are reclaimed every P_gc minutes without ratcheting baseline heap upward.
- Allocator warmup: initial heap growth post-startup before plateauing at steady-state working set.
- Process restarts: abrupt memory drop back to initial footprint upon reboot.

Causal Residual & Differencing Noise:
- Control-adjusted growth contrast: r_{M, it} = Delta M_{it} - Delta bar{M}_{ctrl, t}
  cancels shared demand changes, diurnal cycles, and fleet GC cycles.
- Differencing-induced temporal noise: Differencing white noise xi_t induces an MA(1) error
  Delta xi_t with negative autocorrelation (rho_1 = -0.50) and variance 2 sigma^2.
  We explicitly model the MA(1) differencing state in a state-space formulation:
    s_i = [drift_i, xi_{i, t}, xi_{i, t-1}]^T,  H = [1, 1, -1]
  absorbing the differencing artifact and producing exact, consistent growth estimates.

Operational Guardrail:
- Absolute capacity and Time-To-Exhaustion (TTE = Headroom / max(growth_rate, epsilon))
  are tracked as a distinct operational guardrail separate from the statistical leak detector.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.stats import norm

from canary_ssm.telemetry import TelemetryRecord


@dataclass
class MemoryTargetDefinition:
    """Declared detection target and operational boundaries for resource growth regression.

    Chosen strictly on healthy development data prior to threshold calibration.
    """
    growth_boundary_mb_per_min: float = 0.50      # Declared boundary kappa_M (MB/min)
    persistence_window_ticks: int = 15            # Minimum consecutive ticks required for persistent alert
    headroom_warning_mb: float = 2048.0           # Capacity warning headroom threshold (MB)
    headroom_critical_mb: float = 1024.0          # Capacity critical headroom threshold (MB)
    tte_warning_min: float = 120.0                # Time-to-exhaustion warning boundary (minutes)
    tte_critical_min: float = 30.0                # Time-to-exhaustion critical boundary (minutes)
    disclaimer: str = (
        "Statistical evidence of abnormal resource growth consistent with a leak profile. "
        "This is evidence of resource growth regression, not formal verification of source code."
    )


@dataclass
class MemoryStepResult:
    """Output of a single discrete tick update from the Memory Growth Channel."""
    tick: int
    score: float                                  # Release score (max log exceedance probability, NaN before t0)
    host_scores: np.ndarray                       # (nc,) host-level log exceedance probabilities
    growth_rate_estimates: np.ndarray             # (nc,) estimated growth rate in MB/min (hat{g}_{it})
    growth_rate_se: np.ndarray                    # (nc,) standard error of growth rate estimate
    host_probs: np.ndarray                        # (nc,) Pr(drift_{it} > kappa_M)
    host_headroom_mb: np.ndarray                  # (nc,) capacity headroom (MB)
    host_tte_min: np.ndarray                      # (nc,) estimated Time-To-Exhaustion in minutes
    guardrail_status: str                         # NORMAL | PRESSURE | CRITICAL_OOM_RISK
    is_persistent_leak: bool                      # True if growth > kappa_M for >= persistence_window ticks
    growth_residuals: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=float))
    eligible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class OperationalMemoryGuardrail:
    """Operational guardrail evaluating absolute physical memory capacity and OOM risk.

    Independent of statistical growth rate hypothesis tests.
    """
    def __init__(self, target_def: MemoryTargetDefinition | None = None) -> None:
        self.target_def = target_def or MemoryTargetDefinition()

    def evaluate(
        self,
        memory_mb: np.ndarray,
        capacities_mb: np.ndarray,
        growth_rates: np.ndarray,
    ) -> tuple[str, np.ndarray, np.ndarray]:
        """Compute headroom, Time-To-Exhaustion (TTE), and guardrail advisory status.

        Returns:
            (status, headroom_mb, tte_min)
            status: "NORMAL" | "PRESSURE" | "CRITICAL_OOM_RISK"
        """
        mem = np.asarray(memory_mb, float)
        caps = np.asarray(capacities_mb, float)
        rates = np.asarray(growth_rates, float)

        headroom = np.maximum(0.0, caps - mem)
        utilization = mem / np.maximum(1.0, caps)

        # Time to exhaustion: TTE = headroom / max(rate, epsilon)
        tte = np.full(len(mem), float("inf"), dtype=float)
        growing = rates > 0.05
        tte[growing] = headroom[growing] / np.maximum(rates[growing], 0.01)

        min_headroom = float(np.min(headroom)) if len(headroom) else float("inf")
        max_util = float(np.max(utilization)) if len(utilization) else 0.0
        min_tte = float(np.min(tte)) if len(tte) else float("inf")

        if (
            max_util >= 0.85
            or min_headroom <= self.target_def.headroom_critical_mb
            or min_tte <= self.target_def.tte_critical_min
        ):
            status = "CRITICAL_OOM_RISK"
        elif (
            max_util >= 0.70
            or min_headroom <= self.target_def.headroom_warning_mb
            or min_tte <= self.target_def.tte_warning_min
        ):
            status = "PRESSURE"
        else:
            status = "NORMAL"

        return status, headroom, tte


class OnlineMemoryGrowthDetector:
    """Streaming Memory Growth Detector accounting for differencing noise and control contrast.

    Formulation:
    - Control-adjusted growth residual: r_{M, it} = Delta M_{it} - Delta bar{M}_{ctrl, t}
    - State-Space Model for differencing-induced MA(1) temporal noise:
        State for host i: s_i = [drift_i, xi_{i, t}, xi_{i, t-1}]^T
        Transition: F = [[1, 0, 0], [0, 0, 0], [0, 1, 0]]
        Process Noise: Q = diag([q_drift^2, sigma_M^2, 0])
        Observation Matrix: H = [1, 1, -1]
        Measurement Noise: R = sigma_M^2 / |C_t| (control estimation error)
    - Directly tracks growth rate hat{g}_{it} = s_i[0] and posterior variance P_i[0, 0].
    - Computes exceedance probability Pr(drift_{it} > kappa_M) and log max-host risk score.
    - Evaluates persistence window and operational capacity guardrail.
    """

    def __init__(
        self,
        t0: int,
        canary_ids: list[str],
        control_ids: list[str],
        canary_capacities_mb: list[float] | np.ndarray,
        target_definition: MemoryTargetDefinition | None = None,
        sigma_m: float = 20.0,
        q_drift: float = 0.0,
        prior_drift_sd: float = 1.0,
    ) -> None:
        self.t0 = int(t0)
        self.canary_ids = list(canary_ids)
        self.control_ids = list(control_ids)
        self.nc = len(self.canary_ids)
        self.capacities = np.asarray(canary_capacities_mb, float)
        self.target_def = target_definition or MemoryTargetDefinition()
        self.kappa = float(self.target_def.growth_boundary_mb_per_min)
        self.sigma_m = float(sigma_m)
        self.q_drift = float(q_drift)
        self.prior_drift_sd = float(prior_drift_sd)

        # State transition and observation matrices for MA(1) differencing
        # State: [drift, xi_t, xi_{t-1}]
        self.F = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ], dtype=float)

        self.Q = np.diag([self.q_drift ** 2, self.sigma_m ** 2, 0.0])
        self.H = np.array([[1.0, 1.0, -1.0]], dtype=float)

        self.guardrail = OperationalMemoryGuardrail(self.target_def)
        self.reset()

    def reset(self) -> None:
        """Reset internal filter states and accumulators."""
        self.prev_canary_mem: np.ndarray | None = None
        self.prev_ctrl_mem: dict[str, float] = {}

        # Kalman state per canary host: (nc, 3)
        self.m = np.zeros((self.nc, 3), dtype=float)
        # Covariance per canary host: (nc, 3, 3)
        self.P = np.zeros((self.nc, 3, 3), dtype=float)
        for i in range(self.nc):
            self.P[i] = np.diag([self.prior_drift_sd ** 2, self.sigma_m ** 2, self.sigma_m ** 2])

        # Persistence counters
        self.ticks_above_kappa = np.zeros(self.nc, dtype=int)

    def step(
        self,
        tick: int,
        canary_records: dict[str, TelemetryRecord],
        control_records: dict[str, TelemetryRecord],
        eligible: bool = True,
    ) -> MemoryStepResult:
        """Process one discrete tick of memory observations causally."""
        nc = self.nc

        current_canary_mem = np.array([
            canary_records[cid].memory_mb if cid in canary_records and canary_records[cid].observed else np.nan
            for cid in self.canary_ids
        ])

        # Step 1: Compute control growth baseline (Delta bar{M}_{ctrl, t})
        ctrl_deltas: list[float] = []
        for ctl_id in self.control_ids:
            if ctl_id in control_records and control_records[ctl_id].observed:
                m_curr = control_records[ctl_id].memory_mb
                if ctl_id in self.prev_ctrl_mem:
                    ctrl_deltas.append(m_curr - self.prev_ctrl_mem[ctl_id])
                self.prev_ctrl_mem[ctl_id] = m_curr

        ctrl_growth_mean = float(np.mean(ctrl_deltas)) if ctrl_deltas else 0.0
        n_ctrl_eff = max(len(ctrl_deltas), 1)

        # Measurement noise R includes control estimation variance
        R_val = (self.sigma_m ** 2) / float(n_ctrl_eff)

        # Step 2: Compute canary increments and control-adjusted residuals
        growth_residuals = np.zeros(nc, dtype=float)
        valid_deltas = np.zeros(nc, dtype=bool)

        if self.prev_canary_mem is not None:
            raw_deltas = current_canary_mem - self.prev_canary_mem
            valid_deltas = np.isfinite(raw_deltas)
            growth_residuals[valid_deltas] = raw_deltas[valid_deltas] - ctrl_growth_mean

        if self.prev_canary_mem is None:
            self.prev_canary_mem = current_canary_mem.copy()
        else:
            valid = np.isfinite(current_canary_mem)
            self.prev_canary_mem[valid] = current_canary_mem[valid]

        # Invariant 4: Rollout Onset Reset at tick == t0
        # Initialize proper nonzero effect prior with variance prior_drift_sd^2
        if tick == self.t0:
            self.m[:, 0] = 0.0
            for i in range(nc):
                self.P[i, 0, 0] = self.prior_drift_sd ** 2
            self.ticks_above_kappa.fill(0)

        # Step 3: Kalman Filter Step per host (accounting for MA(1) differencing)
        for i in range(nc):
            # Time update (prediction)
            self.m[i] = self.F @ self.m[i]
            self.P[i] = self.F @ self.P[i] @ self.F.T + self.Q

            # Measurement update if observation is valid
            if valid_deltas[i]:
                y = growth_residuals[i]
                # If host restarted (huge negative delta), reset drift state cleanly
                if y < -100.0:
                    self.m[i, 0] = 0.0
                    self.P[i, 0, 0] = self.prior_drift_sd ** 2
                    self.ticks_above_kappa[i] = 0
                    continue

                S = float((self.H @ self.P[i] @ self.H.T)[0, 0] + R_val)
                K = (self.P[i] @ self.H.T) / max(S, 1e-8)  # (3, 1)
                v = y - float((self.H @ self.m[i])[0])
                self.m[i] = self.m[i] + K[:, 0] * v

                # Joseph-form covariance update for numerical stability
                I_KH = np.eye(3) - K @ self.H
                self.P[i] = I_KH @ self.P[i] @ I_KH.T + K * R_val @ K.T

        # Extract growth rate estimates hat{g}_i and standard errors
        growth_rates = self.m[:, 0].copy()
        growth_se = np.sqrt(np.maximum(self.P[:, 0, 0], 1e-12))

        # Operational capacity guardrail
        status, headroom, tte = self.guardrail.evaluate(
            current_canary_mem, self.capacities, growth_rates
        )

        # Pre-period Phase (tick < t0)
        if tick < self.t0:
            self.ticks_above_kappa.fill(0)
            return MemoryStepResult(
                tick=tick,
                score=np.nan,
                host_scores=np.full(nc, np.nan),
                growth_rate_estimates=growth_rates,
                growth_rate_se=growth_se,
                host_probs=np.full(nc, np.nan),
                host_headroom_mb=headroom,
                host_tte_min=tte,
                guardrail_status=status,
                is_persistent_leak=False,
                eligible=eligible,
            )

        # Rollout Phase (tick >= t0)
        # Probability that true drift exceeds boundary kappa_M: Pr(drift_i > kappa_M)
        zz = (self.kappa - growth_rates) / growth_se
        host_probs = norm.sf(zz)

        # Release score = max host log-risk score (monotone, no underflow)
        host_log_probs = norm.logsf(zz)
        score = float(np.nanmax(host_log_probs)) if eligible else np.nan

        # Persistence window tracking
        above = growth_rates > self.kappa
        self.ticks_above_kappa[above] += 1
        self.ticks_above_kappa[~above] = 0
        is_persistent = bool(np.any(self.ticks_above_kappa >= self.target_def.persistence_window_ticks))

        return MemoryStepResult(
            tick=tick,
            score=score,
            host_scores=host_log_probs,
            growth_rate_estimates=growth_rates,
            growth_rate_se=growth_se,
            host_probs=host_probs,
            host_headroom_mb=headroom,
            host_tte_min=tte,
            guardrail_status=status,
            is_persistent_leak=is_persistent,
            growth_residuals=growth_residuals.copy(),
            eligible=eligible,
            metadata={
                "ticks_above_kappa": self.ticks_above_kappa.tolist(),
                "ctrl_growth_mean": ctrl_growth_mean,
            },
        )
