import json
import numpy as np
import pytest

from canary_ssm import experiments as E


def test_nuisance_recovers_simulated_noise(nuis):
    assert nuis.noise == "ar_only"                                   # handoff: single AR(1) per host by default
    assert np.allclose(nuis.phi_e, 0.6, atol=0.05) and np.allclose(nuis.q_e, 0.01, atol=0.002)
    assert np.allclose(nuis.v, 1e-4)                                 # white SD pinned, not estimated


def test_ar_white_mode_runs_and_reports_boundary_diagnostics():
    from canary_ssm.simulate import SimConfig, simulate
    from canary_ssm.preprocess import fit_nuisance
    rs = [simulate(SimConfig(meas_sd=0.01), s, False)[0] for s in range(20)]
    n = fit_nuisance(rs, noise="ar_white")
    fits = n.diagnostics["classes"][0]["fits"]
    assert all("boundary_hit" in f for f in fits) and 0.3 < n.phi_e[0] < 0.9   # weakly identified split is reported, not hidden


def test_evaluate_refuses_missing_or_mismatched_artifacts(tmp_path, nuis):
    with pytest.raises(FileNotFoundError):
        E.load_models(tmp_path / "nope")
    m = tmp_path / "model"; m.mkdir()
    nuis.save(m / "nuisance_main.json")
    (m / "model_config.json").write_text(json.dumps({"selected": {}, "methods": [], "alpha": 0.05}))
    models, cfg, h = E.load_models(m)
    p = tmp_path / "policy"; p.mkdir()
    (p / "policy.json").write_text(json.dumps({"model_hash": "WRONG", "thresholds": {}, "advisory": {}}))
    with pytest.raises(ValueError):
        E.load_policy(p, h)
    with pytest.raises(FileNotFoundError):
        E.load_policy(tmp_path / "none", h)


def test_small_dev_fold_is_rejected():
    from canary_ssm.simulate import SimConfig, simulate
    dev = [(r, t) for s in range(6) for h in (False, True) for r, t in [simulate(SimConfig(), s, h, pair_id=s)]]
    with pytest.raises(ValueError):
        E.select_on_dev(E.Models({}), dev, "adj_cusum", [{"k": 0.25}], [])
