"""Tests for trading-core gate scripts (QuestDB-based).

Verifies:
  - Scripts compile without errors
  - Blocked output is deterministic and machine-parseable
  - Gate blocks signal generation and backtest on fabricated adjusted feed
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

def test_readiness_reports_blocked_fabricated():
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,HPG,VCB")
    assert result.returncode == 1
    assert "BLOCKED_ADJUSTED_FACTOR_FABRICATED" in result.stdout
    assert "backtest_gate" in result.stdout
    assert "blocked" in result.stdout
    assert "26" not in result.stdout or "warn" in result.stdout  # has row counts


def test_readiness_json_parsable():
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "BLOCKED_ADJUSTED_FACTOR_FABRICATED"
    assert data["backtest_gate"] == "blocked"
    assert data["symbols"] == ["FPT"]
    assert isinstance(data["coverage"], dict)
    assert data["coverage"]["warn_rows"] > 0
    assert data["coverage"]["real_factor_rows"] == 0


def test_readiness_all_6_demo_symbols_blocked():
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,HPG,VCB,CTG,VNM,VHM", "--json")
    data = json.loads(result.stdout)
    for sym in ["FPT", "HPG", "VCB", "CTG", "VNM", "VHM"]:
        sym_data = next((s for s in data["by_symbol"] if s["symbol"] == sym), None)
        assert sym_data is not None, f"{sym} missing from by_symbol"
        assert sym_data["backtest_gate"] == "blocked"
        assert sym_data["warn_rows"] > 0
        assert sym_data["real_factor_rows"] == 0


# ─── signal gate ───────────────────────────────────────────────────────────────

def test_signals_blocked_on_fabricated_feed():
    result = _run("run_trading_signals.py", "--symbols", "FPT,HPG,VCB",
                  "--as-of", "latest", "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "SIGNAL_BLOCKED_ADJUSTED_FACTOR_FABRICATED" in result.stdout


def test_signals_mean_reversion_blocked():
    result = _run("run_trading_signals.py", "--symbols", "FPT,HPG",
                  "--as-of", "latest", "--strategy", "mean_reversion_v1")
    assert result.returncode == 1
    assert "BLOCKED" in result.stdout


def test_signals_json_blocked_parsable():
    result = _run("run_trading_signals.py", "--symbols", "FPT",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert "BLOCKED" in data["status"]
    assert data["gate"] == "blocked"
    assert isinstance(data["caveats"], list)


# ─── backtest gate ─────────────────────────────────────────────────────────────

def test_backtest_blocked_on_fabricated_feed():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--initial-cash", "100000000")
    assert result.returncode == 1
    assert "BACKTEST_BLOCKED_ADJUSTED_FACTOR_FABRICATED" in result.stdout


def test_backtest_dry_run_blocked():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--initial-cash", "100000000",
                  "--dry-run")
    assert result.returncode == 1
    assert "BLOCKED" in result.stdout


def test_backtest_json_blocked_parsable():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert "BLOCKED" in data["status"]
    assert data["gate"] == "blocked"


# ─── demo gate ─────────────────────────────────────────────────────────────────

def test_demo_blocks_at_gate():
    result = _run("run_trading_core_demo.py", "--symbols", "FPT,HPG,VCB",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "BLOCKED_ADJUSTED_FACTOR_FABRICATED" in result.stdout
    assert "STEP 1" in result.stdout
    assert "TRADE GATE" in result.stdout
    assert "Need source-backed adjusted price" in result.stdout


def test_demo_json_blocks_parsable():
    result = _run("run_trading_core_demo.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert "BLOCKED" in data["status"]
    assert "next_action" in data
    assert "source-backed" in data["next_action"].lower()


# ─── no tracebacks ─────────────────────────────────────────────────────────────

BLOCKED_SCRIPTS = [
    ("adjusted_ohlc_readiness.py", ["--symbols", "FPT"]),
    ("run_trading_signals.py", ["--symbols", "FPT", "--as-of", "latest", "--strategy", "momentum_v1"]),
    ("run_custom_backtest.py", ["--symbols", "FPT", "--from", "2021-01-01", "--to", "2025-12-31",
                                "--strategy", "momentum_v1"]),
    ("run_trading_core_demo.py", ["--symbols", "FPT", "--from", "2021-01-01", "--to", "2025-12-31",
                                  "--strategy", "momentum_v1"]),
]


def test_no_tracebacks_on_blocked_gate():
    """All gate scripts must exit cleanly (exit 1, no traceback) when blocked."""
    for script, args in BLOCKED_SCRIPTS:
        result = _run(script, *args)
        assert result.returncode == 1, f"{script} should exit 1 when blocked"
        assert "Traceback" not in result.stderr, f"{script} should not emit Traceback\n{result.stderr}"