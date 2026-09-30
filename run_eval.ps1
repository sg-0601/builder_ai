# PowerShell Helper Runner for Signalpost Evaluation
# Usage:
#   .\run_eval.ps1 --strategy decision_table_router --dry-run
#   .\run_eval.ps1 --challenger browser_fallback_v2 --dry-run

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir
$env:PYTHONPATH = "$ScriptDir;$ScriptDir\src"

python -m eval.run @args
