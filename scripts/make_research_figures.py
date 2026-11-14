"""Generate publication-ready figures and tables for Canary SSM V3 research release.

Reads exclusively from saved experiment CSV and JSON files:
- results/plain_final/table_detection.csv
- results/plain_final/table_paired_differences.csv
- results/study_inertia/table_paired_contrasts.csv
- results/study_inertia/table_scenario_summary.csv
- results/study_inertia/table_calibration_validity.csv
- results/study_combined/table_scenario_summary.csv
- demo/data.json
"""
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Matplotlib styling for academic publication
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

OUT_FIG = Path("paper/FIGURES")
OUT_TAB = Path("paper/TABLES")
OUT_FIG.mkdir(parents=True, exist_ok=True)
OUT_TAB.mkdir(parents=True, exist_ok=True)


def save_fig(fig, base_name):
    png_path = OUT_FIG / f"{base_name}.png"
    svg_path = OUT_FIG / f"{base_name}.svg"
    fig.savefig(png_path)
    fig.savefig(svg_path)
    plt.close(fig)
    print(f"Saved figure: {png_path.name} and {svg_path.name}")


# -------------------------------------------------------------
# Figure 1: Final Test Mean Capped Detection Time Comparison
# -------------------------------------------------------------
def plot_fig1():
    csv_path = Path("results/plain_final/table_detection.csv")
    df = pd.read_csv(csv_path)

    # Key methods to present
    methods_order = [
        ("hier_ssm", "Hierarchical SSM\n(Proposed)", "#1e3a8a"),
        ("indep_ssm", "Independent SSM\n(Unpooled)", "#2563eb"),
        ("sparse_mix_glr", "Sparse Mix GLR\n(Siegmund)", "#0d9488"),
        ("glr_window", "Windowed GLR\n(Sequential)", "#059669"),
        ("pooled_ssm", "Pooled SSM\n(Mean-Only)", "#d97706"),
        ("topk_cusum", "Top-K CUSUM\n(Extreme Host)", "#ea580c"),
        ("adj_cusum", "Workload CUSUM\n(Baseline)", "#dc2626"),
        ("mw_judge", "Mann-Whitney\n(Non-Param)", "#7c3aed"),
    ]

    sub = df[df["method"].isin([m[0] for m in methods_order])].copy()
    sub["sort_idx"] = sub["method"].map({m[0]: i for i, m in enumerate(methods_order)})
    sub = sub.sort_values("sort_idx")

    names = [m[1] for m in methods_order]
    colors = [m[2] for m in methods_order]
    times = sub["mean_capped_time"].values
    misses = sub["miss"].values * 100

    fig, ax1 = plt.subplots(figsize=(9, 4.5))

    x = np.arange(len(names))
    width = 0.55

    bars = ax1.bar(x, times, width, color=colors, alpha=0.85, edgecolor="black", linewidth=0.8)
    ax1.set_ylabel("Mean Horizon-Capped Time (min)")
    ax1.set_title("Detection Latency Across Methods on Unseen Plain Test Set (N = 959 events)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, rotation=25, ha="right")
    ax1.set_ylim(0, 60)

    # Annotate miss rate on top of bars
    for bar, miss in zip(bars, misses):
        h = bar.get_height()
        ax1.annotate(f"{h:.1f}m\n({miss:.1f}% miss)",
                     xy=(bar.get_x() + bar.get_width() / 2, h),
                     xytext=(0, 3),
                     textcoords="offset points",
                     ha="center", va="bottom", fontsize=8)

    save_fig(fig, "fig1_detection_delay_comparison")


# -------------------------------------------------------------
# Figure 2: Hierarchical Pooling Benefit vs Single-Host Trade-off
# -------------------------------------------------------------
def plot_fig2():
    csv_path = Path("results/study_inertia/table_paired_contrasts.csv")
    df = pd.read_csv(csv_path)

    # Filter C2 contrasts at m=1
    c2 = df[(df["contrast"] == "C2_pooling:hier_ssm-vs-indep_ssm@m1")].copy()
    c2 = c2.sort_values("mean_capped_diff")

    scenarios = c2["scenario"].values
    diffs = c2["mean_capped_diff"].values
    ci_lo = c2["ci_lo"].values
    ci_hi = c2["ci_hi"].values
    y_err = [diffs - ci_lo, ci_hi - diffs]

    colors = ["#16a34a" if d < -1 else ("#dc2626" if d > 1 else "#64748b") for d in diffs]

    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(scenarios))

    ax.errorbar(diffs, y, xerr=y_err, fmt="o", color="black", ecolor="gray", elinewidth=1.2, capsize=3, zorder=3)
    ax.scatter(diffs, y, color=colors, s=50, zorder=4)

    ax.axvline(0, color="black", linestyle="--", linewidth=1, alpha=0.7)
    ax.axvline(-3, color="green", linestyle=":", linewidth=0.8, alpha=0.5, label="H1 Benefit (>3m speedup)")
    ax.axvline(3, color="red", linestyle=":", linewidth=0.8, alpha=0.5, label="H1 Cost Check (>3m delay)")

    ax.set_yticks(y)
    ax.set_yticklabels(scenarios)
    ax.set_xlabel("Mean Capped Delay Difference: hier_ssm - indep_ssm (min)\n[Negative favors hier_ssm]")
    ax.set_title("Hierarchical Pooling Contrast Across Scenarios (C2 at m=1, N=300 rollouts/cell)")
    ax.legend(loc="lower right")

    save_fig(fig, "fig2_hier_vs_indep_pooling")


# -------------------------------------------------------------
# Figure 3: Gate G2 Calibration Validity Envelope
# -------------------------------------------------------------
def plot_fig3():
    csv_path = Path("results/study_inertia/table_calibration_validity.csv")
    df = pd.read_csv(csv_path)

    fig, ax = plt.subplots(figsize=(7, 4.5))

    far = df["far"] * 100
    pval = df["bb_pvalue_two_sided"]
    methods = df["method"].unique()

    markers = {"hier_ssm": "o", "hier_ts": "^", "indep_ssm": "s", "glr_window": "D", "adj_cusum": "v"}
    colors = {"hier_ssm": "#1e3a8a", "hier_ts": "#0284c7", "indep_ssm": "#2563eb", "glr_window": "#059669", "adj_cusum": "#dc2626"}

    for m in methods:
        sub = df[df["method"] == m]
        ax.scatter(sub["far"] * 100, sub["bb_pvalue_two_sided"],
                   marker=markers.get(m, "o"), color=colors.get(m, "gray"),
                   s=45, alpha=0.8, label=m)

    ax.axvline(5.0, color="gray", linestyle="-", linewidth=1, label="Nominal Target (5.0%)")
    ax.axvline(7.5, color="red", linestyle="--", linewidth=1, label="Gate G2 Rate Ceiling (7.5%)")
    ax.axhline(0.01, color="red", linestyle=":", linewidth=1, label="Gate G2 p-value Floor (0.01)")

    ax.set_xlim(2.5, 8.5)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("Achieved False-Alert Rate (%) on Validation Nulls (n = 2,000)")
    ax.set_ylabel("Two-Sided Beta-Binomial p-value")
    ax.set_title("Gate G2 Calibration Validity Envelope (N = 50 Primary Study Cells)")
    ax.legend(loc="upper right", framealpha=0.9)

    save_fig(fig, "fig3_calibration_validity_gate_g2")


# -------------------------------------------------------------
# Figure 4: Robustness Under Heavy-Tailed Telemetry Noise
# -------------------------------------------------------------
def plot_fig4():
    csv_path = Path("results/study_combined/table_scenario_summary.csv")
    df = pd.read_csv(csv_path)

    # Scenarios: compare plain regression (regression_recovery) vs regression_plus_heavytail
    ht = df[(df["scenario"] == "regression_plus_heavytail") & (df["m_on"] == 1)].copy()

    methods = [
        ("hier_ssm", "Hierarchical SSM", "#1e3a8a"),
        ("indep_ssm", "Independent SSM", "#2563eb"),
        ("glr_window", "Windowed GLR", "#059669"),
        ("adj_cusum", "Workload CUSUM", "#dc2626"),
    ]

    sub = ht[ht["method"].isin([m[0] for m in methods])].copy()
    sub["sort_idx"] = sub["method"].map({m[0]: i for i, m in enumerate(methods)})
    sub = sub.sort_values("sort_idx")

    names = [m[1] for m in methods]
    far_rates = sub["null_alert_rate"].values * 100
    powers = sub["power"].values * 100

    fig, ax1 = plt.subplots(figsize=(8, 4))
    x = np.arange(len(names))
    width = 0.35

    b1 = ax1.bar(x - width/2, far_rates, width, label="False-Alert Rate (%)", color="#f87171", edgecolor="black")
    b2 = ax1.bar(x + width/2, powers, width, label="Empirical Power (%)", color="#34d399", edgecolor="black")

    ax1.axhline(7.5, color="red", linestyle="--", linewidth=1, label="Gate G2 FAR Bound (7.5%)")

    ax1.set_ylabel("Percentage (%)")
    ax1.set_title("Detector Performance Under Heavy-Tailed Noise (t-dist, df=3, N=300 pairs)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names)
    ax1.set_ylim(0, 105)
    ax1.legend(loc="center right")

    for bar in b1:
        h = bar.get_height()
        ax1.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                     xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8)

    for bar in b2:
        h = bar.get_height()
        ax1.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                     xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8)

    save_fig(fig, "fig4_combined_robustness_heavytail")


# -------------------------------------------------------------
# Figure 5: Decision Hysteresis Depth Trade-Off (H3)
# -------------------------------------------------------------
def plot_fig5():
    csv_path = Path("results/study_inertia/table_scenario_summary.csv")
    df = pd.read_csv(csv_path)

    # Scenarios for H3: non-event disturbance (iso_spike_1host) vs weak_persistent_3host
    spikes = df[(df["scenario"] == "iso_spike_1host") & (df["method"] == "hier_ssm")].sort_values("m_on")
    weak = df[(df["scenario"] == "weak_persistent_3host") & (df["method"] == "hier_ssm")].sort_values("m_on")

    m_vals = spikes["m_on"].values
    false_pauses = spikes["harm_rollout_noevent_alert_rate"].values * 100
    capped_delays = weak["mean_capped"].values

    fig, ax1 = plt.subplots(figsize=(7.5, 4.2))

    color1 = "#dc2626"
    ax1.set_xlabel("Confirmation Depth m (Consecutive Transgressions)")
    ax1.set_ylabel("False Pauses on Transient Spikes (%)", color=color1)
    line1 = ax1.plot(m_vals, false_pauses, marker="o", color=color1, linewidth=2, label="False Pauses (iso_spike)")
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.set_ylim(0, 20)

    ax2 = ax1.twinx()
    color2 = "#2563eb"
    ax2.set_ylabel("Mean Capped Delay on Weak Harm (min)", color=color2)
    line2 = ax2.plot(m_vals, capped_delays, marker="s", color=color2, linewidth=2, linestyle="--", label="Delay on Weak Harm")
    ax2.tick_params(axis="y", labelcolor=color2)
    ax2.set_ylim(15, 40)

    plt.title("Hysteresis Trade-Off: Transient Spike Suppression vs Delay on Weak Harm")
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="center right")

    save_fig(fig, "fig5_hysteresis_tradeoff")


# -------------------------------------------------------------
# Figure 6: Synthetic Telemetry Trajectory & State-Space Filtering
# -------------------------------------------------------------
def plot_fig6():
    data_path = Path("demo/data.json")
    if not data_path.exists():
        print("Skipping fig6: demo/data.json not found")
        return

    with open(data_path) as f:
        demo_data = json.load(f)

    sc = demo_data["regression_recovery"]
    t = np.array(sc["t"])
    canary = np.array(sc["canary_latency"])
    control = np.array(sc["control_latency"])
    contrast = np.array(sc["contrast"])
    true_eff = np.array(sc["true_effect"])
    prob = np.array(sc["ssm_prob"])
    rollout_t = sc["rollout_time"]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(9, 6.5), sharex=True)

    # Subplot 1: Raw Telemetry
    ax1.plot(t, canary, label="Canary Latency", color="#fb923c", linewidth=1.5)
    ax1.plot(t, control, label="Control Latency", color="#38bdf8", linewidth=1.2)
    ax1.axvline(rollout_t, color="black", linestyle="--", linewidth=1, label="Rollout Start (t=180)")
    ax1.set_ylabel("Latency (ms)")
    ax1.set_title("Canary Telemetry and Hierarchical State-Space Estimation (Regression Recovery)")
    ax1.legend(loc="upper left")

    # Subplot 2: Contrast & True Harm
    ax2.plot(t, contrast, label="Adjusted Contrast", color="#0d9488", linewidth=1.2)
    ax2.plot(t, true_eff, label="True Effect a_t", color="#dc2626", linestyle="--", linewidth=1.5)
    ax2.axvline(rollout_t, color="black", linestyle="--", linewidth=1)
    ax2.set_ylabel("Contrast (log ms)")
    ax2.legend(loc="upper left")

    # Subplot 3: Posterior Harm Probability
    ax3.plot(t, prob, label="SSM P(Harm | y_1:t)", color="#16a34a", linewidth=2)
    ax3.axhline(0.85, color="red", linestyle=":", linewidth=1, label="Alarm Threshold tau_high (0.85)")
    ax3.axhline(0.25, color="blue", linestyle=":", linewidth=1, label="Clear Threshold tau_low (0.25)")
    ax3.axvline(rollout_t, color="black", linestyle="--", linewidth=1)
    ax3.set_ylabel("P(Harm)")
    ax3.set_xlabel("Time (min)")
    ax3.set_ylim(-0.05, 1.05)
    ax3.legend(loc="upper left")

    save_fig(fig, "fig6_telemetry_contrast_simulation")


# -------------------------------------------------------------
# Generate Publication Tables in CSV, Markdown, and LaTeX
# -------------------------------------------------------------
def df_to_latex(df, caption="", label=""):
    """Format DataFrame as LaTeX table without requiring Jinja2."""
    cols = df.columns.tolist()
    col_align = "l" + "r" * (len(cols) - 1)
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{{col_align}}}",
        "\\toprule",
        " & ".join(cols) + " \\\\",
        "\\midrule"
    ]
    for _, row in df.iterrows():
        row_str = " & ".join(str(val) for val in row.values) + " \\\\"
        lines.append(row_str)
    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}"
    ])
    return "\n".join(lines)


def make_tables():
    # Table 1: Plain Final Test Detection Results
    df_det = pd.read_csv("results/plain_final/table_detection.csv")
    df_null = pd.read_csv("results/plain_final/table_null_rates.csv")
    merged = df_det.merge(df_null[["method", "rate", "ci_lo", "ci_hi"]], on="method", how="left")

    key_methods = ["hier_ssm", "indep_ssm", "hier_rw", "hier_huber", "sparse_mix_glr", "glr_window", "pooled_ssm", "topk_cusum", "adj_cusum", "mw_judge", "adj_ewma"]
    sub = merged[merged["method"].isin(key_methods)].copy()
    sub["sort_idx"] = sub["method"].map({m: i for i, m in enumerate(key_methods)})
    sub = sub.sort_values("sort_idx")

    tab1 = sub[["method", "rate", "miss", "premature", "late_after_recovery", "mean_capped_time", "cond_delay_median"]].copy()
    tab1.columns = ["Method", "Null FAR", "Miss Rate", "Premature", "Late Post-Rec", "Mean Capped (min)", "Median Delay (min)"]
    tab1["Null FAR"] = tab1["Null FAR"].apply(lambda v: f"{v*100:.2f}%")
    tab1["Miss Rate"] = tab1["Miss Rate"].apply(lambda v: f"{v*100:.2f}%")
    tab1["Premature"] = tab1["Premature"].apply(lambda v: f"{v*100:.2f}%")
    tab1["Late Post-Rec"] = tab1["Late Post-Rec"].apply(lambda v: f"{v*100:.2f}%")
    tab1["Mean Capped (min)"] = tab1["Mean Capped (min)"].round(2)
    tab1["Median Delay (min)"] = tab1["Median Delay (min)"].round(1)

    tab1.to_csv(OUT_TAB / "tab1_final_test_detection_plain.csv", index=False)
    with open(OUT_TAB / "tab1_final_test_detection_plain.md", "w") as f:
        f.write(tab1.to_markdown(index=False))
    with open(OUT_TAB / "tab1_final_test_detection_plain.tex", "w") as f:
        f.write(df_to_latex(tab1, caption="Detection performance on unseen plain test dataset.", label="tab:plain_final"))

    print("Generated Table 1 (CSV, MD, TeX)")

    # Table 2: Paired Differences (Plain Final)
    df_diff = pd.read_csv("results/plain_final/table_paired_differences.csv")
    df_diff.to_csv(OUT_TAB / "tab2_plain_paired_differences.csv", index=False)
    with open(OUT_TAB / "tab2_plain_paired_differences.md", "w") as f:
        f.write(df_diff.to_markdown(index=False))
    with open(OUT_TAB / "tab2_plain_paired_differences.tex", "w") as f:
        f.write(df_to_latex(df_diff, caption="Paired bootstrap differences against hier_ssm on plain test dataset.", label="tab:paired_diff"))

    print("Generated Table 2 (CSV, MD, TeX)")

    # Table 3: Combined Robustness Summary
    df_comb = pd.read_csv("results/study_combined/table_scenario_summary.csv")
    sub_comb = df_comb[df_comb["m_on"] == 1][["scenario", "method", "null_alert_rate", "power", "miss", "mean_capped"]].copy()
    sub_comb["null_alert_rate"] = sub_comb["null_alert_rate"].apply(lambda v: f"{v*100:.1f}%")
    sub_comb["power"] = sub_comb["power"].apply(lambda v: f"{v*100:.1f}%")
    sub_comb["miss"] = sub_comb["miss"].apply(lambda v: f"{v*100:.1f}%")
    sub_comb["mean_capped"] = sub_comb["mean_capped"].round(2)

    sub_comb.to_csv(OUT_TAB / "tab3_combined_robustness_summary.csv", index=False)
    with open(OUT_TAB / "tab3_combined_robustness_summary.md", "w") as f:
        f.write(sub_comb.to_markdown(index=False))
    with open(OUT_TAB / "tab3_combined_robustness_summary.tex", "w") as f:
        f.write(df_to_latex(sub_comb, caption="Multi-stressor robustness scenario evaluation summary.", label="tab:robustness"))

    print("Generated Table 3 (CSV, MD, TeX)")


if __name__ == "__main__":
    print("Generating research figures...")
    plot_fig1()
    plot_fig2()
    plot_fig3()
    plot_fig4()
    plot_fig5()
    plot_fig6()
    print("Generating publication tables...")
    make_tables()
    print("All figures and tables generated successfully!")
