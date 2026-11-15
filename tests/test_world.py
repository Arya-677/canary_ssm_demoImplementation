"""Tests for Virtual Data Center: Fleet topology, SimulatedClock, and EventQueue (Prompt 1)."""
from __future__ import annotations

import copy
import pytest

from canary_ssm.world import (
    Fleet,
    Rack,
    Server,
    SimulatedClock,
    Event,
    EventQueue,
    VirtualWorld,
    create_default_fleet,
)
from canary_ssm import cli


# =====================================================================
# 1. Topology & Record Constraints
# =====================================================================
def test_default_fleet_topology():
    """Default fleet must contain 4 racks of 6 servers (24 total) with stable IDs."""
    fleet = create_default_fleet()
    assert fleet.total_racks == 4
    assert fleet.total_servers == 24

    racks = fleet.list_racks()
    assert len(racks) == 4
    expected_rack_ids = [f"rack-{i}" for i in range(4)]
    assert [r.rack_id for r in racks] == expected_rack_ids

    servers = fleet.list_servers()
    assert len(servers) == 24
    assert len(set(s.server_id for s in servers)) == 24

    # Verify per-rack server count, IDs, and class distribution
    for r_idx, rack in enumerate(racks):
        assert len(rack.servers) == 6
        assert rack.switch_id == f"tor-rack-{r_idx}"
        assert rack.online is True

        classes = [s.class_id for s in rack.servers.values()]
        # 6 servers per rack with 2 classes -> balanced: 3 class 0, 3 class 1
        assert classes.count(0) == 3
        assert classes.count(1) == 3

        for s_idx, (sid, srv) in enumerate(rack.servers.items()):
            assert sid == f"srv-r{r_idx}-s{s_idx}"
            assert srv.rack_id == f"rack-{r_idx}"
            assert srv.online is True
            assert srv.installed_version == "v1.0.0-baseline"
            assert srv.memory_capacity_mb == 16384.0
            assert srv.cpu_cores == 16
            assert srv.base_latency_ms == 100.0


def test_custom_fleet_topology():
    """Custom fleet dimensions must scale accurately."""
    fleet = create_default_fleet(n_racks=2, servers_per_rack=4, n_classes=2)
    assert fleet.total_racks == 2
    assert fleet.total_servers == 8
    summary = fleet.summary()
    assert summary["total_racks"] == 2
    assert summary["total_servers"] == 8
    assert summary["class_distribution"] == {0: 4, 1: 4}


def test_reject_duplicate_server_ids():
    """Must reject duplicate server IDs within a rack and across different racks."""
    # Within same rack
    srv1 = Server(server_id="srv-01", rack_id="rack-0", class_id=0)
    srv1_dup = Server(server_id="srv-01", rack_id="rack-0", class_id=1)
    with pytest.raises(ValueError, match="already exists"):
        rack = Rack(rack_id="rack-0", switch_id="tor-0", servers={"srv-01": srv1})
        rack.add_server(srv1_dup)

    # Across different racks in a fleet
    rack0 = Rack(rack_id="rack-0", switch_id="tor-0", servers={"srv-shared": Server("srv-shared", "rack-0", 0)})
    rack1 = Rack(rack_id="rack-1", switch_id="tor-1", servers={"srv-shared": Server("srv-shared", "rack-1", 1)})
    with pytest.raises(ValueError, match="Duplicate server ID detected across fleet"):
        Fleet(fleet_id="fleet-dup", racks={"rack-0": rack0, "rack-1": rack1})


def test_reject_invalid_capacities():
    """Must reject non-positive capacities and latencies with informative errors."""
    with pytest.raises(ValueError, match="memory_capacity_mb must be strictly positive"):
        Server(server_id="s1", rack_id="r1", class_id=0, memory_capacity_mb=0.0)

    with pytest.raises(ValueError, match="memory_capacity_mb must be strictly positive"):
        Server(server_id="s1", rack_id="r1", class_id=0, memory_capacity_mb=-1024.0)

    with pytest.raises(ValueError, match="cpu_cores must be strictly positive"):
        Server(server_id="s1", rack_id="r1", class_id=0, cpu_cores=0)

    with pytest.raises(ValueError, match="base_latency_ms must be strictly positive"):
        Server(server_id="s1", rack_id="r1", class_id=0, base_latency_ms=-5.0)

    with pytest.raises(ValueError, match="class_id must be a non-negative integer"):
        Server(server_id="s1", rack_id="r1", class_id=-1)


def test_serialization_roundtrip():
    """Fleet, Rack, and Server must serialize to dict and restore identically."""
    f1 = create_default_fleet(n_racks=3, servers_per_rack=4)
    d = f1.to_dict()
    f2 = Fleet.from_dict(d)
    assert f1.fleet_id == f2.fleet_id
    assert f1.total_servers == f2.total_servers
    assert f1.total_racks == f2.total_racks
    for s1, s2 in zip(f1.list_servers(), f2.list_servers()):
        assert s1.to_dict() == s2.to_dict()


# =====================================================================
# 2. Clock and Event Queue Operations
# =====================================================================
def test_clock_operations():
    """SimulatedClock start, pause, step, reset operate on discrete time."""
    clk = SimulatedClock(tick=0, is_paused=True)
    assert clk.current_tick == 0
    assert clk.is_paused is True

    clk.start()
    assert clk.is_paused is False

    new_tick = clk.step(5)
    assert new_tick == 5
    assert clk.current_tick == 5

    clk.pause()
    assert clk.is_paused is True

    clk.reset(initial_tick=0)
    assert clk.current_tick == 0
    assert clk.is_paused is True

    with pytest.raises(ValueError, match="negative"):
        clk.step(-1)


def test_event_queue_priority_and_fifo():
    """EventQueue must strictly order events by (tick, priority, seq)."""
    eq = EventQueue()
    ev1 = eq.schedule(tick=10, event_type="LOW_PRI", priority=20)
    ev2 = eq.schedule(tick=5, event_type="EARLY", priority=10)
    ev3 = eq.schedule(tick=10, event_type="HIGH_PRI", priority=5)
    ev4 = eq.schedule(tick=10, event_type="SAME_PRI_1", priority=10)
    ev5 = eq.schedule(tick=10, event_type="SAME_PRI_2", priority=10)

    assert eq.count() == 5
    popped = eq.pop_until(target_tick=10)
    assert len(popped) == 5

    types = [e.event_type for e in popped]
    # Expected order:
    # 1. tick 5
    # 2. tick 10, pri 5
    # 3. tick 10, pri 10 (seq 4)
    # 4. tick 10, pri 10 (seq 5)
    # 5. tick 10, pri 20
    assert types == ["EARLY", "HIGH_PRI", "SAME_PRI_1", "SAME_PRI_2", "LOW_PRI"]


# =====================================================================
# 3. World Engine & Determinism Guarantees
# =====================================================================
def test_advancing_n_ticks_matches_n_single_steps():
    """Advancing N ticks together (step(N)) must match calling step(1) N times."""
    # World A: single step(10)
    world_a = VirtualWorld(seed=12345)
    world_a.schedule_event(tick=3, event_type="SET_SERVER_ONLINE", target_id="srv-r0-s0", payload={"online": False})
    world_a.schedule_event(tick=7, event_type="SET_SERVER_VERSION", target_id="srv-r1-s2", payload={"version": "v1.1.0-canary"})
    world_a.schedule_event(tick=10, event_type="SET_RACK_ONLINE", target_id="rack-2", payload={"online": False})

    res_a = world_a.step(10)

    # World B: ten steps of step(1)
    world_b = VirtualWorld(seed=12345)
    world_b.schedule_event(tick=3, event_type="SET_SERVER_ONLINE", target_id="srv-r0-s0", payload={"online": False})
    world_b.schedule_event(tick=7, event_type="SET_SERVER_VERSION", target_id="srv-r1-s2", payload={"version": "v1.1.0-canary"})
    world_b.schedule_event(tick=10, event_type="SET_RACK_ONLINE", target_id="rack-2", payload={"online": False})

    all_res_b = []
    for _ in range(10):
        all_res_b.append(world_b.step(1))

    # Assert clock tick matches
    assert world_a.clock.tick == 10
    assert world_b.clock.tick == 10

    # Assert executed event history matches exactly
    assert len(world_a.event_history) == 3
    assert len(world_b.event_history) == 3
    assert world_a.event_history == world_b.event_history

    # Assert topology state matches bitwise
    assert world_a.fleet.to_dict() == world_b.fleet.to_dict()
    assert world_a.fleet.get_server("srv-r0-s0").online is False
    assert world_b.fleet.get_server("srv-r0-s0").online is False
    assert world_a.fleet.get_server("srv-r1-s2").installed_version == "v1.1.0-canary"
    assert world_b.fleet.get_server("srv-r1-s2").installed_version == "v1.1.0-canary"
    assert world_a.fleet.get_rack("rack-2").online is False
    assert world_b.fleet.get_rack("rack-2").online is False


def test_reset_reproduces_same_world():
    """Reset with the same config and seed must reproduce the exact same world."""
    world = VirtualWorld(seed=9999)
    initial_topology = copy.deepcopy(world.fleet.to_dict())

    # Schedule events and advance
    world.schedule_event(tick=5, event_type="SET_SERVER_ONLINE", target_id="srv-r2-s1", payload={"online": False})
    world.schedule_event(tick=15, event_type="SET_SERVER_VERSION", target_id="srv-r3-s4", payload={"version": "v2.0.0-rc1"})
    res1 = world.step(20)
    assert res1.tick == 20
    assert world.fleet.get_server("srv-r2-s1").online is False
    assert world.fleet.get_server("srv-r3-s4").installed_version == "v2.0.0-rc1"
    history1 = copy.deepcopy(world.event_history)

    # Reset
    world.reset()
    assert world.clock.tick == 0
    assert world.clock.is_paused is True
    assert world.fleet.to_dict() == initial_topology
    assert world.event_queue.count() == 0
    assert len(world.event_history) == 0

    # Re-run identical run
    world.schedule_event(tick=5, event_type="SET_SERVER_ONLINE", target_id="srv-r2-s1", payload={"online": False})
    world.schedule_event(tick=15, event_type="SET_SERVER_VERSION", target_id="srv-r3-s4", payload={"version": "v2.0.0-rc1"})
    res2 = world.step(20)
    assert res2.tick == 20
    assert world.event_history == history1
    assert world.fleet.get_server("srv-r2-s1").online is False
    assert world.fleet.get_server("srv-r3-s4").installed_version == "v2.0.0-rc1"


def test_bounded_fast_forward():
    """Fast-forward advances up to until_tick, with safety limits and backward protection."""
    world = VirtualWorld(seed=42)
    world.schedule_event(tick=12, event_type="SET_SERVER_ONLINE", target_id="srv-r0-s1", payload={"online": False})

    res = world.fast_forward(until_tick=15, max_ticks=100)
    assert res.tick == 15
    assert res.ticks_advanced == 15
    assert len(res.events_executed) == 1
    assert world.fleet.get_server("srv-r0-s1").online is False

    # Cannot fast forward backward
    with pytest.raises(ValueError, match="Cannot fast-forward backward"):
        world.fast_forward(until_tick=10)

    # Exceeding max_ticks boundary
    with pytest.raises(ValueError, match="exceeds max_ticks limit"):
        world.fast_forward(until_tick=200, max_ticks=50)


# =====================================================================
# 4. CLI World Subcommand Verification
# =====================================================================
def test_cli_world_topology_and_json(capsys):
    """CLI world command must output topology in human-readable and JSON format."""
    cli.main(["world", "--topology"])
    out = capsys.readouterr().out
    assert "Fleet Topology Summary (fleet-default):" in out
    assert "Total Racks: 4" in out
    assert "Total Servers: 24" in out

    cli.main(["world", "--topology", "--json"])
    out_json = capsys.readouterr().out
    import json
    data = json.loads(out_json)
    assert data["total_racks"] == 4
    assert data["total_servers"] == 24
    assert data["class_distribution"] == {"0": 12, "1": 12}


def test_cli_world_step(capsys):
    """CLI world step command advances simulation ticks."""
    cli.main(["world", "--step", "5"])
    out = capsys.readouterr().out
    assert "World stepped by 5 ticks -> current tick: 5" in out

    cli.main(["world", "--step", "12", "--json"])
    out_json = capsys.readouterr().out
    import json
    data = json.loads(out_json)
    assert data["action"] == "step"
    assert data["ticks_advanced"] == 12
    assert data["tick"] == 12


def test_cli_world_inspect(capsys):
    """CLI world inspect command lists detailed server attributes."""
    cli.main(["world", "--inspect"])
    out = capsys.readouterr().out
    assert "srv-r0-s0: class=0" in out
    assert "mem=16384.0MB" in out
    assert "cpu=16" in out
