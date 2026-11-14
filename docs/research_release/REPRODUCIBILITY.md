# Reproducibility Guide: Canary SSM V3
## Step-by-Step Instructions for Environment Setup and Experiment Execution

- **Target Audience:** Independent Researchers, Reviewers, and Evaluators
- **Standard:** Bit-Level Code Reproducibility, Deterministic Seed Isolation, and Frozen Artifact Verification

---

### 1. Hardware & Environment Specifications

The codebase was executed and verified on the following hardware platform:
- **Operating System:** Windows 11 (AMD64) / Linux (Ubuntu 22.04 LTS compatible)
- **CPU:** AMD Ryzen 7 5800H (8 physical cores, 16 logical threads)
- **Memory:** 16 GB RAM
- **Python Version:** 3.12.10

> [!NOTE]
> Computation uses standard multi-core CPU multiprocessing via Python's `concurrent.futures.ProcessPoolExecutor`. No GPU hardware or specialized acceleration libraries are required.

---

### 2. Environment Setup & Dependency Installation

#### 2.1 Clone Repository & Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/Arya-677/canary_ssm_demoImplementation.git
cd canary_ssm_demoImplementation

# Create a clean Python 3.12 virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate
```

#### 2.2 Install Dependencies from Locked Requirements
```bash
# Install exact pinned versions
pip install -r requirements.lock
```

The core locked dependencies are:
- `numpy==2.5.4`
- `scipy==1.18.1`
- `statsmodels==0.15.0`
- `pandas==3.1.1` (or `2.2.3+`)
- `pytest==9.2.0`
- `matplotlib==3.11.2`
- `pyyaml==6.0.2`

---

### 3. Verification of Existing Research Artifacts

To verify the cryptographic integrity of all packaged review bundles and fitted model artifacts:
```bash
# Verify review bundle checksums against SHA256SUMS.txt
python -c "
import hashlib
from pathlib import Path

with open('SHA256SUMS.txt') as f:
    for line in f:
        sha, fname = line.strip().split()
        p = Path(fname)
        if p.exists():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            status = 'OK' if h == sha else 'MISMATCH'
            print(f'{fname:35} {status}')
        else:
            print(f'{fname:35} MISSING')
"
```

---

### 4. Running Tests Safely (Non-Evaluative)

To run the full unit and regression test suite without generating test data or modifying frozen artifacts:
```bash
pytest -q
```
- **Expected Outcome:** 140 passed, 1 failed (141 total tests).
- **Documented Platform Exception:** `test_v3_changes.py::test_legacy_simulator_outputs_are_bit_identical_after_v3_edits` fails on Windows due to 1-ULP floating-point rounding differences between Windows MSVC UCRT and Linux glibc math libraries (documented in `docs/final_audit/TEST_SUITE_AUDIT.md`).

---

### 5. Safe Experiment Reproduction Commands

The following commands reproduce the development, calibration, and study phases using dev/calibration partitions.

#### 5.1 Simulate Development Telemetry
```bash
python -m canary_ssm.cli simulate --config configs/v3_plain.yaml --role dev --out data/plain/dev
```

#### 5.2 Fit V3 State-Space Hyperparameters
```bash
python -m canary_ssm.cli fit --data data/plain/dev --out artifacts/model_v3 --methods hier_ssm,hier_ts,indep_ssm,glr_window,adj_cusum --auto-expand --max-expansions 2
```

#### 5.3 Calibrate Decision Thresholds (Order Statistics, $B = 2,000$ Nulls)
```bash
python -m canary_ssm.cli simulate --config configs/v3_plain.yaml --role calibration --out data/plain/calibration
python -m canary_ssm.cli calibrate --data data/plain/calibration --model artifacts/model_v3 --out artifacts/policy_plain_v3 --regime plain
```

#### 5.4 Execute Main Inertia Study (16 Scenarios, 9,600 Rollouts)
```bash
python -c "from canary_ssm.studies.study_inertia import run; run(model_dir='artifacts/model_v3', out_dir='results/study_inertia', allow_frozen=True)"
```
- **Expected Runtime:** ~25–35 minutes on 8–16 CPU cores.

#### 5.5 Execute Combined Robustness Study (5 Scenarios, 3,000 Rollouts)
```bash
python -c "from canary_ssm.studies.study_inertia import run; run(model_dir='artifacts/model_v3', out_dir='results/study_combined', scenario_file='configs/v3_combined.yaml', allow_frozen=True)"
```
- **Expected Runtime:** ~8–12 minutes on 8–16 CPU cores.

---

### 6. Held-Out Test Evaluation Protocol (STRICTLY FROZEN)

> [!CAUTION]
> **Data Governance Warning:** The held-out test datasets in `data/plain/test` and `data/step/test` were evaluated strictly **once per regime** in Phase 4. Their outputs are immutably archived in `results/plain_final/` and `results/step_final/`.
> 
> In accordance with Hard Rule 2 and Part 0 safeguards, **do not re-evaluate or tune models against these directories**. They exist solely as archival evidence of generalization.

---

### 7. Launching the Interactive Demonstration Prototype

The interactive local demonstration is completely self-contained and operates offline:

```bash
# Launch local server
python demo/serve_demo.py --port 8080
```
This automatically opens `http://localhost:8080/index.html` in your default browser.

Alternatively, you can open `demo/index.html` directly in any web browser without starting a server:
```bash
# Windows
start demo/index.html

# Linux
xdg-open demo/index.html
```
