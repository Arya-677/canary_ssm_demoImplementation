# Legacy reproduction test: missing-model fix

## Cause and repair

`test_experiment7_legacy_reproduction` consumes
`data_audit/model_pooled_dev`. The original audit workflow creates this model
in `scripts/audit_quick.sh`, but `.gitignore` excluded the entire `data_*/`
tree. The supplied archive therefore lacked its required `model_config.json`
and `nuisance_main.json`. This was a missing test dependency, not a Kalman or
dashboard defect.

Added the small generated frozen audit model at that exact path. It was built
by executing the existing simulator and fitter, with the audit script's
30-development-pair recipe, `sd_host=0.02`, declared frozen effect parameters,
and `beta_mode=pooled_dev`. Nuisance fitting uses the 30 healthy development
rollouts; the generated data role and registered seed ranges are saved in
`generation_manifest.json`. Raw rollout files were generated in a temporary
directory and removed after fitting.

This is a **newly generated audit/test fixture**, not a claim to have recovered
the original historical model bytes or reproduced historical benchmark numbers.
It retains `kind=frozen` and `frozen=true`; the existing tuned-model checks and
missing-artifact errors remain active. Existing inference, model/policy artifacts
under `artifacts/`, and all previously present tests are unchanged.

## Rebuild and provenance

The archive includes the fitted files, so a normal test run needs no setup step.
To generate another copy without overwriting the bundled fixture:

```bash
python -m scripts.prepare_legacy_audit_fixture --out /tmp/canary-audit-model
```

The default output is `data_audit/model_pooled_dev`; the helper refuses any
nonempty existing output directory. `configs/legacy_audit_fixture.yaml` is the
explicit recipe. The generation manifest records its hash, source hashes,
development-data manifest and hashes of all generated model files. The fitter
also saves its usual convergence diagnostics and environment manifest.

`.gitignore` now allows only the small JSON/YAML/CSV files in this one fixture
directory. Bulk rollout data, caches, other audit output and `.npz` files stay
ignored. The fixed archive explicitly includes these files, preventing the
same packaging omission from recurring.

## Verification

Executed with the local audit Python environment from the repository root:

```bash
python -m scripts.prepare_legacy_audit_fixture
python -m pytest -q tests/test_p1_protocol.py::test_experiment7_legacy_reproduction tests/test_legacy_audit_fixture.py
python -m pytest -q
```

Focused result: `4 passed in 4.97s`, including the unchanged original failing
test. New checks verify genuine frozen/development provenance, successful
optimizer starts, file hashes, missing-path rejection and no overwriting of
existing model files. The same focused tests passed from a fresh extraction of
the fixed ZIP: `4 passed in 5.55s`, verifying that the small model ships correctly.

No detector benchmark claims, replacement thresholds, test skips or relaxed
assertions were introduced. The full suite passed: **259 passed in 71.71s**.
Raw focused/full results, packaging checks and file hashes are recorded in
`docs/wp/legacy_fix_validation.json`. The project is still an extracted ZIP without
`.git`, so no commit/merge is claimed.

Suggested commit: `fix: include reproducible legacy audit model fixture`.
