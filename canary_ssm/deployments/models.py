"""Models for Versioned Release Registry, Artifact Metadata, and Behavior Profiles.

Explicitly separates:
- Source Artifact Metadata (content hash, unexecuted label, size/type limits)
- Simulation Behavior Profile (CLEAN, MEMORY_LEAK, CPU_REGRESSION, ERROR_REGRESSION, LATENCY_REGRESSION)
The detector cannot inspect either the artifact contents or the behavior profile.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Maximum source artifact size: 10 MB (10,485,760 bytes)
MAX_ARTIFACT_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_ARTIFACT_EXTENSIONS = {".py", ".tar.gz", ".zip", ".whl", ".json", ".txt", ".yaml", ".yml"}


class BehaviorProfileType(str, Enum):
    """Predeclared simulated behavior profile types."""
    CLEAN = "CLEAN"
    MEMORY_LEAK = "MEMORY_LEAK"
    CPU_REGRESSION = "CPU_REGRESSION"
    ERROR_REGRESSION = "ERROR_REGRESSION"
    LATENCY_REGRESSION = "LATENCY_REGRESSION"


class RolloutState(str, Enum):
    """Validated lifecycle states for canary rollouts."""
    CREATED = "CREATED"
    BASELINING = "BASELINING"
    CANARY = "CANARY"
    PAUSED = "PAUSED"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RolloutTransition:
    """Append-only audit log record of rollout state transitions."""
    release_id: str
    from_state: RolloutState
    to_state: RolloutState
    tick: int
    reason: str


@dataclass(frozen=True)
class BehaviorProfile:
    """Declared simulation behavior associated with a versioned release.

    Note:
        Telemetry is generated numerically based on this profile;
        it is NEVER executed from uploaded source code.
    """
    profile_type: BehaviorProfileType
    severity: float = 0.0               # Magnitude (e.g. MB/min for leak, delta for latency/cpu/err)
    duration: int = 120                 # Active duration in simulation ticks (minutes)
    susceptible_class_id: int | None = None  # Optional compatibility class restriction
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        import math
        if math.isnan(self.severity) or math.isinf(self.severity):
            raise ValueError(f"BehaviorProfile severity must be a finite number, got {self.severity}")
        if self.duration < 0:
            raise ValueError(f"BehaviorProfile duration must be non-negative, got {self.duration}")
        if self.susceptible_class_id is not None and self.susceptible_class_id < 0:
            raise ValueError(f"susceptible_class_id must be non-negative, got {self.susceptible_class_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_type": self.profile_type.value,
            "severity": float(self.severity),
            "duration": int(self.duration),
            "susceptible_class_id": self.susceptible_class_id,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BehaviorProfile":
        return cls(
            profile_type=BehaviorProfileType(d["profile_type"]),
            severity=float(d.get("severity", 0.0)),
            duration=int(d.get("duration", 120)),
            susceptible_class_id=int(d["susceptible_class_id"]) if d.get("susceptible_class_id") is not None else None,
            parameters=dict(d.get("parameters", {})),
        )


@dataclass(frozen=True)
class ReleaseArtifact:
    """Metadata for uploaded unexecuted software source artifact.

    Strict Contract:
        Uploaded files are stored exclusively for provenance tracking and hashing.
        They are NEVER executed inside the virtual data center simulator.
    """
    artifact_filename: str
    checksum_sha256: str
    size_bytes: int
    is_executed: bool = False
    execution_status: str = "UNEXECUTED_SIMULATION_PROFILE"
    notes: str = "Uploaded source artifact stored for simulation profiling only; host execution is disabled."

    def __post_init__(self) -> None:
        if not self.artifact_filename:
            raise ValueError("artifact_filename cannot be empty")
        if self.size_bytes > MAX_ARTIFACT_SIZE_BYTES:
            raise ValueError(
                f"Artifact size ({self.size_bytes} bytes) exceeds limit of {MAX_ARTIFACT_SIZE_BYTES} bytes (10MB)"
            )
        # Check allowed file extensions
        has_allowed_ext = any(self.artifact_filename.lower().endswith(ext) for ext in ALLOWED_ARTIFACT_EXTENSIONS)
        if not has_allowed_ext:
            raise ValueError(
                f"Artifact file extension not supported for {self.artifact_filename!r}. "
                f"Allowed extensions: {sorted(ALLOWED_ARTIFACT_EXTENSIONS)}"
            )
        if self.is_executed is not False:
            raise ValueError("is_executed MUST be False in numerical simulation stage")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_filename": self.artifact_filename,
            "checksum_sha256": self.checksum_sha256,
            "size_bytes": self.size_bytes,
            "is_executed": self.is_executed,
            "execution_status": self.execution_status,
            "notes": self.notes,
        }

    @classmethod
    def create_from_content(cls, filename: str, content: str | bytes) -> "ReleaseArtifact":
        """Compute SHA-256 and create metadata from in-memory content."""
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        sha = hashlib.sha256(raw_bytes).hexdigest()
        return cls(
            artifact_filename=filename,
            checksum_sha256=sha,
            size_bytes=len(raw_bytes),
            is_executed=False,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReleaseArtifact":
        return cls(
            artifact_filename=str(d["artifact_filename"]),
            checksum_sha256=str(d["checksum_sha256"]),
            size_bytes=int(d["size_bytes"]),
            is_executed=bool(d.get("is_executed", False)),
            execution_status=str(d.get("execution_status", "UNEXECUTED_SIMULATION_PROFILE")),
            notes=str(d.get("notes", "Uploaded source artifact stored for simulation profiling only; host execution is disabled.")),
        )


@dataclass
class Release:
    """Versioned release bundle uniting metadata, unexecuted artifact, and simulation profile."""
    release_id: str
    version_tag: str
    behavior_profile: BehaviorProfile
    service_id: str = "default-service"
    schema_version: str = "v1.0"
    rollout_state: RolloutState = RolloutState.CREATED
    artifact: ReleaseArtifact | None = None
    created_at_tick: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.release_id:
            raise ValueError("release_id cannot be empty")
        if not self.version_tag:
            raise ValueError("version_tag cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "version_tag": self.version_tag,
            "service_id": self.service_id,
            "schema_version": self.schema_version,
            "rollout_state": self.rollout_state.value,
            "behavior_profile": self.behavior_profile.to_dict(),
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "created_at_tick": self.created_at_tick,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Release":
        art = ReleaseArtifact.from_dict(d["artifact"]) if d.get("artifact") else None
        prof = BehaviorProfile.from_dict(d["behavior_profile"])
        state = RolloutState(d["rollout_state"]) if d.get("rollout_state") else RolloutState.CREATED
        return cls(
            release_id=str(d["release_id"]),
            version_tag=str(d["version_tag"]),
            behavior_profile=prof,
            service_id=str(d.get("service_id", "default-service")),
            schema_version=str(d.get("schema_version", "v1.0")),
            rollout_state=state,
            artifact=art,
            created_at_tick=int(d.get("created_at_tick", 0)),
            metadata=dict(d.get("metadata", {})),
        )


class ReleaseRegistry:
    """In-memory thread-safe registry of versioned software releases."""

    def __init__(self) -> None:
        self._releases: dict[str, Release] = {}
        # Register standard baseline release by default
        self.register(
            Release(
                release_id="rel-baseline-1.0",
                version_tag="v1.0.0-baseline",
                behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.CLEAN),
                artifact=ReleaseArtifact.create_from_content(
                    filename="server_baseline.py",
                    content="# Standard production baseline build\nVERSION = 'v1.0.0-baseline'\n",
                ),
                created_at_tick=0,
                metadata={"description": "Standard production baseline release"},
            )
        )

    def register(self, release: Release) -> None:
        if release.release_id in self._releases:
            raise ValueError(f"Release {release.release_id!r} is already registered")
        self._releases[release.release_id] = release

    def get(self, release_id: str) -> Release:
        if release_id not in self._releases:
            raise KeyError(f"Release {release_id!r} not found in registry")
        return self._releases[release_id]

    def get_by_version(self, version_tag: str) -> Release | None:
        for rel in self._releases.values():
            if rel.version_tag == version_tag:
                return rel
        return None

    def list_releases(self) -> list[Release]:
        return sorted(self._releases.values(), key=lambda r: (r.created_at_tick, r.release_id))

    def clear(self) -> None:
        self._releases.clear()

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.list_releases()]
