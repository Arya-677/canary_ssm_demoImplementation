#!/usr/bin/env bash
# Frozen-parameter calibration audit (declared values, NO tuning). Compares beta modes. ~15-25 min on one CPU core.
set -euo pipefail
D=data_audit; mkdir -p $D
cat > $D/calib.yaml <<'EOF'
sim: {sd_host: 0.02}
roles: {dev: {pairs: 30}, calibration: {pairs: 500}}
families: [{name: plain, overrides: {}}]
EOF
python -m canary_ssm.cli simulate --config $D/calib.yaml --role dev --out $D/dev
python -m canary_ssm.cli simulate --config $D/calib.yaml --role calibration --out $D/cal
M=matched_contrast,adj_cusum,topk_cusum,pooled_ssm,indep_ssm,hier_ssm
for BM in pre pooled_dev; do
  python -m canary_ssm.cli fit --data $D/dev --out $D/model_$BM --methods $M --frozen --beta-mode $BM
  python -m canary_ssm.cli calibrate --data $D/cal --model $D/model_$BM --out $D/policy_$BM
  python -m canary_ssm.cli audit-null --config configs/audit.yaml --model $D/model_$BM --policy $D/policy_$BM --n 500 --out $D/audit_$BM
done
python scripts/summarize_audit.py "beta_mode=pre::$D/audit_pre/table_audit_null.csv" "beta_mode=pooled_dev::$D/audit_pooled_dev/table_audit_null.csv"
