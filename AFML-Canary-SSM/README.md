# canary_ssm: Hierarchical Canary State-Space Model (V1 + Version 2)

> **Lightweight distribution:** bulk historical runs, telemetry exports and result caches have been removed. Source, fitted models/policies, required test fixtures and built-in dashboard demos remain. See [distribution contents and running instructions](docs/lightweight_distribution.md). Older sections describing saved experiment outputs refer to the full research archive.


The small frozen audit fixture required by the legacy reproduction test is now
included at `data_audit/model_pooled_dev`. No test setup is needed after
extracting this archive. Its executed rebuild recipe and provenance are
documented in [the missing-model fix](docs/wp/LEGACY-FIX.md).
Current full-suite verification after immutable release registration: **507 passed in 83.70s (0:01:23)**.
The earlier repair report remains a historical checkpoint.

## Immutable declared-behavior releases

```bash
python -m canary_ssm.release_fixture --out examples/release_registry
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/release_registry
```

In **Releases**, build or upload a schema-v1 registration manifest, optionally
attach source, then register an immutable ID/version. Healthy, extra CPU work,
retained-memory growth, errors and post-processing response wait have explicit
units/bounds and compose through the resource model. Source is **never executed**.
Two immutable example versions are included. Detector inputs receive identity/
exposure metadata, not behavior labels. See [schema, equations and API](docs/release_registry.md).

## Detector replay and streaming dashboard

```bash
python -m pip install -e '.[dev,report]'
python -m canary_ssm world-dashboard --port 8765 --state-dir runtime/monitor_demo
```

Open `http://127.0.0.1:8765`, choose **Monitoring**, then load a saved demonstration.
Raw latency, adjusted residuals, posterior effect/95% interval, host risk, rack
effect and host deviation use backend host IDs. Independent and two versioned
pooling settings share the same replay. Four algebraic demonstrations and a
validated external stream receiver are included. All results remain uncalibrated;
no automatic world inference or alarms are enabled. See [commands, format, source
labels and limits](docs/detector_dashboard.md). Renderer/API checks pass; visual
browser verification remains unavailable in this runtime.

## Opt-in nested global/rack/host diagnostics

```bash
python -m canary_ssm.nested_fixture --out examples/nested_hierarchy
python -m canary_ssm.nested_hierarchy --settings configs/hierarchy_nested_v1.json --model examples/grouped_hierarchy/model_rack.json --adjusted examples/grouped_hierarchy/adjusted_rack.json --out nested_diagnostic.json
```

A separate nested variant uses deterministic host-weighted rack contrasts and
within-rack sum-zero host deviations. It retains the full joint posterior,
exports all component/cross uncertainty, and excludes AR noise from effect risk.
It requires explicit opt-in and remains **diagnostic only**: new development
selection and calibration are required, with decision eligibility false and no
thresholds or alarms. See [basis equations, crossed-group limits and gate](docs/nested_hierarchy.md).

## Explicit class/rack constrained hierarchy

```bash
python -m canary_ssm.hierarchy_fixture --out examples/grouped_hierarchy
python -m canary_ssm.public_hierarchy --model examples/grouped_hierarchy/model_rack.json --adjusted examples/grouped_hierarchy/adjusted_rack.json --group-by rack_id --settings configs/hierarchy_rack.json --out rack_posterior.json
```

Original class-host research code is preserved. The public adapter defaults to
class grouping; rack grouping is explicit and versioned. One joint theta/b/AR
filter retains full covariance and returns group effects, sum-zero host deviations
and total host effects separately. Effect risk excludes AR noise. Numerical
fixtures demonstrate peer borrowing and a deliberately unpooled negative control.
See [equations, group policy and CLI](docs/grouped_hierarchy.md). Scores remain
uncalibrated and dashboard monitoring remains disconnected.

## Common Gaussian engine and public comparison CLI

```bash
python -m canary_ssm.kalman_fixture --out examples/kalman_engine
python -m canary_ssm.public_filter --model examples/control_adjustment/model_rank1.json --adjusted examples/control_adjustment/adjusted_rank1.json --out comparison.json
```

The existing Cholesky/Joseph filter now serves a public adjustment adapter with
carried preperiod AR state, exposure-only effect priors, independent/pooled
maps and full shared white covariance. EWMA/CUSUM/top-K use the same masked
observations and return statistics, with no fake posteriors. Saved numerical
checks include the requested scalar fractions and an independent multivariate
reference. Scores are **uncalibrated**; thresholds/alarms are null and dashboard
monitoring remains disconnected. See [equations, onset convention and limits](docs/public_gaussian_filter.md).

## Development-frozen public workload and control adjustment

```bash
python -m canary_ssm.adjustment_fixture --out examples/control_adjustment
python -m canary_ssm.public_adjustment fit --slice examples/control_adjustment/public/healthy_development_slice.json --service-id fixture-service --canaries h0 h5 --role development --healthy --provenance-id algebraic-public-fixture-v1 --policy-json configs/rack_adjustment_rank1.json --out adjustment_model.json
python -m canary_ssm.public_adjustment apply --model adjustment_model.json --slice examples/control_adjustment/public/monitoring_slice.json --service-id fixture-service --exposure-time 4860 --out adjusted.json
```

Fits nuisance parameters on declared healthy development data, adapts canary
loadings only from available pre-exposure windows, and uses fresh unexposed
controls. Exports residuals, masks, flags, reference uncertainty and full shared
covariance. Rack policies retain 80% observed canaries and three controls per
monitored rack; rank zero is available. Control contamination is an open challenge.
See [equations, limits and CLI](docs/public_adjustment.md). The algebraic fixture
is an acceptance check; the world detector remains disconnected.

## Small paired scenarios and data roles

```bash
python -m canary_ssm world-scenarios --out examples/scenario_bundles
python -m canary_ssm.world_evaluator --out examples/world_evaluator
python -m canary_ssm world-scenarios --plan-only --out scenario_plan
```

Seven world templates cover healthy, host/rack faults, shared surge, transient
and persistent degradation, and recovery. Smoke pairs are included; development,
threshold-calibration, null-validation and final-test bundles are registered on
disjoint fresh seeds. Statistical pairs retain the exact additive injection
identity; physical-world pairs share exogenous uniforms while queues/routing may
diverge. Public IDs hide scenario/member labels; truth is stored separately.
See [the bundle and evaluator contract](docs/scenario_bundles.md). These tiny
fixtures do not establish calibrated detector performance.

## Public telemetry and causal minute windows

The console emits validated public records with run/host/rack/service/release
identity, simulated event/arrival times, completed-request latency statistics,
workload and fresh masks. Minute inputs freeze at their decision deadline;
duplicates, late arrivals, missing minutes and carried values cannot backfill
older inputs. Injection labels are exported separately for evaluation.

```bash
python -m canary_ssm.telemetry_fixture --out examples/public_telemetry
python -m canary_ssm world-run --config configs/world_telemetry.yaml --ticks 240 --run-id demo-01 --out run.json --telemetry-out telemetry_export
```

See [public schema, sufficient statistics and causal input construction](docs/public_telemetry.md).
`/api/telemetry` and Monitoring's minute table use backend committed records.
The SSM remains disconnected; this does not rewrite inference or calibrate it
for the new quantized completion-latency measurements.

## Background fault scenarios

Independent per-host, correlated per-rack and shared world disturbances now use
explicit rates per simulated second, bounded ranges, cooldowns and concurrency
limits. Fault Lab has enable/disable and developer scenario preview controls.
Schedules are independent of candidate release profiles and inference.

```bash
python -m canary_ssm world-fault-preview --config configs/world_console.yaml --out scenario_preview.json
python -m canary_ssm.scheduler_fixtures --out examples/background_faults
```

See [the sampling contract and fixture commands](docs/fault_scheduler.md).
The console starts with background effects disabled; the enabled rate fixture
is `configs/world_scheduler_rates.yaml`. All-healthy and explicit fixed-schedule
configs are included. Use a fresh state directory when upgrading simulator code.

## Local world dashboard

```bash
python -m canary_ssm world-dashboard --config configs/world_console.yaml --state-dir runtime/world_dashboard --port 8765
```

Open `http://127.0.0.1:8765` for topology drill-down, host CPU/memory/latency
traces and backend-owned start/pause/resume/step/reset/playback controls. Refresh
reconnects to the same run. World, Releases, developer Fault Lab and Monitoring
views support sample/unexecuted uploads, valid canary preview, simulated deploy,
manual rollback, five typed fault mechanisms and seeded schedules. Monitoring
shows **DETECTOR NOT CONNECTED**. Saved runs and command outcomes persist.
See [console setup and replay](docs/console.md) and [fault contracts](docs/faults.md).

```bash
python -m canary_ssm.console_fixture --out examples/console_demo
python -m canary_ssm.fault_fixtures --out examples/faults
```

These headless demos need no browser or SSM. Included CSV traces, separate
developer truth and acceptance checks come from actual deterministic runs.
Upload contents never execute; their declared profile drives simulated behavior.

## Healthy workloads, queues and host resources

```bash
python -m canary_ssm world-fixtures --out examples/resource_world
python -m canary_ssm world-run --config configs/world_recovery.yaml --ticks 120 --out recovery.json --trace-out recovery_trace
python -m canary_ssm world-replay --artifact recovery.json
```

The low-load, increased-load and recovery fixtures export synthetic CPU,
memory, queue, completion/drop and latency-proxy CSVs plus visible PNG traces.
See [the resource equations and assumptions](docs/resources.md). Latency is
explicitly an analytical queue/service estimate; it is not a p95 statistic.

## Deterministic headless world clock

```bash
python -m canary_ssm world-run --config configs/world_clock.yaml --ticks 100 --out world_clock_run.json
python -m canary_ssm world-replay --artifact world_clock_run.json
```

The engine supports start/pause/resume/step/reset, stable scheduled-event order,
separate RNG streams and verified replay. `world_clock.yaml` uses static adapters;
resource configs opt into the bounded workload/resource adapter in the same
engine. See [the engine contract](docs/engine.md).

## Static physical-world topology

The interactive fixture contains one data center, four racks, twenty hosts and
twenty service-replica placements. Validate it and export a JSON snapshot:

```bash
python -m canary_ssm topology --config configs/world_interactive.yaml --out topology_snapshot.json
```

See [the topology contract](docs/topology.md) for custom YAML, capacities, usage,
lifecycle, validation rules and round-trip loading. This static topology is the
first virtual-world chunk; the clock and resource profiles reuse these records.

Statistical-track research codebase for detecting weak, persistent canary-release latency regressions under shared workload and environmental shifts. Includes a reproducible synthetic simulator, workload regression & rank-1 control factor adjustment, Joseph-form Kalman / hierarchical Gaussian state-space filters, classical & prewhitened sequential comparators, clairvoyant upper-bound oracles, leakage-safe order-statistic calibration, Beta-Binomial null gating, and diagnostic study runners.

> **For LLMs / Reviewers Reading This Repository:**
> Start with [`results/V2_IMPLEMENTATION_DETAILED_SUMMARY.md`](results/V2_IMPLEMENTATION_DETAILED_SUMMARY.md) for the complete technical and empirical narrative of Version 2 (`P0 -> P1 -> P1b`), followed by [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md), [`docs/baselines.md`](docs/baselines.md), and [`results/final/report.md`](results/final/report.md) (V1 baseline).
>
> **Tracked vs. Ignored Files:** Both code (`canary_ssm/`, `tests/`, `configs/`, `docs/`, `scripts/`) **and** lightweight reports, tables, plots, manifests, and fitted model/policy configs (`results/`, `artifacts/`) are committed so results are immediately inspectable on GitHub. Heavy generated `.npz` rollouts (`data/`, `data_*/`), caches (`cache/`), `.resume_*/` checkpoints (`*.pkl`), `.venv/`, and incomplete `results/smoke_ora_check/` are gitignored and regenerable deterministically via the commands below.

---

## 1. Tested Environment & Setup

- **Hardware / OS used for saved runs:** CPU-only (no GPU required; neural/Mamba track deliberately omitted), Windows 11 (`Windows-11-10.0.26300-SP0`), `Intel64 Family 6 Model 167 Stepping 1` (12 logical threads; parallel stages default to `cpu_count - 2`, benchmarked with `workers=1` and `workers=8`), Python `3.12.10`.
- **Key libraries (`requirements.lock`):** `numpy==2.5.4`, `scipy==1.18.1`, `pandas==3.1.1`, `statsmodels==0.15.0`, `matplotlib==3.11.2`, `pyyaml==6.0.3`, `hypothesis==6.124.9`, `tabulate==0.10.0`, `pytest==9.2.0` (`pyproject.toml` supports `Python >= 3.10`).

### Windows Setup
```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev,report]"
# Or for exact pinned package versions from the reference environment:
# python -m pip install -r requirements.lock
python -m pytest -q
```

### Linux / macOS Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,report]"
python -m pytest -q
```

**Verified test suite status (`HEAD`):** `107 passed in 111.35s` (`test_simulator.py`, `test_kalman.py`, `test_kalman_properties.py`, `test_hierarchy_factor.py`, `test_nuisance_and_chain.py`, `test_decision_metrics.py`, `test_handoff_changes.py`, `test_p0_housekeeping.py`, `test_p1_protocol.py`, `test_p1b_baselines.py`).

---

## 2. Project Timeline, Saved Results & Exact Scope

| Stage | Git Reference | What Was Implemented & Executed | Key Saved Outputs |
|---|---|---|---|
| **V1 Baseline** | `v0.1-first-full-run` (`8472b2a`) | Initial end-to-end statistical pipeline, null calibration audit, Exp 7 causal regime rule, Exp 8 robustness diagnostics | [`results/final/`](results/final/report.md), [`results/audit/summary.md`](results/audit/summary.md), [`results/experiment_7/`](results/experiment_7/report.md), [`results/experiment_8/`](results/experiment_8/report.md), [`results/runtime_scaling.csv`](results/runtime_scaling.csv), `artifacts/{model,policy}/` |
| **V2 Phase P0** | `v0.2-p0` (`ca0b37e`) | Disjoint 1M-block seed registry (`seeds.py`), cryptographic provenance manifests (`manifest.py`), deterministic Windows multiprocessing & JSONL resume (`parallel.py`), **X-0.1** determinism check (`1` vs `8` workers: `538.401s -> 142.456s`, 3.78x speedup, bitwise-identical `per_rollout_metrics.csv` SHA-256) | [`results/x01/`](results/x01/w1/experiment_manifest.json) |
| **V2 Phase P1** | `v0.3-p1` (`7eb2e8d`) | Regime separation (`plain_main.yaml`, `step_regime.yaml`), Policy Schema v2, `canary_ssm/studies/` guards, **X-0.2(a/b/c)** anomaly diagnoses, **X-0.3** 5-fold CV + 1-SE + edge expansion tuning (`v2.0-exp2`, `fit_s = 4665.79s`, 0 failures), **X-0.4** `B=2000` plain calibration & 14,000-null/method Beta-Binomial Gate G2 (`118/119` pass; `hier_rank0` fails `S5_label_errors` at `9.65%`) | [`results/x02/`](results/x02/x02a/x02a_summary.md), [`results/x03/`](results/x03/x03_profiles.csv), [`results/x04/`](results/x04/x04_summary.md), [`artifacts/model_v2/`](artifacts/model_v2/model_config.json), [`artifacts/policy_plain/`](artifacts/policy_plain/gate_status.json) |
| **V2 Phase P1b** | `v0.4-p1b` (`aae8259`) | **`WP-E1`:** 7 causal sequential comparators (`wmean`, `ar_cusum`, `glr_window`, `sparse_mix_glr`, `bocpd`, `msprt`, `mw_judge`) with AR(1) prewhitening across missing gaps (`baselines_extra.py`). **`WP-E2`:** 3 clairvoyant reference upper-bound oracles (`oracle_cusum`, `oracle_bayes`, `oracle_subset`, `--oracles` CLI flag, `oracles.py`). Verified by `10` new unit tests (`107` total pass). | [`canary_ssm/baselines_extra.py`](canary_ssm/baselines_extra.py), [`canary_ssm/oracles.py`](canary_ssm/oracles.py), [`docs/baselines.md`](docs/baselines.md), [`tests/test_p1b_baselines.py`](tests/test_p1b_baselines.py) |
| **Phases P2–P4** | *(Not yet executed)* | Scaled `evaluate` benchmarks comparing P1b baselines & oracles, plus `E1..E8`, `R1..R8`, `G1..G8`, `RT-1..RT-3` from `docs/Canary_SSM_Change_Plan.pdf` | — |

---

## 3. Replicating Everything From Scratch

All random streams use deterministic 1M-block seeds (`canary_ssm/seeds.py`), so re-running these commands on another CPU machine reproduces the exact data, fits, calibration thresholds, and validation tables.

### A. Quick Smoke Check (~minutes)
```powershell
.\tasks.ps1 smoke
# Linux/macOS: bash scripts/smoke.sh
```

### B. Reproducing V2 Phase P0 (`X-0.1`: Determinism `w=1` vs `w=8`)
Evaluates the frozen V1 artifacts (`artifacts/model`, `artifacts/policy`) on the `test` split (`seed_base = 4000000`, `1,000` rollouts):
```powershell
python -m canary_ssm.cli simulate --config configs/legacy_mixture_with_step.yaml --role test --out data/legacy_test
python -m canary_ssm.cli evaluate --data data/legacy_test --model artifacts/model --policy artifacts/policy --out results/x01/w1 --workers 1 --allow-frozen --allow-regime-mismatch
python -m canary_ssm.cli evaluate --data data/legacy_test --model artifacts/model --policy artifacts/policy --out results/x01/w8 --workers 8 --allow-frozen --allow-regime-mismatch
```

### C. Reproducing V2 Phase P1 Diagnostics (`X-0.2a`, `X-0.2b`, `X-0.2c`)
```powershell
# Run all X-0.2 diagnostics together:
python -m canary_ssm.cli study x02 --model artifacts/model --policy artifacts/policy --out results/x02 --allow-frozen --allow-regime-mismatch

# Or individually: x02a, x02b, x02c
python -m canary_ssm.cli study x02a --model artifacts/model --out results/x02/x02a --allow-frozen
python -m canary_ssm.cli study x02b --model artifacts/model --policy artifacts/policy --out results/x02/x02b --allow-frozen --allow-regime-mismatch
python -m canary_ssm.cli study x02c --model artifacts/model --out results/x02/x02c --allow-frozen
```
*(In-package `study regime` and `study robust` runners are also available via `python -m canary_ssm.cli study regime ...` and `study robust ...`.)*

### D. Reproducing V2 Plain-Regime Fit, Calibration & 14,000-Null Validation (`X-0.3` & `X-0.4`)
```powershell
# 1. Generate dev data & calibration manifest (use --generate-on-the-fly for large null sets to save disk)
python -m canary_ssm.cli simulate --config configs/plain_main.yaml --role dev --out data/plain/dev
python -m canary_ssm.cli simulate --config configs/plain_main.yaml --role calibration --out data/plain/calibration --manifest-only
python -m canary_ssm.cli simulate --config configs/plain_main.yaml --role null_validation --out data/plain/null_validation --manifest-only

# 2. X-0.3: Nuisance MLE + 5-fold CV + 1-SE + auto edge expansion (v2.0 -> v2.0-exp2; ~78 min on 12-thread CPU)
python -m canary_ssm.cli fit --data data/plain/dev --out artifacts/model_v2 --grid configs/grids_v2.yaml --auto-expand --max-expansions 2 --k-folds 5 --cache-dir cache

# 3. X-0.4: Plain calibration (B=2000) & Gate G2 validation (2000 nulls x 7 families = 14,000 nulls/method)
python -m canary_ssm.cli calibrate --data data/plain/calibration --model artifacts/model_v2 --out artifacts/policy_plain --regime plain --generate-on-the-fly --resume
python -m canary_ssm.cli validate-null --data data/plain/null_validation --model artifacts/model_v2 --policy artifacts/policy_plain --generate-on-the-fly --resume
```

### E. Full Pipeline Shortcuts & Oracles
- `.\tasks.ps1 plain-pipeline` / `.\tasks.ps1 step-pipeline` (or `bash tasks.sh ...`) run end-to-end `simulate -> fit -> calibrate -> validate-null -> evaluate`.
- Pass `--oracles` to `calibrate`, `validate-null`, and `evaluate` to include `oracle_cusum`, `oracle_bayes`, and `oracle_subset` (`ORACLE`-tagged upper bounds excluded from real-method rankings).

---

## 4. Repository Structure

```text
canary_ssm_project/
├── canary_ssm/
│   ├── schema.py            # Data contracts; Rollout = detector-visible input only
│   ├── simulate.py          # Synthetic simulator + Truth (evaluator-only, never leaked)
│   ├── seeds.py             # Disjoint 1M-block deterministic seed registry (v2.0)
│   ├── manifest.py          # SHA-256 config/grid/model/policy/git provenance builder
│   ├── parallel.py          # Windows-safe multiprocessing, BLAS=1 pinning, JSONL resume
│   ├── factor.py            # Workload regression, rank-1 control factor, eligibility
│   ├── preprocess.py        # Per-class AR(1) / white nuisance MLE fitting
│   ├── kalman.py            # Joseph-form Kalman filter, Cholesky solves, missing gaps
│   ├── hierarchy.py         # Hierarchical / independent / pooled SSM effect detectors
│   ├── baselines.py         # matched_contrast, adj_ewma, adj_cusum, topk_cusum
│   ├── baselines_extra.py   # wmean, ar_cusum, glr_window, sparse_mix_glr, bocpd, msprt, mw_judge
│   ├── oracles.py           # Clairvoyant upper bounds (ORACLE labeled, --oracles flag)
│   ├── decision.py          # Order-statistic calibration (Schema v2), latched alarm, policy
│   ├── metrics.py           # Capped delay, host localization, Brier, Beta-Binomial & CIs
│   ├── experiments.py       # Pipeline stages, 5-fold/1-SE/edge-check tuning, caching
│   ├── report.py            # Markdown tables & plots generated strictly from saved CSVs
│   ├── cli.py               # CLI entry point (python -m canary_ssm / canary-ssm)
│   └── studies/             # Parameterised V2 studies (study_anomalies, study_regime, study_robust)
├── configs/                 # plain_main.yaml, step_regime.yaml, grids_v2.yaml, audit.yaml, ...
├── docs/                    # Canary_SSM_Change_Plan.pdf, DESIGN_DECISIONS.md, baselines.md, SANDBOX_AUDIT.md
├── scripts/                 # smoke.sh, audit_quick.sh, run_all.ps1, legacy Exp 7/8 scripts
├── tests/                   # 107 unit, causality, property, protocol, and P1b tests
├── artifacts/               # Saved V1 & V2 fitted model configs and calibrated policies
├── results/                 # Saved V1 & V2 reports, manifests, CSV tables, and figures
├── pyproject.toml           # Package & dependency definition (canary_ssm + canary_ssm.studies)
├── requirements.lock        # Pinned environment lockfile (-e .)
├── tasks.ps1 / tasks.sh     # Task runners (test, smoke, plain-pipeline, step-pipeline, audit)
└── AGENTS.md                # Non-negotiable causality, anti-leakage & gate rules
```

See [`AGENTS.md`](AGENTS.md), [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md), and [`docs/baselines.md`](docs/baselines.md) for strict anti-leakage, causality, and calibration contracts.

### Fixed-cohort service rollout

Use **Releases → Fixed-cohort service rollout** for CREATED → BASELINING → CANARY,
manual pause/resume, promotion, rollback and an append-only transition history.
Canaries cover racks/classes with three controls per group; baseline/candidate
traffic weights stay fixed. Promotion ends evaluation; rollback restores baseline
versions and restarts service replicas. Monitoring is uncalibrated and never
uses injected truth to choose a transition. See [docs/rollouts.md](docs/rollouts.md).

```sh
python -m canary_ssm.rollout_fixture --out examples/rollouts
python -m canary_ssm.cli world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/rollout-dashboard
```

### Process memory, OOM and resource health

```sh
python -m canary_ssm.cli world-dashboard --config configs/world_memory.yaml --port 8765 --state-dir runtime/memory-dashboard
python -m canary_ssm.memory_fixture --out examples/process_memory
```

Select `sample-leak-v3` or `sample-cache-v1`. World host details show memory
headroom, request-normalized growth, response latency, process events and an
actual restart button. The separate advisory says **observed memory-growth
warning, not SSM proof of a code-level leak**; it never chooses a deployment
transition. See [docs/process_memory.md](docs/process_memory.md) for allocation,
OOM/restart/rollback semantics, the five development fixtures and legacy behavior.

### Latched first-crossing policy

The new policy layer freezes development/model/preprocessing/simulator/protocol
bindings, calibrates full-horizon eligible null maxima, audits independent nulls,
and latches the first strict crossing. Compatible qualified policies default to
automatic PAUSE and manual ROLLBACK; simulated auto rollback requires explicit
pre-baseline opt-in. Healthy promotion requires a complete eligible evidence
budget. Platform/resource pause reasons and combined-action false alerts remain
separate.

```sh
python -m canary_ssm.policy_fixture --out examples/first_crossing --B 2000 --n-validation 2000
python -m pytest tests/test_first_crossing_policy.py -q
```

The included statistical Gaussian calibration is **not resource-world calibration**;
its hash/domain mismatch is rejected by the live world adapter. See
[docs/latched_policy.md](docs/latched_policy.md) for the exact v1 protocol, APIs,
uncertainty, missing-data behavior and activation requirements.

## Matched physical-world policy checkpoint

`examples/world_policy` adds actual resource-world healthy development,
full-horizon null calibration and independent validation for
`configs/world_policy_v1.yaml`. Its measured qualification and scope are in
[docs/wp/WORLD-POLICY.md](docs/wp/WORLD-POLICY.md). This is a separate
independent-effect, four-minute, all-healthy-background protocol; other model,
fault, loss and advisory configurations require their own qualification.

```sh
python -m pip install -r requirements-world-policy.lock
python -m pip install -e . --no-deps
python -m canary_ssm.world_policy_http_demo --out examples/world_policy
python -m canary_ssm world-dashboard --config configs/world_policy_v1.yaml --port 8765 --state-dir runtime/world-policy
```

Upload `examples/world_policy/http_alarm/session.json` in the dashboard to
replay the real public-telemetry → posterior → automatic PAUSE → manual ROLLBACK
path. The healthy session and every smoke outcome, including HOLDs, are beside it.
This alarm replay is a selected smoke illustration, not a power estimate.
For interactive scoring, run
`python -m canary_ssm.world_policy_live --policy examples/world_policy/policy.json`
alongside the backend. The producer polls committed telemetry and never advances
the world. Setup, exact baseline/exposure timing, replay and regeneration:
[docs/world_policy.md](docs/world_policy.md).

## Integrated seven-view dashboard

World, Host Details, Fault Scenarios, Release Registry, Canary Rollout, Monitoring Evidence and Run History share one backend-owned simulation.

```sh
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/integrated-console
python -m canary_ssm.integrated_console_fixture --out examples/integrated_console
```

Open `http://127.0.0.1:8765/#rollout`. Backend-balanced cohort preview, manifest registration, baseline/exposure/pause/rollback, model/policy context, durable command recovery, backend checkpoints and read-only replay/export are integrated. Paused/recovered backend sessions are included in `examples/integrated_console`. No uploaded source is executed and no fake detector state is shown.

[Setup and boundaries](docs/integrated_dashboard.md) · [executed checks](docs/wp/INTEGRATED-DASHBOARD.md).

## Offline truth-separated replay evaluation (v2)

The evaluator compares adjusted classical methods, independent effects, complete
pooling and declared hierarchies on identical saved public replays, with separately
fitted/calibrated ablations. Research latent outcomes and physical-world offline
paired-latency/infrastructure outcomes have separate tables. Hidden truth is joined
only in the offline evaluator. See [the evaluator guide](docs/evaluator_comparison.md)
and [execution evidence](docs/wp/EVALUATOR.md).

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m canary_ssm.replay_evaluator check-final-lock --out examples/evaluator_v2
python -m canary_ssm.evaluation_report --study examples/evaluator_v2
```

The final-test bundle remains sealed pending the governing per-family gate;
mixture-null qualification is not a resolution of the earlier shared-step issue.
Smoke outcomes and concurrent-load performance measurements are diagnostic.
