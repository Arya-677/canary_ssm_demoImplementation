# Latched first-crossing checkpoint

Historical checkpoint. The later [WORLD-POLICY.md](WORLD-POLICY.md) supplies a
separately scoped physical-world example; it supersedes the missing matched-world
artifact gap below without changing this conditional Gaussian evidence.

15 November 2026. Extends `canary_ssm_process_memory.zip`.

Implemented separate latched score policy, complete-horizon eligible-maxima
calibration, explicit no-data handling, independent nonretuned validation and
uncertainty, immutable development/model/preprocessing/simulator/protocol/policy
bindings, qualified controller attachment, automatic PAUSE/manual ROLLBACK,
explicit auto-rollback opt-in, positive-evidence promotion guard, observed platform
and resource reasons, and separate combined-action false-alert reporting.
The resource guard optionally consumes direct observed memory-growth/headroom/OOM
advisories; platform incidents are supplied as observed evidence, never truth.

## Executed checks

| Check | Observed result |
| --- | --- |
| Full repository suite | 566 passed, 1 warning in 139.61s (0:02:19) |
| Focused new tests | 28 passed, 1 warning in 7.75s |
| HTTP/DOM + checkpoint/browser replay | All 10 gates passed |
| CLI rebuild | Calibrated policy and independent receipt hashes reproduce exactly |
| Existing public scoring CLI | 4 complete monitoring windows produced |
| Source-bound non-scenario replays | 28 verified |
| Scenario manifests | 22 verified |
| Original test files | 29 byte-preserved |
| Original statistical additive files | 60 byte-preserved |
| Legacy resource traces/RNGs | All original common fields equal in three 30-tick healthy/CPU/memory checks |

Original research decision, inference, comparators, fitted models and old
calibration definitions remain unchanged. New policy hashes are separate semantic
JSON hashes. A real browser serialization regression (1.0 versus 1) was fixed and
tested. Raw saved-run upload avoids floating-point/large-integer corruption.
Queued resume/latched-alarm races, exact protocol timing, no-data promotions,
independent roles, source/hash mismatch and resource-only pause/replay are tested.
No existing test was modified or skipped.

## Actual conditional Gaussian example

Generator `policy-conditional-gaussian-null-v1`, healthy development only, fixed
predeclared independent-effect settings, existing rank-one adjustment/no-effect AR
fit and Gaussian posterior scorer. Calibration B=2000,
alpha=0.05, k=1901; the first-500 rank
example gives k=476. Independent validation
n=2000, gate **PASS**, with raw
qualification details/interval assumptions retained. Final validation uses the
registered family 28; calibration/development
use family 21. No final-test data is used.

The table below is generated from saved `false_alerts.csv`. It is **not physical
resource-world performance**. The conditional generator has no observed advisory
producer: extra channels have no events, with nonzero interval upper bounds.
A future enabled physical resource/platform policy needs its own complete combined
null replay; the release alpha does not bound the union automatically.

| Channel | Events | Independent validation nulls | Rate | Exact 95% interval |
| --- | --- | --- | --- | --- |
| release_alarm | 92 | 2000 | 0.046 | [0.037240902034369, 0.056118830543436325] |
| platform_pause | 0 | 2000 | 0.0 | [0.0, 0.0018427397934059364] |
| resource_pause | 0 | 2000 | 0.0 | [0.0, 0.0018427397934059364] |
| combined_action | 92 | 2000 | 0.046 | [0.037240902034369, 0.056118830543436325] |


Policy hash: `f23f37bec8d6341b313bb640fbfdaa5019c61ee54e812d9044e8f7a08c1163ac`.
Validation receipt hash: `1f003a18347bf82db974ae6c96196cd90bc22efe56a8f8eff993d9ce82f0b77e`.
Model/preprocessing/simulator/protocol hashes are retained in
`first_crossing_validation.json` and frozen artifacts. Figures read only saved CSV.

## Workflow boundaries

The shipped statistical artifact is refused by the physical world adapter. A
matching physical healthy-development fit, calibration-null export and independent
validation remain **missing**; no world-calibrated policy is invented. HTTP action
checks use hand-authored controller contract statistics, explicitly not world FAR
evidence and not published as a deployable world policy.

The v1 adapter precommits in a fresh run before baseline and enforces the exact
baseline/exposure boundary. Extended/shifted preperiods are rejected. Automatic
rollback defaults off, applies only after a release-alarm pause, and never follows
an incident/resource-only pause. Healthy promotion needs the completed declared
eligible observation budget and risk ceiling. Lack of data is HOLD. Legacy manual
promotions remain operator overrides with no healthy-evidence claim.

The validation qualification is a conservative single-policy G2-style check,
without changing the existing research multi-cell gate. Calibration rank validity
still assumes independent/exchangeable complete null rollouts from the same
frozen pipeline/protocol. Beta-tail diagnostics assume continuous maxima. Exact
binomial intervals are pointwise, not simultaneous. Control contamination and
the old shared-step failure remain open. No power/causal attribution claim is made.

Implementation/source-contract revisions are recorded in
`policy_retired_versions.json`, with hashes and validation seed ranges. Effect
settings were not selected from those validation outcomes; final validation is
fresh after the last source revision. Browser viewport visual QA is unverified;
actual local HTTP/DOM handlers, raw saved-run replay and checkpoint restoration
were exercised.

Main new files: `first_crossing.py`, `policy_hash.py`, `policy_artifacts.py`,
`policy_public.py`, `policy_control.py`, `policy_fixture.py`, focused tests and
UI/plot helpers. Existing integration files: engine/operations/rollouts/dashboard
and web UI. Full commands, reasons, equations and scope: `docs/latched_policy.md`.
