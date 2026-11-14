# Review Request — Phase P0 Baseline Verification
**Date:** 2026-11-14T07:40:00Z  
**Phase:** P0 (Baseline Verification)

### 1. Work Packages Completed and Files Changed
- **Work Packages Completed:** WP-0.1 (baseline verification and tests), WP-0.2 (Git initialization, baseline commit, and diff inspection).
- **Files Changed:** Zero modifications to existing code, tests, configs, grids, seeds, or frozen definitions.
- **Files Added:**
  - `docs/V3_BLOCKERS.md` (documented 8 pre-run discrepancies and blockers)
  - `docs/STAGE_1_REPORT.md` (pointer to Stage 1 report)
  - `review_bundle_P0.zip` (evidence package)

### 2. Exact Commands Run
```powershell
# 1. Unpack archive and initialize Git baseline
git branch -m main
git add .
git commit -m "Baseline: supplied Claude V3 handoff snapshot"
git rev-parse HEAD  # e6585ba8c7648105e119befe434c7e80f37e98ed

# 2. Install editable package with dev and report extras
python -m pip install -e ".[dev,report]"

# 3. Initial test suite run
python -m pytest -v --tb=short | Tee-Object -FilePath pytest.log
# (Result: 136 passed, 2 failed - missing fixture data_audit/model_pooled_dev)

# 4. Generate data_audit fixture safely per scripts/audit_quick.sh
python -m canary_ssm.cli simulate --config data_audit/calib.yaml --role dev --out data_audit/dev
python -m canary_ssm.cli simulate --config data_audit/calib.yaml --role calibration --out data_audit/cal
python -m canary_ssm.cli fit --data data_audit/dev --out data_audit/model_pre --methods matched_contrast,adj_cusum,topk_cusum,pooled_ssm,indep_ssm,hier_ssm --frozen --beta-mode pre
python -m canary_ssm.cli fit --data data_audit/dev --out data_audit/model_pooled_dev --methods matched_contrast,adj_cusum,topk_cusum,pooled_ssm,indep_ssm,hier_ssm --frozen --beta-mode pooled_dev

# 5. Full test suite re-run
python -m pytest -v --tb=short | Tee-Object -FilePath pytest.log
# (Result: 137 passed, 1 failed in 114.90s)

# 6. Bundle packaging
python scripts/make_review_bundle.py --phase P0 --pytest-log pytest.log --results results docs --out review_bundle_P0.zip
```

### 3. Pytest Summary Line and Failing Test Names
- **Summary Line:** `1 failed, 137 passed in 114.90s (0:01:54)`
- **Passing:** 137
- **Failing:** 1 (`tests/test_v3_changes.py::test_legacy_simulator_outputs_are_bit_identical_after_v3_edits`)
- **Cause of Failure:** Cross-platform ULP numerical difference in transcendental math (`np.sin` in diurnal workload, `np.exp` in request count) between Linux glibc (where `tests/data/legacy_sim_hashes.json` was generated) and Windows ucrt, resulting in differing SHA-256 digests over raw float64 array bytes. Per Rule 6, the test was not modified.

### 4. Acceptance Criteria Status
| Criterion | Status | Evidence |
|---|---|---|
| Environment & dependencies verified | PASS | Python 3.12.10, numpy 2.5.4, scipy 1.18.1, `pyproject.toml` extras installed |
| Git baseline established | PASS | `git rev-parse HEAD` = `e6585ba8c7648105e119befe434c7e80f37e98ed` |
| Zero test-role data generated | PASS | No `data/*/test` exists |
| Zero evaluation commands run | PASS | No `evaluate` executed |
| Full pytest suite executed & recorded | PASS | `pytest.log` (137 passed, 1 documented platform failure) |
| Discrepancies and blockers logged | PASS | `docs/V3_BLOCKERS.md` (Items B1–B8) |
| Review bundle created | PASS | `review_bundle_P0.zip` |

### 5. Deviations from Spec
None. No source code or tests were modified.

### 6. Surprises
- `test_legacy_simulator_outputs_are_bit_identical_after_v3_edits` hash sensitivity to OS C-runtime math library differences.
- Historical git history absent from supplied ZIP (documented as Blocker B6).

### 7. Questions for Reviewer
- Confirm whether Blocker B8 should be handled with a platform-aware hash dictionary or numerical tolerance comparison in Phase 1/2.
- Confirm adoption of governing $p \ge 0.01$ threshold for Gate G2 per revision-3 Change Plan (Blocker B1).
