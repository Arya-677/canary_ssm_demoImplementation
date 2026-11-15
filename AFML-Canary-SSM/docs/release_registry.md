# Immutable declared-behavior releases

This mode simulates a validated behavior manifest. Uploaded source is stored as
inert bytes, hashed and replayed as data; it is never imported or executed.
Release IDs, versions, filenames and profile labels do not select behavior.
Only validated numeric parameters drive service/resource dynamics.

## Registration, identity and immutability

`releases.ReleaseRegistry` is append only. Frozen `Release`, `Creation`,
`Attachment` and `Behavior` records contain immutable strings/scalars; exported
JSON and attachment maps are copies. A release has schema version 1, release_id,
service_id, numeric three-part version (optionally a prerelease suffix), content
hash, creation metadata, behavior manifest and optional source descriptor.
Release IDs are globally unique within the registry; service/version pairs are
also unique. Unknown services and conflicting initial release parentage fail.

An exact retry returns the first record and preserves its creation tick. Changing
content, version, author, creation timestamp, description or attachment name under
an existing ID fails. Register a new ID and version instead. There is no update
or delete command. Registry assets survive simulation reset and are reconstructed
from the private ordered command log on session restore/replay. Reset still
recreates world resources, queues and RNG state; it does not make old versions
mutable. A new unrelated server/session creates its own registry.

`creation_metadata.author` is required (1–100 characters). Optional description
is at most 500 characters. Optional created_at must be ISO-8601 with a timezone;
it is caller-supplied provenance, not trusted wall-clock scheduling. The backend
owns created_tick, measured in simulated ticks. All initial examples use fixed
creation provenance so replay never depends on wall time.

The computed content SHA-256 hashes canonical compact JSON:

```text
{"behavior_manifest": normalized_manifest,
 "source_sha256": SHA256(source_bytes) or null}
```

Manifest profiles are sorted by kind and numeric values normalized. IDs, version
and creation metadata do not alter content identity, but are independently
immutable record fields. A caller-supplied content_hash must match. Attachments
need a plain filename and base64 body, with 1–131072 decoded bytes. Paths, invalid
base64 and oversized bodies fail. The registry bounds are 64 release records and
10 unique attached source blobs, including across simulation resets.

Two built-in immutable examples are `release-001` version 1.0.0 (healthy) and
`release-002` version 1.1.0 (composed behavior). Exact importable registrations
and their computed records are in `examples/release_registry/`. The original
sample IDs and legacy source/profile upload command remain compatibility aliases.
Their names can occur in public release identity metadata; no detector parser
turns those names into numeric features or known-fault labels.

## Behavior manifest schema and composition

```json
{
  "schema_version": 1,
  "profiles": [
    {"kind": "extra_cpu_work", "work_multiplier": 2},
    {"kind": "retained_memory_leak", "retained_mb_per_completion": 0.25},
    {"kind": "increased_error_probability", "error_probability": 0.1},
    {"kind": "slower_response", "response_delay_ms": 1500}
  ]
}
```

Use `[{"kind":"healthy"}]` alone for neutral behavior. Each other kind may occur
once; there may be one to four profiles. Unknown fields/kinds, duplicate kinds,
wrong schema versions, booleans used as numbers and nonfinite values are rejected.
Healthy cannot be mixed with other kinds. Declared neutral numeric values are
valid. No arbitrary script, expression, network action or command is supported.

| Kind | Parameter and units | Inclusive bound | Neutral |
| --- | --- | --- | --- |
| extra_cpu_work | work_multiplier, dimensionless CPU core-seconds/request factor | 1–16 | 1 |
| retained_memory_leak | retained_mb_per_completion, decimal MB per CPU-processed request | 0–64 | 0 |
| increased_error_probability | error_probability, per completed response | 0–1 | 0 |
| slower_response | response_delay_ms, additional fixed post-processing wait in ms | 0–300000 | 0 |

Composition has no order dependence: multiply the service's configured CPU work
once; add bounded retained memory on each CPU processing completion; independently
sample failed responses; add fixed response wait after CPU work. There are no
retries. A registered CPU multiplier is also checked against the existing
ServiceWorkload effective work bounds before registry mutation. Hardware faults
continue to affect host CPU availability, platform memory and rack networking
separately; they do not rewrite release manifests.

## Discrete-time resource assumptions

For replica i and tick length dt seconds, effective CPU work is
`work_i = base_work_i * work_multiplier`. Existing shared CPU/network allocation
and FIFO progress consume that work. A processed request moves either directly
to a response or into a pending-response FIFO for
`ceil(response_delay_ms / (1000*dt))` ticks. Public response latency is actual
simulated FIFO residence through response emission, quantized to ticks. The
analytical next-request proxy adds declared wait and remains a labeled estimate,
never p95. Delayed egress timing is not a packet-level network model.

CPU-queued plus pending-response requests share the queue_limit and temporary
request memory. Admission occurs before resource updates, so a response due this
tick still occupies its slot during that tick's admission phase. CPU is free
while a processed request waits for its response. The pending FIFO has no more
cohort entries than outstanding requests and cannot grow without bound.
Restart/rollback and host unavailability explicitly drop both queued and pending
requests, with the existing restart/unavailable drop counters.

Retained memory grows by `processed_count * retained_mb_per_completion`, including
requests that ultimately return errors. It is capped at free host memory after
baseline, existing retained/platform memory and outstanding temporary memory.
Blocked growth is reported. Retained memory is reclaimed by replica restart or
rollback. Baseline memory, temporary request memory and retained application
memory remain separate. These are bounded simulation assumptions for a laptop.

Errors use a separate deterministic cohort-addressed PCG64 sampler keyed by run
seed, a fixed release-error domain, stable replica identity, processing/response
timing and cohort count. Release names/IDs and source filenames are not RNG keys.
The sampler consumes none of the workload, faults, host-noise or telemetry-loss
streams. It resets/replays deterministically. For each completed cohort,
errors ~ Binomial(completed_count, error_probability). Probabilities 0 and 1 have
the expected exact outcomes. Resources expose processed, completed, succeeded,
errors and pending_response_count as observed counts. Failed responses consume
work and have latency; they are not unavailable-route or queue drops.

Here `completed` means emitted responses including errors, while `processed`
means CPU work finished. With outstanding defined as CPU-queued plus pending,

```text
queue_start + accepted = queue_end + completed
                       + dropped_unavailable_queued + dropped_restart
completed = succeeded + errors
```

Public telemetry's request count/latency includes both successful and failed
emitted responses. Its current typed minute schema does not add error-rate
features. A pure error-only release can therefore be invisible to the existing
latency/workload SSM; this patch does not invent detector power for that case.

## Dashboard/API and separation

The existing Releases view adds a numeric form, a reviewable JSON editor,
registration JSON upload and an optional inert source attachment. The backend
is authoritative for validation and hashing. Local status next to the form
shows accepted or rejected immutable registrations. Candidate information shows
version, content hash, units and declared behavior. This operator view is not an
inference endpoint. The older source/profile upload remains compatible.

Use the existing authenticated, idempotent `/api/commands` envelope:

```json
{
  "command_id": "unique-command-id",
  "run_id": "current-backend-run-id",
  "epoch": 0,
  "command": "register_release",
  "args": {"release": {"schema_version": 1, "release_id": "my-release",
    "service_id": "demo-service", "version": "1.2.0",
    "creation_metadata": {"author": "operator"},
    "behavior_manifest": {"schema_version": 1, "profiles": [{"kind":"healthy"}]}}}
}
```

The command token/origin, body limits, rejection receipts and session persistence
are unchanged. `/api/releases` is the operator registry catalog. Public deployment
metadata includes only release_id, service_id, version and content_hash. Replica
telemetry keeps release identity and exposure, without manifest/profile parameters.
The public resource snapshot exposes only pending counts, never internal response
schedule tuples or their failure probabilities. Private replay control state and
evaluator telemetry keep mechanisms separately. Inference modules do not import
the registry/operations/evaluator code. A label-renaming test preserves every
numeric/mask detector input. No source name is parsed as a behavior feature.

## Commands, examples and validation

```bash
python -m canary_ssm.release_fixture --out examples/release_registry
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/release_registry
python -m pytest -q tests/test_releases.py tests/test_resources.py tests/test_public_telemetry.py tests/test_console.py
```

The tiny fixture saves both example registrations, immutable records, six profile
cases, actual traces and deterministic replay checks. `summary.csv` is computed
from those traces. The acceptance seed comes from the existing registry; no
inference fitting, calibration or benchmark is performed. The legacy before/
after comparison checks all original host/service values and workload RNG state
for healthy, CPU-work and retained-memory behavior. Old tests are preserved.
Because resource/operations source changes are replay-guarded, packaged world
replays and scenario hashes are refreshed. Original statistical paired NPZs,
fitted research models and inference source are not changed.
