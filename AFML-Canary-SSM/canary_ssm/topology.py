"""Validated physical topology snapshots; no clock, workload, faults or inference.

IDs are nonempty strings, globally unique across topology entities. class_id is
the existing research model's nonnegative integer metadata class, not a rack ID.
Capacities and current usage use cores, MB (decimal megabytes), and Mbps.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path

from .configuration import read_yaml_mapping


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a nonempty string without surrounding whitespace")


def _number(value, name, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (value <= 0 if positive else value < 0)):
        bound = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a finite {bound} number")


def _record(cls, value):
    if not isinstance(value, dict):
        raise ValueError(f"{cls.__name__} must be a mapping")
    unknown = set(value) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"unknown {cls.__name__} fields: {sorted(unknown)}")
    try:
        return cls(**value)
    except TypeError as exc:
        raise ValueError(f"invalid {cls.__name__} fields: {exc}") from exc


@dataclass(frozen=True)
class DataCenter:
    data_center_id: str

    def __post_init__(self):
        _identifier(self.data_center_id, "data_center_id")


@dataclass(frozen=True)
class Rack:
    rack_id: str
    data_center_id: str

    def __post_init__(self):
        _identifier(self.rack_id, "rack_id")
        _identifier(self.data_center_id, "data_center_id")


@dataclass(frozen=True)
class HostCapacity:
    cpu_cores: int
    memory_mb: float
    disk_mb: float
    network_mbps: float

    def __post_init__(self):
        if type(self.cpu_cores) is not int or self.cpu_cores <= 0:
            raise ValueError("cpu_cores must be a positive integer")
        for name in ("memory_mb", "disk_mb", "network_mbps"):
            _number(getattr(self, name), name, positive=True)


@dataclass(frozen=True)
class HostUsage:
    cpu_cores: float = 0.0
    memory_mb: float = 0.0
    disk_mb: float = 0.0
    network_mbps: float = 0.0

    def __post_init__(self):
        for f in fields(self):
            _number(getattr(self, f.name), f"usage.{f.name}")


class HostLifecycle(str, Enum):
    READY = "ready"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


@dataclass(frozen=True)
class Host:
    host_id: str
    rack_id: str
    data_center_id: str
    class_id: int
    capacity: HostCapacity
    usage: HostUsage = field(default_factory=HostUsage)
    lifecycle: HostLifecycle = HostLifecycle.READY

    def __post_init__(self):
        for name in ("host_id", "rack_id", "data_center_id"):
            _identifier(getattr(self, name), name)
        if type(self.class_id) is not int or self.class_id < 0:
            raise ValueError("class_id must be a nonnegative integer")
        if not isinstance(self.capacity, HostCapacity) or not isinstance(self.usage, HostUsage):
            raise ValueError("host capacity/usage must be HostCapacity/HostUsage records")
        try:
            object.__setattr__(self, "lifecycle", HostLifecycle(self.lifecycle))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid host lifecycle: {self.lifecycle!r}") from exc
        for f in fields(self.usage):
            if getattr(self.usage, f.name) > getattr(self.capacity, f.name):
                raise ValueError(f"host {self.host_id}: usage.{f.name} exceeds capacity")


@dataclass(frozen=True)
class ServiceReplica:
    service_id: str
    replica_id: str
    host_id: str
    release_id: str

    def __post_init__(self):
        for f in fields(self):
            _identifier(getattr(self, f.name), f.name)


@dataclass(frozen=True)
class Topology:
    data_centers: tuple[DataCenter, ...]
    racks: tuple[Rack, ...]
    hosts: tuple[Host, ...]
    replicas: tuple[ServiceReplica, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported topology schema_version; expected 1")
        seen = set()
        for name, cls, key in (("data_centers", DataCenter, "data_center_id"),
                               ("racks", Rack, "rack_id"), ("hosts", Host, "host_id"),
                               ("replicas", ServiceReplica, "replica_id")):
            records = getattr(self, name)
            if not isinstance(records, (list, tuple)):
                raise ValueError(f"{name} must be a list or tuple")
            object.__setattr__(self, name, tuple(records))
            for record in records:
                if not isinstance(record, cls):
                    raise ValueError(f"{name} must contain {cls.__name__} records")
                entity_id = getattr(record, key)
                if entity_id in seen:
                    raise ValueError(f"duplicate topology ID: {entity_id}")
                seen.add(entity_id)
        if not self.data_centers:
            raise ValueError("topology requires at least one data center")
        centers = {x.data_center_id for x in self.data_centers}
        racks = {x.rack_id: x for x in self.racks}
        hosts = {x.host_id: x for x in self.hosts}
        for rack in self.racks:
            if rack.data_center_id not in centers:
                raise ValueError(f"rack {rack.rack_id}: unknown data_center_id {rack.data_center_id}")
        for host in self.hosts:
            if host.rack_id not in racks:
                raise ValueError(f"host {host.host_id}: unknown rack_id {host.rack_id}")
            if host.data_center_id != racks[host.rack_id].data_center_id:
                raise ValueError(f"host {host.host_id}: conflicting data-center/rack parentage")
        for replica in self.replicas:
            if replica.host_id not in hosts:
                raise ValueError(f"replica {replica.replica_id}: unknown host_id {replica.host_id}")

    def snapshot(self) -> dict:
        """Return detached JSON-compatible data; preserve configured entity ordering."""
        value = asdict(self)
        for name in ("data_centers", "racks", "hosts", "replicas"):
            value[name] = list(value[name])
        for host in value["hosts"]:
            host["lifecycle"] = host["lifecycle"].value
        return value

    @classmethod
    def from_dict(cls, value: dict) -> Topology:
        if not isinstance(value, dict):
            raise ValueError("topology must be a mapping")
        required = {"schema_version", "data_centers", "racks", "hosts"}
        allowed = required | {"replicas"}
        if set(value) - allowed or required - set(value):
            raise ValueError(f"invalid topology keys; missing={sorted(required - set(value))}, "
                             f"unknown={sorted(set(value) - allowed)}")
        parsed = {}
        for name, typ in (("data_centers", DataCenter), ("racks", Rack),
                          ("hosts", Host), ("replicas", ServiceReplica)):
            rows = value.get(name, [])
            if not isinstance(rows, list):
                raise ValueError(f"{name} must be a list")
            records = []
            for row in rows:
                if name == "hosts" and isinstance(row, dict):
                    row = dict(row)
                    row["capacity"] = _record(HostCapacity, row.get("capacity"))
                    row["usage"] = _record(HostUsage, row.get("usage", {}))
                records.append(_record(typ, row))
            parsed[name] = tuple(records)
        return cls(**parsed, schema_version=value["schema_version"])


def load_topology(path: str | Path) -> Topology:
    """Load a project YAML config's topology section or a saved bare snapshot."""
    cfg = read_yaml_mapping(path)
    return Topology.from_dict(cfg["topology"] if "topology" in cfg else cfg)
