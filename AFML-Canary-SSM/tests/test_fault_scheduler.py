import ast
from dataclasses import replace
import json
import math
from pathlib import Path
import pytest
from canary_ssm.dashboard import ApiError, WorldController
from canary_ssm.engine import EngineConfig, SimulationEngine, load_engine_config
from canary_ssm.fault_scheduler import BackgroundFaultConfig, BackgroundFaultScheduler, FaultRate
from canary_ssm.faults import FaultEvent
from canary_ssm.resources import ResourceConfig, ServiceWorkload
from canary_ssm.topology import Topology, DataCenter, Rack, Host, HostCapacity, ServiceReplica

ROOT = Path(__file__).resolve().parents[1]


def world(count=1):
    return Topology((DataCenter("dc"),), (Rack("rack", "dc"),),
        tuple(Host(f"host-{i}", "rack", "dc", 0, HostCapacity(2, 256, 1000, 100)) for i in range(count)),
        tuple(ServiceReplica("service", f"replica-{i}", f"host-{i}", "v1") for i in range(count)))


def rule(**changes):
    return FaultRate(**(dict(rule_id="cpu", kind="cpu_throttle", scope="host", rate_per_second=1000,
        severity_min=.5, severity_max=.5, duration_min_seconds=2, duration_max_seconds=2,
        cooldown_seconds=3) | changes))


def config(background):
    return EngineConfig(world(), resources=ResourceConfig((ServiceWorkload("service", 40, baseline_memory_mb=16),), host_baseline_memory_mb=16),
                        demo=True, background_faults=background)


def command(c, name, args=None):
    payload = dict(command_id=f"id-{c.revision}", run_id=c.run_id, epoch=c.epoch, command=name)
    if args is not None: payload["args"] = args
    return c.command(payload)


def test_hand_computed_half_open_duration_and_post_end_cooldown():
    s = BackgroundFaultScheduler(BackgroundFaultConfig(enabled=True, horizon_ticks=12,rules=(rule(),)),world(),1)
    assert [f.start_tick for f in s.events] == [1,6,11]
    assert [f.end_tick for f in s.events] == [3,8,13]
    assert all(f.severity == .5 for f in s.events)
    assert not s.active_events(3) and s.active_events(6)


def test_hazard_uses_simulated_seconds_and_rates_scale_per_target():
    rules = (rule(rate_per_second=math.log(2)/2, duration_min_seconds=2,duration_max_seconds=4),
             rule(rule_id="rack",scope="rack",kind="network_degradation",rate_per_second=.2),
             rule(rule_id="world",scope="world",kind="demand_surge",rate_per_second=.3))
    s = BackgroundFaultScheduler(BackgroundFaultConfig(rules=rules),world(3),2)
    by_id = {r["rule_id"]:r for r in s.sampling}
    assert by_id["cpu"]["candidate_probability_per_tick"] == pytest.approx(.5)
    assert by_id["cpu"]["nominal_world_rate_per_second"] == pytest.approx(3*math.log(2)/2)
    assert by_id["rack"]["targets"] == 1 and by_id["world"]["targets"] == 1
    assert by_id["cpu"]["duration_ticks_inclusive"] == [1,2]
    assert by_id["cpu"]["cooldown_ticks"] == 2


def test_cap_and_ties_are_deterministic_and_events_are_not_delayed():
    s = BackgroundFaultScheduler(BackgroundFaultConfig(enabled=True,max_concurrent=1,max_events=2,
        horizon_ticks=10,rules=(rule(cooldown_seconds=0),)),world(3),1)
    assert [(f.start_tick,f.target) for f in s.events] == [(1,"host-0"),(3,"host-0")]
    assert s.summary["rejected_concurrency"] > 0 and s.summary["rejected_capacity"] > 0
    assert all(sum(f.active(t) for f in s.events)<=1 for t in range(1,15))


def test_named_streams_preserve_host_candidates_when_adding_hosts():
    c = BackgroundFaultConfig(enabled=True,max_concurrent=100,horizon_ticks=80,rules=(rule(rate_per_second=.2,cooldown_seconds=0),))
    a,b = [BackgroundFaultScheduler(c,world(n),1) for n in (1,2)]
    fields = lambda s:[(f.start_tick,f.duration,f.severity,f.seed) for f in s.events if f.target=="host-0"]
    assert fields(a) and fields(a)==fields(b)
    assert a.manifest()==BackgroundFaultScheduler(c,world(),1).manifest()


@pytest.mark.parametrize("changes",[{"enabled":1},{"seed":True},{"seed":-1},{"horizon_ticks":0},
    {"max_concurrent":0},{"max_events":501},{"mode":"unknown"},{"rules":[{}]},{"fixed_cooldown_seconds":-1}])
def test_invalid_config(changes):
    with pytest.raises(ValueError): BackgroundFaultConfig.from_dict(changes)


@pytest.mark.parametrize("changes",[{"rate_per_second":-1},{"rate_per_second":float("nan")},
    {"rate_per_second":True},{"duration_max_seconds":1},{"severity_max":1},{"cooldown_seconds":-1},{"scope":"world"}])
def test_invalid_rate_rule(changes):
    with pytest.raises(ValueError): rule(**changes)


def test_nonrepresentable_durations_rejected_and_zero_rate_is_healthy():
    with pytest.raises(ValueError,match="whole ticks"):
        BackgroundFaultScheduler(BackgroundFaultConfig(rules=(rule(duration_min_seconds=1,duration_max_seconds=1),)),world(),2)
    s = BackgroundFaultScheduler(BackgroundFaultConfig(rules=(rule(rate_per_second=0),)),world(),1)
    assert s.events==[] and s.summary["candidate_events"]==0


def test_fixed_events_reject_duplicates_parentage_limits_and_cooldown():
    event = FaultEvent("f","cpu_throttle","host","host-0",1,3,.5,10000)
    for events,options in [((event,event),{}),((replace(event,target="absent"),),{}),
        ((event,replace(event,fault_id="g",start_tick=2)),{"max_concurrent":1}),
        ((event,replace(event,fault_id="g",start_tick=4)),{"fixed_cooldown_seconds":2}),
        ((replace(event,start_tick=121),),{})]:
        with pytest.raises(ValueError):
            BackgroundFaultScheduler(BackgroundFaultConfig(mode="fixed",fixed_events=events,**options),world(),1)


def test_enable_disable_reset_replay_and_no_release_dependency(tmp_path):
    b = BackgroundFaultConfig(enabled=True,mode="fixed",horizon_ticks=10,
        fixed_events=(FaultEvent("fixed","cpu_throttle","host","host-0",1,5,.5,10000),))
    c = WorldController(config(b),state_dir=tmp_path)
    command(c,"step")
    assert c.engine.resource_model.cpu_factors["host-0"]==.5
    versions=c.engine.world.replicas;manifest=c.engine.demo.background.manifest()
    command(c,"background_set_enabled",{"enabled":False});command(c,"step")
    assert c.engine.resource_model.cpu_factors["host-0"]==1
    command(c,"background_set_enabled",{"enabled":True});command(c,"step")
    assert c.engine.resource_model.cpu_factors["host-0"]==.5
    assert c.engine.demo.background.manifest()==manifest and c.engine.world.replicas==versions
    assert all(word not in json.dumps(c.packet()) for word in ("fixed","rule_id","schedule_sha256","rate_per_second"))
    c.close();restored=WorldController(config(b),state_dir=tmp_path)
    assert restored.engine.artifact()==c.engine.artifact()
    assert SimulationEngine.replay(c.engine.artifact()).artifact()==c.engine.artifact()
    tampered=c.engine.artifact();tampered["manifest"]["background_faults"]["events"][0]["severity"]=.8
    with pytest.raises(ValueError): SimulationEngine.replay(tampered)
    command(c,"reset")
    assert c.engine.tick==0 and c.engine.demo.background.enabled and c.engine.demo.background.manifest()==manifest
    restored.close()


def test_disabled_background_has_identical_healthy_workload_and_rng():
    b=BackgroundFaultConfig(enabled=False,rules=(rule(),))
    a=SimulationEngine(config(b));healthy=SimulationEngine(replace(config(b),background_faults=None))
    for e in (a,healthy):e.step(10)
    assert a.resource_model.trace()==healthy.resource_model.trace()
    assert a.artifact()["rng_states"]==healthy.artifact()["rng_states"]


def test_deployment_profile_selection_never_resamples_background():
    e=SimulationEngine(load_engine_config(ROOT/"configs/world_scheduler_rates.yaml"));before=e.demo.background.manifest()
    plan=e.operations_command("preview",{"release_id":"sample-leak-v2"})
    e.operations_command("deploy",{"plan_id":plan["plan_id"]});e.step(3)
    assert e.demo.background.manifest()==before
    e.operations_command("rollback",{});e.step()
    assert e.demo.background.manifest()==before


def test_invalid_toggle_is_atomic_and_schedule_work_is_bounded():
    c=WorldController(config(BackgroundFaultConfig()))
    for args in ({},{"enabled":1},{"enabled":True,"seed":3}):
        with pytest.raises(ApiError):command(c,"background_set_enabled",args)
    assert not c.engine.demo.background.enabled
    with pytest.raises(ValueError,match="lane-ticks"):
        BackgroundFaultScheduler(BackgroundFaultConfig(horizon_ticks=10000,
            rules=tuple(rule(rule_id=str(i)) for i in range(16))),world(13),1)


def test_detector_imports_exclude_scheduler_and_truth_paths():
    for name in ("factor","preprocess","baselines","baselines_extra","kalman","hierarchy","decision"):
        for node in ast.walk(ast.parse((ROOT/f"canary_ssm/{name}.py").read_text())):
            if isinstance(node,ast.ImportFrom):
                assert not any(word in (node.module or "") for word in ("fault_scheduler","operations","faults"))
            if isinstance(node,ast.Import):
                assert not any(any(word in alias.name for word in ("fault_scheduler","operations","faults")) for alias in node.names)
