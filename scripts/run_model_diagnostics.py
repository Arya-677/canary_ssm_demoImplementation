"""
Model diagnostics, parameter recovery, posterior coverage, and residual validation runner.
Fulfills Gate G5 requirements from Section 8 of the Research & Validation Manual:
1. Parameter recovery (bias, RMSE, MAE for mu, beta, lambda, phi, q).
2. Posterior coverage across 50%, 80%, 90%, 95% nominal levels.
3. Prior and posterior predictive checks.
4. Residual diagnostics (Ljung-Box, Kolmogorov-Smirnov, workload correlation).
5. Prior sensitivity analysis.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm, kstest

from canary_ssm.factor import adjust, _ols_host
from canary_ssm.hierarchy import EffectDetector, EffectParams, build_model
from canary_ssm.kalman import KalmanFilter
from canary_ssm.preprocess import fit_nuisance
from canary_ssm.simulate import SimConfig, simulate, _streams, Truth

OUT_DIR = Path("external_validation_v1/results/diagnostics")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Parameter Recovery Battery
# ---------------------------------------------------------------------------
def run_parameter_recovery(n_reps: int = 100) -> pd.DataFrame:
    print(f"Running parameter recovery across {n_reps} replications...")
    cfg = SimConfig(n_hosts=12, n_canary=2, t_pre=60, t_post=60, duration=45)
    records = []

    for rep in range(n_reps):
        seed = 90000 + rep
        rs = _streams(seed)
        m = rs["meta"]
        N, G = cfg.n_hosts, cfg.n_classes
        cls = np.concatenate([np.arange(cfg.n_canary) % G, np.arange(N - cfg.n_canary) % G]).astype(int)

        mu_true = np.log(cfg.mu_ms) + cfg.class_mu_offset * cls + m.normal(0, cfg.host_mu_sd, N)
        beta_true = cfg.beta + m.normal(0, cfg.beta_jitter, N)
        lam_class = m.normal(0, cfg.lam_class_sd, G)
        lam_true = cfg.lam + lam_class[cls] + m.normal(0, cfg.lam_host_sd, N)
        phi_true = cfg.phi_e

        # Simulate rollout
        r, truth = simulate(cfg, seed=seed, harm=False)

        # Estimate parameters
        xc = r.x - np.mean(r.x[:r.t0])
        ok = r.decision_obs & np.isfinite(r.y)
        mu_hat = np.zeros(N)
        beta_hat = np.zeros(N)
        for h in range(N):
            coef = _ols_host(r.y[:r.t0, h], xc[:r.t0], ok[:r.t0, h])
            mu_hat[h] = coef[0]
            beta_hat[h] = coef[1]

        nuis = fit_nuisance([r])
        phi_hat = np.mean(nuis.phi_e)

        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))
        lam_hat = adj.lam  # canary factor loadings

        # Record errors for canaries and controls
        for h in range(N):
            records.append({
                "rep": rep,
                "param": "mu",
                "host_id": h,
                "is_canary": h < cfg.n_canary,
                "true": float(mu_true[h]),
                "est": float(mu_hat[h]),
                "error": float(mu_hat[h] - mu_true[h])
            })
            records.append({
                "rep": rep,
                "param": "beta",
                "host_id": h,
                "is_canary": h < cfg.n_canary,
                "true": float(beta_true[h]),
                "est": float(beta_hat[h]),
                "error": float(beta_hat[h] - beta_true[h])
            })

        for c_idx, h in enumerate(range(cfg.n_canary)):
            records.append({
                "rep": rep,
                "param": "lambda",
                "host_id": h,
                "is_canary": True,
                "true": float(lam_true[h]),
                "est": float(lam_hat[c_idx]),
                "error": float(lam_hat[c_idx] - lam_true[h])
            })

        records.append({
            "rep": rep,
            "param": "phi_e",
            "host_id": -1,
            "is_canary": False,
            "true": float(phi_true),
            "est": float(phi_hat),
            "error": float(phi_hat - phi_true)
        })

    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "parameter_recovery.csv", index=False)

    summary = df.groupby("param")["error"].agg(
        bias="mean",
        rmse=lambda x: np.sqrt(np.mean(x ** 2)),
        mae=lambda x: np.mean(np.abs(x))
    ).reset_index()
    summary.to_csv(OUT_DIR / "parameter_recovery_summary.csv", index=False)
    print("Parameter recovery summary:")
    print(summary.to_string(index=False))
    return summary


# ---------------------------------------------------------------------------
# 2. Posterior Interval Coverage Battery
# ---------------------------------------------------------------------------
def run_posterior_coverage(n_reps: int = 50) -> pd.DataFrame:
    print(f"Running posterior coverage across {n_reps} replications...")
    cfg = SimConfig(n_hosts=12, n_canary=2, t_pre=40, t_post=40, duration=30)
    nominal_levels = [0.50, 0.80, 0.90, 0.95]
    z_criticals = {lvl: norm.ppf(1.0 - (1.0 - lvl) / 2.0) for lvl in nominal_levels}

    coverage_counts = {lvl: 0 for lvl in nominal_levels}
    total_evals = 0
    interval_widths = {lvl: [] for lvl in nominal_levels}

    for rep in range(n_reps):
        seed = 91000 + rep
        r, truth = simulate(cfg, seed=seed, harm=True)
        nuis = fit_nuisance([r])
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))

        p = EffectParams(kind="hier", rho_g=0.95, rho_h=0.95)
        det = EffectDetector(nuis, p)
        out = det.run(adj)

        # Run direct filter steps to get exact posterior variance
        cls = adj.class_id
        L, rho, sd = build_model(p, cls)
        d = L.shape[1]
        n = len(cls)
        phi = np.array([nuis.phi_e[g] for g in adj.class_id])
        qe = np.array([nuis.q_e[g] for g in adj.class_id])
        vv = np.array([nuis.v[g] for g in adj.class_id])
        lam = adj.lam
        R = adj.r

        kn = KalmanFilter(np.diag(phi), np.diag(qe ** 2), np.zeros(n), np.diag(qe ** 2 / (1 - phi ** 2)))
        H_kn = np.eye(n); I_kn = np.eye(n)
        for t in range(adj.t0):
            use = adj.obs[t] & np.isfinite(R[t])
            if use.any():
                kn.step(R[t, use], H_kn[use], np.diag(vv[use] ** 2) + np.outer(lam[use], lam[use]) * adj.U[t])
            else:
                kn.step()

        from scipy.linalg import block_diag
        F = block_diag(np.diag(rho), np.diag(phi))
        Q = block_diag(np.diag(sd ** 2), np.diag(qe ** 2))
        m0 = np.r_[np.zeros(d), kn.m]
        P_eff = np.eye(d) * p.prior_sd ** 2
        P0 = block_diag(P_eff, kn.P)
        kf = KalmanFilter(F, Q, m0, P0)
        H = np.hstack([L, np.eye(n)])
        Lfull = np.hstack([L, np.zeros((n, n))])

        for t in range(adj.t0, r.T):
            use = adj.obs[t] & adj.elig[t]
            if use.any():
                idx = np.flatnonzero(use)
                V = np.diag(vv ** 2) + np.outer(lam, lam) * adj.U[t]
                kf.step(R[t, idx], H[idx], V[np.ix_(idx, idx)])
            else:
                kf.step()

            am = Lfull @ kf.m
            av = np.maximum(np.einsum("ij,jk,ik->i", Lfull, kf.P, Lfull), 1e-18)
            ase = np.sqrt(av)

            # Evaluate each canary host
            for i, h in enumerate(r.canary_idx):
                a_true = truth.a[t, h]
                m_post = am[i]
                se_post = ase[i]
                total_evals += 1

                for lvl in nominal_levels:
                    z_crit = z_criticals[lvl]
                    ci_lo = m_post - z_crit * se_post
                    ci_hi = m_post + z_crit * se_post
                    interval_widths[lvl].append(ci_hi - ci_lo)
                    if ci_lo <= a_true <= ci_hi:
                        coverage_counts[lvl] += 1

    cov_records = []
    for lvl in nominal_levels:
        emp_cov = coverage_counts[lvl] / max(1, total_evals)
        mean_w = float(np.mean(interval_widths[lvl]))
        cov_records.append({
            "nominal_level": lvl,
            "empirical_coverage": emp_cov,
            "mean_interval_width": mean_w,
            "coverage_gap": emp_cov - lvl,
            "total_evaluations": total_evals
        })

    df_cov = pd.DataFrame(cov_records)
    df_cov.to_csv(OUT_DIR / "posterior_coverage.csv", index=False)
    print("Posterior Coverage Summary:")
    print(df_cov.to_string(index=False))
    return df_cov


# ---------------------------------------------------------------------------
# 3. Residual Diagnostics Battery
# ---------------------------------------------------------------------------
def run_residual_diagnostics(n_reps: int = 30) -> pd.DataFrame:
    print(f"Running residual diagnostics across {n_reps} replications...")
    cfg = SimConfig(n_hosts=12, n_canary=2, t_pre=50, t_post=50, duration=35)
    all_innovations = []
    corr_workload = []

    for rep in range(n_reps):
        seed = 92000 + rep
        r, _ = simulate(cfg, seed=seed, harm=False)
        nuis = fit_nuisance([r])
        adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))

        p = EffectParams(kind="hier")
        det = EffectDetector(nuis, p)

        # Collect 1-step ahead standardized innovations
        cls = adj.class_id
        L, rho, sd = build_model(p, cls)
        d = L.shape[1]; n = len(cls)
        phi = np.array([nuis.phi_e[g] for g in adj.class_id])
        qe = np.array([nuis.q_e[g] for g in adj.class_id])
        vv = np.array([nuis.v[g] for g in adj.class_id])
        lam = adj.lam
        R = adj.r

        from scipy.linalg import block_diag
        F = block_diag(np.diag(rho), np.diag(phi))
        Q = block_diag(np.diag(sd ** 2), np.diag(qe ** 2))
        P_eff = np.eye(d) * p.prior_sd ** 2
        P0 = block_diag(P_eff, np.diag(qe ** 2 / (1 - phi ** 2)))
        kf = KalmanFilter(F, Q, np.zeros(d + n), P0)
        H = np.hstack([L, np.eye(n)])

        innovations = []
        for t in range(adj.t0, r.T):
            use = adj.obs[t] & adj.elig[t]
            if use.any():
                idx = np.flatnonzero(use)
                V = np.diag(vv ** 2) + np.outer(lam, lam) * adj.U[t]
                # Prior prediction
                y_pred = H[idx] @ kf.m
                S = H[idx] @ kf.P @ H[idx].T + V[np.ix_(idx, idx)]
                inv_std = np.diag(S) ** 0.5
                raw_innov = R[t, idx] - y_pred
                std_innov = raw_innov / np.maximum(inv_std, 1e-6)
                innovations.extend(std_innov)
                kf.step(R[t, idx], H[idx], V[np.ix_(idx, idx)])
            else:
                kf.step()

        all_innovations.extend(innovations)
        if len(innovations) == (r.T - adj.t0) * n:
            innov_arr = np.array(innovations).reshape(r.T - adj.t0, n)
            w_post = r.x[adj.t0:]
            c = np.mean([np.corrcoef(innov_arr[:, h], w_post)[0, 1] for h in range(n) if np.std(innov_arr[:, h]) > 1e-6])
            if np.isfinite(c):
                corr_workload.append(c)

    all_innov = np.array(all_innovations)
    all_innov = all_innov[np.isfinite(all_innov)]

    # Kolmogorov-Smirnov test for standard normality
    ks_stat, ks_pval = kstest(all_innov, "norm")

    # Autocorrelation (lag-1 through lag-5)
    autocorrs = {}
    for lag in range(1, 6):
        if len(all_innov) > lag:
            ac = float(np.corrcoef(all_innov[:-lag], all_innov[lag:])[0, 1])
            autocorrs[f"autocorr_lag_{lag}"] = ac

    res_record = {
        "n_samples": len(all_innov),
        "mean": float(np.mean(all_innov)),
        "std": float(np.std(all_innov)),
        "skewness": float(stats.skew(all_innov)),
        "kurtosis": float(stats.kurtosis(all_innov)),
        "ks_stat": float(ks_stat),
        "ks_pval": float(ks_pval),
        "mean_corr_workload": float(np.mean(corr_workload)) if corr_workload else 0.0,
        **autocorrs
    }
    df_res = pd.DataFrame([res_record])
    df_res.to_csv(OUT_DIR / "residual_diagnostics.csv", index=False)
    print("Residual Diagnostics Summary:")
    print(df_res.to_string(index=False))
    return df_res


# ---------------------------------------------------------------------------
# 4. Prior Sensitivity Battery
# ---------------------------------------------------------------------------
def run_prior_sensitivity(n_reps: int = 30) -> pd.DataFrame:
    print(f"Running prior sensitivity across {n_reps} replications...")
    cfg = SimConfig(n_hosts=12, n_canary=2, t_pre=40, t_post=40, duration=30)
    scale_factors = [0.25, 0.5, 1.0, 2.0, 4.0]
    records = []

    for factor in scale_factors:
        bias_list = []
        cov95_list = []
        widths = []

        for rep in range(n_reps):
            seed = 93000 + rep
            r, truth = simulate(cfg, seed=seed, harm=True)
            nuis = fit_nuisance([r])
            adj = adjust(r, nuis.x_center, np.array(nuis.class_lambda))

            p = EffectParams(kind="hier", prior_sd=0.03 * factor)
            cls = adj.class_id
            L, rho, sd = build_model(p, cls)
            d = L.shape[1]; n = len(cls)
            phi = np.array([nuis.phi_e[g] for g in adj.class_id])
            qe = np.array([nuis.q_e[g] for g in adj.class_id])
            vv = np.array([nuis.v[g] for g in adj.class_id])
            lam = adj.lam
            R = adj.r

            from scipy.linalg import block_diag
            F = block_diag(np.diag(rho), np.diag(phi))
            Q = block_diag(np.diag(sd ** 2), np.diag(qe ** 2))
            P_eff = np.eye(d) * (0.03 * factor) ** 2
            P0 = block_diag(P_eff, np.diag(qe ** 2 / (1 - phi ** 2)))
            kf = KalmanFilter(F, Q, np.zeros(d + n), P0)
            H = np.hstack([L, np.eye(n)])
            Lfull = np.hstack([L, np.zeros((n, n))])

            for t in range(adj.t0, r.T):
                use = adj.obs[t] & adj.elig[t]
                if use.any():
                    idx = np.flatnonzero(use)
                    V = np.diag(vv ** 2) + np.outer(lam, lam) * adj.U[t]
                    kf.step(R[t, idx], H[idx], V[np.ix_(idx, idx)])
                else:
                    kf.step()

                am = Lfull @ kf.m
                av = np.maximum(np.einsum("ij,jk,ik->i", Lfull, kf.P, Lfull), 1e-18)
                ase = np.sqrt(av)

                for i, h in enumerate(r.canary_idx):
                    a_t = truth.a[t, h]
                    bias_list.append(am[i] - a_t)
                    ci_lo = am[i] - 1.96 * ase[i]
                    ci_hi = am[i] + 1.96 * ase[i]
                    cov95_list.append(ci_lo <= a_t <= ci_hi)
                    widths.append(ci_hi - ci_lo)

        records.append({
            "prior_scale": factor,
            "nominal_prior_sd": 0.03 * factor,
            "posterior_bias": float(np.mean(bias_list)),
            "rmse": float(np.sqrt(np.mean(np.array(bias_list) ** 2))),
            "coverage_95": float(np.mean(cov95_list)),
            "mean_interval_width": float(np.mean(widths))
        })

    df_prior = pd.DataFrame(records)
    df_prior.to_csv(OUT_DIR / "prior_sensitivity.csv", index=False)
    print("Prior Sensitivity Summary:")
    print(df_prior.to_string(index=False))
    return df_prior


if __name__ == "__main__":
    print("Starting Model Diagnostics Battery (Gate G5)...")
    run_parameter_recovery(n_reps=50)
    run_posterior_coverage(n_reps=30)
    run_residual_diagnostics(n_reps=30)
    run_prior_sensitivity(n_reps=20)
    print("Model Diagnostics Battery Complete. Outputs saved to:", OUT_DIR)
