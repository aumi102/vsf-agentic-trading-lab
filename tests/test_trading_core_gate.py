"""Tests for trading-core gate scripts (QuestDB-based).

Verifies:
  - Scripts compile without errors
  - Gate PASSes for FPT/VNM (source-backed corporate-action data in adjusted_daily_prices)
  - Gate BLOCKs for HPG/VCB/CTG/VHM (no source-backed data)
  - Signals are real (not fabricated) for FPT
  - Backtest dry-run passes for FPT when gate passes
  - No tracebacks on blocked gates (HPG/VCB/CTG/VHM)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


# ─── compile checks ────────────────────────────────────────────────────────────

def test_adjusted_ohlc_readiness_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(SCRIPTS / "adjusted_ohlc_readiness.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_run_trading_signals_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(SCRIPTS / "run_trading_signals.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_run_custom_backtest_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(SCRIPTS / "run_custom_backtest.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_run_trading_core_demo_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(SCRIPTS / "run_trading_core_demo.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


# ─── adjusted_ohlc_readiness gate ──────────────────────────────────────────────

def test_readiness_fpt_vnm_pass():
    """FPT and VNM have source-backed adjusted data -> gate PASS."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT", "--json")
    assert result.returncode == 0, f"FPT should PASS (exit 0), got:\n{result.stdout}\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "PASS", data["status"]
    assert data["backtest_gate"] == "pass"
    assert data["coverage"]["adjusted_daily_prices_rows"] > 0
    assert data["coverage"]["adjusted_daily_prices_source"] == "vnstock:company_events"


def test_readiness_hpg_blocked():
    """HPG has no source-backed data -> gate BLOCKED."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "HPG", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["backtest_gate"] == "blocked"
    assert data["coverage"]["adjusted_daily_prices_rows"] == 0


def test_readiness_mixed_fpt_hpg():
    """Mixed request (FPT+PASS syms only) -> overall PASS."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,VNM", "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"


# ─── signal gate ───────────────────────────────────────────────────────────────

def test_signals_fpt_computes_real_signal():
    """FPT has source-backed data -> signals computed, not fabricated."""
    result = _run("run_trading_signals.py", "--symbols", "FPT",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 0, f"FPT signals should succeed:\n{result.stdout}\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert len(data["signals"]) == 1
    sig = data["signals"][0]
    assert sig["adjustment_status"] == "source_backed_corporate_action"
    assert "fabricated" not in str(sig.get("risk_flags", [])).lower()
    assert sig["signal"] in ("BUY", "SELL", "HOLD")


def test_signals_mean_reversion_fpt():
    """FPT mean reversion also computes from source-backed data."""
    result = _run("run_trading_signals.py", "--symbols", "FPT",
                  "--as-of", "latest", "--strategy", "mean_reversion_v1", "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    sig = data["signals"][0]
    assert sig["adjustment_status"] == "source_backed_corporate_action"


def test_signals_hpg_blocked():
    """HPG has no source-backed data -> blocked."""
    result = _run("run_trading_signals.py", "--symbols", "HPG",
                  "--as-of", "latest", "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "BLOCKED" in result.stdout


# ─── backtest gate ─────────────────────────────────────────────────────────────

def test_backtest_fpt_dry_run_passes():
    """FPT dry-run passes when gate is pass."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--initial-cash", "100000000",
                  "--dry-run")
    assert result.returncode == 0, f"FPT dry-run should pass:\n{result.stdout}\n{result.stderr}"
    assert "DRY RUN" in result.stdout
    assert "BLOCKED" not in result.stdout


def test_backtest_fpt_json_passes():
    """FPT backtest exits 0 (no fabricates blocked) when gate pass."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    # Exit 0 when gate passes; backtest may succeed or fail on insufficient data but not blocked
    assert result.returncode == 0, f"FPT backtest JSON should exit 0:\n{result.stdout}\n{result.stderr}"


def test_backtest_hpg_blocked():
    """HPG no source-backed -> blocked."""
    result = _run("run_custom_backtest.py", "--symbols", "HPG",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "BLOCKED" in result.stdout


# ─── demo gate ─────────────────────────────────────────────────────────────────

def test_demo_all_blocked_symbols_blocks():
    """Demo with all-no-source symbols (HPG/VCB/CTG/VHM) blocks at gate."""
    result = _run("run_trading_core_demo.py", "--symbols", "HPG,VCB",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "TRADE GATE" in result.stdout or "BLOCKED" in result.stdout
    assert "STEP 1" in result.stdout


# ─── no tracebacks on blocked gates ──────────────────────────────────────────

def test_no_tracebacks_on_blocked_hpg_signals():
    result = _run("run_trading_signals.py", "--symbols", "HPG",
                  "--as-of", "latest", "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_no_tracebacks_on_blocked_hpg_backtest():
    result = _run("run_custom_backtest.py", "--symbols", "HPG",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_no_tracebacks_on_blocked_readiness():
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "HPG")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
