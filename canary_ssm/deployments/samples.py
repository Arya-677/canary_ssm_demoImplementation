"""Sample Release Manifests and Fixture Generators.

Provides declarative manifests for clean and faulty canary releases.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BehaviorProfile, BehaviorProfileType, ReleaseArtifact


def get_sample_manifest(profile_name: str) -> dict[str, Any]:
    """Return a standard declarative sample manifest."""
    p_upper = profile_name.upper()

    if p_upper == "CLEAN":
        return {
            "release_id": "rel-v1.1.0-clean",
            "version_tag": "v1.1.0-clean",
            "behavior_profile": {
                "profile_type": "CLEAN",
                "severity": 0.0,
                "duration": 120,
            },
            "artifact": {
                "artifact_filename": "service_worker_v110.py",
                "content_preview": "# Optimized production build\nVERSION = 'v1.1.0-clean'\n",
            },
            "metadata": {"author": "release-team", "description": "Clean production release"},
        }

    elif p_upper == "MEMORY_LEAK":
        return {
            "release_id": "rel-v1.2.0-leak",
            "version_tag": "v1.2.0-leak",
            "behavior_profile": {
                "profile_type": "MEMORY_LEAK",
                "severity": 30.0,  # 30 MB per minute
                "duration": 120,
            },
            "artifact": {
                "artifact_filename": "cache_service_v120.py",
                "content_preview": "# Unbounded cache accumulation bug\nVERSION = 'v1.2.0-leak'\n",
            },
            "metadata": {"author": "caching-team", "description": "Release with simulated memory leak"},
        }

    elif p_upper == "LATENCY_REGRESSION":
        return {
            "release_id": "rel-v1.3.0-latency",
            "version_tag": "v1.3.0-latency",
            "behavior_profile": {
                "profile_type": "LATENCY_REGRESSION",
                "severity": 0.15,  # ~+16% latency
                "duration": 120,
            },
            "artifact": {
                "artifact_filename": "db_query_v130.py",
                "content_preview": "# Sub-optimal query execution path\nVERSION = 'v1.3.0-latency'\n",
            },
            "metadata": {"author": "backend-team", "description": "Release with algorithmic latency regression"},
        }

    elif p_upper == "CPU_REGRESSION":
        return {
            "release_id": "rel-v1.4.0-cpu",
            "version_tag": "v1.4.0-cpu",
            "behavior_profile": {
                "profile_type": "CPU_REGRESSION",
                "severity": 0.35,  # +35% CPU overhead
                "duration": 120,
            },
            "artifact": {
                "artifact_filename": "serializer_v140.py",
                "content_preview": "# Unvectorized serialization spinlock\nVERSION = 'v1.4.0-cpu'\n",
            },
            "metadata": {"author": "core-team", "description": "Release with CPU saturation bug"},
        }

    elif p_upper == "ERROR_REGRESSION":
        return {
            "release_id": "rel-v1.5.0-errors",
            "version_tag": "v1.5.0-errors",
            "behavior_profile": {
                "profile_type": "ERROR_REGRESSION",
                "severity": 0.04,  # +4% error rate
                "duration": 120,
            },
            "artifact": {
                "artifact_filename": "handler_v150.py",
                "content_preview": "# Null pointer dereference in edge cases\nVERSION = 'v1.5.0-errors'\n",
            },
            "metadata": {"author": "api-team", "description": "Release with 4% request error regression"},
        }

    else:
        raise ValueError(
            f"Unknown sample profile {profile_name!r}. "
            f"Allowed: CLEAN, MEMORY_LEAK, LATENCY_REGRESSION, CPU_REGRESSION, ERROR_REGRESSION"
        )


def write_sample_manifests(output_dir: Path | str) -> list[Path]:
    """Write all sample manifests to disk."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    profiles = ["CLEAN", "MEMORY_LEAK", "LATENCY_REGRESSION", "CPU_REGRESSION", "ERROR_REGRESSION"]
    paths: list[Path] = []

    for p in profiles:
        manifest = get_sample_manifest(p)
        filename = f"sample_manifest_{p.lower()}.json"
        p_path = out / filename
        p_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        paths.append(p_path)

    return paths
