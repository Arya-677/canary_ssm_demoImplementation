# RESOURCES-03 checkpoint

The existing world engine now runs opt-in healthy service workloads through
bounded FIFO cohort queues, shared host CPU budgets and memory admission.
Memory is separated into baseline, temporary and retained components. Drop
reasons and analytical latency proxies are explicit. No detector/inference,
release harm or fault simulation was changed or added.

## Implementation and files

- `canary_ssm/resources.py`: validated work/traffic config, aggregate routing,
  queue/memory admission, fair core-seconds allocation, partial request progress,
  host/service observations, bounded traces and CSV export.
- `canary_ssm/engine.py`: opt-in phase adapter, reset of resource state,
  resource replay/source compatibility and trace verification. Existing static
  configs continue to select static phases.
- `canary_ssm/cli.py`, `canary_ssm/resource_report.py`: trace export and fixture
  runner, with plots/gates generated from saved CSVs.
- `configs/world_low_load.yaml`, `world_increased_load.yaml`,
  `world_recovery.yaml`: deterministic healthy-service scenarios.
- `tests/test_resources.py`: independent arithmetic, units, request accounting,
  queue/memory/CPU bounds, shared host resources, unavailability, causality,
  reset/replay, schema and trace checks.
- `README.md`, `docs/resources.md`, `docs/engine.md`,
  `docs/implementation_status.md`: commands, equations and declared approximations.
- `examples/resource_world/`: executed 120-tick scenarios with replay JSON,
  host/service CSVs, visible PNG traces, summary CSV and computed fixture gates.
- `examples/world_clock_100_ticks.json`: static sample regenerated against the
  current engine source hash; the prior archive retains the previous sample.

## Executed commands

Commands ran from the repository root using the local audit environment
(`../../.audit_venv/bin/python` in place of `python`).

```bash
python -m pytest -q tests/test_resources.py tests/test_engine.py tests/test_topology.py
python -m canary_ssm world-fixtures --out examples/resource_world
python -m pytest -q
```

The final focused result is `127 passed in 4.18s`: 23 resource cases, 28 engine
cases and 76 topology cases. The fixture runner's saved gates all passed for
CPU/memory/queue bounds, request conservation, replay, load response, recorded
overload drops and recovery. Summary values are in the saved `summary.csv`;
figures were rendered from its source CSVs and the recovery figure was visually
inspected. These are synthetic model checks, not detector benchmarks.

Final full regression result: `1 failed, 233 passed in 70.13s`. The legacy
reproduction test's missing `data_audit/model_pooled_dev/model_config.json` is
the previously established archive limitation, not a new resource-model defect.
No existing test was changed, weakened, skipped or supplied a fabricated model.

Raw test output, source hashes, scenario gates and replay checks are saved in
`docs/wp/resource_validation.json`. Final engine docstrings/import cleanup did
not change behavior; bundled artifacts were regenerated with current hashes.

## Limits and next step

Equations, units and assumptions are in `docs/resources.md`: batch arrivals,
perfectly parallel core-seconds work, fixed reference shares for latency,
conservative memory admission and serving-unavailable lifecycle semantics.
There are no request-latency samples/p95, dynamic leaks, OOM/restarts, network
or disk bottlenecks, or release decisions in this chunk.

`world-resources-v1` has explicit artifact/config/source hashes. Previously saved
external runs with old source hashes require regeneration, as enforced by the
existing replay contract. Inference/calibration artifacts were not rewritten.
The clock, RNGs and resource state reset together. Resource CSV buffers have
explicit bounds and eviction counts.

This is an extracted ZIP without `.git`; no branch/commit/merge is claimed.
Suggested commit: `feat: simulate bounded healthy workloads and host resources`.
The initial broad repository audit remains incomplete. Stop at chunk 03; the
read-only world dashboard is the next guide chunk.
