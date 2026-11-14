"""Independent regression tests for V3 blocker fixes B2, B4, B5."""
import inspect
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from canary_ssm.studies import study_inertia
from canary_ssm.studies.study_inertia import holm_adjust


def test_b2_grid_path_parameter_exposed_and_forwarded():
    """Verify that study_inertia.run exposes grid_path and forwards it to tune_hier_ts."""
    sig_run = inspect.signature(study_inertia.run)
    assert "grid_path" in sig_run.parameters
    sig_tune = inspect.signature(study_inertia.tune_hier_ts)
    assert "grid_path" in sig_tune.parameters


def test_b4_holm_adjustment_per_hypothesis_family():
    """Verify that Holm adjustment within hypothesis families produces distinct adjustments
    from global adjustment across all contrasts."""
    # Hand-computed fixture:
    # 2 hypotheses, each with 2 p-values:
    # H1: [0.01, 0.04] -> rank 0: 0.01 * 2 = 0.02, rank 1: 0.04 * 1 = 0.04
    # H2: [0.02, 0.05] -> rank 0: 0.02 * 2 = 0.04, rank 1: 0.05 * 1 = 0.05
    # If done globally (4 p-values: 0.01, 0.02, 0.04, 0.05):
    # rank 0 (0.01): 0.01 * 4 = 0.04
    # rank 1 (0.02): 0.02 * 3 = 0.06
    # rank 2 (0.04): 0.04 * 2 = 0.08
    # rank 3 (0.05): 0.05 * 1 = 0.05 -> running max gives 0.08
    df = pd.DataFrame([
        {"scenario": "s1", "contrast": "C2_pooling:hier_ssm-vs-indep_ssm@m1", "p_signflip": 0.01},
        {"scenario": "s2", "contrast": "C2_pooling:hier_ssm-vs-indep_ssm@m1", "p_signflip": 0.04},
        {"scenario": "s1", "contrast": "C1_asymmetry:hier_ts-vs-hier_ssm@m1", "p_signflip": 0.02},
        {"scenario": "s2", "contrast": "C1_asymmetry:hier_ts-vs-hier_ssm@m1", "p_signflip": 0.05},
    ])

    def _hypothesis_for_contrast(c_name: str) -> str:
        if c_name.startswith("C1_asymmetry"):
            return "H2"
        elif c_name.startswith("C2_pooling"):
            return "H1"
        elif c_name.startswith("C3_hysteresis"):
            return "H3"
        elif c_name.startswith("C4_classical"):
            return "H5"
        return "other"

    df["hypothesis"] = df["contrast"].apply(_hypothesis_for_contrast)
    df["p_holm"] = np.nan
    for hyp, grp in df.groupby("hypothesis"):
        df.loc[grp.index, "p_holm"] = holm_adjust(grp["p_signflip"].to_numpy())

    h1_adj = df.loc[df["hypothesis"] == "H1", "p_holm"].to_numpy()
    assert np.allclose(h1_adj, [0.02, 0.04])
    h2_adj = df.loc[df["hypothesis"] == "H2", "p_holm"].to_numpy()
    assert np.allclose(h2_adj, [0.04, 0.05])

    global_adj = holm_adjust(df["p_signflip"].to_numpy())
    assert not np.allclose(df["p_holm"].to_numpy(), global_adj)


def test_b5_manifest_structure_includes_provenance():
    """Verify that build_manifest preserves seed_ranges and config hashes."""
    from canary_ssm import manifest as man_mod
    man = man_mod.build_manifest(
        out_dir=Path("."),
        study="inertia",
        seed_ranges=[{"purpose": "study_inertia_cal", "count": 2000}],
        inertia_grid_path="configs/grids_inertia.yaml",
        inertia_grid_sha256="abc123",
        scenario_file_path="configs/inertia_scenarios.yaml",
        scenario_file_sha256="def456",
    )
    assert "seed_ranges" in man
    assert man["seed_ranges"] == [{"purpose": "study_inertia_cal", "count": 2000}]
    assert man["inertia_grid_path"] == "configs/grids_inertia.yaml"
    assert man["inertia_grid_sha256"] == "abc123"
    assert man["scenario_file_path"] == "configs/inertia_scenarios.yaml"
    assert man["scenario_file_sha256"] == "def456"
