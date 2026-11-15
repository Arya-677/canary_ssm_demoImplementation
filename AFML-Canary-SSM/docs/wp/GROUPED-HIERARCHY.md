# Constrained class/rack hierarchy checkpoint

14 November 2026. Extends `canary_ssm_gaussian_engine.zip`.

Original class-host research mode is preserved. The new public hierarchy reuses
the research sum-zero basis and a common joint Gaussian engine, with explicit
rack grouping for the physical demo interface. It reports group effects, host
deviations and total effects separately, retaining full joint covariance and
excluding AR noise from effect risk.

## Executed validation

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 445 passed in 88.95s (0:01:28) |
| Focused new hierarchy/public filter/original hierarchy tests | 43 passed in 2.32s |
| `python -m canary_ssm.hierarchy_fixture --out examples/grouped_hierarchy` | All eight computed gates passed |
| Documented class and rack CLI commands | Exit 0; both outputs exactly equal saved fixtures |
| Incoming rank-zero/rank-one public comparisons | Independent/pooled/baseline outputs remain exactly equal |

New tests independently condition a multivariate Gaussian and check full state
and total-effect covariance. They cover singleton/empty local basis, noncontiguous
groups, stable host identity and permutation invariance, basis orthogonality,
induced prior/process covariance, sum-zero reconstruction with cross terms,
future perturbations and AR-excluded risk. A dynamics-only check starts with
diagonal host priors and verifies that different persistence creates pooling.
Original tests are not edited, weakened or skipped.

## Computed pooling acceptance comparison

The following table is generated from `examples/grouped_hierarchy/pooling.csv`.
It uses diagonal white noise, matched marginal priors and a single-host impulse.
These values are conditional effect estimates, not detection performance.

| Model | Host | Effect mean at exposure | Effect variance |
| --- | --- | --- | --- |
| hierarchical | h0 | 0.4370065641823498 | 0.21856154574959863 |
| hierarchical | h1 | 0.36295077426980066 | 0.21856154574959863 |
| independent | h0 | 0.6709937763986487 | 0.3355863480733784 |
| independent | h1 | 0.0 | 0.3355863480733784 |
| diagonal_hierarchy | h0 | 0.6709937763986487 | 0.3355863480733784 |
| diagonal_hierarchy | h1 | 0.0 | 0.3355863480733784 |

The hierarchy moves the peer estimate and shrinks the observed host estimate
toward shared evidence. The diagonal-hierarchy negative control matches independent
inference, demonstrating that a hierarchy label does not establish actual pooling.
No plot, power, false-alert or calibrated alarm result is invented here.

## Changed boundary and limitations

`public_filter.py` extracts its existing joint loop into `_run_model` with optional
full-state retention; default outputs remain identical. New source is
`public_hierarchy.py` and `hierarchy_fixture.py`, with two explicit settings configs,
new tests, equations, audit/status updates and small saved artifacts. Original
`hierarchy.py`, Kalman engine, baselines, nuisance fitting, simulator, original
tests and model artifacts are byte-preserved. This is an extracted archive, with
no git commit or merge claim.

The public hierarchy inherits exposure-only priors and carried preperiod AR state;
the original research wrapper keeps its earlier convention. Grouping must match
control policy. Research 80% observed-canary, three-control and 60-pre-window
requirements are unchanged. All grouping uses monitored canaries, not every host
in the world. Rack/host priors are declared demo settings, not optimized estimates.

The saved public example has four monitored canaries, two per rack, and three
controls per represented rack. It re-emits existing algebraic metrics with a new
explicit exposure cohort and uses only the existing healthy development input
for nuisance fitting. It is not a physical-resource performance experiment.
World observation-model adequacy, control contamination, nuisance uncertainty,
threshold calibration and dashboard integration remain separate work. Raw checks,
manifest and preservation evidence are in `grouped_hierarchy_validation.json`.
