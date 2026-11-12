"""Tables and figures generated ONLY from saved result CSVs (handbook Sections 9-10)."""
from __future__ import annotations

import json
from pathlib import Path

import json

import numpy as np
import pandas as pd

from scipy.stats import binom

from .metrics import DETECT_HORIZONS, betabinom_for_threshold, betabinom_validity, clopper_pearson, paired_bootstrap
from .oracles import efficiency_ratio, is_oracle_method

BASE = [
    "matched_contrast", "adj_ewma", "adj_cusum", "topk_cusum",
    "wmean", "ar_cusum", "glr_window", "sparse_mix_glr", "bocpd", "msprt", "mw_judge",
]


ALPHA, UPPER_LIMIT, MIN_N_GATE = 0.05, 0.08, 400   # legacy exploratory constant
MIN_N_GATE_G2 = 2000
MAX_RATE_G2 = 0.075
BB_P_FLOOR = 0.01


def null_rate_table(
    nl: pd.DataFrame,
    by: list,
    cal_info: dict | None = None,
    min_n: int | None = None,
) -> pd.DataFrame:
    if nl.empty:
        raise ValueError("no null (no_event) rollouts in the results: cannot compute false-alert rates or the calibration gate")
    gate_n = MIN_N_GATE if min_n is None else int(min_n)
    rows = []
    for key, d in nl.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        k, n = int(d["alerted"].sum()), len(d); lo, hi = clopper_pearson(k, n)
        rec = {
            **dict(zip(by, key)), "alerts": k, "n_null": n, "rate": k / n, "ci_lo": lo, "ci_hi": hi,
            "pass_contains_5pct": bool(lo <= ALPHA <= hi), "pass_upper_le_8pct": bool(hi <= UPPER_LIMIT),
            "above_target": bool(lo > ALPHA), "gate_evaluable": bool(n >= gate_n),
        }
        if cal_info is not None and "method" in rec:
            m_info = cal_info[rec["method"]] if rec["method"] in cal_info else cal_info
            if isinstance(m_info, dict) and "B" in m_info and "k" in m_info:
                bb = betabinom_for_threshold(k, n, int(m_info["B"]), int(m_info["k"]))
                rec["expected_alerts"] = bb["expected_alerts"]
                rec["bb_sd"] = bb["bb_sd"]
                rec["bb_pvalue_two_sided"] = bb["bb_pvalue_two_sided"]
        rows.append(rec)
    return pd.DataFrame(rows)


def calibration_gate(
    fam: pd.DataFrame,
    gate_mode: str = "auto",
    min_n: int | None = None,
    regime: str | None = None,
) -> dict:
    """Gate G2 (bb_p >= 0.01 & rate <= 0.075 with multiplicity bound) or legacy CP<=0.08 rule."""
    if fam.empty:
        return {
            "criterion": "empty validation table",
            "regime": regime,
            "cells": 0, "evaluable_cells": 0, "cells_ok": 0,
            "failing_cells_expected_by_chance": 0.0,
            "status": "NOT_EVALUABLE", "failing": [],
        }

    use_g2 = (gate_mode == "g2") or (gate_mode == "auto" and "bb_pvalue_two_sided" in fam.columns)
    n_col = "n_null" if "n_null" in fam.columns else "n"

    if not use_g2:
        ev = fam["gate_evaluable"] if "gate_evaluable" in fam.columns else (fam[n_col] >= (MIN_N_GATE if min_n is None else int(min_n)))
        bad = fam[(ev & ~fam["pass_upper_le_8pct"]) | (~ev & fam["above_target"])]
        status = "FAIL" if not bad.empty else ("PASS" if ev.any() else "NOT_EVALUABLE")
        return {
            "criterion": "95% Clopper-Pearson upper bound <= 0.08 where n>=400; cells with n<400 only fail if the interval lies above 5%",
            "regime": regime,
            "cells": int(len(fam)), "evaluable_cells": int(ev.sum()),
            "cells_ok": int(len(fam) - len(bad)),
            "failing_cells_expected_by_chance": round(0.01 * len(fam), 4),
            "status": status,
            "failing": bad[["family", "method", n_col, "rate", "ci_lo", "ci_hi"]].round(4).to_dict("records"),
        }

    req_n = MIN_N_GATE_G2 if min_n is None else int(min_n)
    ev = fam["gate_evaluable"] if (min_n is None and "gate_evaluable" in fam.columns) else (fam[n_col] >= req_n)
    ev_df = fam[ev]
    n_ev = int(ev.sum())
    if n_ev == 0:
        bad_small = fam[fam["above_target"]] if "above_target" in fam.columns else fam.iloc[0:0]
        status = "FAIL" if not bad_small.empty else "NOT_EVALUABLE"
        bad = bad_small
    else:
        p_fail = ev_df["bb_pvalue_two_sided"] < BB_P_FLOOR
        rate_fail = ev_df["rate"] > MAX_RATE_G2
        # Multiplicity check under exchangeability: P(Binomial(n_ev, 0.01) >= k_p_fail) < 0.01
        k_p_fail = int(p_fail.sum())
        mult_exceeded = (k_p_fail > 0) and (float(binom.sf(k_p_fail - 1, n_ev, BB_P_FLOOR)) < 0.01)
        severe_fail = rate_fail | (p_fail & rate_fail)
        bad = ev_df[severe_fail | p_fail] if (mult_exceeded or severe_fail.any()) else ev_df[severe_fail]
        if bad.empty and (mult_exceeded or severe_fail.any()):
            status = "FAIL"
        elif not bad.empty:
            status = "FAIL"
        else:
            status = "PASS"

    cols = [c for c in ["family", "method", n_col, "alerts", "rate", "ci_lo", "ci_hi", "expected_alerts", "bb_pvalue_two_sided"] if c in fam.columns]
    return {
        "criterion": f"Gate G2: exact Beta-Binomial two-sided p >= {BB_P_FLOOR} (with multiplicity allowance) and achieved rate <= {MAX_RATE_G2} where n >= {req_n}",
        "gate_mode": "g2",
        "min_n_required": req_n,
        "regime": regime,
        "cells": int(len(fam)),
        "evaluable_cells": n_ev,
        "cells_ok": int(len(fam) - len(bad)),
        "failing_cells_expected_by_chance": round(BB_P_FLOOR * n_ev, 4),
        "p_lt_001_count": int((ev_df["bb_pvalue_two_sided"] < BB_P_FLOOR).sum()) if n_ev else 0,
        "status": status,
        "failing": bad[cols].round(5).to_dict("records"),
    }


def make_report(res_dir: Path, validation: Path | None = None, gate_mode: str = "auto", min_n: int | None = None) -> None:
    res = Path(res_dir)
    df = pd.read_csv(res / "per_rollout_metrics.csv")
    methods = list(df["method"].unique())
    man_path = res / "experiment_manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    regime = man.get("regime")
    if regime is None and "regime" in df.columns and df["regime"].notna().any():
        regime = str(df["regime"].dropna().iloc[0])

    # ---- null alert rates with exact binomial intervals; PASS labels computed from the numbers only
    nl = df[df["kind"] == "no_event"].assign(alerted=lambda d: d["alarm_time"].notna())
    rates = null_rate_table(nl, ["method"], min_n=min_n)
    rates = null_rate_table(nl, ["method"], min_n=min_n)
    rates["is_oracle"] = rates["method"].map(is_oracle_method)
    rates["role"] = np.where(rates["is_oracle"], "ORACLE", "method")
    rates.to_csv(res / "table_null_rates.csv", index=False)
    fam = null_rate_table(nl, ["family", "method"], min_n=min_n); fam.to_csv(res / "table_null_by_family.csv", index=False)

    val_fam_path = Path(validation) if validation is not None else None
    if val_fam_path is None:
        pol_dir = Path(man["policy_dir"]) if man.get("policy_dir") else None
        if pol_dir is not None and (pol_dir / "table_validation_by_family.csv").exists():
            val_fam_path = pol_dir / "table_validation_by_family.csv"
    if val_fam_path is not None and val_fam_path.is_dir():
        val_fam_path = val_fam_path / "table_validation_by_family.csv"

    if val_fam_path is not None and val_fam_path.exists():
        val_fam = pd.read_csv(val_fam_path)
        gate = calibration_gate(val_fam, gate_mode=gate_mode if gate_mode != "auto" else "g2", min_n=min_n, regime=regime)
        gate["source"] = str(val_fam_path)
    else:
        gate = calibration_gate(fam, gate_mode=gate_mode, min_n=min_n, regime=regime)
        gate["source"] = str(res / "table_null_by_family.csv")
    (res / "gate_status.json").write_text(json.dumps(gate, indent=1), encoding="utf-8")
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
    det = pd.DataFrame(rows)
    if not det.empty:
        det["is_oracle"] = det["method"].map(is_oracle_method)
        det["role"] = np.where(det["is_oracle"], "ORACLE", "method")
        miss_cap = float(ev["followup"].mean()) if "followup" in ev.columns and not ev.empty else float("nan")
        for om in ("oracle_cusum", "oracle_bayes"):
            om_rows = det[det["method"] == om]
            if not om_rows.empty:
                ocap = float(om_rows["mean_capped_time"].iloc[0])
                det[f"eff_ratio_{om}"] = [
                    np.nan if bool(r["is_oracle"]) else efficiency_ratio(r["mean_capped_time"], ocap, miss_cap)
                    for _, r in det.iterrows()
                ]
    det.to_csv(res / "table_detection.csv", index=False)

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
        hdf = pd.read_csv(hp)
        loc_cols = [c for c in ["top3_recall", "cut_precision", "cut_recall", "cut_fdp", "host_auc"] if c in hdf.columns]
        if loc_cols:
            loc_tbl = hdf.groupby("method")[loc_cols].mean().reset_index()
            loc_tbl["is_oracle"] = loc_tbl["method"].map(is_oracle_method)
            loc_tbl["role"] = np.where(loc_tbl["is_oracle"], "ORACLE", "method")
            loc_tbl.to_csv(res / "table_localization.csv", index=False)
    df.groupby("method")["brier"].mean().dropna().reset_index().to_csv(res / "table_brier.csv", index=False)

    # ---- paired method differences on capped time (rollout-level bootstrap)
    piv = ev.pivot_table(index="rollout_id", columns="method", values="capped")
    best_base = min([m for m in BASE if m in piv and not is_oracle_method(m)], key=lambda m: piv[m].mean(), default=None)
    pairs = [("hier_ssm", "indep_ssm"), ("hier_ssm", "pooled_ssm"), ("hier_ssm", best_base)] + \
            [("hier_ssm", a) for a in ("hier_no_persist", "hier_rw", "hier_rank0", "hier_white", "hier_degraded")]
    rows = []
    for a, b in pairs:
        if a in piv and b in piv:
            mean, lo, hi = paired_bootstrap((piv[a] - piv[b]).to_numpy())
            rows.append({"A": a, "B": b, "mean_capped_diff_A_minus_B": mean, "ci_lo": lo, "ci_hi": hi,
                         "reading": "negative favours A (faster / fewer misses)"})
    pd.DataFrame(rows, columns=["A", "B", "mean_capped_diff_A_minus_B", "ci_lo", "ci_hi", "reading"]) \
        .to_csv(res / "table_paired_differences.csv", index=False)

    # ---- flicker summary
    fp = res / "flicker.csv"
    if fp.exists():
        pd.read_csv(fp).groupby(["method", "harm"])[["reversals", "time_paused"]].mean().reset_index() \
            .to_csv(res / "table_flicker.csv", index=False)

    _plots(res, det, methods)
    (res / "report.md").write_text(_markdown(res), encoding="utf-8")


def _plots(res: Path, det: pd.DataFrame, methods) -> None:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = [f"P_detect_{h}m" for h in DETECT_HORIZONS]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for _, r in det.iterrows():


        lbl = f"{r['method']} [ORACLE]" if is_oracle_method(str(r["method"])) else str(r["method"])
        ls = "--" if is_oracle_method(str(r["method"])) else "-"
        ax.plot(DETECT_HORIZONS, [r[c] for c in cols], marker="o", linestyle=ls, label=lbl)
    ax.set_xlabel("minutes from event onset"); ax.set_ylabel("P(successful detection)")
    ax.set_title("Detection curves at calibrated false-alert budget")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7)
    ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(res / "fig_detection_curves.png", dpi=150); plt.close(fig)
    cb = pd.read_csv(res / "calibration_bins.csv")
    fig, ax = plt.subplots(figsize=(5, 5)); ax.plot([0, 1], [0, 1], "k--", lw=1)
    for m, d in cb.groupby("method"):
        d = d[d["n"] > 0]
        if not d.empty:
            ax.plot(d["sum_p"] / d["n"], d["sum_j"] / d["n"], marker="o", label=m)
    ax.set_xlabel("mean predicted Pr(a > kappa)"); ax.set_ylabel("observed frequency of J")
    ax.set_title("Host-level probability calibration")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7)
    ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(res / "fig_calibration.png", dpi=150); plt.close(fig)


def _markdown(res: Path) -> str:
    g = json.loads((res / "gate_status.json").read_text(encoding="utf-8"))
    man_path = res / "experiment_manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    regime = g.get("regime") or man.get("regime") or "unknown"
    is_frozen = bool(man.get("model_frozen") or man.get("model_kind") == "frozen")
    banner = ["> **FROZEN AUDIT MODEL, NOT FOR PERFORMANCE CLAIMS**\n"] if is_frozen else []
    min_n_lbl = g.get("min_n_required", MIN_N_GATE)
    out = [
        "# Results (generated from CSVs; interpret per handbook Section 15)\n",
        *banner,
        f"**Regime:** `{regime}`  \n",
        "Simulation results under stated assumptions only. Losing methods stay in the tables.\n",
        f"**Calibration gate: {g['status']}** ({g['cells_ok']}/{g['cells']} method x family cells ok; "
        f"{g['evaluable_cells']} have n>={min_n_lbl}). "
        "Delay/power comparisons are valid only for methods inside this gate.\n",
    ]
    for t in ["table_null_rates", "table_null_by_family", "table_abstention", "table_detection", "table_paired_differences", "table_localization", "table_brier",
              "table_flicker", "table_transient"]:
        p = res / f"{t}.csv"
        if p.exists() and p.stat().st_size > 2:
            df_t = pd.read_csv(p)
            body = "_empty_" if df_t.empty else (df_t.round(4).to_markdown(index=False) if _has_tab() else df_t.round(4).to_string(index=False))
            out += [f"\n## {t}\n", body]
    return "\n".join(out)


def _has_tab() -> bool:
    try:
        import tabulate  # noqa
        return True
    except ImportError:
        return False
