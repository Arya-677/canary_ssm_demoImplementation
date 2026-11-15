# TOPOLOGY-01: physical topology checkpoint

## Result and contracts

Added validated frozen records for centers, racks, hosts, capacities, usage,
lifecycle and replica placement. Added the explicit 1/4/20 world fixture and a
`topology` subcommand under the existing CLI. The common YAML mapping reader
is shared with the existing research configuration loader; the existing
`cross` expansion remains in `experiments.load_config`.

The public contract is `load_topology(path) -> Topology`,
`Topology.snapshot() -> dict`, and `Topology.from_dict(snapshot) -> Topology`.
All capacities have explicit units (cores, decimal MB, Mbps); class metadata
remains independent from physical rack grouping. Current usage and lifecycle
can be replaced without changing identity/capacity or previous snapshots.

## Files changed

- `canary_ssm/configuration.py`: common YAML mapping reader and duplicate-key guard.
- `canary_ssm/topology.py`: records, field and reference validation, loader and snapshot.
- `canary_ssm/experiments.py`: use the common YAML reader.
- `canary_ssm/cli.py`: topology validation/export handler.
- `configs/world_interactive.yaml`: explicit fixture.
- `tests/test_topology.py`: validation, containment, immutability, custom config, round-trip and CLI tests.
- `README.md`, `docs/topology.md`, `docs/implementation_status.md`, and this report: usage and checkpoint evidence.

## Executed checks

Commands were run from the extracted repository root using the local audit
Python environment (`../../.audit_venv/bin/python` in place of `python`).

```bash
python -m pytest -q tests/test_topology.py
python -m canary_ssm topology --config configs/world_interactive.yaml --out ../../outputs/topology_snapshot.json
```

Focused result: `76 passed in 7.91s`. Snapshot command exited 0. A separate
Python check loaded that JSON through `load_topology`, compared its snapshot
with the saved JSON, and confirmed one center, four racks, twenty unique hosts
and twenty replicas. This is a structural acceptance check, not a benchmark.

Full regression command:

```bash
python -m pytest -q
```

Result: `1 failed, 182 passed in 75.52s`. The single failure is
`tests/test_p1_protocol.py::test_experiment7_legacy_reproduction`, which raises
`FileNotFoundError` for `data_audit/model_pooled_dev/model_config.json`.
The supplied archive does not contain this required artifact. The same single
test was executed against a freshly extracted, untouched copy of the input ZIP:
`1 failed in 0.58s`, with the same missing-file error. Existing tests were not
modified or skipped and no substitute model artifacts were manufactured.
The remaining 182 cases passed, including all 76 topology cases. The full suite
cannot be called green until the legacy artifact is restored.

Raw regression and baseline output, input ZIP digest, file hashes, environment
versions and computed fixture acceptance checks are saved in
`docs/wp/topology_validation.json`. No detector benchmark or calibration job was
run for this static schema change.

## Limits and repository context

This is an extracted ZIP without `.git`; no branch, commit or merge is claimed.
The governing plan's branch/merge checklist cannot be performed on this archive.
Suggested commit when applying the patch to a checkout:
`feat: add validated physical topology and interactive fixture`.

The static schema is a new virtual-world boundary, not a replacement for the
statistical generator or filter. It has no clock, faults, running applications,
detector integration, rollout transitions, or automatic placement decisions.
Service/release IDs are validated opaque references until those registries exist.
The prior full audit remains unfinished; this checkpoint makes no repository-wide
completion claim. Stop after chunk 01; the next chunk is the clock/event engine.
