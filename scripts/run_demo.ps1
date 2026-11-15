# PowerShell runner for Virtual Data Center one-command demo
param(
    [string]$Scenario = "release_leak_two_canaries",
    [switch]$List,
    [switch]$All,
    [string]$Replay,
    [switch]$Serve,
    [switch]$Plot
)

$ErrorActionPreference = "Stop"

if ($List) {
    python scripts/demo.py --list
} elseif ($All) {
    python scripts/demo.py --all
} elseif ($Replay) {
    python scripts/demo.py --replay $Replay
} elseif ($Plot) {
    python -m canary_ssm.cli plot
} elseif ($Serve) {
    python scripts/demo.py --scenario $Scenario --serve
} else {
    python scripts/demo.py --scenario $Scenario
}
