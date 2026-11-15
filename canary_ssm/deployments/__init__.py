"""Deployments package for Versioned Release Registry and Deployment Lifecycle."""
from __future__ import annotations

from .allocation import (
    AllocationValidationResult,
    generate_default_allocation,
    validate_canary_allocation,
)
from .manager import DeploymentManager
from .models import (
    ALLOWED_ARTIFACT_EXTENSIONS,
    MAX_ARTIFACT_SIZE_BYTES,
    BehaviorProfile,
    BehaviorProfileType,
    Release,
    ReleaseArtifact,
    ReleaseRegistry,
    RolloutState,
    RolloutTransition,
)
from .samples import get_sample_manifest, write_sample_manifests

__all__ = [
    "ALLOWED_ARTIFACT_EXTENSIONS",
    "MAX_ARTIFACT_SIZE_BYTES",
    "AllocationValidationResult",
    "BehaviorProfile",
    "BehaviorProfileType",
    "DeploymentManager",
    "Release",
    "ReleaseArtifact",
    "ReleaseRegistry",
    "RolloutState",
    "RolloutTransition",
    "generate_default_allocation",
    "get_sample_manifest",
    "validate_canary_allocation",
    "write_sample_manifests",
]
