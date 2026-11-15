# Healthy request and resource model (chunk 03)

The existing `SimulationEngine` now selects a bounded request/resource phase
adapter when `engine.resources` is configured. The original statistical
log-latency generator and the static clock fixture retain separate behavior.
No detector, release-induced harm, fault generator or application execution is
introduced. All traces described here are synthetic simulation outputs.

## Run and inspect the fixtures

From the repository root, with project dependencies installed:

```bash
python -m canary_ssm world-fixtures --out examples/resource_world
python -m canary_ssm world-run --config configs/world_recovery.yaml --ticks 120 --out recovery_run.json --trace-out recovery_trace
python -m canary_ssm world-replay --artifact recovery_run.json
```

`world-fixtures` runs the low-load, increased-load and recovery configurations
for 120 one-second ticks each, exports host/service CSVs and replay artifacts,
then reads the saved CSVs to produce plots, a summary table and computed
acceptance gates. Existing generated examples are included in the archive.

| Fixture | Demand schedule | Service behavior |
| --- | --- | --- |
| `configs/world_low_load.yaml` | Base demand throughout | Fixed healthy work/memory |
| `configs/world_increased_load.yaml` | Base demand ticks 1–20; 20× demand from tick 21 | Same fixed healthy work/memory |
| `configs/world_recovery.yaml` | Base demand 1–20; 20× demand 21–60; base demand from 61 | Same fixed healthy work/memory |

All three reuse the existing 20-host topology, registered smoke seed and
replica release IDs. A shared demand surge is a workload condition, not an
injected release effect. Each scenario directory contains `hosts.csv`,
`services.csv`, `run.json`, and `traces.png`. `summary.csv` and
`fixture_checks.json` compare the runs without detector-performance claims.

## Units and state

| Quantity | Unit / interpretation |
| --- | --- |
| Δ = `tick_seconds` | Simulated seconds per tick |
| λ = `arrival_rate_rps` | Requests/second for the entire service, across replicas |
| w = `work_core_seconds` | Core-seconds required per request; identical within one service |
| c = `host.capacity.cpu_cores` | Physical cores; cΔ core-seconds available in one tick |
| K = `queue_limit` | Integer requests per replica, including a partially processed head request |
| Q | Integer outstanding requests at a tick boundary |
| p | Already-served core-seconds on the head request, 0 ≤ p < w |
| Memory quantities | Decimal MB, consistent with the topology schema |
| `latency_proxy_ms` | Analytical next-request queue/service estimate in milliseconds; not a percentile |

`ServiceWorkload` and `ResourceConfig` validate finite numeric quantities and
reject numeric strings, booleans, negative rates/memory and nonpositive work.
Work is bounded to [10⁻⁶, 10⁶] core-seconds/request; queue limits to [1, 10000];
trace lengths and arrival caps have explicit integer bounds. A configuration
whose maximum arrival expectation exceeds 10⁹ requests/tick is rejected before
running. Every placed replica must have a service definition. A configured
service with no placed/available replicas is allowed and reports unavailability.
Baseline plus initial retained memory must fit every host at initialization.

## Discrete-time equations and tick order

Events are applied first, followed by routing/admission, CPU/resource update,
observations and publication, using the existing engine's stable order. All
arrivals in an interval are approximated as a batch at its start. Tick t's rows
describe the completed interval, with `simulated_seconds = tΔ`.

### 1. Shared traffic and service arrivals

For the latest configured traffic level mₜ and one common Uₜ ∼ Uniform(0,1):

\[
f_t=m_t[1+j(2U_t-1)],\qquad A_{s,t}\sim\operatorname{Poisson}(\lambda_s\Delta f_t).
\]

The bounded jitter j is in [0,1]. Exactly the same fₜ affects every service in
that tick. Poisson draws and routing consume only the `workload` RNG stream.
Faults, host noise and telemetry-loss streams remain available and untouched.
The default fixture uses j=0.1; there is no release or latency-effect injection.

If A exceeds `max_arrivals_per_service_tick`, the excess is explicitly counted
as `dropped_arrival_limit`, and only the capped integer count enters routing.
This is a simulator bound, not physical host capacity, and is reported separately.

### 2. Routing and admission

Only replicas on `ready` hosts are eligible. Capped arrivals are distributed
by a multinomial draw with equal probability per eligible replica; replica IDs
have a stable sorted order. Hosts with multiple replicas receive the
corresponding combined share. This is fairness in expectation, not a promise
that every tick has identical counts.

For routed count a and prior queue Q:

\[
a_q=\min(a,K-Q),\quad d_q=a-a_q,
\]
\[
a_{\mathrm{mem}}=\min\!\left(a_q,
\left\lfloor\frac{M_{\mathrm{cap}}-M_{\mathrm{reserved}}-M_{\mathrm{temp,existing}}}
{m_{\mathrm{request}}}\right\rfloor\right),
\quad d_m=a_q-a_{\mathrm{mem}}.
\]

Available memory is floored at zero. Zero per-request memory permits all a_q.
Admission reserves temporary memory immediately; queues never exceed K.
Services are admitted in service-ID order, then replica-ID order, so scarce
shared memory can favor earlier services. This deterministic simplification
is disclosed rather than described as a fair memory scheduler. There are no
retries or secondary routing after queue/memory rejection.

### 3. CPU work, partial requests and FIFO completion

Replica work demand after admission is Dᵣ=(Qᵣ+aᵣ)wᵣ−pᵣ. A ready host's budget
is cΔ core-seconds. `fair_work` water-fills this budget equally among nonempty
replica queues, redistributing unused shares when a queue is satisfied:

\[
0\le b_r\le D_r,\qquad
\sum_{r\text{ on host}} b_r=\min\left(c\Delta,\sum_r D_r\right).
\]

Completions and carried head progress are:

\[
C_r=\min\left(Q_r+a_r,\left\lfloor\frac{p_r+b_r}{w_r}\right\rfloor\right),
\quad Q'_r=Q_r+a_r-C_r,
\]
\[
p'_r=p_r+b_r-C_rw_r\quad\text{if }Q'_r>0,\qquad p'_r=0\text{ otherwise}.
\]

Only tiny floating-point roundoff is tolerated at the completion boundary.
No fractional requests are reported and unused CPU is never banked for future
ticks. FIFO queues store `(arrival_tick, count)` cohorts, not one Python object
per request. Completing a cohort removes counts from the queue head. The number
of cohorts is bounded by the outstanding request limit.

Host mean CPU use during the interval is Σbᵣ/Δ cores; utilization divides that
by c. CPU budget is shared across all colocated services, not independently
granted to each replica. Perfect within-replica parallelism across cores is a
declared approximation: this is a core-seconds work model, not an OS scheduler.

### 4. Memory accounting and cleanup

\[
M_{\mathrm{reserved}}=M_{\mathrm{baseline}}+M_{\mathrm{retained}},\qquad
M_{\mathrm{temp}}=\sum_r Q'_r m_{\mathrm{request},r},
\]
\[
M_{\mathrm{end}}=M_{\mathrm{baseline}}+M_{\mathrm{retained}}+M_{\mathrm{temp}}.
\]

Baseline memory is the configured initial host usage plus
`host_baseline_memory_mb`, plus `baseline_memory_mb` for every placed replica.
Retained memory is separately initialized from
`initial_retained_memory_mb` per replica and stays constant in this healthy
chunk. It is not silently folded into baseline or grown as a simulated leak.

Temporary memory is reserved for every outstanding request, including the head
being processed, and is reclaimed immediately when a request completes or its
queue is dropped. `memory_peak_mb` captures admission-time usage before CPU
completion; `HostUsage.memory_mb` and `memory_temporary_mb` capture end-of-tick
usage. A low-load request can allocate/free within one tick, giving a nonzero
peak even when end-of-tick temporary memory is zero. Admission prevents memory
overflow; OOM/restart and memory-pressure slowdown are later extensions.

### 5. Latency estimate

For a host with n configured replicas, use reference core share c/n. For each
replica, W'ᵣ=Q'ᵣwᵣ−p'ᵣ is remaining queued work. The displayed proxy is:

\[
L_r=1000\frac{w_r+\max(0,W'_r)}{c/n}\ \text{ms}.
\]

The host row averages these proxies over its configured replicas. It increases
with service work and backlog, and falls as the queue drains. It assumes fixed
reference shares and ignores future arrivals; it is not a measured mean, a
queueing-theory guarantee or p95. No request-latency samples are fabricated.
Unavailable hosts or hosts without replicas have a null proxy. CSVs preserve
this as an empty value, not a misleading zero-latency observation.

## Unavailability, drops and accounting

`offline` and `maintenance` mean **unavailable for serving** in this chunk.
Routing excludes them immediately after the tick's events. If all replicas
are unavailable, new arrivals are counted as `dropped_unavailable_routes`.
Previously queued requests on an unavailable host are flushed during resource
update and counted as `dropped_unavailable_queued`; partial CPU progress is
discarded. They are not rerouted to peers. CPU use is zero. Baseline/retained
memory remains reserved until an explicit future process-lifecycle model says
otherwise; unavailable does not yet simulate physical power-off.

Per service, every tick satisfies these independently checked identities:

\[
A=\mathrm{accepted}+d_{queue}+d_{memory}+d_{arrival\_limit}+d_{unavailable\_routes},
\]
\[
Q_{start}+\mathrm{accepted}=Q_{end}+\mathrm{completed}+d_{unavailable\_queued}.
\]

Queue overflow occurs before CPU work that tick. This conservative batch
approximation can drop a burst even if some requests could have completed
between individual arrivals. No timeout, inter-host migration, disk work,
network bottleneck or per-request latency distribution is modeled here. Disk
and network usage fields retain configured values. The resource adapter owns
CPU usage; configured initial CPU use is replaced by the modeled workload.

## Reset, replay, trace bounds and compatibility

The existing engine rebuilds all queue cohorts, partial progress, memory
reservations and trace buffers on reset, together with its original topology
and four RNG streams. Resource snapshots include queue state, release/placement
references and current service counters. `run.json` also saves bounded host
and service trace buffers. Replay compares these traces as well as the ordered
log, full final state and RNG state.

The resource adapter uses generator ID `world-resources-v1` and a resource-source
hash. Static configs retain `clock-static-v1`. Source/config/adapter hashes and
NumPy compatibility are enforced; older external artifacts with earlier source
hashes are rejected rather than silently reinterpreted. The bundled static
100-tick sample is regenerated for this revision. Prior archive versions retain
their original samples. Changed dynamics require fresh research calibration
before any later detector claims.

Default trace buffers retain the latest 20000 rows **per table**, with evictions
reported explicitly in snapshots/artifacts. Queue limits and aggregate routing
bound work without allocating an object for every generated arrival. Complete
120-tick fixture CSVs fit within the default buffer. The event/publication log
retains the existing engine's full audit history; use bounded runs for the
current laptop demo.

The fixtures test software/model coherence under these declared assumptions.
Their plots and gates provide no evidence of real data-center realism or
detector accuracy. Future chunks can add UI, faults and telemetry using this
same engine, without duplicating its clock or statistical inference.
