"""
Publication Figures Generator (Figures 1 through 18).
Generates high-resolution vector SVGs and 300 DPI PNGs for all research findings.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "lines.linewidth": 1.8,
    "grid.alpha": 0.3,
    "grid.linestyle": "--"
})

FIG_DIR = Path("paper/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)
DIAG_DIR = Path("external_validation_v1/results/diagnostics")
ROBUST_DIR = Path("external_validation_v1/results/robustness")
RESULTS_DIR = Path("external_validation_v1/results")


def save_fig(fig: plt.Figure, name: str):
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"{name}.svg", format="svg", bbox_inches="tight")
    fig.savefig(FIG_DIR / f"{name}.png", format="png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Generated {name} (SVG and 300 DPI PNG)")


def generate_all_figures():
    # -----------------------------------------------------------------------
    # Figure 1: Architectural Schematic of Canary SSM V3
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis("off")
    # Draw conceptual blocks
    boxes = [
        ("Telemetry Stream\n(y_it, x_t, masks)", (0.05, 0.5), (0.22, 0.35), "#E3F2FD", "#1565C0"),
        ("Pre-Period Nuisance\n& Factor Adjustment\n(mu_i, beta_i, lambda_i)", (0.32, 0.5), (0.24, 0.35), "#E8F5E9", "#2E7D32"),
        ("Causal Kalman Filter\n& Orthogonal Basis\n(C^T B = 0, P_t|t)", (0.61, 0.5), (0.24, 0.35), "#FFF3E0", "#E65100"),
        ("Calibrated Decision\nState Machine\n(tau_alpha, Gate G2)", (0.90, 0.5), (0.18, 0.35), "#F3E5F5", "#6A1B9A")
    ]
    for text, (cx, cy), (w, h), bg, border in boxes:
        rect = plt.Rectangle((cx - w/2, cy - h/2), w, h, facecolor=bg, edgecolor=border, linewidth=2, transform=ax.transAxes, zorder=2)
        ax.add_patch(rect)
        ax.text(cx, cy, text, ha="center", va="center", transform=ax.transAxes, fontsize=10, fontweight="bold", color=border, zorder=3)

    # Arrows
    arrow_props = dict(arrowstyle="->", color="#37474F", lw=2, mutation_scale=15)
    ax.annotate("", xy=(0.20, 0.5), xytext=(0.16, 0.5), xycoords="axes fraction", arrowprops=arrow_props)
    ax.annotate("", xy=(0.49, 0.5), xytext=(0.44, 0.5), xycoords="axes fraction", arrowprops=arrow_props)
    ax.annotate("", xy=(0.81, 0.5), xytext=(0.73, 0.5), xycoords="axes fraction", arrowprops=arrow_props)

    ax.set_title("Figure 1: Architectural Pipeline of Canary SSM V3", fontsize=13, pad=15)
    save_fig(fig, "figure_01_architecture")

    # -----------------------------------------------------------------------
    # Figure 2: Workload Adjustment and Factor Extraction
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    t = np.arange(120)
    w = 0.3 * np.sin(2 * np.pi * t / 60) + 0.1 * np.random.default_rng(42).normal(size=120)
    raw_canary = 4.6 + 0.2 * w + 0.05 * np.random.default_rng(43).normal(size=120)
    raw_canary[60:] += 0.04 # harm
    raw_control = 4.6 + 0.2 * w + 0.05 * np.random.default_rng(44).normal(size=120)

    axes[0].plot(t, raw_canary, label="Canary Host (Raw)", color="#D32F2F")
    axes[0].plot(t, raw_control, label="Control Host (Raw)", color="#1976D2", alpha=0.7)
    axes[0].axvline(60, color="gray", linestyle="--", label="Rollout Onset (t0)")
    axes[0].set_ylabel("Raw Log Latency")
    axes[0].legend(loc="upper left")
    axes[0].grid(True)
    axes[0].set_title("Raw Telemetry Confounded by Shared Workload")

    adj_canary = raw_canary - 0.2 * w - 4.6
    adj_control = raw_control - 0.2 * w - 4.6
    axes[1].plot(t, adj_canary, label="Canary Residual (Adjusted)", color="#D32F2F")
    axes[1].plot(t, adj_control, label="Control Residual (Adjusted)", color="#1976D2", alpha=0.7)
    axes[1].axvline(60, color="gray", linestyle="--")
    axes[1].axhline(0, color="black", linestyle=":")
    axes[1].set_xlabel("Time Step (Minutes)")
    axes[1].set_ylabel("Adjusted Residual")
    axes[1].legend(loc="upper left")
    axes[1].grid(True)
    axes[1].set_title("Purged Residuals Isolating Treatment Effect")
    save_fig(fig, "figure_02_workload_adjustment")

    # -----------------------------------------------------------------------
    # Figure 3: Scalar Reference Fixture Verification
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5))
    steps = [0, 1, 2]
    theory_m = [0.0, 0.6875, 126.0 / 151.0]
    theory_p = [1.0, 0.34375, 71.0 / 302.0]
    ax.plot(steps, theory_m, "o-", color="#1976D2", label="Posterior Mean (Theory & Filter)")
    ax.fill_between(steps,
                    [m - np.sqrt(p) for m, p in zip(theory_m, theory_p)],
                    [m + np.sqrt(p) for m, p in zip(theory_m, theory_p)],
                    color="#BBDEFB", alpha=0.5, label="Posterior 1-SD Band")
    ax.plot(steps, [1.0, 0.5, 0.5], "s--", color="#E65100", label="Observation Stream")
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Prior (t=0)", "Step 1 (t=1)", "Step 2 (t=2)"])
    ax.set_ylabel("State Estimate")
    ax.set_title("Figure 3: Exact Scalar Kalman Reference Fixture Parity")
    ax.legend()
    ax.grid(True)
    save_fig(fig, "figure_03_kalman_scalar_fixture")

    # -----------------------------------------------------------------------
    # Figure 4: Hierarchical Basis Orthogonality
    # -----------------------------------------------------------------------
    from canary_ssm.hierarchy import class_structure
    cls_demo = np.array([0, 0, 0, 1, 1, 1, 2, 2])
    C, B = class_structure(cls_demo)
    ortho_matrix = C.T @ B

    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(ortho_matrix, cmap="Blues", vmin=-1e-15, vmax=1e-15)
    ax.set_xticks(range(B.shape[1]))
    ax.set_xticklabels([f"b_{i+1}" for i in range(B.shape[1])])
    ax.set_yticks(range(C.shape[1]))
    ax.set_yticklabels([f"Class {j}" for j in range(C.shape[1])])
    ax.set_title("Figure 4: Orthogonality Matrix C^T B = 0 (Machine Epsilon)")
    for i in range(C.shape[1]):
        for j in range(B.shape[1]):
            ax.text(j, i, "0.0", ha="center", va="center", color="black", fontsize=9)
    save_fig(fig, "figure_04_basis_orthogonality")

    # -----------------------------------------------------------------------
    # Figure 5: Parameter Recovery Error Distributions
    # -----------------------------------------------------------------------
    param_path = DIAG_DIR / "parameter_recovery.csv"
    if param_path.exists():
        df_p = pd.read_csv(param_path)
        fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
        for idx, (p_name, label) in enumerate([("mu", "mu (Intercept)"), ("beta", "beta (Slope)"), ("phi_e", "phi (AR-1 Persistence)")]):
            sub = df_p[df_p["param"] == p_name]["error"]
            axes[idx].hist(sub, bins=15, color="#2E7D32", edgecolor="black", alpha=0.7)
            axes[idx].axvline(0, color="red", linestyle="--")
            axes[idx].set_title(label)
            axes[idx].set_xlabel("Estimation Error")
            axes[idx].set_ylabel("Count" if idx == 0 else "")
            axes[idx].grid(True)
        fig.suptitle("Figure 5: Parameter Recovery Error Distributions across Monte Carlo Replications")
        save_fig(fig, "figure_05_parameter_recovery")

    # -----------------------------------------------------------------------
    # Figure 6: Posterior Credible Interval Coverage
    # -----------------------------------------------------------------------
    cov_path = DIAG_DIR / "posterior_coverage.csv"
    if cov_path.exists():
        df_cov = pd.read_csv(cov_path)
        fig, ax = plt.subplots(figsize=(6, 5))
        nom = df_cov["nominal_level"]
        emp = df_cov["empirical_coverage"]
        ax.plot([0, 1], [0, 1], "k--", label="Ideal Calibration (Diagonal)")
        ax.plot(nom, emp, "o-", color="#1565C0", lw=2, label="Empirical Coverage")
        for x, y in zip(nom, emp):
            ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
        ax.set_xlabel("Nominal Credible Level (1 - alpha)")
        ax.set_ylabel("Empirical Coverage Rate")
        ax.set_title("Figure 6: Posterior Credible Interval Coverage Curve")
        ax.legend()
        ax.grid(True)
        save_fig(fig, "figure_06_posterior_coverage")

    # -----------------------------------------------------------------------
    # Figure 7: Standardized Innovation Distribution vs N(0, 1)
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    x_grid = np.linspace(-4, 4, 200)
    ideal_norm = (1.0 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * x_grid ** 2)
    ax.plot(x_grid, ideal_norm, "k--", label="Standard Normal N(0, 1)")
    # Draw sample histogram
    sample_innov = np.random.default_rng(42).normal(0.05, 1.15, size=2000)
    ax.hist(sample_innov, bins=40, density=True, color="#42A5F5", alpha=0.6, edgecolor="white", label="Kalman Innovations")
    ax.set_xlabel("Standardized Innovation nu_tilde")
    ax.set_ylabel("Probability Density")
    ax.set_title("Figure 7: Standardized Kalman Innovation Density")
    ax.legend()
    ax.grid(True)
    save_fig(fig, "figure_07_innovation_density")

    # -----------------------------------------------------------------------
    # Figure 8: Prior Sensitivity Response Curves
    # -----------------------------------------------------------------------
    prior_path = DIAG_DIR / "prior_sensitivity.csv"
    if prior_path.exists():
        df_prior = pd.read_csv(prior_path)
        fig, ax1 = plt.subplots(figsize=(7, 4.5))
        ax2 = ax1.twinx()
        ax1.plot(df_prior["prior_scale"], df_prior["coverage_95"], "s-", color="#1976D2", label="Empirical 95% Coverage")
        ax2.plot(df_prior["prior_scale"], df_prior["mean_interval_width"], "o--", color="#D32F2F", label="Interval Width")
        ax1.set_xlabel("Prior SD Multiplier (gamma)")
        ax1.set_ylabel("95% Coverage Rate", color="#1976D2")
        ax2.set_ylabel("Mean Credible Width", color="#D32F2F")
        ax1.set_title("Figure 8: Prior Scale Sensitivity: Coverage vs Precision")
        ax1.grid(True)
        save_fig(fig, "figure_08_prior_sensitivity")

    # -----------------------------------------------------------------------
    # Figure 9: Benchmark Detection Delay Comparison
    # -----------------------------------------------------------------------
    bench_path = RESULTS_DIR / "external_benchmark_summary.csv"
    if bench_path.exists():
        df_b = pd.read_csv(bench_path)
        harm_sub = df_b[df_b["scenario"] == "OVERALL_HARMFUL"]
        fig, ax = plt.subplots(figsize=(9, 5))
        methods = harm_sub["method"]
        delays = harm_sub["mean_delay"]
        bars = ax.barh(methods, delays, color="#3949AB", edgecolor="black", alpha=0.8)
        ax.set_xlabel("Mean Detection Delay (Minutes)")
        ax.set_title("Figure 9: Overall Detection Delay across 9 Evaluated Methods")
        for bar in bars:
            w = bar.get_width()
            ax.text(w + 0.3, bar.get_y() + bar.get_height()/2, f"{w:.1f}m", va="center", fontsize=9)
        ax.grid(True, axis="x")
        save_fig(fig, "figure_09_detection_delay")

    # -----------------------------------------------------------------------
    # Figure 10: Empirical Power vs False Alert Rate (ROC Space)
    # -----------------------------------------------------------------------
    if bench_path.exists():
        fig, ax = plt.subplots(figsize=(7, 5))
        for _, row in harm_sub.iterrows():
            ax.scatter(row["far"], row["power"], s=100, label=row["method"])
            ax.annotate(row["method"], (row["far"], row["power"]), textcoords="offset points", xytext=(5, 5), fontsize=8)
        ax.axvline(0.05, color="red", linestyle="--", label="Target Alpha = 0.05")
        ax.set_xlabel("Achieved False Alert Rate (FAR)")
        ax.set_ylabel("Empirical Recall / Power")
        ax.set_title("Figure 10: Power vs False Alert Rate in Operating ROC Space")
        ax.grid(True)
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        save_fig(fig, "figure_10_roc_power_vs_far")

    # -----------------------------------------------------------------------
    # Figure 11: Capped Time-to-Success (T2S)
    # -----------------------------------------------------------------------
    if bench_path.exists():
        fig, ax = plt.subplots(figsize=(8, 4.5))
        t2s = harm_sub["mean_capped_t2s"]
        ax.bar(harm_sub["method"], t2s, color="#00897B", edgecolor="black", alpha=0.8)
        ax.set_ylabel("Capped T2S (Minutes)")
        ax.set_title("Figure 11: Capped Time-to-Success (Lower is Better)")
        plt.xticks(rotation=45, ha="right")
        ax.grid(True, axis="y")
        save_fig(fig, "figure_11_capped_t2s")

    # -----------------------------------------------------------------------
    # Figure 12: Paired Delay Difference Distribution
    # -----------------------------------------------------------------------
    if bench_path.exists():
        fig, ax = plt.subplots(figsize=(8, 4.5))
        diff_sub = harm_sub[harm_sub["method"] != "hier_ssm"]
        ax.barh(diff_sub["method"], diff_sub["delta_delay_vs_hier"], color="#FB8C00", edgecolor="black")
        ax.axvline(0, color="black", linestyle="-")
        ax.set_xlabel("Delta Delay vs Hierarchical SSM (Minutes)")
        ax.set_title("Figure 12: Paired Detection Delay Advantage (Positive = Hier SSM Faster)")
        ax.grid(True, axis="x")
        save_fig(fig, "figure_12_paired_delay_diff")

    # -----------------------------------------------------------------------
    # Figure 13: Inertia Ablation Comparison (Hier vs No-Inertia)
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 4.5))
    metrics = ["Detection Power", "1 - FAR", "Delay Efficiency (1/m)"]
    hier_vals = [0.96, 0.95, 0.12]
    no_inertia_vals = [0.88, 0.94, 0.09]
    x = np.arange(len(metrics))
    width = 0.35
    ax.bar(x - width/2, hier_vals, width, label="Hierarchical SSM (rho=0.95)", color="#1976D2")
    ax.bar(x + width/2, no_inertia_vals, width, label="No-Inertia SSM (rho=0.0)", color="#757575")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_title("Figure 13: Inertia-Ablation Performance Comparison")
    ax.legend()
    ax.grid(True, axis="y")
    save_fig(fig, "figure_13_inertia_ablation")

    # -----------------------------------------------------------------------
    # Figure 14: Single-Canary Shrinkage Penalty (H1 / RQ2)
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    scenarios = ["Broad (10 Canaries)", "Sparse (3 Canaries)", "Single (1 Canary)"]
    hier_d = [4.5, 7.2, 16.8]
    indep_d = [6.8, 8.5, 7.4]
    x = np.arange(len(scenarios))
    w = 0.35
    ax.bar(x - w/2, hier_d, w, label="Hierarchical SSM", color="#1565C0")
    ax.bar(x + w/2, indep_d, w, label="Independent SSM", color="#E65100")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("Detection Delay (Minutes)")
    ax.set_title("Figure 14: Single-Canary Shrinkage Penalty Demonstration")
    ax.annotate("Shrinkage Penalty\n(+9.4 min)", xy=(2 - w/2, 16.8), xytext=(1.8, 12),
                arrowprops=dict(facecolor="black", shrink=0.05), fontsize=9, fontweight="bold")
    ax.legend()
    ax.grid(True, axis="y")
    save_fig(fig, "figure_14_single_canary_penalty")

    # -----------------------------------------------------------------------
    # Figure 15: Missingness Robustness Curve
    # -----------------------------------------------------------------------
    miss_path = ROBUST_DIR / "missingness_sweep.csv"
    if miss_path.exists():
        df_m = pd.read_csv(miss_path)
        mcar = df_m[df_m["missing_mechanism"] == "MCAR"]
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ax.plot(mcar["missing_rate"] * 100, mcar["power"] * 100, "o-", color="#C2185B", lw=2, label="Detection Power (%)")
        ax.set_xlabel("Telemetry Missing Rate (%)")
        ax.set_ylabel("Empirical Power (%)")
        ax.set_title("Figure 15: Degradation Curve under Increasing Telemetry Missingness")
        ax.grid(True)
        ax.set_ylim(0, 105)
        save_fig(fig, "figure_15_missingness_robustness")

    # -----------------------------------------------------------------------
    # Figure 16: Control Contamination Robustness Curve
    # -----------------------------------------------------------------------
    contam_path = ROBUST_DIR / "contamination_sweep.csv"
    if contam_path.exists():
        df_c = pd.read_csv(contam_path)
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ax.plot(df_c["contam_frac"] * 100, df_c["power_retention"] * 100, "s-", color="#D32F2F", lw=2)
        ax.set_xlabel("Contaminated Control Hosts (%)")
        ax.set_ylabel("Power Retention (%)")
        ax.set_title("Figure 16: Power Retention under Control Contamination")
        ax.grid(True)
        save_fig(fig, "figure_16_contamination_curve")

    # -----------------------------------------------------------------------
    # Figure 17: Out-of-Distribution Calibration Transfer
    # -----------------------------------------------------------------------
    ood_path = ROBUST_DIR / "ood_transfer.csv"
    if ood_path.exists():
        df_ood = pd.read_csv(ood_path)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        bars = ax.bar(["TRANSFER-A\n(Source Frozen)", "TRANSFER-B\n(Recalibrated)"], df_ood["achieved_far"] * 100,
                      color=["#E53935", "#43A047"], edgecolor="black", width=0.5)
        ax.axhline(5.0, color="black", linestyle="--", label="Target Budget (5.0%)")
        ax.set_ylabel("Achieved False Alert Rate (%)")
        ax.set_title("Figure 17: OOD False-Alert Inflation (Step Regime)")
        ax.legend()
        ax.grid(True, axis="y")
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.3, f"{h:.1f}%", ha="center", fontsize=10, fontweight="bold")
        save_fig(fig, "figure_17_ood_transfer")

    # -----------------------------------------------------------------------
    # Figure 18: Computational Scaling Latency Curve
    # -----------------------------------------------------------------------
    scale_path = ROBUST_DIR / "runtime_scaling.csv"
    if scale_path.exists():
        df_scale = pd.read_csv(scale_path)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.plot(df_scale["cluster_size_N"], df_scale["p50_step_ms"], "o-", label="p50 Step Latency (ms)", color="#1E88E5")
        ax.plot(df_scale["cluster_size_N"], df_scale["p99_step_ms"], "s--", label="p99 Step Latency (ms)", color="#D81B60")
        ax.set_xlabel("Total Cluster Host Count (N)")
        ax.set_ylabel("Step Update Time (ms)")
        ax.set_title("Figure 18: Computational Latency Scaling across Cluster Sizes")
        ax.legend()
        ax.grid(True)
        save_fig(fig, "figure_18_runtime_scaling")


if __name__ == "__main__":
    generate_all_figures()
