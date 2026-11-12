# canary_ssm: statistical-track implementation (Hierarchical Canary SSM)

Implements the *Hierarchical Canary SSM Implementation Plan* (rev. 7 Nov 2026) and the corrected research
report: a reproducible simulator, strong sequential baselines, independent / pooled / hierarchical
Gaussian state-space detectors, leakage-safe calibration, and an evaluator. **No performance claims are
made by this repo; every result must come from your own runs.**

## Hardware
CPU only. The handbook's statistical track needs no GPU (the RTX 3060 is unused; it only matters for the
separate neural track, Section 14, which is deliberately NOT implemented). Per-update filter cost measured in
the build sandbox: p99 ~0.3 ms at 10 canaries, ~8 ms at 100 (gate: < 1 s at 10).

## Setup (Windows)
    py -3.11 -m venv .venv
    .venv\Scripts\activate
    python -m pip install -e ".[dev]"
    python -m pytest -q          # 40 tests, ~10 s

## Pipeline (each step consumes explicit, hash-checked artifacts)
    simulate -> fit -> calibrate -> validate-null -> evaluate      (see scripts/run_all.ps1)
`evaluate` refuses missing artifacts or a policy calibrated for a different model (hash check).
Frozen-value calibration audit (no tuning): `bash scripts/audit_quick.sh`.
Smoke check first: `bash scripts/smoke.sh` (or run the commands by hand with configs/smoke.yaml).

## Layout
| file | role |
|---|---|
| schema.py | data contracts; `Rollout` = everything a detector may see |
| simulate.py | simulator + `Truth` (evaluator-only) |
| factor.py | workload regression, rank-one control factor, eligibility, matched contrast |
| preprocess.py | nuisance fit on healthy dev data (AR(1)+white noise per class, Kalman likelihood) |
| kalman.py | Joseph-form filter, Cholesky solves, subset updates, k-step gaps |
| hierarchy.py | hierarchical / independent / pooled effect detectors, sum-zero local deviations |
| baselines.py | matched contrast, adjusted EWMA/CUSUM, top-K CUSUM (+ predeclared grids) |
| decision.py | order-statistic threshold, latched alarm, advisory policy |
| metrics.py | event labels, outcome classes, localization, Brier, exact CIs, paired bootstrap |
| experiments.py | data generation, fit/calibrate/validate/evaluate, manifest, runtime benchmark |
| report.py | tables/figures generated from saved CSVs only |

See `docs/DESIGN_DECISIONS.md` for every place the handbook was ambiguous and what was chosen, and for the
explicit list of what is NOT implemented. `docs/SANDBOX_AUDIT.md` records the null audit I ran (it reproduces the pilot's shared-step failure; the calibration gate is NOT met).
`AGENTS.md` holds the rules for the coding agent.
