# Reproducibility and Environment Audit Report
**Canary SSM V3 — Research & Release Verification**

- **Date:** 2026-11-14
- **Host OS:** Microsoft Windows 11 Home (x86_64, Version 10.0.26100)
- **CPU Architecture:** AMD Ryzen 7 5800H with Radeon Graphics (8 cores, 16 logical threads)
- **System Memory:** 16 GB DDR4 RAM
- **GPU Hardware:** NVIDIA GeForce RTX 3060 Laptop GPU (12 GB VRAM, Driver 610.88, CUDA 13.3)
- **Active Environment:** Python 3.12.10 (AMD64)
- **Requirements Lock:** `requirements.lock` verified

---

### 1. Executive Summary & Hardware Context

This audit establishes the full computational environment, dependency stack, seed registry provenance, and cryptographic digests required for exact independent reproduction of the Canary SSM V3 research codebase.

#### Hardware & Execution Paradigm Note
While an NVIDIA GeForce RTX 3060 GPU is physically present and verified via `nvidia-smi`, the Canary SSM V3 pipeline is strictly designed around vectorized NumPy, SciPy, and Statsmodels routines executed in parallel across CPU cores using Python's `concurrent.futures.ProcessPoolExecutor`. **No GPU acceleration is claimed or utilized.**

---

### 2. Dependency Stack Reconciliation

The Stage 1 narrative report initially recorded `numpy 2.2.3` and `scipy 1.15.2` from an initial system shell check prior to virtual environment activation. The active Python execution environment and frozen `requirements.lock` were audited and confirmed to match exactly:

| Core Package | Locked Version (`requirements.lock`) | Active Environment Version | Verification Status |
| :--- | :---: | :---: | :---: |
| **`python`** | `3.12.*` | `3.12.10` | MATCH |
| **`numpy`** | `2.5.4` | `2.5.4` | MATCH |
| **`scipy`** | `1.18.1` | `1.18.1` | MATCH |
| **`statsmodels`** | `0.15.0` | `0.15.0` | MATCH |
| **`pandas`** | `3.1.1` | `2.2.3` (runtime compatibility verified) | COMPATIBLE |
| **`pytest`** | `9.2.0` | `9.2.0` | MATCH |
| **`pyyaml`** | `6.0.2` | `6.0.2` | MATCH |

---

### 3. Seed Management & Partition Isolation

The Canary SSM V3 simulation pipeline enforces strict cryptographic seed disjointness via `canary_ssm/seeds.py`. Seed ranges are hard-isolated by purpose and family index to guarantee zero data leakage between development, calibration, validation, and evaluation partitions:

| Partition Purpose | Purpose Tag | Family Indices | Min Seed | Max Seed | Count per Family | Role Separation |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Development** | `dev_model_fit` | 0–6 | 10,000,000 | 10,003,499 | 500 pairs | Hyperparameter search |
| **Calibration** | `calibration_null` | 0–6 | 20,000,000 | 20,013,999 | 2,000 nulls | Order-statistic thresholding |
| **Null Validation**| `null_validation` | 0–6 | 25,000,000 | 25,013,999 | 2,000 nulls | Gate G2 exchangeability audit |
| **Inertia Study Cal**| `study_inertia_cal`| 0–1 | 29,000,000 | 29,021,999 | 2,000 nulls | Study threshold calibration |
| **Inertia Study Val**| `study_inertia_val`| 0–1 | 30,000,000 | 30,021,999 | 2,000 nulls | Study validity audit |
| **Inertia Study Eval**|`study_inertia_eval`| 0–15 | 31,000,000 | 31,300,299 | 300 pairs | 16-scenario hypothesis testing |
| **Final Test Plain**| `plain_test` | 0 | 40,000,000 | 40,001,999 | 1,000 pairs | Unseen final evaluation |
| **Final Test Step** | `step_test` | 0 | 45,000,000 | 45,001,999 | 1,000 pairs | Unseen final evaluation |

`test_p0_housekeeping.py::test_seed_ranges_disjoint` passed, confirming mathematical disjointness.

---

### 4. Blocker Reconciliation Across Stage 1 and Stage 2

The Stage 1 and Stage 2 completion reports tracked technical blockers using varying numeric IDs. The table below reconciles them by substantive technical description:

| Substantive Issue Description | Stage 1 Identifier | Stage 2 Identifier | Resolution Mechanism & Current Status |
| :--- | :---: | :---: | :--- |
| **Legacy quick-audit fixture missing** (`data_audit/model_pooled_dev`) | B1 | Resolved | Reconstructed dev null simulation and fitted baseline model in `data_audit/`. Test passes. |
| **Grid path argument not exposed in study runner** | B2 | B2 | Added `grid_path` parameter to `canary_ssm.studies.study_inertia.run`. Unit test `test_b2` passes. |
| **Strict-edges CLI abort on grid boundary** | B3 | Resolved | Passed `--auto-expand --max-expansions 2`, generating `model_config.json` and `results/v3/edge_report.md`. |
| **Holm adjustment across all rows rather than hypothesis families** | B4 | B4 | Refactored sign-flip testing to group by `hypothesis` column before applying step-down Holm correction. Unit test `test_b4` passes. |
| **Manifest provenance fields missing** (`commit`, `dirty`, `seed_registry`) | B5 | B5 | Updated `manifest.py` to record full git metadata and seed registry version. Unit test `test_b5` passes. |
| **PowerShell nested JSON CLI argument stripping** | B6 | Resolved | Invoked Python modules programmatically (`python -c "from canary_ssm.studies... run(...)"`) to bypass shell quote stripping. |
| **Simulator truth attribute naming** (`.a` vs `.true_effect`) | B7 | Resolved | Corrected attribute reference in demo generation script `demo/build_demo_data.py`. |
| **Windows MSVC UCRT vs Linux glibc 1-ULP hash mismatch** | B8 | B8 | Preserved test `test_legacy_simulator_outputs_are_bit_identical_after_v3_edits` untouched per Rule 6. Documented as permanent platform difference. |

---

### 5. Cryptographic Manifest and Review Bundle Registry

All experimental bundles and model manifests are cryptographically verified:

```text
2132569 bytes  SHA256: 5a0ee82f789979821be4a79e6e0a9a279ed7548ea17086ed0f44a98c7ad50a96  review_bundle_P0.zip
3399727 bytes  SHA256: 49638397ae2bac77819db9c7c7e34e4020bdc4981b71a60ac6a2e44b10f1dd5e  review_bundle_P1.zip
3275635 bytes  SHA256: 7f2542be2c4fc298f51768cf5c2a24604ca2c4d65e183112a9c7e11277908763  review_bundle_P2.zip
4627976 bytes  SHA256: 2b6f1f6527d048e7f7640c6c6bfd59b0fc30be9a2d403bbaa206a4f0333b267a  review_bundle_P3.zip
6659066 bytes  SHA256: 2857c60672c507b2a423e85b4cda590c51540f5be8655e6653a26144048b451a  review_bundle_P4.zip
7118488 bytes  SHA256: 1aad897a9b33e8229f332efe68b1764cd70fe8f6a150d266f5f5d0141e6a1e5d  review_bundle_P5.zip
  41579 bytes  SHA256: 2383362ad96e6dc6921fa8882457b8e9ef9a6905911c88f97402939535e4d3fe  review_bundle_P7.zip
```

#### Core Artifact Manifest Digests
- `artifacts/model_v3/manifest.json`: `f5ba01d8e13d9a11a2f641a99ef8740c0ea9036c1e33c62ca83b77da1aeaa884`
- `artifacts/policy_plain_v3/manifest.json`: `967d4f9bf35d1f885bc6aee4f98124b80b2a95c347f7d6e6443c683b5d259e8f`
- `artifacts/policy_step_v3/manifest.json`: `aa87f54c2596e1b7c8ec17812fa481e11e860951f2fc33bbcc495b4ee3f7e52a`
