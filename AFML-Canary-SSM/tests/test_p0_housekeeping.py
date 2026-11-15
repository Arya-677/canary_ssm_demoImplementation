"""Phase P0 housekeeping tests: seeds, manifest, parallel determinism, cache/resume, on-the-fly, disk guard."""
from __future__ import annotations

import json
import os
import subprocess
import tokenize
from pathlib import Path

import pandas as pd
import pytest

from canary_ssm import experiments as E
from canary_ssm import manifest as M_mod
from canary_ssm import parallel, seeds


def test_seed_ranges_disjoint():
    seeds.assert_disjoint()


def test_seed_for_bounds():
    assert seeds.seed_for("dev", 0, 0) == 1_000_000
    assert seeds.seed_for("audit", 5, 2) == 6_000_000 + 2 * seeds.FAMILY_STRIDE + 5
    with pytest.raises(ValueError):
        seeds.seed_for("dev", -1, 0)
    with pytest.raises(ValueError):
        seeds.seed_for("dev", seeds.FAMILY_STRIDE, 0)
    with pytest.raises(ValueError):
        seeds.seed_for("dev", 0, 50)
    with pytest.raises(ValueError):
        seeds.seed_for("smoke", 0, 49)
    with pytest.raises(KeyError):
        seeds.seed_for("nonexistent_purpose", 0, 0)


def test_no_adhoc_seed_literals():
    pkg = Path(__file__).resolve().parents[1] / "canary_ssm"
    targets = [pkg / "experiments.py"]
    studies_dir = pkg / "studies"
    if studies_dir.exists():
        targets.extend(sorted(studies_dir.glob("*.py")))
    bad = []
    for path in targets:
        lines = path.read_text(encoding="utf-8").splitlines()
        with path.open("rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type == tokenize.NUMBER:
                    raw = tok.string.replace("_", "")
                    if raw.isdigit() and len(raw) >= 7:
                        src_line = lines[tok.start[0] - 1]
                        if not any(k in src_line for k in ("seed_for", "LEGACY", "RANGES")):
                            bad.append(f"{path.name}:{tok.start[0]}: {src_line.strip()}")
    assert not bad, "Ad-hoc >=7-digit integer literals outside seed registry:\n" + "\n".join(bad)


REQUIRED_MANIFEST_KEYS = [
    "commit", "git_dirty", "config", "config_hash", "regime", "beta_mode", "noise_mode",
    "factor_rank", "grid_file", "grid_hash", "candidate_table_hash", "selected", "edge_flags",
    "seed_registry_version", "seed_ranges", "packages", "python", "os", "cpu_model", "threads",
    "wall_times", "fit_failures", "model_hash", "policy_hash", "lockfile_hash", "disk_free_bytes", "created",
]


@pytest.mark.parametrize("key", REQUIRED_MANIFEST_KEYS)
def test_manifest_has_required_keys(key):
    man = M_mod.build_manifest(
        config={}, config_hash="abc", regime="plain", beta_mode="pre",
        noise_mode="ar_only", factor_rank=1, model_hash="mh", policy_hash="ph",
    )
    assert key in man


def test_manifest_records_dirty_flag(tmp_path):
    git_exe = M_mod.find_git()
    assert git_exe is not None, "git executable required for manifest dirty-flag test"
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call([git_exe, "init"], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call([git_exe, "config", "user.name", "Test"], cwd=repo)
    subprocess.check_call([git_exe, "config", "user.email", "test@local"], cwd=repo)
    f = repo / "tracked.txt"
    f.write_text("v1\n", encoding="utf-8")
    subprocess.check_call([git_exe, "add", "tracked.txt"], cwd=repo)
    subprocess.check_call([git_exe, "commit", "-m", "init"], cwd=repo, stdout=subprocess.DEVNULL)

    clean = M_mod.build_manifest(repo_dir=repo)
    assert clean["git_dirty"] is False
    assert clean["commit"] and not str(clean["commit"]).endswith("-dirty")

    f.write_text("v2\n", encoding="utf-8")
    dirty = M_mod.build_manifest(repo_dir=repo)
    assert dirty["git_dirty"] is True
    assert "dirty" in str(dirty["commit"])


def _small_cfg(n_dev=42, n_cal=22, n_val=8, n_test=6):
    return {
        "regime": "plain",
        "sim": {"sd_host": 0.02, "t_pre": 90, "t_post": 40},
        "roles": {
            "dev": {"pairs": n_dev},
            "calibration": {"pairs": n_cal},
            "null_validation": {"pairs": n_val},
            "test": {"pairs": n_test},
        },
        "families": [{"name": "S1_sparse", "weight": 1.0, "overrides": {"n_affected": 3}}],
    }


def test_workers_1_vs_8_and_on_the_fly_deterministic(tmp_path):
    cfg = _small_cfg()
    for role in ("dev", "calibration", "null_validation", "test"):
        E.generate_role(cfg, role, tmp_path / "data" / role)

    methods = ["adj_cusum", "topk_cusum", "hier_ssm"]
    cache_dir = tmp_path / "cache"
    E.fit(tmp_path / "data" / "dev", tmp_path / "model1", methods, grid_stride=6, allow_small_dev=True, workers=1, cache_dir=cache_dir, log=lambda *a: None)
    E.fit(tmp_path / "data" / "dev", tmp_path / "model8", methods, grid_stride=6, allow_small_dev=True, workers=8, cache_dir=cache_dir, log=lambda *a: None)

    df_sel1 = (tmp_path / "model1" / "dev_selection.csv").read_text(encoding="utf-8")
    df_sel8 = (tmp_path / "model8" / "dev_selection.csv").read_text(encoding="utf-8")
    assert pd.read_csv(tmp_path / "model1" / "dev_selection.csv").drop(columns=["seconds"]).equals(
        pd.read_csv(tmp_path / "model8" / "dev_selection.csv").drop(columns=["seconds"])
    )
    assert json.loads((tmp_path / "model1" / "model_config.json").read_text())["selected"] == json.loads((tmp_path / "model8" / "model_config.json").read_text())["selected"]

    p1 = E.calibrate(tmp_path / "data" / "calibration", tmp_path / "model1", tmp_path / "pol1", workers=1, log=lambda *a: None)
    p8 = E.calibrate(tmp_path / "data" / "calibration", tmp_path / "model1", tmp_path / "pol8", workers=8, log=lambda *a: None)
    assert p1["thresholds"] == p8["thresholds"]
    assert p1["ecdf"] == p8["ecdf"]

    E.evaluate(tmp_path / "data" / "test", tmp_path / "model1", tmp_path / "pol1", tmp_path / "out1", workers=1, log=lambda *a: None)
    E.evaluate(tmp_path / "data" / "test", tmp_path / "model1", tmp_path / "pol1", tmp_path / "out8", workers=8, log=lambda *a: None)
    for fname in ("per_rollout_metrics.csv", "host_metrics.csv", "flicker.csv", "calibration_bins.csv", "fit_failures.csv"):
        assert (tmp_path / "out1" / fname).read_text(encoding="utf-8") == (tmp_path / "out8" / fname).read_text(encoding="utf-8")

    # On-the-fly equality against from-disk
    E.generate_role(cfg, "calibration", tmp_path / "fly" / "calibration", manifest_only=True)
    E.generate_role(cfg, "test", tmp_path / "fly" / "test", manifest_only=True)
    pfly = E.calibrate(tmp_path / "fly" / "calibration", tmp_path / "model1", tmp_path / "pol_fly",
                       workers=4, generate_on_the_fly=True, log=lambda *a: None)
    assert pfly["thresholds"] == p1["thresholds"]
    E.evaluate(tmp_path / "fly" / "test", tmp_path / "model1", tmp_path / "pol_fly", tmp_path / "out_fly",
               workers=4, generate_on_the_fly=True, log=lambda *a: None)
    for fname in ("per_rollout_metrics.csv", "host_metrics.csv", "flicker.csv", "calibration_bins.csv"):
        assert (tmp_path / "out1" / fname).read_text(encoding="utf-8") == (tmp_path / "out_fly" / fname).read_text(encoding="utf-8")

    # Resume check: re-run evaluate with resume=True after writing journal and verify equality
    E.evaluate(tmp_path / "data" / "test", tmp_path / "model1", tmp_path / "pol1", tmp_path / "out_res",
               workers=2, resume=True, log=lambda *a: None)
    E.evaluate(tmp_path / "data" / "test", tmp_path / "model1", tmp_path / "pol1", tmp_path / "out_res",
               workers=2, resume=True, log=lambda *a: None)
    assert (tmp_path / "out1" / "per_rollout_metrics.csv").read_text(encoding="utf-8") == (
        tmp_path / "out_res" / "per_rollout_metrics.csv"
    ).read_text(encoding="utf-8")


def test_disk_budget_guard(tmp_path):
    info = parallel.check_disk_budget(tmp_path, n_rollouts_to_store=10)
    assert info["disk_free_bytes"] > 0
    huge = int(info["disk_free_bytes"] / parallel.BYTES_PER_STORED_ROLLOUT) + 10_000
    with pytest.raises(RuntimeError, match="70%"):
        parallel.check_disk_budget(tmp_path, n_rollouts_to_store=huge)
