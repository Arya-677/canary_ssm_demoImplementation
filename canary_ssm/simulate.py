"""Reproducible simulator (handbook Section 4).

  y_it = mu_i + beta_i x_t (+ gamma x_t^2) + lambda_i f_t + d_it a_it + e_it + nu_it
  f_t  = phi_f f_{t-1} + u_t + shock_t          (shared factor, shock at rollout)
  e_it = phi_e e_{i,t-1} + xi_it                (host AR noise; optional heavy tails)
  latency_ms = exp(y)

Independent RNG streams per random ingredient. Paired null/harm rollouts built from the same
seed share every exogenous array and differ ONLY in the injection `d*a` (and contamination spill).
Truth is returned separately and must never be imported by detector code.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from pathlib import Path

import numpy as np

from .schema import Rollout, dict_hash

STREAMS = ["meta", "workload", "factor", "noise", "meas", "exposure", "effect", "missing", "tails", "labels"]


@dataclass
class SimConfig:
    family: str = "baseline"
    n_hosts: int = 100
    n_canary: int = 10
    n_classes: int = 2
    t_pre: int = 180
    t_post: int = 120
    # nuisance dynamics (log units) -- handbook "smoke case" defaults
    phi_f: float = 0.8
    sd_f: float = 0.01
    sd_host: float = 0.01
    phi_e: float = 0.6
    meas_sd: float = 0.0            # optional white measurement noise (handoff: {0, 0.01}); weakly identifiable
    mu_ms: float = 100.0
    host_mu_sd: float = 0.10
    class_mu_offset: float = 0.10
    beta: float = 0.15
    beta_jitter: float = 0.03
    lam: float = 1.0
    lam_class_sd: float = 0.05
    lam_host_sd: float = 0.05
    shock: float = float(np.log(1.05))   # shared factor shock at rollout
    # workload
    workload_sd: float = 0.03
    workload_phi: float = 0.95
    workload_step: float = 0.0           # SUSTAINED shared workload step at rollout; 0.3365 = log(1.4) -> ~+5% on every host
    nonlinear_gamma: float = 0.0         # unmodeled quadratic workload response (stress)
    post_loading_scale: float = 1.0      # canary/control loadings change post rollout (stress)
    heavy_tail_df: float = 0.0           # >0 -> Student-t host innovations (stress)
    # injected effect
    n_affected: int = 3
    affected_mode: str = "random"        # random | class0 (all canaries of true class 0)
    label_error: float = 0.0             # fraction of canary class labels the DETECTOR sees wrongly
    effect_pct: float = 3.0
    duration: int = 45
    onset_delay: int = 0
    shape: str = "abrupt"                # abrupt | ramp
    ramp_len: int = 10
    decay_len: int = 0                   # linear recovery length after `duration`
    contam_frac: float = 0.0             # fraction of controls receiving spill (stress)
    contam_scale: float = 0.5
    # data availability
    missing_rate: float = 0.0
    burst_len: int = 0                   # class-wide canary dropout burst (minutes)
    late_frac: float = 0.0
    late_delay: int = 3

    @staticmethod
    def from_dict(d: dict) -> "SimConfig":
        names = {f.name for f in fields(SimConfig)}
        bad = set(d) - names
        if bad:
            raise KeyError(f"unknown SimConfig keys: {sorted(bad)}")
        return SimConfig(**d)


@dataclass
class Truth:
    """EVALUATOR-ONLY."""
    rollout_id: str
    a: np.ndarray            # (T,N) injected exposed-host effect in log units
    spill: np.ndarray        # (T,N) contamination of controls
    factor: np.ndarray       # (T,)
    noise: np.ndarray        # (T,N) latent AR noise
    affected_hosts: list
    harm: bool
    family: str
    seed: int
    pair_id: int
    t0: int
    config: dict = field(default_factory=dict)

    def save(self, path: Path, compact: bool = False) -> None:
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        import json
        payload = dict(rollout_id=self.rollout_id, a=self.a, factor=self.factor,
                       affected_hosts=np.array(self.affected_hosts, int), harm=self.harm,
                       family=self.family, seed=self.seed, pair_id=self.pair_id, t0=self.t0,
                       config=json.dumps(self.config))
        if not compact:
            payload["spill"] = self.spill
            payload["noise"] = self.noise
        np.savez_compressed(path, **payload)

    @staticmethod
    def load(path: Path) -> "Truth":
        import json
        z = np.load(path, allow_pickle=False)
        a = z["a"]
        spill = z["spill"] if "spill" in z else np.zeros_like(a)
        noise = z["noise"] if "noise" in z else np.zeros_like(a)
        return Truth(str(z["rollout_id"]), a, spill, z["factor"], noise,
                     z["affected_hosts"].tolist(), bool(z["harm"]), str(z["family"]),
                     int(z["seed"]), int(z["pair_id"]), int(z["t0"]), json.loads(str(z["config"])))


def _streams(seed: int) -> dict:
    return {n: np.random.default_rng(np.random.SeedSequence([int(seed), i]))
            for i, n in enumerate(STREAMS)}


def _ar1(T, phi, innov):
    """AR(1) along axis 0 from pre-scaled innovations, started from a stationary draw."""
    out = np.empty_like(innov)
    out[0] = innov[0] / np.sqrt(1 - phi ** 2)      # Var = sd^2 / (1 - phi^2)
    for t in range(1, T):
        out[t] = phi * out[t - 1] + innov[t]
    return out


def effect_profile(cfg: SimConfig, T: int, t0: int) -> np.ndarray:
    """Time profile of the (log) effect for one affected host, length T."""
    mag = float(np.log1p(cfg.effect_pct / 100.0))
    prof = np.zeros(T)
    t_on = t0 + cfg.onset_delay
    t_off = min(T, t_on + cfg.duration)
    if cfg.shape == "ramp":
        for k, t in enumerate(range(t_on, t_off)):
            prof[t] = mag * min(1.0, (k + 1) / max(cfg.ramp_len, 1))
    else:
        prof[t_on:t_off] = mag
    if cfg.decay_len > 0 and t_off < T:
        for k in range(cfg.decay_len):
            if t_off + k < T:
                prof[t_off + k] = mag * (1 - (k + 1) / (cfg.decay_len + 1))
    return prof


def simulate(cfg: SimConfig, seed: int, harm: bool = True, rollout_id: str | None = None,
             pair_id: int = 0) -> tuple[Rollout, Truth]:
    rs = _streams(seed)
    T, N, nc, G = cfg.t_pre + cfg.t_post, cfg.n_hosts, cfg.n_canary, cfg.n_classes
    t0 = cfg.t_pre
    rollout_id = rollout_id or f"r{seed}"

    # ---- host metadata (fixed classes; canaries are hosts 0..nc-1) ----
    cls = np.concatenate([np.arange(nc) % G, np.arange(N - nc) % G]).astype(int)
    exposed = np.zeros(N, bool); exposed[:nc] = True
    m = rs["meta"]
    mu = np.log(cfg.mu_ms) + cfg.class_mu_offset * cls + m.normal(0, cfg.host_mu_sd, N)
    beta = cfg.beta + m.normal(0, cfg.beta_jitter, N)
    lam_class = m.normal(0, cfg.lam_class_sd, G)
    lam = cfg.lam + lam_class[cls] + m.normal(0, cfg.lam_host_sd, N)

    # ---- workload (measured, log scale) ----
    w = rs["workload"]
    wn = w.normal(0, cfg.workload_sd, T)
    x = _ar1(T, cfg.workload_phi, wn)
    x += 0.1 * np.sin(2 * np.pi * np.arange(T) / 1440.0 + w.uniform(0, 2 * np.pi))
    x[t0:] += cfg.workload_step

    # ---- shared factor with shock at rollout ----
    fr = rs["factor"]
    u = fr.normal(0, cfg.sd_f, T)
    u[t0] += cfg.shock
    f = _ar1(T, cfg.phi_f, u)

    # ---- host AR noise (+ optional heavy tails) and white measurement noise ----
    nz = rs["noise"]
    xi = nz.normal(0, cfg.sd_host, (T, N))
    if cfg.heavy_tail_df and cfg.heavy_tail_df > 2:
        tt = rs["tails"].standard_t(cfg.heavy_tail_df, (T, N))
        xi = cfg.sd_host * tt / np.sqrt(cfg.heavy_tail_df / (cfg.heavy_tail_df - 2))
    e = _ar1(T, cfg.phi_e, xi)
    nu = rs["meas"].normal(0, cfg.meas_sd, (T, N))

    # ---- exposure/effect selection (drawn even for null so streams stay aligned) ----
    ex = rs["exposure"]
    affected = np.sort(ex.choice(nc, size=min(cfg.n_affected, nc), replace=False)).tolist()
    if cfg.affected_mode == "class0":
        affected = np.flatnonzero(cls[:nc] == 0).tolist()
    ef = rs["effect"]
    contam_hosts = np.sort(ef.choice(np.arange(nc, N), size=int(round(cfg.contam_frac * (N - nc))),
                                     replace=False)) if cfg.contam_frac > 0 else np.array([], int)
    prof = effect_profile(cfg, T, t0)
    a = np.zeros((T, N)); spill = np.zeros((T, N))
    if harm:
        for h in affected:
            a[:, h] = prof
        for h in contam_hosts:
            spill[:, h] = cfg.contam_scale * prof

    # ---- loadings can change post-rollout (stress) ----
    lam_t = np.tile(lam, (T, 1)); lam_t[t0:] *= cfg.post_loading_scale
    xc = x
    y = (mu[None] + beta[None] * xc[:, None] + cfg.nonlinear_gamma * (xc ** 2)[:, None]
         + lam_t * f[:, None] + a + spill + e + nu)

    # ---- availability ----
    ms = rs["missing"]
    miss = ms.random((T, N)) < cfg.missing_rate
    if cfg.burst_len > 0:
        g = ms.integers(0, G); s = int(ms.integers(t0 + 5, max(t0 + 6, T - cfg.burst_len)))
        miss[s:s + cfg.burst_len, :nc] |= (cls[:nc] == g)[None]
    late = ms.random((T, N)) < cfg.late_frac
    observed = ~miss
    decision_obs = observed & ~late
    y = np.where(observed, y, np.nan)
    req = np.round(np.exp(x)[:, None] * 1000.0 * np.ones((1, N))).astype(np.int32)

    cls_seen = cls.copy()                                   # metadata the detector sees (may be wrong: scenario S5)
    if cfg.label_error > 0:
        flip = rs["labels"].choice(nc, size=int(round(cfg.label_error * nc)), replace=False)
        cls_seen[flip] = (cls_seen[flip] + 1) % G
    roll = Rollout(rollout_id, y, x, observed, decision_obs, cls_seen, exposed, t0, req,
                   {"family": cfg.family, "late_delay": cfg.late_delay, "seed": int(seed),
                    "config_hash": dict_hash(asdict(cfg))})
    truth = Truth(rollout_id, a, spill, f, e, affected if harm else [], harm, cfg.family,
                  int(seed), int(pair_id), t0, asdict(cfg))
    return roll, truth
