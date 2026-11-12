"""python -m canary_ssm.cli <command>   (handbook Section 13 contract)"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import experiments as E
from .report import make_report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="canary_ssm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate"); s.add_argument("--config", required=True); s.add_argument("--role", required=True, choices=list(E.SEED_BASE))
    s.add_argument("--out", required=True); s.add_argument("--csv", action="store_true", help="also dump contract CSV for first 3 rollouts")
    f = sub.add_parser("fit"); f.add_argument("--data", required=True); f.add_argument("--out", required=True)
    f.add_argument("--methods", default="all"); f.add_argument("--grid-stride", type=int, default=1, help="smoke only")
    f.add_argument("--max-dev-pairs", type=int, default=None)
    f.add_argument("--beta-mode", default="pre", choices=["pre", "pooled_dev"])
    f.add_argument("--frozen", action="store_true", help="skip tuning; declared values; calibration AUDITS only")
    c = sub.add_parser("calibrate"); c.add_argument("--data", required=True); c.add_argument("--model", required=True); c.add_argument("--out", required=True)
    v = sub.add_parser("validate-null"); v.add_argument("--data", required=True); v.add_argument("--model", required=True); v.add_argument("--policy", required=True)
    e = sub.add_parser("evaluate"); e.add_argument("--data", required=True); e.add_argument("--model", required=True)
    e.add_argument("--policy", required=True); e.add_argument("--out", required=True)
    u = sub.add_parser("audit-null"); u.add_argument("--config", required=True); u.add_argument("--model", required=True)
    u.add_argument("--policy", required=True); u.add_argument("--n", type=int, default=500); u.add_argument("--out", default="results/audit")
    u.add_argument("--methods", default=None)
    b = sub.add_parser("benchmark"); b.add_argument("--out", default="results/runtime_scaling.csv")
    a = parser_args = ap.parse_args(argv)

    if a.cmd == "simulate":
        print(json.dumps(E.generate_role(E.load_config(a.config), a.role, Path(a.out), a.csv)))
    elif a.cmd == "fit":
        methods = E.BASELINES + E.SSMS + E.ABLATIONS if a.methods == "all" else a.methods.split(",")
        E.fit(Path(a.data), Path(a.out), methods, max_dev_pairs=a.max_dev_pairs, grid_stride=a.grid_stride,
              beta_mode=a.beta_mode, frozen=a.frozen)
    elif a.cmd == "calibrate":
        E.calibrate(Path(a.data), Path(a.model), Path(a.out))
    elif a.cmd == "validate-null":
        E.validate_null(Path(a.data), Path(a.model), Path(a.policy))
    elif a.cmd == "evaluate":
        out = E.evaluate(Path(a.data), Path(a.model), Path(a.policy), Path(a.out)); make_report(out)
    elif a.cmd == "audit-null":
        df = E.audit_null(Path(a.config), Path(a.model), Path(a.policy), a.n, Path(a.out), a.methods.split(",") if a.methods else None)
        print(df.round(3).to_string(index=False))
    elif a.cmd == "benchmark":
        print(E.benchmark(None, out=Path(a.out)).to_string())


if __name__ == "__main__":
    main()
