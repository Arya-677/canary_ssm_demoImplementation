# ANTIGRAVITY SPEC V3 — Canary SSM: what to do, what not to touch, what evidence to produce

Authors: research-architect/reviewer pass (Claude) over the repository as shipped (`canary_ssm_demoImplementation-main`).
Audience: Google Antigravity (implementer). **Read `AGENTS.md` Part 0 first; every rule there still holds.**
The Master Implementation Prompt was NOT available to the reviewer (only the Addendum). Wherever the Addendum refers to
"V2.1 calibration corrections", the reviewer checked the repository instead; the status is in §2.

---------------------------------------------------------------------------------------------------------------------
## 0. How to work (read once)
1. The thinking is done here. Implement exactly what a work package (WP) says; if a WP is impossible or contradicts the
   repository, STOP, write the problem into `docs/V3_BLOCKERS.md` (facts only) and continue with the next independent WP.
2. Never run anything that touches the **test** role (`data/*/test`, `evaluate`) until Phase 4. Never tune, choose m, choose
   thresholds or choose scenarios after looking at validation/test numbers.
3. Do not invent numbers. Every number in a report must come from a CSV/JSON under `results/` with a manifest.
4. After each phase: `python scripts/make_review_bundle.py --phase <P> --results <dirs> --pytest-log pytest.log`, then
   stop and hand the zip back to the reviewer (§9). Do not start the next phase until told "GO Pn".
5. Windows note: if `pytest` reports "disk budget" RuntimeErrors on a healthy disk, set `CANARY_MAX_DISK_USED=0.99`
   (env override added in V3; the default 0.90 is unchanged). Report it, do not edit the guard further.

---------------------------------------------------------------------------------------------------------------------
## 1. What was already in the repo (preserve; do NOT rebuild)
P0 housekeeping, P1 (grid protocol, 5-fold CV + 1-SE, edge detection), G2 exact Beta-Binomial validity gate, B=2000 order-
statistic calibration, role-separated seeds, regime-aware policy schema v2, 14 tuned detectors in `artifacts/model_v2`,
advisory replay, studies exp1–exp8, 107 tests. Hierarchical SSM = class effect g_c + sum-zero local deviations, both AR(1),
plus per-host AR(1) nuisance, workload adjustment with factor-uncertainty covariance, exact Kalman filter.

## 2. Status of the V2.1 / Addendum requirements against the actual repo (reviewer's verification)
| Requirement | Verified status |
|---|---|
| Calibration at B≥2000 with exact order statistic, Beta-Binomial audit | Present (`decision.calibrate_threshold`, `metrics.betabinom_validity`, gate G2). Not re-implemented. |
| Disjoint seed blocks, no test leakage | Present (`seeds.py`). V3 appends 3 blocks; test enforces disjointness. |
| Hierarchical partial pooling (sum-zero) | Present and mathematically correct (tests added: balanced, 8/2, 9/1, singletons). |
| **Cross-level inertia (Addendum B2)** | **Absent.** Group and local levels are independent AR(1) processes with the *same* rho (grid ties `rho_g=rho_h`); `sd_h_ratio` fixed 1.0. |
| Decision hysteresis calibrated separately | **Absent as a calibrated policy** (only `advisory_replay`, uncalibrated, for flicker study). V3 adds exact calibration (§3 WP-D). |
| Classical baselines GLR/CUSUM with matched hysteresis | Detectors exist (`BASELINES`) but **`artifacts/model_v2` was fitted before P1b**: `glr_window, ar_cusum, sparse_mix_glr, bocpd, msprt, mw_judge, wmean` have NO tuned params there. P2 cannot run until refit (Phase 1). |
| Slow/progressive, recovery, improvement, periodic workload, spikes | Ramp existed; others added in V3 (§3 WP-B). |
| Control contamination, label error, heavy tails, missingness | Present; combine them via config only. |
| Multivariate telemetry | **Not possible without schema change** (Rollout has one latency matrix + request_count; no CPU/error channels). Deferred to Phase 6 by the Addendum's own ordering. |
| Different workload distributions for canary vs control | **Not representable**: one shared measured workload vector `x`. Needs schema change; deferred, documented. |

## 3. Reviewer's scientific findings (facts about THIS repo; each is testable)
F1. Tuned `hier_ssm` sits at rho=0.999, sd_g=0.000125 (grid edge after expansion) and `hier_rw` is within ~0.5 % of it on dev
    (13.62 vs 13.68). The tuned "AR hierarchy" is effectively a near-constant-shift detector. The simulator's dominant effect
    shape is an abrupt constant step, which a random-walk-like state matches; so "persistence helps" is partly *generative
    alignment* (AGENTS I-16), not evidence about real telemetry. Ramp / recovery / mixed-speed scenarios are required before
    any inertia claim.
F2. Consequence: a near-random-walk effect state **recovers slowly after a regression ends** (smoke run, not a result: recovery
    delays of tens of minutes). Recovery delay and time-in-PAUSE are therefore primary stability metrics, not extras.
F3. Partial-pooling *strength* was never tuned: `prior_sd` is shared by group and local coordinates and `sd_h_ratio` only scales
    innovations. The classical shrinkage parameter (local prior SD / group prior SD) did not exist. V3 adds it as `prior_h_ratio`.
F4. Alternative B (fast + slow effect components) is **not identifiable against the existing per-host AR(1) nuisance** (phi_e≈0.6
    is already a fast latent component observed with the same noise). Implementing it would double-count; it is documented,
    not built (`docs/INERTIA_MODEL_DESIGNS.md`).
F5. Alternative A as written (group transition driven by a nonlinear function of lower-level *posterior* evidence) reuses the
    data twice and is not a generative model; its only linear-Gaussian form is a VAR coupling that reduces to second-order
    dynamics. Not built. Alternative C (state-dependent Q) is not exact Kalman. Not built.
F6. `lambda * sum ||x_t - x_{t-1}||^2` is exactly the MAP form of a Gaussian random-walk prior (innovation variance proportional to 1/lambda) —
    the same model as `hier_rw`; building it would duplicate an existing method under a new name (Addendum B4 answered).
F7. Tooling: duplicated line in `Models.run` (harmless, removed); disk guard computed free space with reserved blocks (env override).

## 4. What V3 changed already (done by the reviewer, tested; Antigravity must NOT redo or rewrite)
See `CHANGELOG_V3.md` for the exact file list. Summary: `hierarchy.TwoScaleParams` + `prior_scale_vector`; `inertia.py` and
`configs/grids_inertia.yaml` (28 candidates ≤ hier_ssm's 42; nests hier_ssm); `decision.persist_score / calibrate_persistence /
replay_policy`; simulator knobs (all defaults bit-identical to legacy, proven by golden hashes in `tests/data`);
`studies/study_inertia.py` (+ CLI `study inertia --opts '{json}'`); `configs/inertia_scenarios.yaml`; seeds blocks;
`scripts/partial_pooling_audit.py`, `scripts/make_review_bundle.py`; 31 new tests in `tests/test_v3_changes.py`.
Everything above was smoke-tested at tiny scale only. **No experimental conclusion exists yet.**

---------------------------------------------------------------------------------------------------------------------
## 5. Phases, work packages, acceptance criteria

### Phase 0 — Baseline verification (no code changes)
WP-0.1 `pip install -e ".[dev,report]"`, `python -m pytest -q`. Expected: all pass except tests that need generated data
(`test_experiment7_legacy_reproduction` needs `data/` + artifacts; run the pipeline first if it fails with FileNotFound).
WP-0.2 Confirm `git diff` only shows files in `CHANGELOG_V3.md`.
**Accept:** pytest summary line pasted; 0 failures other than documented data-dependent ones (list each with reason).

### Phase 1 — Refit including every baseline (so P2/P3 comparisons are possible)
WP-1.1 Generate dev/calibration/null_validation roles for the plain regime exactly as `tasks.sh plain-pipeline` (skip `evaluate`).
WP-1.2 `fit --data data/plain/dev --out artifacts/model_v3 --methods all --strict-edges --auto-expand --cache-dir cache`.
        Verify `model_config.json["methods"]` contains `glr_window, ar_cusum, sparse_mix_glr, bocpd, msprt, mw_judge, wmean`
        and all SSMs/ablations. If `--methods all` omits P1b baselines, pass the explicit list (see `BASELINES`) — do not edit grids.
WP-1.3 Candidate budget table: write `results/v3/budget_parity.csv` (method, n_candidates after pruning). hier_ts must be ≤ hier_ssm.
**Accept:** `model_config.json` lists tuned params for all methods; no unreviewed edge hit (each edge flag listed in
`results/v3/edge_report.md` with the one-step expansion decision); `fit_failures == 0`.

### Phase 2 — Core benchmark validity (existing V2 questions, unchanged protocol)
WP-2.1 calibrate + validate-null on `artifacts/model_v3` (plain, then step regime pipelines per `tasks.sh`). NO `evaluate` yet.
**Accept:** G2 gate passes for every method at n_null=2000 (`bb_pvalue_two_sided > 0.001` AND the existing gate rules); any method
failing is reported, not tuned away.

### Phase 3 — Inertia / hysteresis experiment (the research question)
Preregistered in `docs/PREREGISTRATION_V3.md` (read it; do not edit after Phase 3 starts).
WP-3.1 Tune hier_ts: generate dev role if absent, then `python -m canary_ssm.cli study inertia --model artifacts/model_v3 ...`
        with `--opts '{"dev_dir":"data/plain/dev","tune":true}'` (the study tunes hier_ts on dev only, 5-fold CV + 1-SE).
        Edge protocol: if `hier_ts_params.json["edge_flags"]` has a true flag on an axis with >1 value, extend THAT axis one step in a
        NEW grid file version, rerun, keep both. Max two expansions (same rule as P1).
WP-3.2 Full run: `n_null=2000`, `n_harm=300` (use 500 if wall-time allows), methods
        `indep_ssm hier_ssm hier_ts adj_cusum glr_window`, `persist_m [1,3,5,10,15]`, all 16 scenarios, `workers=<cores-1>`.
WP-3.3 Add `docs/V3_RESULTS_INERTIA.md` generated ONLY from the CSVs: tables + the 5 preregistered verdicts (H1–H5) as
        SUPPORTED / NOT SUPPORTED / INCONCLUSIVE using the decision rules in the preregistration. No narrative beyond the rules.
**Accept:** (a) `table_calibration_validity.csv` shows every (regime, method, m) cell with bb_p > 0.001; (b) every scenario cell
has n_pairs=n_harm; (c) paired-contrast table contains C1–C4 for every event scenario; (d) manifest records grid versions,
seeds, hashes; (e) report states which hypotheses failed. Negative results are acceptable and expected to be reported.

### Phase 4 — Final test evaluation (only after reviewer says "GO P4")
Run `evaluate` once per regime on the test role with frozen policy. Never rerun after seeing results.

### Phase 5 — Robustness & combined scenarios (Addendum F5), uses existing configs
WP-5.1 Create `configs/v3_combined.yaml` families: regression+step, regression+heavy tail (df 3), regression+missing 20 %,
        regression+contamination 20 %, regression+label error 30 %. Reuse `study_inertia` with `--opts '{"scenario_file": ...}'`.
**Accept:** table of FAR/power per combination; calibration failures listed (expected for distribution shifts — report, do not fix).

### Phase 6 — Multivariate prototype (ONLY after Phases 1–3 are accepted and reviewed)
Spec: `docs/MULTIVARIATE_PROTOTYPE_SPEC.md`. Requires a schema extension; do not start without "GO P6".

### Phase 7 — Documentation & AFML report inputs
WP-7.1 Fill `docs/RELATED_WORK_MATRIX.md` verification column from primary sources (title, authors, year, venue, DOI/URL).
        Anything not verifiable stays "UNVERIFIED". WP-7.2 Update `docs/RESEARCH_CONTRIBUTION_MATRIX.md` "status" column from
        Phase 3 verdicts. WP-7.3 Write the two novelty statements (G4) from verdicts only.

---------------------------------------------------------------------------------------------------------------------
## 6. File-by-file roadmap (who touches what)
| File | Status | Instruction |
|---|---|---|
| `canary_ssm/hierarchy.py` | DONE | `TwoScaleParams`, `prior_scale_vector`. Do not change filter math. |
| `canary_ssm/inertia.py`, `configs/grids_inertia.yaml` | DONE | Only grid *extension* per edge protocol, as new version. |
| `canary_ssm/decision.py` | DONE | Do not alter legacy functions; V3 functions are appended. |
| `canary_ssm/simulate.py` | DONE | New knobs default to legacy. Never change default behaviour; `tests/data/legacy_sim_hashes.json` guards it. |
| `canary_ssm/studies/study_inertia.py` | DONE (smoke) | Bug fixes only, each with a test. Do not change calibration logic. |
| `canary_ssm/experiments.py` | 3 tiny edits DONE | Do not register hier_ts in `ABLATIONS`/`SSMS` (would change method counts and legacy gates). |
| `configs/inertia_scenarios.yaml` | DONE | Frozen once Phase 3 starts. |
| `scripts/*` | DONE | Use as is. |
| `tests/test_v3_changes.py` | DONE | Add tests, never weaken. |
| `docs/*` | partly DONE | Fill "UNVERIFIED"/"status" cells only where this spec says. |
| everything else | NOT TO CHANGE | Especially `kalman.py`, `factor.py`, `preprocess.py`, `metrics.py`, `schema.py`, `seeds.py` existing ranges. |

## 7. Mathematical decisions needing independent derivation / external verification (human or second tool)
1. Exactness of persistence calibration: s_m(t)=min of last m scores; its null maximum is exchangeable ⇒ order-statistic bound
   valid. Reviewer's proof is in `MATHEMATICAL_MODEL_AUDIT.md §5`; an independent check is the statistical test
   `test_persistence_calibration_is_exactly...`. Ask a second reader to confirm the proof.
2. The Kalman posterior vs direct Gaussian conditioning (done in tests for 3 class layouts × 3 parameterisations, with missing data).
   Still unverified: factor-adjustment covariance `V_t = diag(v²)+λλ'U_t` and ignored uncertainty of beta/loadings.
3. The release score `max_i P(a_i>κ)` uses host marginals; its relation to the joint event probability is not derived. Do not
   change; document in the audit.
4. Identifiability of g_c vs local deviation under label errors (partial-pooling audit CSV shows prior leakage; the *posterior*
   behaviour under mislabels is an experiment in Phase 5, not a derivation).

## 8. Things Antigravity must NOT do
- Do not implement Alternatives A/B/C, a 3rd latent "deployment" state, a regulariser-penalty variant, neural baselines or
  multivariate observation models before the reviewer's "GO".
- Do not retune any non-hier_ts method, change KAPPA/D_MIN, edit existing seed ranges, edit existing grids, or lower B/n.
- Do not report a mechanism as a "contribution" unless preregistered rule H2 or H3 is SUPPORTED.
- Do not produce production-readiness claims.

## 9. Review protocol (how results come back to the reviewer)
After each phase run `python scripts/make_review_bundle.py --phase P3 --results results/study_inertia results/v3 --pytest-log pytest.log`
and upload `review_bundle_P3.zip` plus the filled `REVIEW_REQUEST.md` (facts only). The reviewer will answer with: (i) verdict per
acceptance criterion, (ii) defects with file/line, (iii) "GO Pn" or a fix list. Antigravity must not self-approve a phase.

## 10. Paste-ready kickoff prompt for Antigravity
> Open `docs/ANTIGRAVITY_SPEC_V3.md` and `AGENTS.md`. Execute Phase 0 only. Do not modify code. Report exactly as §9 requires.
> After the reviewer replies "GO P1", execute Phase 1, and so on. Never skip a phase, never edit frozen files, never invent numbers.
