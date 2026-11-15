"""Deterministic Windows-safe parallel runner, JSONL resume journal, and disk budget checks (WP-I2, WP-I6)."""
from __future__ import annotations

import json
import multiprocessing
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
U = TypeVar("U")

BLAS_ENV_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def default_workers() -> int:
    """Leave two hardware threads free on the CPU (WP-I2)."""
    return max(1, (os.cpu_count() or 1) - 2)


def resolve_workers(workers: int | None, n_items: int) -> int:
    """Resolve worker count: small batches (<20) avoid Windows spawn overhead when `workers is None`."""
    if n_items <= 1:
        return 1
    if workers is None:
        return 1 if n_items < 20 else default_workers()
    return max(1, min(int(workers), n_items))


def _worker_init() -> None:
    """Force single-threaded BLAS in each worker to prevent oversubscription."""
    for var in BLAS_ENV_VARS:
        os.environ[var] = "1"


def pmap(
    fn: Callable[[T], U],
    items: Iterable[T],
    workers: int | None = None,
    chunk: int = 1,
    desc: str | None = None,
    log: Callable[[str], None] | None = None,
) -> list[U]:
    """Deterministic parallel map returning outputs in exact input order.

    Uses Windows-safe `spawn` context, requires top-level picklable `fn`, sets single-thread BLAS
    variables before child import/init, and executes synchronously when `workers == 1`.
    """
    seq = list(items)
    if not seq:
        return []
    w = resolve_workers(workers, len(seq))
    if w <= 1:
        return [fn(x) for x in seq]
    if desc and log is not None:
        log(f"  [{desc}] running {len(seq)} tasks on {w} workers")
    saved = {k: os.environ.get(k) for k in BLAS_ENV_VARS}
    for k in BLAS_ENV_VARS:
        os.environ[k] = "1"
    try:
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=w, mp_context=ctx, initializer=_worker_init) as ex:
            return list(ex.map(fn, seq, chunksize=max(1, int(chunk))))
    finally:
        for k, prev in saved.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class ProgressJournal:
    """Append-only JSON-lines progress log supporting idempotent `--resume` (WP-I2)."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def completed_keys(self, key_field: str = "key") -> set[str]:
        if not self.path.exists():
            return set()
        done: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if key_field in rec:
                    done.add(str(rec[key_field]))
            except json.JSONDecodeError:
                continue
        return done

    def load_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


BYTES_PER_STORED_ROLLOUT = int(0.7 * 1024 * 1024)  # WP-I6: ~0.7 MB per rollout + truth


def check_disk_budget(
    target_path: Path | str,
    n_rollouts_to_store: int = 0,
    max_free_fraction: float = 0.70,
    max_used_fraction: float = 0.90,
) -> dict[str, float]:
    """Check free disk space and abort if current usage or estimated storage exceeds safe bounds (WP-I2/I6)."""
    p = Path(target_path)
    probe = p if p.exists() else p.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    du = shutil.disk_usage(probe)
    used_frac = (du.total - du.free) / du.total if du.total > 0 else 1.0
    est_bytes = int(max(0, n_rollouts_to_store) * BYTES_PER_STORED_ROLLOUT)
    free_frac = est_bytes / du.free if du.free > 0 else 1.0
    info = {
        "disk_free_bytes": int(du.free),
        "disk_total_bytes": int(du.total),
        "disk_used_fraction": float(used_frac),
        "estimated_write_bytes": est_bytes,
        "estimated_fraction_of_free": float(free_frac),
    }
    if used_frac >= max_used_fraction:
        raise RuntimeError(
            f"Disk critically full ({100 * used_frac:.1f}% used on {probe}); aborting run."
        )
    if n_rollouts_to_store > 0 and free_frac > max_free_fraction:
        raise RuntimeError(
            f"Estimated storage {est_bytes / 1e9:.2f} GB exceeds {int(100 * max_free_fraction)}% "
            f"of free disk space ({du.free / 1e9:.2f} GB) at {probe}; use --generate-on-the-fly."
        )
    return info
