"""Role and Seed Separation Architecture (Prompt 11 / Change Plan WP-A4).

Enforces strict separation across experimental data roles:
- `smoke`: Sanity checks and integration smoke tests.
- `dev`: Nuisance parameter estimation and model candidate selection.
- `calibration`: Pure null rollouts for threshold estimation and policy replay.
- `null_validation`: Independent unseen null rollouts for audit and validity testing.
- `test`: Unseen final test scenarios across harm and matched null controls.

Every role operates within a disjoint, non-overlapping seed block.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DataRole(str, Enum):
    SMOKE = "smoke"
    DEV = "dev"
    CALIBRATION = "calibration"
    NULL_VALIDATION = "null_validation"
    TEST = "test"


@dataclass(frozen=True)
class RoleSeedBundle:
    """Disjoint seed allocation and operational rules for a data role."""
    role: DataRole
    seed_base: int
    seed_block_size: int
    max_rollouts: int
    allowed_harm: bool
    purpose: str

    @property
    def seed_max(self) -> int:
        return self.seed_base + self.seed_block_size - 1

    def contains_seed(self, seed: int) -> bool:
        return self.seed_base <= seed <= self.seed_max

    def get_seed(self, index: int, is_harm: bool = False) -> int:
        """Derive deterministic seed for rollout index within the role's block."""
        stride = 2 if self.allowed_harm else 1
        offset = index * stride + (1 if is_harm else 0)
        seed = self.seed_base + offset
        if seed > self.seed_max:
            raise OverflowError(
                f"Requested rollout index {index} (seed {seed}) exceeds block maximum {self.seed_max} for role '{self.role.value}'"
            )
        return seed


# Strict disjoint allocation table (1,000,000 integer block stride)
ROLE_SEED_REGISTRY: dict[DataRole, RoleSeedBundle] = {
    DataRole.SMOKE: RoleSeedBundle(
        role=DataRole.SMOKE,
        seed_base=10_000,
        seed_block_size=100_000,
        max_rollouts=1_000,
        allowed_harm=True,
        purpose="Small smoke verification and fast integration tests.",
    ),
    DataRole.DEV: RoleSeedBundle(
        role=DataRole.DEV,
        seed_base=1_000_000,
        seed_block_size=1_000_000,
        max_rollouts=50_000,
        allowed_harm=True,
        purpose="Pre-period parameter fitting, nuisance estimation, and model candidate selection.",
    ),
    DataRole.CALIBRATION: RoleSeedBundle(
        role=DataRole.CALIBRATION,
        seed_base=2_000_000,
        seed_block_size=1_000_000,
        max_rollouts=50_000,
        allowed_harm=False,
        purpose="Strictly pure null rollouts for order-statistic threshold calibration and policy replay.",
    ),
    DataRole.NULL_VALIDATION: RoleSeedBundle(
        role=DataRole.NULL_VALIDATION,
        seed_base=3_000_000,
        seed_block_size=1_000_000,
        max_rollouts=50_000,
        allowed_harm=False,
        purpose="Independent unseen null audit for exact Beta-Binomial validity and false alert rate control.",
    ),
    DataRole.TEST: RoleSeedBundle(
        role=DataRole.TEST,
        seed_base=4_000_000,
        seed_block_size=1_000_000,
        max_rollouts=50_000,
        allowed_harm=True,
        purpose="Final unseen benchmark scenarios (13 conditions across paired null and harm).",
    ),
}


def get_seed_bundle(role: str | DataRole) -> RoleSeedBundle:
    """Retrieve seed bundle by string or DataRole enum."""
    r = DataRole(role.lower()) if isinstance(role, str) else role
    if r not in ROLE_SEED_REGISTRY:
        raise KeyError(f"Unknown data role: {role}. Allowed: {[e.value for e in DataRole]}")
    return ROLE_SEED_REGISTRY[r]


def get_all_role_bundles() -> dict[str, RoleSeedBundle]:
    return {r.value: b for r, b in ROLE_SEED_REGISTRY.items()}


def verify_seed_separation(bundles: dict[str, RoleSeedBundle] | None = None) -> bool:
    """Assert mathematically that no two role seed intervals overlap."""
    b_dict = bundles or get_all_role_bundles()
    intervals: list[tuple[int, int, str]] = []
    for name, b in b_dict.items():
        intervals.append((b.seed_base, b.seed_max, name))

    intervals.sort(key=lambda x: x[0])
    for i in range(len(intervals) - 1):
        cur_start, cur_end, cur_name = intervals[i]
        next_start, next_end, next_name = intervals[i + 1]
        if cur_end >= next_start:
            raise AssertionError(
                f"Seed collision detected between role '{cur_name}' [{cur_start}, {cur_end}] "
                f"and role '{next_name}' [{next_start}, {next_end}]!"
            )
    return True


@dataclass
class FrozenModelParameters:
    """Declared, immutable model and nuisance parameters frozen before calibration."""
    model_id: str = "MODEL-HSSM-V1"
    version: str = "1.0.0"
    nuisance_phi_e: float = 0.60
    nuisance_sd_xi: float = 0.01
    hier_rho_g: float = 0.95
    hier_rho_h: float = 0.95
    hier_sd_g: float = 0.001
    hier_sd_h: float = 0.001
    hier_prior_sd: float = 0.01
    cusum_k: float = 0.25
    topk_K: int = 3
    ewma_alpha: float = 0.20
    # Declared separate metric boundaries
    boundary_latency_log: float = 0.0198026  # log(1.02)
    boundary_memory_drift_mb_per_min: float = 0.50  # kappa_M
    boundary_memory_persistence_ticks: int = 15     # H
    boundary_cpu_saturation: float = 0.85
    boundary_error_rate: float = 0.05
    # Declared policy structure
    policy_id: str = "POLICY-SIDAK-0.05"
    target_fwer: float = 0.05
    epistemic_disclaimer: str = (
        "Observational statistical evidence consistent with release regression; "
        "not proof of a source code bug or causal certainty."
    )

    def compute_sha256(self) -> str:
        """Deterministic cryptographic hash of frozen parameters."""
        data = asdict(self)
        s = json.dumps(data, sort_keys=True)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sha256"] = self.compute_sha256()
        return d

    def save_frozen_artifact(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return p
