"""Tables and figures generated ONLY from saved result CSVs (handbook Sections 9-10)."""
from __future__ import annotations

import json
from pathlib import Path

import json

import numpy as np
import pandas as pd

from .metrics import DETECT_HORIZONS, clopper_pearson, paired_bootstrap

BASE = ["matched_contrast", "adj_ewma", "adj_cusum", "topk_cusum"]


ALPHA, UPPER_LIMIT, MIN_N_GATE = 0.05, 0.08, 400   # upper<=8% is unreachable for a correct 5% method at small n


def null_rate_table(nl: pd.DataFrame, by: list) -> pd.DataFrame:
    if nl.empty:
        raise ValueError("no null (no_event) rollouts in the results: cannot compute false-alert rates or the calibration gate")
    rows = []
    for key, d in nl.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        k, n = int(d["alerted"].sum()), len(d); lo, hi = clopper_pearson(k, n)
        rows.append({**dict(zip(by, key)), "alerts": k, "n_null": n, "rate": k / n, "ci_lo": lo, "ci_hi": hi,
                     "pass_contains_5pct": bool(lo <= ALPHA <= hi), "pass_upper_le_8pct": bool(hi <= UPPER_LIMIT),
                     "above_target": bool(lo > ALPHA), "gate_evaluable": bool(n >= MIN_N_GATE)})
    return pd.DataFrame(rows)


def calibration_gate(fam: pd.DataFrame) -> dict:
    """PASS only if every EVALUABLE cell (n >= 400) has CI upper bound <= 8% AND no smaller cell is demonstrably above 5%."""
    ev = fam["gate_evaluable"]
    bad = fam[(ev & ~fam["pass_upper_le_8pct"]) | (~ev & fam["above_target"])]
    return {"criterion": "95% Clopper-Pearson upper bound <= 0.08 where n>=400; cells with n<400 only fail if the interval lies above 5%",
            "cells": int(len(fam)), "evaluable_cells": int(ev.sum()),
            "cells_ok": int(len(fam) - len(bad)), "status": "FAIL" if not bad.empty else ("PASS" if ev.any() else "NOT_EVALUABLE"),
            "failing": bad[["family", "method", "n_null", "rate", "ci_lo", "ci_hi"]].round(4).to_dict("records")}


def make_report(res_dir: Path, validation: Path | None = None) -> None:
    res = Path(res_dir)
    df = pd.read_csv(res / "per_rollout_metrics.csv")
    methods = list(df["method"].unique())

    # ---- null alert rates with exact binomial intervals; PASS labels computed from the numbers only
    nl = df[df["kind"] == "no_event"].assign(alerted=lambda d: d["alarm_time"].notna())
    rates = null_rate_table(nl, ["method"])
    rates.to_csv(res / "table_null_rates.csv", index=False)
    fam = null_rate_table(nl, ["family", "method"]); fam.to_csv(res / "table_null_by_family.csv", index=False)
    gate = calibration_gate(fam)
    (res / "gate_status.json").write_text(json.dumps(gate, indent=1))
    # abstention (ineligible minutes): a detector that never alerts under missingness is blind, not robust
    df.groupby(["family", "method"])["elig_frac"].mean().rename("eligible_fraction").reset_index() \
        .to_csv(res / "table_abstention.csv", index=False)

    # ---- detection outcomes on qualifying events
    ev = df[df["kind"] == "event"]
    rows = []
    for m in methods:
        d = ev[ev["method"] == m]
        row = {"method": m, "n_events": len(d), "miss": d["status"].eq("miss").mean(),
               "premature": d["status"].eq("premature").mean(), "late_after_recovery": d["status"].eq("late_after_recovery").mean(),
               "mean_capped_time": d["capped"].mean(), "cond_delay_mean": d["delay"].mean(), "cond_delay_median": d["delay"].median()}
        for h in DETECT_HORIZONS:
            dh = d[d["followup"] >= h]
            row[f"P_detect_{h}m"] = (dh["status"].eq("success") & (dh["delay"] <= h)).mean() if len(dh) else np.nan
        rows.append(row)
    det = pd.DataFrame(rows); det.to_csv(res / "table_detection.csv", index=False)

    # ---- transient challenge set (reported separately, never folded into healthy)
    tr = df[df["kind"] == "transient"]
    if len(tr):
        tr.groupby("method")["alarm_time"].apply(lambda s: s.notna().mean()).rename("alarm_rate").reset_index() \
            .to_csv(res / "table_transient.csv", index=False)

    # ---- per-family null rates / detection
    ev.assign(success=ev["status"].eq("success")).groupby(["family", "method"])["success"].mean().reset_index() \
        .to_csv(res / "table_success_by_family.csv", index=False)

    # ---- localization + Brier
    hp = res / "host_metrics.csv"
    if hp.exists() and hp.stat().st_size > 2:
        pd.read_csv(hp).groupby("method")[["top3_recall", "cut_precision", "cut_recall", "cut_fdp"]].mean().reset_index() \
            .to_csv(res / "table_localization.csv", index=False)
    df.groupby("method")["brier"].mean().dropna().reset_index().to_csv(res / "table_brier.csv", index=False)

    # ---- paired method differences on capped time (rollout-level bootstrap)
    piv = ev.pivot_table(index="rollout_id", columns="method", values="capped")
    best_base = min([m for m in BASE if m in piv], key=lambda m: piv[m].mean(), default=None)
    pairs = [("hier_ssm", "indep_ssm"), ("hier_ssm", "pooled_ssm"), ("hier_ssm", best_base)] + \
            [("hier_ssm", a) for a in ("hier_no_persist", "hier_rank0", "hier_white", "hier_degraded")]
    rows = []
    for a, b in pairs:
        if a in piv and b in piv:
            mean, lo, hi = paired_bootstrap((piv[a] - piv[b]).to_numpy())
            rows.append({"A": a, "B": b, "mean_capped_diff_A_minus_B": mean, "ci_lo": lo, "ci_hi": hi,
                         "reading": "negative favours A (faster / fewer misses)"})
    pd.DataFrame(rows).to_csv(res / "table_paired_differences.csv", index=False)

    # ---- flicker summary
    fp = res / "flicker.csv"
    if fp.exists():
        pd.read_csv(fp).groupby(["method", "harm"])[["reversals", "time_paused"]].mean().reset_index() \
            .to_csv(res / "table_flicker.csv", index=False)

    _plots(res, det, methods)
    (res / "report.md").write_text(_markdown(res))


def _plots(res: Path, det: pd.DataFrame, methods) -> None:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = [f"P_detect_{h}m" for h in DETECT_HORIZONS]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for _, r in det.iterrows():
        ax.plot(DETECT_HORIZONS, [r[c] for c in cols], marker="o", label=r["method"])
    ax.set_xlabel("minutes from event onset"); ax.set_ylabel("P(successful detection)")
    ax.set_title("Detection curves at calibrated false-alert budget"); ax.legend(fontsize=7); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(res / "fig_detection_curves.png", dpi=150); plt.close(fig)
    cb = pd.read_csv(res / "calibration_bins.csv")
    fig, ax = plt.subplots(figsize=(5, 5)); ax.plot([0, 1], [0, 1], "k--", lw=1)
    for m, d in cb.groupby("method"):
        d = d[d["n"] > 0]; ax.plot(d["sum_p"] / d["n"], d["sum_j"] / d["n"], marker="o", label=m)
    ax.set_xlabel("mean predicted Pr(a > kappa)"); ax.set_ylabel("observed frequency of J")
    ax.set_title("Host-level probability calibration"); ax.legend(fontsize=7); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(res / "fig_calibration.png", dpi=150); plt.close(fig)


def _markdown(res: Path) -> str:
    g = json.loads((res / "gate_status.json").read_text())
    out = ["# Results (generated from CSVs; interpret per handbook Section 15)\n",
           "Simulation results under stated assumptions only. Losing methods stay in the tables.\n",
           f"**Calibration gate: {g['status']}** ({g['cells_ok']}/{g['cells']} method x family cells ok; {g['evaluable_cells']} have n>=400). "
           "Delay/power comparisons are valid only for methods inside this gate.\n"]
    for t in ["table_null_rates", "table_null_by_family", "table_abstention", "table_detection", "table_paired_differences", "table_localization", "table_brier",
              "table_flicker", "table_transient"]:
        p = res / f"{t}.csv"
        if p.exists():
            out += [f"\n## {t}\n", pd.read_csv(p).round(4).to_markdown(index=False) if _has_tab() else pd.read_csv(p).round(4).to_string(index=False)]
    return "\n".join(out)


def _has_tab() -> bool:
    try:
        import tabulate  # noqa
        return True
    except ImportError:
        return False
