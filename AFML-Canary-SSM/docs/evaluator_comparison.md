# Offline replay evaluator

`evaluation_scoring.py` receives only public records and healthy-development
fits. It never imports the simulator, metrics or evaluator. Producers save truth
under `evaluator/`, public observations under `public/`; `evaluation_outcomes.py`
computes retrospective target outcomes; development target utilities and null
attestations remain inside the offline evaluator orchestrator. Original evaluator paths and
numerical inference are preserved.

The recovered Linux workspace did not contain the unarchived Mac evaluator or
its null caches. This is a new version, `truth-separated-replay-v2-linux-rebuild`,
with fresh registered seeds, fits and calibration. Earlier Mac results are
historical conversation evidence, not included as measured results of this run.

## Methods and inputs

| Method | Implementation | Fit/calibration |
| --- | --- | --- |
| Adjusted EWMA/CUSUM/top-K CUSUM | Existing `baselines.run_baseline`; K=3 declared in advance | Identical residuals/masks; each has own null threshold; no posterior invented |
| Independent effects / complete pooling | Existing `public_filter.GaussianEffects` | Development SD selection and separate thresholds |
| Class → host | Existing joint `GroupedGaussianEffects` | Original constrained class hierarchy |
| Rack → host | Same joint engine with explicit rack grouping | Physical-world variant, separate settings/threshold |
| Global → rack → host | Existing opt-in `NestedGaussianEffects` | Newly selected/calibrated offline diagnostic adapter; production activation remains blocked |
| Factor off | Rank-zero adjustment | Healthy nuisance/noise refit and new calibration |
| Persistence off | Group and deviation rho=0 | Effect SD reselected; nuisance unchanged because no-effect likelihood contains no effect rho; new threshold |
| AR noise off | Phi=0, white variance refit | Healthy white-noise refit; world likelihood includes known control uncertainty and tiny schema-required process floor; new threshold |
| Weaker / stronger pooling | Deviation innovation SD 3/.2 times selected SD | Development-selected group SD; new threshold for each |

There are 11 research and 13 world methods. All base methods consume the same
saved raw replay, residuals, shared white covariance exactly once and masks.
Ablations change the declared preprocessing/noise component, never the raw
replay. Three healthy development runs fit nuisance models. Three separate
positive development pairs select effect SD from {.003,.008} using eligible
**all-host-window** squared error. The true affected count never selects K or
any setting. All candidates, failed fits and bound hits are retained.

Original research host regressions remain preperiod-based; world regressions
are frozen healthy-development fits with pre-exposure loading adaptation.
Controls require freshness, no exposure, at least three per represented rack;
canary coverage remains 80%. Class/rack overlap is not silently nested.

## Targets

Research uses the original `metrics.event_truth/classify/localization/host_auc/brier`:
strict host effect >log(1.02), latent duration >=15 minutes, no premature success,
first detection inside a qualifying interval, remaining-horizon cap for misses,
premature and late alarms; localization at onset+30. Prediction-only canonical
research localization remains available alongside its explicit freshness flag
and fresh-only alternative. No-data rollouts cannot alert and do not erase misses.

World **release attribution** is separately named: same-exogenous paired log
completed-request mean-latency difference >log(1.02) for 15 jointly fresh minutes
on a monitored canary. This is offline evaluation, never an online observed
counterfactual or additive injected latent effect. Missing paired windows are
unknown; a nonneutral no-event run with missing target windows is unverifiable.
Neutral manifests supply a structural release-null attestation, not imputed data.
Completion latency can miss OOM/drop harm, which stays separate resource evidence.

World **infrastructure detection** uses operator-recorded active host/rack/shared
fault windows, minimum one minute, an all-healthy platform-null calibration and
separate result rows/policies. Rack targets include unmonitored controls; full-rack
localization is unsupported if target hosts lie outside the monitored cohort.
A platform alarm is not a release-attribution result.

World pairs share exogenous streams while queues/completions/routing can diverge.
`pairing_and_interference.csv` records control latency/routing/queue divergence
and canary queue divergence; no additive identity is imposed. Statistical pairs
still verify the exact original injected effect plus shared contamination identity.

## Scenario and role coverage

Healthy rollout, shared surge, host fault, rack outage, broad release harm,
transient harm, retention with/without latency harm, contaminated controls,
missing telemetry and recovery all have paired smoke rows. Statistical host/rack
cases are labeled analogues; physical memory mechanisms are explicitly unsupported
in the research generator. Retention/OOM/recovery scenarios are not guaranteed to
produce a qualifying completion-latency target: negative/unknown outcomes remain.

Seed registry family slots 34–44 separate scenarios and generator-specific purpose
blocks separate development, calibration, independent validation, smoke and final.
V2 uses offset12500, with infrastructure null indices offset+3000. Both pair
members always stay in one role. Pilot/test-only identities lie outside the saved
calibration/validation ranges. Final plans are identities only, without arrays.

## Calibration, gates and locked final data

Every method/endpoint uses complete eligible horizon maxima. No eligible window
means -infinity. With alpha=.05/B=2000, k=1901. Only strict score>ordered maximum
alarms; ties stay conservative and k>B gives infinity. Validation never changes
thresholds/settings. Pointwise exact 95% Clopper–Pearson null-alert intervals use **all**
independent rollouts, with no-data counts reported separately.

Release nulls are an iid hash-selected uniform mixture of six declared backgrounds:
healthy, surge, host fault, rack fault, contaminated controls and missing data.
Platform nulls are all healthy. This mixture audit is **not** the governing plan's
per-family qualification and does not close the original shared-step failure.
Computed audit statuses require B/n>=2000, finite threshold, exact two-sided
Beta–Binomial diagnostic p>=.01 and alert rate<=.075. Continuous-maxima diagnostics
can fail for tied/saturated scores despite conservative zero alarms; failures are
retained, not repaired with jitter or threshold retuning.

Final data deliberately remain sealed in this version because per-family
qualification has not been completed. Forging a PASS field cannot open them.
`checked_freeze` checks model/settings/source/runtime content; resumes also check
every completed score/public/private cache hash. Model/config/runtime changes
require a new study/version with fresh registered null identities.

## Reproduction

Run from the project root, with dependencies from pyproject.toml installed:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python -m canary_ssm.replay_evaluator run --out examples/evaluator_v2 --B 2000 --n-validation 2000 --offset 12500 --workers 8 --resume
python -m canary_ssm.evaluation_archive replay-null --study examples/evaluator_v2 --generator world --endpoint release_latency --role null-validation --index 0
python -m canary_ssm.replay_evaluator check-final-lock --out examples/evaluator_v2
python -m canary_ssm.evaluation_report --study examples/evaluator_v2
python -m pytest -q
```

For a new study, reserve fresh registered identities and omit --resume. Do not
reuse an existing directory with changed sources/settings. Saved manifests bind
Python/NumPy/SciPy versions; cross-runtime resumption is rejected.

Raw generator-specific outcome tables, full per-minute scores/eligibility masks,
independent maxima and full scenario-example public/private arrays are retained.
The compact download replaces large null-input generation buffers with semantic
public/truth fingerprints, config/seed/ordered commands and exact regeneration
checks. `evaluation_archive replay-null` regenerates and verifies all scores,
masks, public inputs, hidden truth and ordered commands; add `--materialize` to
restore that input's raw buffers. The original full-workspace resume command
requires raw null buffers; restore archived inputs before using it on the compact
delivery. `python -m canary_ssm.evaluation_check --study examples/evaluator_v2`
rebuilds every threshold, validation interval and gate from saved minute scores
without regenerating physical worlds. All figures and
numeric summaries derive from CSVs. No efficacy/superiority, production causal
attribution or real-system claim is made from the smoke examples.

## Performance scope

`evaluation_performance.py` measures actual Kalman-step wall time/state bytes,
whole-method replay and a separate traced peak-allocation replay (not RSS),
full-engine ticks, actual HTTP snapshot and durable step commands. The strict
DOM-ID VM runs the real app functions against the real HTTP API; its throughput
is separate from browser layout/paint/input. A real Chromium launch is attempted
and its environment failure is saved rather than claimed as a browser benchmark.
The measured API server has no live detector attached; posterior update costs
are measured separately. These are component measurements, not a combined
production capacity claim. Measurements during the concurrent audit are
diagnostic, not isolated limits.
The performance input copies are public-only, from a separate smoke replay, and
have their own hashes; they do not read evaluator targets.
