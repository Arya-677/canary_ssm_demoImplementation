Latest extension: offline evaluator v2; see `evaluator_comparison.md` and
`wp/EVALUATOR.md` for current targets, executed audit, tests and limitations.
Earlier sections below retain their historical scope.

# Implementation status

Latest checkpoint: separate latched policy/controller; **566 tests pass**. Earlier process-memory checkpoint: 538 tests. Earlier rollout result: 519 tests. See the final table and `docs/rollouts.md`. Earlier sections retain their historical scope.

Updated 14 November 2026. This checkpoint covers virtual-world chunks 01–04 plus the console and typed-fault extension.
Earlier typed-fault checkpoint suite: **385 passed in 80.43s (0:01:20)**; no preexisting tests modified or skipped.
The previous repository-wide audit was interrupted and is not represented here
as complete. Statuses below refer to inspected source and executed checks.

| Requirement | Status | Actual implementation / evidence | Smallest next patch |
| --- | --- | --- | --- |
| Data-center and rack records | implemented | `topology.DataCenter`, `Rack`; IDs and center references validated by `Topology.__post_init__` | None for chunk 01 |
| Host identity, parentage and metadata | implemented | `topology.Host`; host/rack/center IDs, integer `class_id`; cross-record parent validation | None for chunk 01 |
| Immutable capacities | implemented | Frozen `HostCapacity`; cores, memory MB, disk MB, network Mbps; finite positive validation | None for chunk 01 |
| Usage and lifecycle separate from capacity | implemented | Frozen `HostUsage` and `HostLifecycle`; `Host` checks usage bounds; updates create new records with `dataclasses.replace` | Clock engine can replace snapshots later |
| Service-replica placement | implemented | `ServiceReplica` with required service/replica/host/release IDs; unknown hosts rejected | Later release registry can resolve opaque release references |
| Duplicate IDs and conflicting parentage | implemented | Global entity-ID uniqueness; rack center existence; host center/rack agreement; duplicate YAML keys rejected | None for chunk 01 |
| Configurable loader | implemented | `load_topology`, `Topology.from_dict`; shared `configuration.read_yaml_mapping` used by existing `experiments.load_config` | None for chunk 01 |
| Interactive fixture | implemented | `configs/world_interactive.yaml`; one center, four racks, five uniquely identified hosts per rack; one replica per host | None for chunk 01 |
| Serializable snapshot and round-trip | implemented | `Topology.snapshot`; detached JSON-safe values, stable IDs, parent links, units documented in `docs/topology.md`; CLI export reloaded successfully | None for chunk 01 |
| Documented CLI | implemented | `cli.main` command `topology --config ... [--out ...]`; module and installed entry points share handler | None for chunk 01 |
| Focused acceptance checks | implemented | `tests/test_topology.py`: **76 passed in 7.91s**; CLI snapshot export and reload also executed | None for chunk 01 |
| Full regression verification (missing-fixture repair) | implemented | Executed: **259 passed in 71.71s**. The legacy test's missing frozen audit fixture was genuinely rebuilt from the existing development recipe and included in the archive; no existing tests changed or skipped | None for this failure |
| Reproducible legacy audit fixture | implemented | `data_audit/model_pooled_dev`, `configs/legacy_audit_fixture.yaml`, `scripts/prepare_legacy_audit_fixture.py`; generation manifest, nuisance diagnostics and file hashes included; narrow ignore exceptions preserve small artifacts | Rebuild to a new directory when intentionally changing the recipe |
| Deterministic clock and controls | implemented | `engine.SimulationEngine`: explicit tick, start/pause/resume/step/reset; wall time never advances state | None for chunk 02 |
| Stable tick and tied-event order | implemented | `_tick_once`: events → routing → resources → observations → snapshot publication; ties follow insertion index | None for chunk 02 |
| Separate seeded streams | implemented | `RNG_STREAMS`, explicit PCG64/SeedSequence streams; tests independently consume workload/faults/host_noise/telemetry_loss | Later phases consume the corresponding streams |
| Reset and verified replay | implemented | `_initialize`, `save`, `replay`; restores configured world/RNG/event queue, retains ordered reset log | Version future adapters before replaying their data |
| Headless 100-tick fixture | implemented | `configs/world_clock.yaml`; `world-run` and `world-replay` executed; tick=100, simulated_seconds=100, verified replay | None for chunk 02 |
| Engine/topology focused tests | implemented | `tests/test_engine.py` and `tests/test_topology.py`: 104 passed in 2.54s | None for chunk 02 |
| Service request arrivals and routing | implemented | `resources.ResourceModel.route`: Poisson service arrivals, shared traffic factor, equal-probability routing to ready hosts | None for chunk 03 |
| Bounded queues, CPU processing and partial requests | implemented | `resources.fair_work`, `_consume`, `update`: FIFO cohorts, per-replica queue cap, shared host core-seconds, carried head progress | None for chunk 03 |
| Baseline/temporary/retained memory | implemented | `reserved_memory`, `temporary_memory`, memory admission, end/peak trace fields; healthy retained allocation stays constant | Future leak/process chunk can introduce retention dynamics |
| Drops and unavailable hosts | implemented | Separate queue/memory/arrival-limit/no-route/old-unavailable-queue counts; conservation identities verified | Future faults can drive serving availability |
| Latency responds to service work and queues | implemented | `latency_proxy_ms`: documented analytical service/backlog estimate; no percentile claim | Request samples required before any empirical p95 |
| Low-load, increased-load and recovery fixtures | implemented | `configs/world_{low_load,increased_load,recovery}.yaml`; `world-fixtures`; actual CSV/PNG/replay outputs in `examples/resource_world` | None for chunk 03 |
| Resource/engine/topology acceptance checks | implemented | 127 focused cases passed in 4.18s; `fixture_checks.json` reports all resource-bound, accounting, recovery and replay checks true | None for chunk 03 |
| Typed platform faults and seeded schedule | implemented | `faults.FaultEvent`, `operations.before_tick`; five actual resource mechanisms; all five before/during/after fixtures pass | None for requested mechanisms |
| Release-induced slow/leak behavior | implemented | Per-replica work/retention profiles, explicit registry selection, bounded growth and rollback cleanup | None for bounded simulation |
| OOM/process-killer realism | missing | Memory pressure and retained growth clamp to physical headroom; no OOM killer | Separate process lifecycle model if requested |
| Local dashboard and backend ownership | implemented | `dashboard.WorldController`, `make_server`, packaged `web/`; one locked engine/scheduler per server, reads do not advance it | None for chunk 04 |
| Physical drill-down and per-host charts | implemented | `web/app.js` renders center/rack/host references and selected backend history; actual HTTP/DOM-state checks passed | Browser verification passed at 1280×720 |
| Validated controls and playback | implemented | Backend command validation, state/run/epoch guards, duplicate-ID receipts, wall-only speed controls | None for chunk 04 |
| Connection and monitoring labels | implemented | Polling, timestamps/revisions, stale/disconnected/recorded states; Monitoring not connected | Connect monitoring only in its later guide chunk |
| Recorded fixture without engine | implemented | `web/recorded_snapshot.json`, `?recorded=1`; ordinary static-server path checked | None for chunk 04 |
| Dashboard backend/HTTP tests | implemented | `tests/test_dashboard.py`: 22 passed in 1.72s; JS syntax and DOM-state checks passed | None for chunk 04 |
| Browser layout/manual UI verification | implemented | 1280×720 in-app browser: world, release preview 4/16, deploy, manual CPU fault, observed monitoring, next-tick rollback verified | Broader device/accessibility testing remains unverified |
| Simulated deployment and manual rollback | implemented | `DemoOperations.preview/command/before_tick`; validated per-rack controls, version changes, queued transitions and restart drops; console exit gate passed | No real code deployment requested |
| World-to-SSM adapter | missing | Dashboard resource observations never call `hierarchy.EffectDetector`; neutral detector label | Define observation units/aggregation and causal eligibility adapter before connecting |
| Saved run persistence and verified replay | implemented | `WorldController.export_run/_checkpoint`, `load_run`; restart restoration and idempotence tests pass | Animated replay/scrubbing remains missing |
| Artifact execution | missing | Upload bytes are stored, hashed and explicitly marked unexecuted; declared bounded profile only | Sandboxed execution would be a separate feature |
| Fault truth separation | implemented | `developer_truth`, separate Fault Lab route and explicit replay artifact; absent public state/telemetry | Keep future detector input on telemetry path |

Run commands and test details are recorded in [the checkpoint report](wp/TOPOLOGY-01.md).
The topology schema is documented in [topology.md](topology.md).

Chunk 02 commands, limits and evidence: [engine contract](engine.md),
[clock checkpoint](wp/ENGINE-02.md), and `docs/wp/engine_validation.json`.
The saved 100-tick replay is `examples/world_clock_100_ticks.json`.

Chunk 03 contract/equations: [resources.md](resources.md). Checkpoint and raw
verification: `docs/wp/RESOURCES-03.md`, `docs/wp/resource_validation.json`.
Previous external replay artifacts are subject to the existing strict source-hash
guard; the bundled static sample was regenerated for this revision.

Chunk 04 setup and boundaries: [dashboard.md](dashboard.md).
Checkpoint and saved evidence: `docs/wp/DASHBOARD-04.md` and
`docs/wp/dashboard_validation.json`. No engine/inference source or model
artifacts were changed for the dashboard.

Subsequent repair of the missing legacy test dependency is documented in
`docs/wp/LEGACY-FIX.md`; raw verification is in
`docs/wp/legacy_fix_validation.json`. Earlier checkpoint failures remain as
historical records. This repair adds a new frozen audit fixture and does not
modify the preexisting `artifacts/` models or inference implementation.


Current extension contract: [console.md](console.md), [faults.md](faults.md).
Executed commands and validation: [CONSOLE-FAULTS.md](wp/CONSOLE-FAULTS.md),
`docs/wp/console_fault_validation.json`. Earlier check counts and interrupted
verification notes above describe their original checkpoints, not current failures.


## Background scheduler checkpoint

| Requirement | Status | Actual implementation / evidence | Smallest next patch |
| --- | --- | --- | --- |
| Rate scheduler and scope scaling | implemented | `fault_scheduler.FaultRate`, `_sample`; per-target hazard/unit/stream tests | None for bounded grid sampling |
| Cooldowns, ranges, caps and deterministic admission | implemented | `BackgroundFaultConfig`, `_fixed/_sample`; hand-computed timing, rejection counters and fixture gates | Continuous-time event sampling is not requested |
| No-release background vs deployment profiles | implemented | `DemoOperations.background` independent from registry/profiles; deployment-independence and healthy-RNG tests | None |
| Persisted pre-generated schedule | implemented | `SimulationEngine.artifact/replay`; complete background manifest/hash/source guards, toggle command log | Old external runs require deliberate migration or regeneration |
| Enable/disable and scenario preview | implemented | `background_set_enabled`, developer Fault Lab API/UI, `world-fault-preview`; real API DOM harness passes | New panel visual browser QA remains unverified |
| All-healthy/fixed/rate fixtures | implemented | `world_scheduler_*.yaml`, `scheduler_fixtures.export_fixtures`; checked CSVs, truth, manifest and replay bundles | None |
| Scheduler-to-inference isolation | implemented | No inference imports/changes; AST boundary test; public state excludes scheduler fields | Keep future adapter telemetry-only |

See [fault_scheduler.md](fault_scheduler.md) and [FAULT-SCHEDULER.md](wp/FAULT-SCHEDULER.md). Earlier test counts remain historical.


## Public telemetry checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Public run/host/rack/class and service/release metadata | implemented | `telemetry.PublicRecord`, engine source adapter; strict field/parentage validation and true-field rejection tests | None |
| Completion latency and request-weighted sufficient statistics | implemented | `ResourceModel._consume` captures FIFO cohorts; pipeline emits arithmetic/log sums and squared sums; hand-computed checks | Sub-tick timings or empirical percentiles remain separate work |
| Minute aggregation and fresh masks | implemented | `CausalWindowStore._aggregate`; explicit missing roster rows, mixed-exposure rejection, no carried values counted fresh | None for declared replica-level windows |
| Delay, duplication and missing windows | implemented | `TelemetryConfig`, `TelemetryPipeline.emit/deliver_through`; separate telemetry-loss RNG and deterministic fixture | None for bounded transport simulation |
| Causal slices and immutable inputs/scores | implemented | `time_slice`, `score_once`, `causal_time_slice`; late backdating, exact deadlines and future perturbation tests | Actual SSM callback integration remains missing |
| Separate evaluator-only labels | implemented | `telemetry_evaluator`; separate export subdirectory and private replay member; AST isolation tests | No additive counterfactual latent effect is defined, so it is null |
| Public API, CLI, monitoring and replay | implemented | `/api/telemetry`, `--telemetry-out`, `--run-id`, separate minute table; HTTP/DOM checks and replay tests | Visual rendering of the new table remains unverified |

Contract: [public_telemetry.md](public_telemetry.md). Validation: `wp/PUBLIC-TELEMETRY.md` and `wp/public_telemetry_validation.json`. Earlier counts are historical.


## Paired scenario bundle checkpoint

| Requirement | Status | Actual files/functions and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Seven small world scenarios | implemented | `world_scenario_catalog.yaml`, `scenario_bundles.run_world_member`; saved smoke pairs and resource/telemetry traces | None for fixtures |
| Config/seed/command/public/separate truth storage | implemented | `export_world_pair`, `export_statistical_pair`, per-member manifests/data hashes, `verify_member` | None |
| Disjoint roles and indivisible pairs | implemented | `scenario_registry.PairSpec`, registry manifests, stage/member selection guards; fresh world/additive seed blocks | Larger frozen protocol before scientific calibration |
| Exact old additive pairing | implemented | Original `simulate.py` unchanged; wrapper checks y_harm-y_null=a+spill to 1e-12 and equal exogenous arrays/masks | None |
| Resource-world pairing | implemented | Opt-in uniform-quantile arrivals plus separate routing stream; recorded exogenous uniforms and equal exogenous state; queues/routing may diverge | No additive equality is applicable |
| Different generator IDs | implemented | `statistical-additive-latency-v1` vs `resource-world-scenarios-v1`; paired engine/replay manifests | None |
| Hand-labeled evaluator skeleton | implemented | `world_evaluator.OperatorLabel/classify`; independent hand cases and computed CSV gate | Define scientific labels and connect actual predictions separately |
| Threshold/null/final-test performance evaluation | missing | Roles reserved; no fitted world detector, thresholds or final predictions | Separate reviewed frozen experiment protocol |

Earlier typed-fault checkpoint suite: **385 passed in 80.43s (0:01:20)**. See `scenario_bundles.md`, `wp/SCENARIO-BUNDLES.md` and raw `wp/scenario_bundle_validation.json`.


## Development-frozen public adjustment checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Reuse workload regression and rank-one pipeline | implemented | `factor._ols_host`, `fit_rank_one_controls`, `project_rank_one_controls`, `reference_covariance`; original rank-zero/rank-one outputs bitwise equal | None for preprocessing |
| Healthy development-only intercepts, workload coefficients, scales and noise | implemented | `public_adjustment.fit_development`, `HealthyDevelopment`; frozen lineage/hash, independent OLS checks, rejected non-development roles | Provide independently attested healthy world training data for an experiment |
| Pre-exposure-only canary loading adaptation | implemented | `FrozenAdjustment.prepare`; both event and receipt times precede freeze, actual early exposure caps fit, minimum 60 windows; flagged development fallback | None for documented fallback contract |
| Fresh unexposed controls at decisions | implemented | `_controls`, `panel_from_time_slice`; planned canaries excluded, all-service exposure and fresh masks enforced | Aggregate multiple same-service replicas per host before this adapter if needed |
| Residuals, masks, quality and reference uncertainty | implemented | `PreparedAdjustment.transform`; event/decision times, eligibility, flags, U, immutable fitted artifact | Connect output to a reviewed scoring adapter separately |
| Full shared canary covariance and single subtraction | implemented | `reference_covariance`; hand fixture gives U=4/3 and off-diagonal covariance 8; residual reference subtracted exactly once | Consumer must retain full matrix and avoid a second matched contrast |
| Per-rack overlap and research defaults | implemented | `AdjustmentPolicy`, `rack_adjustment_rank*.json`; 80% / 3 per represented group, local pre-support and runtime counts, workload-overlap diagnostics | Any altered demo threshold needs a new policy ID and reason |
| Control contamination challenge | implemented | Explicit challenge labels and independent failure test; plain projection moves when a control is contaminated | Robust control estimation remains missing and needs a separate method and validation |
| Rank-zero ablation | implemented | Same development workload fit and eligibility gates, zero factor/U/shared covariance | None |
| Public adjustment to world SSM and calibrated monitoring | missing | Offline CLI/API only; no new scorer or dashboard score; detector remains disconnected | Build causal full-covariance scoring adapter, then freeze/calibrate on distinct roles |
| Scientific performance of new public pipeline | unverified | Algebraic acceptance fixture only; no threshold/null/final benchmark | Use separately frozen development/calibration/null/final protocol |

See [public_adjustment.md](public_adjustment.md), [validation checkpoint](wp/PUBLIC-ADJUSTMENT.md) and raw `wp/public_adjustment_validation.json`. Latest full suite: **410 passed in 139.17s (0:02:19)**. Earlier checkpoint counts are historical.


## Common Gaussian filter checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Common Cholesky/Joseph engine | implemented | Existing `kalman.KalmanFilter` unchanged; requested scalar values, statsmodels comparison, multivariate conditioning and PSD tests pass | None for this engine |
| Subset observations and repeated missing-minute predictions | implemented | `KalmanFilter.step/predict`; `public_filter.GaussianEffects.run` converts simulated minute gaps and uses V principal submatrices | None for declared minute grid |
| White V separated from AR Qe | implemented | `Observations.V`, block-diagonal process covariance; full shared measurement covariance verified once, q_e squared only in Qe | Retain this distinction in future hierarchical public adapter |
| Healthy no-effect innovation fitting | implemented | Existing `fit_ar_class/scalar_nll` reused by development adapter; common-engine likelihood equivalence; new optimizer status/messages/bounds; frozen fit parameters unchanged | Validate model adequacy on independently healthy world data |
| Carry AR state and initialize effects at exposure | implemented | `GaussianEffects.run`; independent joint-conditioning check, nonzero carried AR mean/full covariance, pre-receipt guard and explicit exposure prior | No sub-minute onset policy yet |
| Independent and complete pooling interface | implemented | Same `GaussianEffects.run(Observations)`, existing `build_model` maps; full posterior effect covariance | Public constrained-hierarchy adapter remains separate work |
| EWMA/CUSUM/top-K on same inputs | implemented | `run_comparison`, original `run_baseline`; common masked residuals/scales and eligibility, baseline posterior/probability null | Calibrate each method separately at a common false-alert budget |
| Numerical fixtures, CLI and replayable saved inputs | implemented | `kalman_fixture`, `public_filter` CLI; scalar and multivariate CSV, rank-zero/rank-one outputs and manifest; CLI equals saved fixture | None for acceptance demonstration |
| Calibrated world detector/dashboard | missing | Scores explicitly uncalibrated; no thresholds/alarms and dashboard remains disconnected | Freeze protocol, calibrate/audit, then connect causal scoring transport |
| New method detection performance | unverified | No power/false-alert benchmark run | Separate frozen experiment on disjoint roles |

Latest full suite: **428 passed in 85.43s (0:01:25)**. See [contract](public_gaussian_filter.md), [checkpoint](wp/KALMAN-ENGINE.md) and raw `wp/kalman_engine_validation.json`. Earlier checkpoint counts remain historical.


## Constrained class/rack hierarchy checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Preserve class-host research mode | implemented | Original `hierarchy.py`, research entry points, artifacts and tests unchanged; original basis reused by `grouped_structure` | None |
| Explicit rack grouping | implemented | `public_hierarchy.GroupedParams`, `--group-by rack_id`, `hierarchy_rack.json`; frozen rack metadata and matching control policy required | Validate physical-world Gaussian adequacy separately |
| Incidence and orthonormal sum-zero basis | implemented | `grouped_structure` reuses `class_structure`; n by G C and n by n-G B; noncontiguous, singleton and permutation tests | None |
| Joint state F/H/L and full covariance | implemented | `GroupedGaussianEffects.run`, shared `_run_model`; independent joint-conditioning reference and retained theta/b/e cross covariance | None for declared Gaussian model |
| Induced prior and innovation covariance | implemented | Explicit output matrices; hand check and coordinate prior configuration | Fit/select effect priors only on a separately declared development protocol |
| Separate group, deviation and total effects | implemented | Group/host component means and full marginals plus group-deviation cross covariance; reconstruction tests | Dashboard presentation remains separate work |
| Actual pooling | implemented | `pooling.csv`: matched marginal-prior independent comparison with diagonal V; diagonal hierarchy negative control; distinct-dynamics pooling test | No detection-power claim without calibration |
| AR excluded from effect risk | implemented | `effect_risk_map=[C,B,0]`; tests project full posterior and perturb AR coordinates | None |
| Public independent/pooled compatibility | implemented | Shared-engine extraction preserves both incoming rank-zero/rank-one saved comparison outputs exactly | None |
| Calibrated physical-world detector/dashboard | missing | Scores remain uncalibrated; thresholds/alarms null, dashboard disconnected | Freeze tuning/calibration/audit protocol before integration |

Latest full suite: **445 passed in 88.95s (0:01:28)**. See [contract](grouped_hierarchy.md), [checkpoint](wp/GROUPED-HIERARCHY.md) and raw `wp/grouped_hierarchy_validation.json`. Earlier statuses/counts are historical.


## Opt-in nested global/rack/host checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Separately versioned opt-in variant | implemented | `nested_hierarchy.NestedParams`, required settings CLI, `hierarchy_nested_v1.json`; disabled defaults and no automatic loading | None for diagnostic use |
| Weighted deterministic rack contrasts | implemented | `nested_structure`: orthonormal rack incidence plus fixed Householder contrast; hand (2,1) contrast, projector and weighted-zero tests | None |
| Unequal/single/singleton racks | implemented | Empty R/B levels and numerical fixtures; preserved host order and permutation invariance | None |
| Three effect levels and AR dynamics | implemented | `NestedGaussianEffects.run`; explicit level persistence, innovation/prior SDs, H=[1,R,B,I] and effect map [1,R,B,0] | New development selection before promotion |
| Full joint/component uncertainty | implemented | Joint posterior, global/rack/host marginals, all three component cross-covariance pairs and total host covariance; independent Gaussian-conditioning and reconstruction checks | None for declared Gaussian diagnostic model |
| Global release component distinguished from workload factor | implemented | Separate residual-state g; public adjustment remains unchanged; explicit interpretation/limitations in outputs and contract | No causal attribution claim supported |
| Crossed class/rack guard | implemented | Rack-only config rejects class/extra-level fields; docs explain crossed incidence/constraints need a separate model | Design and validate crossed effects separately if needed |
| New selection/calibration requirement | implemented | Required protocol fingerprint; diagnostic score only, decision eligibility false, no thresholds/alarms or bypass configuration | Implement fresh development selection, freeze and calibrate/audit this variant under a separate protocol |
| Actual new selection/calibration | missing | Explicitly not performed; old artifacts cannot enable decisions through this API | Separate experiment package using disjoint registered roles/seeds |
| Existing research/public behavior | implemented | No existing inference code modified; all prior tests, models and fixtures preserved | None |

Latest full suite: **461 passed in 82.20s (0:01:22)**. See [contract](nested_hierarchy.md), [checkpoint](wp/NESTED-HIERARCHY.md) and raw `wp/nested_hierarchy_validation.json`. Earlier checkpoint counts are historical.


## Detector dashboard checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Saved and streaming detector output feeds | implemented | `monitor_feed.DetectorFeed`, authenticated `monitor_load/begin/append`, polling `/api/detectors`; real HTTP/producer CLI checks | Install a separately fitted live producer for a chosen world protocol |
| Six requested monitoring traces | implemented | `web/detectors.js`; raw latency, residual, posterior mean/95% band, host risk, rack effect, host deviation; six SVGs checked | Visual browser check remains unverified |
| Stable IDs and same-replay comparisons | implemented | Roster/parentage validation against `WorldController.engine.world`; shared frame input hash and independent/weak/strong versioned outputs | None for the declared adapter |
| Stronger/weaker actual pooling settings | implemented | `detector_dashboard_fixture`, `pooling_settings.csv`; both have positive prior/process sharing and ordered pair correlation; values from real joint Gaussian filters | Separate development selection before scientific use |
| Host risk and release score semantics | implemented | `monitor_feed.risk`, effect covariance only, exact log(1.02), hand normal-CDF checks and max-host score; never joint probability | Compatible probability-unit policy integration remains missing |
| Calibration and data quality honesty | implemented | Always UNCALIBRATED; preperiod, missing/insufficient, stale stream and disconnected states; no healthy inference verdict | Calibrate/audit a compatible frozen protocol separately |
| Host/group/shared/recovery demonstrations | implemented | Four saved algebraic trace artifacts, summary CSV, disjoint registered development/smoke slots; no benchmark claim | Physical-world adequacy/performance is unverified |
| Truth separation | implemented | `monitor_evaluator.recipe_for`, explicit Fault Lab button and developer-only route; strict public schema/AST isolation tests | None for this local separation contract |
| Backend playback, persistence and outcomes | implemented | Controller scheduler/commands, saved-session artifact+cursor, import/export; read-only GET and unchanged world deadline tests | Dedicated live producer reconnection protocol if needed |
| Laptop-width visual layout | partial | Responsive CSS at 850px; DOM rendering validated; browser preview unavailable | Manual browser check on target laptops/mobile widths |
| Automatic resource-world inference and calibrated alarms | missing | No automatic fitting/scoring loop or compatible policy; separate feed source/run labels | Freeze healthy-world nuisance model, stream causal scores, then calibrate/audit |

Latest full suite: **480 passed, 1 warning in 76.83s (0:01:16)**. Contract: [detector_dashboard.md](detector_dashboard.md). Checkpoint: [DETECTOR-DASHBOARD.md](wp/DETECTOR-DASHBOARD.md); raw `wp/detector_dashboard_validation.json`. Older counts/statuses remain historical.


## Immutable declared-release registry checkpoint

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Immutable ID/service/version/hash/creation records | implemented | `releases.ReleaseRegistry`, frozen records, append-only API, unique service/version and exact-retry handling; reset/replay tests | None for per-session registry scope |
| Validated schema and composition | implemented | `behavior_manifest`, schema version 1, numeric bounds, unique kinds, healthy-only rule, unknown-field rejection | None |
| Healthy/CPU/retention/error/response-wait dynamics | implemented | `operations.before_tick`, `ResourceModel._consume/_emit_response/update`; hand queue/memory/delay/error checks and six deterministic trace cases | Broader physical fidelity is unverified |
| Capacity separate from usage; bounded pending responses | implemented | CPU/response queues share admission slots and temporary memory; retained growth clipped; restart/unavailability conservation tests | Packet-level network/response scheduling remains outside this approximation |
| Dashboard form and manifest/source upload | implemented | Releases JSON editor, numeric composition form, optional inert attachment; real HTTP/DOM checks and browser registration success | Broader visual/device QA remains unverified |
| Source never executed | implemented | Base64 bytes stored/hashed only, executed=false, filesystem sentinel test and visible simulation labels | No source execution mode exists |
| Public deployment metadata, hidden manifest parameters | implemented | `release_metadata` ID/service/version/hash; typed telemetry unchanged; pending snapshot counts only, private evaluator mechanisms | Error counts are resource observations; typed minute error-rate features remain separate work |
| Release names excluded from detector features | implemented | Public-panel label-renaming equality and inference import-boundary tests; all inference source unchanged | None for current latency/workload feature contract |
| Two immutable versions and rejection fixtures | implemented | `example_payloads`, `release-001` 1.0.0 and `release-002` 1.1.0, saved request/record JSON and invalid-manifest tests | None |
| Replay/persistence/backward compatibility | implemented | 34 engine replays and 22 scenario hashes verify; original host/service fields + workload RNG equal for healthy/legacy CPU/memory cases | Old external artifacts still need their original source/runtime or explicit regeneration |
| SSM detection of pure error-only releases | unverified | Current SSM features remain latency/workload; no new detector or power benchmark | Separately specify, fit and calibrate any error-rate feature model |

Latest full suite: **507 passed in 83.70s (0:01:23)**. Contract: [release_registry.md](release_registry.md); checkpoint: [RELEASE-REGISTRY.md](wp/RELEASE-REGISTRY.md); raw `wp/release_registry_validation.json`. Earlier checkpoint counts are historical.

## Fixed-cohort service rollout checkpoint — 14 November 2026

Latest executed full suite: **519 passed in 88.72s (0:01:28)**. Original tests and inference source remain byte-preserved.

| Requirement | Status | Actual file/function and executed evidence | Smallest next patch |
| --- | --- | --- | --- |
| Seven service rollout states and validated commands | implemented | `rollouts.RolloutState`, `RolloutManager.command/before_tick`; `test_rollouts.py` state, invalid-command and deferred-action tests | None for manual v1 |
| Append-only transition history | implemented | Frozen `Transition`, hash-chained `_transition`; snapshot copies, replay verification and log-prefix preservation across reset tested | External signed audit persistence would be separate work |
| Frozen canary/control membership and traffic | implemented | `select_cohort`, `ResourceModel.fixed_routes/route`; same baseline/candidate weights, pause/resume and unavailable-slot checks | Progressive changes require new epoch/calibration; no edit command |
| Rack/class representation and unexposed controls | implemented | Deterministic crossed-partition search; canary in each rack/class, at least 3 controls in each; reserves other active cohorts | Larger topologies may need a scalable constrained selector; v1 bounded search rejects |
| Fair routing and request counts | implemented | Equal expected within-cohort multinomial allocation; unavailable slots drop without redistribution; service C/K offered counts and conservation tests | None for declared discrete-time approximation |
| Side-by-side baseline/candidate versions | implemented | `rollout.baseline_releases/candidate`; `web/app.js:renderRollout`; actual button handlers checked against HTTP backend | Visual layout at laptop width unverified in this patch |
| Exposure initialization and no pre-exposure alerts | implemented | Exposure epoch metadata and first clean full-window boundary; `dashboard.WorldController.command` current-run stream guards tested before exposure/after promotion | A connected/calibrated detector remains separate; no automatic alert claims |
| Rollback restores routing/version and memory semantics | implemented | `_place(rollback)`, `ResourceModel.restart`; all service versions/parameters restored, delayed/CPU queues dropped and counted, initial retained memory restored | Migration unsupported; hosts do not move in this protocol |
| Promotion closes fixed evaluation; later epochs | implemented | `_close`, promoted placement, removes fixed routing; same-candidate rejection/new-epoch test | Development selection and compatible recalibration for future policies are missing |
| Manual pause/promote/rollback buttons | implemented | Releases fixed-cohort card, backend command validation, local HTTP/DOM acceptance | Real browser viewport/accessibility review remains unverified |
| No truth-based transitions | implemented | Rollout source imports no fault/evaluator modules; manual/public placement checks only; no detector automation | Contaminated controls remain a challenge; no robust estimator claimed |
| Persistence, reset history and replay | implemented | Engine `rollout_state`, source hash, ordered command log; reset/replay/hash-tamper tests; controller existing checkpoint mechanism | Older source-bound artifacts require their matching source; no migration added |
| Calibrated deployment policy / progressive rollout | missing | Epoch explicitly `UNCALIBRATED`, `alerts_enabled=false`; unsupported membership/fraction edits rejected | Separate development selection, null validation and versioned compatible calibration |
| Specific viewport visual verification | unverified | HTTP/DOM and JS syntax checked; no screenshot or browser visual claim | Inspect Releases at laptop width in a browser |

## Process memory checkpoint — 15 November 2026

Latest full suite: **538 passed, 1 warning in 331.25s (0:05:31)**. See `docs/process_memory.md` and `docs/wp/PROCESS_MEMORY.md`.

| Requirement | Status | Actual implementation / evidence | Smallest next patch |
| --- | --- | --- | --- |
| Per-request and separate background retention | implemented | `releases.behavior_manifest`, `ResourceModel.configure_behavior/update`; hand-computed MB/request and MB/s tests | None for declared model |
| Temporary reclamation and retained lifetime | implemented | Queue/pending-response ownership, `_emit_response`, `restart`; idle, delayed response and behavior-only-switch tests | GC/eviction would require an explicit new mechanism |
| Memory-pressure latency | implemented | `resources.update` pressure core budget and FIFO processing; actual weighted response latency versus labeled proxy; pressure fixture | Hardware fidelity unverified; no fitted paging model |
| OOM and bounded restart behavior | implemented | Per-process states/counters, OOM drops/exit, startup allocation failure, queued manual restart; before/after tests and replay | Automatic restart policy intentionally absent |
| Rollback frees memory only by restart | implemented | Both `operations.before_tick` and `rollouts._place` record actual restart; recovery fixture and no-magic-free unit tests | None for manual protocol |
| Memory/headroom/growth/restart/latency dashboard | implemented | Host resource card, sampled mean chart and restart button; HTTP/DOM + restored checkpoint gates | Specific laptop viewport visual QA unverified |
| Separate development-defined advisory | implemented | `resource_health.ResourceHealthPolicy/summarize`, version/checksum, causal windows, insufficient/stale states; no truth/inference imports | Resource transport loss not modeled; direct-counter channel explicitly labeled |
| Warning is not SSM/code-leak proof | implemented | Explicit UI/docs label; null detector decision/action; cache-warmup/plateau challenge | Validated leak attribution and advisory calibration are missing, not claimed |
| Five deterministic exercises and visible traces | implemented | `memory_fixture.export_fixture`, development seed registry family 20, public CSV/JSON/PNG and private replay/evaluator artifacts | None for acceptance examples |
| Original immutable releases and research artifacts | implemented | Legacy bounded semantics preserved; versioned new samples; original tests, inference and additive pairs byte-preserved | Never silently migrate old immutable manifests |
| Statistical advisory calibration / hardware fidelity | unverified | Development engineering criteria and heuristic physical model only; no validation/test tuning or benchmark claim | Separate preregistered validation and new versioned policy if requested |

## Latched policy checkpoint — 15 November 2026

Latest full suite: **566 passed, 1 warning in 139.61s (0:02:19)**. See `docs/wp/FIRST_CROSSING.md` for computed results and scope.

| Requirement | Status | Actual implementation / evidence | Smallest next patch |
| --- | --- | --- | --- |
| Separate latched first crossing and eligibility | implemented | `first_crossing.LatchedFirstCrossing/eligibility`; strict ties, missing controls/quality, future/revised/duplicate frames and no-data tests | None for declared Gaussian score contract |
| Freeze only healthy development settings | implemented | `policy_artifacts.freeze_development`; existing healthy regression/control/AR fit; predeclared effect settings, provenance/source checks | A different model/selection rule needs new development freeze/calibration |
| Explicit five hashes and immutable receipts | implemented | Frozen model/preprocessing/simulator/protocol and calibrated policy hashes; controller/validation hashes; semantic browser round-trip regression | Trusted provenance/independence attestations are not cryptographic proof of dataset truth |
| Full-horizon B null maxima, k rule and infinity | implemented | `ordered_threshold`, `full_trace`, `calibrate`; B500/k476 unit and actual subset check; all no-eligible maxima retained, incomplete horizons rejected | None for mathematical contract |
| Independent validation without retuning and intervals | implemented | `validate_nulls`; disjoint IDs/seeds, CP/Beta intervals, abstention counts and preserved failed/insufficient qualification | Physical-world calibration/validation remains missing |
| Qualified automatic PAUSE / manual rollback | implemented | `policy_control.PolicyController`, backend commands; actual HTTP/DOM and replay checks using explicit contract inputs | Supply matched physical-world artifacts before live-world activation |
| Explicit opt-in simulated auto rollback | implemented | Immutable `auto_rollback=false` default, operational hash, separate later transition; unit checks no incident/resource-only auto rollback | None for simulation adapter |
| Positive-evidence healthy promotion | implemented | Guard requires completed horizon, eligible budget, declared score ceiling and no latch; no data never counts as healthy | Promotion utility/miss rates unverified, not claimed |
| Shared platform incident pause reason | implemented | Typed observed-metrics/evidence/two-group command, separate reason and no release rollback | Upstream incident classifier is external/not implemented here |
| Resource guardrails and combined null rates | implemented | Optional direct resource-health observer hook and distinct pause reason; separate per-rollout union/CI reporting and overlap tests | Matched physical combined-policy false-alert calibration is missing |
| Existing frontend/API persistence and replay | implemented | Policy upload/receipt/opt-in/status panel, validated commands, automatic reason log, raw saved-run loading and checkpoints | Specific laptop viewport visual QA unverified |
| Physical-world calibrated policy artifact | missing | Shipped actual example is conditional Gaussian; simulator/protocol mismatch is explicitly rejected | Generate matched healthy-development/public-world null bundles and independent validation using the frozen protocol |

## Matched physical-world policy checkpoint — 15 November 2026

This table supersedes the earlier physical-calibration gap only for `configs/world_policy_v1.yaml`. Earlier rows and test counts describe their original checkpoints. See [WORLD-POLICY.md](wp/WORLD-POLICY.md) for measured results and [world_policy.md](world_policy.md) for runnable commands.

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Healthy physical development fit | implemented | world_policy_fixture.export_fixture → fit_development; development_fit.json, frozen.json | None within the declared all-healthy distribution |
| Full-horizon physical null maxima and strict first crossing | implemented | world_policy_fixture._null; null_maxima.csv; existing policy_artifacts.calibrate | None for this fixed four-minute protocol |
| Independent physical null qualification | implemented | validation.json gate PASS; false_alerts.csv; separate registered seed roles | New version and fresh data for any changed distribution/settings; never retune this audit |
| Compatible policy and explicit hashes | implemented | world_simulator/world_protocol, frozen.json, policy.json; actual HTTP attachment | None for the supplied independent-effect configuration |
| Public live telemetry → posterior charts and policy | implemented | world_policy_live.public_outputs/PublicPolicyPump.poll_once; http_demo_checks.json; ten saved HTTP sessions | Run the external producer alongside the backend; no browser simulation loop |
| Automatic PAUSE, manual ROLLBACK and replay | implemented | world_policy_http_demo.export_demo; actual public observations and command_outcomes.json | None if the saved HTTP demo gates pass |
| Opt-in automatic rollback | implemented | Existing policy_control adapter and original tests; HTTP examples explicitly keep it off | Optional separately recorded opt-in; default remains false |
| Positive-evidence promotion | implemented | Existing PolicyController.guard and LatchedFirstCrossing; full eligible budget plus healthy score ceiling | No utility/power claim from absence of an alarm |
| Broader fault/missingness/advisory null distribution | partial | Current config has no random platform faults or telemetry loss; resource/platform producers disabled | New development freeze, full combined-policy null replay and independent validation for an enabled wider family |
| Physical hierarchical/pooling calibration | missing | This matched policy uses EffectParams(kind=indep); original grouped/nested demos remain separate | Freeze each hierarchy setting on development, calibrate and validate independently |
| Specific laptop browser visual check | unverified | Cloud browser could not reach this backend loopback origin (ERR_CONNECTION_REFUSED); real local HTTP path is checked | Inspect the saved dashboard sessions in a browser on the running backend host |
| Original inference, tests and research artifact preservation | implemented | world_policy_preservation.json; original tests byte-preserved; no original canary_ssm source change | None |
## Integrated dashboard checkpoint — 15 November 2026

Latest evidence: [INTEGRATED-DASHBOARD.md](wp/INTEGRATED-DASHBOARD.md). Setup: [integrated_dashboard.md](integrated_dashboard.md). Earlier checkpoint counts/limits remain historical.

| Requirement | Status | Actual file/function | Evidence | Smallest next patch / boundary |
| --- | --- | --- | --- | --- |
| Seven coordinated views | implemented | web/index.html; app.selectView; console.js | Actual HTTP/HTML-ID harness covers all seven views | None |
| Shared topology in World and Canary Rollout | implemented | shared-topology; selectView; render rack-grid/tree | Both views keep the same map/tree; stable backend host IDs | None |
| Mode, run/seed, clock, model/policy/calibration IDs | implemented | dashboard.packet; dashboard_evidence.console_evidence; renderDashboard | Current-world uncalibrated stream IDs and disconnected state tested; replay identity regression fixed | None |
| Active replica version, routing and actual counts | implemented | console_evidence.replicas; replicaTable | Hand-checked .35/4=.0875 and .65/16=.040625; actual last-tick counts; exposure/rollback versions checked | None |
| Manifest/source registration | implemented | Existing registry validation; Release Registry form/upload; send | Valid and malformed registration exercised through actual frontend/API; uploaded source stays inert | None |
| Choose and preview canaries | implemented | preview_rollout; existing RolloutManager.command/select_cohort; rollout-preview | One/two balanced canaries per rack; exact IDs shown, three controls per rack/class retained; preview is nonmutating | Arbitrary individual host editing is outside this bounded selector |
| Baseline, exposure, pause and manual rollback | implemented | Existing rollout commands; Canary Rollout view | Queued versus applied state, frozen traffic and restart cleanup preserved; API workflow passes | None |
| Memory and latency inspection | implemented | Moved Host Details; existing resource-health and monitoring renderers | Backend request/memory traces; advisory and analytical/sample-mean latency labels remain distinct | None |
| Separate fault scheduling and truth | implemented | Fault Scenarios; existing developer fault endpoint | Public console excludes injected mechanism/severity/type; fixture schedules a rack disturbance separately | None |
| Full command IDs, pending/success/error and duplicate suppression | implemented | app.send; WorldController.command; command_journal | Duplicate click and accepted-response-loss checks pass; same ID/different parameters rejected | None within declared command bounds |
| Receipt eviction/restart deduplication | implemented | Persistent compact command journal and receipt lookup | Actual cache eviction and restart regression prevents a second step; bounded at 10000 IDs | Export/checkpoint and use fresh state directory at journal limit |
| Disconnect/refresh recovery | implemented | session-storage pending request; recoverUnconfirmed; GET /api/commands | Undelivered retry keeps exact ID; prior run/epoch is never resubmitted; large-body limits declared | Large upload payload may need reselection after refresh; unknown outcomes require explicit acknowledgement |
| Refresh/server restart reconnects to same run | implemented | WorldController restore/load; command_journal persistence | Imported run now matches actual engine ID through refresh/reset/restart; frontend refresh reads existing backend | None |
| Backend Run History and checkpoints | implemented | RunArchive; history_save/history_load; GET /api/history | 128 bounded content-addressed snapshots; cached metadata; hash corruption/traversal rejected | Use --state-dir for disk persistence |
| Replay/export from saved backend data | implemented | Existing strict SimulationEngine.replay; /api/run; /api/history | Paused/recovered fixtures replay exactly; direct JSON export avoids browser RNG/summary calculation | Older artifacts require their exact compatible numerical runtime/source |
| Laptop/narrow responsive structure | implemented | web/styles.css; seven-view navigation and table scroll containers | CSS breakpoints at 1150/760; HTML IDs and view visibility checked | Viewport screenshot QA remains unverified |
| Native screenshot/viewport visual review | unverified | Headless Chrome attempt log | Chrome exited -6 in sandbox; no screenshot or visual-pass claim | Inspect actual app at laptop width in a browser capable of running here |
| Inference, simulator and calibration preservation | implemented | integrated_preservation.json | All original inference/engine/protocol code, 32 test files and existing research/calibration artifacts byte-preserved | No new calibration/benchmark claimed |
