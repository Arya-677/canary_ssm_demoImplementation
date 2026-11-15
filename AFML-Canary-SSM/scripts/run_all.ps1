# Full statistical-track benchmark on Windows PowerShell. Run from repo root with the venv active.
# Order matters: dev -> fit -> calibration -> calibrate -> null_validation -> validate -> test -> evaluate.
$ErrorActionPreference = "Stop"
$cfg = "configs/plain_main.yaml"
python -m pytest -q
foreach ($role in "dev","calibration","null_validation","test") {
  python -m canary_ssm.cli simulate --config $cfg --role $role --out "data/$role"
}
python -m canary_ssm.cli fit           --data data/dev --out artifacts/model          # ~30-60 min CPU
python -m canary_ssm.cli calibrate     --data data/calibration --model artifacts/model --out artifacts/policy
python -m canary_ssm.cli validate-null --data data/null_validation --model artifacts/model --policy artifacts/policy
python -m canary_ssm.cli evaluate      --data data/test --model artifacts/model --policy artifacts/policy --out results/final
python -m canary_ssm.cli audit-null --config configs/audit.yaml --model artifacts/model --policy artifacts/policy --n 500 --out results/audit
python -m canary_ssm.cli benchmark --out results/runtime_scaling.csv
# Noise sweep (0.01/0.02/0.04), same frozen model+policy; never tune on it:
python -m canary_ssm.cli simulate --config configs/noise_sweep.yaml --role test --out data/noise_sweep
python -m canary_ssm.cli evaluate --data data/noise_sweep --model artifacts/model --policy artifacts/policy --out results/noise_sweep
# Stress suite (never tune on it): 
python -m canary_ssm.cli simulate --config configs/stress.yaml --role test --out data/stress
python -m canary_ssm.cli evaluate --data data/stress --model artifacts/model --policy artifacts/policy --out results/stress
