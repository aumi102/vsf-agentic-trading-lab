"""Tests for trading-core gate scripts (QuestDB-based).

Verifies:
  - Scripts compile without errors
  - Source policy gate: approved_only (default) blocks vnstock-derived rows
  - Source policy gate: prototype_allowed allows vnstock rows as PASS_PROTOTYPE
  - Gate BLOCKs for HPG/VCB/CTG/VHM (no source-backed data)
  - Signals are real (not fabricated) for symbols with approved source
  - Backtest dry-run passes for symbols with approved/gated source
  - No tracebacks on blocked gates (HPG/VCB/CTG/VHM)
  - DB event audit script works
  - No raw daily_prices fallback
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
        [sys.executable, "-u", str(SCRIPTS / script_name), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
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

def test_readiness_approved_only_fpt_vnm_blocked():
    """FPT/VNM: vnstock source, approved_only (default) -> BLOCKED_UNAPPROVED_SOURCE."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,VNM", "--json")
    assert result.returncode == 1, f"FPT/VNM should be blocked, got:\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    data = json.loads(result.stdout)
    assert data["status"] == "BLOCKED_UNAPPROVED_SOURCE"
    assert data["backtest_gate"] == "blocked"
    assert data["coverage"]["adjusted_daily_prices_rows"] > 0
    assert "vnstock" in data["coverage"]["adjusted_daily_prices_source"]
    for sym_data in data["by_symbol"]:
        assert sym_data["source_approval_status"] == "BLOCKED_UNAPPROVED_SOURCE"
        assert sym_data["adjustment_source"] and "vnstock" in sym_data["adjustment_source"]
        assert sym_data["source_policy"] == "approved_only"
        assert "vnstock" in sym_data["caveats"][0].lower()
        assert "approved" in sym_data["blocked_reason"].lower()


def test_readiness_prototype_allowed_fpt_vnm_pass_prototype():
    """FPT/VNM: vnstock source, prototype_allowed -> PASS_PROTOTYPE."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,VNM",
                   "--json", "--source-policy", "prototype_allowed")
    assert result.returncode == 0, f"PASS_PROTOTYPE should exit 0, got:\n{result.stdout}"
    data = json.loads(result.stdout)
    assert data["status"] == "PASS_PROTOTYPE"
    assert data["backtest_gate"] == "partial"
    for sym_data in data["by_symbol"]:
        assert sym_data["status"] == "PASS_PROTOTYPE"
        assert sym_data["source_approval_status"] == "PROTOTYPE_ONLY"
        assert sym_data["source_policy"] == "prototype_allowed"
        assert "prototype" in sym_data["caveats"][0].lower()
        assert sym_data["blocked_reason"] is None


def test_readiness_hpg_blocked():
    """HPG has no source-backed data -> BLOCKED_ADJUSTED_SOURCE_MISSING."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "HPG", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["backtest_gate"] == "blocked"
    assert data["coverage"]["adjusted_daily_prices_rows"] == 0


def test_readiness_mixed_fpt_hpg_vcb_vnm_partial():
    """Mixed FPT+VNM+HPG+VCB -> overall blocked (all are blocked under approved_only)."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT,HPG,VCB,VNM", "--json")
    # All blocked under approved_only -> exit 1
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["backtest_gate"] == "blocked"
    # FPT/VNM are BLOCKED_UNAPPROVED_SOURCE, HPG/VCB are BLOCKED_ADJUSTED_SOURCE_MISSING
    for sym_data in data["by_symbol"]:
        assert sym_data["backtest_gate"] == "blocked"
        assert sym_data["blocked_reason"] is not None
        assert len(sym_data["blocked_reason"]) > 20


def test_readiness_source_policy_in_output():
    """source_policy field appears in coverage output."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "HPG", "--json")
    data = json.loads(result.stdout)
    assert "source_policy" in data["coverage"]
    assert data["coverage"]["source_policy"] == "approved_only"


def test_readiness_require_all_fails_for_blocked():
    """All blocked + --require-all -> exit 1."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "HPG,VCB",
                  "--json", "--require-all")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["backtest_gate"] == "blocked"


# ─── signal gate ───────────────────────────────────────────────────────────────

def test_signals_fpt_vnm_blocked_approved_only():
    """FPT/VNM: vnstock source, approved_only -> BLOCKED."""
    result = _run("run_trading_signals.py", "--symbols", "FPT,VNM",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] in ("partial_blocked", "blocked")
    sigs = {s["symbol"]: s for s in data.get("signals", [])}
    for sym in ("FPT", "VNM"):
        assert sigs.get(sym, {}).get("signal") == "BLOCKED"


def test_signals_hpg_blocked():
    """HPG has no source-backed data -> blocked with precise reason."""
    result = _run("run_trading_signals.py", "--symbols", "HPG",
                  "--as-of", "latest", "--strategy", "momentum_v1")
    assert result.returncode == 1
    assert "BLOCKED" in result.stdout


def test_signals_no_raw_fallback():
    """HPG blocked must NOT use daily_prices as adjusted source."""
    result = _run("run_trading_signals.py", "--symbols", "HPG",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data.get("status") in ("partial_blocked", "blocked")
    assert "daily_prices" not in str(data.get("error", "")), (
        "HPG blocked signal must not reference daily_prices as adjusted source"
    )


def test_signals_all_blocked_exit_1():
    """HPG+VCB+CTG+VHM all blocked under approved_only -> exit 1."""
    result = _run("run_trading_signals.py", "--symbols", "HPG,VCB,CTG,VHM",
                  "--as-of", "latest", "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] in ("partial_blocked", "blocked")


# ─── backtest gate ─────────────────────────────────────────────────────────────

def test_backtest_hpg_all_blocked():
    """HPG only -> BLOCKED under approved_only."""
    result = _run("run_custom_backtest.py", "--symbols", "HPG",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "BLOCKED"


def test_backtest_all_no_source_blocked():
    """HPG+VCB+CTG+VHM all blocked under approved_only -> exit 1."""
    result = _run("run_custom_backtest.py", "--symbols", "HPG,VCB,CTG,VHM",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] in ("BLOCKED", "PARTIAL_BLOCKED")


def test_backtest_no_tracebacks_on_blocked():
    """No tracebacks when all symbols blocked."""
    result = _run("run_custom_backtest.py", "--symbols", "HPG,VCB,CTG,VHM",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_backtest_mixed_fpt_hpg_all_blocked():
    """FPT+HPG+VCB+VNM all blocked under approved_only -> exit 1."""
    result = _run("run_custom_backtest.py", "--symbols", "FPT,HPG,VCB,VNM",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    # All blocked under approved_only: FPT=vnstock blocked, others=no source
    assert data.get("backtest_gate", data.get("gate")) == "blocked"
    for res in data.get("results", []):
        assert res["gate"] == "blocked"


def test_backtest_require_all_fails_for_blocked():
    """All blocked + --require-all -> exit 1."""
    result = _run("run_custom_backtest.py", "--symbols", "HPG,VCB",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "momentum_v1", "--json", "--require-all")
    assert result.returncode == 1


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



# ─── new: cost/slippage model (CHECKPOINT 3) ───────────────────────────────

def test_backtest_with_cost_args_compiles():
    for script in ("trading_cost_model.py", "run_custom_backtest.py"):
        result = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", str(SCRIPTS / script)],
            cwd=ROOT, capture_output=True, check=False,
        )
        assert result.returncode == 0, f"{script} should compile: {result.stderr}"


def test_backtest_cost_model_zero_trades_no_commission():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "ma_cross_v1",
                  "--initial-cash", "100000000",
                  "--commission-bps", "15", "--slippage-bps", "5",
                  "--price-band-guard", "--json",
                  "--source-policy", "prototype_allowed")
    assert result.returncode == 0, f"Should succeed: {result.stdout} {result.stderr}"
    data = json.loads(result.stdout)
    res = data["results"][0]
    assert res["gate"] == "pass"
    # Zero-trade strategy must have zero commission
    assert res["metrics"]["total_commission"] == 0.0, \
        f"0-trade backtest must have 0 commission, got {res['metrics']['total_commission']}"
    assert res["metrics"]["total_slippage_estimate"] == 0.0, \
        f"0-trade backtest must have 0 slippage"
    assert "cost_slippage_assumptions" in res["metrics"]


def test_backtest_baseline_charges_realistic_costs():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "baseline_buy_hold_v1",
                  "--initial-cash", "100000000",
                  "--commission-bps", "15", "--slippage-bps", "5",
                  "--price-band-guard", "--json",
                  "--source-policy", "prototype_allowed")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    res = data["results"][0]
    assert res["gate"] == "pass"
    assert res["metrics"]["total_commission"] > 0, "BUY+SELL trades must charge commission"
    assert res["metrics"]["total_slippage_estimate"] > 0, "BUY+SELL trades must charge slippage"
    assert "cost_summary" in res
    assert res["cost_summary"]["blocked_orders_due_price_band"] == 0
    for t in res["trade_ledger"]:
        assert "commission" in t
        assert "slippage_bps" in t
        assert "slippage_value_estimate" in t
        assert "raw_base_price" in t
        assert "execution_price" in t


def test_backtest_trade_ledger_has_pnl_fields():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "baseline_buy_hold_v1",
                  "--initial-cash", "100000000",
                  "--commission-bps", "15", "--slippage-bps", "5", "--json",
                  "--source-policy", "prototype_allowed")
    data = json.loads(result.stdout)
    res = data["results"][0]
    sells = [t for t in res["trade_ledger"] if t["side"] == "SELL"]
    if sells:
        s = sells[-1]
        assert "realized_pnl" in s
        assert "realized_pnl_pct" in s
        assert "entry_price" in s


def test_backtest_cost_assumptions_in_output():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "baseline_buy_hold_v1",
                  "--commission-bps", "15", "--slippage-bps", "5", "--json",
                  "--source-policy", "prototype_allowed")
    data = json.loads(result.stdout)
    assert "cost_assumptions" in data
    ca = data["cost_assumptions"]
    assert ca["commission_bps"] == 15.0
    assert ca["slippage_bps"] == 5.0


# ─── new: ma_cross_v1 strategy (CHECKPOINT 6) ──────────────────────────────

def test_ma_cross_v1_signal_works():
    result = _run("run_trading_signals.py", "--symbols", "FPT",
                  "--as-of", "latest", "--strategy", "ma_cross_v1", "--json",
                  "--source-policy", "prototype_allowed")
    assert result.returncode == 0, f"ma_cross_v1 should work: {result.stdout} {result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["signals"][0]["signal"] in ("BUY", "SELL", "HOLD")
    assert data["signals"][0]["gate"] == "pass"
    assert data["signals"][0]["adjustment_status"] == "source_backed_corporate_action"


def test_ma_cross_v1_backtest_works():
    result = _run("run_custom_backtest.py", "--symbols", "FPT",
                  "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "ma_cross_v1",
                  "--commission-bps", "15", "--slippage-bps", "5", "--json",
                  "--source-policy", "prototype_allowed")
    assert result.returncode == 0, f"ma_cross_v1 backtest should work: {result.stdout} {result.stderr}"


# ─── new: inventory script (CHECKPOINT 1) ─────────────────────────────────

def test_inventory_corporate_events_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(SCRIPTS / "inventory_corporate_events_universe.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_inventory_only_fpt_vnm_computable():
    result = _run("inventory_corporate_events_universe.py", "--json")
    data = json.loads(result.stdout)
    adjustable = data["adjustment_feasibility_summary"]["ADJUSTABLE_CASH_DIVIDEND"]["symbols"]
    assert set(adjustable) == {"FPT", "VNM"}, f"Expected FPT+VNM, got {adjustable}"
    assert data["computable_symbols_count"] == 2
    assert data["target_50_achievable"] is False
    assert data["target_100_achievable"] is False


def test_inventory_hpg_vcb_ctg_vhm_no_event_data():
    result = _run("inventory_corporate_events_universe.py", "--symbols", "HPG,VCB,CTG,VHM", "--json")
    data = json.loads(result.stdout)
    for sym in ["HPG", "VCB", "CTG", "VHM"]:
        # Script uses hpg_vcb_ctg_vhm_status key; inner status is NO_EVENT_DATA
        assert data["hpg_vcb_ctg_vhm_status"][sym]["status"] in (
            "NO_EVENT_DATA", "NO_EVENTS"), \
            f"{sym} should have no event data, got {data['hpg_vcb_ctg_vhm_status'][sym]['status']}"


# ─── new: list_adjusted_pass_symbols ─────────────────────────────────────

def test_list_adjusted_pass_symbols_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(SCRIPTS / "list_adjusted_pass_symbols.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_list_adjusted_pass_symbols_shows_2():
    result = _run("list_adjusted_pass_symbols.py", "--limit", "100", "--json")
    data = json.loads(result.stdout)
    assert data["status"] == "OK"
    assert data["total_pass_count"] == 2, f"Expected 2 PASS, got {data['total_pass_count']}"
    pass_syms = {s["symbol"] for s in data["pass_symbols"]}
    assert pass_syms == {"FPT", "VNM"}


# ─── new: multi-symbol demo (CHECKPOINT 7) ────────────────────────────────

def test_multi_symbol_demo_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(SCRIPTS / "run_multi_symbol_trading_core_demo.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_multi_symbol_demo_reports_limited():
    result = _run("run_multi_symbol_trading_core_demo.py",
                  "--limit", "100", "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "ma_cross_v1",
                  "--commission-bps", "15", "--slippage-bps", "5",
                  "--price-band-guard", "--json")
    data = json.loads(result.stdout)
    assert data["demo_status"] == "BROAD_DEMO_LIMITED_SOURCE_BACKED_SYMBOLS"
    assert data["pass_symbols_count"] == 2
    assert data["broad_demo_limited"] is True
    assert "baseline_buy_hold_v1" in data["backtests"]
    assert "ma_cross_v1" in data["backtests"]


# ─── new: probe script (CHECKPOINT 5) ──────────────────────────────────

def test_probe_hpg_vcb_ctg_vhm_no_source():
    result = _run("probe_adjusted_price_sources.py",
                  "--symbols", "HPG,VCB,CTG,VHM", "--limit", "4", "--json")
    data = json.loads(result.stdout)
    for sym in ["HPG", "VCB", "CTG", "VHM"]:
        status = data["by_symbol"][sym]["status"]
        # NO_DATA means vnstock company_events dir exists but symbol not present
        assert status in ("NO_DATA", "NO_CORPORATE_ACTION_SOURCE", "SOURCE_NOT_CONFIGURED"), \
            f"{sym} should be blocked, got {status}"


# ─── new: mentor report (CHECKPOINT 8) ────────────────────────────────

def test_mentor_report_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(SCRIPTS / "run_mentor_trading_core_report.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_mentor_report_approved_only_status():
    result = _run("run_mentor_trading_core_report.py",
                  "--limit", "100", "--from", "2021-01-01", "--to", "2025-12-31",
                  "--strategy", "ma_cross_v1",
                  "--commission-bps", "15", "--slippage-bps", "5",
                  "--price-band-guard", "--json")
    data = json.loads(result.stdout)
    # list_adjusted_pass_symbols uses DB query (no source_policy) -> counts FPT/VNM as pass
    assert data["adjusted_ohlc_pipeline"]["source_backed_symbols_count"] == 2
    assert data["adjusted_ohlc_pipeline"]["target_50_achieved"] is False
    # but sym_status uses approved_only -> FPT/VNM blocked (vnstock), HPG/VCB blocked (no source)
    assert data["adjusted_ohlc_pipeline"]["target_symbols"]["HPG"]["gate"] == "blocked"
    assert data["adjusted_ohlc_pipeline"]["target_symbols"]["VCB"]["gate"] == "blocked"
    # FPT/VNM now blocked under approved_only (vnstock source)
    assert data["adjusted_ohlc_pipeline"]["target_symbols"]["FPT"]["gate"] == "blocked"
    assert data["adjusted_ohlc_pipeline"]["target_symbols"]["VNM"]["gate"] == "blocked"


# ─── new: DB event audit script ─────────────────────────────────────────────

def test_audit_questdb_event_tables_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(SCRIPTS / "audit_questdb_event_tables_for_corporate_actions.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_audit_fpt_has_20_rows_1_dividend_candidate():
    result = _run("audit_questdb_event_tables_for_corporate_actions.py",
                   "--symbols", "FPT", "--json")
    data = json.loads(result.stdout)
    assert data["global"]["event_news_items"]["exists"] is True
    assert data["global"]["event_news_raw_payloads"]["exists"] is True
    fpt = next(s for s in data["symbols"] if s["symbol"] == "FPT")
    assert fpt["event_news_count"] == 20
    assert fpt["raw_payload_count"] == 20
    assert fpt["candidate_corporate_action_count"] >= 1
    assert any(c["candidate_dividend"] for c in fpt["candidates"])


def test_audit_vnm_hpg_vcb_ctg_vhm_no_db_rows():
    result = _run("audit_questdb_event_tables_for_corporate_actions.py",
                   "--symbols", "VNM,HPG,VCB,CTG,VHM", "--json")
    data = json.loads(result.stdout)
    for sym in ["VNM", "HPG", "VCB", "CTG", "VHM"]:
        sym_data = next(s for s in data["symbols"] if s["symbol"] == sym)
        assert sym_data["source_status"] == "NO_DB_EVENT_ROWS"
        assert sym_data["adjustment_feasibility"] == "NO_CORPORATE_ACTION_SOURCE"
        assert sym_data["candidate_corporate_action_count"] == 0


def test_audit_fpt_insufficient_fields():
    result = _run("audit_questdb_event_tables_for_corporate_actions.py",
                   "--symbols", "FPT", "--json")
    data = json.loads(result.stdout)
    fpt = next(s for s in data["symbols"] if s["symbol"] == "FPT")
    assert fpt["adjustment_feasibility"] == "NEEDS_RAW_PAYLOAD_PARSER"
    assert fpt["source_status"] == "DB_DISCLOSURE_TEXT_CANDIDATE"
    # Required fields must be missing
    for field in ["ex_date", "record_date", "cash_dividend_per_share", "currency"]:
        assert field in fpt["missing_required_fields"]


def test_audit_no_structured_corporate_action():
    """No symbol should be ADJUSTABLE_FROM_DB_STRUCTURED with current schema."""
    result = _run("audit_questdb_event_tables_for_corporate_actions.py",
                   "--symbols", "FPT,VNM,HPG,VCB,CTG,VHM", "--json")
    data = json.loads(result.stdout)
    for sym_data in data["symbols"]:
        assert sym_data.get("adjustment_feasibility") != "ADJUSTABLE_FROM_DB_STRUCTURED", \
            f"{sym_data['symbol']} should not be ADJUSTABLE_FROM_DB_STRUCTURED"


# ─── new: inspect raw payload script ────────────────────────────────────────

def test_inspect_raw_payload_compiles():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(SCRIPTS / "inspect_event_raw_payload.py")],
        cwd=ROOT, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_inspect_fpt_dividend_insufficient_fields():
    result = _run("inspect_event_raw_payload.py", "--symbol", "FPT",
                   "--keyword", "dividend", "--json")
    data = json.loads(result.stdout)
    assert data["extraction_status"] == "INSUFFICIENT_FIELDS"
    assert data["adjustment_feasibility"] == "INSUFFICIENT_FIELDS"
    assert data["file_type"] in ("html", None)
    # All 4 required fields missing
    for field in ["ex_date", "record_date", "cash_dividend_per_share", "currency"]:
        assert field in data["missing_fields"]


# ─── new: source policy tests ────────────────────────────────────────────────

def test_source_policy_default_is_approved_only():
    """Default source_policy in CLI must be approved_only."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT", "--json")
    data = json.loads(result.stdout)
    assert data["coverage"]["source_policy"] == "approved_only"
    for sym_data in data["by_symbol"]:
        assert sym_data["source_policy"] == "approved_only"


def test_prototype_allowed_fpt_not_blocked():
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "FPT",
                   "--json", "--source-policy", "prototype_allowed")
    data = json.loads(result.stdout)
    # prototype_allowed should not exit 1
    assert result.returncode == 0
    fpt = next(s for s in data["by_symbol"] if s["symbol"] == "FPT")
    assert fpt["status"] == "PASS_PROTOTYPE"
    assert fpt["source_approval_status"] == "PROTOTYPE_ONLY"
    assert "prototype" in fpt["caveats"][0].lower()


def test_no_raw_daily_prices_fallback():
    """approved_only: no symbol should silently fall back to raw daily_prices."""
    result = _run("adjusted_ohlc_readiness.py", "--symbols", "HPG,VCB", "--json")
    data = json.loads(result.stdout)
    for sym_data in data["by_symbol"]:
        assert sym_data["source_approval_status"] == "BLOCKED_APPROVED_ADJUSTED_SOURCE_MISSING"
        assert "raw" not in sym_data.get("blocked_reason", "").lower() or \
               "daily_prices" in sym_data.get("blocked_reason", "").lower()
        # Should not have an approved status
        assert sym_data["source_approval_status"] not in ("APPROVED",)