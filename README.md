# canary_ssm: Hierarchical Canary State-Space Model & Virtual Data Center

[![Tests](https://img.shields.io/badge/tests-258%2B%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

A statistical research codebase and interactive Virtual Data Center for detecting weak, persistent canary-release regressions under shared workload and environmental shifts.

It combines **Hierarchical State-Space Modeling (HSSM)** with nested SVD factor subtraction and within-class shrinkage, comparing partial pooling against independent estimation and complete pooling in real-time streaming telemetry and reproducible benchmark simulations.

---

## 1. Quick Start

### Launch the Interactive Web Dashboard
Run the one-command local demo dashboard:
```bash
python -m canary_ssm.cli dashboard --host 127.0.0.1 --port 8000
```
or via the installed entrypoint:
```bash
canary-ssm dashboard --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

- **1-Click Demo:** Click **"▶ Start Demo"** in the top bar to run canonical scenarios (Clean Release, Memory Leak, Rack Slowdown, Fleet Demand Spike, CPU Contention, Healthy GC Oscillations, Combined Faults, Missing Controls).
- **Interactive Workflow:** Follow the guided 7-step workflow from scenario selection to ground-truth audit.
- **Side-by-Side Method Comparison:** Compare **Hierarchical SSM (partial pooling)**, **Independent SSM (no pooling)**, and **Complete Pooling** side-by-side on the live telemetry stream.

For detailed instructions, see the [Dashboard User Guide](docs/dashboard_user_guide.md).

---

## 2. Tested Environment & Setup

- **Hardware / OS:** CPU-only (no GPU required; neural/Mamba track deliberately omitted), Windows 11 / Linux / macOS, Python `>= 3.10` (tested on Python 3.12).
- **Core Dependencies:** `numpy`, `scipy`, `pandas`, `statsmodels`, `fastapi`, `uvicorn`, `matplotlib`, `pyyaml`, `hypothesis`, `pytest`.

### Installation
```bash
# Clone the repository
git clone https://github.com/29kumaranish-hash/AFML_Demo.git
cd AFML_Demo

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux / macOS:
source .venv/bin/activate

# Install package with development dependencies
pip install -e ".[dev,report]"
```

### Running the Test Suite
```bash
# Run all fast tests (258+ tests):
python -m pytest -m "not slow" -q

# Run inference parity and policy validation regression suites:
python -m pytest tests/test_inference_parity.py tests/test_policy_validation.py tests/test_api_scenarios.py -v
```

---

## 3. Key Statistical Architecture

### Hierarchical State-Space Model (Partial Pooling)
The system monitors canaries across heterogeneous hardware classes $g \in \{1, \dots, G\}$ and physical racks:
- **Helmert Contrast Basis:** An orthonormal basis $L = [C \quad B]$ decomposes effects into class means $\theta_g$ and host deviations $b_i$ that sum to zero within each class ($B^T B = I_{n-G}, C^T B = 0$).
- **Within-Class Shrinkage:** Damps individual host telemetry noise by shrinking estimates toward the hardware class mean, boosting statistical power while preserving single-host sensitivity.
- **Nested SVD Factor Adjustment:** Removes fleet-wide diurnal cycles and rack-switch network latency before state-space filtering.
- **Joseph Covariance Stabilization:** Ensures numerical positive semi-definiteness ($P = (I - K H) P (I - K H)^T + K R K^T$) during long telemetry gaps.

### Release Decision Metric
- **Release Score: Maximum Host Risk:**
  $$\text{Score}_t = \max_{i \in \text{Canaries}} \log P(a_{it} > \kappa_{\text{lat}} \mid \text{data}_{\le t})$$
- **Declared Harm Boundary:** $\kappa_{\text{lat}} = \log(1.02) \approx +0.0198$ represents an operational $+2.0\%$ latency increase.
- **Log Probability Scale:** Scores fall strictly in $(-\infty, 0.0]$. Initial null scores are set to `None` to prevent confusion with $\log(1.0) = 0.0$.
- **Dual Advisory Firewall:** Evaluates `InfrastructureAdvisory` (fleet/rack health from concurrent baseline controls) separately from `CanaryReleaseAdvisory` (canary-specific harm).

---

## 4. Repository Structure

```text
AFML_Demo/
├── canary_ssm/
│   ├── world/               # Virtual datacenter: Fleet, Racks, Servers, Clock, Telemetry
│   ├── faults/              # Fault engine: typed infrastructure vs release faults, truth store
│   ├── deployments/         # Release registry, SHA-256 artifacts, identifiability validator
│   ├── telemetry/           # Time slicing, streaming residuals, pre-period baselines
│   ├── kalman.py            # Joseph-form Kalman filter, missingness prediction
│   ├── hierarchy.py         # Hierarchical, independent, and pooled batch SSM detectors
│   ├── memory.py            # Process memory growth residual, GC sawtooth dynamics, TTE
│   ├── detector_service.py  # Streaming detector service, policy validation, 8-state machine
│   ├── baselines.py         # Matched contrast, adjusted EWMA, CUSUM, Top-K CUSUM
│   ├── baselines_extra.py   # Prewhitened sequential comparators (GLR, BOCPD, MSPRT, MW-Judge)
│   ├── oracles.py           # Clairvoyant reference upper bounds (Oracle-CUSUM, Oracle-Bayes)
│   ├── decision.py          # Order-statistic calibration, latched alarm, policy schemas
│   ├── scenarios/           # 8 versioned canonical scenario presets
│   ├── api/                 # FastAPI REST backend (routes, schemas, simulator service)
│   └── dashboard/           # Modern 8-tab SPA dashboard (HTML5 Canvas charts, zero build tools)
├── configs/                 # plain_main.yaml, step_regime.yaml, grids_v2.yaml, audit.yaml
├── docs/
│   ├── bug_audit.md         # Comprehensive correctness audit & verified bug fixes
│   ├── dashboard_user_guide.md # First-time user manual and 7-step walkthrough
│   ├── implementation_status.md # Versioned milestone inventory and test audit
│   ├── LIMITATIONS.md       # Statistical boundaries, step failures, and missingness
│   └── DESIGN_DECISIONS.md  # Architectural contracts and deferred research boundaries
├── results/                 # Saved CSV tables, Gate G2 validation matrices, and plots
├── tests/                   # 248+ unit, property, parity, policy, and API tests
├── pyproject.toml           # Package build and dependency specification
├── requirements.lock        # Pinned reference environment lockfile
└── AGENTS.md                # Non-negotiable anti-leakage, causality & calibration rules
```

---

## 5. Epistemic Transparency & Research Scope

In accordance with the project's statistical design guidelines:
1. **Gate G2 Validity:** Hierarchical SSM with factor subtraction passes the exact Beta-Binomial validity test ($B \ge 2000, n \ge 2000$) across stationary nulls, step-contaminated nulls, and heavy-tailed noise.
2. **Known Failure Under S5 (Label Errors):** In `results/x04/x04_summary.md`, `hier_rank0` (which omits nested factor subtraction) failed Gate G2 under label noise ($p = 1.218 \times 10^{-8}$). The evaluation tab prominently marks `hier_rank0` on S5 as **INVALIDATED**.
3. **Deferred Research Scope:** As documented in `docs/DESIGN_DECISIONS.md`, Borg cluster traces and neural/Mamba/LSTM baselines were designated as deferred research scope. Telemetry analysis isolates statistical evidence of abnormal growth and latency shifts, not mathematical proof of source code defects.
