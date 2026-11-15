# Retained process memory and resource advisories

This extension adds `process-memory-v1` to declared release behavior. It does not
execute source, change an SSM, prove a code defect, or automatically choose a
rollout transition. It models bounded request batches and a process heap, not
an operating system allocator, tracing GC, fragmentation, swap or page faults.

## Use the dashboard or headless fixtures

```sh
python -m pip install -e '.[dev,report]'
python -m canary_ssm.cli world-dashboard --config configs/world_memory.yaml --port 8765 --state-dir runtime/memory-dashboard
python -m canary_ssm.memory_fixture --out examples/process_memory
python -m pytest tests/test_process_memory.py -q
```

The new interactive config retains the one-center/four-rack/five-host-per-rack
layout with smaller declared memory capacities for a short laptop demonstration.
Select `sample-leak-v3` (persistent retention) or `sample-cache-v1` (finite cap) in
Releases, preview and deploy, or use the existing fixed-cohort rollout commands.
The World host detail panel shows used/headroom memory, observed growth per
processed request, sampled response latency, generation/restart/OOM counters and
process events. **Restart selected process** sends validated `restart_process`
with `replica_id`; it applies before routing on the next simulated tick and is
persisted in the command log. It does not change the release. Continuing to run a
retaining release after restart can grow the heap and OOM again.

The manifest form has an explicit memory-model selector. Choosing Process memory
uses the fields below. Source attachments remain inert. The older memory field
is visibly labeled legacy, bounded and without OOM semantics.

## Immutable behavior manifest and units

A release still uses registration schema 1 and behavior-manifest schema 1. A new
unique behavior kind supplies a separately identified memory model:

```json
{
  "schema_version": 1,
  "profiles": [
    {
      "kind": "process_memory",
      "retained_mb_per_request": 0.5,
      "background_mb_per_second": 0.0,
      "retained_limit_mb": null
    }
  ]
}
```

| Field | Unit and bounds | Meaning |
| --- | --- | --- |
| `retained_mb_per_request` | Finite 0–64 MB / CPU-processed request attempt | Includes attempts that later return an error; not arrivals, successful requests or retries |
| `background_mb_per_second` | Finite 0–64 MB / simulated second; default 0 | Separately declared growth during available running ticks, including ticks with no requests |
| `retained_limit_mb` | Null or finite 0–1e9 MB; default null | Optional application allocation cap (cache plateau); never a physical memory override |

CPU work, response delay and error profiles may compose with this kind. Two
memory models in one manifest are rejected. Rates, caps, IDs, unknown fields,
NaNs, infinities and booleans are validated by the existing registry path.
Canonical manifests/content hashes stay immutable. `sample-cache-v1` and
`sample-leak-v3` are new service versions; previous immutable versions and hashes
are not rebound. Historical `retained_memory_leak/retained_mb_per_completion`
manifests keep their **legacy-bounded-v1** clipping behavior so old research/demo
commands retain their declared meaning. These old profiles are not claimed to
model process OOM. The explicit new process profile is the recommended leak demo.

## Tick equations and allocation lifetime

For a host, let K be immutable capacity (MB), M0 its host/container baseline
reservation (MB), P its platform reservation, Mj the retained heap of process j,
Uj the queued CPU requests plus delayed responses, and tj their temporary MB.

\[
M=M_0+P+\sum_j M_j+\sum_j t_j U_j,\qquad
\mathrm{headroom}=K-M.
\]

Admission uses free physical headroom and bounded request slots. A temporary
allocation that does not fit drops that request (`dropped_memory`), without
killing the process. Temporary memory is reclaimed when a response completes,
when an unavailable queue is discarded, or when a process exits/restarts. CPU
completion alone does not reclaim temporary memory for a delayed response.

After routing, the pre-processing occupancy o determines a declared slowdown:

\[
f(o)=\max(0.1,\,1-4\max(0,o-0.8)),\qquad
\mathrm{core\ budget}=\mathrm{cores}\times f(o)\times f_{CPU}\times\Delta t.
\]

The existing fair CPU allocator then updates FIFO work. Slower CPU work creates
queueing and changes actual completed-request latency, quantized to ticks.
This heuristic is an explicit simulation assumption, not a fitted hardware model.
It applies to the new process-memory model, retained heaps and platform memory
pressure. Legacy empty-heap workloads retain their previous resource behavior.
The analytical next-request latency proxy remains separately labeled; the new
latency trace is a request-count-weighted mean of actual response batches, not p95.

For Nj CPU-processed attempts and a tick of duration dt seconds, proposed gains
are request gain rj Nj and background gain bj dt. If a cache cap Lj is declared,
request allocation takes min(rj Nj, max(0,Lj-Mj)), followed by background allocation
up to the remaining cap room. Without a cap, both gains remain unbounded by an
application limit. Stable replica-ID order resolves competition for host memory.
The resulting batch allocation either fits physical headroom or fails atomically.
Retained allocations stay live across idle ticks, error responses, and changes to
future release parameters. Lowering an allocation cap does not evict old memory.
`configure_behavior` never frees existing allocations.

## OOM, process restart and rollback

A failed retained/background allocation causes an **observed OOM process exit**.
The process enters OOM, its retained heap is reclaimed, and queued CPU work and
pending responses are dropped and counted as `dropped_oom`. The physical
host/container baseline reservation remains. Other processes keep their heaps;
there is no host-wide magic cleanup. Actual memory and recorded peak remain
bounded by K: an uncommitted oversized request is not recorded as allocated RSS.

The bounded batch approximation charges retention after that tick's CPU and
response emission. Responses already emitted survive; delayed responses still
owned by the dying process are dropped. This is not an instruction-level allocator
or an atomic per-request transaction. OOM applies to retained/background allocation;
ordinary temporary-allocation admission failures reject requests instead.

An OOM process remains down until an explicit restart or a release operation
that actually restarts it. Normal routing excludes stopped processes; fixed-cohort
routing preserves their frozen traffic slots and records unavailable-route drops.
The hardware lifecycle is separate: a ready host can contain an OOM process.
Cohort selection excludes observed OOM hosts from new canary/control membership.

Restart increments a generation and restart count, drops outstanding requests as
`dropped_restart`, resets partial CPU work, and creates the configured initial
retained heap. A startup heap that cannot fit causes another OOM exit; it never
exceeds capacity. All starts/exits record a bounded process event history with
sequence, tick, replica/host IDs, reason, reclaimed MB and dropped request count.
The event history reports evictions; it is not an unbounded audit store.

Rollback's existing restart operation is now visible in these counters/events.
The legacy rollout restarts its canaries; the fixed-cohort protocol restarts all
service replicas. Their baseline behavior/version placement is then restored.
Merely switching a behavior to healthy does not release an existing heap or remove
its pressure. Recovery requires actual process exit/restart or a future explicitly
modeled reclamation mechanism. New requests can allocate again on the restart tick.

## Observed growth versus latency inference

`resource_health.ResourceHealthPolicy` uses development-defined engineering
criteria, recorded in `resources.health_policy`, policy ID `resource-health-dev-v1`
and a policy-content checksum. They are not calibrated statistical thresholds.
Changing these criteria changes that checksum/config; do not reuse a calibrated
latency policy as though it covered this advisory.

Default criteria use a trailing 10 simulated seconds, at least 3 samples spanning
5 seconds, and at least 20 processed requests. An observed retained-growth warning
requires net retained growth >=0.05 MB / processed request **and** >=0.5 MB/s. A
separate idle criterion warns on >=0.5 MB/s with zero processed requests. Low
headroom is advisory when usage reaches 80% of capacity. OOM is an observed
process-availability condition, not a detector verdict.

This advisory uses the direct backend resource-observation channel shown in world
snapshots, not the separate delayed/lossy one-minute latency telemetry receiver.
Resource-observer loss/delay is not simulated in this version; the dashboard
connection banner separately reports polling disconnection/staleness. These direct
resource counters are never substituted for missing latency-detector inputs.

The window uses only records at or before the current simulated timestamp and
never bridges an OOM or restart. Missing/unavailable history and insufficient
request counts are explicitly insufficient; stale timestamps are stale. Cache
warmup can warn and plateau can clear the warning. The absence of a warning is
not a claim that a process is healthy or leak-free.

The advisory's normalized **net** growth includes any concurrent background growth
and is not an estimate of the declared per-request parameter. The chart's separate
`retained_added_mb_per_request` is observed successful request-allocation MB divided
by that tick's processed count, excludes background allocations, and is null when
the denominator is zero. Background allocation has its own observed counter.

The label is **Observed memory-growth warning, not SSM proof of a code-level
leak**. `latency_detector_decision` and `automatic_action` remain null. Advisories
never consume release names/parameters, fault schedules/truth, posterior scores,
or evaluator labels. No changes are made to adjustment, Kalman engines, effects,
risk, thresholds, detector policy or rollout decision logic. Resource-triggered
process failure is physical simulation behavior, not a latency-based deployment
decision. Operator behavior manifests and evaluator labels remain outside the
public inference path.

## Fixtures and evidence

`examples/process_memory` contains five small **development-only** scenarios with
separate config/seed/commands, public telemetry/resource traces, public resource
advisory histories, evaluator-only expectations/truth, and private replay artifacts.
The generator ID is `resource-world-process-memory-v1`. Seeds use the existing
registry's `world_dev`, reserved family slot 20, and scenario indices 0–4. No
calibration, null-validation or final-test data is used to define this advisory.

The cases are cache warmup/plateau, retention without latency harm, bounded
pressure with actual queueing latency, OOM that stays down, and OOM/restart/rollback
recovery. Checks are computed into `checks.json`; numeric summaries and figures
are generated from saved CSV rows. They demonstrate assumptions and lifecycle,
not real data-center fidelity, leak attribution or detector power.

See `docs/wp/PROCESS_MEMORY.md` and its raw validation files for executed checks.
Browser visual layout at specific laptop widths is not claimed by the HTTP/DOM
harness. Original tests, inference files and statistical additive pair artifacts
remain byte-preserved; old world fixtures are regenerated for strict source-bound
replay compatibility with this implementation/runtime.
