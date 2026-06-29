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


def test_readiness_mixed_fpt_vnm_all_pass():
    """FPT+VNM (all PASS) -> overall PASS."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,VNM", "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "PASS"
    assert data["backtest_gate"] == "pass"


def test_readiness_mixed_fpt_hpg_vcb_vnm_partial():
    """Mixed FPT+VNM+HPG+VCB -> overall PARTIAL."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,HPG,VCB,VNM", "--json")
    # PARTIAL without --require-all -> exit 0
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "PARTIAL"
    assert data["backtest_gate"] == "partial"
    pass_syms = [s["symbol"] for s in data["by_symbol"] if s["status"] == "PASS"]
    block_syms = [s["symbol"] for s in data["by_symbol"] if s["status"] == "BLOCKED"]
    assert set(pass_syms) == {"FPT", "VNM"}, f"Expected FPT+VNM PASS, got {pass_syms}"
    assert set(block_syms) == {"HPG", "VCB"}, f"Expected HPG+VCB BLOCKED, got {block_syms}"
    for s in data["by_symbol"]:
        if s["status"] == "BLOCKED":
            assert s["blocked_reason"] is not None
            assert len(s["blocked_reason"]) > 20


def test_readiness_require_all_fails_for_partial():
    """PARTIAL + --require-all -> exit 1."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,HPG,VCB,VNM",
                  "--json", "--require-all")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "PARTIAL"
    assert data["backtest_gate"] == "partial"


# ─── signal gate ───────────────────────────────────────────────────────────────

def test_signals_fpt_computes_real_signal():
    """FPT has source-backed data -> signals computed from adjusted_daily_prices."""
    result = _run("run_trading_signals.py", "--symbols", "FPT",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 0, f"FPT signals should succeed:\n{result.stdout}\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert len(data["signals"]) == 1
    sig = data["signals"][0]
    assert sig["adjustment_status"] == "source_backed_corporate_action"
    assert sig["data_source"] == "adjusted_daily_prices"
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
    """HPG has no source-backed data -> blocked with precise reason."""
    result = _run("run_trading_signals.py", "--symbols", "HPG",
                  "--as-of", "latest", "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "BLOCKED" in result.stdout


def test_signals_mixed_partial():
    """FPT+HPG+VCB+VNM -> PARTIAL with both computed and blocked records."""
    result = _run("run_trading_signals.py", "--symbols", "FPT,HPG,VCB,VNM",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    # PARTIAL -> exit 0
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "partial"
    sigs = {s["symbol"]: s for s in data["signals"]}
    assert sigs["FPT"]["signal"] in ("BUY", "SELL", "HOLD")
    assert sigs["FPT"]["gate"] == "pass"
    assert sigs["FPT"]["data_source"] == "adjusted_daily_prices"
    assert sigs["VNM"]["signal"] in ("BUY", "SELL", "HOLD")
    assert sigs["VNM"]["gate"] == "pass"
    assert sigs["HPG"]["signal"] == "BLOCKED"
    assert sigs["HPG"]["gate"] == "blocked"
    assert sigs["HPG"]["data_source"] is None
    assert sigs["VCB"]["signal"] == "BLOCKED"
    assert sigs["VCB"]["gate"] == "blocked"


def test_signals_require_all_fails_for_partial():
    """PARTIAL + --require-all -> exit 1."""
    result = _run("run_trading_signals.py", "--symbols", "FPT,HPG,VCB,VNM",
                  "--as-of", "latest", "--strategy", "momentum_v1",
                  "--json", "--require-all")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "PARTIAL_BLOCKED"


def test_signals_no_raw_fallback():
    """HPG blocked must NOT use daily_prices as adjusted source.

    When all symbols blocked, script returns PARTIAL_BLOCKED error JSON.
    When mixed, blocked symbols return signal=BLOCKED with data_source=null.
    In either case, no raw daily_prices data may be used.
    """
    result = _run("run_trading_signals.py", "--symbols", "HPG",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    # All-blocked path: no signals array, error message only
    assert data.get("status") in ("PARTIAL_BLOCKED", "blocked")
    # Must not claim to have used daily_prices as adjusted source
    assert "daily_prices" not in str(data.get("error", "")), (
        "HPG blocked signal must not reference daily_prices as adjusted source"
    )


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
    """FPT backtest exits 0 when gate passes."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 0, f"FPT backtest JSON should exit 0:\n{result.stdout}\n{result.stderr}"


def test_backtest_hpg_all_blocked():
    """HPG only -> all blocked."""
    result = _run("run_custom_backtest.py", "--symbols", "HPG",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "BLOCKED"


def test_backtest_mixed_partial():
    """FPT+HPG+VCB+VNM -> PARTIAL."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT,HPG,VCB,VNM",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "partial"
    res = {r["symbol"]: r for r in data["results"]}
    assert res["FPT"]["gate"] == "pass"
    assert res["VNM"]["gate"] == "pass"
    assert res["HPG"]["gate"] == "blocked"
    assert res["VCB"]["gate"] == "blocked"
    # Pass symbols must not use raw daily_prices
    assert res["FPT"]["data_source"] == "adjusted_daily_prices"


def test_backtest_require_all_fails_for_partial():
    """PARTIAL + --require-all -> exit 1."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT,HPG,VCB,VNM",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json", "--require-all")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "PARTIAL_BLOCKED"


def test_backtest_baseline_fpt_produces_trades():
    """baseline_buy_hold_v1 produces BUY + SELL trades for FPT."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "baseline_buy_hold_v1",
                  "--initial-cash", "100000000", "--json")
    assert result.returncode == 0, f"Baseline backtest should succeed:\n{result.stdout}\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    res = data["results"][0]
    assert res["gate"] == "pass"
    assert res["data_source"] == "adjusted_daily_prices"
    trades = res["trade_ledger"]
    assert len(trades) >= 2, f"Expected >=2 trades (BUY+SELL), got {len(trades)}: {trades}"
    sides = [t["side"] for t in trades]
    assert "BUY" in sides and "SELL" in sides
    metrics = res["metrics"]
    assert "sharpe_ratio" in metrics
    assert "sortino_ratio" in metrics
    assert "profit_factor" in metrics
    assert "max_drawdown_pct" in metrics
    assert "total_return_pct" in metrics
    assert "cost_slippage_assumptions" in metrics


def test_backtest_baseline_vnm_produces_trades():
    """baseline_buy_hold_v1 produces BUY + SELL trades for VNM."""
    result = _run("run_custom_backtest.py", "--symbols", "VNM",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "baseline_buy_hold_v1",
                  "--initial-cash", "100000000", "--json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    res = data["results"][0]
    assert res["gate"] == "pass"
    trades = res["trade_ledger"]
    assert len(trades) >= 2
    sides = [t["side"] for t in trades]
    assert "BUY" in sides and "SELL" in sides


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
