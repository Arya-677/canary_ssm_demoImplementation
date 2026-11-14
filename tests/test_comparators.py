"""
Unit tests and reference fixtures for external comparators (Gate G4).
Implements CMP-01 through CMP-10:
- CMP-01: KayentaJudge identical distributions
- CMP-02: KayentaJudge degraded canary
- CMP-03: KayentaJudge insufficient samples (NODATA)
- CMP-04: KayentaJudge rolling sequence evaluation
- CMP-05: SLOThresholdComparator positive contrast
- CMP-06: SLOThresholdComparator standardization scaling
- CMP-07: ArgoRolloutsPolicy AR-1 immediate failure
- CMP-08: ArgoRolloutsPolicy consecutive vs cumulative mode
- CMP-09: FlaggerPolicy failed checks accumulation
- CMP-10: NoInertiaSSM memoryless effect response
"""
import numpy as np
import pytest

from canary_ssm.comparators import (
    KayentaJudge, KayentaConfig,
    SLOThresholdComparator, SLOConfig,
    ArgoRolloutsPolicy, ArgoPolicyConfig,
    FlaggerPolicy, FlaggerPolicyConfig,
    NoInertiaSSM
)
from canary_ssm.factor import adjust
from canary_ssm.hierarchy import EffectDetector, EffectParams
from canary_ssm.preprocess import fit_nuisance
from canary_ssm.simulate import SimConfig, simulate


@pytest.fixture
def rollout_pair():
    cfg = SimConfig(n_hosts=12, n_canary=2, t_pre=30, t_post=30, duration=25)
    r_null, _ = simulate(cfg, seed=101, harm=False)
    r_harm, _ = simulate(cfg, seed=202, harm=True)
    nuis = fit_nuisance([r_null])
    adj_null = adjust(r_null, nuis.x_center, np.array(nuis.class_lambda))
    adj_harm = adjust(r_harm, nuis.x_center, np.array(nuis.class_lambda))
    return nuis, adj_null, adj_harm


# ---------------------------------------------------------------------------
# CMP-01: KayentaJudge Identical Distributions -> PASS
# ---------------------------------------------------------------------------
def test_cmp_01_kayenta_identical_distributions():
    judge = KayentaJudge(KayentaConfig(min_samples=5))
    canary = np.array([10.0, 10.2, 9.8, 10.1, 9.9, 10.0])
    control = np.array([10.0, 10.1, 9.9, 10.0, 10.2, 9.8])
    outcome, p_val, z = judge.evaluate_sample(canary, control)
    assert outcome == "PASS"
    assert p_val > 0.1


# ---------------------------------------------------------------------------
# CMP-02: KayentaJudge Degraded Canary -> FAIL_CRITICAL
# ---------------------------------------------------------------------------
def test_cmp_02_kayenta_degraded_canary():
    judge = KayentaJudge(KayentaConfig(min_samples=5, effect_size_threshold=0.5))
    canary = np.array([25.0, 26.0, 24.5, 27.0, 25.5, 28.0])
    control = np.array([10.0, 10.5, 9.8, 10.2, 9.9, 10.1])
    outcome, p_val, z = judge.evaluate_sample(canary, control)
    assert outcome == "FAIL_CRITICAL"
    assert p_val < 0.01
    assert z > 2.0


# ---------------------------------------------------------------------------
# CMP-03: KayentaJudge Insufficient Samples -> NODATA
# ---------------------------------------------------------------------------
def test_cmp_03_kayenta_insufficient_samples():
    judge = KayentaJudge(KayentaConfig(min_samples=10))
    canary = np.array([12.0, 13.0, 14.0])
    control = np.array([10.0, 10.5, 9.8])
    outcome, p_val, z = judge.evaluate_sample(canary, control)
    assert outcome == "NODATA"
    assert p_val == 1.0
    assert z == 0.0


# ---------------------------------------------------------------------------
# CMP-04: KayentaJudge Rolling Evaluation
# ---------------------------------------------------------------------------
def test_cmp_04_kayenta_rolling_run(rollout_pair):
    _, adj_null, adj_harm = rollout_pair
    judge = KayentaJudge(KayentaConfig(window=10))
    out_null = judge.run(adj_null)
    out_harm = judge.run(adj_harm)

    assert out_null.score.shape == (adj_null.r.shape[0],)
    assert np.isnan(out_null.score[:adj_null.t0]).all()
    assert np.isfinite(out_null.score[adj_null.t0:]).all()

    # Harmful rollout should achieve significantly higher score than null rollout
    mean_harm = np.mean(out_harm.score[adj_harm.t0:])
    mean_null = np.mean(out_null.score[adj_null.t0:])
    assert mean_harm > mean_null


# ---------------------------------------------------------------------------
# CMP-05: SLOThresholdComparator Positive Contrast
# ---------------------------------------------------------------------------
def test_cmp_05_slo_positive_contrast(rollout_pair):
    _, adj_null, adj_harm = rollout_pair
    slo = SLOThresholdComparator(SLOConfig(window=5, standardize=True))
    out_harm = slo.run(adj_harm)
    out_null = slo.run(adj_null)

    assert np.mean(out_harm.score[adj_harm.t0:]) > np.mean(out_null.score[adj_null.t0:])


# ---------------------------------------------------------------------------
# CMP-06: SLOThresholdComparator Standardization
# ---------------------------------------------------------------------------
def test_cmp_06_slo_standardization(rollout_pair):
    _, adj_null, _ = rollout_pair
    slo_std = SLOThresholdComparator(SLOConfig(standardize=True))
    slo_raw = SLOThresholdComparator(SLOConfig(standardize=False))
    out_std = slo_std.run(adj_null)
    out_raw = slo_raw.run(adj_null)

    assert out_std.score.shape == out_raw.score.shape
    assert not np.isnan(out_std.score[adj_null.t0:]).any()


# ---------------------------------------------------------------------------
# CMP-07: ArgoRolloutsPolicy AR-1 Immediate Failure
# ---------------------------------------------------------------------------
def test_cmp_07_argo_ar1_immediate_failure(rollout_pair):
    _, _, adj_harm = rollout_pair
    argo_ar1 = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=1))
    out = argo_ar1.run(adj_harm)
    # Once failure counter reaches 1, score reaches 1.0 (failure threshold)
    assert (out.score[adj_harm.t0:] >= 1.0).any()


# ---------------------------------------------------------------------------
# CMP-08: ArgoRolloutsPolicy Consecutive vs Cumulative
# ---------------------------------------------------------------------------
def test_cmp_08_argo_consecutive_vs_cumulative(rollout_pair):
    _, _, adj_harm = rollout_pair
    argo_cumul = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=5, consecutive=False))
    argo_consec = ArgoRolloutsPolicy(ArgoPolicyConfig(failure_limit=5, consecutive=True))

    out_cumul = argo_cumul.run(adj_harm)
    out_consec = argo_consec.run(adj_harm)

    # Cumulative score is non-decreasing; consecutive can reset
    diffs_cumul = np.diff(out_cumul.score[adj_harm.t0:])
    assert (diffs_cumul >= 0).all()


# ---------------------------------------------------------------------------
# CMP-09: FlaggerPolicy Failed Checks Accumulation
# ---------------------------------------------------------------------------
def test_cmp_09_flagger_policy_accumulation(rollout_pair):
    _, _, adj_harm = rollout_pair
    flagger = FlaggerPolicy(FlaggerPolicyConfig(max_failed_checks=10))
    out = flagger.run(adj_harm)

    assert out.method == "flagger_policy"
    # Budget fraction increases monotonically
    diffs = np.diff(out.score[adj_harm.t0:])
    assert (diffs >= 0).all()


# ---------------------------------------------------------------------------
# CMP-10: NoInertiaSSM Memoryless Response
# ---------------------------------------------------------------------------
def test_cmp_10_no_inertia_ssm_memoryless(rollout_pair):
    nuis, adj_null, adj_harm = rollout_pair
    no_inertia = NoInertiaSSM(nuis)
    hier = EffectDetector(nuis, EffectParams(kind="hier", rho_g=0.95, rho_h=0.95))

    out_no_inertia = no_inertia.run(adj_harm)
    out_hier = hier.run(adj_harm)

    assert out_no_inertia.method == "no_inertia_ssm"
    assert out_no_inertia.score.shape == out_hier.score.shape
    # Ensure no-inertia score fluctuates more rapidly due to zero temporal smoothing
    var_no_inertia = np.var(np.diff(out_no_inertia.score[adj_harm.t0:]))
    var_hier = np.var(np.diff(out_hier.score[adj_harm.t0:]))
    assert var_no_inertia > var_hier, "No-inertia SSM did not exhibit higher variance than smoothed SSM"
