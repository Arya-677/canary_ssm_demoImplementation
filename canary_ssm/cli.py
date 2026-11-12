"""python -m canary_ssm.cli <command>   (handbook Section 13 contract)"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import experiments as E
from . import parallel
from .report import make_report


def _add_exec_args(parser: argparse.ArgumentParser, with_resume: bool = False, with_fly: bool = False) -> None:
    parser.add_argument("--workers", type=int, default=parallel.default_workers(),
                        help="Worker process count (default: cpu_count - 2)")
    parser.add_argument("--cache-dir", default=None, help="Optional directory for adj/sel caches")
    if with_resume:
        parser.add_argument("--resume", action="store_true", help="Resume from chunk JSONL journal")
    if with_fly:
        parser.add_argument("--generate-on-the-fly", action="store_true",
                            help="Regenerate rollouts in memory from data/<role>/manifest.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="canary_ssm")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate")
    s.add_argument("--config", required=True)
    s.add_argument("--role", required=True, choices=list(E.SEED_BASE))
    s.add_argument("--out", required=True)
    s.add_argument("--csv", action="store_true", help="also dump contract CSV for first 3 rollouts")
    s.add_argument("--manifest-only", action="store_true", help="write manifest.json only (for --generate-on-the-fly)")
    s.add_argument("--compact", action="store_true", help="store float32 y and omit spill/noise arrays")

    f = sub.add_parser("fit")
    f.add_argument("--data", required=True); f.add_argument("--out", required=True)
    f.add_argument("--methods", default="all"); f.add_argument("--grid-stride", type=int, default=1, help="smoke only")
    f.add_argument("--max-dev-pairs", type=int, default=None)
    f.add_argument("--beta-mode", default="pre", choices=["pre", "pooled_dev"])
    f.add_argument("--frozen", action="store_true", help="skip tuning; declared values; calibration AUDITS only")
    _add_exec_args(f)

    c = sub.add_parser("calibrate")
    c.add_argument("--data", required=True); c.add_argument("--model", required=True); c.add_argument("--out", required=True)
    _add_exec_args(c, with_resume=True, with_fly=True)

    v = sub.add_parser("validate-null")
    v.add_argument("--data", required=True); v.add_argument("--model", required=True); v.add_argument("--policy", required=True)
    _add_exec_args(v, with_resume=True, with_fly=True)

    e = sub.add_parser("evaluate")
    e.add_argument("--data", required=True); e.add_argument("--model", required=True)
    e.add_argument("--policy", required=True); e.add_argument("--out", required=True)
    _add_exec_args(e, with_resume=True, with_fly=True)

    u = sub.add_parser("audit-null")
    u.add_argument("--config", required=True); u.add_argument("--model", required=True)
    u.add_argument("--policy", required=True); u.add_argument("--n", type=int, default=500); u.add_argument("--out", default="results/audit")
    u.add_argument("--methods", default=None)
    _add_exec_args(u)

    b = sub.add_parser("benchmark")
    b.add_argument("--out", default="results/runtime_scaling.csv")

    a = ap.parse_args(argv)
    cache_dir = Path(a.cache_dir) if getattr(a, "cache_dir", None) else None

    if a.cmd == "simulate":
        print(json.dumps(E.generate_role(
            E.load_config(a.config), a.role, Path(a.out), csv=a.csv,
            manifest_only=a.manifest_only, compact=a.compact, config_path=a.config,
        )))
    elif a.cmd == "fit":
        methods = E.BASELINES + E.SSMS + E.ABLATIONS if a.methods == "all" else a.methods.split(",")
        E.fit(
            Path(a.data), Path(a.out), methods, max_dev_pairs=a.max_dev_pairs, grid_stride=a.grid_stride,
            beta_mode=a.beta_mode, frozen=a.frozen, workers=a.workers, cache_dir=cache_dir,
        )
    elif a.cmd == "calibrate":
        E.calibrate(
            Path(a.data), Path(a.model), Path(a.out), workers=a.workers, cache_dir=cache_dir,
            resume=a.resume, generate_on_the_fly=a.generate_on_the_fly,
        )
    elif a.cmd == "validate-null":
        E.validate_null(
            Path(a.data), Path(a.model), Path(a.policy), workers=a.workers, cache_dir=cache_dir,
            resume=a.resume, generate_on_the_fly=a.generate_on_the_fly,
        )
    elif a.cmd == "evaluate":
        out = E.evaluate(
            Path(a.data), Path(a.model), Path(a.policy), Path(a.out), workers=a.workers,
            cache_dir=cache_dir, resume=a.resume, generate_on_the_fly=a.generate_on_the_fly,
        )
        make_report(out)
    elif a.cmd == "audit-null":
        df = E.audit_null(
            Path(a.config), Path(a.model), Path(a.policy), a.n, Path(a.out),
            a.methods.split(",") if a.methods else None, workers=a.workers, cache_dir=cache_dir,
        )
        print(df.round(3).to_string(index=False))
    elif a.cmd == "benchmark":
        print(E.benchmark(None, out=Path(a.out)).to_string())


if __name__ == "__main__":
    main()
