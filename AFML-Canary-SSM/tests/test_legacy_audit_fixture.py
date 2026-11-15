import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from canary_ssm.experiments import load_models
from scripts.prepare_legacy_audit_fixture import prepare

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data_audit" / "model_pooled_dev"


def test_legacy_fixture_is_a_real_frozen_dev_fit_with_provenance():
    models, config, _ = load_models(FIXTURE)
    provenance = json.loads((FIXTURE / "generation_manifest.json").read_text())
    assert config["kind"] == "frozen" and config["frozen"] is True
    assert config["beta_mode"] == models.nuis["main"].beta_mode == "pooled_dev"
    assert provenance["data_role"] == "dev"
    assert provenance["n_healthy_dev_rollouts"] == 30
    assert provenance["dev_manifest"]["role"] == "dev"
    assert provenance["dev_manifest"]["seed_purpose"] == "dev"
    assert np.isfinite(models.nuis["main"].beta_pooled)
    for entry in models.nuis["main"].diagnostics["classes"]:
        assert any(fit["success"] for fit in entry["fits"])
    for name, expected in provenance["files_sha256"].items():
        assert hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == expected


def test_model_loading_still_rejects_missing_artifacts(tmp_path):
    with pytest.raises(FileNotFoundError, match="missing model artifact"):
        load_models(tmp_path / "missing")


def test_rebuild_never_overwrites_an_existing_model(tmp_path):
    directory = tmp_path / "existing"
    directory.mkdir()
    sentinel = directory / "model_config.json"
    sentinel.write_text("keep this model")
    with pytest.raises(FileExistsError):
        prepare(directory)
    assert sentinel.read_text() == "keep this model"
