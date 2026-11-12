# Design decisions, deviations, and gaps

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
