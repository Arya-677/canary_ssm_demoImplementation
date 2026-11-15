# Paired scenario bundle checkpoint

14 November 2026. Extends `canary_ssm_public_telemetry.zip`.

Created seven resource-world scenarios and four additive-statistical smoke pair
profiles, with separate role/pair/generator identities, public outputs and
private evaluator truth. The default archive materializes only smoke data;
all five roles are registered with indivisible pairs and fresh seed blocks.
The registry contains 55 pair plans and 110 distinct member IDs.
Template families recur across roles with fresh instances; this is not an
unseen-template generalization claim.

## Executed validation

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 385 passed in 80.43s (0:01:20) |
| Scenario-specific tests | 25 cases included in the final full-suite run |
| `python -m canary_ssm world-scenarios --out examples/scenario_bundles` | All 11 smoke-pair gates passed |
| `world-scenarios --plan-only --out ...` | Registry written; no run data materialized |
| `python -m canary_ssm.world_evaluator --out examples/world_evaluator` | All 14 authored outcome cases passed |
| Existing dashboard, scheduler and public-telemetry HTTP/DOM checks | All gates passed; no visual rendering claim |
| `node --check canary_ssm/web/app.js` | Exit 0 |

The full suite preserves the original statistical generator and inference tests.
The seed registry only appends purposes, preserving every old seed base. The
world adds an opt-in paired sampler because routing-dependent consumption of the
old workload RNG could shift later arrivals. Shared uniforms and a separate
routing stream now keep exogenous randomness coupled even if service availability,
arrival rate, queues, drops or routing outcomes differ. Statistical code is not
rewritten; its exact additive difference is tested separately.

## Generated smoke summary

The following table is generated from `examples/scenario_bundles/summary.csv`.
Divergence is a resource-trace comparison, not evidence of detection or an
additive-effect estimate. Residual is only defined for the additive generator.

| Family | Computed pair pass | Endogenous divergence | Max additive residual |
| --- | --- | --- | --- |
| healthy | True | False | n/a |
| host_fault | True | True | n/a |
| rack_fault | True | True | n/a |
| shared_demand_surge | True | True | n/a |
| transient_degradation | True | True | n/a |
| persistent_degradation | True | True | n/a |
| recovery | True | True | n/a |
| additive_baseline | True | n/a | 0.0 |
| additive_transient | True | n/a | 3.434752482434078e-16 |
| additive_persistent | True | n/a | 3.434752482434078e-16 |
| additive_recovery | True | n/a | 4.40619762898109e-16 |

Each world member stores config, seed, ordered engine commands, replay artifact,
public telemetry/resource CSVs, separate injection/operator truth and the private
exogenous-uniform trace. Per-member hashes validate data identity. Public IDs do
not reveal family, role or null/harm labels. Pair validation and role-use guards
reject split/moved pairs and forbid harmed members in threshold/null-audit views.
Fresh additive fixture blocks also isolate future holdouts from archived research
runs. Default generated folders contain only the smoke role.

The evaluator skeleton consumes explicit operator labels and authored first-alarm
times. It covers quiet/false-alarm, premature/success/miss, after-recovery,
abstention, censoring and follow-up limits. No disconnected detector is treated
as a missed event. No thresholds, calibrated false-alert rates, new SSM benchmark
or production-fidelity result is reported.

Raw validation is in `scenario_bundle_validation.json`. Existing saved engine
examples were regenerated for exact source/hash compatibility. The archive is an
extracted source tree, so no git branch or merge is claimed. Narrow ignore
exceptions preserve the small bundled smoke NPZs; larger role data stays ignored.
Existing inference, original simulate.py, research metrics and model artifacts
remain unchanged, and no preexisting test was edited or skipped.
