"""Package everything a reviewer needs into ONE zip (Section 'Review protocol' of docs/ANTIGRAVITY_SPEC_V3.md).

Usage:  python scripts/make_review_bundle.py --phase P2 [--results results/study_inertia ...] [--pytest-log pytest.log]
Contains: git status/log/diff-stat, pytest log, every CSV/JSON/MD in the given result dirs (size-capped), manifests,
SHA-256 of every file, a REVIEW_REQUEST.md template that Antigravity must fill with facts only.
"""
from __future__ import annotations

import argparse, hashlib, subprocess, zipfile
from datetime import datetime, timezone
from pathlib import Path

MAX_FILE = 25 * 1024 * 1024
KEEP = {".csv", ".json", ".md", ".yaml", ".yml", ".txt", ".log", ".png"}


def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception as e:                                   # git may be missing on Windows
        return f"(unavailable: {e})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--results", nargs="*", default=["results"])
    ap.add_argument("--pytest-log", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out or f"review_bundle_{a.phase}.zip")
    files = []
    for r in a.results:
        for p in sorted(Path(r).rglob("*")):
            if p.is_file() and p.suffix.lower() in KEEP and p.stat().st_size <= MAX_FILE and "data" not in p.parts[:1]:
                files.append(p)
    meta = {"git_status.txt": sh(["git", "status", "--short"]), "git_log.txt": sh(["git", "log", "--oneline", "-20"]),
            "git_diff_stat.txt": sh(["git", "diff", "--stat", "HEAD"])}
    if a.pytest_log and Path(a.pytest_log).exists():
        files.append(Path(a.pytest_log))
    sums = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, t in meta.items():
            z.writestr(f"bundle/{n}", t)
        for p in files:
            z.write(p, f"bundle/files/{p.as_posix()}")
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.as_posix()}")
        z.writestr("bundle/SHA256SUMS.txt", "\n".join(sums))
        z.writestr("bundle/REVIEW_REQUEST.md",
                   f"# Review request, phase {a.phase} ({datetime.now(timezone.utc).isoformat()})\n\n"
                   "Fill with FACTS ONLY (no interpretation, no invented numbers):\n"
                   "1. Work packages completed (ids) and files changed (from git_diff_stat.txt).\n"
                   "2. Commands run, exact.\n3. pytest summary line (passed/failed/skipped) and every failing test name.\n"
                   "4. Each acceptance criterion of this phase: PASS/FAIL/NOT RUN with the CSV/JSON file+row that proves it.\n"
                   "5. Deviations from the spec and why. 6. Anything surprising (unexpected warnings, boundary hits, NaNs).\n"
                   "7. Questions you could not resolve from the repo.\n")
    print(f"wrote {out} ({len(files)} files)")


if __name__ == "__main__":
    main()
