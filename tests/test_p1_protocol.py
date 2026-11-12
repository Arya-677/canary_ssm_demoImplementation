"""Tests for Phase P1 protocol repair (WP-A1, A2, A5, A6, B1-B6, C1-C4)."""
from __future__ import annotations

import json
import sys
import tokenize
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from scipy.stats import kstest

from canary_ssm import decision as dec
from canary_ssm import experiments as E
from canary_ssm import metrics as M
from canary_ssm import report as R
from canary_ssm import seeds
from canary_ssm.baselines import matched_contrast, run_baseline
from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectParams, long_run_sd
from canary_ssm.preprocess import fit_nuisance
from canary_ssm.schema import KAPPA
from canary_ssm.simulate import SimConfig, simulate


ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ WP-A1
def test_plain_main_has_no_step_overrides():
    cfg = yaml.safe_load((ROOT / "configs" / "plain_main.yaml").read_text(encoding="utf-8"))
    assert cfg["regime"] == "plain"
    assert abs(sum(f["weight"] for f in cfg["families"]) - 1.0) < 1e-9
    for fam in cfg["families"]:
        assert float(fam.get("overrides", {}).get("workload_step", 0.0)) == 0.0


def test_regime_recorded_in_manifest_and_mismatch_refused(tmp_path):
    cfg_plain = {
        "regime": "plain",
        "sim": {"sd_host": 0.02, "t_pre": 90, "t_post": 40},
        "roles": {
            "dev": {"pairs": 35},
            "calibration": {"pairs": 25},
            "null_validation": {"per_family": 5},
            "test": {"pairs": 4},
        },
        "families": [{"name": "S1_sparse", "weight": 1.0, "overrides": {"n_affected": 3}}],
    }
    cfg_step = {
        **cfg_plain,
        "regime": "step",
        "families": [{"name": "S1_sparse", "weight": 1.0, "overrides": {"n_affected": 3, "workload_step": 0.3365}}],
    }
    E.generate_role(cfg_plain, "dev", tmp_path / "plain_dev")
    E.generate_role(cfg_plain, "calibration", tmp_path / "plain_cal")
    E.generate_role(cfg_step, "null_validation", tmp_path / "step_val")
    E.generate_role(cfg_step, "test", tmp_path / "step_test")

    assert json.loads((tmp_path / "plain_cal" / "manifest.json").read_text())["regime"] == "plain"
    assert json.loads((tmp_path / "step_test" / "manifest.json").read_text())["regime"] == "step"

    E.fit(tmp_path / "plain_dev", tmp_path / "model", ["matched_contrast", "adj_cusum"],
          allow_small_dev=True, log=lambda *a: None)
    pol = E.calibrate(tmp_path / "plain_cal", tmp_path / "model", tmp_path / "pol", log=lambda *a: None)
    assert pol["regime"] == "plain"
    assert pol["schema_version"] == 2
    assert "plain" in pol["regimes"]

    with pytest.raises(ValueError, match="regime"):
        E.validate_null(tmp_path / "step_val", tmp_path / "model", tmp_path / "pol", log=lambda *a: None)
    with pytest.raises(ValueError, match="regime"):
        E.evaluate(tmp_path / "step_test", tmp_path / "model", tmp_path / "pol", tmp_path / "out", log=lambda *a: None)

    out = E.evaluate(
        tmp_path / "step_test", tmp_path / "model", tmp_path / "pol", tmp_path / "out",
        allow_regime_mismatch=True, log=lambda *a: None,
    )
    man = json.loads((out / "experiment_manifest.json").read_text())
    assert man["allow_regime_mismatch"] is True


# ------------------------------------------------------------------ WP-A2 & WP-C3
def test_per_family_counts_exact(tmp_path):
    cfg = {
        "regime": "plain",
        "sim": {"sd_host": 0.02, "t_pre": 60, "t_post": 30},
        "roles": {"null_validation": {"per_family": 7}},
        "families": [
            {"name": "f0", "weight": 0.5, "overrides": {"n_affected": 3}},
            {"name": "f1", "weight": 0.3, "overrides": {"affected_mode": "class0"}},
            {"name": "f2", "weight": 0.2, "overrides": {"n_affected": 1}},
        ],
    }
    man = E.generate_role(cfg, "null_validation", tmp_path / "val")
    assert man["per_family"] == 7
    assert man["n_rollouts"] == 21
    assert man["family_counts"] == {"f0": 7, "f1": 7, "f2": 7}
    rolls = E.load_role(tmp_path / "val", truth=False)
    counts = pd.Series([r.meta["family"] for r, _ in rolls]).value_counts().to_dict()
    assert counts == {"f0": 7, "f1": 7, "f2": 7}


def test_betabinom_mean_sd_hand_values():
    res = M.betabinom_validity(45, 500, 500, 476)
    assert abs(res["expected_alerts"] - 500 * 25 / 501) < 1e-9
    assert abs(res["bb_sd"] - 6.8752095115) < 1e-6
    assert abs(res["p_upper"] - 0.006046845) < 1e-6
    assert res["bb_pvalue_two_sided"] < 0.02


def test_validity_p_uniform_under_exchangeability():
    rng = np.random.default_rng(123)
    B, n, alpha = 200, 200, 0.05
    k_ord = int(np.ceil((B + 1) * (1 - alpha)))
    pvals = []
    # Sample Beta(B+1-k, k) exceedance probabilities directly for fast exact Monte Carlo
    ps = rng.beta(B + 1 - k_ord, k_ord, size=2000)
    ks = rng.binomial(n, ps)
    for k in ks:
        pvals.append(M.betabinom_validity(int(k), n, B, k_ord)["bb_pvalue_two_sided"])
    # For discrete distributions two-sided exact p-values are stochastically >= Uniform(0,1),
    # check tail calibration P(p <= 0.05) <= 0.06 and P(p <= 0.01) <= 0.02 and mean in [0.45, 0.65]
    pv = np.array(pvals)
    assert np.mean(pv <= 0.05) <= 0.065
    assert np.mean(pv <= 0.01) <= 0.02
    assert 0.45 <= float(np.mean(pv)) <= 0.65


def test_validity_detects_shift():
    rng = np.random.default_rng(7)
    B, n = 500, 500
    k_ord = int(np.ceil((B + 1) * 0.95))
    cal = np.max(rng.normal(size=(B, 50)), axis=1)
    thr = np.sort(cal)[k_ord - 1]
    val_shifted = np.max(rng.normal(size=(n, 50)), axis=1) + 0.3
    k_alerts = int(np.sum(val_shifted > thr))
    res = M.betabinom_validity(k_alerts, n, B, k_ord)
    assert res["bb_pvalue_two_sided"] < 0.01


def test_gate_g2_modes_and_requirements():
    small_rows = [
        {"family": f"f{i}", "method": "m", "alerts": 2, "n_null": 50, "rate": 0.04,
         "ci_lo": 0.005, "ci_hi": 0.137, "bb_pvalue_two_sided": 0.8, "above_target": False,
         "pass_contains_5pct": True, "pass_upper_le_8pct": False, "gate_evaluable": False}
        for i in range(3)
    ]
    g_small = R.calibration_gate(pd.DataFrame(small_rows), gate_mode="g2", min_n=400)
    assert g_small["status"] == "NOT_EVALUABLE"

    # Zero evaluable cells must NEVER yield PASS even if nothing failed
    assert g_small["status"] != "PASS"

    ok_rows = [
        {"family": f"f{i}", "method": "m", "alerts": 100, "n_null": 2000, "rate": 0.05,
         "ci_lo": 0.041, "ci_hi": 0.060, "bb_pvalue_two_sided": 0.95, "above_target": False,
         "pass_contains_5pct": True, "pass_upper_le_8pct": True, "gate_evaluable": True}
        for i in range(3)
    ]
    g_pass = R.calibration_gate(pd.DataFrame(ok_rows), gate_mode="g2", min_n=2000)
    assert g_pass["status"] == "PASS" and g_pass["evaluable_cells"] == 3

    bad_rows = ok_rows + [{
        "family": "f3", "method": "m", "alerts": 200, "n_null": 2000, "rate": 0.10,
        "ci_lo": 0.087, "ci_hi": 0.114, "bb_pvalue_two_sided": 1e-6, "above_target": True,
        "pass_contains_5pct": False, "pass_upper_le_8pct": False, "gate_evaluable": True,
    }]
    g_fail = R.calibration_gate(pd.DataFrame(bad_rows), gate_mode="g2", min_n=2000)
    assert g_fail["status"] == "FAIL"


# ------------------------------------------------------------------ WP-A5 & WP-A6
def test_no_decision_obs_all_in_studies():
    studies_dir = ROOT / "canary_ssm" / "studies"
    for p in sorted(studies_dir.glob("*.py")):
        with p.open("rb") as f:
            toks = [t.string for t in tokenize.tokenize(f.readline) if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE)]
        joined = "".join(toks)
        assert "decision_obs.all" not in joined, f"{p.name} uses decision_obs.all instead of DetectorOutput.elig"


def test_study_refuses_frozen_model():
    from canary_ssm.studies import require_tuned
    with pytest.raises(ValueError):
        require_tuned({"kind": "frozen", "frozen": True}, allow_frozen=False)
    require_tuned({"kind": "frozen", "frozen": True}, allow_frozen=True)
    require_tuned({"kind": "tuned", "frozen": False}, allow_frozen=False)


def test_study_cli_dispatch(tmp_path):
    from canary_ssm import cli
    with pytest.raises(SystemExit) as ex:
        cli.main(["study", "--help"])
    assert ex.value.code == 0


@pytest.mark.slow
def test_experiment7_legacy_reproduction(tmp_path):
    from canary_ssm.studies import study_regime
    man = study_regime.run(
        model_dir=ROOT / "data_audit" / "model_pooled_dev",
        out_dir=tmp_path / "reg",
        n_null=30,
        n_harm=10,
        allow_frozen=True,
        legacy_seeds=True,
        workers=1,
    )
    assert (tmp_path / "reg" / "table_regime_null_rates.csv").exists()
    assert (tmp_path / "reg" / "table_regime_confusion.csv").exists()
    assert man["legacy_seeds"] is True


# ------------------------------------------------------------------ WP-B1..B6
def test_grid_counts_and_hash_and_constraint(tmp_path):
    g1 = E.load_grids(ROOT / "configs" / "grids_v2.yaml")
    assert len(E.candidate_grid("adj_cusum", g1)) == 6
    assert len(E.candidate_grid("adj_ewma", g1)) == 6
    assert len(E.candidate_grid("topk_cusum", g1)) == 24
    assert len(E.candidate_grid("matched_contrast", g1)) == 5
    assert len(E.candidate_grid("hier_no_persist", g1)) == 15
    assert len(E.candidate_grid("hier_rw", g1)) == 9

    ssm_cands = E.ssm_grid("hier", grids=g1)
    assert all(long_run_sd(p) <= KAPPA for p in ssm_cands)
    assert not any(p.rho_g == 0.999 and p.sd_g == 0.001 for p in ssm_cands)  # lr_sd=0.02237 > KAPPA
    np_cands = E.candidate_grid("hier_no_persist", g1)
    assert any(p["sd_g"] == 0.05 for p in np_cands)

    mod_yaml = (ROOT / "configs" / "grids_v2.yaml").read_text(encoding="utf-8").replace("v2.0", "v2.0-test")
    p2 = tmp_path / "g.yaml"
    p2.write_text(mod_yaml, encoding="utf-8")
    assert E.dict_hash(g1) != E.dict_hash(E.load_grids(p2))


def test_matched_contrast_window_behavior():
    r, _ = simulate(SimConfig(), 5, True)
    adj = adjust(r, 0.0, np.array([0.015, 0.015]), factor_rank=1, beta_pooled=0.15)
    o1 = matched_contrast(adj, window=1)
    o10 = matched_contrast(adj, window=10)
    assert np.all(np.isnan(o10.score[:r.t0]))
    assert np.allclose(o1.score[r.t0:], run_baseline("matched_contrast", adj).score[r.t0:], equal_nan=True)
    assert not np.allclose(o10.score[r.t0 + 10:], o1.score[r.t0 + 10:], equal_nan=True)


def test_edge_detection_on_synthetic_candidate_table():
    selected = {
        "adj_cusum": {"params": {"k": 1.5}},
        "adj_ewma": {"params": {"alpha": 0.1}},
    }
    rows = [
        {"method": "adj_cusum", "cand": i, "params": json.dumps({"k": k}), "dev_capped_time": 20.0 - i}
        for i, k in enumerate([0.1, 0.5, 1.0, 1.5])
    ] + [
        {"method": "adj_ewma", "cand": i, "params": json.dumps({"alpha": a}), "dev_capped_time": 25.0}
        for i, a in enumerate([0.02, 0.1, 0.5])
    ]
    edge_df = E.detect_edge_selections(selected, rows, grid_version="v2.0")
    c_row = edge_df[edge_df["method"] == "adj_cusum"].iloc[0]
    e_row = edge_df[edge_df["method"] == "adj_ewma"].iloc[0]
    assert bool(c_row["at_edge"]) is True
    assert bool(e_row["at_edge"]) is False


def test_kfold_threshold_uses_only_training_nulls(monkeypatch):
    dev = [(r, t) for s in range(25) for h in (False, True) for r, t in [simulate(SimConfig(t_pre=60, t_post=30), s, h, pair_id=s)]]
    nuis = fit_nuisance([r for r, t in dev if not t.harm][:5])
    seen_B = []
    orig_cal = dec.calibrate_threshold

    def spy_cal(maxima, alpha=0.05):
        seen_B.append(len(maxima))
        return orig_cal(maxima, alpha)

    monkeypatch.setattr(dec, "calibrate_threshold", spy_cal)
    E.select_on_dev(
        E.Models({"main": nuis}), dev, "matched_contrast", [{"window": 1}], [],
        log=lambda *a: None, k_folds=5, min_dev_nulls=25,
    )
    assert seen_B == [20, 20, 20, 20, 20]  # 25 nulls across 5 folds -> 20 training nulls per fold


def test_one_se_rule_picks_simpler():
    # Candidate 0: complex (small regularisation k=0.1), slightly better mean 10.0, SE 1.0
    # Candidate 1: simpler (larger regularisation k=1.0), mean 10.5 <= 10.0 + 1.0 -> 1-SE picks Candidate 1
    assert E.pick_one_se_candidate([
        {"cand": 0, "method": "adj_cusum", "params": json.dumps({"k": 0.1}), "dev_capped_time": 10.0, "dev_se": 1.0},
        {"cand": 1, "method": "adj_cusum", "params": json.dumps({"k": 1.0}), "dev_capped_time": 10.5, "dev_se": 1.0},
    ])["cand"] == 1


def test_objective_weighting():
    # Family A (weight 9 items): capped=10.0, Family B (1 item): capped=50.0
    per_roll = [
        {"pair_id": i, "family": "A", "capped": 10.0} for i in range(9)
    ] + [{"pair_id": 9, "family": "B", "capped": 50.0}]
    mix_score = E.aggregate_fold_objective(per_roll, objective="mixture")
    bal_score = E.aggregate_fold_objective(per_roll, objective="family_balanced")
    assert abs(mix_score - 14.0) < 1e-9
    assert abs(bal_score - 30.0) < 1e-9


def test_evaluate_refuses_frozen(tmp_path):
    cfg = {
        "regime": "plain",
        "sim": {"t_pre": 60, "t_post": 30},
        "roles": {"dev": {"pairs": 10}, "calibration": {"pairs": 25}, "test": {"pairs": 4}},
        "families": [{"name": "s1", "overrides": {"n_affected": 3}}],
    }
    for role in ("dev", "calibration", "test"):
        E.generate_role(cfg, role, tmp_path / role)
    E.fit(tmp_path / "dev", tmp_path / "model", ["matched_contrast"], frozen=True, log=lambda *a: None)
    E.calibrate(tmp_path / "calibration", tmp_path / "model", tmp_path / "policy", log=lambda *a: None)
    with pytest.raises(ValueError, match="frozen"):
        E.evaluate(tmp_path / "test", tmp_path / "model", tmp_path / "policy", tmp_path / "out", log=lambda *a: None)
    out = E.evaluate(
        tmp_path / "test", tmp_path / "model", tmp_path / "policy", tmp_path / "out",
        allow_frozen=True, log=lambda *a: None,
    )
    R.make_report(out)
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "FROZEN AUDIT MODEL, NOT FOR PERFORMANCE CLAIMS" in md


def test_strict_edges_cli_exit_code_3(tmp_path):
    import subprocess
    cfg = {
        "regime": "plain",
        "sim": {"t_pre": 60, "t_post": 30},
        "roles": {"dev": {"pairs": 25}},
        "families": [{"name": "s1", "overrides": {"n_affected": 3, "effect_pct": 5.0}}],
    }
    E.generate_role(cfg, "dev", tmp_path / "dev")
    gpath = tmp_path / "edge_grid.yaml"
    gpath.write_text(
        "version: edge-test\n"
        "adj_cusum:\n  k: [0.25, 1.0]\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable, "-m", "canary_ssm.cli", "fit",
            "--data", str(tmp_path / "dev"),
            "--out", str(tmp_path / "model"),
            "--methods", "adj_cusum",
            "--grid", str(gpath),
            "--strict-edges",
            "--allow-small-dev",
        ],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 3
    edge_df = pd.read_csv(tmp_path / "model" / "edge_selection.csv")
    assert bool(edge_df["at_edge"].any()) is True


# ------------------------------------------------------------------ WP-C1..C4
def test_thresholds_for_alpha_and_min_B_hand_values():
    mx = np.arange(1, 501, dtype=float)
    res = dec.thresholds_for_alpha(mx, (0.01, 0.02, 0.05, 0.10))
    assert res["0.05"]["k"] == 476 and res["0.05"]["threshold"] == 476.0
    assert res["0.01"]["k"] == 496 and res["0.01"]["threshold"] == 496.0
    assert res["0.1"]["k"] == 451 and res["0.1"]["threshold"] == 451.0

    small = np.arange(1, 51, dtype=float)
    res_s = dec.thresholds_for_alpha(small, (0.01, 0.05))
    assert res_s["0.01"]["threshold"] == float("inf")
    assert dec.min_B_for_alpha(0.05) == 19
    assert dec.min_B_for_alpha(0.01) == 99


def test_beta_quantiles_match_simulation():
    rng = np.random.default_rng(42)
    B, alpha = 200, 0.05
    k_ord = int(np.ceil((B + 1) * (1 - alpha)))
    # Uniform(0,1) maxima of 1 iid variate -> F(M_(k)) = M_(k), so 1-F(T) = 1 - U_(k) ~ Beta(B+1-k, k)
    u = rng.uniform(size=(20_000, B))
    u_k = np.partition(u, k_ord - 1, axis=1)[:, k_ord - 1]
    emp_far = 1.0 - u_k
    unc = dec.threshold_uncertainty(np.sort(u[0]), alpha=alpha, n_boot=500, seed=0)
    q_emp = np.quantile(emp_far, [0.025, 0.975])
    assert abs(q_emp[0] - unc["far_beta_lo"]) < 0.005
    assert abs(q_emp[1] - unc["far_beta_hi"]) < 0.005


def test_policy_v2_schema_and_horizons(tmp_path):
    cfg = {
        "regime": "plain",
        "sim": {"t_pre": 60, "t_post": 130},
        "roles": {"dev": {"pairs": 30}, "calibration": {"pairs": 100}},
        "families": [{"name": "s1", "overrides": {"n_affected": 3}}],
    }
    E.generate_role(cfg, "dev", tmp_path / "dev")
    E.generate_role(cfg, "calibration", tmp_path / "cal")
    E.fit(tmp_path / "dev", tmp_path / "model", ["matched_contrast"], allow_small_dev=True, log=lambda *a: None)
    pol = E.calibrate(tmp_path / "cal", tmp_path / "model", tmp_path / "pol", horizons=(30, 60, 120), log=lambda *a: None)
    assert pol["schema_version"] == 2
    reg_pol = pol["regimes"]["plain"]
    assert reg_pol["B"] == 100
    assert set(reg_pol["thresholds_by_alpha"]["matched_contrast"]) >= {"0.01", "0.02", "0.05", "0.1"}
    assert set(map(str, reg_pol["horizons"])) >= {"30", "60", "120"}
    assert "matched_contrast" in reg_pol["threshold_uncertainty"]
