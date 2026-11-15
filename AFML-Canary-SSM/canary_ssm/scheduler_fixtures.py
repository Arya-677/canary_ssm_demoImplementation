"""Export healthy, fixed and rate-sampled scenarios with no candidate release."""
import argparse
import json
import math
from pathlib import Path
from .engine import SimulationEngine, load_engine_config


def export_fixtures(directory):
    directory=Path(directory)
    results=[]
    root=Path(__file__).resolve().parents[1]
    for name in ("all_healthy","fixed","rates"):
        e=SimulationEngine(load_engine_config(root/f"configs/world_scheduler_{name}.yaml"))
        scheduler=e.demo.background
        manifest=scheduler.manifest();events=scheduler.events
        ticks=max([scheduler.config.horizon_ticks,*(f.end_tick for f in events)])
        e.step(ticks)
        hosts=e.resource_model.host_trace
        rules={r.rule_id:r for r in scheduler.config.rules}
        last={};cooldown_ok=ranges_ok=True
        for f in events:
            rule=rules.get(scheduler.rule_ids.get(f.fault_id))
            cooldown=math.ceil((rule.cooldown_seconds if rule else scheduler.config.fixed_cooldown_seconds)/e.config.tick_seconds)
            key=(f.scope.value,f.target)
            cooldown_ok &= f.start_tick>=last.get(key,1)
            last[key]=f.end_tick+cooldown
            if rule:
                lo,hi=rule.duration_ticks(e.config.tick_seconds)
                ranges_ok &= lo<=f.duration<=hi and rule.severity_min<=f.severity<=rule.severity_max
        checks={"cooldowns":bool(cooldown_ok),"ranges":bool(ranges_ok),
            "concurrency":all(sum(f.active(t) for f in events)<=scheduler.config.max_concurrent for t in range(1,ticks+1)),
            "event_budget":len(events)<=scheduler.config.max_events,
            "recovered":all(v==1 for v in e.resource_model.cpu_factors.values()) and all(v==1 for v in e.resource_model.network_factors.values()) and not e.resource_model.unavailable_hosts and e.resource_model.demand_multiplier==1,
            "no_release_required":all(r.release_id=="release-healthy-v1" for r in e.world.replicas),
            "public_telemetry_excludes_schedule":all(not ({"fault_id","kind","seed","rule_id","severity"}&row.keys()) for row in hosts),
            "replay":SimulationEngine.replay(e.artifact()).artifact()==e.artifact()}
        if name=="all_healthy":
            checks["zero_faults"]=not events and all(r["available"] and r["memory_platform_mb"]==0 for r in hosts)
        elif name=="fixed":
            checks["fixed_host_effect"]=all(r["cpu_capacity_cores"]<8 for r in hosts if r["host_id"]=="host-01-01" and 3<=r["tick"]<6)
            affected=[r for r in hosts if r["rack_id"]=="rack-02" and 5<=r["tick"]<9]
            checks["fixed_rack_descendants"]=len(affected)==20 and all(r["network_capacity_mbps"]<1000 for r in affected)
            checks["fixed_shared_demand"]=all(r["shared_traffic_factor"]>4 for r in e.resource_model.service_trace if 12<=r["tick"]<17)
        else:
            checks["all_rate_scopes_present"]={f.scope.value for f in events}=={"host","rack","world"}
        out=directory/name
        e.export_traces(out);e.save(out/"run.json")
        (out/"schedule_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        (out/"developer_fault_truth.json").write_text(json.dumps({"developer_only":True,"faults":e.demo.developer_truth()},indent=2)+"\n")
        result={"scenario":name,"ticks":ticks,"events":len(events),"checks":checks,"passed":all(checks.values())}
        (out/"checks.json").write_text(json.dumps(result,indent=2)+"\n");results.append(result)
    summary={"synthetic":True,"scenarios":results,"passed":all(r["passed"] for r in results)}
    (directory/"fixture_checks.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",default="examples/background_faults")
    result=export_fixtures(parser.parse_args().out)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["passed"] else 1)
