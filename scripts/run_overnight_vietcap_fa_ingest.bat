@echo off
REM Overnight / resumable Vietcap FA full-universe ingester.
REM Sequential, low-concurrency, no secrets. Edit RUN_ID only if you want.
REM
REM How to stop safely:
REM   Press Ctrl-C in this window.  Then re-run the printed resume_command.
REM
REM Coverage check after:
REM   python scripts\questdb_fa_coverage.py

setlocal

set "RUN_ID=FA_FULL_UNIVERSE_OVERNIGHT"
if not "%~1"=="" set "RUN_ID=%~1"

cd /d "%~dp0\.."

echo === Overnight Vietcap FA full-universe ingester ===
echo run_id=%RUN_ID%
echo.
echo Stop safely : Ctrl-C, then re-run the resume_command printed below.
echo Coverage    : python scripts\questdb_fa_coverage.py
echo.

python scripts\batch_ingest_vietcap_fa_full_universe.py ^
  --run-id %RUN_ID% ^
  --only-missing --resume ^
  --sleep-seconds 2 --jitter-seconds 1 ^
  --stop-on-rate-limit ^
  --max-consecutive-failures 10 ^
  --max-symbols 0 ^
  --write-summary-json data\cache\fa_overnight_summary.json

echo.
echo === Done. Coverage snapshot: ===
python scripts\questdb_fa_coverage.py
endlocal
