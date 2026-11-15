# Process memory checkpoint

15 November 2026. Extends `canary_ssm_fixed_rollouts.zip`.

Implemented explicit per-request/background retention, optional cache plateau,
heap lifetime, pressure-driven CPU/queue latency, OOM process exit, restart/startup
allocation behavior and a separate observed resource advisory. Actual restart
commands are validated, deferred, logged and replayable. Both deployment paths
apply these behaviors through `ResourceModel.configure_behavior`; changing future
behavior alone does not reclaim memory. Prior immutable memory profiles retain
legacy bounded semantics; new leak/cache release versions have explicit process
semantics. Dashboard labels source attachments unexecuted and resource warnings
as observations rather than SSM/code-level leak proof.

## Executed checks

| Check | Observed result |
| --- | --- |
| Full suite | 538 passed, 1 warning in 331.25s (0:05:31) |
| Additional tests relative to saved rollout checkpoint | 19 |
| Five development memory scenarios | All computed gates passed |
| HTTP/DOM integration + checkpoint restoration | All 9 gates passed |
| Source-bound non-scenario replay artifacts | 28 verified |
| Scenario member manifests | 22 verified |
| Original tests byte-preserved | 28 files |
| Statistical additive pairs byte-preserved | 60 files |
| Original numeric trace/RNG compatibility | Healthy, legacy CPU and legacy memory cases, 30 ticks each, all common original fields equal |
| JavaScript syntax | Exit 0 |

The initial restored environment lacked the optional `tabulate` reporting dependency;
it was installed before the final suite. An initial public observation key reused
an injected fault-type string and tripped the existing separation test; it was
renamed `pressure_slowdown_factor` and the advisory uses observed-low-headroom
wording. The recorded UI snapshot and old source-bound world fixtures were
refreshed for the changed source/runtime. Original tests were not modified or
skipped. Raw earlier failure output is retained; the verified suite above is final.

## Computed development traces

Generated directly from `examples/process_memory/summary.csv`. These are
qualitative simulator acceptance outcomes, not SSM performance, calibration,
production fidelity or proof of a code defect. Maximum sampled mean is a maximum
of per-tick sample-weighted means, not an individual maximum or percentile.

| Scenario | Processed | Final retained MB | Minimum headroom MB | Maximum sampled mean latency ms | OOM exits | Restarts | Gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cache_plateau | 339 | 40.0 | 213.0 | 1000.0 | 0 | 1 | True |
| retention_no_latency_harm | 333 | 666.0 | 99331.0 | 1000.0 | 0 | 1 | True |
| pressure_latency_harm | 414 | 110.0 | 3.0 | 29000.0 | 0 | 1 | True |
| oom | 33 | 0.0 | 29.0 | 1000.0 | 1 | 1 | True |
| recovery | 175 | 0.0 | 9.0 | 1000.0 | 1 | 2 | True |


## Boundaries and limitations

The pressure function and atomic end-of-tick allocation batch are declared
simulation assumptions. Process/container baseline reservations remain after OOM;
heap and queued temporary memory are freed by process exit. Cache warmup can warn
before plateau. Low-request-count/unavailable/stale resource history is not a
clear health verdict. Advisories use direct backend counters, not the separate
loss/delay transport of one-minute latency telemetry. No robust allocator model,
resource-advisory calibration, code attribution or automatic deployment rule is
claimed. Browser visual layout at specific viewport sizes is unverified; UI
checks execute real HTTP commands with a DOM harness.

Research inference, adjusted inputs, thresholds, calibration artifacts and
statistical additive pairs remain unchanged. Public process/lifecycle counters
are resource observations; release behavior manifests and evaluator expectations
are separate from latency inference.

Main files: `resources.py`, `releases.py`, `resource_health.py`, `operations.py`,
`rollouts.py`, `engine.py`, `telemetry_evaluator.py`, `dashboard.py`, web UI,
`memory_fixture.py`, `configs/world_memory.yaml`, `tests/test_process_memory.py`.
See `docs/process_memory.md` for commands, units, equations and rollback semantics.
Raw evidence: `process_memory_validation.json`, `memory_pytest_verified.txt`,
`memory_ui_validation.json`, `memory_artifact_validation.json`,
`memory_preservation.json`, `memory_environment.json`.
