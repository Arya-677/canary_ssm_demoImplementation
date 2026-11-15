"""Configurable Fleet, Rack, and Server records for the Virtual Data Center.

Enforces:
- Stable IDs for racks and servers
- Explicit hardware/service class IDs
- Strict validation: capacities must be positive (>0), no duplicate server IDs
- Online state and installed version tracking
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ServerResourceState:
    """Current dynamic numerical workload and resource state of a server."""
    workload_demand: float = 0.0          # Current effective log workload demand
    request_count: int = 6000             # Requests served in current 1-minute window
    cpu_fraction: float = 0.25            # Current CPU utilization in [0.0, 1.0]
    memory_mb: float = 2048.0             # Current resident process memory in MB
    latency_ms: float = 100.0             # Geometric mean latency over current window in ms
    log_latency: float = 4.60517          # log(latency_ms)
    error_count: int = 3                  # Error requests in current window
    noise_ar: float = 0.0                 # Current host-level temporal AR(1) latency noise
    mem_noise_ar: float = 0.0             # Current memory AR(1) noise state in MB
    observed: bool = True                 # Whether record was successfully observed

    def to_dict(self) -> dict[str, Any]:
        return {
            "workload_demand": round(float(self.workload_demand), 4),
            "request_count": int(self.request_count),
            "cpu_fraction": round(float(self.cpu_fraction), 4),
            "memory_mb": round(float(self.memory_mb), 2),
            "latency_ms": round(float(self.latency_ms), 4),
            "log_latency": round(float(self.log_latency), 4),
            "error_count": int(self.error_count),
            "noise_ar": round(float(self.noise_ar), 6),
            "mem_noise_ar": round(float(self.mem_noise_ar), 6),
            "observed": bool(self.observed),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ServerResourceState":
        return cls(
            workload_demand=float(d.get("workload_demand", 0.0)),
            request_count=int(d.get("request_count", 6000)),
            cpu_fraction=float(d.get("cpu_fraction", 0.25)),
            memory_mb=float(d.get("memory_mb", 2048.0)),
            latency_ms=float(d.get("latency_ms", 100.0)),
            log_latency=float(d.get("log_latency", 4.60517)),
            error_count=int(d.get("error_count", 3)),
            noise_ar=float(d.get("noise_ar", 0.0)),
            mem_noise_ar=float(d.get("mem_noise_ar", 0.0)),
            observed=bool(d.get("observed", True)),
        )


@dataclass
class Server:
    """Simulated host in a datacenter rack.

    Attributes:
        server_id: Stable unique server identifier across the entire fleet.
        rack_id: Identifier of the rack housing this server.
        class_id: Hardware or service class (e.g. 0 for x86_standard, 1 for arm64_highmem).
        base_memory_mb: Nominal baseline memory consumption in Megabytes (> 0).
        memory_capacity_mb: Physical/allocated memory capacity in Megabytes (> 0).
        cpu_cores: Number of logical CPU cores (> 0).
        base_latency_ms: Baseline latency in milliseconds (> 0).
        workload_elasticity: Workload slope (beta_i) relating log workload to latency.
        factor_loading: Shared factor loading (lambda_i).
        online: Whether the host is powered on and healthy.
        installed_version: Installed software release version tag.
        current_state: Current dynamic numerical resource state.
        metadata: Arbitrary user tags (zone, role, etc.).
    """
    server_id: str
    rack_id: str
    class_id: int
    base_memory_mb: float = 2048.0
    memory_capacity_mb: float = 16384.0
    cpu_cores: int = 16
    base_latency_ms: float = 100.0
    workload_elasticity: float = 0.15
    factor_loading: float = 1.0
    online: bool = True
    installed_version: str = "v1.0.0-baseline"
    current_state: ServerResourceState = field(default_factory=ServerResourceState)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.server_id or not isinstance(self.server_id, str):
            raise ValueError(f"server_id must be a non-empty string, got {self.server_id!r}")
        if not self.rack_id or not isinstance(self.rack_id, str):
            raise ValueError(f"rack_id must be a non-empty string, got {self.rack_id!r}")
        if not isinstance(self.class_id, int) or self.class_id < 0:
            raise ValueError(f"class_id must be a non-negative integer, got {self.class_id!r}")
        if self.base_memory_mb <= 0:
            raise ValueError(f"base_memory_mb must be strictly positive, got {self.base_memory_mb}")
        if self.memory_capacity_mb <= 0:
            raise ValueError(f"memory_capacity_mb must be strictly positive, got {self.memory_capacity_mb}")
        if self.base_memory_mb > self.memory_capacity_mb:
            raise ValueError(
                f"base_memory_mb ({self.base_memory_mb}) cannot exceed memory_capacity_mb ({self.memory_capacity_mb})"
            )
        if self.cpu_cores <= 0:
            raise ValueError(f"cpu_cores must be strictly positive, got {self.cpu_cores}")
        if self.base_latency_ms <= 0:
            raise ValueError(f"base_latency_ms must be strictly positive, got {self.base_latency_ms}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "rack_id": self.rack_id,
            "class_id": self.class_id,
            "base_memory_mb": float(self.base_memory_mb),
            "memory_capacity_mb": float(self.memory_capacity_mb),
            "cpu_cores": int(self.cpu_cores),
            "base_latency_ms": float(self.base_latency_ms),
            "workload_elasticity": float(self.workload_elasticity),
            "factor_loading": float(self.factor_loading),
            "online": bool(self.online),
            "installed_version": str(self.installed_version),
            "current_state": self.current_state.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Server":
        state_dict = d.get("current_state")
        state = ServerResourceState.from_dict(state_dict) if state_dict else ServerResourceState()
        return cls(
            server_id=str(d["server_id"]),
            rack_id=str(d["rack_id"]),
            class_id=int(d["class_id"]),
            base_memory_mb=float(d.get("base_memory_mb", 2048.0)),
            memory_capacity_mb=float(d.get("memory_capacity_mb", 16384.0)),
            cpu_cores=int(d.get("cpu_cores", 16)),
            base_latency_ms=float(d.get("base_latency_ms", 100.0)),
            workload_elasticity=float(d.get("workload_elasticity", 0.15)),
            factor_loading=float(d.get("factor_loading", 1.0)),
            online=bool(d.get("online", True)),
            installed_version=str(d.get("installed_version", "v1.0.0-baseline")),
            current_state=state,
            metadata=dict(d.get("metadata", {})),
        )


@dataclass
class Rack:
    """Datacenter rack grouping servers with shared Top-of-Rack (ToR) switch and power.

    Attributes:
        rack_id: Stable unique rack identifier.
        switch_id: Top-of-Rack network switch identifier.
        servers: Mapping of server_id -> Server instance.
        online: Whether the rack infrastructure (switch/power) is functional.
        metadata: Arbitrary rack tags.
    """
    rack_id: str
    switch_id: str
    servers: dict[str, Server] = field(default_factory=dict)
    online: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rack_id or not isinstance(self.rack_id, str):
            raise ValueError(f"rack_id must be a non-empty string, got {self.rack_id!r}")
        if not self.switch_id or not isinstance(self.switch_id, str):
            raise ValueError(f"switch_id must be a non-empty string, got {self.switch_id!r}")

        # Validate servers belong to this rack and have distinct IDs
        seen: set[str] = set()
        for sid, srv in self.servers.items():
            if sid != srv.server_id:
                raise ValueError(f"Server key {sid!r} does not match server.server_id {srv.server_id!r}")
            if sid in seen:
                raise ValueError(f"Duplicate server ID detected in rack {self.rack_id}: {sid!r}")
            seen.add(sid)
            if srv.rack_id != self.rack_id:
                raise ValueError(
                    f"Server {sid} has rack_id {srv.rack_id!r}, expected {self.rack_id!r}"
                )

    def add_server(self, server: Server) -> None:
        if server.server_id in self.servers:
            raise ValueError(f"Server {server.server_id!r} already exists in rack {self.rack_id}")
        if server.rack_id != self.rack_id:
            raise ValueError(
                f"Server {server.server_id} has rack_id {server.rack_id!r}, expected {self.rack_id!r}"
            )
        self.servers[server.server_id] = server

    def get_server(self, server_id: str) -> Server:
        if server_id not in self.servers:
            raise KeyError(f"Server {server_id!r} not found in rack {self.rack_id}")
        return self.servers[server_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rack_id": self.rack_id,
            "switch_id": self.switch_id,
            "online": bool(self.online),
            "metadata": dict(self.metadata),
            "servers": {sid: srv.to_dict() for sid, srv in self.servers.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rack":
        srvs = {sid: Server.from_dict(sd) for sid, sd in d.get("servers", {}).items()}
        return cls(
            rack_id=str(d["rack_id"]),
            switch_id=str(d.get("switch_id", f"tor-{d['rack_id']}")),
            servers=srvs,
            online=bool(d.get("online", True)),
            metadata=dict(d.get("metadata", {})),
        )


@dataclass
class Fleet:
    """Datacenter fleet containing racks and simulated servers.

    Attributes:
        fleet_id: Unique fleet identifier.
        racks: Mapping of rack_id -> Rack instance.
        metadata: Arbitrary fleet-level metadata.
    """
    fleet_id: str = "fleet-default"
    racks: dict[str, Rack] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fleet_id or not isinstance(self.fleet_id, str):
            raise ValueError(f"fleet_id must be a non-empty string, got {self.fleet_id!r}")

        # Validate global uniqueness of server IDs across all racks
        all_servers: set[str] = set()
        for rid, rack in self.racks.items():
            if rid != rack.rack_id:
                raise ValueError(f"Rack key {rid!r} does not match rack.rack_id {rack.rack_id!r}")
            for sid in rack.servers:
                if sid in all_servers:
                    raise ValueError(f"Duplicate server ID detected across fleet: {sid!r}")
                all_servers.add(sid)

    def add_rack(self, rack: Rack) -> None:
        if rack.rack_id in self.racks:
            raise ValueError(f"Rack {rack.rack_id!r} already exists in fleet {self.fleet_id}")
        # Check server ID collisions
        existing = set(self.list_server_ids())
        new_ids = set(rack.servers.keys())
        overlap = existing & new_ids
        if overlap:
            raise ValueError(f"Duplicate server IDs detected when adding rack {rack.rack_id}: {sorted(overlap)}")
        self.racks[rack.rack_id] = rack

    def get_rack(self, rack_id: str) -> Rack:
        if rack_id not in self.racks:
            raise KeyError(f"Rack {rack_id!r} not found in fleet {self.fleet_id}")
        return self.racks[rack_id]

    def get_server(self, server_id: str) -> Server:
        for rack in self.racks.values():
            if server_id in rack.servers:
                return rack.servers[server_id]
        raise KeyError(f"Server {server_id!r} not found in fleet {self.fleet_id}")

    def list_racks(self) -> list[Rack]:
        return [self.racks[rid] for rid in sorted(self.racks.keys())]

    def list_servers(self) -> list[Server]:
        servers: list[Server] = []
        for rack in self.list_racks():
            for sid in sorted(rack.servers.keys()):
                servers.append(rack.servers[sid])
        return servers

    def list_server_ids(self) -> list[str]:
        return [s.server_id for s in self.list_servers()]

    @property
    def total_racks(self) -> int:
        return len(self.racks)

    @property
    def total_servers(self) -> int:
        return sum(len(r.servers) for r in self.racks.values())

    def summary(self) -> dict[str, Any]:
        classes: dict[int, int] = {}
        versions: dict[str, int] = {}
        online_count = 0
        total = 0
        for srv in self.list_servers():
            total += 1
            if srv.online:
                online_count += 1
            classes[srv.class_id] = classes.get(srv.class_id, 0) + 1
            versions[srv.installed_version] = versions.get(srv.installed_version, 0) + 1

        return {
            "fleet_id": self.fleet_id,
            "total_racks": self.total_racks,
            "total_servers": total,
            "online_servers": online_count,
            "class_distribution": classes,
            "version_distribution": versions,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "fleet_id": self.fleet_id,
            "metadata": dict(self.metadata),
            "racks": {rid: rack.to_dict() for rid, rack in self.racks.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Fleet":
        racks = {rid: Rack.from_dict(rd) for rid, rd in d.get("racks", {}).items()}
        return cls(
            fleet_id=str(d.get("fleet_id", "fleet-default")),
            racks=racks,
            metadata=dict(d.get("metadata", {})),
        )


def create_default_fleet(
    n_racks: int = 4,
    servers_per_rack: int = 6,
    n_classes: int = 2,
    default_version: str = "v1.0.0-baseline",
    memory_capacity_mb: float = 16384.0,
    cpu_cores: int = 16,
    base_latency_ms: float = 100.0,
    fleet_id: str = "fleet-default",
) -> Fleet:
    """Creates the standard virtual datacenter fleet.

    Default topology:
    - 4 racks: rack-0 through rack-3
    - 6 servers per rack: srv-r0-s0 .. srv-r3-s5 (24 servers total)
    - 2 compatibility classes evenly partitioned:
      Class 0: servers 0, 1, 2 in each rack (3 per rack)
      Class 1: servers 3, 4, 5 in each rack (3 per rack)
    This balanced topology guarantees that any single-canary per rack allocation
    leaves at least two same-rack same-class baseline controls, strictly satisfying
    the identifiability condition.
    """
    if n_racks <= 0:
        raise ValueError(f"n_racks must be positive, got {n_racks}")
    if servers_per_rack <= 0:
        raise ValueError(f"servers_per_rack must be positive, got {servers_per_rack}")
    if n_classes <= 0:
        raise ValueError(f"n_classes must be positive, got {n_classes}")

    racks: dict[str, Rack] = {}
    servers_per_class = max(1, servers_per_rack // n_classes)

    for r in range(n_racks):
        rack_id = f"rack-{r}"
        switch_id = f"tor-{rack_id}"
        rack_servers: dict[str, Server] = {}

        for s in range(servers_per_rack):
            server_id = f"srv-r{r}-s{s}"
            # Block-balanced class assignment: e.g. for 6 servers, 2 classes -> [0,0,0, 1,1,1]
            class_id = min(s // servers_per_class, n_classes - 1)

            srv = Server(
                server_id=server_id,
                rack_id=rack_id,
                class_id=class_id,
                memory_capacity_mb=memory_capacity_mb,
                cpu_cores=cpu_cores,
                base_latency_ms=base_latency_ms,
                online=True,
                installed_version=default_version,
                metadata={"rack_index": r, "slot_index": s},
            )
            rack_servers[server_id] = srv

        racks[rack_id] = Rack(
            rack_id=rack_id,
            switch_id=switch_id,
            servers=rack_servers,
            online=True,
            metadata={"rack_index": r},
        )

    return Fleet(fleet_id=fleet_id, racks=racks)
