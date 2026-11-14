"""Provenance and environment manifest builder (WP-A3).

Every pipeline stage and study can trace its outputs back to git commit + dirty flag,
configs/grids/candidate-table hashes, seed registry ranges, package versions, OS/CPU,
wall-clock times, fit failures, and lockfile hash.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import seeds


def find_git() -> str | None:
    """Locate git executable cleanly on Linux/macOS and Windows (including WinGet MinGit)."""
    exe = shutil.which("git")
    if exe:
        return exe
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        wg = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
        if wg.exists():
            for cand in wg.glob("Git.MinGit*/cmd/git.exe"):
                return str(cand)
        links = Path(local_app) / "Microsoft" / "WinGet" / "Links" / "git.exe"
        if links.exists():
            return str(links)
    for cand in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(cand).exists():
            return cand
    return None


def git_info(repo_dir: Path | str | None = None) -> dict[str, Any]:
    """Inspect HEAD commit, dirty state, branch, and exact tag in `repo_dir`."""
    git_exe = find_git()
    cwd = str(Path(repo_dir)) if repo_dir is not None else str(Path(__file__).resolve().parents[1])
    if not git_exe:
        return {"commit": None, "git_dirty": None, "branch": None, "tag": None, "git_available": False}

    def _run(args: list[str]) -> str | None:
        try:
            out = subprocess.check_output(
                [git_exe, *args], cwd=cwd, stderr=subprocess.DEVNULL, text=True
            )
            return out.strip()
        except Exception:
            return None

    head = _run(["rev-parse", "HEAD"])
    status = _run(["status", "--porcelain"])
    dirty = bool(status) if status is not None else None
    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    tag = _run(["describe", "--tags", "--exact-match", "HEAD"])
    commit = f"{head}-dirty" if (head and dirty) else ("dirty" if dirty else head)
    return {
        "commit": commit,
        "git_head": head,
        "git_dirty": dirty,
        "branch": branch,
        "tag": tag,
        "git_available": True,
    }


def sha256_file(path: Path | str | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _pkg_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def package_versions() -> dict[str, str | None]:
    pkgs = ["numpy", "scipy", "pandas", "statsmodels", "matplotlib", "pyyaml", "hypothesis", "tabulate", "pytest"]
    return {p: _pkg_version(p) for p in pkgs}


def env_info(repo_root: Path | None = None, probe_path: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    lock_path = root / "requirements.lock"
    du = shutil.disk_usage(probe_path if (probe_path and Path(probe_path).exists()) else root)
    return {
        "python": sys.version,
        "os": platform.platform(),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "cpu_model": platform.processor(),
        "threads": os.cpu_count(),
        "packages": package_versions(),
        "lockfile_hash": sha256_file(lock_path),
        "disk_free_bytes": int(du.free),
        "disk_total_bytes": int(du.total),
    }


def build_manifest(repo_dir: Path | str | None = None, **extra: Any) -> dict[str, Any]:
    """Build a complete provenance manifest dict merging git, env, seeds, and stage metadata."""
    root = Path(repo_dir) if repo_dir is not None else Path(__file__).resolve().parents[1]
    g = git_info(root)
    env = env_info(root, probe_path=Path(extra["out_dir"]) if extra.get("out_dir") else root)
    man: dict[str, Any] = {
        "commit": g["commit"],
        "git_head": g["git_head"],
        "git_dirty": g["git_dirty"],
        "branch": g["branch"],
        "tag": g["tag"],
        "config": extra.pop("config", None),
        "config_hash": extra.pop("config_hash", None),
        "regime": extra.pop("regime", None),
        "beta_mode": extra.pop("beta_mode", None),
        "noise_mode": extra.pop("noise_mode", None),
        "factor_rank": extra.pop("factor_rank", None),
        "grid_file": extra.pop("grid_file", None),
        "grid_hash": extra.pop("grid_hash", None),
        "candidate_table_hash": extra.pop("candidate_table_hash", None),
        "selected": extra.pop("selected", None),
        "edge_flags": extra.pop("edge_flags", None),
        "seed_registry_version": seeds.REGISTRY_VERSION,
        "seed_ranges": extra.pop("seed_ranges", None),
        "packages": env["packages"],
        "python": env["python"],
        "os": env["os"],
        "machine": env["machine"],
        "cpu_model": env["cpu_model"],
        "threads": env["threads"],
        "wall_times": extra.pop("wall_times", {}),
        "fit_failures": extra.pop("fit_failures", 0),
        "model_hash": extra.pop("model_hash", None),
        "policy_hash": extra.pop("policy_hash", None),
        "calib_hash": extra.pop("calib_hash", None),
        "lockfile_hash": env["lockfile_hash"],
        "disk_free_bytes": env["disk_free_bytes"],
        "disk_total_bytes": env["disk_total_bytes"],
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if man["calib_hash"] is None and man["policy_hash"] is not None:
        man["calib_hash"] = man["policy_hash"]
    if man["policy_hash"] is None and man["calib_hash"] is not None:
        man["policy_hash"] = man["calib_hash"]
    man.update(extra)
    return man
