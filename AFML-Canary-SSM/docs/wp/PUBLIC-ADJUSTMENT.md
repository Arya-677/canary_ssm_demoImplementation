# Public workload and control adjustment checkpoint

14 November 2026. Extends `canary_ssm_scenario_bundles.zip`.

This adds a versioned public-window preprocessing API and CLI. Intercepts,
workload coefficients, scales and group AR noise are fitted only on declared
healthy development inputs. Canary loadings alone adapt on pre-exposure windows
that were available by the freeze boundary. Current references use fresh,
publicly unexposed controls. The output preserves the full shared canary
covariance and subtracts its reference once. No SSM score is connected.

## Executed checks

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 410 passed in 139.17s (0:02:19) |
| `python -m pytest -q tests/test_public_adjustment.py` | 25 passed in 0.75s |
| `python -m canary_ssm.adjustment_fixture --out examples/control_adjustment` | All 11 computed acceptance gates passed |
| Documented `public_adjustment fit` and `apply` commands | Exit 0; Python API, saved output and CLI output agree exactly |
| Original factor rank-zero and rank-one before/after comparison | Bitwise equal for all checked arrays, with missing/late data |
| Existing engine artifact replays | All 28 pass |
| Existing scenario member verification | All 22 pass |
| Original tests and model artifacts | Byte-preserved; no existing test edited or skipped |

Raw evidence is `public_adjustment_validation.json`; the small compatibility
CSV is `examples/control_adjustment/research_compatibility.csv`. Comparison checked
r, obs, elig, U, lam, sigma, rm, f_hat and ctl_r against the original factor module
from the incoming ZIP, with NaNs compared equal. These are compatibility and
acceptance results, not false-alert, detection-delay or power benchmarks.

## Hand checks and leakage guards

An independently calculated projection fixture has factor 1 and uncertainty
4/3. Canary loadings 2 and 3 give shared off-diagonal covariance 8. The fixture
checks subtraction once, control exposure/staleness, the exact 4-of-5 canary
boundary, per-rack support, pre-window receipt deadlines, future perturbations,
rank zero, frozen nuisance parameters and failed contaminated-control behavior.
The contamination case deliberately shifts the plain factor estimator; it is
not reported as robust. Earlier outputs cannot use later pre-window receipts to
refit a loading. Missing minutes cannot be compacted into adjacent AR steps.

The saved algebraic fixture uses public records and committed causal windows,
with generative recipe labels in a separate evaluator directory. It is not a
resource-world experiment and does not establish calibration or model adequacy
for queue-generated latency. Tiny world scenarios lack 60 pre-minutes and use
the explicit frozen-development loading fallback rather than weakened defaults.

## Changed files and next boundary

Existing `factor.py` shares extracted rank-one helpers, preserving its behavior.
New files are `public_adjustment.py`, `adjustment_fixture.py`, two rack-policy
configs, `test_public_adjustment.py`, the contract, these reports and the small
saved fixture. README, design decisions and audit/status tables document the
new boundary. Existing simulator, inference state transitions, research metrics,
fitted research artifacts, tests, web app and backend commands are unchanged.
The source is an extracted archive; no git commit or merge is claimed.

The next patch is a causal scoring adapter that consumes the full covariance
without subtracting another shared contrast, followed by separately frozen
threshold calibration. Robust estimation under background control faults,
parameter uncertainty propagation, multiple same-service replica aggregation
and world detector performance remain open. Monitoring still says detector not
connected. No threshold or holdout data was used for fitting here.
