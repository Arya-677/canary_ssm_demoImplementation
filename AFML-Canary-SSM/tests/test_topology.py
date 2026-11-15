"""Topology acceptance tests with independent fixture counts and broken references."""
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from canary_ssm.configuration import read_yaml_mapping
from canary_ssm.experiments import load_config
from canary_ssm.topology import HostUsage, Topology, load_topology

FIXTURE = Path(__file__).resolve().parents[1] / "configs" / "world_interactive.yaml"


@pytest.fixture
def snapshot():
    return load_topology(FIXTURE).snapshot()


def test_interactive_fixture_and_json_yaml_roundtrip(tmp_path):
    world = load_topology(FIXTURE)
    assert len(world.data_centers) == 1
    assert len(world.racks) == 4
    assert len(world.hosts) == len({h.host_id for h in world.hosts}) == 20
    assert len(world.replicas) == 20
    for rack in world.racks:
        assert sum(h.rack_id == rack.rack_id for h in world.hosts) == 5
        assert rack.data_center_id == "dc-01"
    assert {h.class_id for h in world.hosts} == {0, 1}
    hosts = {h.host_id: h for h in world.hosts}
    assert all(r.host_id in hosts for r in world.replicas)
    raw = world.snapshot()
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(raw, allow_nan=False))
    assert load_topology(path) == world
    assert Topology.from_dict(load_config(FIXTURE)["topology"]) == world
    # A caller changing a serialized copy cannot mutate the live records.
    raw["hosts"][0]["capacity"]["memory_mb"] = 1
    assert world.hosts[0].capacity.memory_mb == 16000


@pytest.mark.parametrize("collection", ["data_centers", "racks", "hosts", "replicas"])
def test_duplicate_entity_ids_rejected(snapshot, collection):
    snapshot[collection].append(dict(snapshot[collection][0]))
    with pytest.raises(ValueError, match="duplicate topology ID"):
        Topology.from_dict(snapshot)


def test_duplicate_host_with_conflicting_parent_rejected(snapshot):
    host = dict(snapshot["hosts"][0], rack_id="rack-02")
    snapshot["hosts"].append(host)
    with pytest.raises(ValueError, match="duplicate topology ID"):
        Topology.from_dict(snapshot)


@pytest.mark.parametrize("collection,key,value,error", [
    ("racks", "data_center_id", "absent", "unknown data_center_id"),
    ("hosts", "rack_id", "absent", "unknown rack_id"),
    ("hosts", "data_center_id", "absent", "conflicting.*parentage"),
    ("replicas", "host_id", "absent", "unknown host_id"),
])
def test_orphan_records_rejected(snapshot, collection, key, value, error):
    snapshot[collection][0][key] = value
    with pytest.raises(ValueError, match=error):
        Topology.from_dict(snapshot)


def test_conflicting_existing_center_rejected(snapshot):
    snapshot["data_centers"].append({"data_center_id": "dc-02"})
    snapshot["hosts"][0]["data_center_id"] = "dc-02"
    with pytest.raises(ValueError, match="conflicting.*parentage"):
        Topology.from_dict(snapshot)


@pytest.mark.parametrize("name", ["cpu_cores", "memory_mb", "disk_mb", "network_mbps"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "8"])
def test_invalid_capacity_rejected(snapshot, name, value):
    snapshot["hosts"][0]["capacity"][name] = value
    with pytest.raises(ValueError):
        Topology.from_dict(snapshot)


@pytest.mark.parametrize("name", ["cpu_cores", "memory_mb", "disk_mb", "network_mbps"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "0", 1000000])
def test_invalid_or_over_capacity_usage_rejected(snapshot, name, value):
    snapshot["hosts"][0]["usage"][name] = value
    with pytest.raises(ValueError):
        Topology.from_dict(snapshot)


def test_usage_lifecycle_and_capacity_are_separate():
    host = load_topology(FIXTURE).hosts[0]
    with pytest.raises(FrozenInstanceError):
        host.capacity.memory_mb = 32
    with pytest.raises(FrozenInstanceError):
        host.host_id = "renamed"
    current = replace(host, usage=HostUsage(cpu_cores=2, memory_mb=100), lifecycle="maintenance")
    assert current.capacity == host.capacity
    assert current.host_id == host.host_id
    assert host.usage.memory_mb == 0
    assert current.usage.memory_mb == 100
    assert current.lifecycle.value == "maintenance"


@pytest.mark.parametrize("collection,key,value", [
    ("hosts", "class_id", -1), ("hosts", "class_id", True),
    ("hosts", "class_id", "0"), ("hosts", "lifecycle", "broken"),
    ("hosts", "host_id", ""), ("hosts", "host_id", " host-01-01 "),
    ("replicas", "release_id", ""), ("replicas", "service_id", None),
])
def test_invalid_metadata_rejected(snapshot, collection, key, value):
    snapshot[collection][0][key] = value
    with pytest.raises(ValueError):
        Topology.from_dict(snapshot)


def test_schema_unknown_fields_and_missing_capacity_rejected(snapshot):
    snapshot["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        Topology.from_dict(snapshot)
    snapshot["schema_version"] = 1
    snapshot["hosts"][0]["capacitty"] = {}
    with pytest.raises(ValueError, match="unknown Host fields"):
        Topology.from_dict(snapshot)
    del snapshot["hosts"][0]["capacitty"]
    del snapshot["hosts"][0]["capacity"]
    with pytest.raises(ValueError, match="HostCapacity"):
        Topology.from_dict(snapshot)


def test_minimal_custom_config_defaults(tmp_path):
    p = tmp_path / "small.yaml"
    p.write_text('''topology:
  schema_version: 1
  data_centers: [{data_center_id: custom-dc}]
  racks: [{rack_id: custom-rack, data_center_id: custom-dc}]
  hosts:
    - host_id: custom-host
      rack_id: custom-rack
      data_center_id: custom-dc
      class_id: 4
      capacity: {cpu_cores: 2, memory_mb: 4000, disk_mb: 8000, network_mbps: 100}
''')
    world = load_topology(p)
    assert len(world.hosts) == 1
    assert world.hosts[0].usage == HostUsage()
    assert world.hosts[0].lifecycle.value == "ready"
    assert world.replicas == ()


@pytest.mark.parametrize("contents", ["[]", "", "topology: [", "topology: {}\ntopology: {}"])
def test_bad_yaml_rejected(tmp_path, contents):
    p = tmp_path / "bad.yaml"
    p.write_text(contents)
    with pytest.raises(ValueError):
        load_topology(p)


def test_duplicate_yaml_parent_key_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("host: {rack_id: rack-01, rack_id: rack-02}")
    with pytest.raises(ValueError, match="duplicate configuration key: rack_id"):
        read_yaml_mapping(p)


def test_cli_snapshot_and_validation_error(tmp_path, capsys):
    from canary_ssm.cli import main
    main(["topology", "--config", str(FIXTURE)])
    printed = json.loads(capsys.readouterr().out)
    assert len(printed["hosts"]) == 20
    out = tmp_path / "nested" / "snapshot.json"
    main(["topology", "--config", str(FIXTURE), "--out", str(out)])
    assert load_topology(out).snapshot() == printed
    bad = tmp_path / "bad.yaml"
    bad.write_text("topology: {}")
    with pytest.raises(SystemExit) as exc:
        main(["topology", "--config", str(bad)])
    assert exc.value.code == 2
    assert "invalid topology keys" in capsys.readouterr().err
