# Canary SSM V3: Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Gate G2 Validated](https://img.shields.io/badge/Gate%20G2-Validated%20(p%E2%89%A50.01)-brightgreen.svg)](docs/research_release/RESULTS_AND_FINDINGS.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Research Release: V3 Complete](https://img.shields.io/badge/Release-V3%20Complete-purple.svg)](docs/research_release/PROJECT_OVERVIEW.md)

Statistical research implementation and benchmark evaluating **hierarchical linear-Gaussian state-space models (DLMs)** for automated software canary monitoring under shared workload shifts, diurnal environmental drift, and telemetry confounders.

---

### Executive Overview & Abstract

Progressive canary deployments protect cloud systems by testing software releases on a small fraction of instances (e.g., 5% to 10%) before global promotion. However, detecting performance degradations in live canary telemetry is complicated by environmental confounders: diurnal workload surges, background batch jobs, and host-level heterogeneity. Classical sequential monitoring algorithms (CUSUM, EWMA, Sequential GLR) lack host-level hierarchy and latent state memory, causing false-alert rates to escalate under non-Gaussian noise (surpassing 85% in stress testing).

**Canary SSM V3** provides a principled, leakage-safe framework that models canary telemetry by decomposing observed metric streams into:
1. Shared cluster-wide workload and environmental factors (estimated via pre-period regression and PCA rank reduction).
2. Group-level latent deployment effects (class-level latent states).
3. Host-specific deviation states and measurement noise.

Coupled with finite-sample order-statistic threshold calibration (Gate G2, Beta-Binomial $p \ge 0.01$) and an automated advisory replay policy, the system provides mathematically bounded false-alert budgets while reducing detection latency on correlated fleet regressions.

---

### Key Research Findings

Benchmarked across 9,600 simulated rollouts in the primary study and evaluated on held-out test partitions:

1. **Fleet Detection Speedup (H1 Supported):**
   Hierarchical state-space modeling reduces mean horizon-capped detection delay on correlated fleet anomalies to **15.57 min**—a statistically significant **2.53 min advantage** over unpooled models ($p = 0.0012$) and a **17.81 min advantage** over sequential GLR (33.38 min).
2. **The Localized Shrinkage Trade-Off (H1 Cost Check):**
   When defects are isolated to a single canary host (`single_host_persistent`), hierarchical shrinkage delays detection by **+9.46 min** ($30.89\text{ min}$ vs $21.43\text{ min}$ for unpooled SSM), confirming that pooling suppresses isolated defects.
3. **Multi-Stressor Robustness:**
   Under heavy-tailed measurement noise ($t(3)$), Kalman observation updates regularize noise, preserving false alerts at **6.0%** (Gate G2 compliant) and achieving **99.67%** empirical power. In contrast, classical windowed GLR false alerts explode to **85.7%** and CUSUM to **12.7%**.
4. **Unsupported Secondary Hypotheses (Negative Findings):**
   - **H2 (Two-Scale Dynamics):** Class-level inertia states provided no practical or statistical benefit over fleet-level filtering ($\Delta = -0.18\text{ min}$, $p = 0.42$).
   - **H3 (Decision Hysteresis):** Requiring confirmation depth $m \ge 3$ effectively suppressed isolated spikes, but delayed detection on weak persistent harm by $+4.12\text{ min}$, exceeding the preregistered 3-minute tolerance.
   - **H5 (Universal Dominance):** Classical detectors remain faster and computationally lighter in clean, unconfounded environments.

---

### Mandatory Scientific Non-Claims (Gate G4)

- **No Novel Mathematical Model Family:** The core filter is an exact linear-Gaussian Kalman formulation / Dynamic Linear Model (DLM) with orthonormal sum-to-zero class deviations and Joseph-form updates. Novelty lies in the methodological integration, finite-sample order-statistic threshold calibration, and empirical benchmarking.
- **No Production Readiness Claim:** Evaluated on high-fidelity synthetic microservice benchmarks; not validated for unmonitored live industrial deployment.
- **No Multivariate Telemetry Validation:** Evaluated strictly on univariate latency telemetry.
- **No Causal Attribution:** State estimates are statistical projections conditioned on pre-period nuisance priors.

---

### Interactive Local Demonstration

A self-contained, zero-dependency interactive dashboard is included in [`demo/`](demo/):

```bash
# Launch the local HTTP demonstration server
python demo/serve_demo.py --port 8080
```
This automatically opens `http://localhost:8080/index.html` in your browser.

- **Features:** Synchronized telemetry, adjusted contrast, and posterior probability charts; real-time adjustable hysteresis thresholds ($\tau_{\text{high}}$, $\tau_{\text{low}}$, confirmation depth $k$); timeline scrubber; and 6 scenario presets.
- **Zero Dependencies:** Pure HTML5 Canvas with embedded JSON telemetry; runs 100% offline.

---

### Repository Directory Guide

```text
canary-ssm-v3/
│
├── canary_ssm/                 # Core Python package
│   ├── simulate.py             # Telemetry simulator (workload, factors, noise)
│   ├── preprocess.py           # Pre-period nuisance parameter estimation
│   ├── factor.py               # Dynamic PCA factor adjustment
│   ├── hierarchy.py            # Hierarchical state-space decomposition
│   ├── kalman.py               # Joseph-form Kalman filter & gap handling
│   ├── inertia.py              # Posterior harm probability & persistence scoring
│   ├── decision.py             # Order-statistic calibration & replay policy
│   ├── baselines.py            # Classical detectors (CUSUM, EWMA, Top-K)
│   ├── baselines_extra.py      # Sequential GLR, Siegmund Mix-GLR, BOCPD, mSPRT
│   └── studies/                # Preregistered study orchestrators
│
├── configs/                    # Simulation and study configuration files
│   ├── v3_plain.yaml           # Baseline unconfounded plain regime
│   ├── v3_step.yaml            # Step confounder regime
│   └── v3_combined.yaml        # Multi-stressor composite scenarios
│
├── artifacts/                  # Frozen model parameters and calibrated policies
│   ├── model_v3/               # Selected state-space hyperparameters (manifest.json)
│   ├── policy_plain_v3/        # Gate G2 calibrated policy (plain regime)
│   └── policy_step_v3/         # Gate G2 calibrated policy (step regime)
│
├── results/                    # Immutable experimental outputs & CSV records
│   ├── study_inertia/          # Main 16-scenario study (9,600 rollouts)
│   ├── plain_final/            # Held-out plain test evaluation (2,000 rollouts)
│   ├── step_final/             # Held-out step test evaluation (2,000 rollouts)
│   └── study_combined/         # Multi-stressor robustness study (3,000 rollouts)
│
├── docs/                       # Research documentation and audit reports
│   ├── research_release/       # Complete publication release package
│   │   ├── PROJECT_OVERVIEW.md
│   │   ├── SYSTEM_ARCHITECTURE.md
│   │   ├── MATHEMATICAL_MODEL.md
│   │   ├── EXPERIMENTAL_METHODOLOGY.md
│   │   ├── RESULTS_AND_FINDINGS.md
│   │   ├── STATISTICAL_ANALYSIS.md
│   │   ├── LIMITATIONS_AND_NONCLAIMS.md
│   │   ├── DATA_DICTIONARY.md
│   │   ├── REPRODUCIBILITY.md
│   │   ├── DEMO_GUIDE.md
│   │   ├── DEMO_VIDEO_STORYBOARD.md
│   │   ├── DEMO_VIDEO_SCRIPT.md
│   │   └── ARTIFACT_INDEX.md
│   └── final_audit/            # Comprehensive technical & scientific audit reports
│       ├── TEST_SUITE_AUDIT.md
│       ├── HYPOTHESIS_RECONCILIATION.md
│       ├── ROBUSTNESS_AUDIT.md
│       ├── CALIBRATION_AUDIT.md
│       ├── FINAL_TEST_RESULTS_AUDIT.md
│       └── REPRODUCIBILITY_AUDIT.md
│
├── paper/                      # Academic research paper preparation materials
│   ├── MANUSCRIPT_SKELETON.md  # Full draft manuscript with KaTeX math & citations
│   ├── PAPER_OUTLINE.md        # Detailed sectional plan and word budgets
│   ├── RESULTS_EVIDENCE_MAP.md # Line-by-line traceability from claims to CSVs
│   ├── REFERENCES.bib          # Primary-source BibTeX bibliography (verified DOIs)
│   ├── FIGURES/                # Publication-ready figures (PNG 300 DPI & SVG)
│   └── TABLES/                 # Publication tables (CSV, Markdown, LaTeX)
│
├── demo/                       # Interactive local demonstration prototype
│   ├── index.html              # Standalone web dashboard
│   ├── serve_demo.py           # Local HTTP server script
│   ├── data.json               # Embedded microservice telemetry trajectories
│   └── README.md               # Demo user guide
│
├── scripts/                    # Automation and visualization scripts
│   ├── make_research_figures.py # Generates paper figures & tables from CSVs
│   └── build_release_manifest.py# Generates cryptographic manifests & checksums
│
├── review_bundle_P*.zip        # Cryptographically signed review bundles (P0 to P7)
├── RESEARCH_RELEASE_MANIFEST.json # Machine-readable release inventory
├── SHA256SUMS.txt              # Cryptographic SHA-256 checksums
└── requirements.lock           # Exact pinned Python dependencies
```

---

### Installation & Environment Setup

#### Requirements
- Python 3.12 (CPython x86_64)
- CPU-only execution (multi-threaded via `concurrent.futures.ProcessPoolExecutor`)
- No GPU hardware or proprietary drivers required.

```bash
# Clone the repository
git clone https://github.com/Arya-677/canary_ssm_demoImplementation.git
cd canary_ssm_demoImplementation

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install exact pinned dependencies
pip install -r requirements.lock

# Run test suite
pytest -q
```
*Note on test status:* 140 tests pass. Exactly 1 test (`test_legacy_simulator_outputs_are_bit_identical_after_v3_edits`) fails on Windows due to a 1-ULP floating-point difference between Windows MSVC UCRT and Linux glibc math libraries (fully documented in [`docs/final_audit/TEST_SUITE_AUDIT.md`](docs/final_audit/TEST_SUITE_AUDIT.md)).

---

### Reproducing Research Experiments

Refer to [`docs/research_release/REPRODUCIBILITY.md`](docs/research_release/REPRODUCIBILITY.md) for full commands.

```bash
# 1. Regenerate publication figures and tables directly from saved CSVs:
python scripts/make_research_figures.py

# 2. Verify all artifact checksums:
python -c "import hashlib; [print(f'{f.split()[1]}: OK') for f in open('SHA256SUMS.txt') if hashlib.sha256(open(f.split()[1],'rb').read()).hexdigest() == f.split()[0]]"

# 3. Launch interactive demo:
python demo/serve_demo.py
```

---

### Citation

If using this research archive, codebase, or benchmark data, cite as:

```bibtex
@misc{canary_ssm_v3_2026,
  title        = {Hierarchical, Inertia-Constrained State-Space Models for Safer Software Rollout Decisions},
  author       = {[AUTHOR INPUT REQUIRED: Primary Investigator]},
  year         = {2026},
  howpublished = {\url{https://github.com/Arya-677/canary_ssm_demoImplementation}},
  note         = {Research Archive and Artifact Release V3}
}
```
*(Primary literature citations available in [`paper/REFERENCES.bib`](paper/REFERENCES.bib).)*
