# Physical topology (world chunk 01)

Subsequent chunks now connect these records to the [clock](engine.md) and
[healthy workload/resource model](resources.md). The schema below remains the
shared containment/placement contract.

This is the static world model. A data center contains racks, a rack contains
hosts, and service replicas reference their placement hosts. `class_id` remains
an independent hardware/statistical grouping; it is not inferred from `rack_id`.
The existing statistical latency simulator still uses its original configuration.

## Run from the repository root

With the project dependencies installed in your Python environment:

```bash
python -m canary_ssm topology --config configs/world_interactive.yaml
python -m canary_ssm topology --config configs/world_interactive.yaml --out topology_snapshot.json
python -m canary_ssm topology --config topology_snapshot.json
```

The installed `canary-ssm topology ...` command and
`python -m canary_ssm.cli topology ...` expose the same handler. Without `--out`,
stdout contains only the JSON snapshot. Invalid configurations exit with code 2.
The output path's parent directories are created when needed.

`configs/world_interactive.yaml` explicitly lists one data center (`dc-01`),
four racks (`rack-01` through `rack-04`), and five hosts in each rack
(`host-01-01` through `host-04-05`). Every host has one `demo-service` replica
referencing `release-healthy-v1`. These are placement references, not running
processes. All usage starts at zero and all hosts start `ready`.

## Configuration and snapshot contract

`canary_ssm.configuration.read_yaml_mapping` is the common YAML/JSON reader used
by the research config loader and topology loader. It reads UTF-8 (including
BOM), requires a mapping root and rejects duplicate mapping keys rather than
silently overwriting conflicting values. Existing research `cross` expansion
remains in `experiments.load_config`.

`load_topology(path)` accepts either a project's `topology:` section or the bare
JSON/YAML snapshot emitted by `Topology.snapshot()`. It constructs typed,
validated records through `Topology.from_dict`. Unknown topology/record fields,
missing required fields and unsupported schema versions are errors.

```yaml
topology:
  schema_version: 1
  data_centers:
    - data_center_id: dc-a
  racks:
    - rack_id: rack-a
      data_center_id: dc-a
  hosts:
    - host_id: host-a
      rack_id: rack-a
      data_center_id: dc-a
      class_id: 0
      capacity:
        cpu_cores: 8
        memory_mb: 16000
        disk_mb: 500000
        network_mbps: 1000
      usage: {cpu_cores: 0, memory_mb: 0, disk_mb: 0, network_mbps: 0}
      lifecycle: ready
  replicas:
    - service_id: example-service
      replica_id: replica-a
      host_id: host-a
      release_id: example-v1
```

| Record | Required fields | Validation |
| --- | --- | --- |
| `DataCenter` | `data_center_id` | Nonempty ID |
| `Rack` | `rack_id`, `data_center_id` | Data center must exist |
| `Host` | `host_id`, `rack_id`, `data_center_id`, `class_id`, `capacity` | Rack must exist; host's data center must equal the rack's; class is a nonnegative integer |
| `HostCapacity` | `cpu_cores`, `memory_mb`, `disk_mb`, `network_mbps` | CPU is a positive integer; all other capacities are finite positive numbers |
| `HostUsage` | Optional fields with the same names as capacity | Finite nonnegative numbers, no value above its host's capacity; defaults to zero |
| `ServiceReplica` | `service_id`, `replica_id`, `host_id`, `release_id` | Host must exist; service/release IDs are nonempty opaque references |

Capacity/usage units are physical cores, decimal MB for memory/disk, and Mbps
for network capacity/current throughput. Neither MB nor Mbps is implicitly
converted to binary units. Booleans and numeric strings are rejected as numeric
values. `NaN` and infinity are rejected. Host lifecycle is one of `ready`,
`offline`, or `maintenance`, independently of immutable hardware capacity.

IDs must be strings without surrounding whitespace. Entity IDs are globally
unique across centers, racks, hosts and replicas; service and release IDs may
repeat across replicas. References must match IDs exactly. At least one data
center is required; empty racks/host lists and omitted replicas are allowed for
incremental world construction. The loader does not fabricate IDs, choose
placement or register services/releases.

All records are frozen dataclasses; topology collections are immutable tuples.
An updated usage/lifecycle snapshot can be created with `dataclasses.replace`
without modifying the capacity record or old snapshots:

```python
from dataclasses import replace
from canary_ssm.topology import HostUsage, load_topology

world = load_topology("configs/world_interactive.yaml")
host = world.hosts[0]
updated = replace(host, usage=HostUsage(cpu_cores=2, memory_mb=100), lifecycle="maintenance")
next_world = replace(world, hosts=(updated, *world.hosts[1:]))
snapshot = next_world.snapshot()
```

`snapshot()` returns detached JSON-compatible lists/dictionaries, preserves
configuration ordering and includes all parent links, capacity, usage,
lifecycle, replica placement and `schema_version`. Host IDs remain stable when
usage/lifecycle changes. Save using `json.dumps(snapshot, allow_nan=False)`;
reloading reconstructs the same records. There are no time units or tick state
yet because this chunk has no simulation clock.

## Scope and next gate

This chunk validates containment and placement only. Resource evolution, random
faults, telemetry windows, inference connections and rollout decisions belong
to later chunks. The next patch can add a clock/event engine that holds and
replaces these snapshots; it should reuse this schema and retain the independent
statistical research pipeline.
