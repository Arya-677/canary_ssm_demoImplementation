# Physical-world policy checkpoint — 15 November 2026

This closes the earlier checkpoint's missing matched physical-world calibration
within one explicitly scoped version. It does not close the original shared-step
failure or certify other world configurations, hierarchies or advisory producers.
No original inference implementation or test was rewritten.

## Executed evidence

Full repository suite: **584 passed, 1 warning in 114.19s (0:01:54)**.

Calibration B=2000, alpha=0.05, k=1901, frozen threshold=-0.9663903893998882. Independent validation gate: **PASS**. Gate details, Beta diagnostics, ineligible/no-data counts and all outcome rows are retained in `examples/world_policy/validation.json`.

| Channel | Events | Null rollouts | Rate | Pointwise exact 95% interval |
| --- | --- | --- | --- | --- |
| release_alarm | 98 | 2000 | 0.049 | [0.03995675692495896, 0.059392645124689336] |
| platform_pause | 0 | 2000 | 0.0 | [0.0, 0.0018427397934059364] |
| resource_pause | 0 | 2000 | 0.0 | [0.0, 0.0018427397934059364] |
| combined_action | 98 | 2000 | 0.049 | [0.03995675692495896, 0.059392645124689336] |

**Abstention matters:** 1143 of 2000 null rollouts had no eligible monitoring windows. Among 857 rollouts with any eligible window, the conditional alert fraction was 0.11435239206534423; the nominal alpha guarantee is not conditional on eligibility. In particular, current workload-support overlap checks often HOLD in this short four-minute protocol. No-data rollouts are never promoted as healthy.

The combined row is the measured union. Platform/resource producers are disabled in this null family; their zero observed counts do not imply zero population false alerts. Intervals are pointwise, not simultaneous. Calibration rank coverage assumes independent/exchangeable complete null rollouts from this exact frozen pipeline.

Policy hash: `221f2b817cbc42a58090edf58adfd25fde96acfd7767a17cb53ca609c645c5ed`.

Validation hash: `23c8e0d39d39d86df6a2240be4003c5556685bd8768a820f812ca293e84a352c`.

Both HTTP sessions use actual physical requests, saved public telemetry and the frozen Gaussian posterior. Polls never advance the world. Repeated polls emit no duplicate decisions. The candidate example is illustrative and is not a power estimate.

| HTTP example | Automatic pause | Final state | Detector frames | Exact engine replay |
| --- | --- | --- | --- | --- |
| healthy | False | CANARY | 4 | True |
| combined_hold | False | CANARY | 4 | True |
| slow_0 | False | CANARY | 4 | True |
| slow_1 | False | CANARY | 4 | True |
| slow_2 | False | CANARY | 4 | True |
| slow_3 | False | CANARY | 4 | True |
| slow_4 | True | ROLLED_BACK | 4 | True |
| slow_5 | True | ROLLED_BACK | 3 | True |
| slow_6 | False | CANARY | 4 | True |
| slow_7 | True | ROLLED_BACK | 3 | True |

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

The HTTP smoke bundle retains all healthy/combined/strong-delay outcomes. `http_alarm` aliases the first eligible crossing in the eight predeclared strong-delay smoke seeds; no model, threshold or validation seed was selected from these outcomes. This selected replay is not a power estimate. The original combined release can show high posterior risk while eligibility flags correctly hold action. A client clock-command argument mismatch was caught by actual HTTP execution and fixed in the new client; its failing regression is retained.

Commands and scope: [world_policy.md](../world_policy.md). Actual logs: `world_policy_full_tests_initial.txt`, `world_policy_full_tests_verified.txt`, `world_policy_fixture_run.txt`, `world_policy_http_run.txt`, `world_policy_cli_validation.json`. The first full run encountered a missing optional `tabulate` dependency in the restored environment; after installing the declared report dependency, the complete suite passed without editing a test. Original checkpoint reports remain historical.
