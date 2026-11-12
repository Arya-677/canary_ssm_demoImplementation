# canary_ssm: Hierarchical Canary State-Space Model (Version 2)

Statistical-track research implementation for detecting weak canary-release latency regressions under shared workload and environmental shifts. Includes a reproducible synthetic simulator, workload/factor adjustment, Kalman/hierarchical Gaussian state-space filters, classical & prewhitened sequential comparators, clairvoyant reference oracles, leakage-safe calibration, Beta-Binomial null gating, and study runners.

**Repository policy:** Generated datasets (`data/`, `data_*/`), fitted artifacts (`artifacts/`, `artifacts_*/`), caches (`cache/`), and experiment outputs (`results/`, `results_*/`) are gitignored so this repository tracks only source implementation, specifications, configurations, scripts, and tests.

## Hardware & Environment
CPU only. The statistical track needs no GPU (the neural/Mamba track is deliberately not implemented). Tested on Windows 11 with Python 3.12 (`numpy`, `scipy`, `pandas`, `pyyaml`, `matplotlib`, `statsmodels`, `hypothesis`, `pytest`).

## Setup (Windows / Linux)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev,report]"
python -m pytest -q          # 107 tests
```

On Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,report]"
python -m pytest -q
```

## Quick Pipeline Commands

Each pipeline stage consumes explicit, SHA-256 hash-checked and regime-matched artifacts (`simulate -> fit -> calibrate -> validate-null -> evaluate`), orchestrated via `tasks.ps1` / `tasks.sh` or `python -m canary_ssm.cli`:

```powershell
# Smoke check
.\tasks.ps1 smoke

# Plain-regime pipeline (configs/plain_main.yaml)
.\tasks.ps1 plain-pipeline

# Step-regime pipeline (configs/step_regime.yaml)
.\tasks.ps1 step-pipeline

# Parameterised V2 diagnostic / robustness studies
python -m canary_ssm.cli study x02 --out results/x02
```

Pass `--oracles` to `calibrate`, `validate-null`, and `evaluate` to run clairvoyant upper-bound reference detectors (`oracle_cusum`, `oracle_bayes`, `oracle_subset`, marked `ORACLE` and excluded from real-method rankings).

## Repository Structure

```text
canary_ssm_project/
├── canary_ssm/
│   ├── schema.py            # Data contracts; Rollout = detector-visible input only
│   ├── simulate.py          # Synthetic simulator + Truth (evaluator-only)
│   ├── seeds.py             # V2 disjoint 1M-block deterministic seed registry
│   ├── manifest.py          # Cryptographic config/grid/model/policy/git provenance
│   ├── parallel.py          # Windows-safe deterministic multiprocessing & JSONL resume
│   ├── factor.py            # Workload regression, rank-1 control factor, eligibility
│   ├── preprocess.py        # Per-class AR(1) / white nuisance MLE fitting
│   ├── kalman.py            # Joseph-form Kalman filter, Cholesky solves, missing gaps
│   ├── hierarchy.py         # Hierarchical / independent / pooled SSM effect detectors
│   ├── baselines.py         # matched_contrast, adj_ewma, adj_cusum, topk_cusum
│   ├── baselines_extra.py   # wmean, ar_cusum, glr_window, sparse_mix_glr, bocpd, msprt, mw_judge
│   ├── oracles.py           # Clairvoyant upper bounds (ORACLE labeled, --oracles flag)
│   ├── decision.py          # Order-statistic calibration (Schema v2), latched alarm, policy
│   ├── metrics.py           # Capped delay, host localization, Brier, Beta-Binomial & CIs
│   ├── experiments.py       # Pipeline stages, 5-fold/1-SE/edge-check tuning, caching
│   ├── report.py            # Markdown tables/figures generated strictly from saved CSVs
│   ├── cli.py               # CLI entry point (python -m canary_ssm / canary-ssm)
│   └── studies/             # Parameterised V2 study runners (x02a/b/c, regime, robust)
├── configs/                 # Regime & grid specs (plain_main.yaml, step_regime.yaml, grids_v2.yaml, ...)
├── docs/                    # Change plan, design decisions, baselines spec, sandbox audit
├── scripts/                 # Smoke, audit, and reproduction scripts
└── tests/                   # 107 automated unit & property tests
```

See [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md), [docs/baselines.md](docs/baselines.md), and [AGENTS.md](AGENTS.md) for methodological contracts, anti-leakage rules, and protocol details.
