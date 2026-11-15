# Canary SSM V3 Evidence Inventory

- **Repository**: `canary_ssm_demoImplementation`
- **Audit Date**: 2026-11-15
- **Commit Base**: `dd00b01ec472d2604ddefa563a862b6758f2b68c`
- **Governing Specification**: Section 4 of *Canary SSM V3 Comprehensive Research, Validation and Engineering Test Specification*

---

## 1. Directory Structure Overview

The repository is structured into distinct, decoupled subsystems:

```
c:/afml-implementation/
├── canary_ssm/                 # Production & research core library
│   ├── factor/                 # Workload & rank-1 factor estimation (mu, beta, lambda)
│   ├── kalman/                 # State-space modeling & Kalman filtering
│   ├── hierarchy/              # Null-space projection & orthogonal basis construction
│   ├── decision/               # Sequential decision policies, stopping, hysteresis
│   ├── baselines/              # Classical detectors (CUSUM, EWMA, Shewhart, GLR, Xie-Siegmund)
│   ├── simulate/               # Ground truth generation & rollout simulation engine
│   ├── metrics.py              # Evaluator metrics (detection delay, false alarm rates)
│   └── experiments.py          # Experiment orchestration & regime evaluation
├── tests/                      # Formal pytest test suite
├── configs/                    # Simulation and scenario configuration YAMLs
├── scripts/                    # Command-line drivers, audit scripts, figure generators
├── docs/                       # Core project specifications, architecture docs, audit reports
│   ├── final_audit/            # Stage 1, Stage 2, Stage 3 independent audit records
│   ├── research_release/       # Release manifests, changelogs, research release notes
│   └── validation/             # [New] External validation & model diagnostics reports
├── artifacts/                  # Frozen V3 model checkpoints, calibration artifacts, policies
├── results/                    # Preserved historical experimental evaluation CSVs
│   ├── study_inertia/          # V3 inertia study results (plain, step, combined)
│   ├── plain_final/            # Evaluated plain regime test results
│   ├── step_final/             # Evaluated step regime test results
│   └── study_combined/         # Evaluated combined regime test results
├── paper/                      # Research paper drafts, figures, tables, evidence registry
│   ├── figures/                # Vector SVG and 300 DPI publication figures
│   ├── tables/                 # Publication tables (LaTeX, CSV, Markdown)
│   └── evidence/               # Machine-readable claim mappings
└── external_validation_v1/     # [New] Isolated external validation workspace
    ├── protocol/               # Pre-experimental registration and benchmark protocol
    ├── configs/                # New benchmark scenario configurations
    ├── artifacts/              # External validation model artifacts & calibration thresholds
    ├── data/                   # Calibrated synthetic data for external tests
    ├── results/                # Per-rollout evaluation CSVs and metrics
    ├── figures/                # External benchmark figures
    ├── tables/                 # External benchmark tables
    ├── logs/                   # Execution logs
    ├── manifests/              # Hash manifests and run integrity records
    └── reports/                # Milestone reports
```

---

## 2. Frozen Historical Artifacts Inventory & Preservation Verification

The following historical artifacts from Stages 1–3 are permanently frozen and preserved as read-only evidence. They are strictly protected from modification or overwriting:

### 2.1 Model Checkpoints and Calibration Artifacts
| Artifact Path | SHA-256 Digest | Status | Description |
|---|---|---|---|
| `artifacts/model_v3/fitted_model.json` | `5e91fc8a38db8b3ee1ebfe6f1cfec9ba2ff8163f4f72db1a95a560124ca60d62` | Frozen / Preserved | Stage 1 fitted SSM model parameters |
| `artifacts/policy_plain_v3/policy.json` | `f5971ad10b0f79e5e783454b5dfa91b4c3e80e34c9797034b75fcfa1c68676bf` | Frozen / Preserved | Calibrated decision thresholds for plain regime |
| `artifacts/policy_step_v3/policy.json` | `e2a053229b1d305ea07e1e6992d19d67b2d28f8f0fce21e3f89bf94f260bc4b8` | Frozen / Preserved | Calibrated decision thresholds for step regime |
| `artifacts/classifier_v3/classifier.json`| `dfc9725539d0cf3b55c3c126d400e4dc3a9e782bc4b7f833503264663c0a5254` | Frozen / Preserved | Pre-rollout regime classification model |

### 2.2 Historical Evaluation Results
| Results Path | Key Files | Evaluation Status | Purpose |
|---|---|---|---|
| `results/study_inertia/` | `summary_metrics.csv`, `per_rollout_metrics.csv` | Frozen | Primary test-role evaluation of inertia ablation |
| `results/plain_final/` | `summary_metrics.csv`, `per_rollout_metrics.csv` | Frozen | Final test evaluation under plain regime |
| `results/step_final/` | `summary_metrics.csv`, `per_rollout_metrics.csv` | Frozen | Final test evaluation under step regime |
| `results/study_combined/`| `summary_metrics.csv`, `per_rollout_metrics.csv` | Frozen | Final test evaluation under combined regime |

### 2.3 Review Bundles
| Bundle | Location | SHA-256 Digest | Preserved Scope |
|---|---|---|---|
| P0 | `review_bundle_P0.zip` | Verified | Preregistration and change plan freeze |
| P1 | `review_bundle_P1.zip` | Verified | Baseline simulator and factor models |
| P2 | `review_bundle_P2.zip` | Verified | Kalman filtering core & covariance |
| P3 | `review_bundle_P3.zip` | Verified | Decision engine, hysteresis, policy |
| P4 | `review_bundle_P4.zip` | Verified | Calibration pipeline ($B=2,000$ nulls) |
| P5 | `review_bundle_P5.zip` | Verified | Experiment matrix execution |
| P6 | `review_bundle_P6.zip` | Verified | Evaluator metrics & sign-flip tests |
| P7 | `review_bundle_P7.zip` | Verified | End-to-end report and documentation |

---

## 3. Data Role Separation and Isolation Assurance

1. **Test-Role Invariance**: No code in `external_validation_v1/` reads or references `data/plain/test/`, `data/step/test/`, or any existing evaluation outputs.
2. **Dedicated Workspace**: All new simulations, synthetic streams, calibration runs, and evaluations are confined strictly to `external_validation_v1/`.
3. **Reproducibility Guarantee**: Random seeds for external validation are explicitly partitioned from historical seeds (using seeds starting from 90,000+).
