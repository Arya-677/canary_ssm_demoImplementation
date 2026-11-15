# Detector dashboard checkpoint

14 November 2026. Extends `canary_ssm_nested_hierarchy.zip`.

The existing Monitoring view now reads saved/incrementally streamed Gaussian
outputs through a validated backend adapter. It shows raw latency, residual,
effect uncertainty, host risk, rack effect and host deviation, with independent
and weaker/stronger pooling comparisons on one observation replay. Backend IDs,
source/run clocks, data masks and calibration state remain explicit.

## Executed validation

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` | 480 passed, 1 warning in 76.83s (0:01:16) |
| `python -m pytest -q tests/test_monitor_feed.py tests/test_dashboard.py` | 41 passed, 1 warning in 3.68s |
| `python -m canary_ssm.detector_dashboard_fixture` | Four case gates and the positive/ordered pooling gate passed |
| `node --check` on app, detector renderer and UI harness | All exit 0 |
| `scripts/check_detector_ui.mjs` with real HTTP server | Eleven computed DOM/API gates passed |
| `monitor_stream` CLI with frames 100–102 | Three frames delivered; world tick remains zero |
| Browser visual check | Unverified; local preview inaccessible to cloud browser and local Chromium startup blocked |

The browser limitation is recorded rather than replaced with a screenshot claim.
Responsive CSS implements two-column laptop charts and a narrow-screen layout;
actual browser/device rendering remains unverified. A preexisting environment-
bound world snapshot was regenerated with its documented command after the
Python/NumPy/platform change. A first full run lacked the declared optional
`tabulate` reporting dependency; installing it resolved that failure. No original
test was modified, weakened or skipped. One external pytest-plugin deprecation
warning remains. Raw validation is `detector_dashboard_validation.json`.

## Computed pooling settings

This table is generated from `examples/detector_dashboard/pooling_settings.csv`.
For two monitored hosts per rack, shared prior covariance is sigma_group squared
minus sigma_deviation squared/2. Both settings share positive covariance; the
strong setting has a larger prior pair correlation. These are declared parameter
properties, not detector power or calibration results.

| Setting | Prior within-rack pair correlation | Effect innovation pair covariance |
| --- | --- | --- |
| weak | 0.16279069767441873 | 1.0000000000000006e-06 |
| strong | 0.9393939393939394 | 3.55e-05 |

`summary.csv` records the four fixture lengths, monitored cohort size and input
eligibility counts. All methods use the same frame/prefix hash. The fixtures
use healthy-development nuisance fitting and fresh registered development/smoke
slots, with a separate algebraic generator ID and evaluator-only recipes. No
threshold/null/final role is fitted or evaluated here.

## Behavior and boundaries

The backend computes P(effect>log(1.02)) from the effect covariance, and max host
risk is labeled release score, not joint release probability. No old policy is
assumed compatible with this probability-scale display. Missing/preperiod/stale/
disconnected states never become healthy verdicts; score is withheld for
ineligible inputs. All methods are uncalibrated and no automated action is added.

Streaming is an authenticated append-only output API. Its tested CLI example
streams saved posteriors; a real live producer must fit/freeze the correct world
protocol and publish causal committed outputs through the same interface.
Opening the dashboard does not create such a model. Current-world connection
is only shown for a matching-run external feed; a different-run recording has
its own clear clock/source. The nested prototype's separate gate is unchanged.

New files are the feed adapter, generator, stream CLI, evaluator reader, detector
renderer, UI harness, tests, docs and saved artifacts. Existing dashboard/API
and web assets are updated. No inference, simulator, research metric or existing
fitted model source is rewritten. Session exports preserve loaded output artifacts
and cursors; reset clears the feed. The source is an extracted ZIP, with no git
commit or merge claim. Compatible calibration, automatic resource-world scoring
and visual browser verification remain explicit next patches.
