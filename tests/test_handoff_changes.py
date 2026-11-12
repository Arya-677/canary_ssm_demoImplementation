"""Tests added after the Experiment 1-6 handoffs."""
import numpy as np
import yaml

from canary_ssm import experiments as E
from canary_ssm.hierarchy import EffectDetector, EffectParams, long_run_sd
from canary_ssm.preprocess import fit_nuisance, adjust_roll
from canary_ssm.schema import KAPPA
from canary_ssm.simulate import SimConfig, simulate


def test_effect_grid_respects_long_run_sd_constraint():
    g = E.ssm_grid("hier")
    assert all(long_run_sd(p) <= KAPPA for p in g) and 0 < len(g) <= 24
    assert not any(p.rho_g == 0.99 and p.sd_g >= 0.005 for p in g)           # the 99.7%-crossing configuration
    assert len(E.ssm_grid("hier", constrain=False)) == 24


def test_workload_step_is_sustained_and_shifts_all_hosts():
    c = SimConfig(workload_step=float(np.log(1.4)), shock=0.0, sd_f=0.0, sd_host=0.0, host_mu_sd=0.0, beta_jitter=0.0,
                  workload_sd=0.0, lam_class_sd=0.0, lam_host_sd=0.0)
    r, _ = simulate(c, 1, False)
    assert np.allclose(np.nanmean(r.y[r.t0 + 20:], 0) - np.nanmean(r.y[:r.t0], 0), 0.15 * np.log(1.4), atol=0.003)


def test_class_wide_and_label_error_scenarios():
    r, t = simulate(SimConfig(affected_mode="class0", label_error=0.3), 4, True)
    true_cls = np.concatenate([np.arange(10) % 2])
    assert t.affected_hosts == [i for i in range(10) if true_cls[i] == 0]     # all of true class 0
    assert (r.class_id[:10] != true_cls).sum() == 3                           # detector sees 30% wrong labels


def test_pooled_beta_mode_reduces_step_residual_spread():
    """Handoff diagnostic: SD/RMS of per-rollout post-pre residual shift (not the signed mean)."""
    step = SimConfig(workload_step=float(np.log(1.4)), beta_jitter=0.0)
    healthy = [simulate(SimConfig(beta_jitter=0.0), s, False)[0] for s in range(25)]
    rms = {}
    for mode in ("pre", "pooled_dev"):
        nu = fit_nuisance(healthy, beta_mode=mode)
        sh = []
        for s in range(100, 140):
            r, _ = simulate(step, s, False); a = adjust_roll(r, nu)
            sh.append(np.nanmean(a.r[r.t0 + 10:]) - np.nanmean(a.r[:r.t0]))
        rms[mode] = float(np.sqrt(np.mean(np.square(sh))))
    assert 0.12 < fit_nuisance(healthy, beta_mode="pooled_dev").beta_pooled < 0.18
    assert rms["pooled_dev"] < rms["pre"]


def test_huber_limits_outlier_influence(nuis):
    r, _ = simulate(SimConfig(), 21, False)
    r.y[r.t0 + 30, :3] += 0.5                                                  # 3 hosts spike at one minute
    a = adjust_roll(r, nuis)
    plain = EffectDetector(nuis, EffectParams()).run(a).score
    hub = EffectDetector(nuis, EffectParams(huber_c=3.0)).run(a).score
    assert np.nanmax(hub) < np.nanmax(plain)


def test_combined_detector_has_one_budget():
    """Union of two detectors calibrated jointly keeps the null rate near alpha; naive OR of separate thresholds does not."""
    from canary_ssm.baselines import DetectorOutput
    from canary_ssm import decision as D
    rng = np.random.default_rng(0); T, t0 = 60, 20; el = np.ones(T, bool)
    def mk(): return [DetectorOutput(n, np.r_[np.full(t0, np.nan), rng.normal(size=T - t0)], el, None) for n in "ab"]
    cal = [mk() for _ in range(500)]; val = [mk() for _ in range(2000)]
    ec = [np.sort([D.release_max(c[i].score, el, t0) for c in cal]) for i in range(2)]
    comb = lambda c: E.combine_outputs("u", c, ec)
    thr = D.calibrate_threshold([D.release_max(comb(c).score, el, t0) for c in cal], 0.05)["threshold"]
    rate = np.mean([D.first_alarm(comb(c).score, el, thr, t0) is not None for c in val])
    thrs = [D.calibrate_threshold(e, 0.05)["threshold"] for e in ec]
    naive = np.mean([any(D.first_alarm(c[i].score, el, thrs[i], t0) is not None for i in range(2)) for c in val])
    assert abs(rate - 0.05) < 0.02 and naive > rate + 0.02


def test_cross_expansion(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"roles": {}, "cross": {"sd_host": [0.01, 0.02, 0.04]},
                                 "families": [{"name": "a", "weight": 1.0, "overrides": {"n_affected": 3}}]}))
    cfg = E.load_config(p)
    assert len(cfg["families"]) == 3 and abs(sum(f["weight"] for f in cfg["families"]) - 1) < 1e-9
    assert {f["overrides"]["sd_host"] for f in cfg["families"]} == {0.01, 0.02, 0.04}


def test_frozen_fit_calibrate_audit_chain(tmp_path):
    cfg = {"sim": {}, "roles": {"dev": {"pairs": 6}, "calibration": {"pairs": 25}},
           "families": [{"name": "s1", "overrides": {"n_affected": 3}}]}
    for role in ("dev", "calibration"):
        E.generate_role(cfg, role, tmp_path / role)
    ms = ["matched_contrast", "topk_cusum", "hier_ssm"]
    E.fit(tmp_path / "dev", tmp_path / "model", ms, log=lambda *a: None, frozen=True)
    pol = E.calibrate(tmp_path / "calibration", tmp_path / "model", tmp_path / "policy", log=lambda *a: None)
    assert "combo_hier_topk" in pol["combos"] and "combo_hier_topk" in pol["thresholds"]
    acfg = tmp_path / "audit.yaml"
    acfg.write_text(yaml.safe_dump({"sim": {}, "families": [{"name": "plain", "overrides": {}}, {"name": "step", "overrides": {"workload_step": 0.3365}}]}))
    df = E.audit_null(acfg, tmp_path / "model", tmp_path / "policy", n=4, out_dir=tmp_path / "audit", log=lambda *a: None)
    assert set(df["family"]) == {"plain", "step"} and {"pass_contains_5pct", "pass_upper_le_8pct"} <= set(df.columns)


def test_report_pass_labels_follow_numbers_not_prose():
    import pandas as pd
    from canary_ssm.report import null_rate_table, calibration_gate
    # 42/500 = 8.4% [6.1, 11.2]: handoff Experiment 5 labelled this PASS; the numbers say FAIL
    nl = pd.DataFrame({"method": "m5", "family": "matched", "alerted": [True] * 42 + [False] * 458})
    t = null_rate_table(nl, ["family", "method"])
    assert not t.loc[0, "pass_contains_5pct"] and not t.loc[0, "pass_upper_le_8pct"]
    assert calibration_gate(t)["status"] == "FAIL"
    small = pd.DataFrame({"method": "m", "family": "f", "alerted": [True] * 4 + [False] * 56})   # n=60: not evaluable, not above
    assert calibration_gate(null_rate_table(small, ["family", "method"]))["status"] == "NOT_EVALUABLE"   # never PASS without data
    ok = pd.DataFrame({"method": "m", "family": "f", "alerted": [True] * 25 + [False] * 475})
    assert calibration_gate(null_rate_table(ok, ["family", "method"]))["status"] == "PASS"


def test_null_rows_survive_csv_roundtrip_and_reach_the_null_table(tmp_path):
    """Regression: kind='null' was parsed by pandas as NaN, silently emptying every null-rate table."""
    import pandas as pd
    from canary_ssm import metrics as M
    from canary_ssm.report import null_rate_table
    c = M.classify(None, {"has_event": False, "transient": False}, 100)
    assert c["kind"] != "null"
    pd.DataFrame([{"kind": c["kind"], "family": "f", "method": "m", "alarm_time": None}] * 5).to_csv(tmp_path / "x.csv", index=False)
    df = pd.read_csv(tmp_path / "x.csv")
    nl = df[df["kind"] == "no_event"].assign(alerted=lambda d: d["alarm_time"].notna())
    assert len(nl) == 5 and null_rate_table(nl, ["family", "method"]).loc[0, "n_null"] == 5
