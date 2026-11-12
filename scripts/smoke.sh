#!/usr/bin/env bash
# Pipeline plumbing check (~5 min CPU). Reports NO accuracy; strided grids are for speed only.
set -euo pipefail
C=configs/smoke.yaml; D=data_smoke; A=artifacts_smoke
for r in dev calibration null_validation test; do python -m canary_ssm.cli simulate --config $C --role $r --out $D/$r; done
python -m canary_ssm.cli fit --data $D/dev --out $A/model --grid-stride 4
python -m canary_ssm.cli calibrate --data $D/calibration --model $A/model --out $A/policy
python -m canary_ssm.cli validate-null --data $D/null_validation --model $A/model --policy $A/policy
python -m canary_ssm.cli evaluate --data $D/test --model $A/model --policy $A/policy --out results_smoke
