"""One-command local demo startup and reset/replay workflow.

Usage:
    python scripts/demo.py                        # Runs canonical scenario (release_leak_two_canaries)
    python scripts/demo.py --list                 # Lists all 8 versioned scenarios
    python scripts/demo.py --scenario <name>      # Runs specified scenario
    python scripts/demo.py --all                  # Runs and persists all 8 scenarios
    python scripts/demo.py --replay <path>        # Verifies bit-for-bit replay
    python scripts/demo.py --serve                # Launches interactive web dashboard
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canary_ssm.cli import main

if __name__ == "__main__":
    # If no arguments provided, default to running demo
    args = sys.argv[1:]
    if not args:
        args = ["demo", "--scenario", "release_leak_two_canaries"]
    elif args[0] != "demo":
        args = ["demo"] + args
    main(args)
