# Overnight / resumable Vietcap FA full-universe ingester (PowerShell).
# Sequential, low-concurrency, no secrets. Override RUN_ID via parameter.
#
# How to stop safely:
#   Press Ctrl-C in this window.  Then re-run the printed resume_command.
#
# Coverage check after:
#   python scripts\questdb_fa_coverage.py

param(
    [string]$RunId = "FA_FULL_UNIVERSE_OVERNIGHT"
)

$ErrorActionPreference = "Stop"
Set-Location -Path (Join-Path $PSScriptRoot "..")

Write-Host "=== Overnight Vietcap FA full-universe ingester ==="
Write-Host "run_id=$RunId"
Write-Host ""
Write-Host "Stop safely : Ctrl-C, then re-run the resume_command printed below."
Write-Host "Coverage    : python scripts\questdb_fa_coverage.py"
Write-Host ""

python scripts\batch_ingest_vietcap_fa_full_universe.py `
    --run-id $RunId `
    --only-missing --resume `
    --sleep-seconds 2 --jitter-seconds 1 `
    --stop-on-rate-limit `
    --max-consecutive-failures 10 `
    --max-symbols 0 `
    --write-summary-json data\cache\fa_overnight_summary.json

Write-Host ""
Write-Host "=== Done. Coverage snapshot: ==="
python scripts\questdb_fa_coverage.py
