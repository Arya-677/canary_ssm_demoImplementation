"""Module entry point allowing `python -m canary_ssm ...`."""
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
