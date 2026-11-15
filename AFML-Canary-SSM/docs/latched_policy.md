# Latched first-crossing policy v1

Historical conditional-generator checkpoint. A subsequent matched physical-world
checkpoint is documented in [world_policy.md](world_policy.md), with measured
qualification in [wp/WORLD-POLICY.md](wp/WORLD-POLICY.md). Its narrow configuration
supersedes the missing physical example below; the statistical artifact itself
remains incompatible with the physical adapter.

This is a separate policy/artifact/controller layer around the existing public
adjustment and Gaussian engines. Research `decision.py`, inference, comparators,
harm boundary and previously frozen policies are unchanged. The score is **log
maximum marginal host risk**, with effect > log(1.02). It is a release score,
not a joint release probability and not proof of a release/code root cause.

## Executed entry points

```sh
python -m canary_ssm.policy_fixture --out examples/first_crossing --B 2000 --n-validation 2000
python -m canary_ssm.policy_artifacts calibrate --input examples/first_crossing/frozen.json --traces examples/first_crossing/calibration_nulls.json --out /tmp/rebuilt-policy.json
python -m canary_ssm.policy_artifacts validate --input /tmp/rebuilt-policy.json --traces examples/first_crossing/validation_nulls.json --out /tmp/rebuilt-validation.json
python -m canary_ssm.policy_public --policy examples/first_crossing/policy.json --slice examples/first_crossing/public_example_slice.json --service-id fixture-service --exposure-time 3660 --out /tmp/public-policy-scores.json
python scripts/plot_first_crossing.py --directory examples/first_crossing
python -m pytest tests/test_first_crossing_policy.py -q
```

**The supplied calibration is a conditional statistical Gaussian example, not
resource-world calibration.** Its generator ID, protocol and simulator hash are
different. Uploading it to a physical world is rejected. Physical-world automatic
actions remain disabled until a matching healthy-development fit, full null
calibration and independent validation receipt are supplied. No physical-world
false-alert rate, power or calibrated posterior probability is claimed.

`policy_public.score_slice` reuses `FrozenAdjustment.prepare/transform`, the
common Gaussian filter, or the constrained grouped Gaussian adapter. Canary
loadings adapt only on pre-exposure observations. Fresh-control masks, white
reference uncertainty and shared covariance remain in the existing pipeline.
No common reference is subtracted twice. Baseline comparators are not assigned
Bayesian posteriors; this v1 operational contract accepts Gaussian log-risk
scores. Each independent/pooled/grouped setting needs its own calibration.

## Development freeze and compatibility

`policy_artifacts.freeze_development` accepts a fitted `FrozenAdjustment` payload,
predeclared effect settings, simulator descriptor, frozen protocol and healthy
**development** provenance. It validates fit success, complete represented-group
control membership, cohort/order metadata, development fingerprints and roles.
All noise fits/bounds remain recorded. Model settings cannot be selected on
calibration, null-validation or final-test data. Effect priors/dynamics in the
example are predeclared; healthy data fits regression, rank-one controls, scales
and no-effect AR noise. It does not identify effect dynamics from healthy nulls.

A world workflow uses the existing healthy public-development fitter, with the
actual selected canary IDs, before calling:

```python
frozen = freeze_development(
    model.to_dict(), vars(effect_params), world_simulator(engine),
    world_protocol(engine, rollout, model.policy.group_by),
    development_manifest, settings=rule(horizon_windows),
)
```

| Binding | Contents |
| --- | --- |
| `model_hash` | Frozen effect settings; Gaussian/grouped/Kalman/basis source and harm-boundary schema |
| `preprocessing_hash` | Fitted healthy-development artifact, adjustment/AR/control code and public policy producer code |
| `simulator_hash` | Exact generator/distribution/config/support-code descriptor; the world variant also binds public committed baseline content hashes |
| `protocol_hash` | Cohorts, represented monitoring groups/controls, traffic fraction, baseline, horizon, minute alignment, eligibility, and protocol source |
| `policy_hash` | Frozen bundle, rule, full calibration-maxima ledger, threshold and uncertainty metadata |

A separate `controller_hash` binds the calibrated policy, adapter code and explicit
simulated auto-rollback opt-in. Validation has its own immutable receipt/hash;
validating never changes the policy hash or threshold. NumPy/SciPy versions and
source hashes are bound. Old artifacts are refused after incompatible changes.
Policy hashes normalize integral JSON numbers (`1.0` and `1`) so browser upload
preserves meaning. Existing research hashes are untouched. Saved world files are
uploaded as raw text to preserve large RNG integers and float spelling.

The world simulator descriptor excludes per-run seeds and realized intervention
schedules/labels. Those are not oracle features or regime selectors. Distribution
configuration and committed baseline public identities are compatibility data,
not score features. Each rollout still has a distinct registered seed/identity.
Fixed injected schedules and scheduled lifecycle interventions require separately
supported calibration and are refused by this adapter. Manual injections outside
the calibrated sampling family are stress tests, not evidence of nominal coverage.

## Full-horizon order statistic and missingness

Each calibration input is a declared-null **threshold-calibration** rollout with
unique seed/ID, four frozen hashes, freeze hash, exposure time and every monitoring
window, including missing/ineligible windows. No truncated follow-up or stopping
at first alarm is allowed. Development, calibration and validation IDs/seeds must
be disjoint. These are provenance contracts with a trusted offline producer,
not cryptographic proof that supplied data is independent or truly null.

For B independent null rollouts, compute each full-horizon maximum **eligible**
score, then use k = ceil((B+1)(1-alpha)). At alpha .05, B=500 gives k=476. The
threshold is the kth ordered maximum, or +infinity if k>B. Alert only for a score
**strictly greater** than the threshold; ties do not cross. No-eligible rollouts
remain in B with maximum -infinity. They are counted/reported, never discarded.
If the selected threshold is nonfinite the artifact is operationally insufficient:
it cannot authorize automatic actions or healthy promotion. JSON uses explicit
`+inf`/`-inf` strings rather than nonstandard numeric infinities.

Eligibility preserves at least 80% fresh observed canaries and at least three
fresh **unexposed** controls in every represented monitoring group. Nonfresh,
unavailable, missing-score or quality-flagged observations hold. Known exposed
hosts cannot count as controls. Unrecognized control IDs/groups are rejected.
Control contamination remains an explicit upstream challenge; no robust estimator
or causal attribution is silently assumed.

`LatchedFirstCrossing` retains the first crossing permanently within an epoch,
even if later observations are missing or recover. Exact duplicate observations
are idempotent; changed earlier records, reversed deadlines/indices and late
revisions are rejected. Missing windows must be explicit placeholders. The
upstream causal window store freezes inputs received by each decision deadline;
carried values cannot be declared fresh. Runtime future/pre-exposure and foreign
run/epoch/hash records are rejected. Controller receipt/action ticks are logged
separately from the producer's decision time; late delivery does not backdate
an applied transition.

## Independent null validation and uncertainty

`validate_nulls` replays an already frozen policy on independent nulls without
retuning. It retains per-rollout outcomes, no-eligible counts, conditional-on-any-
eligible diagnostics and exact binomial 95% intervals. The primary marginal bound
includes no-data rollouts; it is not a conditional-on-eligibility guarantee.
The calibration artifact retains exact Beta order-statistic tail-probability
quantiles under continuous iid maxima. Ties/no-data mass make that Beta diagnostic
assumption-dependent; strict ranks remain conservative under exchangeability.

Automatic attachment additionally requires the versioned, conservative single-
policy qualification: B>=2000, independent n>=2000, Beta-Binomial two-sided p>=.01
and observed release-alarm rate<=.075. This is a G2-style operational check, not
an alteration of the existing research multi-cell gate. B=500 still demonstrates
the requested rank rule; it is not mislabeled as a fully validated deployment
policy. Failed or insufficient qualification blocks actions, with its intervals
retained. No validation tuning or automatic fallback threshold exists.

Release alarms, observed platform pauses, observed resource pauses and their
**union** have separate counts/rates/intervals. Combined action false alerts are
not promised controlled at release alpha. The example statistical generator has
no platform/resource advisory producer: zero extra events do not establish a
physical guardrail false-alert rate, and their interval upper bounds are nonzero.

## Controller commands and exact v1 protocol

The existing authenticated `/api/commands` and
`SimulationEngine.operations_command` expose:

| Command | Validated inputs / behavior |
| --- | --- |
| `policy_attach` | `rollout_id`, policy, independent validation receipt, optional boolean `auto_rollback=false`; immutable epoch commitment |
| `policy_observe` | `rollout_id`, run ID, integer monitoring epoch, all five hashes and a typed causal observation |
| `policy_advisory` | Observed-metrics source, evidence hash/time, platform/resource kind; shared platform evidence covers two represented groups |
| `rollout_promote` | For an attached policy, completed horizon/eligible budget, declared healthy score ceiling and no latched blocked reason |
| `rollout_rollback` | Manual rollback remains available; actual resource restarts retain existing semantics |

Commit in CREATED at a **fresh world origin**, before baseline. Baseline must
start at tick 1, last the exact declared duration (at least 60 minutes), and expose
at that clean minute boundary. A longer/shifted preperiod cannot silently reuse
this calibration. Pause the world clock and step to the boundary, or use a
headless driver with exact tick counts. This v1 does not provide a broad
calendar-phase or variable-preperiod calibration. Existing unmonitored manual
rollouts remain operator overrides and make no healthy-evidence claim.

A calibrated release crossing queues PAUSE for the next tick. Its reason is
`release_regression_alarm`. Pause retains frozen cohort/traffic and simulation
observations; it does not stop time. The default requires **manual ROLLBACK**.
An explicit pre-baseline opt-in enables rollback only after the pause has applied,
with reason `opt_in_release_alarm_auto_rollback` on a distinct subsequent tick.
A queued resume is cancelled if an alarm latches before application; a latch
cannot be cleared by resume, later missing data, a new score, or changing settings.

Observed incidents and resource guardrails use `shared_platform_incident` and
`resource_health_guardrail`. They can pause after actual exposure, without
waiting for a complete latency window, and never trigger release auto-rollback.
Platform incidents are typed inputs from an observed monitor/operator, not a
new root-cause detector or Fault Lab truth. When enabled, the resource guardrail
also consumes the existing direct resource-health advisories after observations
are emitted, before snapshot publication, and queues its pause for the next tick. Resource pause is separately disabled unless
frozen rule `resource_guardrails=observed_pause` enables it. Changing that mode
requires a new policy/combined null report. Direct resource-health observations
are separate from delayed/lossy latency telemetry.

Promotion requires every horizon slot to be accounted for, the declared eligible
budget (default all H windows), maximum eligible log risk below the declared
healthy ceiling (default log(.05)), and no alarm/incident/guardrail latch. Missing
or absent evidence holds. `HEALTHY_CRITERIA_MET` is an operational criterion, not
Pr(all hosts healthy), a validated miss-rate bound or proof of good source code.
Promotion/rollback/reset close the policy epoch; history, reasons, receipts and
hashes remain replayable. Saved replay is read only and labeled separately.

## Evidence and limits

See `docs/wp/FIRST_CROSSING.md`, raw test/HTTP/checkpoint/CLI/replay/preservation
records, and `examples/first_crossing`. Unit/HTTP controller fixtures use hand-
authored null statistics to test the adapter contract. They are **not** saved as
physical-world calibration evidence or a deployable world policy. The shipped
actual calibration/validation uses the existing public Gaussian scorer and a
separately identified statistical generator; the backend rejects domain mismatch.

Model adequacy, independence/exchangeability, release-null definition and healthy-
promotion utility remain assumptions to validate for each deployment environment.
The existing shared-step/control-contamination failure remains open. Browser
viewport visual QA is unverified; HTTP/DOM handlers and saved-run restoration
are exercised. This change does not invent resource-world benchmarks or silently
connect an incompatible detector/policy.
