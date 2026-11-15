"""Plot generation strictly from versioned CSV results tables.

Generates:
1. runtime_memory_scaling.png: Runtime (ms/tick) and RAM (MB) vs fleet size.
2. null_validation_audit.png: Achieved FAR vs 5% target with Clopper-Pearson 95% CIs.
3. paired_bootstrap_contrasts.png: Paired bootstrap contrasts (Capped Time difference vs Hierarchical SSM).
4. scenario_detection_horizons.png: Cumulative detection rate by horizon across benchmark scenarios.
5. scenario_timeline_leak.png: 4-panel scenario timeline from saved telemetry and recommendations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_runtime_memory_scaling(
    csv_path: str | Path = "results/runtime_scaling.csv",
    out_path: str | Path = "results/plots/runtime_memory_scaling.png",
) -> Path:
    """Plot runtime and RAM scaling against fleet size from saved benchmark table."""
    df = pd.read_csv(csv_path)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), dpi=150)

    # Panel 1: Execution Time per Tick
    ax1.plot(df["fleet_size"], df["median_ms_per_tick"], marker="o", color="#2563eb", linewidth=2, label="Median ms/tick")
    ax1.fill_between(df["fleet_size"], df["median_ms_per_tick"], df["p95_ms_per_tick"], color="#93c5fd", alpha=0.4, label="p95 band")
    ax1.set_xlabel("Fleet Size (Total Hosts)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Latency per Tick (ms)", fontsize=11, fontweight="bold")
    ax1.set_title("Inference Latency vs Fleet Size", fontsize=12, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left")

    # Panel 2: Process RAM (MB)
    ax2.plot(df["fleet_size"], df["peak_ram_mb"], marker="s", color="#059669", linewidth=2, label="Peak RAM (RSS)")
    ax2.set_xlabel("Fleet Size (Total Hosts)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Process Memory (MB)", fontsize=11, fontweight="bold")
    ax2.set_title("Memory Footprint vs Fleet Size", fontsize=12, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper left")

    # Machine annotation
    machine_desc = df["machine"].iloc[0] if "machine" in df.columns else "Generic CPU"
    fig.suptitle(f"Computational Scaling Across Fleet Sizes ({machine_desc})", fontsize=13, fontweight="bold", y=0.98)
    plt.tight_layout()
    fig.savefig(out_p, bbox_inches="tight")
    plt.close(fig)

    return out_p


def plot_null_validation_audit(
    csv_path: str | Path = "results/table_null_validation.csv",
    out_path: str | Path = "results/plots/null_validation_audit.png",
) -> Path:
    """Plot achieved null alert rates with 95% Clopper-Pearson confidence intervals."""
    df = pd.read_csv(csv_path)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    methods = df["method"].tolist()
    far = df["achieved_far"].to_numpy()
    ci_lower = df["ci_lower_95"].to_numpy()
    ci_upper = df["ci_upper_95"].to_numpy()
    yerr = [far - ci_lower, ci_upper - far]

    bars = ax.bar(methods, far * 100, yerr=np.array(yerr) * 100, capsize=5, color="#3b82f6", edgecolor="#1d4ed8", alpha=0.85)

    # Reference target budget line (5%)
    ax.axhline(5.0, color="#dc2626", linestyle="--", linewidth=2, label="Target Budget (5%)")

    ax.set_ylabel("Achieved False Alert Rate (%)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Detector Method", fontsize=11, fontweight="bold")
    ax.set_title("Independent Null Validation: False Alert Rate with 95% Clopper-Pearson CIs", fontsize=12, fontweight="bold")
    ax.set_ylim(0, 10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, h + 0.3, f"{h:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")

    plt.tight_layout()
    fig.savefig(out_p, bbox_inches="tight")
    plt.close(fig)

    return out_p


def plot_paired_bootstrap_contrasts(
    csv_path: str | Path = "results/table_paired_bootstrap_contrasts.csv",
    out_path: str | Path = "results/plots/paired_bootstrap_contrasts.png",
) -> Path:
    """Forest plot of paired bootstrap contrasts in Capped Time-to-Success."""
    df = pd.read_csv(csv_path)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    y_pos = np.arange(len(df))
    diffs = df["mean_capped_time_difference"].to_numpy()
    ci_lower = df["ci_lower_95"].to_numpy()
    ci_upper = df["ci_upper_95"].to_numpy()
    err_left = diffs - ci_lower
    err_right = ci_upper - diffs

    colors = ["#16a34a" if sup else "#64748b" for sup in df["hierarchy_statistically_superior"]]

    ax.errorbar(diffs, y_pos, xerr=[err_left, err_right], fmt="o", color="#1e293b", ecolor="#64748b", elinewidth=2, capsize=5, markersize=8)
    ax.scatter(diffs, y_pos, c=colors, s=100, zorder=3)

    ax.axvline(0.0, color="#dc2626", linestyle="--", linewidth=1.5, label="Parity (Delta = 0)")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(df["comparator"], fontsize=11, fontweight="bold")
    ax.set_xlabel("Mean Difference in Capped Time (minutes)\nPositive = Hierarchical SSM is faster", fontsize=11, fontweight="bold")
    ax.set_title("Paired Bootstrap Contrasts: Capped Time-to-Success vs Hierarchical SSM", fontsize=12, fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    # Annotate values
    for i, diff in enumerate(diffs):
        ax.text(diff, i + 0.25, f"+{diff:.2f}m" if diff > 0 else f"{diff:.2f}m", ha="center", fontsize=9, fontweight="bold")

    plt.tight_layout()
    fig.savefig(out_p, bbox_inches="tight")
    plt.close(fig)

    return out_p


def plot_scenario_timeline(
    scenario_dir: str | Path = "results/scenarios/release_leak_two_canaries",
    out_path: str | Path = "results/plots/scenario_timeline_leak.png",
) -> Path:
    """Generate multi-panel scenario timeline from saved telemetry and recommendations."""
    scen_path = Path(scenario_dir)
    telem_df = pd.read_csv(scen_path / "telemetry.csv")
    recom_df = pd.read_csv(scen_path / "recommendations.csv")
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, dpi=150)

    ticks = recom_df["tick"].to_numpy()

    # Panel 1: Process Memory
    ax1 = axes[0]
    canary_mem = telem_df[telem_df["exposure"] == True].groupby("tick")["memory_mb"].mean()
    ctrl_mem = telem_df[telem_df["exposure"] == False].groupby("tick")["memory_mb"].mean()

    ax1.plot(canary_mem.index, canary_mem.values, color="#dc2626", linewidth=2, label="Exposed Canaries (srv-r0-s0, srv-r1-s0)")
    ax1.plot(ctrl_mem.index, ctrl_mem.values, color="#64748b", linestyle="--", linewidth=1.5, label="Baseline Controls")
    ax1.axvline(30, color="#94a3b8", linestyle=":", label="Deployment (t0=30)")
    alarm_tick = recom_df[recom_df["canary_release_advisory"].isin(["PAUSE RECOMMENDED", "ROLLED BACK"])]["tick"].min()
    if pd.notna(alarm_tick):
        ax1.axvline(alarm_tick, color="#b91c1c", linestyle="-", linewidth=2, label=f"First Alert (t={int(alarm_tick)})")
    ax1.set_ylabel("Memory (MB)", fontsize=10, fontweight="bold")
    ax1.set_title("Process Memory: Canary Leak vs Controls", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left")

    # Panel 2: Memory Score & Drift Rate
    ax2 = axes[1]
    if "score_mem" in recom_df.columns:
        ax2.plot(ticks, recom_df["score_mem"], color="#7c3aed", linewidth=2, label="Memory Log-Risk Score")
        ax2.axhline(-0.693147, color="#ef4444", linestyle="--", label="Threshold (-0.693)")
    ax2.axvline(30, color="#94a3b8", linestyle=":")
    if pd.notna(alarm_tick):
        ax2.axvline(alarm_tick, color="#b91c1c", linestyle="-", linewidth=2)
    ax2.set_ylabel("Score", fontsize=10, fontweight="bold")
    ax2.set_title("Multi-Channel Memory Growth Channel Decision", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper left")

    # Panel 3: Latency Effect Contrast & CI
    ax3 = axes[2]
    if "canary_effect_mean" in recom_df.columns:
        ax3.plot(ticks, recom_df["canary_effect_mean"] * 100, color="#2563eb", linewidth=2, label="Canary Latency Effect (%)")
        if "canary_effect_ci_lower" in recom_df.columns:
            ax3.fill_between(
                ticks,
                recom_df["canary_effect_ci_lower"] * 100,
                recom_df["canary_effect_ci_upper"] * 100,
                color="#bfdbfe",
                alpha=0.5,
                label="95% Credible Interval",
            )
        ax3.axhline(0.0, color="#64748b", linestyle="--")
        ax3.axhline(np.log(1.02) * 100, color="#ea580c", linestyle=":", label="Harm Boundary (+2%)")
    ax3.axvline(30, color="#94a3b8", linestyle=":")
    if pd.notna(alarm_tick):
        ax3.axvline(alarm_tick, color="#b91c1c", linestyle="-", linewidth=2)
    ax3.set_ylabel("Latency Effect (%)", fontsize=10, fontweight="bold")
    ax3.set_xlabel("Discrete Simulation Tick (minutes)", fontsize=11, fontweight="bold")
    ax3.set_title("Latency Channel: Hierarchical Contrast Effect with Analytical 95% CIs", fontsize=11, fontweight="bold")
    ax3.grid(True, linestyle="--", alpha=0.5)
    ax3.legend(loc="upper left")

    plt.tight_layout()
    fig.savefig(out_p, bbox_inches="tight")
    plt.close(fig)

    return out_p


def generate_all_plots(out_dir: str | Path = "results/plots") -> list[Path]:
    """Generate all static evaluation and benchmark figures from saved CSV tables."""
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    # 1. Scaling Plot
    if Path("results/runtime_scaling.csv").exists():
        p1 = plot_runtime_memory_scaling("results/runtime_scaling.csv", out_p / "runtime_memory_scaling.png")
        generated.append(p1)

    # 2. Null Validation Audit Plot
    if Path("results/table_null_validation.csv").exists():
        p2 = plot_null_validation_audit("results/table_null_validation.csv", out_p / "null_validation_audit.png")
        generated.append(p2)

    # 3. Paired Bootstrap Contrasts Plot
    if Path("results/table_paired_bootstrap_contrasts.csv").exists():
        p3 = plot_paired_bootstrap_contrasts("results/table_paired_bootstrap_contrasts.csv", out_p / "paired_bootstrap_contrasts.png")
        generated.append(p3)

    # 4. Scenario Timeline Plot
    scen_leak_dir = Path("results/scenarios/release_leak_two_canaries")
    if (scen_leak_dir / "telemetry.csv").exists() and (scen_leak_dir / "recommendations.csv").exists():
        p4 = plot_scenario_timeline(scen_leak_dir, out_p / "scenario_timeline_leak.png")
        generated.append(p4)

    return generated
