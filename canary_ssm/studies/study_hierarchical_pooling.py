"""Study of Hierarchical Effect SSM Pooling Dynamics (handbook Section 7, Prompt 8).

Systematic demonstration across 4 scenarios:
1. Class-wide harm: Heterogeneous harm on Class 0 canaries, Class 1 clean.
   Demonstrates faster detection and lower posterior variance in Hierarchical SSM via class pooling.
2. Sparse harm: Single canary in Class 0 harmed, remaining canaries clean.
   Demonstrates negative transfer and harm dilution in Complete Pooling SSM;
   Hierarchical SSM isolates local deviation without contaminating clean hosts.
3. Infrastructure rack shock: Shared network latency shock on Rack 0.
   Demonstrates that Prompt 6 physical rack adjustment absorbs the shock via baseline controls,
   preventing false release alarms across all detectors.
4. Recovery: Harm onset at t0, followed by rollback at t0+30.
   Demonstrates smooth contraction of effect posterior means and decay of risk probability.

Diagnostic traces are written to `results/table_pooling_diagnostic_traces.csv`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from canary_ssm.detectors import (
    OnlineHierarchicalSSM,
    OnlineIndependentSSM,
    OnlinePooledSSM,
)
from canary_ssm.factor import Adjusted
from canary_ssm.hierarchy import (
    EffectDetector,
    EffectParams,
    class_structure,
    implied_host_covariance,
    pooling_correlation,
)
from canary_ssm.preprocess import Nuisance
from canary_ssm.schema import KAPPA


@dataclass
class ScenarioOutcome:
    name: str
    metrics: dict[str, Any]
    traces: list[dict[str, Any]]


def make_synthetic_nuisance(
    n_classes: int = 2,
    phi: float = 0.40,
    q: float = 0.01,
    v: float = 0.005,
) -> Nuisance:
    """Create a calibrated Nuisance object for reproducible simulation studies."""
    return Nuisance(
        x_center=0.0,
        class_lambda=[1.0] * n_classes,
        phi_e=[phi] * n_classes,
        q_e=[q] * n_classes,
        v=[v] * n_classes,
        factor_rank=1,
        noise="ar_only",
    )


def generate_ar1_series(
    T: int,
    nc: int,
    phi: float,
    q: float,
    v: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate stationary AR(1) series plus white observation noise."""
    e = np.zeros((T, nc))
    # Stationary initialization
    init_sd = q / np.sqrt(max(1.0 - phi ** 2, 1e-6))
    e[0] = rng.normal(0.0, init_sd, size=nc)
    for t in range(1, T):
        e[t] = phi * e[t - 1] + rng.normal(0.0, q, size=nc)
    obs_noise = rng.normal(0.0, v, size=(T, nc))
    return e + obs_noise


def run_scenario_class_wide_harm(
    seed: int = 42,
    T: int = 120,
    t0: int = 60,
    harm_shift: float = 0.06,
) -> ScenarioOutcome:
    """Scenario 1: Class-Wide Harm (Heterogeneous release harm on Class 0).

    4 canaries across 2 classes:
    - Class 0: Canaries 0, 1 (harmed at t >= t0 by harm_shift)
    - Class 1: Canaries 2, 3 (unaffected / clean)
    """
    rng = np.random.default_rng(seed)
    nc = 4
    class_id = np.array([0, 0, 1, 1], dtype=int)
    nuis = make_synthetic_nuisance(n_classes=2)

    # Base AR(1) noise residuals
    r = generate_ar1_series(T, nc, nuis.phi_e[0], nuis.q_e[0], nuis.v[0], rng)

    # Inject class-wide harm on Class 0 canaries only
    for t in range(t0, T):
        r[t, 0] += harm_shift
        r[t, 1] += harm_shift

    obs = np.ones((T, nc), dtype=bool)
    elig = np.ones(T, dtype=bool)
    lam = np.ones(nc, dtype=float)
    sigma = np.full(nc, 0.015, dtype=float)
    cov_U = np.zeros((T, nc, nc), dtype=float)

    adj = Adjusted(
        r=r,
        obs=obs,
        elig=elig,
        U=np.zeros(T),
        lam=lam,
        sigma=sigma,
        rm=r.copy(),
        class_id=class_id,
        t0=t0,
        fallback=np.zeros(nc, dtype=bool),
        f_hat=np.zeros(T),
        cov_U=cov_U,
    )

    params = EffectParams(sd_g=0.005, sd_h_ratio=0.5, prior_sd=0.03)
    out_hier = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "hier"})).run(adj)
    out_indep = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "indep"})).run(adj)
    out_pooled = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "pooled"})).run(adj)

    # Calculate detection ticks (first tick where score > log(0.50))
    threshold = np.log(0.50)
    delay_hier = next((t - t0 for t in range(t0, T) if out_hier.score[t] > threshold), T - t0)
    delay_indep = next((t - t0 for t in range(t0, T) if out_indep.score[t] > threshold), T - t0)
    delay_pooled = next((t - t0 for t in range(t0, T) if out_pooled.score[t] > threshold), T - t0)

    # Posterior variance on Class 0 at t0 + 20
    t_eval = t0 + 20
    var_hier_c0 = float(out_hier.effect_cov[t_eval, 0, 0])
    var_indep_c0 = float(out_indep.effect_cov[t_eval, 0, 0])

    # Class 1 risk probability at t_eval
    prob_hier_c1 = float(np.mean(out_hier.host_prob[t_eval, 2:]))
    prob_pooled_c1 = float(np.mean(out_pooled.host_prob[t_eval, 2:]))

    metrics = {
        "delay_hier": delay_hier,
        "delay_indep": delay_indep,
        "delay_pooled": delay_pooled,
        "var_hier_c0": var_hier_c0,
        "var_indep_c0": var_indep_c0,
        "variance_reduction_pct": 100.0 * (1.0 - var_hier_c0 / max(var_indep_c0, 1e-12)),
        "prob_hier_c1": prob_hier_c1,
        "prob_pooled_c1": prob_pooled_c1,
        "pooling_speedup": delay_indep - delay_hier,
    }

    # Record traces
    traces = []
    detectors = [("hier_ssm", out_hier), ("indep_ssm", out_indep), ("pooled_ssm", out_pooled)]
    for det_name, out in detectors:
        for t in range(t0, T):
            for i in range(nc):
                c_id = int(class_id[i])
                th_val = float(out.class_effects[t, c_id]) if out.class_effects is not None and c_id < out.class_effects.shape[1] else np.nan
                dev_val = float(out.host_deviations[t, i]) if out.host_deviations is not None else np.nan
                traces.append({
                    "scenario": "class_wide_harm",
                    "tick": t,
                    "t_rollout": t - t0,
                    "canary_id": i,
                    "class_id": c_id,
                    "detector": det_name,
                    "raw_obs": float(r[t, i]),
                    "effect_mean": float(out.host_score[t, i]),
                    "effect_sd": float(np.sqrt(out.effect_cov[t, i, i])),
                    "class_effect": th_val,
                    "host_deviation": dev_val,
                    "risk_prob": float(out.host_prob[t, i]),
                    "release_score": float(out.score[t]),
                    "is_harm_active": bool(i in (0, 1)),
                })

    return ScenarioOutcome("class_wide_harm", metrics, traces)


def run_scenario_sparse_harm(
    seed: int = 42,
    T: int = 120,
    t0: int = 60,
    harm_shift: float = 0.06,
) -> ScenarioOutcome:
    """Scenario 2: Sparse Harm & Negative Transfer.

    4 canaries across 2 classes:
    - Canary 0 (Class 0): single harmed canary (+harm_shift at t >= t0)
    - Canaries 1 (Class 0), 2 (Class 1), 3 (Class 1): completely clean.

    Demonstrates:
    - Complete pooling suffers from harm dilution (4x attenuation) and misses Canary 0.
    - Complete pooling causes negative transfer: clean canaries suffer falsely elevated risk.
    - Hierarchical SSM isolates Canary 0 via local deviation B b without diluting or contaminating.
    """
    rng = np.random.default_rng(seed)
    nc = 4
    class_id = np.array([0, 0, 1, 1], dtype=int)
    nuis = make_synthetic_nuisance(n_classes=2)

    r = generate_ar1_series(T, nc, nuis.phi_e[0], nuis.q_e[0], nuis.v[0], rng)

    # Only Canary 0 is harmed!
    for t in range(t0, T):
        r[t, 0] += harm_shift

    obs = np.ones((T, nc), dtype=bool)
    elig = np.ones(T, dtype=bool)
    lam = np.ones(nc, dtype=float)
    sigma = np.full(nc, 0.015, dtype=float)
    cov_U = np.zeros((T, nc, nc), dtype=float)

    adj = Adjusted(
        r=r,
        obs=obs,
        elig=elig,
        U=np.zeros(T),
        lam=lam,
        sigma=sigma,
        rm=r.copy(),
        class_id=class_id,
        t0=t0,
        fallback=np.zeros(nc, dtype=bool),
        f_hat=np.zeros(T),
        cov_U=cov_U,
    )

    params = EffectParams(sd_g=0.005, sd_h_ratio=0.5, prior_sd=0.03)
    out_hier = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "hier"})).run(adj)
    out_indep = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "indep"})).run(adj)
    out_pooled = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "pooled"})).run(adj)

    t_eval = t0 + 20
    # Estimated effect on harmed canary 0
    eff_hier_harm = float(out_hier.host_score[t_eval, 0])
    eff_indep_harm = float(out_indep.host_score[t_eval, 0])
    eff_pooled_harm = float(out_pooled.host_score[t_eval, 0])

    # Harm dilution factor: Indep effect / Pooled effect
    dilution_ratio = eff_indep_harm / max(eff_pooled_harm, 1e-6)

    # Risk probabilities on clean canaries [1, 2, 3]
    clean_risk_hier = float(np.mean(out_hier.host_prob[t_eval, 1:]))
    clean_risk_indep = float(np.mean(out_indep.host_prob[t_eval, 1:]))
    clean_risk_pooled = float(np.mean(out_pooled.host_prob[t_eval, 1:]))

    # Negative transfer metric: excess risk on clean hosts caused by complete pooling
    negative_transfer = clean_risk_pooled - clean_risk_hier

    metrics = {
        "eff_hier_harm": eff_hier_harm,
        "eff_indep_harm": eff_indep_harm,
        "eff_pooled_harm": eff_pooled_harm,
        "dilution_ratio": dilution_ratio,
        "clean_risk_hier": clean_risk_hier,
        "clean_risk_indep": clean_risk_indep,
        "clean_risk_pooled": clean_risk_pooled,
        "negative_transfer": negative_transfer,
        "harm_detected_hier": bool(out_hier.host_prob[t_eval, 0] > 0.80),
        "harm_detected_pooled": bool(out_pooled.host_prob[t_eval, 0] > 0.80),
    }

    traces = []
    detectors = [("hier_ssm", out_hier), ("indep_ssm", out_indep), ("pooled_ssm", out_pooled)]
    for det_name, out in detectors:
        for t in range(t0, T):
            for i in range(nc):
                c_id = int(class_id[i])
                th_val = float(out.class_effects[t, c_id]) if out.class_effects is not None and c_id < out.class_effects.shape[1] else np.nan
                dev_val = float(out.host_deviations[t, i]) if out.host_deviations is not None else np.nan
                traces.append({
                    "scenario": "sparse_harm",
                    "tick": t,
                    "t_rollout": t - t0,
                    "canary_id": i,
                    "class_id": c_id,
                    "detector": det_name,
                    "raw_obs": float(r[t, i]),
                    "effect_mean": float(out.host_score[t, i]),
                    "effect_sd": float(np.sqrt(out.effect_cov[t, i, i])),
                    "class_effect": th_val,
                    "host_deviation": dev_val,
                    "risk_prob": float(out.host_prob[t, i]),
                    "release_score": float(out.score[t]),
                    "is_harm_active": bool(i == 0),
                })

    return ScenarioOutcome("sparse_harm", metrics, traces)


def run_scenario_rack_shock(
    seed: int = 42,
    T: int = 120,
    t0: int = 60,
    shock_magnitude: float = 0.15,
) -> ScenarioOutcome:
    """Scenario 3: Infrastructure Rack Shock.

    4 racks with 6 servers each (1 canary, 5 baseline controls per rack).
    At t >= t0 + 10, a shared physical network latency shock hits Rack 0.
    The baseline controls in Rack 0 experience the shock, allowing Prompt 6
    nested rack adjustment gamma_hat to absorb it.
    Canary residual r_{0, t} = c_{0, t} - gamma_hat_0(t) remains unaffected (~0).
    Demonstrates that physical rack adjustment remains cleanly distinguished from release harm.
    """
    rng = np.random.default_rng(seed)
    nc = 4
    class_id = np.array([0, 0, 1, 1], dtype=int)
    nuis = make_synthetic_nuisance(n_classes=2)

    # Base AR(1) noise residuals
    raw_canary = generate_ar1_series(T, nc, nuis.phi_e[0], nuis.q_e[0], nuis.v[0], rng)

    # 5 controls in Rack 0
    n_ctl_r0 = 5
    raw_ctl_r0 = generate_ar1_series(T, n_ctl_r0, nuis.phi_e[0], nuis.q_e[0], nuis.v[0], rng)

    # Shared rack network shock on Rack 0 at t >= t0 + 10
    t_shock = t0 + 10
    for t in range(t_shock, T):
        raw_canary[t, 0] += shock_magnitude
        raw_ctl_r0[t, :] += shock_magnitude

    # Nested rack adjustment from controls: gamma_hat_0(t) = mean(ctl_r0)
    gamma_hat_0 = np.zeros(T)
    for t in range(T):
        gamma_hat_0[t] = np.mean(raw_ctl_r0[t])

    # Adjusted canary residuals: Canary 0 has gamma_hat_0 subtracted
    r_adj = raw_canary.copy()
    r_adj[:, 0] -= gamma_hat_0

    # Uncertainty from rack adjustment: Var(gamma_hat_0) = v^2 / 5
    cov_U = np.zeros((T, nc, nc), dtype=float)
    cov_U[:, 0, 0] = (nuis.v[0] ** 2) / n_ctl_r0

    obs = np.ones((T, nc), dtype=bool)
    elig = np.ones(T, dtype=bool)
    lam = np.ones(nc, dtype=float)
    sigma = np.full(nc, 0.015, dtype=float)

    adj = Adjusted(
        r=r_adj,
        obs=obs,
        elig=elig,
        U=np.zeros(T),
        lam=lam,
        sigma=sigma,
        rm=r_adj.copy(),
        class_id=class_id,
        t0=t0,
        fallback=np.zeros(nc, dtype=bool),
        f_hat=np.zeros(T),
        cov_U=cov_U,
    )

    params = EffectParams(sd_g=0.005, sd_h_ratio=0.5, prior_sd=0.03)
    out_hier = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "hier"})).run(adj)
    out_indep = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "indep"})).run(adj)
    out_pooled = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "pooled"})).run(adj)

    # Max risk probability across rollout for all detectors
    max_risk_hier = float(np.nanmax(out_hier.host_prob[t0:]))
    max_risk_indep = float(np.nanmax(out_indep.host_prob[t0:]))
    max_risk_pooled = float(np.nanmax(out_pooled.host_prob[t0:]))

    # Threshold = log(0.50)
    false_alarm_hier = bool(np.nanmax(out_hier.score[t0:]) > np.log(0.50))
    false_alarm_indep = bool(np.nanmax(out_indep.score[t0:]) > np.log(0.50))
    false_alarm_pooled = bool(np.nanmax(out_pooled.score[t0:]) > np.log(0.50))

    metrics = {
        "shock_absorbed_gamma_hat_mean": float(np.mean(gamma_hat_0[t_shock:])),
        "post_adj_residual_canary0_mean": float(np.mean(r_adj[t_shock:, 0])),
        "max_risk_hier": max_risk_hier,
        "max_risk_indep": max_risk_indep,
        "max_risk_pooled": max_risk_pooled,
        "false_alarm_hier": false_alarm_hier,
        "false_alarm_indep": false_alarm_indep,
        "false_alarm_pooled": false_alarm_pooled,
        "absorbed_cleanly": not (false_alarm_hier or false_alarm_indep or false_alarm_pooled),
    }

    traces = []
    detectors = [("hier_ssm", out_hier), ("indep_ssm", out_indep), ("pooled_ssm", out_pooled)]
    for det_name, out in detectors:
        for t in range(t0, T):
            for i in range(nc):
                c_id = int(class_id[i])
                th_val = float(out.class_effects[t, c_id]) if out.class_effects is not None and c_id < out.class_effects.shape[1] else np.nan
                dev_val = float(out.host_deviations[t, i]) if out.host_deviations is not None else np.nan
                traces.append({
                    "scenario": "rack_shock",
                    "tick": t,
                    "t_rollout": t - t0,
                    "canary_id": i,
                    "class_id": c_id,
                    "detector": det_name,
                    "raw_obs": float(r_adj[t, i]),
                    "effect_mean": float(out.host_score[t, i]),
                    "effect_sd": float(np.sqrt(out.effect_cov[t, i, i])),
                    "class_effect": th_val,
                    "host_deviation": dev_val,
                    "risk_prob": float(out.host_prob[t, i]),
                    "release_score": float(out.score[t]),
                    "is_harm_active": False,  # Infrastructure shock, not release harm
                })

    return ScenarioOutcome("rack_shock", metrics, traces)


def run_scenario_recovery(
    seed: int = 42,
    T: int = 130,
    t0: int = 50,
    t_rollback: int = 80,
    harm_shift: float = 0.06,
) -> ScenarioOutcome:
    """Scenario 4: Rollout Harm followed by Rollback / Recovery.

    - Exposure onset at t0 = 50: Class 0 canaries experience harm (+harm_shift).
    - Rollback occurs at t_rollback = 80: Canary harm is eliminated (residuals return to healthy AR(1) baseline).
    - Demonstrates that effect states contract smoothly back to zero without hysteresis.
    """
    rng = np.random.default_rng(seed)
    nc = 4
    class_id = np.array([0, 0, 1, 1], dtype=int)
    nuis = make_synthetic_nuisance(n_classes=2)

    r = generate_ar1_series(T, nc, nuis.phi_e[0], nuis.q_e[0], nuis.v[0], rng)

    # Harm active strictly between [t0, t_rollback)
    for t in range(t0, t_rollback):
        r[t, 0] += harm_shift
        r[t, 1] += harm_shift

    obs = np.ones((T, nc), dtype=bool)
    elig = np.ones(T, dtype=bool)
    lam = np.ones(nc, dtype=float)
    sigma = np.full(nc, 0.015, dtype=float)
    cov_U = np.zeros((T, nc, nc), dtype=float)

    adj = Adjusted(
        r=r,
        obs=obs,
        elig=elig,
        U=np.zeros(T),
        lam=lam,
        sigma=sigma,
        rm=r.copy(),
        class_id=class_id,
        t0=t0,
        fallback=np.zeros(nc, dtype=bool),
        f_hat=np.zeros(T),
        cov_U=cov_U,
    )

    params = EffectParams(sd_g=0.005, sd_h_ratio=0.5, prior_sd=0.03)
    out_hier = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "hier"})).run(adj)
    out_indep = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "indep"})).run(adj)
    out_pooled = EffectDetector(nuis, EffectParams(**{**params.__dict__, "kind": "pooled"})).run(adj)

    # Peak score during harm phase
    peak_score_hier = float(np.nanmax(out_hier.score[t0:t_rollback]))
    peak_prob_hier = float(np.nanmax(out_hier.host_prob[t0:t_rollback, 0]))

    # Final score and probability after recovery (at T-1)
    recovered_score_hier = float(out_hier.score[-1])
    recovered_prob_hier = float(np.nanmax(out_hier.host_prob[-1]))
    recovered_effect_mean = float(np.nanmax(np.abs(out_hier.host_score[-1])))

    metrics = {
        "peak_score_hier": peak_score_hier,
        "peak_prob_hier": peak_prob_hier,
        "recovered_score_hier": recovered_score_hier,
        "recovered_prob_hier": recovered_prob_hier,
        "recovered_effect_mean": recovered_effect_mean,
        "decay_successful": bool(recovered_prob_hier < 0.10 and recovered_effect_mean < 0.015),
    }

    traces = []
    detectors = [("hier_ssm", out_hier), ("indep_ssm", out_indep), ("pooled_ssm", out_pooled)]
    for det_name, out in detectors:
        for t in range(t0, T):
            for i in range(nc):
                c_id = int(class_id[i])
                th_val = float(out.class_effects[t, c_id]) if out.class_effects is not None and c_id < out.class_effects.shape[1] else np.nan
                dev_val = float(out.host_deviations[t, i]) if out.host_deviations is not None else np.nan
                traces.append({
                    "scenario": "recovery",
                    "tick": t,
                    "t_rollout": t - t0,
                    "canary_id": i,
                    "class_id": c_id,
                    "detector": det_name,
                    "raw_obs": float(r[t, i]),
                    "effect_mean": float(out.host_score[t, i]),
                    "effect_sd": float(np.sqrt(out.effect_cov[t, i, i])),
                    "class_effect": th_val,
                    "host_deviation": dev_val,
                    "risk_prob": float(out.host_prob[t, i]),
                    "release_score": float(out.score[t]),
                    "is_harm_active": bool(t < t_rollback and i in (0, 1)),
                })

    return ScenarioOutcome("recovery", metrics, traces)


def run(
    seed: int = 42,
    output_dir: Path | str = "results",
) -> dict[str, Any]:
    """Execute all 4 hierarchical pooling demonstration scenarios and write diagnostic traces."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    res1 = run_scenario_class_wide_harm(seed=seed)
    res2 = run_scenario_sparse_harm(seed=seed)
    res3 = run_scenario_rack_shock(seed=seed)
    res4 = run_scenario_recovery(seed=seed)

    all_traces = res1.traces + res2.traces + res3.traces + res4.traces
    df = pd.DataFrame(all_traces)
    trace_csv_path = out_path / "table_pooling_diagnostic_traces.csv"
    df.to_csv(trace_csv_path, index=False)

    summary = {
        "class_wide_harm": res1.metrics,
        "sparse_harm": res2.metrics,
        "rack_shock": res3.metrics,
        "recovery": res4.metrics,
        "trace_file": str(trace_csv_path),
        "total_records": len(df),
    }

    return summary


if __name__ == "__main__":
    summary = run()
    import pprint
    pprint.pprint(summary)
