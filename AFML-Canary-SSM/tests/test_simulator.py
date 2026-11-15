import ast
import numpy as np
from pathlib import Path

from canary_ssm.simulate import SimConfig, simulate
from canary_ssm.schema import Rollout, telemetry_to_rollout, KAPPA


def test_reproducible():
    a, _ = simulate(SimConfig(), 5, True); b, _ = simulate(SimConfig(), 5, True)
    assert np.array_equal(np.nan_to_num(a.y), np.nan_to_num(b.y))


def test_pair_differs_only_by_injection(pair):
    (rh, th), (rn, tn) = pair
    d = rh.y - rn.y
    assert np.allclose(d, th.a + th.spill, atol=1e-12)
    assert np.array_equal(rh.observed, rn.observed)               # missingness held fixed
    assert np.array_equal(th.factor, tn.factor) and np.array_equal(th.noise, tn.noise)


def test_no_harm_before_exposure_or_on_controls(pair):
    (rh, th), _ = pair
    assert th.a[:rh.t0].max() == 0
    assert th.a[:, rh.control_idx].max() == 0
    assert set(th.affected_hosts) <= set(rh.canary_idx.tolist())


def test_three_percent_is_log_1_03(pair):
    (_, th), _ = pair
    assert np.isclose(th.a.max(), np.log(1.03)) and not np.isclose(th.a.max(), 0.03 * 1)  # not 3 units / pp
    assert np.log(1.03) > KAPPA > 0


def test_truth_not_in_rollout():
    names = set(Rollout.__dataclass_fields__)
    assert not {"a", "truth", "factor", "noise", "spill"} & names


def test_inference_modules_never_touch_truth():
    pkg = Path(__file__).parents[1] / "canary_ssm"
    for f in ["factor", "preprocess", "baselines", "kalman", "hierarchy", "decision"]:
        tree = ast.parse((pkg / f"{f}.py").read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                assert "simulate" not in n.module and "metrics" not in n.module, f"{f} imports {n.module}"
            if isinstance(n, ast.Name):
                assert n.id != "Truth", f"{f} references Truth"


def test_csv_roundtrip(pair, tmp_path):
    (rh, _), _ = pair
    df = rh.to_telemetry(); assert "a_i_t" not in df.columns and "truth" not in " ".join(df.columns)
    df.to_csv(tmp_path / "t.csv", index=False)
    import pandas as pd
    r2 = telemetry_to_rollout(pd.read_csv(tmp_path / "t.csv"), rh.metadata())
    assert np.allclose(np.nan_to_num(r2.y), np.nan_to_num(rh.y)) and np.array_equal(r2.exposed, rh.exposed)


def test_missing_and_late_masks():
    r, _ = simulate(SimConfig(missing_rate=0.2, late_frac=0.1, burst_len=10), 3, True)
    assert 0.1 < (~r.observed).mean() < 0.35
    assert (r.decision_obs <= r.observed).all() and (r.decision_obs.sum() < r.observed.sum())
