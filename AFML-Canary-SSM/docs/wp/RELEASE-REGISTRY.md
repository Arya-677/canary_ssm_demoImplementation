# Immutable release registry checkpoint

14 November 2026. Extends `canary_ssm_detector_dashboard.zip`.

The mutable profile dictionary is replaced by a frozen append-only registry,
retaining compatibility aliases for existing commands. Schema-v1 manifests drive
CPU work, retained memory, response errors and bounded response wait. Source
attachments remain inert. Dashboard registration, public identity metadata and
private behavior/evaluator boundaries are documented and checked.

## Executed checks

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 507 passed in 83.70s (0:01:23) |
| New registry + original resource/telemetry/console focused checks | 96 passed in 9.26s |
| `python -m canary_ssm.release_fixture --out examples/release_registry` | All six case gates passed |
| Release form real HTTP/DOM harness | Seven computed gates passed |
| In-app browser composed registration | Visible registration success, immutable version/hash and all four numeric parameters |
| Existing/new engine replay artifacts | All 34 verify |
| Scenario members | All 22 verify |
| Legacy resource compatibility | All original host/service fields and workload RNG states equal across three 30-tick cases |
| JavaScript syntax | app.js and release UI harness exit 0 |

The browser check used accessibility state; no layout screenshot claim is made.
Original tests were not edited or skipped. A direct FIFO helper regression exposed
response-counting coupling and was fixed by counting emitted batches in the
resource update. Public pending-response snapshots were restricted to counts,
keeping scheduled probabilities private. Raw evidence is in
`release_registry_validation.json`.

## Computed trace acceptance summary

This table is generated from `examples/release_registry/summary.csv`. It describes
eight-tick, four-canary resource traces, not detector performance or production
fidelity. Delay holds response memory without adding CPU work; errors consume
work and are distinguished from drops. The error case declares probability one.

| Case | CPU processed | Responses | Errors | Maximum retained MB | Maximum pending responses | Acceptance pass |
| --- | --- | --- | --- | --- | --- | --- |
| healthy | 650 | 650 | 0 | 0.0 | 0 | True |
| cpu | 627 | 627 | 0 | 0.0 | 0 | True |
| memory | 650 | 650 | 0 | 344.0 | 0 | True |
| errors | 650 | 650 | 650 | 0.0 | 0 | True |
| delay | 650 | 504 | 0 | 0.0 | 52 | True |
| composed | 650 | 504 | 54 | 43.0 | 52 | True |

`compatibility.csv` records the healthy, legacy CPU and legacy memory before/after
comparison on all original fields and workload RNG state. Statistical generator
and inference code are untouched. No calibrated benchmark is reported.

## Changed files and limits

New source is `releases.py` and `release_fixture.py`, with a new test module and
DOM harness, two example registrations, immutable records and six replay/trace
cases. `operations.py`, `resources.py`, `engine.py` and private
`telemetry_evaluator.py` integrate the registry and response dynamics. Web assets
add a reviewed JSON workflow and local rejection feedback. No source execution
or new detector is enabled. The original class/rack/nested Gaussian pipelines,
research artifacts and statistical paired data are preserved.

Resource/operations source changes require refreshed world replays, world scenario
member hashes, static snapshot provenance and resource CSV/figure artifacts.
The registry code/behavior version is now included in strict replay compatibility.
Old external artifacts are not silently reinterpreted. The source is an extracted
archive, with no git commit or merge claim.

Registry assets persist across simulation reset but remain bounded per session.
Response waiting uses fixed tick-quantized delays and existing network accounting;
there is no packet-level egress or retry model. Error rates are observed resource
counts, not new typed minute/SSM features. Pure error-only regression detection,
physical-model fidelity and broader browser/device layout remain unverified.
