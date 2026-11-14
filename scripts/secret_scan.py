"""Scan repository for credentials, API keys, private keys, and sensitive tokens."""
import os
import re
from pathlib import Path

secret_patterns = [
    re.compile(r'(?i)api[_-]?key\s*[:=]\s*["\'][A-Za-z0-9_\-]{16,}["\']'),
    re.compile(r'(?i)secret\s*[:=]\s*["\'][A-Za-z0-9_\-]{16,}["\']'),
    re.compile(r'(?i)token\s*[:=]\s*["\'][A-Za-z0-9_\-]{16,}["\']'),
    re.compile(r'BEGIN (?:RSA|OPENSSH|DSA|EC) PRIVATE KEY'),
    re.compile(r'ghp_[A-Za-z0-9]{36}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{80}')
]

print("=== EXECUTING SECRET SCAN ===")
violations = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in [".git", "data", "data_audit", "cache", "__pycache__", ".venv"]]
    for f in files:
        if f.endswith((".png", ".svg", ".zip", ".npz", ".pyc")):
            continue
        p = Path(root) / f
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for pat in secret_patterns:
                if pat.search(content):
                    violations.append((str(p), pat.pattern))
                    print(f"POTENTIAL MATCH in {p}: {pat.pattern}")
        except Exception:
            pass

if not violations:
    print("SCAN RESULT: Clean! Zero credentials, secrets, tokens, or private keys detected.")
else:
    print(f"SCAN RESULT: Found {len(violations)} potential matches.")
