import numpy as np

from canary_ssm import decision as D
from canary_ssm import metrics as M
from canary_ssm.simulate import Truth


def mk_truth(a, nc=3):
    T = a.shape[0]
    return Truth("x", a, np.zeros_like(a), np.zeros(T), np.zeros_like(a), [], True, "f", 0, 0, 10, {})


def test_threshold_rank_and_infinite():
    c = D.calibrate_threshold(np.arange(500.), 0.05)
    assert c["k"] == 476 and c["threshold"] == 475.0
    assert D.calibrate_threshold(np.arange(10.), 0.05)["threshold"] == float("inf")


def test_strict_ties_and_no_pre_rollout_alarm():
    s = np.array([9, 9, 1, 5, 5, 5.]); e = np.ones(6, bool)
    assert D.first_alarm(s, e, 5.0, 2) is None                      # equal to threshold is not an alarm
    assert D.first_alarm(s, e, 4.9, 2) == 3
    assert D.first_alarm(s, e, 0.0, 2) == 2                         # earlier high scores before t0 ignored
    e[3] = False
    assert D.first_alarm(s, e, 4.9, 2) == 4                         # ineligible minute cannot alarm


def test_release_max_full_horizon_eligible_only():
    s = np.array([100, 1, 7, 3.]); e = np.array([1, 1, 0, 1], bool)
    assert D.release_max(s, e, 1) == 3.0


def test_advisory_policy():
    s = np.array([0, 0, 5, 5, 1, 1, 1, 1, 1, 1, 5.]); e = np.ones(11, bool); e[8] = False
    r = D.advisory_replay(s, e, 0, h_on=4, h_off=2, n_clear=5)
    assert r["first_pause"] == 2 and r["states"][8] == D.UNKNOWN
    assert r["reversals"] == 1                                       # ineligible minute resets clear counter


def test_event_truth_equality_is_not_harm_and_duration():
    from canary_ssm.schema import KAPPA
    a = np.zeros((60, 3)); a[10:30, 0] = KAPPA                      # exactly kappa -> non-harmful
    assert not M.event_truth(mk_truth(a), 3)["has_event"]
    a[10:30, 0] = KAPPA * 1.5; a[40:50, 1] = KAPPA * 1.5            # 20 min qualifies, 10 min transient
    ev = M.event_truth(mk_truth(a), 3)
    assert ev["has_event"] and ev["onset"] == 10 and ev["affected"] == [0]
    a2 = np.zeros((60, 3)); a2[40:50, 1] = KAPPA * 1.5
    assert M.event_truth(mk_truth(a2), 3)["transient"]


def _ev(onset=10, end=40):
    return {"has_event": True, "onset": onset, "intervals": [(0, onset, end)], "transient": False, "affected": [0]}


def test_toy_outcomes_all_miss_premature_late_success():
    T = 100
    assert M.classify(None, _ev(), T)["status"] == "miss" and M.classify(None, _ev(), T)["capped"] == 90
    assert M.classify(5, _ev(), T)["status"] == "premature"          # not negative delay, capped at remaining
    assert M.classify(5, _ev(), T)["capped"] == 90
    c = M.classify(15, _ev(), T); assert c["status"] == "success" and c["delay"] == 5
    assert M.classify(60, _ev(), T)["status"] == "late_after_recovery"
    n = {"has_event": False, "transient": False}
    assert M.classify(None, n, T)["status"] == "quiet" and M.classify(3, n, T)["status"] == "alarm"


def test_clopper_pearson_and_bootstrap():
    assert abs(M.upper_one_sided(0, 60) - 0.0487) < 5e-4
    lo, hi = M.clopper_pearson(25, 500); assert lo < 0.05 < hi
    m, lo, hi = M.paired_bootstrap(np.r_[np.ones(50), -np.ones(50)]); assert lo < 0 < hi
