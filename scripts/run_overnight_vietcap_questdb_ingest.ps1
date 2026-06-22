<#
.SYNOPSIS
  External overnight/resume runner for the Vietcap -> QuestDB OHLCV ingest.

  Runs the operator-safe batch ingester in rounds until the row/symbol target is
  reached or MaxRounds is hit. Handles the ingester's clean throttle-stop (exit 75)
  by sleeping CooldownMinutes and resuming. Does NOT hammer the endpoint.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_overnight_vietcap_questdb_ingest.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run_overnight_vietcap_questdb_ingest.ps1 -MaxRounds 1 -CooldownMinutes 1
#>
[CmdletBinding()]
param(
    [int]    $CooldownMinutes = 30,
    [int]    $MaxRounds       = 30,
    [long]   $TargetRows      = 3000000,
    [int]    $TargetSymbols   = 1500,
    [int]    $BatchSize       = 10,
    [double] $SleepJitterMin  = 2,
    [double] $SleepJitterMax  = 5,
    [string] $QuestDbUrl      = "http://localhost:9000"
)

$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"

# --- Repo root + python ---
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($env:PY_INTERP) { $Py = $env:PY_INTERP }
else { $Py = "C:\Users\NguyenDucHoangPhuc\.conda\envs\vsf-trading\python.exe" }
if (-not (Test-Path $Py)) {
    Write-Error "Python interpreter not found: $Py. Set `$env:PY_INTERP and retry."
    exit 1
}

# --- Log file (timestamped) ---
$LogDir = Join-Path $RepoRoot "logs\questdb_ingest"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir ("overnight_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Write-Log([string]$Message) {
    "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message | Tee-Object -FilePath $LogFile -Append
}

# --- QuestDB helpers ---
function Get-State {
    $uri = "$QuestDbUrl/exec?query=" + [uri]::EscapeDataString("SELECT count(), count_distinct(symbol) FROM daily_prices")
    try {
        $r = Invoke-RestMethod -Uri $uri -TimeoutSec 30
        return [pscustomobject]@{ Rows = [long]$r.dataset[0][0]; Symbols = [int]$r.dataset[0][1] }
    } catch {
        return [pscustomobject]@{ Rows = -1; Symbols = -1 }
    }
}

Write-Log "=== overnight runner start ==="
Write-Log "python=$Py"
Write-Log "log=$LogFile"
Write-Log "params: MaxRounds=$MaxRounds CooldownMinutes=$CooldownMinutes TargetRows=$TargetRows TargetSymbols=$TargetSymbols BatchSize=$BatchSize jitter=$SleepJitterMin..$SleepJitterMax"

# --- Verify QuestDB is up ---
try {
    $ping = Invoke-RestMethod -Uri ("$QuestDbUrl/exec?query=" + [uri]::EscapeDataString("SELECT 1")) -TimeoutSec 15
    if ([int]$ping.dataset[0][0] -ne 1) { Write-Log "ERROR: QuestDB did not answer SELECT 1."; exit 1 }
} catch {
    Write-Log "ERROR: cannot reach QuestDB at $QuestDbUrl ($_)."; exit 1
}
Write-Log "QuestDB OK at $QuestDbUrl"

$ingestArgs = @(
    "scripts\batch_ingest_vietcap_ohlcv_to_questdb.py",
    "--resume", "--only-missing",
    "--batch-size", "$BatchSize",
    "--sleep-jitter-min", "$SleepJitterMin",
    "--sleep-jitter-max", "$SleepJitterMax",
    "--max-consecutive-rate-limits", "5",
    "--stop-on-rate-limit"
)

$reached = $false
for ($round = 1; $round -le $MaxRounds; $round++) {
    Write-Log "---------- round $round / $MaxRounds ----------"

    $state = Get-State
    Write-Log "current: rows=$($state.Rows) distinct_symbols=$($state.Symbols)"
    if ($state.Rows -ge $TargetRows -or $state.Symbols -ge $TargetSymbols) {
        Write-Log "TARGET REACHED (rows>=$TargetRows or symbols>=$TargetSymbols). Stopping."
        $reached = $true
        break
    }

    Write-Log "running status snapshot ..."
    & $Py "scripts\questdb_ingest_status.py" 2>&1 | Tee-Object -FilePath $LogFile -Append

    Write-Log "running batch ingest round $round ..."
    & $Py $ingestArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
    $code = $LASTEXITCODE
    Write-Log "batch ingest exit code = $code"

    if ($code -eq 0) {
        $state = Get-State
        Write-Log "after pass: rows=$($state.Rows) distinct_symbols=$($state.Symbols)"
        if ($state.Rows -ge $TargetRows -or $state.Symbols -ge $TargetSymbols) {
            Write-Log "TARGET REACHED. Stopping."
            $reached = $true
            break
        }
        Write-Log "pass completed without throttle; continuing immediately."
        continue
    }
    elseif ($code -eq 75) {
        if ($round -lt $MaxRounds) {
            Write-Log "throttled (exit 75); sleeping $CooldownMinutes minute(s) then resuming ..."
            Start-Sleep -Seconds ([int]($CooldownMinutes * 60))
        } else {
            Write-Log "throttled (exit 75) on final round; not sleeping. Re-run later to continue."
        }
        continue
    }
    else {
        Write-Log "ERROR: batch ingest failed with exit code $code. Stopping."
        exit $code
    }
}

$final = Get-State
Write-Log "=== overnight runner end ==="
Write-Log "final: rows=$($final.Rows) distinct_symbols=$($final.Symbols) target_reached=$reached"
if ($reached) { exit 0 } else { exit 75 }
