# REPRODUCIBILITY MANIFEST: CANARY SSM V3 PAPER-READY PACKAGE

- **Release Date**: 2026-11-15
- **Branch**: `v3` / `research-release-v3` / `external-validation-v1`
- **Target Architecture**: AMD64 / x86_64
- **Operating System**: Windows 11 Version 10.0.26100 (UCRT runtime)
- **Python Runtime**: Python 3.12.10 (tags/v3.12.10:9815048)
- **Key Dependencies**:
  - `numpy`: 2.5.4
  - `scipy`: 1.18.1
  - `statsmodels`: 0.15.0
  - `pandas`: 2.2.3
  - `matplotlib`: 3.10.1
  - `pytest`: 9.2.0

---

## 1. Reproduction Commands

### A. Run Full Software Verification Suite
```powershell
pytest tests/ -v
```

### B. Run Deterministic Comparator Semantics Fixtures
```powershell
pytest tests/test_comparator_semantics.py -v
```

### C. Run Model Diagnostics
```powershell
python scripts/run_model_diagnostics.py
```

### D. Run Confirmatory Benchmark
```powershell
python scripts/run_external_benchmark.py
```

### E. Regenerate Publication Tables and Figures
```powershell
python scripts/make_publication_tables.py
python scripts/make_publication_figures.py
python scripts/build_paper_ready_package.py
```

---

## 2. Random Seed Hierarchy

- **Nuisance Pre-Period Baseline**: Seed `42`
- **Null Calibration Set ($B=1,000$)**: Seeds `100000` to `100999`
- **Validation Audit Set ($N_{\text{val}}=500$)**: Seeds `101000` to `101499`
- **Confirmatory Benchmark ($26 \times 50$)**: Seeds `102000 + scenario_idx * 1000 + pair_id`
- **Sign-Flip Permutations (5,000)**: `np.random.default_rng(42)`
- **Bootstrap Resampling (2,000)**: `np.random.default_rng(42)`
