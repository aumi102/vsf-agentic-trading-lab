from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.backtest.metrics import max_drawdown, profit_factor, summarize_metrics
from trading_agent.backtest.mvp_engine import run_backtest
from trading_agent.db.schema import create_schema, replace_table
from trading_agent.signals.mvp_momentum import STRATEGY_ID, SIGNAL_VERSION


def test_metrics_functions_on_tiny_arrays() -> None:
    metrics = summarize_metrics(
        equity=[100.0, 110.0, 105.0],
        dates=["2026-01-01", "2026-01-02", "2026-01-03"],
        trade_pnls=[10.0, -5.0],
        position_flags=[False, True, True],
        number_of_trades=2,
    )

    assert metrics["total_return"] == pytest.approx(0.05)
    assert metrics["number_of_trades"] == 2
    assert metrics["exposure"] == pytest.approx(2 / 3)


def test_max_drawdown_calculation() -> None:
    assert max_drawdown([100.0, 120.0, 90.0, 130.0]) == pytest.approx(-0.25)


def test_profit_factor_with_wins_and_losses() -> None:
    assert profit_factor([10.0, -2.0, 5.0, -3.0]) == pytest.approx(3.0)


def test_missing_db_returns_clear_error(tmp_path: Path) -> None:
    result = run_backtest(symbols=["FPT"], db_path=tmp_path / "missing.sqlite")

    assert result["status"] == "error"
    assert "Build it first" in " ".join(result["caveats"])


def test_unknown_symbol_returns_not_found(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["HPG"], db_path=db_path)

    assert result["status"] == "not_found"
    assert result["trades"] == []


def test_valid_single_symbol_backtest_returns_ok(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    assert result["status"] == "ok"
    assert result["strategy_id"] == STRATEGY_ID
    assert result["metrics"]["number_of_trades"] == 2


def test_valid_multi_symbol_backtest_returns_ok(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT", "VNM", "VCB"])

    result = run_backtest(symbols=["FPT", "VNM", "VCB"], db_path=db_path)

    assert result["status"] == "ok"
    assert sorted(result["symbols_found"]) == ["FPT", "VCB", "VNM"]
    assert set(result["metrics"]["by_symbol"]) == {"FPT", "VNM", "VCB"}


def test_partial_missing_symbols_returns_ok_with_warning_and_caveat(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT", "HPG"], db_path=db_path)

    gates = {gate["name"]: gate for gate in result["validation_gates"]}
    assert result["status"] == "ok"
    assert result["symbols_found"] == ["FPT"]
    assert result["symbols_missing"] == ["HPG"]
    assert gates["symbols_exist"]["status"] == "warn"
    assert "Some requested symbols were not found" in " ".join(result["caveats"])


def test_date_range_with_no_usable_rows_returns_not_found(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(
        symbols=["FPT"],
        db_path=db_path,
        start_date="2030-01-01",
        end_date="2030-12-31",
    )

    gates = {gate["name"]: gate for gate in result["validation_gates"]}
    assert result["status"] == "not_found"
    assert result["symbols_found"] == ["FPT"]
    assert result["symbols_missing"] == []
    assert gates["usable_rows_exist"]["status"] == "fail"
    assert "No usable price rows" in " ".join(result["caveats"])


def test_invalid_unsupported_strategy_id_is_deterministic(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path, strategy_id="other")

    assert result["status"] == "invalid_assumptions"
    assert "Unsupported strategy_id=other" in " ".join(result["caveats"])


def test_invalid_initial_capital_zero_is_deterministic(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path, initial_capital=0)

    assert result["status"] == "invalid_assumptions"
    assert "initial_capital must be greater than zero" in " ".join(result["caveats"])


def test_invalid_negative_transaction_cost_is_deterministic(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path, transaction_cost=-0.1)

    assert result["status"] == "invalid_assumptions"
    assert "transaction_cost must be non-negative" in " ".join(result["caveats"])


def test_invalid_negative_slippage_is_deterministic(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path, slippage=-0.1)

    assert result["status"] == "invalid_assumptions"
    assert "slippage must be non-negative" in " ".join(result["caveats"])


def test_trades_include_cost_and_slippage_assumptions(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path, transaction_cost=0.002, slippage=0.001)

    assert result["trades"]
    assert result["trades"][0]["transaction_cost"] == pytest.approx(0.002)
    assert result["trades"][0]["slippage"] == pytest.approx(0.001)


def test_validation_gates_include_source_lineage_check(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    gates = {gate["name"]: gate for gate in result["validation_gates"]}
    assert gates["daily_prices_have_source_id_raw_path"]["status"] == "pass"


def test_validation_gates_include_execution_and_adjustment_caveats(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    gates = {gate["name"]: gate for gate in result["validation_gates"]}
    assert gates["adjustment_corporate_action_warning"]["status"] == "warn"
    assert gates["no_future_leakage_caveat"]["status"] == "warn"


def test_fail_ohlc_rows_are_excluded(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"], include_fail=True)

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    gates = {gate["name"]: gate for gate in result["validation_gates"]}
    assert gates["fail_ohlc_rows_excluded"]["detail"] == "excluded_fail_rows=1"
    assert all(point["date"] != "2026-01-11" for point in result["equity_curve"])


def test_no_shorting_behavior(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"], sell_only=True)

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    assert result["status"] == "ok"
    assert result["trades"] == []
    assert result["metrics"]["number_of_trades"] == 0


def test_cli_smoke_valid_run(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    completed = _run_cli("--symbols", "FPT", "--db-path", str(db_path))

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout
    assert "not financial advice" in completed.stdout


def test_cli_missing_db_no_traceback(tmp_path: Path) -> None:
    completed = _run_cli("--symbols", "FPT", "--db-path", str(tmp_path / "missing.sqlite"))

    assert completed.returncode == 1
    assert "Build it first" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_unknown_symbol_no_traceback(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    completed = _run_cli("--symbols", "HPG", "--db-path", str(db_path))

    assert completed.returncode == 1
    assert '"status": "not_found"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_invalid_assumption_exits_2_without_traceback(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    completed = _run_cli("--symbols", "FPT", "--db-path", str(db_path), "--initial-capital", "0")

    assert completed.returncode == 2
    assert '"status": "invalid_assumptions"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_partial_missing_symbols_prints_missing_list(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    completed = _run_cli("--symbols", "FPT,HPG", "--db-path", str(db_path))

    assert completed.returncode == 0
    assert '"symbols_missing": [' in completed.stdout
    assert '"HPG"' in completed.stdout


def test_cli_date_range_no_data_no_traceback(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    completed = _run_cli(
        "--symbols",
        "FPT",
        "--db-path",
        str(db_path),
        "--start-date",
        "2030-01-01",
        "--end-date",
        "2030-12-31",
    )

    assert completed.returncode == 1
    assert '"status": "not_found"' in completed.stdout
    assert "No usable price rows" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_metric_none_caveat_when_no_closed_trades_or_losses(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    assert result["metrics"]["profit_factor"] is None
    assert "Metric profit_factor could not be computed reliably" in " ".join(result["caveats"])


def test_symbols_found_and_missing_present_for_ok_and_not_found(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    ok_result = run_backtest(symbols=["FPT"], db_path=db_path)
    missing_result = run_backtest(symbols=["HPG"], db_path=db_path)

    assert ok_result["symbols_found"] == ["FPT"]
    assert ok_result["symbols_missing"] == []
    assert missing_result["symbols_found"] == []
    assert missing_result["symbols_missing"] == ["HPG"]


def test_not_financial_advice_wording_present(tmp_path: Path) -> None:
    db_path = _write_backtest_db(tmp_path, ["FPT"])

    result = run_backtest(symbols=["FPT"], db_path=db_path)

    assert result["not_financial_advice"] is True
    assert "not financial advice" in " ".join(result["caveats"])


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_backtest_demo.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _write_backtest_db(
    tmp_path: Path,
    symbols: list[str],
    *,
    include_fail: bool = False,
    sell_only: bool = False,
) -> Path:
    db_path = tmp_path / "backtest.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        securities = []
        prices = []
        features = []
        signals = []
        for offset, symbol in enumerate(symbols):
            security_id = f"vietcap_iq:HOSE:{symbol}"
            securities.append(
                {
                    "security_id": security_id,
                    "symbol": symbol,
                    "exchange": "HOSE",
                    "issuer_name": symbol,
                    "source_id": f"src-{symbol}",
                    "raw_path": f"payload-{symbol}.json",
                    "first_seen_at": "2026-01-01T00:00:00+00:00",
                    "quality_status": "pass",
                }
            )
            for i in range(70):
                trade_date = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
                close = 100.0 + offset + i
                quality = "fail" if include_fail and i == 10 else "pass"
                prices.append(
                    {
                        "security_id": security_id,
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "open": close,
                        "high": close + 1,
                        "low": close - 1,
                        "close": close,
                        "volume": 1000 + i,
                        "value": 100000 + i,
                        "price_basis": "source_reported",
                        "adjustment_status": "unknown",
                        "source_id": f"src-{symbol}",
                        "raw_path": f"payload-{symbol}.json",
                        "quality_status": quality,
                    }
                )
                if quality == "fail":
                    continue
                features.append(
                    {
                        "security_id": security_id,
                        "symbol": symbol,
                        "as_of_date": trade_date,
                        "return_1d": 0.01,
                        "return_5d": 0.05,
                        "return_20d": 0.2,
                        "ma_20": close - 1,
                        "ma_50": close - 2,
                        "volatility_20d": 0.02,
                        "volume_ratio_20d": 1.0,
                        "feature_version": "fixture_v1",
                        "lookback_coverage": i + 1,
                        "quality_status": "pass" if i >= 49 else "warn",
                    }
                )
                action = _fixture_action(i, sell_only=sell_only)
                signals.append(
                    {
                        "security_id": security_id,
                        "symbol": symbol,
                        "as_of_date": trade_date,
                        "strategy_id": STRATEGY_ID,
                        "action": action,
                        "score": 1.0 if action == "BUY" else -1.0 if action == "SELL" else 0.0,
                        "reason_code": "fixture",
                        "reason_text": "fixture",
                        "signal_version": SIGNAL_VERSION,
                        "quality_status": "pass" if i >= 49 else "warn",
                    }
                )
        replace_table(con, "securities", securities)
        replace_table(con, "daily_prices", prices)
        replace_table(con, "feature_snapshots", features)
        replace_table(con, "signals", signals)
    return db_path


def _fixture_action(i: int, *, sell_only: bool) -> str:
    if sell_only:
        return "SELL" if i >= 49 else "HOLD_WITH_LOW_CONFIDENCE"
    if i < 49:
        return "HOLD_WITH_LOW_CONFIDENCE"
    if i == 50:
        return "BUY"
    if i == 60:
        return "SELL"
    return "HOLD"
