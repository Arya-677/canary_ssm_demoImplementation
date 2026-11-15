# Detector outputs in Monitoring

Monitoring now consumes saved or incrementally received Gaussian detector outputs.
It does not fit a model or advance a simulator in the browser. The original
research filters, nuisance fitting, thresholds and metrics are unchanged.

## Run the demo

From the extracted repository, install the declared dependencies and run:

```bash
python -m pip install -e '.[dev,report]'
python -m canary_ssm.detector_dashboard_fixture
python -m canary_ssm world-dashboard --config configs/world_recovery.yaml --port 8765 --state-dir runtime/monitor_demo
```

Open `http://127.0.0.1:8765`, choose Monitoring, select a demonstration and click
Load recording. The samples are included; regeneration is optional. Detector
Replay/Pause, seek and speed operate a backend recording cursor. The world
controls above continue to operate only the world. Both clocks and run identities
are labeled; loading a detector recording does not rewind or simulate the world.

Use the host selector's actual backend IDs. The same replay and observation
prefix feed independent, weaker-pooling and stronger-pooling Gaussian models.
Each line has a versioned artifact/configuration. The setting selector chooses
the displayed marginal uncertainty band, rack effect and host deviation; it does
not tune a model or generate new values. Import/export buttons support the same
validated public artifact format, with an 8 MiB browser upload limit.

## Saved and streamed data contract

`monitor_feed.py` validates `detector-monitor-v1` artifacts against the backend
host ID/rack roster. Every artifact includes run/replay identity, source kind,
version, method settings, exposure boundary, ordered frames and a checksum.
Frames include event/decision timestamps, an input hash shared by all methods,
fresh masks, eligibility, raw latency, adjusted residual and full effect covariance.
Hierarchical group and deviation means must reconstruct total effect means.
Matrices must be finite, symmetric and PSD with nonnegative diagonals. Pre-
exposure posteriors, malformed masks, unknown fields, orphan IDs, conflicting
parentage and bad checksums are rejected. Histories are bounded to 1,000 frames,
128 hosts, four methods and one million covariance entries across methods.
The existing HTTP request limit is 32 MiB; the smaller UI limit is intentional.

Public GET routes are read only:

| Route | Result |
| --- | --- |
| `/api/detectors?host_id=...` | Selected host prefix, posterior intervals/risks, versions, masks and feed state |
| `/api/detectors/export` | Full saved detector artifact, preserving all covariance |
| `/api/detectors/evaluator?developer=1` | Explicit evaluator-only authored recipe, never part of detector GET |

Authenticated commands use the existing `/api/commands` run/epoch, command-ID
and local token validation. `monitor_load` accepts one sample ID or artifact.
`monitor_seek`, `monitor_play`, `monitor_pause` and `monitor_speed` manage saved
playback. `monitor_begin` accepts explicit external-stream metadata;
`monitor_append` accepts one next committed frame. All command outcomes use the
existing persisted receipt mechanism. Duplicate identical last frames are
ignored; late/revised frames are rejected rather than rewriting earlier output.
The browser polls at 750 ms and does no posterior calculation.

A live detector producer may post a frame after its observation deadline. A
working producer example streams the saved real detector outputs incrementally:

```bash
python -m canary_ssm.monitor_stream --artifact examples/detector_dashboard/demo-01.json --url http://127.0.0.1:8765 --start 80 --stop 140 --interval 0.2
```

This command replays already-computed outputs; it is not new live inference.
A live producer uses the same begin/append interface after freezing its nuisance
model and pre-exposure loadings. No automatic model fitting or resource-world
scoring is enabled by opening the dashboard. The current-world connection card
changes only for an external stream whose run ID matches the current world.
Such frames cannot have a decision timestamp after the world's simulated clock.
Different-run streams and saved recordings remain explicitly separate feeds.
Reset clears the detector attachment; saved world sessions include a loaded
artifact and cursor. Restored streams become recordings, never apparently live
producers. Playback commands do not move the world tick or its wall-time deadline.

## Risk, uncertainty and interpretation

For posterior total effect mean m_i and effect variance P_ii, the backend computes

```text
host risk = P(a_i > log(1.02))
          = normal_survival((log(1.02)-m_i)/sqrt(P_ii))
95% marginal interval = m_i +/- 1.959963984540054 sqrt(P_ii)
release score = max_i host risk
```

A zero-variance posterior uses the strict point-mass exceedance definition.
These are effect posteriors: AR observation noise is not added to P_ii. Full
host covariance is retained in the artifact, even though each chart uses a
marginal variance. The interval is pointwise and marginal, not simultaneous.
Release score is explicitly maximum host risk, not a joint release probability.
The original research log-score thresholds cannot silently apply to this
probability-scale display. No policy is compatible/loaded in this checkpoint;
all outputs are UNCALIBRATED, with no alarms or automatic deployment decisions.
The independently versioned nested variant retains its separate selection and
calibration gate; this view compares independent and two-level rack-host models.

Raw latency is a saved simulated window metric in milliseconds. Residuals,
total effect, rack contribution C theta and deviation B b use log latency units.
The adjusted residual already subtracts workload regression/control reference
once. The dashboard does not subtract another reference. CPU/memory/resource-
proxy panels below remain separate existing world telemetry with their own labels.

## Freshness and evaluator separation

| State | Display meaning |
| --- | --- |
| PRE-EXPOSURE | No effect prior/posterior yet; raw public metrics can exist |
| OBSERVATIONS AVAILABLE | Eligible current observations, still uncalibrated; no healthy verdict |
| INSUFFICIENT DATA | Missing selected-host data or upstream coverage/control gate failure |
| WAITING FOR FRAMES | Stream opened, no committed output received |
| STALE STREAM | No new frame receipt for more than five wall seconds |
| DISCONNECTED | Poll failed or contact expired; retained data explicitly labeled last received |
| Saved recording | Fixed/replayed history; old event timestamps do not pretend to be live freshness |

Prediction-only posterior traces may exist during insufficient minutes. Raw
missing observations stay chart gaps, masks/quality flags remain visible and
release score is withheld when the upstream decision input is ineligible.
None of these states is colored from injected labels. Line colors identify
methods only. Frame arrival freshness is separate from model eligibility and
from the world's operational host readiness.

The four authored examples are host-local, group-wide, shared shock and recovery.
They use `dashboard-algebraic-latency-v1`, fresh registered development/smoke
seed slots, backend topology IDs and healthy-development nuisance fitting. Their
shared preperiod is identical. The stronger/weaker settings are declared,
not selected on holdouts. They are algebraic acceptance traces, not physical
resource-model detection or calibration results. Shared shock changes all hosts,
including controls; no robust-control claim is made. Original 80% canary / three
fresh controls per represented rack and pre-loading rules remain in force.

Recipes live in `examples/detector_dashboard/evaluator/recipes.json`. Only the
separately labeled Fault Lab evaluator button loads them. Monitor artifacts and
adapter imports exclude truth fields. Demo names in the sample selector are
authored descriptions; they are not inferred diagnoses or status colors.

## Verification and remaining work

`tests/test_monitor_feed.py` independently checks risk constants, intervals,
release scores, covariance, host identity, frozen stream prefixes, persistence,
world-clock separation, future-current-world frames and evaluator boundaries.
`scripts/check_detector_ui.mjs` runs the real chart renderer in a DOM harness
against real HTTP. It checks six charts, three lines, a credible band, settings,
insufficiency, staleness/recovery and disconnection/reconnection.

Browser screenshot verification was unavailable: the cloud browser could not
reach the local preview, and local Chromium could not start in this execution
environment. Laptop/mobile layout is implemented with responsive CSS but visual
rendering remains unverified. No screenshots or visual claims are fabricated.
Resource-world model adequacy, compatible policy calibration and automatic
engine-to-detector fitting/scoring remain separate work. See the checkpoint
report and raw validation for executed results and runtime details.
