"""python -m canary_ssm.cli <command>   (handbook Section 13 contract)"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import experiments as E
from . import parallel
from .report import make_report
from .studies import available_studies, run_study
from .topology import load_topology
from .engine import SimulationEngine, load_engine_config


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

    dashboard = sub.add_parser("world-dashboard", help="serve the local backend-owned world dashboard")
    dashboard.add_argument("--config", default="configs/world_recovery.yaml")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.add_argument("--state-dir", default="runtime/world_dashboard", help="durable local run/checkpoint directory")

    clock = sub.add_parser("world-run", help="advance a deterministic headless world clock")
    clock.add_argument("--config", required=True)
    clock.add_argument("--ticks", type=int, default=100)
    clock.add_argument("--out", required=True, help="save replay artifact JSON")
    clock.add_argument("--trace-out", default=None, help="export host/service resource CSV traces")
    clock.add_argument("--telemetry-out", default=None, help="export separate public telemetry and evaluator artifacts")
    clock.add_argument("--run-id", default=None, help="explicit public run identity")
    fixture = sub.add_parser("world-fixtures", help="export low-load, increased-load and recovery traces/plots")
    fixture.add_argument("--out", required=True)
    replay = sub.add_parser("world-replay", help="replay and verify a saved world run")
    replay.add_argument("--artifact", required=True)
    preview = sub.add_parser("world-fault-preview", help="preview the developer-only background schedule without advancing time")
    preview.add_argument("--config", required=True)
    preview.add_argument("--out", default=None)
    scenarios = sub.add_parser("world-scenarios", help="register role bundles and export tiny paired scenarios")
    scenarios.add_argument("--out", required=True)
    scenarios.add_argument("--role", choices=["smoke","development","threshold-calibration","null-validation","final-test"], default="smoke")
    scenarios.add_argument("--pairs-per-family", type=int, default=1)
    scenarios.add_argument("--plan-only", action="store_true", help="register all roles without generating any run data")

    t = sub.add_parser("topology", help="validate a physical topology and emit its JSON snapshot")
    t.add_argument("--config", required=True, help="YAML config or JSON topology snapshot")
    t.add_argument("--out", default=None, help="write snapshot to this path instead of stdout")

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
    f.add_argument("--grid", default=None, help="YAML candidate grid path (default: configs/grids_v2.yaml)")
    f.add_argument("--strict-edges", action="store_true", help="exit with code 3 if any tuned parameter hits a grid edge")
    f.add_argument("--auto-expand", action="store_true", help="expand flagged primary grid dimensions up to 2 times")
    f.add_argument("--max-expansions", type=int, default=2)
    f.add_argument("--k-folds", type=int, default=5)
    f.add_argument("--no-one-se", action="store_true", help="use raw argmin instead of 1-SE regularisation rule")
    f.add_argument("--objective", default="mixture", choices=["mixture", "family_balanced"])
    f.add_argument("--allow-small-dev", action="store_true", help="allow <200 dev nulls (smoke/unit tests only)")
    _add_exec_args(f)

    c = sub.add_parser("calibrate")
    c.add_argument("--data", required=True); c.add_argument("--model", required=True); c.add_argument("--out", required=True)
    c.add_argument("--regime", default=None, help="regime label stored in policy schema v2 (default: data manifest regime)")
    c.add_argument("--allow-regime-mismatch", action="store_true")
    c.add_argument("--oracles", action="store_true", help="include ORACLE reference upper bounds")
    _add_exec_args(c, with_resume=True, with_fly=True)

    v = sub.add_parser("validate-null")
    v.add_argument("--data", required=True); v.add_argument("--model", required=True); v.add_argument("--policy", required=True)
    v.add_argument("--allow-regime-mismatch", action="store_true")
    v.add_argument("--exploratory-gate", action="store_true", help="use n>=400 exploratory threshold instead of final n>=2000")
    v.add_argument("--oracles", action="store_true", help="include ORACLE reference upper bounds")
    _add_exec_args(v, with_resume=True, with_fly=True)

    e = sub.add_parser("evaluate")
    e.add_argument("--data", required=True); e.add_argument("--model", required=True)
    e.add_argument("--policy", required=True); e.add_argument("--out", required=True)
    e.add_argument("--allow-frozen", action="store_true", help="allow frozen audit models (banners report as non-claim audit)")
    e.add_argument("--oracles", action="store_true", help="include ORACLE reference upper bounds")
    e.add_argument("--allow-regime-mismatch", action="store_true")
    _add_exec_args(e, with_resume=True, with_fly=True)

    u = sub.add_parser("audit-null")
    u.add_argument("--config", required=True); u.add_argument("--model", required=True)
    u.add_argument("--policy", required=True); u.add_argument("--n", type=int, default=500); u.add_argument("--out", default="results/audit")
    u.add_argument("--methods", default=None)
    _add_exec_args(u)

    b = sub.add_parser("benchmark")
    b.add_argument("--out", default="results/runtime_scaling.csv")

    st = sub.add_parser("study")
    st.add_argument("name", help=f"Study name ({', '.join(available_studies())})")
    st.add_argument("--model", default="artifacts/model")
    st.add_argument("--policy", default=None)
    st.add_argument("--out", required=True)
    st.add_argument("--n-null", type=int, default=500)
    st.add_argument("--n-harm", type=int, default=200)
    st.add_argument("--seed-purpose", default=None)
    st.add_argument("--allow-frozen", action="store_true")
    st.add_argument("--allow-regime-mismatch", action="store_true")
    st.add_argument("--legacy-seeds", action="store_true")
    _add_exec_args(st)

    a = ap.parse_args(argv)
    cache_dir = Path(a.cache_dir) if getattr(a, "cache_dir", None) else None

    if a.cmd == "world-dashboard":
        from .dashboard import serve_dashboard
        if not 0 <= a.port <= 65535:
            ap.error("port must be in [0, 65535]")
        try:
            serve_dashboard(a.config, a.port, a.state_dir)
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    elif a.cmd == "world-scenarios":
        try:
            from .scenario_registry import registry_manifest
            from .scenario_bundles import export_suite, write_json
            if a.plan_only:
                write_json(Path(a.out)/"registry.json",registry_manifest(a.pairs_per_family))
                print(json.dumps({"registered":True,"materialized":False}))
            else:
                result = export_suite(a.out,a.role,a.pairs_per_family)
                print(json.dumps({"passed":result["passed"],"role":a.role,"pairs":len(result["results"])}))
                if not result["passed"]:
                    ap.error("Scenario functional checks failed; inspect checks.json")
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    elif a.cmd == "world-fault-preview":
        try:
            engine = SimulationEngine(load_engine_config(a.config))
            if engine.demo is None:
                raise ValueError("Fault preview requires demo resource mode")
            text = json.dumps(engine.demo.background.preview(engine.tick), indent=2)+"\n"
            if a.out:
                Path(a.out).parent.mkdir(parents=True, exist_ok=True)
                Path(a.out).write_text(text)
            else:
                print(text, end="")
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    elif a.cmd == "world-fixtures":
        from .resource_report import run_fixtures
        try:
            print(json.dumps(run_fixtures(Path(a.out))))
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    elif a.cmd in ("world-run", "world-replay"):
        try:
            if a.cmd == "world-run":
                engine = SimulationEngine(load_engine_config(a.config),run_id=a.run_id)
                engine.start()
                engine.advance(a.ticks)
                engine.pause()
                if a.trace_out:
                    engine.export_traces(a.trace_out)
                if a.telemetry_out:
                    engine.export_telemetry(a.telemetry_out)
                engine.save(a.out)
            else:
                from .configuration import read_yaml_mapping
                engine = SimulationEngine.replay(read_yaml_mapping(a.artifact))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            ap.error(str(exc))
        print(json.dumps({"tick": engine.tick, "simulated_seconds": engine.snapshot()["simulated_seconds"],
                          "state": engine.state.value, "replay_verified": a.cmd == "world-replay"}))
    elif a.cmd == "topology":
        try:
            snapshot = load_topology(a.config).snapshot()
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
        payload = json.dumps(snapshot, indent=2, allow_nan=False) + "\n"
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
    elif a.cmd == "simulate":
        print(json.dumps(E.generate_role(
            E.load_config(a.config), a.role, Path(a.out), csv=a.csv,
            manifest_only=a.manifest_only, compact=a.compact, config_path=a.config,
        )))
    elif a.cmd == "fit":
        methods = E.BASELINES + E.SSMS + E.ABLATIONS if a.methods == "all" else a.methods.split(",")
        try:
            E.fit(
                Path(a.data), Path(a.out), methods, max_dev_pairs=a.max_dev_pairs, grid_stride=a.grid_stride,
                beta_mode=a.beta_mode, frozen=a.frozen, workers=a.workers, cache_dir=cache_dir,
                grid_path=Path(a.grid) if a.grid else None, strict_edges=a.strict_edges,
                k_folds=a.k_folds, use_one_se=not a.no_one_se, objective=a.objective,
                allow_small_dev=a.allow_small_dev, auto_expand=a.auto_expand, max_expansions=a.max_expansions,
            )
        except E.StrictEdgeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(3)
    elif a.cmd == "calibrate":
        E.calibrate(
            Path(a.data), Path(a.model), Path(a.out), workers=a.workers, cache_dir=cache_dir,
            resume=a.resume, generate_on_the_fly=a.generate_on_the_fly,
            regime=a.regime, allow_regime_mismatch=a.allow_regime_mismatch, include_oracles=a.oracles,
        )
    elif a.cmd == "validate-null":
        E.validate_null(
            Path(a.data), Path(a.model), Path(a.policy), workers=a.workers, cache_dir=cache_dir,
            resume=a.resume, generate_on_the_fly=a.generate_on_the_fly,
            allow_regime_mismatch=a.allow_regime_mismatch,
            min_n_gate=400 if a.exploratory_gate else 2000,
            include_oracles=True if a.oracles else None,
        )
    elif a.cmd == "evaluate":
        out = E.evaluate(
            Path(a.data), Path(a.model), Path(a.policy), Path(a.out), workers=a.workers,
            cache_dir=cache_dir, resume=a.resume, generate_on_the_fly=a.generate_on_the_fly,
            allow_frozen=a.allow_frozen, allow_regime_mismatch=a.allow_regime_mismatch,
            include_oracles=True if a.oracles else None,
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
    elif a.cmd == "study":
        kw = dict(
            model_dir=a.model,
            policy_dir=a.policy,
            out_dir=a.out,
            n_null=a.n_null,
            n_harm=a.n_harm,
            allow_frozen=a.allow_frozen,
            allow_regime_mismatch=a.allow_regime_mismatch,
            legacy_seeds=a.legacy_seeds,
            workers=a.workers,
        )
        if a.seed_purpose is not None:
            kw["seed_purpose"] = a.seed_purpose
        print(json.dumps(run_study(a.name, **kw), indent=1, default=str))


if __name__ == "__main__":
    main()
