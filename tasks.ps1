param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("test", "smoke", "plain-pipeline", "step-pipeline", "audit", "studies", "report")]
    [string]$Target
)

$ErrorActionPreference = "Stop"
$Py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

function Run-Cmd([string]$Cmd) {
    Write-Host ">>> $Cmd" -ForegroundColor Cyan
    Invoke-Expression $Cmd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    "test" {
        Run-Cmd "$Py -m pytest -q"
    }
    "smoke" {
        foreach ($r in @("dev", "calibration", "null_validation", "test")) {
            Run-Cmd "$Py -m canary_ssm.cli simulate --config configs/smoke.yaml --role $r --out data_smoke/$r"
        }
        Run-Cmd "$Py -m canary_ssm.cli fit --data data_smoke/dev --out artifacts_smoke/model --grid-stride 4 --allow-small-dev"
        Run-Cmd "$Py -m canary_ssm.cli calibrate --data data_smoke/calibration --model artifacts_smoke/model --out artifacts_smoke/policy"
        Run-Cmd "$Py -m canary_ssm.cli validate-null --data data_smoke/null_validation --model artifacts_smoke/model --policy artifacts_smoke/policy"
        Run-Cmd "$Py -m canary_ssm.cli evaluate --data data_smoke/test --model artifacts_smoke/model --policy artifacts_smoke/policy --out results_smoke"
    }
    "plain-pipeline" {
        $cfg = if (Test-Path "configs/plain_main.yaml") { "configs/plain_main.yaml" } else { "configs/default.yaml" }
        foreach ($r in @("dev", "calibration", "null_validation", "test")) {
            Run-Cmd "$Py -m canary_ssm.cli simulate --config $cfg --role $r --out data/plain/$r"
        }
        Run-Cmd "$Py -m canary_ssm.cli fit --data data/plain/dev --out artifacts/plain_model --cache-dir cache"
        Run-Cmd "$Py -m canary_ssm.cli calibrate --data data/plain/calibration --model artifacts/plain_model --out artifacts/plain_policy --cache-dir cache"
        Run-Cmd "$Py -m canary_ssm.cli validate-null --data data/plain/null_validation --model artifacts/plain_model --policy artifacts/plain_policy --cache-dir cache"
        Run-Cmd "$Py -m canary_ssm.cli evaluate --data data/plain/test --model artifacts/plain_model --policy artifacts/plain_policy --out results/plain_final --cache-dir cache"
    }
    "step-pipeline" {
        $cfg = if (Test-Path "configs/step_regime.yaml") { "configs/step_regime.yaml" } else { "configs/audit.yaml" }
        foreach ($r in @("dev", "calibration", "null_validation", "test")) {
            Run-Cmd "$Py -m canary_ssm.cli simulate --config $cfg --role $r --out data/step/$r"
        }
        Run-Cmd "$Py -m canary_ssm.cli fit --data data/step/dev --out artifacts/step_model --cache-dir cache"
        Run-Cmd "$Py -m canary_ssm.cli calibrate --data data/step/calibration --model artifacts/step_model --out artifacts/step_policy --cache-dir cache"
        Run-Cmd "$Py -m canary_ssm.cli validate-null --data data/step/null_validation --model artifacts/step_model --policy artifacts/step_policy --cache-dir cache"
        Run-Cmd "$Py -m canary_ssm.cli evaluate --data data/step/test --model artifacts/step_model --policy artifacts/step_policy --out results/step_final --cache-dir cache"
    }
    "audit" {
        Run-Cmd "$Py -m canary_ssm.cli audit-null --config configs/audit.yaml --model artifacts/model --policy artifacts/policy --n 500 --out results/audit"
    }
    "studies" {
        Write-Host ">>> Run study modules via: $Py -m canary_ssm.cli study <name> ..." -ForegroundColor Yellow
    }
    "report" {
        Run-Cmd "$Py -c `"from pathlib import Path; from canary_ssm.report import make_report; make_report(Path('results/final'))`""
    }
}
