"""Deployment Manager: Release Registry and Deployment Lifecycle Coordinator.

Handles:
- Creating versioned releases with unexecuted source artifacts and behavior profiles.
- Validating canary allocations with identifiability checks.
- Deploying releases to validated canary hosts.
- Rollback with explicit process restart / memory clearing semantics.
- Idempotent command execution via command_id tracking.
"""
from __future__ import annotations

import copy
import uuid
from typing import Any

from canary_ssm.faults.models import FaultCategory, FaultDefinition, FaultScope, FaultType
from canary_ssm.world import VirtualWorld
from canary_ssm.world.models import Fleet, Server
from .allocation import AllocationValidationResult, generate_default_allocation, validate_canary_allocation
from .models import (
    BehaviorProfile,
    BehaviorProfileType,
    Release,
    ReleaseArtifact,
    ReleaseRegistry,
    RolloutState,
    RolloutTransition,
)


class DeploymentManager:
    """Manages the full lifecycle of versioned releases and canary deployments."""

    def __init__(self, registry: ReleaseRegistry | None = None) -> None:
        self.registry = registry or ReleaseRegistry()
        self.executed_commands: dict[str, dict[str, Any]] = {}
        self.deployment_history: list[dict[str, Any]] = []
        self.server_baseline_placement: dict[str, str] = {}
        self.transitions: list[RolloutTransition] = []

    def create_release(
        self,
        release_id: str,
        version_tag: str,
        behavior_profile: BehaviorProfile | dict[str, Any],
        artifact_filename: str | None = None,
        artifact_content: str | bytes | None = None,
        created_at_tick: int = 0,
        metadata: dict[str, Any] | None = None,
        command_id: str | None = None,
    ) -> Release:
        """Create and register a versioned release bundle.

        Strict Contract:
            Uploaded artifact contents are hashed and labeled unexecuted.
            The simulation behavior is dictated exclusively by behavior_profile.
        """
        cid = command_id or f"cmd-create-{release_id}"
        if cid in self.executed_commands:
            return self.registry.get(release_id)

        # Parse behavior profile
        if isinstance(behavior_profile, dict):
            prof = BehaviorProfile.from_dict(behavior_profile)
        else:
            prof = behavior_profile

        # Build artifact metadata if content provided
        art = None
        if artifact_filename and artifact_content is not None:
            art = ReleaseArtifact.create_from_content(
                filename=artifact_filename,
                content=artifact_content,
            )

        release = Release(
            release_id=release_id,
            version_tag=version_tag,
            behavior_profile=prof,
            artifact=art,
            created_at_tick=created_at_tick,
            metadata=dict(metadata or {}),
        )
        self.registry.register(release)

        record = {
            "command_id": cid,
            "action": "CREATE_RELEASE",
            "release_id": release_id,
            "version_tag": version_tag,
            "profile": prof.profile_type.value,
            "artifact_hash": art.checksum_sha256 if art else None,
            "tick": created_at_tick,
        }
        self.executed_commands[cid] = record
        self.deployment_history.append(record)
        return release

    def validate_allocation(self, fleet: Fleet, canary_ids: list[str]) -> AllocationValidationResult:
        """Validate candidate canary allocation against confounding and identifiability rules."""
        return validate_canary_allocation(fleet, canary_ids)

    def deploy_canary(
        self,
        world: VirtualWorld,
        release_id: str,
        canary_ids: list[str] | None = None,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        """Deploy a versioned candidate release to canary servers.

        Actions:
            1. Enforces idempotency via command_id.
            2. Validates canary allocation for identifiability.
            3. Updates canary servers to installed_version = release.version_tag.
            4. If behavior profile specifies regressions, registers matching FaultDefinition.
        """
        cid = command_id or f"cmd-deploy-{release_id}-{world.clock.tick}-{len(self.deployment_history)}"
        if cid in self.executed_commands:
            return dict(self.executed_commands[cid])

        release = self.registry.get(release_id)
        old_state = release.rollout_state
        if old_state not in (RolloutState.CREATED, RolloutState.BASELINING, RolloutState.PAUSED, RolloutState.ROLLED_BACK):
            raise ValueError(f"Cannot deploy release {release_id} from state {old_state.value}")

        active_canaries = canary_ids if canary_ids is not None else generate_default_allocation(world.fleet)

        # Validate allocation
        val = self.validate_allocation(world.fleet, active_canaries)
        if not val.is_valid:
            raise ValueError(f"Canary allocation rejected: {'; '.join(val.issues)}")

        current_tick = world.clock.tick

        # Snapshot baseline server placement before updating version
        for sid in active_canaries:
            if sid not in self.server_baseline_placement:
                srv = world.fleet.get_server(sid)
                self.server_baseline_placement[sid] = srv.installed_version

        # Deploy software version to canary servers
        for sid in active_canaries:
            world.set_server_version(sid, release.version_tag)

        # Update rollout state & record transition
        release.rollout_state = RolloutState.CANARY
        self.transitions.append(
            RolloutTransition(
                release_id=release_id,
                from_state=old_state,
                to_state=RolloutState.CANARY,
                tick=current_tick,
                reason="Deploy canary to target servers",
            )
        )

        # Wire behavior profile into world's fault engine if regression declared
        prof = release.behavior_profile
        injected_fault_id = None

        if prof.profile_type != BehaviorProfileType.CLEAN:
            fault_type_map = {
                BehaviorProfileType.MEMORY_LEAK: FaultType.PROCESS_MEMORY_LEAK,
                BehaviorProfileType.CPU_REGRESSION: FaultType.CPU_SATURATION,
                BehaviorProfileType.ERROR_REGRESSION: FaultType.ERROR_REGRESSION,
                BehaviorProfileType.LATENCY_REGRESSION: FaultType.RELEASE_LATENCY_REGRESSION,
            }
            ft = fault_type_map[prof.profile_type]
            injected_fault_id = f"fault-{release.release_id}-{prof.profile_type.value.lower()}"

            fault_def = FaultDefinition(
                fault_id=injected_fault_id,
                fault_type=ft,
                scope=FaultScope.SERVER,
                target_id=release.release_id,
                onset_tick=current_tick,
                duration=prof.duration,
                severity=prof.severity,
                target_version=release.version_tag,
                susceptible_class_id=prof.susceptible_class_id,
                parameters={"target_server_ids": list(active_canaries), **prof.parameters},
            )
            world.inject_fault(fault_def)

        outcome = {
            "command_id": cid,
            "action": "DEPLOY_CANARY",
            "release_id": release_id,
            "version_tag": release.version_tag,
            "canary_servers": list(active_canaries),
            "control_servers": list(val.control_server_ids),
            "tick": current_tick,
            "injected_fault_id": injected_fault_id,
            "status": "DEPLOYED",
            "rollout_state": release.rollout_state.value,
        }
        self.executed_commands[cid] = outcome
        self.deployment_history.append(outcome)
        return outcome

    def pause_canary(
        self,
        world: VirtualWorld | str | None = None,
        release_id: str = "",
        reason: str = "Operator manual pause of rollout",
        command_id: str | None = None,
        current_tick: int | None = None,
    ) -> dict[str, Any]:
        """Manually pause an active canary rollout without rolling back."""
        if isinstance(world, str):
            release_id = world
            world = None
        tick = current_tick if current_tick is not None else (world.clock.tick if world is not None else 0)
        cid = command_id or f"cmd-pause-{release_id}-{tick}-{len(self.deployment_history)}"
        if cid in self.executed_commands:
            return dict(self.executed_commands[cid])

        release = self.registry.get(release_id)
        if release.rollout_state != RolloutState.CANARY:
            raise ValueError(f"Cannot pause release {release_id} from state {release.rollout_state.value}; must be in CANARY state")

        old_state = release.rollout_state
        release.rollout_state = RolloutState.PAUSED

        self.transitions.append(
            RolloutTransition(
                release_id=release_id,
                from_state=old_state,
                to_state=RolloutState.PAUSED,
                tick=tick,
                reason=reason,
            )
        )
        outcome = {
            "command_id": cid,
            "action": "PAUSE_CANARY",
            "release_id": release_id,
            "version_tag": release.version_tag,
            "tick": tick,
            "status": "PAUSED",
            "rollout_state": release.rollout_state.value,
        }
        self.executed_commands[cid] = outcome
        self.deployment_history.append(outcome)
        return outcome

    def promote_canary(
        self,
        world: VirtualWorld,
        release_id: str,
        reason: str = "Operator manual promotion of canary rollout",
        command_id: str | None = None,
    ) -> dict[str, Any]:
        """Promote candidate release to 100% of fleet, terminating canary evaluation epoch."""
        cid = command_id or f"cmd-promote-{release_id}-{world.clock.tick}-{len(self.deployment_history)}"
        if cid in self.executed_commands:
            return dict(self.executed_commands[cid])

        release = self.registry.get(release_id)
        if release.rollout_state not in (RolloutState.CANARY, RolloutState.PAUSED):
            raise ValueError(f"Cannot promote release {release_id} from state {release.rollout_state.value}")

        old_state = release.rollout_state
        current_tick = world.clock.tick
        promoted_servers: list[str] = []

        # Promote all servers to candidate version
        for srv in world.fleet.list_servers():
            world.set_server_version(srv.server_id, release.version_tag)
            promoted_servers.append(srv.server_id)

        release.rollout_state = RolloutState.PROMOTED
        self.transitions.append(
            RolloutTransition(
                release_id=release_id,
                from_state=old_state,
                to_state=RolloutState.PROMOTED,
                tick=current_tick,
                reason=reason,
            )
        )
        outcome = {
            "command_id": cid,
            "action": "PROMOTE_CANARY",
            "release_id": release_id,
            "version_tag": release.version_tag,
            "promoted_servers": promoted_servers,
            "tick": current_tick,
            "status": "PROMOTED",
            "rollout_state": release.rollout_state.value,
        }
        self.executed_commands[cid] = outcome
        self.deployment_history.append(outcome)
        return outcome

    def rollback_canary(
        self,
        world: VirtualWorld,
        release_id: str,
        baseline_version: str = "v1.0.0-baseline",
        restart_process: bool = True,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        """Roll back canary servers running a candidate release.

        Semantics:
            - Reverts installed_version to pre-deployment baseline version.
            - Terminates any active or scheduled faults targeting release_id.
            - If restart_process == True:
                Models a full process restart: server memory resets to baseline,
                clearing accumulated memory leaks.
            - If restart_process == False:
                Models hot version tag revert without restarting process:
                leak progression stops, but current resident memory is NOT cleared.
        """
        cid = command_id or f"cmd-rollback-{release_id}-{world.clock.tick}-{len(self.deployment_history)}"
        if cid in self.executed_commands:
            return dict(self.executed_commands[cid])

        release = self.registry.get(release_id)
        if release.rollout_state not in (RolloutState.CANARY, RolloutState.PAUSED):
            raise ValueError(f"Cannot rollback release in state {release.rollout_state.value}")
        current_tick = world.clock.tick
        rolled_back_servers: list[str] = []

        for srv in world.fleet.list_servers():
            if srv.installed_version == release.version_tag:
                rolled_back_servers.append(srv.server_id)
                # Restore exact pre-deployment placement
                orig_ver = self.server_baseline_placement.get(srv.server_id, baseline_version)
                world.set_server_version(srv.server_id, orig_ver)

                if restart_process:
                    # Clean process restart resets process memory to nominal baseline
                    srv.current_state.memory_mb = srv.base_memory_mb
                    # Clear internal leak memory in fault engine
                    world.fault_engine._server_memory_leaks_mb[srv.server_id] = 0.0

        # Terminate any release-scoped faults immediately
        world.fault_engine.terminate_release_faults(release_id, current_tick)

        old_state = release.rollout_state
        release.rollout_state = RolloutState.ROLLED_BACK
        self.transitions.append(
            RolloutTransition(
                release_id=release_id,
                from_state=old_state,
                to_state=RolloutState.ROLLED_BACK,
                tick=current_tick,
                reason="Canary rollback to baseline placement",
            )
        )

        outcome = {
            "command_id": cid,
            "action": "ROLLBACK_CANARY",
            "release_id": release_id,
            "version_tag": release.version_tag,
            "baseline_version": baseline_version,
            "rolled_back_servers": rolled_back_servers,
            "restart_process": restart_process,
            "memory_cleared": bool(restart_process),
            "tick": current_tick,
            "status": "ROLLED_BACK",
            "rollout_state": release.rollout_state.value,
        }
        self.executed_commands[cid] = outcome
        self.deployment_history.append(outcome)
        return outcome
        self.deployment_history.append(outcome)
        return outcome
