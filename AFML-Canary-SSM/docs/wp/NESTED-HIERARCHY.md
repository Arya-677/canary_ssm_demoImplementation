# Opt-in nested Gaussian hierarchy checkpoint

14 November 2026. Extends `canary_ssm_grouped_hierarchy.zip`.

This adds a separately versioned a=1*g+R*u+B*b variant with host-weighted rack
contrasts, within-rack host contrasts and full joint AR noise inference. Every
level has explicit priors, persistence and process noise. Separate component
outputs retain cross-level uncertainty and total host uncertainty. Existing
class-host and rack-host implementations are unchanged.

## Executed validation

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 461 passed in 82.20s (0:01:22) |
| `python -m pytest -q tests/test_nested_hierarchy.py` | 16 passed in 0.79s |
| `python -m canary_ssm.nested_fixture --out examples/nested_hierarchy` | All eleven computed gates passed |
| Documented nested public CLI | Exit 0; exactly reproduces saved public diagnostic output |
| Maximum basis error from saved CSV | 3.3306690738754696e-16 |

`basis_checks.csv` contains computed errors for unequal counts (3,2,1), a single
rack, all-singleton racks and one host. `components.csv` contains component means
and variances; JSON retains full covariance. The manifest records settings and
hashes, input/source hashes, package versions, machine, timing and failed gates.
No new random seeds or development/calibration runs are introduced.

## Independent checks and limits

Tests include the hand-computed (2,1) host contrast, projector-derived prior and
process covariance, stable identity and host permutation, empty levels, weighted
rack constraints, full Gaussian conditioning with subsets/gaps, covariance
reconstruction including every component cross term, future perturbations and
AR-excluded effect risk. A homogeneous full-observation test setup initially had
zero cross-level covariance by symmetry; its new test fixture now masks a host
to exercise nonzero cross terms. No preexisting test was modified or weakened.

The default configuration is disabled; CLI settings are mandatory. Config cannot
turn off selection/calibration requirements or insert an old threshold. Nested
results expose `diagnostic_score`, observation eligibility and false decision
eligibility, with null thresholds/alarms. The protocol fingerprint binds the
variant, settings, nuisance model, fixed roster and bases. New selection,
freezing, calibration and null audit remain separate work; none was performed.

Global residual structure is release-associated, not the workload factor estimated
from controls and not causal attribution. Overlapping hardware classes and racks
are crossed groups; extra class/level configuration is rejected rather than
stacked as a false hierarchy. Nuisance uncertainty, control contamination and
physical-world Gaussian adequacy remain unresolved.

New source is `nested_hierarchy.py` and `nested_fixture.py`, with one opt-in config,
new tests, equations, saved acceptance artifacts and audit/status updates.
All existing inference/simulator code, tests, models and fixtures are preserved.
The source is an extracted archive; no git commit or merge is claimed. Raw
validation and preservation evidence are in `nested_hierarchy_validation.json`.
No benchmark performance or calibrated scientific claim is reported.
