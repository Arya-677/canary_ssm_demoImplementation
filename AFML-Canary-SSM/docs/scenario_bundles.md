# Small scenarios, role bundles and pairing contracts

This extension adds a **fixture-sized data protocol**, not a calibrated detector
benchmark. `scenario_registry.py` registers indivisible pairs and data-use roles;
`scenario_bundles.py` materializes runs; `world_evaluator.py` is a separate
operator-label evaluator skeleton. Inference never imports those generators or
evaluator labels. Existing `simulate.py`, research metrics, inference and fitted
models are unchanged.

## Reproduce the small bundles

```bash
python -m canary_ssm world-scenarios --out examples/scenario_bundles
python -m canary_ssm.world_evaluator --out examples/world_evaluator
python -m canary_ssm world-scenarios --plan-only --out scenario_plan
```

The default materializes only the **smoke** role: seven world pairs and four
additive-statistical pairs. All five roles are registered in `registry.json`;
other roles contain plans, not generated observations, unless explicitly selected
with `--role`. No threshold selection, null audit or final-test detection
performance is run. `--pairs-per-family` accepts 1–3 for this tiny fixture protocol.
This deliberately small scale cannot satisfy research calibration gate sample
sizes; it must not be used to claim a valid false-alert rate.

Configs use the existing YAML/topology/resource/telemetry loader:
`world_scenario_base.yaml`, `world_scenario_topology.yaml` and
`world_scenario_catalog.yaml`. The world has two racks, five hosts per rack,
two cores and 1,024 MB per host, one service replica per host and five-second
ticks. The horizon is 48 ticks (240 simulated seconds). The source remains a
bounded laptop simulation, including tick-quantized request latency.

| World template | Intervention member | Timing in simulated seconds | Reference member |
| --- | --- | --- | --- |
| healthy | No intervention | Entire horizon | Identical healthy dynamics |
| host_fault | One host's service replicas crash | [60,90) | No target intervention |
| rack_fault | Rack-a network capacity falls to 10% through all descendants | [60,90) | No target intervention |
| shared_demand_surge | Shared request rate multiplied by 6.25 | [60,90) | No target intervention |
| transient_degradation | Slow candidate on one host per rack, then manual rollback | [60,70) | Healthy release throughout |
| persistent_degradation | Slow candidate remains active | [60,horizon], right-censored | Healthy release throughout |
| recovery | Slow candidate followed by rollback and continued observation | [60,150), recovery to horizon | Healthy release throughout |

Platform cases have no candidate deployment. Release cases use the existing
registry, valid canary preview and next-tick deployment/rollback handlers.
Rollback restarts the cohort and explicitly counts discarded queues; recovery
is not represented as cost-free removal of queued work. Persistent labels do
not pretend an unobserved recovery occurred. Short or mixed-version minutes can
be masked by the existing public telemetry eligibility rules; the fixture does
not fabricate alarms to compensate.

## Pairing is different for the two generators

| Generator ID | Pair contract | Required check |
| --- | --- | --- |
| `statistical-additive-latency-v1` | Existing additive statistical generator, unchanged | On observed cells, `y_harm-y_null = a+spill` to floating precision; workload/factor/noise/missingness/arrival masks and counts are shared |
| `resource-world-scenarios-v1` | Same initial world and shared exogenous random primitives; intervention changes physical processing | Exogenous uniforms and their stream states align; endogenous queues, routing, completions, drops and measured latency may diverge |

The additive wrapper calls the existing `simulate.simulate` directly. It records
its source hash and preserves the original arrays and masks; it never replaces
its pairing test with an approximation. The numerical gate uses absolute
residual <= 1e-12 with no relative tolerance. This expresses the exact structural
additive identity with ordinary floating-point roundoff, not a claim of bitwise
subtraction equality. Default additive fixture profiles are baseline, transient,
persistent and recovery; these are statistical latency arrays, not physical
host/rack models. The stress test also covers control spill, heavy tails, missing
records and late masks without modifying the old generator.

For the world, `resources.paired_exogenous: true` opts into separate streams:

- Existing workload stream index 0 draws a shared traffic uniform and one
  arrival uniform per sorted service per tick, independently of readiness,
  queues and routing. Arrival counts use `Poisson(rate*dt).ppf(uniform)`; uniform
  zero maps to zero as the discrete lower endpoint. A demand intervention changes
  the rate, so counts may differ despite identical uniforms.
- A separate routing stream uses `SeedSequence([seed,4])`. Availability changes
  its multinomial calls and the number of eligible replicas; routing RNG states
  and outcomes are intentionally allowed to diverge. Such changes cannot shift
  later workload draws.
- Fault, host-noise and telemetry-loss streams keep their existing indices.
  Current fault/noise streams are reserved where not consumed. The telemetry
  source emits one heartbeat per replica/tick, so its delay/loss/duplicate draws
  stay aligned even when completion counts and latency masks differ.

The private `world_exogenous` trace records the common traffic/arrival uniforms.
It is not public telemetry. Ordinary resource configs keep the original direct
Poisson/routing behavior unless they opt into paired mode. No additive identity
is required, computed or claimed for world latency. In particular, equal random
seeds do not imply equal observed resource arrays or outcomes after an
intervention. Tests explicitly check that host crashes do not shift future
arrival counts, and demand changes return to the reference arrival stream after
recovery.

Both members share a seed and stay in one role. They have distinct opaque public
run IDs. Public IDs do not spell out the role, scenario, or null/harm member.
The private manifests link those identities to pair metadata. The `harm` member
name means the designated intervention for a world fixture; it is not proof of
causal harm, an additive latent effect or a qualifying research event.

## Disjoint roles and seed registration

The seed registry is append-only version 2.1. All existing seed bases and old
`seed_for(...)` outputs are preserved. Five new million-seed world blocks and five separate additive-fixture blocks
follow the existing registry. This avoids reusing archived research-run seeds
for new additive holdout plans. Family slots use the existing 20,000-seed stride.

| Role | Fresh additive-fixture purpose/base | World purpose/base | Permitted consumer use |
| --- | --- | --- | --- |
| smoke | additive_smoke / 34,000,000 | world_smoke / 29,000,000 | debug |
| development | additive_dev / 35,000,000 | world_dev / 30,000,000 | fit, tune |
| threshold-calibration | additive_calibration / 36,000,000 | world_calibration / 31,000,000 | threshold; null members only |
| null-validation | additive_null_validation / 37,000,000 | world_null_validation / 32,000,000 | audit; null members only |
| final-test | additive_test / 38,000,000 | world_test / 33,000,000 | evaluate after freezing choices |

`PairSpec.register` derives seed, pair ID and two scenario IDs from generator,
role, family and index. Validation rejects changed seeds, moved roles, split
members and duplicate pair/seed registrations. `select_members` enforces the
role/use table and refuses harmed members for threshold/null-audit consumption.
Both members remain registered in the same role even when a null-only consumer
selects only its reference observations.

Disjointness applies to **realized scenario instances, seeds, pair IDs and run
IDs**, not to template families. The same templates deliberately recur with
fresh role-specific seeds so calibration and validation can target the same
scenario distribution. This is not an unseen-template generalization claim.
Materialized holdout data must not be used to tune a detector. The default
archive generates only smoke data and reserves the remaining bundles.

## Artifacts and replay

Each world member directory has:

- `config.json`, `commands.json`, seed/role/pair/generator `manifest.json`, and a
  private verified engine `run.json`;
- `public/` with telemetry records, frozen minute windows, causal decisions,
  metadata and resource CSV traces;
- `evaluator/` with injection truth and the explicit operator intervention label;
- private `exogenous.json` for common-random-number verification.

Public data does not carry the role, pair member, fault type, true affected
status, injected latent effect or exogenous uniforms. Private manifests, directory
labels, full engine bundles and evaluator files are not inference inputs.
`verify_member` validates pair/role identity, public run identity and data/config/
command/replay hashes. An exported pair also has `pair.json` and computed
`checks.json`. The suite writes `summary.csv`, `checks.json` and all-role registry.
Existing engine replay verifies the paired-mode generator ID, source hashes,
RNG states, exogenous trace, resources and public telemetry.

The original numeric `Truth.pair_id` in additive exports uses the globally unique
registered seed, linked to the canonical opaque pair ID in the private manifest.
This prevents per-family index zero from colliding across roles.

Statistical members instead contain the original public `Rollout` NPZ and CSV
schema plus separate original `Truth` NPZ, configuration, seed, command and
source-hash metadata. Their existing research units and public metadata are
preserved; world and statistical records are never concatenated under one
schema/generator ID.

## Hand-labeled evaluator skeleton

```bash
python -m canary_ssm.world_evaluator --out examples/world_evaluator
```

`configs/world_evaluator_handlabels.json` contains hand-authored event intervals,
first-alarm times and expected outcomes. The skeleton writes `outcomes.csv` and
a computed pass gate. No alarm in that file is a detector prediction.

`OperatorLabel` uses simulated seconds and `operator-intervention-v1`, separate
from the unchanged research `J(i,t)`, kappa and 15-minute duration definition.
For a declared interval [onset,recovery), onset alarms succeed and recovery
boundary alarms are after-recovery. An ongoing interval can succeed at the last
observed timestamp and remains right-censored. Cases cover healthy quiet,
false alarm, premature, success, miss, after-recovery, abstention and insufficient
follow-up. The fixture minimum follow-up is 30 seconds, not a new research rule.
Success delay is onset-relative; missed/premature/after-recovery cases retain
horizon-capped delay. Null cases, abstentions and insufficient follow-up do not
receive invented success delays. These labels can fail: moving an onset changes
an expected success into a premature outcome.

Scenario exports keep `DETECTOR NOT CONNECTED` and do not evaluate missing
predictions as detector misses. Connecting an actual frozen detector and defining
scientific release-harm labels remain separate work. No thresholds, comparison
benchmarks or production-fidelity claims are made by this skeleton.
