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
    b.add_argument("--fleet-scaling", action="store_true", help="Run multi-rack fleet size scaling benchmark")

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

    w = sub.add_parser("world", help="Inspect and step the virtual fleet world")
    w.add_argument("--topology", action="store_true", help="Print fleet topology")
    w.add_argument("--step", type=int, default=None, help="Step simulation by N ticks")
    w.add_argument("--fast-forward", type=int, default=None, help="Fast forward until tick T")
    w.add_argument("--max-ticks", type=int, default=1000, help="Max ticks for fast forward")
    w.add_argument("--inspect", action="store_true", help="Detailed server inspection")
    w.add_argument("--racks", type=int, default=4, help="Number of racks (default: 4)")
    w.add_argument("--servers-per-rack", type=int, default=6, help="Servers per rack (default: 6)")
    w.add_argument("--classes", type=int, default=2, help="Number of classes (default: 2)")
    w.add_argument("--seed", type=int, default=42, help="Simulation seed (default: 42)")
    w.add_argument("--telemetry", action="store_true", help="Include telemetry observations in output")
    w.add_argument("--json", action="store_true", help="Output pure JSON format")

    rel = sub.add_parser("release", help="Manage releases, sample manifests, and canary allocations")
    rel.add_argument("--list", action="store_true", help="List registered releases")
    rel.add_argument("--create", help="Create release from manifest JSON path")
    rel.add_argument("--validate", help="Validate comma-separated canary server IDs (e.g. srv-0-0,srv-1-0)")
    rel.add_argument("--default-allocation", action="store_true", help="Print default balanced canary allocation")
    rel.add_argument("--sample-manifests", help="Output directory to generate sample manifests")
    rel.add_argument("--racks", type=int, default=4, help="Racks in fleet for allocation (default: 4)")
    rel.add_argument("--servers-per-rack", type=int, default=6, help="Servers per rack (default: 6)")
    rel.add_argument("--json", action="store_true", help="Output pure JSON format")

    dash = sub.add_parser("dashboard", help="Start the Virtual Data Center Web Dashboard and REST API")
    dash.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    dash.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")

    demo = sub.add_parser("demo", help="One-command local demo startup and reset/replay workflow")
    demo.add_argument("--scenario", default=None, help="Scenario name to run (e.g. clean_release, release_leak_two_canaries)")
    demo.add_argument("--list", action="store_true", help="List available versioned scenarios")
    demo.add_argument("--all", action="store_true", help="Execute and persist all 8 versioned scenarios")
    demo.add_argument("--out", default=None, help="Output directory for persisted scenario artifacts")
    demo.add_argument("--replay", default=None, help="Verify reproducibility from a saved scenario directory")
    demo.add_argument("--serve", action="store_true", help="Start dashboard after running demo scenario")
    demo.add_argument("--host", default="127.0.0.1", help="Bind host for dashboard")
    demo.add_argument("--port", type=int, default=8000, help="Bind port for dashboard")
    demo.add_argument("--json", action="store_true", help="Output pure JSON summary")

    plt_cmd = sub.add_parser("plot", help="Generate publication plots strictly from saved results tables")
    plt_cmd.add_argument("--out-dir", default="results/plots", help="Output directory for plots")

    a = ap.parse_args(argv)
    cache_dir = Path(a.cache_dir) if getattr(a, "cache_dir", None) else None

    if a.cmd == "simulate":
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
        if a.fleet_scaling:
            from canary_ssm.evaluation.benchmarking import run_fleet_scaling_benchmark
            df = run_fleet_scaling_benchmark(out_csv=a.out)
            print(df.to_string())
        else:
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
    elif a.cmd == "world":
        from .world import VirtualWorld, create_default_fleet
        fleet = create_default_fleet(
            n_racks=a.racks,
            servers_per_rack=a.servers_per_rack,
            n_classes=a.classes,
        )
        world = VirtualWorld(fleet=fleet, seed=a.seed)
        if a.step is not None:
            res = world.step(a.step)
            out_obj: dict[str, Any] = {
                "action": "step",
                "tick": res.tick,
                "ticks_advanced": res.ticks_advanced,
                "is_paused": res.is_paused,
                "events_executed": res.events_executed,
            }
            if a.telemetry:
                out_obj["telemetry"] = [t.to_dict() for t in world.get_latest_telemetry()]
            if a.json:
                print(json.dumps(out_obj, indent=2))
            else:
                print(f"World stepped by {res.ticks_advanced} ticks -> current tick: {res.tick}")
                if a.telemetry:
                    print("Latest Telemetry Records:")
                    for t in world.get_latest_telemetry():
                        print(f"  {t.server_id} [v={t.version}, exp={t.exposure}]: {t.request_count} reqs, {t.cpu_fraction*100:.1f}% CPU, {t.memory_mb:.1f}MB, {t.latency_ms:.2f}ms, {t.error_count} errs")
        elif a.fast_forward is not None:
            res = world.fast_forward(a.fast_forward, max_ticks=a.max_ticks)
            if a.json:
                print(json.dumps({
                    "action": "fast_forward",
                    "tick": res.tick,
                    "ticks_advanced": res.ticks_advanced,
                    "is_paused": res.is_paused,
                    "events_executed": res.events_executed,
                }, indent=2))
            else:
                print(f"World fast-forwarded to tick: {res.tick} (advanced {res.ticks_advanced} ticks)")
        elif a.inspect:
            info = {
                "summary": world.inspect_topology(),
                "servers": [s.to_dict() for s in world.fleet.list_servers()],
            }
            if a.json:
                print(json.dumps(info, indent=2))
            else:
                print(f"=== Fleet: {world.fleet.fleet_id} ({world.fleet.total_racks} racks, {world.fleet.total_servers} servers) ===")
                for rack in world.fleet.list_racks():
                    print(f"Rack {rack.rack_id} [switch={rack.switch_id}, online={rack.online}]:")
                    for srv in rack.servers.values():
                        print(f"  {srv.server_id}: class={srv.class_id}, ver={srv.installed_version}, mem={srv.memory_capacity_mb}MB, cpu={srv.cpu_cores}, online={srv.online}")
        else:
            topo = world.inspect_topology()
            if a.json:
                print(json.dumps(topo, indent=2))
            else:
                print(f"Fleet Topology Summary ({topo['fleet_id']}):")
                print(f"  Total Racks: {topo['total_racks']}")
                print(f"  Total Servers: {topo['total_servers']} ({topo['online_servers']} online)")
                print(f"  Class Distribution: {topo['class_distribution']}")
                print(f"  Version Distribution: {topo['version_distribution']}")
                print(f"  Clock: tick={topo['clock']['tick']}, paused={topo['clock']['is_paused']}")
    elif a.cmd == "release":
        from canary_ssm.deployments import (
            DeploymentManager,
            generate_default_allocation,
            validate_canary_allocation,
            write_sample_manifests,
        )
        from canary_ssm.world.models import create_default_fleet

        fleet = create_default_fleet(n_racks=a.racks, servers_per_rack=a.servers_per_rack)
        mgr = DeploymentManager()

        if a.sample_manifests:
            paths = write_sample_manifests(a.sample_manifests)
            if a.json:
                print(json.dumps([str(p) for p in paths], indent=2))
            else:
                print(f"Generated {len(paths)} sample manifests in {a.sample_manifests}:")
                for p in paths:
                    print(f"  {p.name}")
        elif a.default_allocation:
            alloc = generate_default_allocation(fleet)
            val = validate_canary_allocation(fleet, alloc)
            if a.json:
                print(json.dumps(val.to_dict(), indent=2))
            else:
                print(f"Default Balanced Canary Allocation ({len(alloc)} canaries, {len(val.control_server_ids)} controls):")
                print(f"  Canaries: {alloc}")
                print(f"  Is Valid: {val.is_valid}")
                print(f"  Rack breakdown: {val.rack_breakdown}")
        elif a.validate:
            canaries = [s.strip() for s in a.validate.split(",") if s.strip()]
            val = validate_canary_allocation(fleet, canaries)
            if a.json:
                print(json.dumps(val.to_dict(), indent=2))
            else:
                print(f"Canary Allocation Validation (Valid={val.is_valid}):")
                print(f"  Canaries: {list(val.canary_server_ids)}")
                print(f"  Controls: {len(val.control_server_ids)} servers")
                if val.issues:
                    print(f"  ISSUES (BLOCKING):")
                    for iss in val.issues:
                        print(f"    - {iss}")
                if val.warnings:
                    print(f"  WARNINGS:")
                    for w in val.warnings:
                        print(f"    - {w}")
        elif a.create:
            manifest_path = Path(a.create)
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            art_data = data.get("artifact", {})
            rel = mgr.create_release(
                release_id=data["release_id"],
                version_tag=data["version_tag"],
                behavior_profile=data["behavior_profile"],
                artifact_filename=art_data.get("artifact_filename"),
                artifact_content=art_data.get("content_preview"),
                metadata=data.get("metadata"),
            )
            if a.json:
                print(json.dumps(rel.to_dict(), indent=2))
            else:
                print(f"Release created: {rel.release_id} (tag={rel.version_tag}, profile={rel.behavior_profile.profile_type.value})")
                if rel.artifact:
                    print(f"  Artifact: {rel.artifact.artifact_filename} (SHA-256={rel.artifact.checksum_sha256[:16]}..., unexecuted={not rel.artifact.is_executed})")
        else:
            rels = mgr.registry.list_releases()
            if a.json:
                print(json.dumps([r.to_dict() for r in rels], indent=2))
            else:
                print(f"Registered Releases ({len(rels)}):")
                for r in rels:
                    print(f"  {r.release_id}: tag={r.version_tag}, profile={r.behavior_profile.profile_type.value}")
    elif a.cmd == "dashboard":
        from canary_ssm.api.app import run_server
        print(f"Starting Virtual Data Center Dashboard on http://{a.host}:{a.port}")
        run_server(host=a.host, port=a.port)
    elif a.cmd == "demo":
        from canary_ssm.scenarios import (
            create_scenario_catalog,
            run_scenario,
            save_declarative_configs,
            verify_scenario_reproducibility,
        )
        catalog = create_scenario_catalog()

        if a.list:
            if a.json:
                print(json.dumps([s.to_dict() for s in catalog.values()], indent=2))
            else:
                print(f"Available Versioned Scenarios ({len(catalog)}):")
                for name, s in catalog.items():
                    print(f"  * {name:35s} (seed={s.seed}, ticks={s.horizon_ticks})")
                    print(f"    {s.description}")
        elif a.replay:
            rep_res = verify_scenario_reproducibility(a.replay)
            if a.json:
                print(json.dumps(rep_res, indent=2))
            else:
                status_str = "SUCCESS (EXACT MATCH)" if rep_res["reproduced"] else "FAILED (MISMATCH)"
                print(f"Replay Verification for {rep_res['scenario_name']}: {status_str}")
                print(f"  * Telemetry Rows Compared:      {rep_res['telemetry_rows_compared']} (matches={rep_res['telemetry_matches']})")
                print(f"  * Recommendation Rows Compared: {rep_res['recommendation_rows_compared']} (matches={rep_res['advisories_match']})")
                print(f"  * Max Latency Difference:       {rep_res['max_latency_diff']:.6f} ms")
                print(f"  * Max Memory Difference:        {rep_res['max_memory_diff']:.6f} MB")
                print(f"  * Max CPU Difference:           {rep_res['max_cpu_diff']:.6f}")
        elif a.all:
            base_out = Path(a.out) if a.out else Path("results/scenarios")
            save_declarative_configs()
            print(f"Executing and persisting all {len(catalog)} versioned scenarios to {base_out}...")
            results = []
            for name, scen in catalog.items():
                scen_out = base_out / name
                res = run_scenario(scen, output_dir=scen_out)
                results.append({
                    "scenario": name,
                    "status": res.evaluator_results["detection_status"],
                    "alarm_tick": res.evaluator_results["alarm_tick"],
                    "infra_advisory": res.evaluator_results["final_infrastructure_advisory"],
                    "canary_advisory": res.evaluator_results["final_canary_release_advisory"],
                    "attribution": res.evaluator_results["final_attribution"],
                })
            if a.json:
                print(json.dumps(results, indent=2))
            else:
                print("\nExecution Summary Table:")
                print(f"{'Scenario Name':36s} {'Status':12s} {'Alarm':8s} {'Infrastructure':22s} {'Canary Release'}")
                print("-" * 100)
                for r in results:
                    al_str = str(r["alarm_tick"]) if r["alarm_tick"] is not None else "None"
                    print(f"{r['scenario']:36s} {r['status']:12s} {al_str:8s} {r['infra_advisory']:22s} {r['canary_advisory']}")
        else:
            target_name = a.scenario or "release_leak_two_canaries"
            if target_name not in catalog:
                print(f"Error: Unknown scenario '{target_name}'. Available: {list(catalog.keys())}", file=sys.stderr)
                sys.exit(1)
            scen = catalog[target_name]
            out_dir = Path(a.out) if a.out else Path(f"results/scenarios/{target_name}")
            print(f"Running scenario '{target_name}' (seed={scen.seed}, t0={scen.deployment.deploy_tick}, horizon={scen.horizon_ticks})...")
            res = run_scenario(scen, output_dir=out_dir)
            ev = res.evaluator_results
            if a.json:
                print(json.dumps(ev, indent=2))
            else:
                print(f"\nScenario '{target_name}' Completed Successfully:")
                print(f"  * Detection Status:             {ev['detection_status']}")
                print(f"  * First Alarm Tick:             {ev['alarm_tick']}")
                print(f"  * Detection Delay:              {ev['detection_delay']} ticks")
                print(f"  * Final Infrastructure State:   {ev['final_infrastructure_advisory']}")
                print(f"  * Final Canary Release State:   {ev['final_canary_release_advisory']}")
                print(f"  * Final Inferred Attribution:   {ev['final_attribution']}")
                print(f"  * Persisted Artifacts saved to: {out_dir}")
                print(f"    - {out_dir / 'manifest.json'}")
                print(f"    - {out_dir / 'telemetry.csv'}")
                print(f"    - {out_dir / 'model_policy.json'}")
                print(f"    - {out_dir / 'recommendations.csv'}")
                print(f"    - {out_dir / 'evaluator_results.json'}")

            if a.serve:
                from canary_ssm.api.app import run_server
                print(f"\nStarting Interactive Dashboard on http://{a.host}:{a.port}...")
                run_server(host=a.host, port=a.port)
    elif a.cmd == "plot":
        from canary_ssm.evaluation.plotting import generate_all_plots
        print(f"Generating plots into {a.out_dir} strictly from saved CSV tables...")
        generated = generate_all_plots(out_dir=a.out_dir)
        print(f"Successfully generated {len(generated)} publication figures:")
        for p in generated:
            print(f"  * {p}")



if __name__ == "__main__":
    main()
