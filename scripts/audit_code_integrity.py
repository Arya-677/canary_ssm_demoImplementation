"""
Audit code integrity and leakage safety across canary_ssm packages.
Enforces Rule 1: detector code must never import simulate.Truth, metrics, or read *_truth files.
"""
import os
import re
import sys

detector_dirs = [
    'canary_ssm/factor',
    'canary_ssm/preprocess',
    'canary_ssm/baselines',
    'canary_ssm/kalman',
    'canary_ssm/hierarchy',
    'canary_ssm/decision'
]

forbidden = [
    re.compile(r'from\s+.*\bsimulate\b.*import.*Truth'),
    re.compile(r'import\s+.*simulate\.Truth'),
    re.compile(r'from\s+.*\bmetrics\b\s+import'),
    re.compile(r'import\s+.*metrics'),
    re.compile(r'[\'\"][^\'\"]*_truth[^\'\"]*[\'\"]')
]

violations = []
for d in detector_dirs:
    if not os.path.exists(d):
        continue
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as fh:
                    for i, line in enumerate(fh, 1):
                        for p in forbidden:
                            if p.search(line):
                                violations.append((path, i, line.strip()))

if violations:
    print(f"FAILED: Found {len(violations)} leakage violations:")
    for path, lineno, line in violations:
        print(f"  {path}:{lineno}: {line}")
    sys.exit(1)
else:
    print("SUCCESS: 0 leakage violations. All detector directories are strictly clean.")
