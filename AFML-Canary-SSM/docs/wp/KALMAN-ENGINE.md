# Common engine and public Gaussian adapter checkpoint

14 November 2026. Extends `canary_ssm_control_adjustment.zip`.

The original common linear Gaussian engine was verified, not replaced. A new
public adjustment consumer connects independent and complete pooling with full
shared white covariance, carries no-effect AR state, and initializes effect
priors at the exposure minute. Existing EWMA, CUSUM and top-K implementations
consume the same residual/mask contract without fabricated posteriors.

## Executed validation

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 428 passed in 85.43s (0:01:25) |
| `python -m pytest -q tests/test_public_filter.py tests/test_kalman.py` | 22 passed in 1.25s |
| `python -m canary_ssm.kalman_fixture --out examples/kalman_engine` | All six computed gates passed |
| Documented `python -m canary_ssm.public_filter ...` | Exit 0; output exactly matches saved fixture |
| Supplied scalar and multivariate CSV reference | Max absolute error 1.1102230246251565e-16 |
| AR-only and AR-plus-white optimizer compatibility | Parameters, likelihood, success and boundary flags bitwise unchanged |

Numerical values are calculated in `examples/kalman_engine/numerical_checks.csv`;
compatibility is saved in `noise_compatibility.csv`. Raw check evidence is
`kalman_engine_validation.json`. The example manifest includes input/source
hashes, declared parameters, versions, machine, timing and computed failures.
No new randomness or calibration/holdout fitting is used.

## Evidence and limits

New tests independently condition Gaussian states with covariance downdates and
information-form equations, including correlated V, subset observations and
multi-minute gaps. They verify nonzero carried AR state, full covariance, exact
exposure prior variance, no pre-exposure effect output, missing/ineligible
prediction, late pre-receipt exclusion, future perturbations and a hand CUSUM
recurrence. The scalar no-effect innovation likelihood is checked against the
common engine with known white/control variance and missing observations.
A deliberately failed optimizer records every failed start and active bound.
The original scalar/statsmodels/PSD tests are untouched.

Only `preprocess.py` changes existing algorithm source, adding diagnostic metadata
to each optimizer start. Its optimization and parameters remain unchanged.
New source is `public_filter.py` and `kalman_fixture.py`; new tests are
`test_public_filter.py`. Docs, README and saved acceptance outputs are updated.
Existing Kalman/hierarchy/baseline/simulator source, research definitions,
original tests, fitted research models and prior fixtures are byte-preserved.
This is an extracted archive, with no git commit or merge claim.

The public prior is placed at exposure before the first observation, rather
than adding a first-step effect Q before that observation as the legacy wrapper
does. The new pipeline version documents this convention without changing the
old research path. Unavailable EWMA normalization yields an explicit unavailable
result. White covariance cannot be diagonalized or added again by this adapter.
No sub-minute exposure model is supplied.

The algebraic public fixture is an acceptance demonstration, not a resource-world
or calibrated detector benchmark. Tail probabilities are conditional on fixed
parameters and Gaussian assumptions; the release score is log maximum host risk,
not a release-union probability. Baseline outputs are sequential statistics.
Thresholds and alarms remain null. Background control contamination and nuisance
uncertainty remain open. The next patch is a separately reviewed frozen
calibration/audit protocol, before causal dashboard integration.
