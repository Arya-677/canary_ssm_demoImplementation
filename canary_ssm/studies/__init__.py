"""In-package parameterised study runners (WP-A5, WP-A6).

Every study:
- imports from `canary_ssm` (never mutating `sys.path` or hardcoding script paths)
- gets eligibility strictly from `DetectorOutput.elig` (never raw observation masks)
- refuses frozen models and regime mismatches unless explicitly flagged
- draws disjoint seeds via `canary_ssm.seeds`
- emits CSV/JSON artifacts and derives any Markdown tables strictly from those CSVs
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


STUDY_MODULES: dict[str, str] = {
    "x02a": "canary_ssm.studies.study_anomalies:run_x02a",
    "x02b": "canary_ssm.studies.study_anomalies:run_x02b",
    "x02c": "canary_ssm.studies.study_anomalies:run_x02c",
    "x02": "canary_ssm.studies.study_anomalies:run",
    "regime": "canary_ssm.studies.study_regime:run",
    "exp7": "canary_ssm.studies.study_regime:run",
    "robust": "canary_ssm.studies.study_robust:run",
    "exp8": "canary_ssm.studies.study_robust:run",
}


def require_tuned(model_cfg: dict[str, Any], allow_frozen: bool = False) -> None:
    """Enforce that performance studies use a tuned model (`kind == 'tuned'`)."""
    kind = model_cfg.get("kind")
    if kind != "tuned" and not allow_frozen:
        raise ValueError(
            f"Refusing non-tuned model (kind={kind!r}, frozen={model_cfg.get('frozen')!r}). "
            "Pass allow_frozen=True / --allow-frozen only for explicit calibration or diagnostic audits."
        )


def policy_regime(policy: dict[str, Any]) -> str | None:
    """Extract active regime label from Policy Schema v1 or v2."""
    if policy.get("schema_version") == 2 and "regimes" in policy:
        return policy.get("default_regime") or policy.get("regime")
    return policy.get("regime")


def require_regime(
    policy: dict[str, Any],
    expected: str | None,
    allow_mismatch: bool = False,
) -> str | None:
    """Verify policy regime matches `expected` unless `allow_mismatch=True`."""
    got = policy_regime(policy)
    if expected is not None and got != expected and not allow_mismatch:
        raise ValueError(
            f"Regime mismatch: policy has regime={got!r}, expected {expected!r}. "
            "Pass allow_regime_mismatch=True / --allow-regime-mismatch only for explicit audits."
        )
    return got


def available_studies() -> list[str]:
    return sorted(STUDY_MODULES)


def run_study(name: str, **kwargs) -> dict[str, Any]:
    """Dispatch a registered study by name."""
    key = str(name).strip().lower()
    if key not in STUDY_MODULES:
        raise KeyError(f"Unknown study {name!r}; available: {available_studies()}")
    mod_name, fn_name = STUDY_MODULES[key].split(":")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name)
    return fn(**kwargs)


def write_summary_md(path: Path, title: str, sections: list[tuple[str, str]]) -> Path:
    """Render Markdown strictly from saved CSVs / tables."""
    lines = [f"# {title}\n", "_Generated strictly from saved CSV/JSON outputs._\n"]
    for heading, body in sections:
        lines.append(f"\n## {heading}\n")
        lines.append(body)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(path)
