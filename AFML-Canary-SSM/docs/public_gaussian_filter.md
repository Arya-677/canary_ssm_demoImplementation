# Public Gaussian effects and comparator adapter

`canary_ssm.public_filter` consumes the existing frozen adjustment output and
model. It does not fit another reference or regress against canaries a second
time. `kalman.KalmanFilter` is the existing common engine; original research
`hierarchy.EffectDetector` already uses it for independent, pooled and constrained
hierarchical Gaussian effects. This patch connects independent and complete
pooling to the new public-window contract. No neural model is introduced.

## Equations and units

Time is simulated seconds on minute boundaries, with transition interval one
minute. A gap of k minutes applies k predictions, including process noise on each
transition. The engine accepts an observed subset through corresponding rows of
H and the full principal submatrix of V. No observations means prediction only.

For effect coordinates a and host AR noise e:

```text
s = [a, e]
r = [L, I] s + epsilon
F = blockdiag(diag(rho), diag(phi))
Q = blockdiag(diag(sd_effect^2), Qe)
Qe = diag(q_e^2)
V_t = diag(v^2) + outer(lambda, lambda) U_t
```

`q_e`, `v`, `sd_effect` and `prior_sd` are standard deviations in log latency;
Q, Qe and V are variances/covariances in squared log latency. Reporting residual
scales standardize baseline inputs; they are not added again to V or Qe.
Independent effects use L=I; complete pooling uses a single coordinate and L=1.
The same engine and observation subset logic apply to both. Correlated white
reference uncertainty can produce correlated independent-effect posteriors.

The common update computes S=H Pminus H' + V and its Cholesky factor, solves for
the gain, and uses the Joseph covariance formula:

```text
Pplus = (I-KH) Pminus (I-KH)' + K V K'
```

No inverse is used by the engine. Tiny covariance floors are counted; materially
negative covariance raises an error. The adapter validates dimensions, finite
observed residuals, stationarity, positive SDs, covariance symmetry/PSD and memory
budgets (128 canaries; 2 million covariance entries per batch). Minute gaps are
allowed by the filter API; the upstream public adjustment preserves missing rows
on a complete minute grid. No gap is treated as a single transition.

## Noise fitting and onset

The healthy-development fitting entry point remains
`public_adjustment.fit_development`. It calls the existing `fit_ar_class` and
`scalar_nll`: a vectorized no-effect AR innovation likelihood, with the known
lambda-squared-U contribution in measurement variance. Tests compare that
likelihood to the common Kalman engine with missing observations. The omitted
Gaussian constant is parameter-independent. This is a pooled marginal likelihood
across host series, not a joint likelihood for correlated development hosts.

The original AR-only fit pins white SD at V_FLOOR=1e-4 because the AR/white split
can be weakly identified. AR-plus-white remains available in the existing fitter.
Every optimization start now records status/message, iterations, evaluations,
explicit bounds and fixed white floor as well as success, objective and boundary
hits. Selection and numerical parameter fitting remain unchanged. The public
adjustment's noise-fit failure gate remains in force; a boundary fit is flagged,
not silently dropped. Existing saved models retain their historical diagnostics.
Healthy provenance is an explicit development attestation; hidden control faults
are still an open contamination challenge.

Preperiod filtering has AR states only, initialized stationary. Available fresh
observations update that no-effect filter. Its mean and full covariance are
predicted to the exposure boundary and carried into rollout. Preperiod windows
received after exposure are excluded from this state; later receipts cannot
retroactively revise it. This matches the loading-freeze receipt-time rule.

Effect coordinates are first created at the declared exposure minute, before
that minute's observation, with mean zero and variance prior_sd squared. There
is no effect process transition before this prior. Later minutes predict both
effect and noise; missing minutes predict repeatedly. If the first available
rollout row is later, prediction starts at the exposure prior. Without preperiod
observations, stationary AR initialization is explicitly reported. Exposure
inside a minute is unsupported and must be defined by an upstream policy.

This exposure-prior convention is versioned `public-gaussian-effects-v1`.
The legacy research wrapper remains unchanged: it initializes its joint filter
at the preceding step and calls `step` at the first rollout row. Thus the new
adapter has prior_sd squared, rather than an additional first-step effect Q,
before the exposure observation. No old research result or model is relabeled.
Observed exposure earlier than the declaration is rejected; rebuild adjustment
at the actual onset rather than absorbing early harm into preperiod AR state.

## Shared observations and honest outputs

`observations_from_adjustment` checks the frozen model/policy/feature contract,
scales and noise. It verifies full V equals diag(v squared)+lambda lambda' U.
A diagonalized matrix, duplicated shared covariance, changed frozen noise or
extra reference subtraction is rejected. No matched contrast is performed.

`GaussianEffects.run` returns host effect means, full covariance and conditional
Gaussian tail probabilities only at/after exposure. Its release score is the
existing log maximum host tail probability above KAPPA. This is not a probability
that any host is harmful. Scores are masked on ineligible rows; predictive
posterior values may still exist there and `updated` indicates observation use.
Results are conditional on fixed parameters and the declared linear Gaussian
model, whose adequacy for resource-world completion latency is unverified.

`run_comparison` invokes the existing adjusted EWMA, CUSUM and top-K CUSUM on
exactly the same masked residuals and eligibility as the Gaussian methods.
Preperiod availability is used only for AR filtering and EWMA normalization;
rollout updates use decision eligibility. Original baselines hold accumulators
on missing observations; the Kalman states predict. Existing EWMA needs at least
two usable observations per host after its 20-window preperiod warmup; otherwise
it returns an explicit unavailable result. CUSUM/top-K still run. Baselines emit
sequential statistics and host ranks, with `posterior=null` and
`host_probability=null`. They do not receive Bayesian probabilities.

Thresholds and alarms are null for every method. No tuning, equal-false-alert
comparison, calibrated detection performance or dashboard connection is claimed.
Monitoring remains DETECTOR NOT CONNECTED. Background control contamination and
unpropagated regression/loading uncertainty are carried through from adjustment.

## Executed entry points and fixtures

```bash
python -m canary_ssm.kalman_fixture --out examples/kalman_engine
python -m canary_ssm.public_filter --model examples/control_adjustment/model_rank1.json --adjusted examples/control_adjustment/adjusted_rank1.json --out comparison.json
python -m pytest -q tests/test_public_filter.py tests/test_kalman.py
```

Use `--effect-params params.json` to declare existing EffectParams fields; no
selection or optimization is performed. The exact adapter accepts independent
and pooled effects, with huber_c=0. `run_comparison` runs both effect maps under
the same declared hyperparameters, plus the three existing baseline defaults.

`examples/kalman_engine/numerical_checks.csv` records the supplied scalar
fractions and an independent multivariate information-form reference. Unit tests
add subset observations, multivariate repeated gaps, carried noise covariance,
exposure-only priors, receipt-time guards and future perturbations. Existing
statsmodels and long-gap PSD checks remain unmodified. The fixture reuses both
rank-zero and rank-one public algebraic acceptance artifacts, with no new seeds.
Its manifest records inputs, source hashes, configuration, versions, machine,
timing, failures and computed gates. These are numerical acceptance checks,
not a resource-world or detector-power benchmark.
