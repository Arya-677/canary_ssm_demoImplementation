# Development-frozen public control adjustment

`public_adjustment.py` prepares public residuals for a future detector. It does
not fit an effect SSM, choose thresholds, produce detector scores or connect the
dashboard to inference. Existing research constants, likelihoods, effect filters,
models and results are preserved. The new model ID is
`development-frozen-control-adjustment-v1`; it is not a replacement file for an
existing research nuisance artifact.

## What is reused, and what is versioned

The new path reuses `factor._ols_host`, the extracted research PCA/projection
helpers `fit_rank_one_controls` / `project_rank_one_controls`, and
`preprocess.fit_ar_class`. The existing research `factor.adjust` calls those same
factor helpers. Its intercept/slope pre-period fitting behavior remains
unchanged. A saved before/after check compared the previous source from the base
archive against the refactor and found bitwise-equal research arrays for rank
zero and rank one, including masks, uncertainty and matched contrasts.

The public path follows the requested different fit boundary: host intercepts,
workload slopes, control weights/loadings, scales and noise are frozen on
**declared healthy development** inputs. On a target run only canary loadings may
adapt, using pre-exposure public data that was also available by the freeze time.
It does not re-fit regression or noise on current canary/post-exposure data.

The research input is unchanged. Public input features have a separate feature
ID, `public-logmean-log1pworkload-v1`:

- y is `log_latency_mean`, the completed-request mean of log latency in ms;
- x is `log1p(workload_rps)` per host/service;
- workload centering is fitted once on valid healthy development entries;
- the new regression permits host-specific measured workloads. A shared x_t can
  be represented by identical columns; the research path still uses its shared
  workload vector and original units.

This is not a silent conversion between log(arithmetic latency mean), mean(log
latency), or the original research simulator. Matching units/estimands and
calibrating a later world detector remain necessary.

## Public input and fit admission

`panel_from_time_slice(slice, service_id)` accepts a committed public telemetry
prefix with a matching input hash. It rejects evaluator fields, mixed runs or
epochs, future windows, changing placement and multiple same-service replicas
per host. Multi-replica service aggregation is not implemented: replicas must
not be counted as independent host controls. Other services are inspected only
for **public exposure metadata**: if any service exposes a host, that host is
not an unexposed control. Missing or mixed exposure metadata is not fresh proof
of an unexposed host.

`PublicPanel` validates finite fresh values, boolean masks, stable host/rack/class
metadata and a complete one-minute grid. Missing minutes must be explicit masked
rows. They cannot be compacted, since the existing AR likelihood advances one
minute per row. Decision-time availability is retained separately from event
time. It may include the receiver's configured grace period.

Fit requires `HealthyDevelopment(panel, role='development', declared_healthy=True,
provenance_id=...)`. Other data roles, a missing attestation, or any public exposed
host are rejected. Each host needs at least ten fresh healthy development windows.
The caller's health declaration is an offline provenance attestation, not a claim
that public measurements can prove no background fault existed. The fitter does
not read evaluator truth to select or trim samples. Dataset hashes, the role and
provenance ID are saved for audit. An incorrectly declared development set can
contaminate the fit; a robust health selector is not provided.

Fit fixes a planned monitored-host set. Those hosts are excluded from the control
pool even while unexposed, preventing self-reference when their pre-loadings are
adapted. Unknown hosts or a different roster/group/feature convention require a
separate fit; target data is not used to repair a missing development model.

## Equations and development estimates

For host i, healthy development OLS fits

`c_it = y_it - mu_i - beta_i * (x_it - x_center)`.

A non-varying workload cannot identify a slope. It gets beta=0 with an explicit
`workload_not_identified` diagnostic; the output does not claim that coefficient
was estimated precisely. Development workload support is recorded for later
extrapolation flags.

The rank-one control PCA uses the existing sign/scale convention: residuals are
zero-filled only at missing development entries, loadings come from the leading
singular vector, and their mean fixes the sign. Counts of those missing entries
are returned; zero-filling is not a robust missing-data estimator. Control
residual variances have the existing 1e-8 floor. The fitted development control
loadings/weights are then fixed on the target run.

At each decision, use only fresh, observed, known-unexposed control hosts:

```text
W_t = diag(1 / frozen_control_variance) on fresh controls, zero otherwise
fhat_t = (lambda_C' W_t lambda_C)^-1 lambda_C' W_t c_C,t
U_t    = (lambda_C' W_t lambda_C)^-1
r_i,t  = c_i,t - lambda_i fhat_t
```

No second control mean or matched contrast is subtracted from r. The research
matched-contrast comparator remains a separate old path. Rank zero sets fhat,
U and loadings to zero; its output is workload-only c, not a different hidden
reference estimator.

Development canary loadings supply a frozen prior/fallback. A target run's canary
loading is fitted through the origin against pre-exposure fhat only, with at
least 60 usable pre-windows and nonzero factor energy. The fit excludes exposed
canaries, stale/missing inputs and pre-windows without the required fresh controls
in that canary's own group. It also excludes windows whose decision-time receipt
is later than the loading-freeze boundary. The earliest public exposure caps an
incorrectly late declared boundary. Insufficient pre-data keeps the development
loading and sets an explicit fallback flag; post-exposure canaries never repair it.

Scales are empirical healthy-development residual SDs (floor 1e-6). For fitting
scales and noise, each development control is left out of its own reference.
Canaries always use independent development controls. The existing AR+white
innovation likelihood fits group phi and q, with white SD pinned to the research
AR-only floor 1e-4. Known reference-error variance `lambda_i^2 * U_t` is supplied
to that likelihood. Separate development runs form separate series; no artificial
AR transition connects their endpoints. Fit starts, convergence and boundary
hits are retained. Failed noise fitting masks decisions; boundary fits are flags,
not evidence that calibration succeeded.

## Shared covariance, exactly once

The returned measurement covariance is in **log-latency squared units**:

`V_t = diag(v_group(i)^2) + outer(lambda_canary, lambda_canary) * U_t`.

The full shared matrix is preserved, including cross-rack canary covariance.
It is not replaced by independent diagonal terms. AR state noise phi/q remains
separate. Empirical reporting scales are not added again to V. A downstream
consumer must use either this full V or its equivalent (lambda,U,v) recipe,
**not both**. No downstream SSM connection is supplied in this checkpoint.

For example, three controls with loading 1 and variance 4 give fhat=1 and U=4/3
when each residual is 1. Canary loadings 2 and 3 then give off-diagonal covariance
`2*3*(4/3)=8`. Their common signal is removed once, producing residuals zero;
subtracting another reference would fail the hand-computed test. Losing one
control raises U to 2 and makes the default three-control decision ineligible.

These covariances are conditional on frozen parameters and the diagonal control
noise approximation. Regression/loading estimation uncertainty is not fully
propagated. Correlated faults and control contamination can invalidate that
approximation. No causal attribution, robustness or marginal-model exactness is
claimed.

## Eligibility, per-rack support and quality

Research defaults remain **80% observed canaries and three fresh controls per
represented group**. Rank zero retains the same overlap/coverage requirement.
The existing factor-identification and usable-fit checks also apply.

The default policy `research-eligibility-v1` uses class_id and forbids changes to
those constants or the 60-pre-window loading rule. Rack demos use separately
versioned `demo-rack-rank1-v1` / `demo-rack-rank0-v1` policies with exactly the same
80%/3 defaults. Every represented monitored rack must independently have enough
fresh controls; many controls in another rack cannot compensate. Current workload
support overlap and development extrapolation are returned as quality flags;
they do not silently change the eligibility threshold.

Changing thresholds requires a distinct `demo-*` policy ID and a nonempty
recorded reason. The policy, actual numerical settings and reason are embedded in
the saved model and every result. No code changes the global research constants.

Output contains residuals, observed/control masks, availability and decision
eligibility, canary exposure metadata, group control counts, factor/U, full shared
and measurement covariance, frozen scales/noise, adaptation counts/cutoffs,
fallbacks, convergence diagnostics and per-time quality flags. Unknown factor
information remains missing; it is not zero uncertainty.

`availability_eligible` describes coverage/reference availability. `eligible` is
also false before the declared monitoring/exposure boundary. Pre-period residuals
are explicitly diagnostic-only: their loadings were frozen using the completed
pre-period, so they must not be reported as historical online decisions. A
prepared state is bound to its run and epoch; another run must prepare its own
loadings. For an event-time window convention, supply the first monitored window
timestamp as `exposure_time`; earlier physical timestamps conservatively exclude
additional pre-data. Receipt availability is always checked as well.

Background faults **can contaminate controls**. The estimator remains ordinary
weighted projection and will follow contaminated references. Results explicitly
include `background_control_contamination_possible` and
`plain_weighted_projection_not_robust`. The test deliberately shows a contaminated
reference hiding a positive canary value; it does not use hidden injected labels
to drop controls or claim a robust estimator has solved this challenge.

## Commands and fixture

```bash
python -m canary_ssm.adjustment_fixture --out examples/control_adjustment
python -m canary_ssm.public_adjustment fit --slice examples/control_adjustment/public/healthy_development_slice.json --service-id fixture-service --canaries h0 h5 --role development --healthy --provenance-id algebraic-public-fixture-v1 --policy-json configs/rack_adjustment_rank1.json --out adjustment_model.json
python -m canary_ssm.public_adjustment apply --model adjustment_model.json --slice examples/control_adjustment/public/monitoring_slice.json --service-id fixture-service --exposure-time 4860 --out adjusted.json
```

The frozen JSON model has an integrity checksum and validated parameter shapes,
positive variances/scales and stationary AR parameters. Parameter getters return
copies. The rank-zero policy provides the documented workload-only ablation.

The acceptance fixture supplies algebraic public metrics on a minute grid; it is
not a physical-world run or SSM benchmark. Development inputs use registered
world_dev seeds; monitoring inputs use world_smoke seeds. Generative challenge
metadata is stored separately under evaluator and is never read by the fitter.
Both rank outputs, fitted artifacts, public slices and computed gates are saved.
No control fault label becomes a detector score or dashboard status.

Tiny four-minute world scenarios do not provide 60 pre-windows. They should use
the flagged development-loading fallback, not a silently relaxed research rule.
For longer real world pre-periods, size telemetry budgets accordingly: twenty
one-second replica sources require 72,000 records for sixty minutes; raise the
configured budget within its bound or use an appropriate coarser tick. The
existing default budget is finite and is not overridden by this preprocessing
module. Actual detector calibration and monitoring integration remain subsequent
work.
