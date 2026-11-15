# Public telemetry and causal monitoring windows

`telemetry.py` is the inference-facing contract and receiver. It imports no
simulator, fault scheduler, evaluator, release operations or inference code.
`telemetry_transport.py` generates and delivers public records using only public
placement, completion/routing counts, observed resources and release exposure.
`telemetry_evaluator.py` writes separate injection labels. Existing Gaussian
inference and the research `schema.Rollout` remain unchanged.

## Records, identities and units

Required public fields include `run_id`, `host_id`, `rack_id`, `class_id`,
`event_time`, `arrival_time`, `service_id`, `replica_id`, `release_id`, `exposed`,
`request_count`, `latency_ms`, `workload` and observed masks. The validated
`PublicRecord` also contains an opaque stable `record_id`, `epoch`, interval
length, additive sufficient statistics and optional host CPU/memory/network
measurements. Unknown fields, including injected truth, are rejected.

Times are **simulated seconds since the current epoch's start**, not wall-clock
or Unix timestamps. `event_time` is the end of the processing tick. The source
arrival time is event time plus transport delay; the receiver stamps its actual
receipt time, preventing a caller from backdating late ingestion. `arrival_time`
can never precede event time. Run IDs are persisted and supplied on replay.
The dashboard supplies its run ID; the headless default is a deterministic
configuration identity. Supply `--run-id` to distinguish repeated headless runs.
Reset retains the run identity, increments telemetry `epoch`, and rebuilds queues,
RNG, records and windows. IDs hash run/epoch/tick/replica, so retries keep the ID
and reset records cannot collide with the preceding epoch. Imported saved-run
records retain their original source run identity.

`exposed` means that this replica actually carries the selected candidate release
on a canary host. It says nothing about harm. It follows actual placement after
next-tick deployment/rollback, not an intended UI status. Parentage and class are
validated against the initial public roster. Services and replicas stay separate;
there is no implicit pooling across services or assignment of host-wide CPU to
individual applications. Host resource values repeat on co-located replica rows
and must not be summed as independent usage.

## Latency comes from completed requests

The old `latency_proxy_ms` remains an analytical backlog/service estimate. It is
not renamed to public `latency_ms`. The resource model now records completed FIFO
cohorts without changing allocation, request completion counts or queue behavior.
For a request arriving at the start of tick a and completing by the end of tick t,

`L_ms = (t - a + 1) * tick_seconds * 1000`.

Every completed request in that arrival/completion cohort has this quantized
latency. This deliberately bounded discrete-time measurement assumes arrivals at
tick start and completions at tick end; it is not sub-tick tracing. Requests that
finish within one tick all measure one tick. More work changes these latencies
when it changes the completion tick/backlog. The finer analytical estimate remains
available separately in resource traces. No percentile or real-system fidelity
claim is made.

Each replica tick record contains completion count n and mean response latency,
plus request-weighted `latency_sum_ms`, `latency_sum_sq_ms2`, `log_latency_sum`
and `log_latency_sum_sq`. Cohorts contribute `n*L`, `n*L^2`, `n*log(L)` and
`n*log(L)^2`; completed requests are never expanded into large per-request arrays.
No completion gives n=0, latency=null and `latency_observed=false`; zero is never
substituted for missing latency. Dropped and unavailable requests have no response
latency and are not included in n. Other resource traces retain explicit drop
counters. Lower completion latency alone cannot establish improved reliability.

`workload` is actual routed request count per replica divided by tick seconds
(requests/second), not hidden demand truth or configured work per request.

## One-minute sufficient statistics

Telemetry is opt-in for resource configs using `engine.telemetry.enabled: true`.
The console enables it. Supported telemetry tick sizes are integer divisors of
60 seconds, with a tick-aligned decision grace. Unsupported sizes are rejected
rather than dividing one completion count across windows speculatively.

Windows are right-closed: `(0,60]`, `(60,120]`, etc. Thus the tick ending at 60
belongs to minute zero. Windows are keyed by run, epoch and replica, preserving
host/rack/class/service identity. The configured roster emits an explicit missing
row even if an entire minute receives nothing.

| Aggregate | Calculation from unique, timely, fresh tick records |
| --- | --- |
| `request_count` | Sum completion counts with a fresh latency mask |
| `latency_sum_ms`, `latency_sum_sq_ms2` | Sum the additive request statistics |
| `latency_ms` | Sum latency / sum completion count; request-weighted arithmetic mean |
| `log_latency_sum`, `log_latency_sum_sq` | Sum request log-latency statistics |
| `log_latency_mean` | Sum log latency / completion count; differs from log(arithmetic mean) |
| `workload_integral` | Sum fresh workload_rps × interval_seconds (routed requests over observed intervals) |
| `workload_seconds` | Sum intervals with fresh workload |
| `workload` | Integral / observed workload seconds, not a carry-forward estimate |
| `coverage` | Fresh unique tick intervals / 60 seconds |
| `release_ids`, `mixed_exposure` | Actual fresh release/cohort metadata received for this minute |

The two moments and count allow sample variance calculation as
`(sum_sq - sum^2/n)/(n-1)` when n>1, in arithmetic or log units. They are sufficient
for these descriptive means/variances, not universally sufficient for an SSM or
for empirical percentiles. A population/request independence assumption is not
asserted by exporting them. No p95 is generated.

A latency window is `observed=true` only if fresh coverage reaches
`minimum_coverage` (default 0.8), at least one response completed, and exposure
metadata has adequate coverage with one consistent version/cohort. Mixed release
or cohort minutes remain numerically inspectable but are masked from inference.
Workload and exposure have separate masks. Partial statistics can exist on a
masked row; consumers must honor masks. Empty minutes have null means, zero count
and false masks. Carried display values require false fresh masks and never
contribute to sufficient statistics or coverage.

## Causal receipts, late data and immutable scores

Window k closes once at `(k+1)*60 + decision_delay_seconds`. All arrivals at the
exact deadline are delivered before closing. Later arrivals can appear in the
unique received-record log for audit, but cannot enter that closed window or be
relocated into a later minute. There is no backfill of earlier inputs or scores.
No wall time is involved.

Deduplication checks both record ID and `(replica_id,event_time)` logical slot.
Repeated payloads with later arrival times or retry IDs are ignored; conflicting
payloads are counted and the first receipt remains authoritative. Different
replicas at the same timestamp remain distinct. Counters distinguish duplicate,
conflicting, late and capacity-dropped records.

`CausalWindowStore.time_slice(timestamp)` freezes completed windows and returns
an immutable-by-copy prefix receipt with an input SHA-256. New decisions must be
monotonic; historical committed timestamps return their original receipt even
after later ingestion. `score_once(timestamp, callback)` is an optional trusted
external scoring hook over copied public inputs: a successful result is cached
and never recalculated for that timestamp. Tests use a simple sum callback to
verify immutability; no detector or fake production score is supplied. This
receiver-level callback is not a new engine command or an SSM integration; an
external inference integration must persist its own committed scoring ledger.
Built-in engine replay covers the built-in telemetry flow, with no external
callback mutations.

For offline public records, `causal_time_slice(records, run_id, roster,
decision_time, ...)` first filters by receiver arrival timestamp, before reading
future payload values. It then merges eligible receipts and window deadlines in
causal order. This prevents future records, future release changes and late
historical values from altering an earlier slice. Historical arrival timestamps
must come from the receiver's recorded log, not be reconstructed from event time.

There is intentionally no silent conversion into the legacy research `Rollout`:
that schema uses fixed canary membership and research log-latency conventions.
The new per-request mean log latency and dynamic service/version metadata need
a separately reviewed observation and eligibility adapter plus calibration before
connecting the existing SSM. Monitoring continues to say DETECTOR NOT CONNECTED.

## Transport configuration and bounds

```yaml
telemetry:
  enabled: true
  delay_min_ticks: 0
  delay_max_ticks: 2
  duplicate_probability: 0.1
  missing_probability: 0.02
  missing_window_probability: 0.05
  drop_windows: []
  late_windows: []
  late_delay_ticks: 120
  decision_delay_seconds: 0
  minimum_coverage: 0.8
  max_records: 50000
  max_windows: 1000
```

Delay is discrete uniform over the inclusive tick range. Explicit late-window
indices add `late_delay_ticks`. A duplicate retransmits the same ID/payload one
tick later than its original scheduled arrival. Missing-record and
missing-replica-window decisions use the engine's separate `telemetry_loss` PCG64
stream. Explicit `drop_windows` suppresses all replica records in those indexed
minutes. A per-replica/window missing draw is made once, then per-record
missing/duplicate/delay draws are consumed independently of metric values. These
are simulation assumptions, not transport performance estimates.

Source records and the pending heap are bounded by `max_records` (up to 200,000);
monitoring is bounded by `max_windows` (up to 1,000) and a public roster of at most
1,000 replicas. Capacity suppression is counted, never silently evicted or turned
into a fresh observation. Reset is required to clear a full source budget.
The receiver stores unique receipts; duplicate wire frames are represented by
counters, not extra latency samples. Transport configuration, pending arrivals,
loss decisions, RNG states and epoch are saved in the private replay bundle.
Exact source/NumPy guards verify reproducibility; old external source revisions
are rejected rather than silently reinterpreted.

## Public versus evaluator-only files

```bash
python -m canary_ssm world-run --config configs/world_telemetry.yaml --ticks 240 --run-id demo-01 --out run.json --telemetry-out telemetry_export
python -m canary_ssm world-replay --artifact run.json
python -m canary_ssm.telemetry_fixture --out examples/public_telemetry
```

`telemetry_export/public/` contains `records.jsonl`, `windows.jsonl`,
`decisions.jsonl`, `scores.jsonl` (empty without an external scorer) and
`metadata.json`. No fault type, true affected status, injected effect, schedule
or evaluator label belongs there. `telemetry_export/evaluator/` separately holds
`truth.jsonl` and its label definitions. Full private engine/run bundles include
both for verified replay and are not inference inputs.

Evaluator `true_affected` means a targeted active platform injection or an active
nonhealthy release profile, not measured harm or the research qualifying event.
`fault_type` and injection mechanism parameters are evaluator-only. The physical
resource simulator defines no counterfactual additive latent log-latency effect,
so `injected_latent_effect` is explicitly null rather than inventing a scalar.
This does not change the existing research simulator's truth/event definitions.

`GET /api/telemetry` returns only public data, with explicit response limits of
500 latest unique receipts and 2,000 latest monitoring rows. A committed
`?decision_time=60` returns its frozen full public prefix; future/uncommitted
timestamps are rejected and GET never advances the engine. Exports contain the
full retained public record set. Monitoring displays a separate minute table
from this backend endpoint, with coverage and fresh/masked status. The existing
resource charts remain explicitly analytical estimates. Recorded static UI mode
does not call telemetry APIs or fabricate minute data.

The four-minute fixture exercises delayed first-minute receipts, a completely
missing second minute, duplicates, a later CPU injection and recovery. Public
and evaluator files, computed gates and a verified run are bundled. Unit tests
also perturb future workload and future payload values, check request-weighted
moments by hand, reject truth fields, and verify that prior inputs and scores
remain unchanged after late arrivals.
