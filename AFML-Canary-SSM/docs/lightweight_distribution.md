# Lightweight project distribution

This checkout and the replacement ZIP contain the runnable project, required
models/policies and small fixtures. Bulk historical experiment runs are excluded.

Retained:

- All Python/JavaScript source, dashboard assets, configuration files and tests.
- Fitted research models and policy artifacts under `artifacts/`.
- World-policy and first-crossing model/policy/validation files.
- The evaluator's frozen development settings, fitted models, policy summaries
  and independent-null interval summary. Final-test inputs remain sealed.
- Small adjustment and hierarchy fixtures needed by tests and fixture generators.
- Four built-in detector dashboard demos, their catalog and evaluator recipes.
- The legacy audit model fixture and packaged recorded dashboard snapshot.

Removed:

- Individual calibration/validation run directories, per-minute score caches,
  raw telemetry exports, hidden-truth exports and replay session histories.
- Saved world, release, rollout, memory and scenario-bundle run outputs.
- Saved benchmark/performance buffers, duplicate source snapshots and generated
  result/figure directories. Existing documentation describes historical checks;
  the corresponding large datasets are no longer bundled.

`distribution_manifest.json` records the removal counts and retained example
assets. No detector, simulator, policy equation or test was changed by this
cleanup. Remaining policy compatibility checks still apply; removing old runs
neither recalibrates a policy nor turns failed audits into passing audits.

## Running the application

Use Python 3.12 and the existing tested dependency lock when reproducing the
original environment:

```sh
python -m pip install -r requirements-world-policy.lock
python -m pip install -e . --no-deps
python -m canary_ssm world-dashboard --config configs/world_console.yaml --port 8765 --state-dir runtime/integrated-console
```

The simulator creates fresh observations when it runs. Explicit exports, saved
history and experiment commands can still generate new run data. These outputs
are ignored by Git; deleting old exports does not disable live monitoring.

Offline report/replay commands that need historical run inputs require freshly
generated data or restoration of the full research archive. Use a fresh output
directory and the documented role/seed protocol for a new study. Do not claim
that the retained summary files alone reproduce the removed raw audit dataset.

## Repository history

This is a normal cleanup commit. The current branch and downloadable source ZIP
are smaller. The earlier full-import commit remains in Git history, so a complete
clone can still download the old data. History was not rewritten or force-pushed.

## Cleanup validation

The simulator/API smoke check, all four built-in detector playback demos and
all four fitted adjustment/hierarchy fixture models loaded successfully. Source,
tests, configs and retained fixture contents match the full-import commit.

The current host test run had 616 passes and 9 failures: eight existing disk-budget
guards stopped generation because host usage exceeds 90%; one recorded fixture
compares Linux runtime metadata against the current macOS runtime. No missing-file
failures occurred, and no tests or safety guards were weakened.
