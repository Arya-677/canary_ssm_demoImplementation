# Physical-world first-crossing policy

This checkpoint supplies a matched **physical resource-world** development fit,
null calibration, independent null audit and actual public-observation controller
demo. The older `examples/first_crossing` conditional Gaussian example remains a
different generator and is still rejected by the physical-world adapter.
Executed results and requirement statuses are generated in
[`wp/WORLD-POLICY.md`](wp/WORLD-POLICY.md). Read the measured gate there; a failed
gate must never be bypassed or described as validated.

## Run the saved demo

From the extracted repository, with Python 3.12:

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements-world-policy.lock
python -m pip install -e . --no-deps
python -m canary_ssm.world_policy_http_demo --out examples/world_policy
python -m canary_ssm world-dashboard --config configs/world_policy_v1.yaml --port 8765 --state-dir runtime/world-policy
```

Open `http://127.0.0.1:8765`. Use the dashboard's saved-run upload to load
`examples/world_policy/http_alarm/session.json` or `http_healthy/session.json`.
These recordings retain the actual command receipts, world state, policy
decisions, resource traces and detector frames. Upload is read only. The browser
does not recreate the simulation or fabricate chart values. A standalone
`detector.json` recording is also included for the existing Monitoring upload.
The HTTP demo starts its own temporary local API server and requires no browser.
It retains the healthy example, the original combined behavior HOLD example and
all eight predeclared strong-delay smoke seeds. `http_alarm` aliases the first
actual eligible crossing in that smoke bundle. This selection demonstrates the
controller path; it is not an unbiased power estimate. The strong-delay manifest
adds 120000 ms response delay without CPU/memory changes and is simulated only.

## Run an interactive fresh epoch

Use the same dashboard command above with a fresh state directory. In Releases,
create a rollout for `release-001` (healthy) or `release-002` (declared combined
degradation), baseline **3600 seconds**, monitoring **240 seconds**, one canary per
rack and canary traffic **0.2**. Upload `examples/world_policy/policy.json` and
`validation.json` before starting baseline. Keep auto rollback unchecked for the
automatic-PAUSE/manual-ROLLBACK workflow.

In a second terminal, start the public scorer:

```sh
python -m canary_ssm.world_policy_live --policy examples/world_policy/policy.json --url http://127.0.0.1:8765
```

The producer waits for a matching attached policy and exposure. Start baseline at
tick zero, advance exactly 60 simulated ticks, then expose at the declared
boundary. A tick is 60 simulated seconds in this version. Speed changes wall-clock
playback only. The fixed four-minute horizon has four decisions. On an eligible
strict threshold crossing, the backend queues PAUSE for the next tick; rollback
is manual. Promotion still requires the complete eligible budget and the separate
healthy risk ceiling. A noncrossing score alone need not satisfy that ceiling.

The producer reads only `/api/state`, committed `/api/telemetry?decision_time=…`
and `/api/detectors`, and posts validated policy/monitor commands. It never calls
step/start/reset, reads fault truth, selects deployments or runs a second world
clock. Reconnect resumes from backend observation/frame counts. Stable command
IDs make uncertain POST retries idempotent. Closed epochs/read-only replays hold;
they are not silently reopened. Restarting or changing worlds requires a fresh
matching epoch. The chart's marginal posterior remains conditional on the model;
the separately qualified policy card supplies alarm calibration, not a claim of
calibrated marginal posterior probabilities.

## Exact calibrated scope and assumptions

`configs/world_policy_v1.yaml` is a versioned laptop approximation: one center,
four racks, five hosts per rack, one core and 8192 MB per host, 60-second ticks,
200 expected service requests per host per tick, 0.25 core-seconds of work per
request, bounded 1000-request queues and shared demand jitter 0.35. Existing
bounded resource equations, FIFO request cohorts, actual completion-latency
sufficient statistics and minute aggregation are used unchanged. The observation
is mean log completion latency; charts use the saved arithmetic mean latency.
Neither value is named p95. The coarse tick duration is a simulation assumption,
not a fidelity or performance claim about real data centers.

Healthy development supplies 120 minutes, with no exposure. Each null supplies
60 baseline minutes followed by the full four-minute exposed healthy-candidate
horizon. Cohorts and traffic are fixed. Grouping is explicitly `rack_id`; the
80% canary coverage, three fresh unexposed controls per represented group and
60-minute preperiod defaults are unchanged. Workload regression, rank-one
controls, reference covariance, AR noise fitting/state carryover and the common
Gaussian filter are reused. This artifact uses **independent** effect settings
predeclared before calibration; it does not claim hierarchical pooling benefits.
Existing independent/hierarchical comparison examples remain separately versioned
and uncalibrated. Changing model/pooling settings requires new development freeze,
calibration and independent validation.

The calibrated null has **no background platform faults, no loss/delay, no
resource guardrail and no external incident producer**. Shared stochastic demand
variation and endogenous queues/routing are present. Platform/resource channels
are reported separately, with nonzero uncertainty even when their observed count
is zero. Their union is measured, not assumed controlled by release alpha.
Manual faults, missingness, different hardware/traffic, longer horizons or enabled
advisories are outside this null distribution and require new compatible
calibration. A manual fault demo is a stress illustration, not null validation.
The original shared-step/control-contamination failure remains open. No robust
estimator, root-cause proof, power, or universal false-alert guarantee is claimed.

## Reproduce and audit

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m canary_ssm.world_policy_fixture calibrate --out examples/world_policy --B 2000 --n-validation 2000 --workers 4
python -m canary_ssm.world_policy_fixture verify --out examples/world_policy --role threshold-calibration --index 0
python -m canary_ssm.world_policy_fixture verify --out examples/world_policy --role null-validation --index 0
python -m canary_ssm.world_policy_fixture demo --out examples/world_policy
python -m canary_ssm.world_policy_http_demo --out examples/world_policy
python scripts/plot_world_policy.py --directory examples/world_policy
python -m pytest -q
```

The first line executes 4000 resource-world rollouts; it is deliberately bounded
to four worker processes. No final-test role is consumed. Registered seed family
30 separates development, calibration, validation, smoke and reserved final test.
`preregistration.json` and `frozen.json` are written before calibration. Validation
is generated after the policy hash exists and cannot retune it. Failed fits/bounds,
ineligible windows, empty-data rollouts and failed gates remain in the artifacts.
Small `--B`/`--n-validation` runs are pipeline smoke checks and cannot qualify for
automatic attachment.

Every null retains its seed, ordered command/event/publication log, public input
fingerprints, full monitoring record prefix and role. Raw telemetry can be
regenerated by `verify`; this checkpoint does not store 4000 redundant complete
world snapshots. Development and both HTTP demos include complete public slices;
demo truth is a separate evaluator file and never enters the scorer. Rebuilding
calibration/validation directly from the saved public score records is supported
by the existing `policy_artifacts` CLI. Hash and NumPy/SciPy compatibility checks
remain strict. `requirements-world-policy.lock` records this executed environment;
the older research environment lock is preserved.
