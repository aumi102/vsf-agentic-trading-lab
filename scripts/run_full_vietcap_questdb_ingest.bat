@echo off
setlocal enabledelayedexpansion

REM Full Vietcap universe -> QuestDB daily OHLCV ingestion (sequential, no async).
REM Usage:
REM   scripts\run_full_vietcap_questdb_ingest.bat
REM   scripts\run_full_vietcap_questdb_ingest.bat --limit-symbols 30
REM   scripts\run_full_vietcap_questdb_ingest.bat --symbols FPT,VNM,VCB
REM   scripts\run_full_vietcap_questdb_ingest.bat --batch-size 10
REM Any extra args are forwarded to the ingest script (later args override defaults).

cd /d "%~dp0.."

if defined PY_INTERP (
  set "PY=%PY_INTERP%"
) else (
  set "PY=C:\Users\NguyenDucHoangPhuc\.conda\envs\vsf-trading\python.exe"
)
if not exist "!PY!" (
  echo ERROR: Python interpreter not found: !PY!
  echo Set PY_INTERP to your python.exe and retry.
  exit /b 1
)
echo Using Python: !PY!

set "QDB=%QUESTDB_URL%"
if "!QDB!"=="" set "QDB=http://localhost:9000"

echo Checking QuestDB at !QDB! ...
curl -s -f -o nul "!QDB!/exec?query=SELECT%%201"
if errorlevel 1 (
  echo ERROR: QuestDB did not answer SELECT 1 at !QDB!. Is QuestDB running?
  exit /b 1
)
echo QuestDB OK.

echo === Step 1/2: fetch full Vietcap universe ===
"!PY!" scripts\fetch_vietcap_universe.py
if errorlevel 1 (
  echo ERROR: universe fetch failed.
  exit /b 1
)

echo === Step 2/2: batch-ingest daily OHLCV into QuestDB (operator-safe) ===
"!PY!" scripts\batch_ingest_vietcap_ohlcv_to_questdb.py ^
  --questdb-url "!QDB!" ^
  --from-date 2000-01-01 ^
  --to-date today ^
  --batch-size 10 ^
  --table daily_prices ^
  --resume ^
  --only-missing ^
  --retry-failed ^
  --sleep-jitter-min 2 ^
  --sleep-jitter-max 5 ^
  --max-consecutive-rate-limits 5 ^
  --stop-on-rate-limit %*
REM exit code 75 = stopped cleanly on sustained rate limiting (not a failure).
if errorlevel 75 (
  echo NOTE: ingest stopped cleanly due to sustained Vietcap rate limiting.
  echo       Progress is checkpointed. Wait for the throttle window, then re-run this same command to continue.
  endlocal
  exit /b 75
)
if errorlevel 1 (
  echo ERROR: batch ingest failed.
  exit /b 1
)

echo Done.
endlocal
