"""Phase P1b tests: WP-E1 additional baselines, WP-E2 oracles, and WP-E3 grid parity."""
from __future__ import annotations

import ast
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.special import gammaln
from scipy.stats import mannwhitneyu

from canary_ssm import experiments as E
from canary_ssm import oracles as OR
from canary_ssm import report as R
from canary_ssm.baselines import config_grid, run_baseline
from canary_ssm.baselines_extra import (
    EXTRA_BASELINES,
    ar_cusum,
    bocpd,
    glr_window,
    msprt,
    mw_judge,
    sparse_mix_glr,
    wmean,
)
from canary_ssm.factor import Adjusted, adjust
from canary_ssm.preprocess import Nuisance
from canary_ssm.simulate import SimConfig, simulate

ROOT = Path(__file__).resolve().parents[1]


def _make_synthetic_adj(
    r_mat: np.ndarray,
    t0: int = 2,
    ctl_r: np.ndarray | None = None,
    class_id: np.ndarray | None = None,
    ctl_class_id: np.ndarray | None = None,
) -> Adjusted:
    T, nc = r_mat.shape
    obs = np.isfinite(r_mat)
    elig = np.ones(T, dtype=bool)
    cls = np.zeros(nc, dtype=int) if class_id is None else class_id
    if ctl_r is None:
        ctl_r = np.zeros((T, 4), dtype=float)
    if ctl_class_id is None:
        ctl_class_id = np.zeros(ctl_r.shape[1], dtype=int)
    return Adjusted(
        r=r_mat.astype(float),
        obs=obs,
        elig=elig,
        U=np.zeros(T, dtype=float),
        lam=np.ones(nc, dtype=float),
        sigma=np.ones(nc, dtype=float),
        rm=r_mat.astype(float),
        class_id=cls,
        t0=t0,
        fallback=np.zeros(nc, dtype=bool),
        f_hat=np.zeros(T, dtype=float),
        ctl_r=ctl_r,
        ctl_class_id=ctl_class_id,
    )


def test_baselines_extra_never_touches_truth():
    tree = ast.parse((ROOT / "canary_ssm" / "baselines_extra.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "simulate" not in node.module and "metrics" not in node.module
            assert "oracles" not in node.module
        if isinstance(node, ast.Name):
            assert node.id != "Truth"


def test_hand_computed_msprt():
    r = np.array([[0.0], [0.0], [1.0], [2.0], [3.0]])
    adj = _make_synthetic_adj(r, t0=2)
    out = msprt(adj, tau=1.0, phi=0.0)
    assert np.all(np.isnan(out.score[:2]))
    expected = []
    best = 0.0
    for m, s in [(1, 1.0), (2, 3.0), (3, 6.0)]:
        log_lam = 0.5 * math.log(1.0 / (1.0 + m)) + (s * s) / (2.0 * (1.0 + m))
        best = max(best, log_lam)
        expected.append(best)
    assert np.allclose(out.score[2:], expected, atol=1e-12)


def test_hand_computed_sparse_mix_glr():
    r = np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
    adj = _make_synthetic_adj(r, t0=2)
    p0 = 0.3
    out = sparse_mix_glr(adj, p0=p0, W=2, phi=0.0)
    assert np.all(np.isnan(out.score[:2]))

    def mix_val(u0: float, u1: float) -> float:
        a = math.log((1 - p0) + p0 * math.exp(0.5 * max(0.0, u0) ** 2))
        b = math.log((1 - p0) + p0 * math.exp(0.5 * max(0.0, u1) ** 2))
        return a + b

    exp_t2 = mix_val(1.0, 0.0)
    exp_t3 = max(mix_val(2.0, 0.0), mix_val(3.0 / math.sqrt(2.0), 0.0))
    exp_t4 = max(mix_val(3.0, 0.0), mix_val(5.0 / math.sqrt(2.0), 0.0))
    assert np.allclose(out.score[2:], [exp_t2, exp_t3, exp_t4], atol=1e-12)


def test_hand_computed_ar_cusum_with_gap():
    phi = 0.6
    r = np.array([[0.0], [1.0], [2.0], [np.nan], [3.0]])
    adj = _make_synthetic_adj(r, t0=2)
    out = ar_cusum(adj, k=0.25, phi=phi)
    assert np.all(np.isnan(out.score[:2]))
    k_pw = 0.25 * math.sqrt((1.0 - phi) / (1.0 + phi))
    e2 = (2.0 - phi * 1.0) / math.sqrt(1.0 - phi ** 2)
    c2 = max(0.0, e2 - k_pw)
    # Missing minute at t=3 leaves state unchanged
    c3 = c2
    phi2 = phi ** 2
    e4 = (3.0 - phi2 * 2.0) / math.sqrt(1.0 - phi2 ** 2)
    c4 = max(0.0, c3 + e4 - k_pw)
    assert np.allclose(out.score[2:], [c2, c3, c4], atol=1e-12)


def test_hand_computed_wmean_and_glr_window():
    r = np.array([[0.0], [0.0], [2.0], [4.0], [-1.0]])
    adj = _make_synthetic_adj(r, t0=2)
    ow = wmean(adj, w=2, K=1)
    assert np.allclose(ow.score[2:], [2.0, 6.0 / math.sqrt(2.0), 3.0 / math.sqrt(2.0)], atol=1e-12)
    og = glr_window(adj, W=2, K=1, phi=0.0)
    assert np.allclose(og.score[2:], [0.5 * 4.0, 0.5 * max(4.0, 6.0 / math.sqrt(2.0)) ** 2, 0.5 * (3.0 / math.sqrt(2.0)) ** 2], atol=1e-12)


def test_hand_computed_bocpd_two_post_steps():
    # t0 = 0 (pure two-step sequential sequence): x = [1.5, 2.0], hazard = 1/60
    r = np.array([[1.5], [2.0]])
    adj = _make_synthetic_adj(r, t0=0)
    lam_h = 60.0
    H = 1.0 / lam_h
    out = bocpd(adj, lambda_h=lam_h, phi=0.0)
    # Step t=0: single active run length r=0, posterior P(r0=0)=1, mu0=0 -> score[0]=0
    assert abs(out.score[0] - 0.0) < 1e-12

    # Step t=1: manual Adams-MacKay Eq. (2)-(3) predictive probabilities & updated means
    def t_pdf(x, mu, kap, alp, bet):
        nu = 2.0 * alp
        s2 = bet * (kap + 1.0) / (alp * kap)
        lp = gammaln(0.5 * (nu + 1.0)) - gammaln(0.5 * nu) - 0.5 * math.log(nu * math.pi * s2)
        lp -= 0.5 * (nu + 1.0) * math.log1p(((x - mu) ** 2) / (nu * s2))
        return math.exp(lp)

    # After t=0 observed x0=1.5: r_0=0 prob=H, r_0=1 prob=(1-H)
    p0_a, p1_a = H, 1.0 - H
    kap1_a = 2.0
    mu1_a = (0.0 + 1.5) / 2.0
    alp1_a = 1.5
    bet1_a = 1.0 + (1.0 * (1.5 - 0.0) ** 2) / 4.0

    # At t=1 observe x1=2.0:
    pi0 = t_pdf(2.0, 0.0, 1.0, 1.0, 1.0)
    pi1 = t_pdf(2.0, mu1_a, kap1_a, alp1_a, bet1_a)
    w0 = p0_a * pi0
    w1 = p1_a * pi1
    g1 = w0 * (1.0 - H)
    g2 = w1 * (1.0 - H)
    cp = (w0 + w1) * H
    Z = cp + g1 + g2
    # At t=1, m_post=2 so r < 2 picks r in {0, 1}. mu[0]=0 (excluded), mu[1]=(0+2)/2=1.0 > 0 (included).
    expected_p1 = g1 / Z
    assert np.isclose(out.score[1], expected_p1, atol=1e-12)


def test_mw_judge_matches_scipy_asymptotic():
    rng = np.random.default_rng(123)
    can = rng.normal(0.5, 1.0, size=(30, 3))
    ctl = rng.normal(0.0, 1.0, size=(30, 10))
    # Inject exact ties too
    can[20, 0] = ctl[20, 0]
    adj = _make_synthetic_adj(can, t0=20, ctl_r=ctl, class_id=np.zeros(3, int), ctl_class_id=np.zeros(10, int))
    out = mw_judge(adj, w=15)
    assert np.all(np.isnan(out.score[:20]))
    for t in (20, 25, 29):
        x = can[t - 15 + 1 : t + 1].ravel()
        y = ctl[t - 15 + 1 : t + 1].ravel()
        res = mannwhitneyu(x, y, alternative="greater", method="asymptotic", use_continuity=False)
        # Reconstruct exact SciPy asymptotic z via norm.isf(pvalue)
        from scipy.stats import norm
        z_scipy = float(norm.isf(res.pvalue))
        assert abs(out.score[t] - z_scipy) < 1e-10


def test_extra_baselines_causality_horizon_and_missingness():
    r1, _ = simulate(SimConfig(t_pre=90, t_post=60), 42, False)
    nu = Nuisance(0.0, [1.0, 1.0], [0.6, 0.6], [0.01, 0.01], [1e-4, 1e-4])
    a1 = adjust(r1, nu.x_center, np.array(nu.class_lambda))

    t_cut = r1.t0 + 25
    r2, _ = simulate(SimConfig(t_pre=90, t_post=60), 42, False)
    r2.y[t_cut + 1 :] += 0.25
    a2 = adjust(r2, nu.x_center, np.array(nu.class_lambda))

    # Missing minute at t_miss leaves sequential accumulators unchanged and avoids zero-imputation
    r_miss, _ = simulate(SimConfig(t_pre=90, t_post=60), 42, False)
    t_miss = r1.t0 + 5
    r_miss.decision_obs[t_miss, :] = False
    a_miss = adjust(r_miss, nu.x_center, np.array(nu.class_lambda))

    for name in EXTRA_BASELINES:
        o1 = run_baseline(name, a1)
        o2 = run_baseline(name, a2)
        assert np.all(np.isnan(o1.score[: r1.t0])), name
        assert np.all(np.isfinite(o1.score[r1.t0 :])), name
        # Causality
        assert np.allclose(o1.score[: t_cut + 1], o2.score[: t_cut + 1], equal_nan=True), name
        # Null horizon monotonicity
        m30 = float(np.max(o1.score[r1.t0 : r1.t0 + 30]))
        m60 = float(np.max(o1.score[r1.t0 : r1.t0 + 60]))
        assert m60 >= m30 - 1e-12, name
        # Missing minute state invariance inside post window
        om = run_baseline(name, a_miss)
        if name in ("ar_cusum", "bocpd", "msprt"):
            assert np.allclose(om.host_score[t_miss], om.host_score[t_miss - 1], equal_nan=True), name
        elif name != "mw_judge":
            # Windowed charts stay constant when t_miss < t0 + min_window
            assert np.allclose(om.score[t_miss], om.score[t_miss - 1], equal_nan=True), name


def test_bocpd_and_mw_judge_runtime_and_grid_parity():
    g = E.load_grids(ROOT / "configs" / "grids_v2.yaml")
    for m in EXTRA_BASELINES:
        cands = E.candidate_grid(m, g)
        assert 1 <= len(cands) <= 24, f"{m} has {len(cands)} candidates"
    assert set(EXTRA_BASELINES) <= {name for name, _ in config_grid()}

    r, _ = simulate(SimConfig(t_pre=180, t_post=120), 77, False)
    nu = Nuisance(0.0, [1.0, 1.0], [0.6, 0.6], [0.01, 0.01], [1e-4, 1e-4])
    adj = adjust(r, nu.x_center, np.array(nu.class_lambda))
    t0 = time.perf_counter()
    bocpd(adj, lambda_h=120.0, phi=0.6)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 250.0, f"bocpd took {elapsed_ms:.1f} ms on T=300 rollout"


def test_oracles_and_report_oracle_tag(tmp_path):
    rh, th = simulate(SimConfig(t_pre=90, t_post=60), 55, True)
    rn, tn = simulate(SimConfig(t_pre=90, t_post=60), 55, False)
    nu = Nuisance(0.0, [1.0, 1.0], [0.6, 0.6], [0.01, 0.01], [1e-4, 1e-4])
    ah = adjust(rh, nu.x_center, np.array(nu.class_lambda))
    an = adjust(rn, nu.x_center, np.array(nu.class_lambda))

    for om in OR.ORACLE_METHODS:
        assert OR.is_oracle_method(om)
        oh = OR.run_oracle(om, ah, th, nuis=nu)
        on = OR.run_oracle(om, an, tn, nuis=nu)
        assert oh.params.get("is_oracle") is True
        assert oh.params.get("label") == "ORACLE"
        assert np.all(np.isnan(oh.score[: rh.t0]))
        assert np.all(np.isfinite(oh.score[rh.t0 :]))
        assert np.all(np.isfinite(on.score[rn.t0 :]))
        assert np.max(oh.score[rh.t0 :]) >= np.max(on.score[rn.t0 :]) - 1.0

    # Report excludes oracles from best_base and adds ORACLE role + efficiency ratios
    rows = []
    for rid, harm, kind, m, cap, st in [
        ("r1_n", False, "no_event", "wmean", np.nan, "quiet"),
        ("r1_n", False, "no_event", "oracle_cusum", np.nan, "quiet"),
        ("r1_h", True, "event", "wmean", 18.0, "success"),
        ("r1_h", True, "event", "hier_ssm", 10.0, "success"),
        ("r1_h", True, "event", "oracle_cusum", 5.0, "success"),
    ]:
        rows.append({
            "rollout_id": rid, "pair_id": 0, "family": "baseline", "regime": "plain", "harm": harm,
            "method": m, "kind": kind, "status": st, "alarm_time": 100 if st == "success" else np.nan,
            "onset": 90 if harm else np.nan, "delay": cap if harm else np.nan, "capped": cap,
            "followup": 60.0 if harm else np.nan, "brier": 0.1, "elig_frac": 1.0,
        })
    pd.DataFrame(rows).to_csv(tmp_path / "per_rollout_metrics.csv", index=False)
    pd.DataFrame([{"method": "hier_ssm", "bin": 0, "n": 1, "sum_p": 0.1, "sum_j": 0.0}]).to_csv(
        tmp_path / "calibration_bins.csv", index=False
    )
    R.make_report(tmp_path)
    det = pd.read_csv(tmp_path / "table_detection.csv").set_index("method")
    assert det.loc["oracle_cusum", "role"] == "ORACLE"
    assert det.loc["wmean", "role"] == "method"
    assert np.isclose(det.loc["hier_ssm", "eff_ratio_oracle_cusum"], (10.0 - 5.0) / (60.0 - 5.0))
    pd_tbl = pd.read_csv(tmp_path / "table_paired_differences.csv")
    assert "oracle_cusum" not in set(pd_tbl["B"])
