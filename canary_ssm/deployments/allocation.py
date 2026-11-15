"""Canary Allocation Validation and Default Topology Placement.

Enforces:
- Coexistence of canary and baseline controls within every represented rack and compatibility group.
- Strict rejection of confounded allocations (pure-canary racks or pure-canary classes).
- Default allocation of one canary per rack with matched same-rack baseline controls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from canary_ssm.world.models import Fleet, Rack, Server


@dataclass(frozen=True)
class AllocationValidationResult:
    """Outcome of validating a candidate canary allocation."""
    is_valid: bool
    canary_server_ids: tuple[str, ...]
    control_server_ids: tuple[str, ...]
    issues: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    rack_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)
    class_breakdown: dict[int, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_canaries": len(self.canary_server_ids),
            "total_controls": len(self.control_server_ids),
            "canary_server_ids": list(self.canary_server_ids),
            "control_server_ids": list(self.control_server_ids),
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "rack_breakdown": dict(self.rack_breakdown),
            "class_breakdown": {str(k): dict(v) for k, v in self.class_breakdown.items()},
        }


def validate_canary_allocation(fleet: Fleet, canary_server_ids: list[str]) -> AllocationValidationResult:
    """Validate whether candidate canary server IDs satisfy identifiability and control overlap rules.

    Rejection Rules (BLOCKING):
        1. No canaries allocated (empty set).
        2. Unknown server IDs not in fleet.
        3. All servers in fleet allocated as canaries (zero controls).
        4. Pure-canary rack: An entire rack running only canaries with 0 controls.
           Confounded: Rack infrastructure faults cannot be distinguished from release faults.
        5. Pure-canary class: An entire hardware class running only canaries with 0 controls.
           Confounded: Hardware class differences cannot be separated from release effects.

    Warning Rules (NON-BLOCKING):
        - Represented rack with fewer than 2 same-rack controls (marginal statistical power).
        - Represented class with fewer than 2 same-class controls.
    """
    issues: list[str] = []
    warnings: list[str] = []

    all_server_ids = set(fleet.list_server_ids())
    canary_set = set(canary_server_ids)

    # 1. Non-empty check
    if not canary_set:
        issues.append("Allocation is empty: At least one canary server must be specified.")
        return AllocationValidationResult(
            is_valid=False,
            canary_server_ids=(),
            control_server_ids=tuple(sorted(all_server_ids)),
            issues=tuple(issues),
        )

    # 2. Unknown servers check
    unknown = canary_set - all_server_ids
    if unknown:
        issues.append(f"Unknown server IDs in allocation not found in fleet: {sorted(unknown)}")

    # 3. All servers canary check
    control_set = all_server_ids - canary_set
    if not control_set:
        issues.append("Confounded allocation: All servers in the fleet are allocated as canaries, leaving zero controls.")

    # 4. Rack Breakdown & Identifiability Guard
    rack_breakdown: dict[str, dict[str, int]] = {}
    for rack in fleet.list_racks():
        rid = rack.rack_id
        rack_servers = set(rack.servers.keys())
        r_canaries = rack_servers & canary_set
        r_controls = rack_servers - canary_set
        rack_breakdown[rid] = {
            "canaries": len(r_canaries),
            "controls": len(r_controls),
            "total": len(rack_servers),
        }

        # Check pure-canary rack confounding
        if r_canaries and len(r_controls) == 0:
            issues.append(
                f"CONFUSED_RACK_CONFOUNDING: Rack {rid!r} has {len(r_canaries)} canaries and 0 baseline controls. "
                f"Infrastructure rack variation and release effect are mathematically indistinguishable."
            )
        elif r_canaries and len(r_controls) < 2:
            warnings.append(
                f"Rack {rid!r} has only {len(r_controls)} control host(s); recommendation is >= 2 same-rack controls."
            )

    # 5. Compatibility Class Breakdown & Identifiability Guard
    class_breakdown: dict[int, dict[str, int]] = {}
    classes_present = set(s.class_id for s in fleet.list_servers())
    for cid in sorted(classes_present):
        cls_servers = set(s.server_id for s in fleet.list_servers() if s.class_id == cid)
        c_canaries = cls_servers & canary_set
        c_controls = cls_servers - canary_set
        class_breakdown[cid] = {
            "canaries": len(c_canaries),
            "controls": len(c_controls),
            "total": len(cls_servers),
        }

        # Check pure-canary class confounding
        if c_canaries and len(c_controls) == 0:
            issues.append(
                f"CONFUSED_CLASS_CONFOUNDING: Class {cid} has {len(c_canaries)} canaries and 0 baseline controls. "
                f"Hardware class baseline differences cannot be separated from release effects."
            )
        elif c_canaries and len(c_controls) < 2:
            warnings.append(
                f"Class {cid} has only {len(c_controls)} control host(s); recommendation is >= 2 controls."
            )

    is_valid = (len(issues) == 0)
    return AllocationValidationResult(
        is_valid=is_valid,
        canary_server_ids=tuple(sorted(canary_set & all_server_ids)),
        control_server_ids=tuple(sorted(control_set)),
        issues=tuple(issues),
        warnings=tuple(warnings),
        rack_breakdown=rack_breakdown,
        class_breakdown=class_breakdown,
    )


def generate_default_allocation(fleet: Fleet) -> list[str]:
    """Generates the recommended default allocation: exactly one canary per rack.

    Selects one server per rack, alternating hardware classes across racks to guarantee
    balanced control overlap across all represented racks and classes.
    For default 4 racks of 6 servers:
    - 4 canaries (1 per rack)
    - 20 controls (5 per rack)
    - 2 canaries in Class 0, 2 canaries in Class 1
    """
    canary_ids: list[str] = []
    racks = fleet.list_racks()

    for r_idx, rack in enumerate(racks):
        # Alternate target class across racks for balance
        target_class = r_idx % 2
        # Find first server in rack with matching class
        candidate = None
        for srv in rack.servers.values():
            if srv.class_id == target_class:
                candidate = srv.server_id
                break
        if candidate is None and rack.servers:
            # Fallback to first server in rack
            candidate = next(iter(rack.servers.keys()))

        if candidate:
            canary_ids.append(candidate)

    return sorted(canary_ids)
