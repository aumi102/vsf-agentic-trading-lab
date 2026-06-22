@echo off
REM Overnight/resume runner for Vietcap -> QuestDB ingest.
REM Forwards all args to the PowerShell runner, e.g.:
REM   scripts\run_overnight_vietcap_questdb_ingest.bat
REM   scripts\run_overnight_vietcap_questdb_ingest.bat -MaxRounds 10 -CooldownMinutes 20
powershell -ExecutionPolicy Bypass -File "%~dp0run_overnight_vietcap_questdb_ingest.ps1" %*
exit /b %ERRORLEVEL%
