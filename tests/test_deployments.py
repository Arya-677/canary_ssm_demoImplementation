"""Unit tests for Release Registry, Behavior Profiles, and Deployment Lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from canary_ssm.deployments.allocation import (
    AllocationValidationResult,
    generate_default_allocation,
    validate_canary_allocation,
)
from canary_ssm.deployments.manager import DeploymentManager
from canary_ssm.deployments.models import (
    ALLOWED_ARTIFACT_EXTENSIONS,
    MAX_ARTIFACT_SIZE_BYTES,
    BehaviorProfile,
    BehaviorProfileType,
    Release,
    ReleaseArtifact,
    ReleaseRegistry,
)
from canary_ssm.deployments.samples import get_sample_manifest, write_sample_manifests
from canary_ssm.world.models import create_default_fleet
from canary_ssm.world.world import VirtualWorld


def test_release_artifact_unexecuted_metadata():
    """Verify artifact hashing, size checks, extension checks, and unexecuted guarantees."""
    content = b"print('Hello world!')\n"
    artifact = ReleaseArtifact.create_from_content("test_service.py", content)

    assert artifact.artifact_filename == "test_service.py"
    assert artifact.size_bytes == len(content)
    assert artifact.is_executed is False
    assert artifact.execution_status == "UNEXECUTED_SIMULATION_PROFILE"
    assert len(artifact.checksum_sha256) == 64

    # Disallowed extension rejection
    with pytest.raises(ValueError, match="extension not supported"):
        ReleaseArtifact.create_from_content("malicious.exe", content)

    # Size limit rejection
    with pytest.raises(ValueError, match="exceeds limit"):
        ReleaseArtifact(
            artifact_filename="oversized.zip",
            checksum_sha256="abc",
            size_bytes=MAX_ARTIFACT_SIZE_BYTES + 1,
        )

    # Execution flag rejection
    with pytest.raises(ValueError, match="is_executed MUST be False"):
        ReleaseArtifact(
            artifact_filename="test.py",
            checksum_sha256="abc",
            size_bytes=100,
            is_executed=True,
        )


def test_behavior_profile_serialization():
    """Verify serialization and deserialization of all behavior profile types."""
    profiles = [
        BehaviorProfile(profile_type=BehaviorProfileType.CLEAN),
        BehaviorProfile(profile_type=BehaviorProfileType.MEMORY_LEAK, severity=25.0, duration=90),
        BehaviorProfile(profile_type=BehaviorProfileType.CPU_REGRESSION, severity=0.40, susceptible_class_id=1),
        BehaviorProfile(profile_type=BehaviorProfileType.ERROR_REGRESSION, severity=0.05),
        BehaviorProfile(profile_type=BehaviorProfileType.LATENCY_REGRESSION, severity=0.20),
    ]

    for prof in profiles:
        d = prof.to_dict()
        restored = BehaviorProfile.from_dict(d)
        assert restored.profile_type == prof.profile_type
        assert restored.severity == prof.severity
        assert restored.duration == prof.duration
        assert restored.susceptible_class_id == prof.susceptible_class_id


def test_release_registry_operations():
    """Verify release registry stores, lists, retrieves, and rejects duplicate releases."""
    reg = ReleaseRegistry()
    assert len(reg.list_releases()) == 1  # Default baseline release

    # Add clean release
    rel1 = Release(
        release_id="rel-v1.1",
        version_tag="v1.1.0",
        behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.CLEAN),
    )
    reg.register(rel1)
    assert reg.get("rel-v1.1") == rel1
    assert reg.get_by_version("v1.1.0") == rel1

    # Duplicate rejection
    with pytest.raises(ValueError, match="already registered"):
        reg.register(rel1)

    # Missing release
    with pytest.raises(KeyError, match="not found"):
        reg.get("non-existent")


def test_canary_allocation_validation_and_identifiability():
    """Verify identifiability guards: reject pure-canary racks and pure-canary classes."""
    fleet = create_default_fleet(n_racks=4, servers_per_rack=6, n_classes=2)

    # 1. Valid default allocation: 1 canary per rack
    default_canaries = generate_default_allocation(fleet)
    assert len(default_canaries) == 4
    val_default = validate_canary_allocation(fleet, default_canaries)
    assert val_default.is_valid is True
    assert len(val_default.issues) == 0
    assert len(val_default.control_server_ids) == 20

    # 2. Empty allocation rejection
    val_empty = validate_canary_allocation(fleet, [])
    assert val_empty.is_valid is False
    assert any("empty" in iss for iss in val_empty.issues)

    # 3. Unknown server rejection
    val_unknown = validate_canary_allocation(fleet, ["srv-unknown-999"])
    assert val_unknown.is_valid is False
    assert any("Unknown" in iss for iss in val_unknown.issues)

    # 4. Pure-canary rack rejection (confounded)
    rack0_servers = [s.server_id for s in fleet.racks["rack-0"].servers.values()]
    val_pure_rack = validate_canary_allocation(fleet, rack0_servers)
    assert val_pure_rack.is_valid is False
    assert any("CONFUSED_RACK_CONFOUNDING" in iss for iss in val_pure_rack.issues)

    # 5. Pure-canary class rejection (confounded)
    class0_servers = [s.server_id for s in fleet.list_servers() if s.class_id == 0]
    val_pure_class = validate_canary_allocation(fleet, class0_servers)
    assert val_pure_class.is_valid is False
    assert any("CONFUSED_CLASS_CONFOUNDING" in iss for iss in val_pure_class.issues)


def test_deployment_lifecycle_and_two_version_coexistence():
    """Verify deploying a release updates versions, creates faults, and coexists with controls."""
    world = VirtualWorld.create_default(n_racks=4, servers_per_rack=6, seed=42)
    mgr = DeploymentManager()

    # Pre-exposure: all servers run baseline
    for srv in world.fleet.list_servers():
        assert srv.installed_version == "v1.0.0-baseline"

    # Create leak release
    leak_release = mgr.create_release(
        release_id="rel-v1.2-leak",
        version_tag="v1.2.0-leak",
        behavior_profile=BehaviorProfile(
            profile_type=BehaviorProfileType.MEMORY_LEAK,
            severity=40.0,
            duration=60,
        ),
        artifact_filename="service_leak.py",
        artifact_content="# Simulated memory leak\n",
    )

    canaries = ["srv-r0-s0", "srv-r1-s3", "srv-r2-s0", "srv-r3-s3"]
    outcome = mgr.deploy_canary(world, release_id="rel-v1.2-leak", canary_ids=canaries)
    assert outcome["status"] == "DEPLOYED"

    # Check two versions coexist
    for srv in world.fleet.list_servers():
        if srv.server_id in canaries:
            assert srv.installed_version == "v1.2.0-leak"
        else:
            assert srv.installed_version == "v1.0.0-baseline"

    # Run for 20 ticks: only canaries leak memory
    world.step(20)

    for sid in canaries:
        srv = world.fleet.get_server(sid)
        # Server memory must have accumulated from leak
        assert srv.current_state.memory_mb > srv.base_memory_mb + 200.0

    # Control servers must NOT have leaked memory
    for srv in world.fleet.list_servers():
        if srv.server_id not in canaries:
            assert world.fault_engine._server_memory_leaks_mb.get(srv.server_id, 0.0) == 0.0


def test_rollback_lifecycle_with_and_without_restart():
    """Verify rollback semantics: restart_process clears resident memory; non-restart preserves heap."""
    # Scenario A: Rollback WITH process restart
    world_a = VirtualWorld.create_default(n_racks=4, servers_per_rack=6, seed=42)
    mgr_a = DeploymentManager()

    mgr_a.create_release(
        release_id="rel-leak-a",
        version_tag="v1.2.0-leak",
        behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.MEMORY_LEAK, severity=50.0),
    )
    canaries = ["srv-r0-s0", "srv-r1-s0"]
    mgr_a.deploy_canary(world_a, "rel-leak-a", canaries)
    world_a.step(15)

    srv0_a = world_a.fleet.get_server("srv-r0-s0")
    assert srv0_a.current_state.memory_mb > srv0_a.base_memory_mb + 200.0

    # Rollback WITH restart -> clears memory
    rb_a = mgr_a.rollback_canary(world_a, "rel-leak-a", restart_process=True)
    assert rb_a["memory_cleared"] is True
    assert srv0_a.installed_version == "v1.0.0-baseline"
    assert srv0_a.current_state.memory_mb == srv0_a.base_memory_mb

    # Scenario B: Rollback WITHOUT process restart
    world_b = VirtualWorld.create_default(n_racks=4, servers_per_rack=6, seed=42)
    mgr_b = DeploymentManager()

    mgr_b.create_release(
        release_id="rel-leak-b",
        version_tag="v1.2.0-leak",
        behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.MEMORY_LEAK, severity=50.0),
    )
    mgr_b.deploy_canary(world_b, "rel-leak-b", canaries)
    world_b.step(15)

    srv0_b = world_b.fleet.get_server("srv-r0-s0")
    mem_before_rb = srv0_b.current_state.memory_mb
    assert mem_before_rb > srv0_b.base_memory_mb + 200.0

    # Rollback WITHOUT restart -> version reverts, but accumulated resident memory persists
    rb_b = mgr_b.rollback_canary(world_b, "rel-leak-b", restart_process=False)
    assert rb_b["memory_cleared"] is False
    assert srv0_b.installed_version == "v1.0.0-baseline"
    assert srv0_b.current_state.memory_mb == mem_before_rb  # Unchanged!


def test_command_id_idempotency():
    """Verify commands with the same command_id are strictly idempotent."""
    world = VirtualWorld.create_default(seed=42)
    mgr = DeploymentManager()

    # Create release twice with same command_id
    r1 = mgr.create_release(
        release_id="rel-idem",
        version_tag="v1.9.0",
        behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.CLEAN),
        command_id="cmd-create-123",
    )
    r2 = mgr.create_release(
        release_id="rel-idem",
        version_tag="v1.9.0",
        behavior_profile=BehaviorProfile(profile_type=BehaviorProfileType.CLEAN),
        command_id="cmd-create-123",
    )
    assert r1.release_id == r2.release_id
    assert len(mgr.deployment_history) == 1

    # Deploy twice with same command_id
    d1 = mgr.deploy_canary(world, "rel-idem", command_id="cmd-deploy-123")
    d2 = mgr.deploy_canary(world, "rel-idem", command_id="cmd-deploy-123")
    assert d1 == d2
    assert len(mgr.deployment_history) == 2


def test_sample_manifests(tmp_path: Path):
    """Verify declarative sample manifests write to disk, parse correctly, and can be deployed."""
    paths = write_sample_manifests(tmp_path)
    assert len(paths) == 5

    world = VirtualWorld.create_default(seed=42)
    mgr = DeploymentManager()

    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        art = data.get("artifact", {})
        rel = mgr.create_release(
            release_id=data["release_id"],
            version_tag=data["version_tag"],
            behavior_profile=data["behavior_profile"],
            artifact_filename=art.get("artifact_filename"),
            artifact_content=art.get("content_preview"),
        )
        assert rel.behavior_profile.profile_type.value == data["behavior_profile"]["profile_type"]
        assert rel.artifact is not None
        assert rel.artifact.is_executed is False
