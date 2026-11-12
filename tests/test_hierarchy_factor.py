import numpy as np

from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectDetector, EffectParams, class_structure, build_model
from canary_ssm.simulate import SimConfig, simulate
from canary_ssm.baselines import run_baseline


def test_class_structure_sum_zero_orthonormal_and_singleton():
    cls = np.array([0, 0, 0, 1, 1, 2])                      # class 2 is a singleton
    C, B = class_structure(cls)
    assert C.shape == (6, 3) and B.shape == (6, 3)           # n - G = 3 deviation coordinates
    assert np.allclose(C.T @ B, 0, atol=1e-12)               # deviations sum to zero within class
    assert np.allclose(B.T @ B, np.eye(3), atol=1e-12)
    assert np.allclose(B[5], 0)                              # singleton has no local deviation


def test_effect_map_is_full_rank_identifiable():
    cls = np.array([0, 1] * 5)
    L, rho, sd = build_model(EffectParams(kind="hier"), cls)
    assert np.linalg.matrix_rank(L) == 10                    # class + local coordinates span host space


def test_canary_loading_uses_pre_period_only(nuis, pair):
    (rh, _), _ = pair
    a1 = adjust(rh, nuis.x_center, np.array(nuis.class_lambda))
    r2 = simulate(SimConfig(), 777, True)[0]
    r2.y[rh.t0:, :rh.canary_idx.size] += 0.5                 # wreck canary POST data
    a2 = adjust(r2, nuis.x_center, np.array(nuis.class_lambda))
    assert np.allclose(a1.lam, a2.lam) and np.allclose(a1.sigma, a2.sigma)


def test_future_perturbation_leaves_past_unchanged(nuis, pair):
    (rh, _), _ = pair
    t1 = rh.t0 + 40
    r2 = simulate(SimConfig(), 777, True)[0]
    rng = np.random.default_rng(0); r2.y[t1 + 1:] += rng.normal(0, 0.1, r2.y[t1 + 1:].shape)
    a1 = adjust(rh, nuis.x_center, np.array(nuis.class_lambda)); a2 = adjust(r2, nuis.x_center, np.array(nuis.class_lambda))
    assert np.allclose(a1.r[:t1 + 1], a2.r[:t1 + 1], equal_nan=True)
    for kind in ("hier", "indep", "pooled"):
        s1 = EffectDetector(nuis, EffectParams(kind=kind)).run(a1).score
        s2 = EffectDetector(nuis, EffectParams(kind=kind)).run(a2).score
        assert np.allclose(s1[:t1 + 1], s2[:t1 + 1], equal_nan=True)
    for name, p in [("adj_cusum", {}), ("adj_ewma", {}), ("topk_cusum", {}), ("matched_contrast", {})]:
        s1 = run_baseline(name, a1, **p).score; s2 = run_baseline(name, a2, **p).score
        assert np.allclose(s1[:t1 + 1], s2[:t1 + 1], equal_nan=True), name


def test_no_scores_before_rollout(nuis, pair):
    (rh, _), _ = pair
    a = adjust(rh, nuis.x_center, np.array(nuis.class_lambda))
    assert np.isnan(EffectDetector(nuis, EffectParams()).run(a).score[:rh.t0]).all()
    assert np.isnan(run_baseline("adj_cusum", a).score[:rh.t0]).all()


def test_rank_zero_and_shared_shock(nuis):
    r, _ = simulate(SimConfig(shock=0.15), 11, False)
    a1 = adjust(r, nuis.x_center, np.array(nuis.class_lambda), 1)
    a0 = adjust(r, nuis.x_center, np.array(nuis.class_lambda), 0)
    assert np.all(a0.f_hat == 0)
    # the shared shock lands in residuals only when the factor is NOT removed
    assert np.nanmax(np.abs(a0.r[r.t0:r.t0 + 5])) > 3 * np.nanmax(np.abs(a1.r[r.t0:r.t0 + 5]))


def test_eligibility_rules():
    r, _ = simulate(SimConfig(), 12, False)
    r.decision_obs[r.t0 + 3, :8] = False                      # only 2/10 canaries observed -> insufficient
    r.decision_obs[r.t0 + 4, r.control_idx[:90]] = False      # no controls -> insufficient
    from canary_ssm.preprocess import Nuisance
    a = adjust(r, 0.0, np.ones(2))
    assert not a.elig[r.t0 + 3] and not a.elig[r.t0 + 4] and a.elig[r.t0 + 5]


def test_hier_detects_harm_more_than_null(nuis, pair):
    (rh, _), (rn, _) = pair
    sh = EffectDetector(nuis, EffectParams()).run(adjust(rh, nuis.x_center, np.array(nuis.class_lambda)))
    sn = EffectDetector(nuis, EffectParams()).run(adjust(rn, nuis.x_center, np.array(nuis.class_lambda)))
    assert np.nanmax(sh.score) > np.nanmax(sn.score)
    assert sh.params["min_eig"] > -1e-10
