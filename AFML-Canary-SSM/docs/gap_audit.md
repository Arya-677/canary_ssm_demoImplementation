Latest extension: offline evaluator v2; see `evaluator_comparison.md` and
`wp/EVALUATOR.md` for current targets, executed audit, tests and limitations.
Earlier sections below retain their historical scope.

# Source-grounded virtual-world gap audit

Latest checkpoint: integrated dashboard; see the final requirement table. Earlier sections retain historical scope.

Updated 14 November 2026 against the extracted repository after the console
and typed-fault extension. This table maps the requirements visible in the
implementation requests. A line-by-line comparison to an unseen external
corrected plan/virtual-world guide is **unverified**; it is not claimed here.
Earlier checkpoint reports remain historical. No saved research benchmark was
rerun or newly claimed by this audit.

## Actual SSM family and simulator boundaries

`hierarchy.build_model` implements three linear Gaussian effect families:
independent (`L=I`), complete pooling (`L=1`) and constrained hierarchical
Gaussian (`L=[C B]`). For hierarchy, `class_structure` builds one indicator
column per `class_id` and a block orthonormal null-space basis `B` whose host
deviations sum to zero within each class. This is class → host hierarchy,
not data center → rack → host hierarchy, and not a neural SSM.

The implemented rollout state is `s_t=[z_t,e_t]` with

```text
s_t = block_diag(diag(rho), diag(phi)) s_(t-1) + eta_t
Cov(eta_t) = block_diag(diag(sd^2), diag(q_e^2))
r_t = [L I] s_t + nu_t
Cov(nu_t) = diag(v^2) + lambda lambda' U_t
a_t = L z_t
score_t = max_i log Pr(a_it > kappa | observations through t)
```

`EffectDetector.run` carries the noise-only pre-period posterior into rollout,
resets the effect prior, masks observations by observed/eligible flags, and
uses `kalman.KalmanFilter` with Joseph covariance update. Missing observations
are predict-only. This score is a maximum marginal host risk, not a joint
release-harm probability. `experiments.Models.run` selects these families;
`factor`/`preprocess` provide the existing adjustment path. `artifacts/model_v2/`
contains fitted JSON model/nuisance/policy metadata, not neural weights.
The small `data_audit/model_pooled_dev` is the earlier legacy test fixture.
These inference modules and model artifacts were not changed in this extension.

Two simulators now coexist:

| Call path | Actual output/behavior | Boundary |
| --- | --- | --- |
| Research CLI → `experiments.generate_role` → `simulate.simulate` | Statistical arrays with `y_it=mu_i+beta_i*x_t+gamma*x_t^2+lambda_i*f_t+d_it*a_it+e_it+nu_it`, `latency_ms=exp(y)`; AR shared/host noise and explicit harm profile | No physical CPU/memory/queue/rack dynamics |
| World CLI/API → `engine._tick_once` → `DemoOperations.before_tick` → `ResourceModel.route/update` → observations/snapshot | Simulated arrivals, bounded queues, CPU/core-seconds, memory accounting, coupled network capacity, serving availability, version placements, analytical latency proxy | Physical resource approximation; no real code execution and no detector connection |

## Requirement and proposed module mapping

| Requirement / module boundary | Status | Current files/functions and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Validated center/rack/host/replica records | implemented | `topology` frozen records and `Topology.__post_init__`; capacity/identity/parentage/placement tests | None |
| Existing config loader, interactive fixture | implemented | `configuration.read_yaml_mapping`, `load_topology`, `EngineConfig.from_dict`; `world_interactive.yaml`, `world_console.yaml` | None |
| Immutable capacity versus usage/lifecycle | implemented | `HostCapacity`, `HostUsage`, `HostLifecycle`; resource updates replace records | None |
| Backend clock, tick order and tied events | implemented | `engine.SimulationEngine._tick_once`, command/event insertion order; engine tests | None |
| Independent workload/fault/noise/loss RNG streams | implemented | `RNG_STREAMS`; seed/reset tests; optional schedule uses separately seeded PCG64 | Consume noise/loss streams only when those mechanisms are requested |
| Initial-world/RNG reset, ordered replay log | implemented | `_initialize`, `artifact/replay`; strict source hash guards; clock/resource/fault fixtures replay | Version adapters before changing semantics |
| 100-tick headless clock | implemented | `world-run`, saved `examples/world_clock_100_ticks.json` | None |
| Workload, routing, queues and processing | implemented | `ResourceModel.route`, `fair_work`, `_consume`, `update`; conservation/unit tests | None for bounded discrete-time model |
| Baseline/request/retained/platform memory | implemented | `reserved_memory`, `temporary_memory`, admission, retention clamping; distinct telemetry fields | None for bounded model |
| Completed-request latency and empirical p95 | partial | `ResourceModel._consume` now records quantized FIFO completion cohorts and exact cohort sufficient statistics; public mean is separate from the old proxy | No p95 is calculated; retain samples/histograms if percentile output is later requested |
| Healthy/load/recovery trace fixtures | implemented | `resource_report.run_fixtures`; saved CSV/PNG/checks and verified runs | None |
| Typed fault contract | implemented | `faults.FaultEvent`, enums, `_validate_fault`; ID/time/severity/seed/recovery validation tests | None |
| CPU/memory/crash/network/demand effects | implemented | `DemoOperations.before_tick`, resource budgets/routing; each tiny fixture passes | None for requested mechanisms |
| Rack descendant effects | implemented | `FaultEvent.resolve`, per-host factors; network test checks all five rack descendants and unaffected racks | None |
| Overlap composition and recovery | implemented | Multiplicative floors, summed bounded memory, union crash, capped surge; overlap tests | None; exact assumptions in `faults.md` |
| Separate platform and release behavior | implemented | Platform events do not mutate versions/profiles; registry assigns per-replica work/retention separately | None |
| Hidden truth versus observed telemetry | implemented | Separate `developer_truth`, Fault Lab endpoint and replay artifact; public packet/CSV tests | Keep future detector input free of truth |
| Manual fault API and optional controls | implemented | `operations_command`, validated `WorldController.command`, Fault Lab all five kinds | None |
| Per-fault deterministic before/during/after | implemented | `fault_fixtures.run_fixture/export_fixtures`; 8-tick outputs for each kind | None |
| Backend state/API boundary | implemented | `dashboard.WorldController`, `make_server`, one lock/scheduler; GET reads do not tick | None for local single-user demo |
| World/Releases/Fault Lab/Monitoring UI | implemented | Packaged `web/index.html`, `app.js`, `style.css`; real browser preview/deploy/fault/rollback check | Broader browser/accessibility QA unverified |
| Version/resource tiles, clock/freshness | implemented | Backend snapshots/history rendered by `app.js`; stale/disconnect/reconnect DOM/API checks | None |
| Sample release or uploaded artifact | implemented | `register_release`, `catalog`; hash/metadata, declared profile, explicitly unexecuted bytes | None for simulated profiles |
| Execute uploaded applications | missing | Contents never run; profiles drive bounded synthetic behavior | Separate execution sandbox/process model |
| Valid canary preview/deploy/rollback | implemented | `DemoOperations.preview/command/before_tick`; sorted per-rack controls, stale plan guard, next-tick version changes | None for manual simulated workflow |
| Save outcomes and recover sessions | implemented | `export_run`, `_checkpoint`, retained receipts/outcomes; restart/idempotence tests | None within documented bounds |
| Saved-run replay | implemented | Backend verified reexecution, read-only final state/history; saved console run import check | Animated replay/scrubbing is missing; add backend cursor/snapshot sequence if needed |
| Recorded UI fixture without engine | implemented | `?recorded=1`, `recorded_snapshot.json`; zero engine API calls in harness | None |
| World telemetry → statistical observation adapter | partial | Public per-replica minute slices, dynamic exposure and masks exist; dashboard still never calls `EffectDetector` | Review legacy Rollout mapping, pre-period fitting and calibration for this new latency estimand |
| Physical rack hierarchy in Gaussian SSM | missing | Existing grouping remains `class_id`; rack topology is not used by `build_model` | Separate reviewed state/basis design with identifiability tests |
| Honest disconnected detector | implemented | Literal `DETECTOR NOT CONNECTED`; chart data comes from backend history | Connect only after adapter and calibration exist |
| Automatic detector deployment decisions | missing | Only explicit manual deploy/rollback implemented | Separate policy adapter after detector integration |
| Real-world fidelity / fault detection performance | unverified | Functional simulation checks only; no new detection benchmark | Define and run a separate evaluation protocol |

Current executed evidence: **292 passed in 75.30s**, eight DOM/API checks,
five deterministic fault gates and twelve console demo gates passed. See
`wp/CONSOLE-FAULTS.md` and `wp/console_fault_validation.json` for commands.
UI labels describe modes; actual resource effects and releases are established
by code, saved telemetry, version placements and tests, not labels or colors.


## Scheduler extension

| Requirement | Status | Current files/functions and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Rate scheduler and scope scaling | implemented | `fault_scheduler.FaultRate`, `_sample`; per-target hazard/unit/stream tests | None for bounded grid sampling |
| Cooldowns, ranges, caps and deterministic admission | implemented | `BackgroundFaultConfig`, `_fixed/_sample`; hand-computed timing, rejection counters and fixture gates | Continuous-time event sampling is not requested |
| No-release background vs deployment profiles | implemented | `DemoOperations.background` independent from registry/profiles; deployment-independence and healthy-RNG tests | None |
| Persisted pre-generated schedule | implemented | `SimulationEngine.artifact/replay`; complete background manifest/hash/source guards, toggle command log | Old external runs require deliberate migration or regeneration |
| Enable/disable and scenario preview | implemented | `background_set_enabled`, developer Fault Lab API/UI, `world-fault-preview`; real API DOM harness passes | New panel visual browser QA remains unverified |
| All-healthy/fixed/rate fixtures | implemented | `world_scheduler_*.yaml`, `scheduler_fixtures.export_fixtures`; checked CSVs, truth, manifest and replay bundles | None |
| Scheduler-to-inference isolation | implemented | No inference imports/changes; AST boundary test; public state excludes scheduler fields | Keep future adapter telemetry-only |

Current suite: **319 passed, 1 warning in 59.99s**. Details: `wp/FAULT-SCHEDULER.md` and `wp/fault_scheduler_validation.json`.


## Public telemetry extension

| Requirement | Status | Actual file/function and evidence | Smallest next patch |
| --- | --- | --- | --- |
| Public run/host/rack/class and service/release metadata | implemented | `telemetry.PublicRecord`, engine source adapter; strict field/parentage validation and true-field rejection tests | None |
| Completion latency and request-weighted sufficient statistics | implemented | `ResourceModel._consume` captures FIFO cohorts; pipeline emits arithmetic/log sums and squared sums; hand-computed checks | Sub-tick timings or empirical percentiles remain separate work |
| Minute aggregation and fresh masks | implemented | `CausalWindowStore._aggregate`; explicit missing roster rows, mixed-exposure rejection, no carried values counted fresh | None for declared replica-level windows |
| Delay, duplication and missing windows | implemented | `TelemetryConfig`, `TelemetryPipeline.emit/deliver_through`; separate telemetry-loss RNG and deterministic fixture | None for bounded transport simulation |
| Causal slices and immutable inputs/scores | implemented | `time_slice`, `score_once`, `causal_time_slice`; late backdating, exact deadlines and future perturbation tests | Actual SSM callback integration remains missing |
| Separate evaluator-only labels | implemented | `telemetry_evaluator`; separate export subdirectory and private replay member; AST isolation tests | No additive counterfactual latent effect is defined, so it is null |
| Public API, CLI, monitoring and replay | implemented | `/api/telemetry`, `--telemetry-out`, `--run-id`, separate minute table; HTTP/DOM checks and replay tests | Visual rendering of the new table remains unverified |

Current full verification: **360 passed in 83.92s (0:01:23)**. See `wp/PUBLIC-TELEMETRY.md`. No new statistical benchmark was run.


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

Current full suite: **385 passed in 80.43s (0:01:20)**. See `scenario_bundles.md`, `wp/SCENARIO-BUNDLES.md` and raw `wp/scenario_bundle_validation.json`.


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
