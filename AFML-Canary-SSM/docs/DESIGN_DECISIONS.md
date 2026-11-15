# Design decisions, deviations, and gaps

## Physical-world policy extension — 15 November 2026

The original research definitions, inference and frozen artifacts are preserved.
`world_policy_fixture.py` supplies a separately versioned rack-grouped **eligibility**
protocol with independent Gaussian effects, 60-second physical ticks, a four-minute
fixed horizon and all-healthy background. Effect defaults are predeclared; healthy
development alone fits nuisance preprocessing. Calibration freezes the threshold;
separate null-validation seeds audit it without retuning. This is not hierarchical
calibration, general fault robustness, or closure of the shared-step failure.
`world_policy_live.py` sends only committed public prefixes through the existing
filter and validated API; it does not own the world clock. Full measured scope and
remaining gaps: [world_policy.md](world_policy.md), [wp/WORLD-POLICY.md](wp/WORLD-POLICY.md).

## Choices where the handbook left room (review these)
1. **Factor sign/scale.** Rank-one PCA on pre-period control residuals; factor normalised to unit variance;
   sign fixed so the *mean* control loading is positive (a stabler stand-in for "a designated positive
   reference loading"). Loadings therefore carry the factor's SD (~0.016 in the default sim, not ~1).
2. **Release score** = `log max_i Pr(a_i > kappa)`. Same ordering as the handbook's max-host probability but does not
   underflow (raw probabilities reached ~1e-86 on null rollouts in smoke runs). Host probabilities are still stored
   and used for Brier/calibration. It is a score, never "Pr(any host harmful)".
3. **Pooled SSM** uses the full state (one effect + per-host AR noise) rather than a literal pre-averaged canary mean.
4. **Effect prior** is reset to zero with proper diagonal variance at t0-1; pre-period filtered AR noise state and
   covariance are carried in. Effect and nuisance parameters are fitted separately.
5. **Ineligible minutes** (coverage < 80% of canaries, < 3 fresh controls per represented class, or no factor) are
   predict-only and cannot alarm. Late records (`decision_obs=False`) are treated as unavailable.
6. **Dev selection**: two-fold by pair id (threshold from nulls of one fold, capped time-to-success on the other fold's
   harmed rollouts, misses = remaining horizon). Needs >= 20 nulls per fold at alpha=0.05, enforced with an error.
7. **Ablations** `hier_rank0`, `hier_arwhite`, `hier_white`, `hier_huber`, `hier_degraded` reuse the hierarchy's selected effect hyperparameters
   (nuisance refit where required); `hier_no_persist` is re-selected over rho=0 with the 3x2 SD grids. Each gets a fresh
   calibrated threshold. Re-tuning all ablations separately is an optional stricter protocol.
8. **Simulator** white measurement noise is now OFF by default (optional SD 0.01 via `meas_sd`), after the pilot showed the AR-innovation/white split is weakly identified. See the handoff section below.
9. **Advisory policy** h_off = h_on - 0.5*(h_on - median null score); h_on from the one-crossing rule.
10. **Localization cutoff** m in 1..5 chosen on dev by mean F1 at onset+30 min; top-3 recall is
    |top3 ∩ A| / min(3, |A|).

## Observed during build (sandbox, not evidence about the method)
* Smoke dev data with 24 pairs gave an infinite threshold for every method (fold too small); now a hard error.
* With 20% MCAR missingness the 80%-coverage rule makes the detector abstain ~1/3 of minutes (10 canaries). That is a
  policy default to revisit and report, not a bug.
* The simulator matches the filter's assumptions closely; add the stress suite before believing any advantage.

## NOT implemented (each needs its own estimate; do not describe the project as covering them)
Xie-Siegmund mixture GLR and BOCPD comparators; Monte Carlo joint release probability; rank > 1 factor;
informative missingness and duplicate/out-of-order records beyond late arrivals; consecutive-crossing policy
calibration by replay (only the advisory replay exists); survival-analysis stratification (horizons with
insufficient follow-up are excluded instead); real data / Borg traces; dashboard; the neural/Mamba track.


## Changes driven by the Experiment 1-6 handoffs (rev. 10 Nov 2026)
The handoffs are second-hand summaries of reports; the pilot code and CSVs were not seen, so their numbers stay "as reported".
What follows is what this repo now does about each point and what it does NOT resolve.

| Handoff finding | Change in this repo | Status |
|---|---|---|
| Single AR(1) per host; white split weakly identified | default nuisance `noise="ar_only"` (white SD pinned at 1e-4); `ar_white` and `white` kept as ablations `hier_arwhite` / `hier_white` so the missing comparison table gets generated | decision supported by pilot; comparison table still to be produced by the pipeline |
| Sustained workload step breaks adjusted detectors | simulator `workload_step` (0.3365 = log 1.4); `beta_mode` = `pre` or `pooled_dev`; `audit-null` command; `configs/audit.yaml` | **reproduced, NOT solved** (docs/SANDBOX_AUDIT.md) |
| Host-specific beta untested | `beta_jitter` scenario `step_beta_heterogeneous` | pooled slope fails under heterogeneity in this repo |
| Calibrate on the evaluated distribution; per-family P3 not deployable | calibration role is the evaluated mixture; no per-family thresholds; a causal runtime regime rule is **not implemented** | open (Experiment 7) |
| 99.7% healthy crossings at rho=.99, innovation SD .005 | `long_run_sd <= kappa` constraint on the effect grid (24 -> 18 candidates); a test enforces it | implemented |
| Heavy tails inflate false alerts | `hier_huber` ablation (winsorise at 3 pre-period SDs); audit family `student_t3` | implemented; effect to be measured |
| phi_e misspecification: 73.4% false alerts | audit family `phi_e_0.8` | measured here: model-based detectors inflated; no fix |
| Missingness "robust" may mean blind | `table_abstention.csv`, `abstain_frac` in audit | implemented |
| Mislabelled PASS verdicts, summary vs table contradictions | PASS/FAIL computed from CIs (`report.calibration_gate`, `gate_status.json`); a test uses the 42/500 case; gate needs n >= 400 per cell | implemented |
| Top-3 CUSUM used K = true affected count | K chosen on development data from {1,3,5,10} | implemented (already the case) |
| Dual-mode detector untested | `combo_*` union detectors with ONE joint calibration (ECDF-max of null maxima); a test shows a naive OR exceeds the budget | implemented, not evaluated at scale |
| Scenarios S1-S5, class-wide harm, 30% label errors | `affected_mode: class0`, `label_error`, configs/default.yaml families | implemented; S6 unknown to me |
| Noise sweep 0.01/0.02/0.04 | `cross:` expansion, configs/noise_sweep.yaml | implemented |

### Seeds
Handoff seed ranges (400000-559999 and set 1) are avoided: this repo uses 10k, 1M-7M. Set-1 ranges were not stated; check for overlap if reproducing pilot runs.

### Why the step failure is hard (hypothesis, partly measured)
A persistent per-host offset from `(beta_i - beta_hat_i) * step` is observationally identical to a persistent regression on that host.
Pooling beta shrinks the estimation error when hosts respond alike and creates systematic offsets when they do not (measured in
docs/SANDBOX_AUDIT.md). Estimating beta online from controls after the step is tempting but is confounded with the shared factor
shock when the two coincide (the plan's identifiability trap); not implemented. A causal regime rule keyed on the measured workload
shift (the covariate is observed) is the candidate for Experiment 7.

## Phase P1 Protocol Repair & Tier-0 Findings (`v0.3-p1`, `X-0.2..X-0.4`)
- **Regime separation (`WP-A1`):** Replaced `configs/default.yaml` with `configs/plain_main.yaml` (`regime: plain`) and `configs/step_regime.yaml` (`regime: step`); `configs/legacy_mixture_with_step.yaml` is retained for reproduction only. Policy Schema v2 keys thresholds by active regime and enforces regime matching in `calibrate`, `validate-null`, `evaluate`, and `study`.
- **`X-0.2(a)` `hier_arwhite` under `meas_sd=0`:** Confirmed in `nuisance_arwhite.json` that `v = 0.000100` hits the lower optimizer boundary (`boundary_hit=True`), making `hier_arwhite` coincide with `hier_ssm` (`max_abs_diff_median = 0.000312` across 50 rollouts). Under `meas_sd=0.01`, `ar_white` recovers `v = [0.009918, 0.008582]` and diverges (`max_abs_diff_median = 0.1567`). Therefore `hier_arwhite` is dropped/redundant in `meas_sd=0` plain benchmarks and tested under `meas_sd > 0` in `E2/A3` and `R2`.
- **`X-0.2(b)` Step false alerts in v1 Exp 7:** Confirmed the 6.8%–9.0% step excess at `B=500, n=500` came from `B=500` threshold order-statistic sampling noise (all 8 `(regime, method)` cells pass Gate G2 at `B=2000, n=2000` with `bb_p = 0.0299..0.9422`).
- **`X-0.2(c)` Label-error sensitivity:** Confirmed the apparent v1 `hier == label-error` invariance came from weak local variance (`sd_h_ratio=1.0`, dominated by `S2` class-0 energy); varying `sd_h_ratio in {0.25, 1.0, 4.0}` changes `mean_capped_time` monotonically under 0%/30%/50% label corruption (`1.45 -> 5.08 -> 6.37` min at `sd_h_ratio=1.0`).
- **`X-0.3` Predeclared grid expansion & 5-fold CV + 1-SE (`v2.0-exp2`):** Auto-expansion (`v2.0 -> v2.0-exp1 -> v2.0-exp2`) resolved all boundaries for all 4 classical baselines + `pooled_ssm` + `indep_ssm`; `hier_ssm` settles at interior `rho=0.999` (`[0.9, 0.9995]`) and lower edge `sd_g=0.000125, prior_sd=0.005` matching the constant-shift asymptote (`hier_rw`, ~13.6 min vs 29.46 min for `topk_cusum`).
- **`X-0.4` Gate G2 on 14,000 plain validation nulls (`artifacts/policy_plain`):** All 7 primary methods, `combo_*`, and 5 of 6 ablations passed Gate G2 across all 7 families (`118/119` cells pass; min `bb_p = 0.0351` among those 112 cells). Only ablation `hier_rank0` failed on `S5_label_errors` (`193/2000 = 0.0965`, `bb_p = 1.22e-8`) because skipping factor adjustment leaves the shared +5% shock intact, so random label flips producing imbalanced class splits (`max_cls=6`: `8.18%`; `max_cls=8`: `30.00%`) pool correlated positive shock residuals onto larger classes. `hier_rank0` is flagged FAIL under S5 / dropped from equal-FAR performance claims.


## Virtual-world console and platform faults (14 Nov 2026)

The local dashboard listed as absent in the original statistical-track gap list
now exists in `dashboard.py` and `web/`. It does not connect that statistical
detector to the world. Typed platform events are in `faults.py`; orchestration
and simulated release profiles are in `operations.py`; physical approximations
remain in `resources.py`. `docs/faults.md` records exact overlap/recovery rules,
fixed 64 KB/request-equivalent network work, bounded memory pressure, and
separate developer truth. `docs/console.md` describes persistence and replay.
No neural model, new statistical calibration or inference rewrite was added.
The world latency estimate is not the statistical pipeline's log-latency data.


## Background scheduler (14 Nov 2026)

Background events use a per-target Bernoulli grid hazard, p = 1-exp(-rate*dt),
with per-host/per-nonempty-rack/per-world rates in simulated seconds. Named
PCG64 streams keep host proposals independent; global admission caps introduce
accepted-event dependence. Stable lexical ties, post-end scoped-target cooldowns,
bounded uniform durations/severities, and the finite start horizon are declared
in `fault_scheduler.md`. This is a physical-world simulation approximation,
not a new research event/harm definition. The existing Gaussian inference,
calibration policies, fitted artifacts and qualifying-event definitions remain
unchanged. Schedule truth is private replay/developer data, never a detector input.


## Public telemetry and causal windows (14 Nov 2026)

Public latency now has a separate tick-quantized completed-FIFO-request source;
the analytical resource proxy and original research log-latency model are unchanged.
The arithmetic and log request moments are exported separately, without silently
substituting log(mean latency) for mean(log latency). Minute windows close on a
fixed deadline, use explicit fresh masks/coverage, reject mixed exposure from
inference eligibility, and never backfill prior inputs or scoring receipts.
Delay/duplication/loss use the telemetry RNG only. Injection labels and mechanism
parameters are evaluator-only. `true_affected` is targeted-injection status, not
the research qualifying event J(i,t). There is no physical-model counterfactual
additive latent log effect; that evaluator field remains null. This work changes
world observation plumbing, not frozen research harm/metric/calibration definitions.
See `public_telemetry.md` for units, sufficient statistics, limits and adapter gaps.


## Scenario bundles and paired-world randomness (14 Nov 2026)

Registry 2.1 appends world and additive-fixture role blocks after every existing
purpose, preserving old seed_for outputs. Fresh additive holdout plans avoid
reusing archived research seeds. Scenario IDs are opaque; roles, pair labels,
operator truth and common-uniform traces remain outside inference inputs.
Original simulate.py remains byte-identical and retains its structural additive
pairing check. Opt-in paired resource configs use shared traffic/arrival uniforms
and inverse-Poisson counts with an independent routing stream. Endogenous
routing, queues, completions and latency may differ; no additive world identity
is asserted. Default resource sampling remains unchanged unless opted in.

The new evaluator labels operator intervention intervals in simulated seconds;
they do not alter research kappa, J(i,t), the 15-minute qualifying duration,
calibration rules or scientific outcome metrics. Hand-case alarms are authored
fixtures, not detector predictions. Only smoke data is materialized by default;
new held-out roles are registered plans. See scenario_bundles.md for stage guards
and limits. No model fitting, threshold tuning or final performance experiment
is performed here.


## Development-frozen public control adjustment (14 Nov 2026)

The current user requirement freezes intercepts, workload coefficients, scales
and AR noise from healthy development data, with only canary factor loadings
adapted on available pre-exposure data. This intentionally differs from the
original research pre-period regression. It is a separately versioned public
feature/model adapter, not a rewrite of the research definition. Existing factor
code only shares extracted algebra helpers; rank-zero and rank-one original
outputs are bitwise unchanged against the incoming source archive.

Public features are mean request log latency and log1p workload rate. Complete
minute grids retain missing rows; event and decision receipt times both constrain
loading adaptation. Fit provenance is a healthy-data attestation, not an inference
claim that hidden background faults are absent. Planned canaries never serve as
controls; public exposure on another service also excludes the host. Rack policy
IDs change grouping only, retaining 80% canary coverage, 3 fresh controls and
60 pre-observations. Short pre-periods use the flagged development loading.

The reference is subtracted once. Its uncertainty remains the full rank-one
canary covariance outer(lambda,lambda)*U; measurement white noise is added once,
AR noise stays separate, and reporting scales are not added as noise again.
Frozen regression/loading parameter uncertainty is not propagated. Plain weighted
control projection is not robust; contamination is an explicit unsolved challenge.
Rank zero is workload-only with the same availability gates. No new SSM score,
threshold, detector dashboard state or scientific benchmark is supplied here.


## Common engine and public Gaussian effects (14 Nov 2026)

The existing Cholesky/Joseph KalmanFilter and original research effect wrapper
are retained byte-for-byte. A versioned public adapter now uses the same engine
for independent and completely pooled effect maps on the prior public adjustment.
It carries the no-effect preperiod AR state, including full covariance, and
creates effect priors only at exposure. Windows received after exposure cannot
revise that state. White reference/measurement V stays outside AR process Qe.

For the public adapter, the effect prior is located at the exposure minute before
its observation; no additional effect Q is applied at that instant. This differs
from the legacy wrapper's preceding-step initialization followed by step(). The
old wrapper is unchanged and its old model/results remain historical research
artifacts. The new pipeline ID makes the convention explicit. No frozen harm,
event, calibration or evaluation definition changes. Early actual exposure is
rejected until adjustment is rebuilt at the actual onset.

Noise optimization is unchanged; every start now also reports optimizer status,
message, counts, bounds and fixed-white-floor metadata. Both AR-only and
AR-plus-white fitted parameters and likelihoods compare bitwise equal to the
incoming implementation on the executed fixture. The likelihood is a pooled
marginal no-effect likelihood, not a new joint estimator or robust procedure.
Baselines reuse the same masked residuals and have no posterior probabilities.
No thresholds, alerts or dashboard integration are enabled by this checkpoint.


## Explicit public class/rack constrained hierarchy (14 Nov 2026)

The original class-host research hierarchy, entry points, artifacts and defaults
remain unchanged. The public adapter now accepts class grouping by default and
an explicit versioned rack demo variant. Group membership is selected from frozen
public host metadata and must match adjustment/control-eligibility grouping.
No physical rack is silently substituted for a research class. The roster is
fixed in canary order; group columns are sorted and the original orthonormal
sum-zero basis is reused. Singletons contribute no local coordinate.

The new state is jointly filtered as [theta,b,e] with H=[C,B,I] and effect-risk
map [C,B,0]. Coordinate priors and process variances induce full host covariance;
posterior theta/b/e cross terms are retained. Component output uses B*b, not
individual b coordinates mislabeled as host effects. Separate class/rack effect,
host deviation and total effect outputs include the cross covariance needed for
reconstruction. AR noise is conditioned on but excluded from effect risk.

Pooling is demonstrated with diagonal white noise and a matched-marginal-prior
independent comparison. A diagonal induced prior/process covariance with equal
dynamics deliberately removes pooling; different group/local dynamics can create
it again. This guards against calling independent host filters hierarchical.
Rack settings are declared acceptance/demo choices, not tuned performance claims.
The public exposure prior convention is inherited; legacy research timing is not
changed. The shared public Gaussian engine extraction reproduces earlier saved
independent/pooled/baseline outputs exactly for both factor ranks.

The four-canary acceptance fixture re-emits existing algebraic public metric
values with an explicit two-canary-per-rack exposure cohort and three controls
per rack. Healthy nuisance fitting uses the existing development-only input.
No new seeds, physical-world benchmark, threshold tuning, holdout evaluation or
monitoring connection is introduced. Scientific harm/event definitions and
eligibility defaults remain unchanged.


## Opt-in nested global/rack/host variant (14 Nov 2026)

`nested-global-rack-host-v1` is a new diagnostic-only variant behind explicit
configuration. Original research, public class/rack hierarchy, independent,
pooled, baseline and nuisance code remain unchanged. Its state is [g,u,b,e],
with a=1*g+R*u+B*b. R uses host-count-normalized rack incidence and a fixed
Householder contrast against sqrt(rack counts/n); it spans rack-constant host
vectors orthogonal to all-ones. Rack deviations have host-count-weighted zero
mean. Empty rack/host levels are explicit for one rack or singleton racks.

Global, rack and host persistence, priors and innovations are separately declared.
The existing joint Gaussian engine retains all effect/noise and cross-level
covariances. Component outputs include all covariance pairs; risk excludes e.
The global coordinate is release-associated residual structure, distinct from
the already-subtracted control workload factor. It does not establish causation.
Hardware classes overlapping racks are crossed, not an additional nested level;
this model accepts racks only and needs a separate crossed-effects design.

No prior policy or selection artifact can promote this variant. It returns only
diagnostic scores and false decision eligibility, with null thresholds/alarms.
New development selection, freezing and calibration/null auditing are required
under a new protocol fingerprint before a future promotion patch. The current
fixture does none of those experiments and introduces no new random seeds.
Existing scientific definitions, eligibility defaults and held-out data remain
unchanged. Public/noise fitting and legacy research paths are byte-preserved.


## Detector dashboard output transport (14 Nov 2026)

Monitoring now consumes a separately identified saved or external detector feed.
The existing world clock and all inference algorithms remain unchanged. A saved
recording never pretends to be current-world inference; only a matching-run
external stream changes the current-world connection card, and future decision
timestamps for that world are rejected. Playback advances only the backend feed
cursor. Public GET is read only; detector controls do not move world deadlines.
Saved sessions include the loaded artifact/cursor; restored streams are recordings.

The adapter derives host risk from effect posterior mean and variance at the
fixed log(1.02) boundary. Maximum host risk is a probability-scale release score,
not a release-union probability; legacy log-score thresholds are not reused.
All displayed methods remain uncalibrated with no policy, alarms or automated
deployment decisions. Missing/preperiod/stale/disconnected states are distinct
from availability. Full host effect covariance is saved; AR noise is excluded
from risk. Prediction-only posteriors do not turn missing metrics into fresh data.

Independent and two-level rack hierarchy traces share the same replay/input
prefix. Stronger/weaker settings are separately versioned declared choices,
not tuned results. Both have positive shared prior/process covariance, with
ordered prior pair correlations. The separate nested variant's promotion gate
is unchanged. The four new algebraic scenarios use backend topology IDs and
fresh development/smoke registry slots, not final/calibration data. They are not
resource-model or detection benchmarks. Truth recipes are evaluator-only and
never imported or used for status coloring by the feed/rendering pipeline.

The runtime-bound static world snapshot was regenerated on Linux; only Python,
NumPy and platform provenance changed. No original test was edited or skipped.
The renderer and real HTTP path pass DOM tests; browser visual verification was
blocked by this execution environment and remains unverified. Automatic world
fitting/inference and compatible calibration/policy integration remain separate.


## Immutable declared release behavior (14 Nov 2026)

The operator release catalog now wraps an append-only registry of frozen records.
Release IDs and service/version pairs cannot be rebound. Exact retries preserve
first creation time. Registry assets survive world reset and restore through the
private command log; reset still recreates world resources and RNGs. Creation
wall timestamps are optional caller provenance; the backend owns simulated tick.
Content hash covers canonical behavior manifest plus optional source-byte hash.
Attachments are inert data, never imported or executed. Legacy sample/upload
commands remain compatible, but new records have explicit version and schema.

Behavior parameters, not release/filename labels, drive extra CPU work, retained
memory, response failures and post-CPU response wait. Unique behavior kinds compose
without order dependence; healthy is exclusive. Pending responses share request
slots and temporary memory with CPU queues. Completed responses include successes
and errors, while processed counts CPU completions. Retained memory grows on CPU
completion, including failed attempts, and remains bounded. Error sampling uses a
separate cohort-addressed seed domain, consuming no clock RNG streams. No retries
or packet-level delayed egress model is introduced.

Public deployment identity contains release/service/version/hash only. Public
replica snapshots expose pending counts, not internal scheduled-response tuples
or their error probabilities. The manifest/mechanisms stay in operator/private
replay/evaluator paths. Inference features and source are unchanged; a release-
label perturbation preserves every numeric/mask input. The current latency SSM
is not claimed to detect pure error-only releases. No policy or detector changes.

World artifacts and scenario member hashes are regenerated because strict replay
checks source hashes. Original statistical additive pairs and fitted research
artifacts remain byte-preserved. A direct before/after comparison retains every
original host/service field and workload RNG state for healthy/legacy CPU/memory
behavior. Existing tests are not modified. Browser composed registration succeeded;
DOM/API checks cover errors and immutability, with broader layout QA unverified.

## Fixed-cohort manual service rollout v1 — 14 November 2026

`rollouts.RolloutManager` adds uppercase lifecycle states separately from the
legacy lowercase one-shot demo deployment. Rack and class selection are crossed
constraints with three controls each. Baseline and canary phases share fixed
multinomial weights; unavailable slots drop requests rather than redirecting
traffic. Pause preserves exposure and the horizon. Promotion closes evaluation;
rollback restarts all service replicas and restores original versions/parameters.
The append-only hash-chained transition log survives reset and verified replay.
Monitoring metadata initializes at exposure; mixed monitoring minutes are skipped.
Current-run external streams are bound to the frozen cohort/epoch/horizon. No
truth-driven transition, policy, calibration or inference rewrite is introduced.
See `docs/rollouts.md` for command states, equations and cleanup semantics.

## Process memory and resource-health advisory — 15 November 2026

Add the explicit `process_memory` behavior kind/model `process-memory-v1`, using
MB per CPU-processed attempt and a separately declared MB/s background term.
Historical immutable completion-based releases keep legacy bounded semantics;
new leak/cache versions implement process lifetime, optional application cap,
pressure slowdown and OOM exit. Temporary memory remains until response completion
or drop/exit. Heap allocations are not reclaimed by changing future behavior;
rollback frees them only through its recorded restart. A failed retained batch
allocation kills that process after the tick's CPU/response work; queued and delayed
requests are counted as OOM drops. Startup allocation failure is also bounded.

Resource-health engineering criteria are versioned separately from latency
inference and report observed growth/low headroom/OOM, never code-leak proof or
an automatic deployment action. Healthy caches can warn during warmup. No SSM,
harm boundary, outcome class, calibrated policy, data role or research definition
changes. See `docs/process_memory.md` for equations, timing and compatibility.

## Separate latched policy and controller — 15 November 2026

Keep research decision/inference unchanged. Add `first_crossing` and immutable
policy artifacts, using complete eligible null maxima, strict ranks/ties, explicit
no-data sentinels and independent nonretuned validation. Five compatibility hashes
and a separate operational controller hash bind the exact workflow. New policy
hashes normalize JSON integral numbers without changing research hashes; browser
saved-run upload preserves raw bytes/numeric spelling.

The v1 automatic adapter commits before baseline in a fresh run, enforces the
exact baseline/exposure/horizon and preserves 80%/three-control eligibility.
Qualified release alarms pause with a latched reason; rollback defaults manual
and explicit opt-in acts on a later tick. Observed incidents/resource guardrails
have distinct pause-only reasons. Complete eligible observations and a declared
risk ceiling are required for a policy-based promotion. No known injection truth
or absence of data drives these decisions. Legacy manual promotions remain
unmonitored operator overrides with no healthy claim.

The actual example is conditional Gaussian/public-metric calibration with a new
generator identity; it is refused by the physical world. Contract-test synthetic
statistics exercise HTTP/actions but are not scientific world calibration data.
No harm boundary, outcome definition, existing research gate, posterior engine,
comparator, dataset role or prior frozen artifact is redefined. Source/bookkeeping
iterations retain retired policy hashes/validation seed ranges; final validation
uses a fresh registry family, with no statistical retuning from validation.

## Integrated dashboard boundary — 15 November 2026

The UI reuses the deterministic balanced cohort selector (one/two per rack), with exact host IDs in a nonmutating backend preview; it does not introduce arbitrary cohort editing or change protocol/inference definitions. New console projections and checkpoint/journal storage live outside the engine. Full receipts remain bounded to 256, with a compact 10000-ID journal retaining duplicate protection across cache eviction and restart. Imported replay identity now follows the saved engine. Existing calibration artifacts retain strict source/runtime compatibility; no recalibration or benchmark is implied by this UI change. See [integrated_dashboard.md](integrated_dashboard.md).

## Truth-separated replay evaluation v2 — 15 November 2026

The Mac workspace's unarchived evaluator/cache was unavailable in the restored
Linux workspace. Rebuild this extension from the preserved integrated-dashboard
ZIP, refit on new development identities and use fresh calibration/validation
indices. Do not import historical conversation results into this run's tables.
Preserve prior numerical engines, original outcome definitions and original tests.
Refresh only the recorded dashboard's Python/NumPy/platform manifest fields for
the current runtime; retain the original Mac fixture separately.

The public comparison adapter never imports evaluator truth. Producers write
separate public/private files, and outcome joins are evaluator-only. Statistical
latent harm retains the strict 2%/15-minute definition and original metrics.
World release attribution uses a separately named offline same-exogenous
completion-latency contrast; infrastructure operator targets are separate.
Missing targets, unmonitored hosts, queue/routing interference and abstentions
remain explicit. No online counterfactual is asserted.

All ablations receive healthy nuisance refits when needed, development selection
and new method/endpoint thresholds. The no-effect nuisance likelihood is unchanged
for persistence-off, so only effect dynamics/selection need changing there.
Selection uses all eligible host-windows, never the true affected count.
The separately versioned nested offline adapter does not activate production policy.

The new release-null mixture audit cannot substitute for the governing per-family
gate. Final-test materialization deliberately remains disabled pending that gate,
even if some mixture audit statuses pass. No definitions or original gate changed.
Saturated-score and conservative tied-score failures remain negative results.

Runtime measurements distinguish tracked allocations from RSS and VM rendering
from real browser layout/paint/input. An initially repeated API measurement reused
persisted command identities and measured cached receipts; retain it as invalid.
The corrected benchmark uses a fresh runtime directory and asserts exactly one
engine tick per measured API step, with a regression test for duplicate receipts.


## Lightweight distribution cleanup — 15 November 2026

At the user's request, remove generated historical run/telemetry/result data from the current branch and replacement ZIP. Preserve all source/tests/configs, fitted artifacts, policy/validation bindings and the exact small files referenced by runtime views and tests. Keep compact audit summaries without claiming that absent raw datasets are still bundled. Add ignore rules for regenerated runs. This is a normal deletion commit, without history rewriting; old data remain in the full-import commit. See `lightweight_distribution.md` and `distribution_manifest.json`.
