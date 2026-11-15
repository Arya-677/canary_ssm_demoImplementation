#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:?Usage: $0 {test|smoke|plain-pipeline|step-pipeline|audit|studies|report}}"
PY="${PYTHON:-python}"

run() { echo ">>> $*"; "$@"; }

case "$TARGET" in
  test)
    run "$PY" -m pytest -q
    ;;
  smoke)
    for r in dev calibration null_validation test; do
      run "$PY" -m canary_ssm.cli simulate --config configs/smoke.yaml --role "$r" --out "data_smoke/$r"
    done
    run "$PY" -m canary_ssm.cli fit --data data_smoke/dev --out artifacts_smoke/model --grid-stride 4 --allow-small-dev
    run "$PY" -m canary_ssm.cli calibrate --data data_smoke/calibration --model artifacts_smoke/model --out artifacts_smoke/policy
    run "$PY" -m canary_ssm.cli validate-null --data data_smoke/null_validation --model artifacts_smoke/model --policy artifacts_smoke/policy
    run "$PY" -m canary_ssm.cli evaluate --data data_smoke/test --model artifacts_smoke/model --policy artifacts_smoke/policy --out results_smoke
    ;;
  plain-pipeline)
    CFG="configs/plain_main.yaml"; [[ -f "$CFG" ]] || CFG="configs/default.yaml"
    for r in dev calibration null_validation test; do
      run "$PY" -m canary_ssm.cli simulate --config "$CFG" --role "$r" --out "data/plain/$r"
    done
    run "$PY" -m canary_ssm.cli fit --data data/plain/dev --out artifacts/plain_model --cache-dir cache
    run "$PY" -m canary_ssm.cli calibrate --data data/plain/calibration --model artifacts/plain_model --out artifacts/plain_policy --cache-dir cache
    run "$PY" -m canary_ssm.cli validate-null --data data/plain/null_validation --model artifacts/plain_model --policy artifacts/plain_policy --cache-dir cache
    run "$PY" -m canary_ssm.cli evaluate --data data/plain/test --model artifacts/plain_model --policy artifacts/plain_policy --out results/plain_final --cache-dir cache
    ;;
  step-pipeline)
    CFG="configs/step_regime.yaml"; [[ -f "$CFG" ]] || CFG="configs/audit.yaml"
    for r in dev calibration null_validation test; do
      run "$PY" -m canary_ssm.cli simulate --config "$CFG" --role "$r" --out "data/step/$r"
    done
    run "$PY" -m canary_ssm.cli fit --data data/step/dev --out artifacts/step_model --cache-dir cache
    run "$PY" -m canary_ssm.cli calibrate --data data/step/calibration --model artifacts/step_model --out artifacts/step_policy --cache-dir cache
    run "$PY" -m canary_ssm.cli validate-null --data data/step/null_validation --model artifacts/step_model --policy artifacts/step_policy --cache-dir cache
    run "$PY" -m canary_ssm.cli evaluate --data data/step/test --model artifacts/step_model --policy artifacts/step_policy --out results/step_final --cache-dir cache
    ;;
  audit)
    run "$PY" -m canary_ssm.cli audit-null --config configs/audit.yaml --model artifacts/model --policy artifacts/policy --n 500 --out results/audit
    ;;
  studies)
    echo ">>> Run study modules via: $PY -m canary_ssm.cli study <name> ..."
    ;;
  report)
    run "$PY" -c "from pathlib import Path; from canary_ssm.report import make_report; make_report(Path('results/final'))"
    ;;
  *)
    echo "Unknown target: $TARGET" >&2; exit 2
    ;;
esac
