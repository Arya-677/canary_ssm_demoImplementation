"""V3 tests: decision-level inertia, two-scale hierarchy, independent numerical verification, simulator invariance.

Independent references (not the code under test): hand-computed fixtures, a direct batch Gaussian-conditioning
solver written here from first principles, and golden hashes of the LEGACY simulator recorded before V3 edits.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from canary_ssm import decision as dec
from canary_ssm import metrics as M
from canary_ssm.factor import Adjusted, adjust
from canary_ssm.hierarchy import (EffectDetector, EffectParams, TwoScaleParams, build_model, class_structure,
                                  prior_scale_vector)
from canary_ssm.inertia import nests_hier_ssm, ts_candidates
from canary_ssm.preprocess import Nuisance
from canary_ssm.schema import KAPPA
from canary_ssm.simulate import SimConfig, simulate

DATA = Path(__file__).parent / "data"


# ------------------------------------------------------------------ decision-level inertia (Mechanism 3)
def test_persist_score_hand_computed_running_min():
    sc = np.array([0, 0, 1, 2, 3, 1, 4, 4, 4, 0.]); el = np.ones(10, bool)
    s, v = dec.persist_score(sc, el, t0=2, m=3)
    # windows start at t0: t=4 -> min(1,2,3)=1 ; t=5 -> min(2,3,1)=1 ; t=8 -> min(4,4,4)=4 ; t=9 -> min(4,4,0)=0
    assert np.isnan(s[:4]).all() and s[4] == 1 and s[5] == 1 and s[6] == 1 and s[7] == 1 and s[8] == 4 and s[9] == 0
    assert (v == np.isfinite(s)).all()


def test_persist_m1_is_the_legacy_score_and_maximum():
    rng = np.random.default_rng(0)
    for _ in range(20):
        sc = rng.normal(size=120); el = rng.random(120) > 0.2
        s, v = dec.persist_score(sc, el, 30, 1)
        assert dec.release_max(s, v, 30) == dec.release_max(sc, el, 30)
        assert dec.first_alarm(s, v, 0.5, 30) == dec.first_alarm(sc, el, 0.5, 30)


def test_ineligible_minute_breaks_the_run():
    sc = np.full(12, 5.0); el = np.ones(12, bool); el[6] = False
    s, v = dec.persist_score(sc, el, 2, 3)
    assert v[4] and not v[6] and not v[7] and not v[8] and v[9]        # runs restart after the gap


def test_emergency_offset_allows_a_single_severe_minute():
    sc = np.zeros(30); sc[15] = 10.0; el = np.ones(30, bool)
    s, v = dec.persist_score(sc, el, 5, 5)
    assert dec.first_alarm(s, v, 3.0, 5) is None                       # m=5 refuses an isolated spike
    s2, v2 = dec.persist_score(sc, el, 5, 5, emergency_offset=2.0)
    assert dec.first_alarm(s2, v2, 3.0, 5) == 15                       # 10 - 2 = 8 > 3 pauses immediately


def test_persistence_calibration_is_exact_on_exchangeable_nulls():
    """Order-statistic calibration of the running-min score must keep the exact Beta-Binomial validity."""
    rng = np.random.default_rng(123)
    def paths(n):
        out = []
        for _ in range(n):
            z = np.zeros(120); e = rng.normal(size=120)
            for t in range(1, 120):
                z[t] = 0.7 * z[t - 1] + e[t]
            out.append(z)
        return out
    cal, val = paths(600), paths(3000); el = np.ones(120, bool)
    for m in (1, 5, 10):
        pol = dec.calibrate_persistence(cal, [el] * len(cal), 20, m, 0.05)
        k = 0
        for z in val:
            s, v = dec.persist_score(z, el, 20, m)
            k += dec.first_alarm(s, v, pol["h_on"], 20) is not None
        bb = M.betabinom_validity(k, len(val), pol["base"]["B"], pol["base"]["k"])
        assert bb["bb_pvalue_two_sided"] > 0.001, (m, k, bb)


def test_replay_policy_with_m1_equals_legacy_advisory_replay():
    rng = np.random.default_rng(1)
    for _ in range(10):
        sc = np.cumsum(rng.normal(size=100)) * 0.3; el = rng.random(100) > 0.1
        a = dec.replay_policy(sc, el, 20, 2.0, 0.5, m_on=1, n_clear=4)
        b = dec.advisory_replay(sc, el, 20, 2.0, 0.5, n_clear=4)
        assert a["reversals"] == b["reversals"] and a["time_paused"] == b["time_paused"] and a["first_pause"] == b["first_pause"]
        assert np.array_equal(a["states"], b["states"])


def test_replay_exit_needs_n_clear_consecutive_and_ineligible_resets():
    sc = np.r_[np.zeros(5), np.full(5, 9.0), [0, 0, 9, 0, 0, 0, 0, 0.]]; el = np.ones(len(sc), bool)
    r = dec.replay_policy(sc, el, 0, 5.0, 1.0, 1, n_clear=3)
    assert r["first_pause"] == 5 and r["pause_episodes"] == 1
    assert r["states"][10] == dec.PAUSE and r["states"][11] == dec.PAUSE      # 2 clear minutes < n_clear
    assert r["states"][12] == dec.PAUSE                                       # a high score resets the clear counter
    assert r["states"][len(sc) - 1] == dec.NORMAL                             # 3 clear minutes in a row
    el2 = el.copy(); el2[15] = False
    r2 = dec.replay_policy(sc, el2, 0, 5.0, 1.0, 1, n_clear=3)
    assert r2["states"][15] == dec.UNKNOWN and r2["states"][len(sc) - 1] == dec.PAUSE   # reset by the gap


# ------------------------------------------------------------------ two-scale hierarchy (Mechanism 2)
def test_hier_ts_with_symmetric_parameters_is_bit_identical_to_hier(nuis, pair):
    (rh, _), _ = pair
    adj = adjust(rh, nuis.x_center, np.array(nuis.class_lambda))
    base = dict(kind="hier", rho_g=0.99, rho_h=0.99, sd_g=0.001, sd_h_ratio=1.0, prior_sd=0.01)
    a = EffectDetector(nuis, EffectParams(**base)).run(adj)
    b = EffectDetector(nuis, TwoScaleParams(**base, prior_h_ratio=1.0)).run(adj)
    assert np.array_equal(a.score, b.score, equal_nan=True) and np.array_equal(a.host_prob, b.host_prob, equal_nan=True)


def test_prior_h_ratio_controls_partial_pooling_strength():
    cls = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p1 = TwoScaleParams(kind="hier", prior_h_ratio=1.0); p2 = TwoScaleParams(kind="hier", prior_h_ratio=0.1)
    L, _, _ = build_model(p1, cls)
    for p, expect_local in ((p1, 1.0), (p2, 0.1)):
        v = prior_scale_vector(p, cls)
        assert np.allclose(v[:2], 1.0) and np.allclose(v[2:], expect_local)
        S = L @ np.diag(v ** 2) @ L.T                                          # prior covariance / prior_sd^2
        m = 4; r2 = expect_local ** 2
        assert np.isclose(S[0, 0], 1 + r2 * (1 - 1 / m)) and np.isclose(S[0, 1], 1 - r2 / m)
        assert np.isclose(S[0, 4], 0.0)                                        # classes independent
    assert np.all(prior_scale_vector(EffectParams(kind="indep"), cls) == 1.0)


def test_grid_budget_parity_and_nesting():
    from canary_ssm.experiments import candidate_grid, load_grids
    cands = ts_candidates()
    assert 0 < len(cands) <= len(candidate_grid("hier_ssm", load_grids()))
    hp = json.loads(Path("artifacts/model_v2/model_config.json").read_text())["selected"]["hier_ssm"]["params"] \
        if Path("artifacts/model_v2/model_config.json").exists() else None
    if hp is not None:
        assert nests_hier_ssm(cands, hp)


# ------------------------------------------------------------------ independent numerical verification (D2)
def _batch_filtering_reference(F, Q, m0, P0, H, Vfun, ys, obs_idx, kappa_loader=None):
    """Direct Gaussian conditioning on the stacked trajectory. For each t, condition z_{t0..t} on y_{t0..t}.
    z_s = F^{s+1} z_{-1} + sum_{j<=s} F^{s-j} w_j  (z_{-1} ~ N(m0,P0), w_j ~ N(0,Q)); written independently of kalman.py."""
    d = F.shape[0]; K = len(ys); out = []
    for t in range(K):
        n_t = t + 1
        S = np.zeros((n_t * d, d + n_t * d))            # maps W=[z_-1, w_0..w_t] -> [z_0..z_t]
        for s in range(n_t):
            S[s * d:(s + 1) * d, :d] = np.linalg.matrix_power(F, s + 1)
            for j in range(s + 1):
                S[s * d:(s + 1) * d, d + j * d:d + (j + 1) * d] = np.linalg.matrix_power(F, s - j)
        SW = np.zeros((d + n_t * d,) * 2); SW[:d, :d] = P0
        for j in range(n_t):
            SW[d + j * d:d + (j + 1) * d, d + j * d:d + (j + 1) * d] = Q
        muW = np.r_[m0, np.zeros(n_t * d)]
        Sz = S @ SW @ S.T; mz = S @ muW
        rows, yv, Rblocks = [], [], []
        for s in range(n_t):
            idx = obs_idx[s]
            if len(idx):
                Hs = np.zeros((len(idx), n_t * d)); Hs[:, s * d:(s + 1) * d] = H[idx]
                rows.append(Hs); yv.append(ys[s][idx]); Rblocks.append(Vfun(s)[np.ix_(idx, idx)])
        if rows:
            O = np.vstack(rows); y = np.concatenate(yv)
            R = np.zeros((len(y), len(y))); o = 0
            for B in Rblocks:
                R[o:o + len(B), o:o + len(B)] = B; o += len(B)
            G = Sz @ O.T @ np.linalg.inv(O @ Sz @ O.T + R)
            mz = mz + G @ (y - O @ mz); Sz = Sz - G @ O @ Sz
        out.append((mz[-d:], Sz[-d:, -d:]))
    return out


def _mk_nuis(G):
    return Nuisance(x_center=0.0, class_lambda=[1.0] * G, phi_e=[0.5, 0.7][:G], q_e=[0.02, 0.03][:G], v=[1e-3, 2e-3][:G])


@pytest.mark.parametrize("cls", [np.array([0, 0, 1, 1]), np.array([0, 0, 0, 1]), np.array([0, 1, 1, 1, 0])])
@pytest.mark.parametrize("params", [
    EffectParams(kind="hier", rho_g=0.97, rho_h=0.97, sd_g=0.004, sd_h_ratio=1.0, prior_sd=0.02),
    TwoScaleParams(kind="hier", rho_g=0.999, rho_h=0.9, sd_g=0.001, sd_h_ratio=3.0, prior_sd=0.01, prior_h_ratio=0.4),
    EffectParams(kind="indep", rho_g=0.95, sd_g=0.003, prior_sd=0.02),
])
def test_effect_detector_matches_direct_gaussian_conditioning(cls, params):
    """Hierarchical (balanced, unbalanced, singleton class), two-scale and independent models; missing data included."""
    rng = np.random.default_rng(5)
    n = len(cls); G = len(np.unique(cls)); t0, K = 4, 7; T = t0 + K
    nu = _mk_nuis(G)
    r = rng.normal(0, 0.03, size=(T, n)); obs = np.ones((T, n), bool)
    obs[t0 + 2, 1] = False; obs[t0 + 4, :] = False; obs[t0 + 5, 0] = False           # partial and total dropout
    obs[:t0] = False                                    # no pre-period data: AR state starts at its stationary law
    r = np.where(obs, r, np.nan); elig = np.ones(T, bool)
    adj = Adjusted(r, obs, elig, np.zeros(T), np.ones(n), np.ones(n), np.full((T, n), np.nan), cls, t0,
                   np.zeros(n, bool), np.zeros(T))
    out = EffectDetector(nu, params).run(adj)

    L, rho, sd = build_model(params, cls); d = L.shape[1]
    phi = np.array([nu.phi_e[g] for g in cls]); qe = np.array([nu.q_e[g] for g in cls]); vv = np.array([nu.v[g] for g in cls])
    pv = prior_scale_vector(params, cls) * params.prior_sd
    F = np.zeros((d + n, d + n)); F[:d, :d] = np.diag(rho); F[d:, d:] = np.diag(phi)
    Q = np.zeros_like(F); Q[:d, :d] = np.diag(sd ** 2); Q[d:, d:] = np.diag(qe ** 2)
    P0 = np.zeros_like(F); P0[:d, :d] = np.diag(pv ** 2); P0[d:, d:] = np.diag(qe ** 2 / (1 - phi ** 2))
    H = np.hstack([L, np.eye(n)])
    ys = [np.nan_to_num(r[t0 + k]) for k in range(K)]
    obs_idx = [np.flatnonzero(obs[t0 + k]) for k in range(K)]
    ref = _batch_filtering_reference(F, Q, np.zeros(d + n), P0, H, lambda s: np.diag(vv ** 2), ys, obs_idx)
    Lfull = np.hstack([L, np.zeros((n, n))])
    for k, (mz, Sz) in enumerate(ref):
        am = Lfull @ mz; av = np.maximum(np.einsum("ij,jk,ik->i", Lfull, Sz, Lfull), 1e-18)
        assert np.allclose(out.host_score[t0 + k], am, atol=1e-9), k
        assert np.allclose(out.host_prob[t0 + k], norm.sf((KAPPA - am) / np.sqrt(av)), atol=1e-9), k


# ------------------------------------------------------------------ partial pooling audit (C3)
@pytest.mark.parametrize("cls", [np.array([0] * 5 + [1] * 5), np.array([0] * 8 + [1] * 2), np.array([0] * 9 + [1]),
                                 np.array([0, 1, 2, 3, 4, 5])])
def test_sum_zero_local_deviations_and_group_interpretation(cls):
    C, B = class_structure(cls)
    for g in np.unique(cls):
        idx = np.flatnonzero(cls == g)
        assert np.allclose(B[idx].sum(0), 0, atol=1e-12)                       # deviations sum to zero within class
        cols = np.flatnonzero(np.abs(B[idx]).sum(0) > 1e-12)
        assert np.allclose(B[np.setdiff1d(np.arange(len(cls)), idx)][:, cols], 0, atol=1e-12)   # no leakage across classes
    S = C @ C.T + B @ B.T                                                      # unit-variance prior covariance
    for g in np.unique(cls):
        idx = np.flatnonzero(cls == g); m = len(idx)
        assert np.isclose(S[idx[0], idx[0]], 1 + (1 - 1 / m) if m > 1 else 1.0)  # singleton: no local deviation
        if m > 1:
            assert np.isclose(S[idx[0], idx[1]], 1 - 1 / m)                      # within-class covariance
    assert np.linalg.matrix_rank(np.hstack([C, B])) == len(cls)                 # full rank: host effects identifiable


# ------------------------------------------------------------------ simulator: legacy invariance + new scenarios
def _hash(r, t):
    h = hashlib.sha256()
    for a in (r.y, r.x, r.observed, r.decision_obs, r.class_id, r.exposed, r.request_count, t.a, t.spill, t.factor, t.noise):
        h.update(np.ascontiguousarray(np.nan_to_num(a.astype(float), nan=-999.0)).tobytes())
    return h.hexdigest()[:20]


def test_legacy_simulator_outputs_are_bit_identical_after_v3_edits():
    gold = json.loads((DATA / "legacy_sim_hashes.json").read_text())
    cfgs = {"default": SimConfig(), "step": SimConfig(workload_step=0.3365),
            "ramp_miss": SimConfig(shape="ramp", missing_rate=0.2, late_frac=0.1, heavy_tail_df=3, label_error=0.3,
                                   contam_frac=0.2, decay_len=10),
            "class0": SimConfig(affected_mode="class0", meas_sd=0.01)}
    for name, c in cfgs.items():
        for seed in (1, 2, 777):
            for harm in (True, False):
                assert _hash(*simulate(c, seed, harm)) == gold[f"{name}|{seed}|{int(harm)}"], (name, seed, harm)


def test_improvement_and_sub_boundary_are_not_events():
    for pct in (-3.0, 0.0, 2.0):
        _, t = simulate(SimConfig(effect_pct=pct, n_affected=3), 11, True)
        assert not M.event_truth(t, 10)["has_event"], pct
    _, t = simulate(SimConfig(effect_pct=2.5, n_affected=3), 11, True)
    assert M.event_truth(t, 10)["has_event"]


def test_mixed_fast_slow_gives_one_abrupt_host_and_slow_ramps():
    _, t = simulate(SimConfig(n_affected=4, mixed_mode="fast_host_slow_group", slow_ramp_len=40, duration=100), 5, True)
    fast, slow = t.affected_hosts[0], t.affected_hosts[1:]
    assert t.a[t.t0, fast] > 0.025                                             # abrupt: full size at onset
    assert all(t.a[t.t0, h] < 0.002 for h in slow) and all(t.a[t.t0 + 40, h] > 0.025 for h in slow)


def test_partial_recovery_even_hosts_recover_early():
    _, t = simulate(SimConfig(n_affected=4, mixed_mode="partial_recovery", duration=60), 5, True)
    ev = [int((t.a[:, h] > 0).sum()) for h in t.affected_hosts]
    assert ev[0] < ev[1] and ev[2] < ev[3] and ev[1] == ev[3] == 60


def test_workload_spikes_change_only_the_measured_workload_stream():
    r0, t0_ = simulate(SimConfig(), 9, False); r1, t1_ = simulate(SimConfig(spike_n=2, spike_mag=0.3, spike_len=6), 9, False)
    assert np.abs(r1.x - r0.x).max() > 0.29 and np.array_equal(t0_.factor, t1_.factor) and np.array_equal(t0_.noise, t1_.noise)


def test_bad_mixed_mode_is_rejected():
    with pytest.raises(ValueError):
        simulate(SimConfig(mixed_mode="nonsense"), 1, True)


# ------------------------------------------------------------------ statistics helpers
def test_holm_and_signflip():
    from canary_ssm.studies.study_inertia import holm_adjust, sign_flip_pvalue
    assert np.allclose(holm_adjust(np.array([0.01, 0.04, 0.03])), [0.03, 0.06, 0.06])
    rng = np.random.default_rng(0)
    assert sign_flip_pvalue(rng.normal(1.0, 1.0, 200)) < 0.01
    assert sign_flip_pvalue(rng.normal(0.0, 1.0, 200), seed=1) > 0.01
    assert sign_flip_pvalue(np.zeros(10)) == 1.0


# ------------------------------------------------------------------ end-to-end smoke of the study
@pytest.mark.skipif(not Path("artifacts/model_v2/model_config.json").exists(), reason="shipped tuned model absent")
def test_inertia_study_smoke(tmp_path):
    from canary_ssm.studies.study_inertia import run
    ts = {"kind": "hier", "rho_g": 0.999, "rho_h": 0.99, "sd_g": 0.000125, "sd_h_ratio": 4.0, "prior_sd": 0.005,
          "huber_c": 0.0, "prior_h_ratio": 0.5}
    run(model_dir="artifacts/model_v2", out_dir=tmp_path, n_null=30, n_val=30, n_harm=3, workers=1, persist_m=(1, 3),
        methods=["hier_ssm", "hier_ts", "adj_cusum"], ts_params=ts, tune=False, only_scenarios=["iso_spike_1host"])
    import pandas as pd
    v = pd.read_csv(tmp_path / "table_calibration_validity.csv")
    assert set(v["m_on"]) == {1, 3} and set(v["method"]) == {"hier_ssm", "hier_ts", "adj_cusum"}
    assert (tmp_path / "per_rollout_policy.csv").exists() and (tmp_path / "experiment_manifest.json").exists()
