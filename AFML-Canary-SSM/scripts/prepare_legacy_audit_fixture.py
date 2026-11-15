"""Rebuild the small frozen audit model required by the legacy reproduction test.

Run from the repository root: python -m scripts.prepare_legacy_audit_fixture
This is a newly generated reproducible fixture, not recovered historical bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from canary_ssm import experiments as E

ROOT = Path(__file__).resolve().parents[1]
METHODS = ["matched_contrast", "adj_cusum", "topk_cusum", "pooled_ssm", "indep_ssm", "hier_ssm"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(out=None):
    out = Path(out) if out is not None else ROOT / "data_audit" / "model_pooled_dev"
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing model directory: {out}; choose --out for a new fixture")
    recipe_path = ROOT / "configs" / "legacy_audit_fixture.yaml"
    config = E.load_config(recipe_path)
    with tempfile.TemporaryDirectory(prefix="canary-legacy-dev-") as temporary:
        dev_dir = Path(temporary) / "dev"
        dev_manifest = E.generate_role(config, "dev", dev_dir, config_path=str(recipe_path))
        model = E.fit(dev_dir, out, METHODS, beta_mode="pooled_dev", frozen=True, workers=1)
    # The original fitter writes convergence diagnostics and explicit frozen flags.
    files = sorted(p for p in out.iterdir() if p.is_file())
    provenance = {
        "purpose": "New frozen audit/reproduction fixture; not the original historical model",
        "command": "python -m scripts.prepare_legacy_audit_fixture",
        "recipe": str(recipe_path.relative_to(ROOT)),
        "recipe_sha256": sha256(recipe_path),
        "data_role": "dev",
        "n_healthy_dev_rollouts": dev_manifest["n_pairs"],
        "dev_manifest": dev_manifest,
        "frozen": model["frozen"],
        "beta_mode": model["beta_mode"],
        "source_sha256": {f"canary_ssm/{name}": sha256(ROOT / "canary_ssm" / name) for name in
                          ("simulate.py", "schema.py", "factor.py", "preprocess.py", "experiments.py", "seeds.py")},
        "files_sha256": {p.name: sha256(p) for p in files},
    }
    (out / "generation_manifest.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="new output directory; existing models are never overwritten")
    args = parser.parse_args()
    print(f"Prepared frozen legacy audit fixture: {prepare(args.out)}")


if __name__ == "__main__":
    main()
