# V3 Pre-Run Technical and Scientific Blockers

**Date:** 14 November 2026  
**Audience:** Antigravity (implementer) and Research Reviewer  
**Status:** Baseline audit completed during Stage 1 / Phase 0.

The following source-level discrepancies and technical blockers were identified during the Stage 1 inspection of the V3 codebase, companion PDFs, and initial test suite. Per Part 0 rules, no frozen definition, calibration gate, or test has been modified to bypass these items.

---

### B1 — Gate G2 Beta-Binomial Validity Threshold Mismatch
- **Locations:** `docs/ANTIGRAVITY_SPEC_V3.md` (§5 Phase 2 / WP-2.1), `docs/Canary_SSM_Change_Plan.pdf` (revision 3, Part 0 / WP-C3), `canary_ssm/report.py` (`BB_P_FLOOR = 0.01`).
- **Conflict:** The V3 spec text states `bb_pvalue_two_sided > 0.001` for G2 acceptance. However, `docs/Canary_SSM_Change_Plan.pdf` (revision 3) is designated as the governing plan and specifies two-sided Beta-Binomial $p \ge 0.01$ and achieved false-alert rate $\le 0.075$ with a Binomial multiplicity calculation. The codebase (`canary_ssm/report.py`) implements `BB_P_FLOOR = 0.01` and `MAX_RATE_G2 = 0.075`.
- **Handling:** Governed by revision-3 Change Plan. Do not relax `report.py` to 0.001. The stricter threshold ($p \ge 0.01$) is retained for Phase 2 validity.

---

### B2 — Missing `grid_path` Parameter Forwarding in `study_inertia.run`
- **Location:** `canary_ssm/studies/study_inertia.py` (`run()` vs `tune_hier_ts()`).
- **Conflict:** `tune_hier_ts` accepts an explicit `grid_path: Path | None = None` parameter to enable tuning over versioned expanded grids (WP-3.1 edge protocol). However, `study_inertia.run` accepts `**kwargs` and calls `tune_hier_ts` without passing `grid_path`.
- **Handling:** Propose the smallest backward-compatible parameter forwarding (`grid_path=None` in `study_inertia.run` passed to `tune_hier_ts`) and accompany it with a focused unit test before Phase 3 full execution.

---

### B3 — Fixed `prior_sd = 0.005` in `configs/grids_inertia.yaml`
- **Locations:** `configs/grids_inertia.yaml`, `artifacts/model_v2/model_config.json`, `canary_ssm/inertia.py` (`nests_hier_ssm`).
- **Conflict:** The shipped inertia grid fixes `prior_sd` at 0.005 because the legacy `model_v2` hierarchical fit selected 0.005. Phase 1 refits `hier_ssm` into `artifacts/model_v3`. If the refitted `model_v3` selects a different `prior_sd`, the shipped `grids_inertia.yaml` will fail `nests_hier_ssm`.
- **Handling:** Verify `nests_hier_ssm(ts_candidates, model_v3 hier_ssm params)` immediately after Phase 1 refit. If false, stop and request reviewer approval for a new versioned grid file restoring nesting.

---

### B4 — Holm Multiplicity Adjustment Scope in `study_inertia.py`
- **Locations:** `canary_ssm/studies/study_inertia.py` (`run()`), `docs/PREREGISTRATION_V3.md`.
- **Conflict:** `docs/PREREGISTRATION_V3.md` specifies that Holm step-down multiplicity correction must be performed within each hypothesis family (H1, H2, H3, H5). Currently, `study_inertia.py` applies `holm_adjust` globally across all rows of the contrast table in one pass.
- **Handling:** Before Phase 3 full execution, map contrast rows (C1–C4) to hypothesis families (H1–H5), implement family-wise Holm adjustment, and verify with an independently computed unit test.

---

### B5 — Study Manifest Missing Explicit Seed Ranges and Grid/Scenario Hashes
- **Locations:** `canary_ssm/studies/study_inertia.py`, `canary_ssm/manifest.py`.
- **Conflict:** Phase 3 acceptance requires the study manifest to record exact seed ranges for all three study purposes (`study_inertia_cal`, `study_inertia_val`, `study_inertia_eval`) and SHA-256 hashes for `grids_inertia.yaml` and `inertia_scenarios.yaml`. The current `study_inertia.py` manifest call site only passes model-level metadata.
- **Handling:** Add the missing provenance fields to the manifest construction call in `study_inertia.py` before Phase 3, backed by a manifest completeness test.

---

### B6 — Missing Historical Git History in Supplied Archive
- **Location:** Repository root.
- **Conflict:** The supplied ZIP contained no `.git` directory. Consequently, `git diff` cannot verify the historical transition from V2 to V3 against `CHANGELOG_V3.md`.
- **Handling:** Initialized Git and created the baseline commit `e6585ba8c7648105e119befe434c7e80f37e98ed` (`"Baseline: supplied Claude V3 handoff snapshot"`). Future changes will be tracked against this baseline.

---

### B7 — Convenience Pipeline Wrappers Touch Test Data and Evaluate
- **Locations:** `tasks.sh` (`plain-pipeline`, `step-pipeline`, `smoke`), `tasks.ps1`.
- **Conflict:** Convenience scripts run `simulate --role test` and `evaluate` end-to-end. Running these scripts prior to Phase 4 would violate the data-role firewall.
- **Handling:** Prohibit running `tasks.sh plain-pipeline`, `tasks.sh step-pipeline`, or `scripts/smoke.sh` prior to Phase 4. Use only explicit subcommand invocations (`simulate --role dev`, `fit`, `calibrate`, `validate-null`).

---

### B8 — Simulator Golden Hash Cross-Platform ULP Mismatch
- **Locations:** `tests/test_v3_changes.py` (`test_legacy_simulator_outputs_are_bit_identical_after_v3_edits`), `tests/data/legacy_sim_hashes.json`.
- **Conflict:** `test_legacy_simulator_outputs_are_bit_identical_after_v3_edits` compares SHA-256 digests of raw IEEE 754 float64 arrays (`tobytes()`) across 24 configurations. The golden hashes were recorded in a Linux environment (Claude review sandbox with glibc). On Windows 11 with MSVC/UCRT, transcendental functions (`np.sin` in diurnal workload and `np.exp` in request counts and latency) exhibit standard 1-ULP numerical differences, causing binary byte mismatches while numerical properties remain identical.
- **Handling:** Per AGENTS.md Rule 6, the test was NOT modified, weakened, or deleted in Phase 0. Documented as an environment-dependent test failure to be formally resolved with a tolerance-based numerical comparison or platform-aware hash fixture.
