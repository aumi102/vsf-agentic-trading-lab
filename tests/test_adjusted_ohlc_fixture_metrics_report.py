from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.backtest.adjusted_ohlc_fixture_metrics_report import (
    build_fixture_metrics_report,
    render_fixture_metrics_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/report_adjusted_ohlc_fixture_metrics.py")
SOURCE = Path("src/trading_agent/backtest/adjusted_ohlc_fixture_metrics_report.py")

FORBIDDEN_METRIC_KEYS = (
    "sharpe",
    "sortino",
    "profit_factor",
    "max_drawdown",
    "drawdown",
    "pnl",
    "equity",
    "equity_curve",
    "win_rate",
    "alpha",
)


def _signal_row(symbol: str, datetime_value: str = "2026-01-02") -> dict[str, object]:
    return {
        "symbol": symbol,
        "datetime": datetime_value,
        "fixture_signal_action": "NO_POSITION",
        "reason": "research_fixture_all_cash",
    }


def _write_fixture_signal(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = ("FPT", "VNM", "VCB"),
    rows: list[dict[str, object]] | None = None,
    overrides: dict[str, object] | None = None,
) -> Path:
    if rows is None:
        rows = [_signal_row(symbol) for symbol in symbols]
    payload: dict[str, object] = {
        "status": "ok",
        "dry_run_stage": "fixture_signal_preview",
        "price_basis": "adjusted_ohlc",
        "signal_mode": "all_cash",
        "symbols": list(symbols),
        "requested_symbols": list(symbols),
        "represented_symbols": list(symbols),
        "missing_symbols": [],
        "row_count": len(rows),
        "signal_rows": rows,
        "performance_metrics": None,
        "reasons": [],
        "caveats": [],
        "not_financial_advice": True,
    }
    if overrides:
        payload.update(overrides)
    path = tmp_path / "fixture_signal.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _build(tmp_path: Path, *, signal_path: Path | None = None, **kwargs: object) -> dict[str, object]:
    if signal_path is None:
        signal_path = _write_fixture_signal(tmp_path)
    params: dict[str, object] = {
        "fixture_signal_path": signal_path,
        "symbols": ["FPT", "VNM", "VCB"],
    }
    params.update(kwargs)
    return build_fixture_metrics_report(**params)  # type: ignore[arg-type]


# 1
def test_missing_fixture_signal_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, signal_path=tmp_path / "nope.json")
    assert result["status"] == "blocked"
    assert any(str(r).startswith("fixture_signal_missing:") for r in result["reasons"])


# 2
def test_invalid_json_blocks(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = _build(tmp_path, signal_path=bad)
    assert result["status"] == "blocked"
    assert "fixture_signal_invalid_json" in result["reasons"]


# 3
def test_fixture_signal_not_object_blocks(tmp_path: Path) -> None:
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    result = _build(tmp_path, signal_path=arr)
    assert result["status"] == "blocked"
    assert "fixture_signal_must_be_object" in result["reasons"]


# 4
def test_fixture_signal_status_not_ok_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, overrides={"status": "blocked"})
    result = _build(tmp_path, signal_path=sig)
    assert result["status"] == "blocked"
    assert "fixture_signal_status_not_ok:blocked" in result["reasons"]


# 5
def test_wrong_dry_run_stage_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, overrides={"dry_run_stage": "something_else"})
    result = _build(tmp_path, signal_path=sig)
    assert result["status"] == "blocked"
    assert "fixture_signal_stage_invalid:something_else" in result["reasons"]


# 6
def test_price_basis_not_adjusted_ohlc_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, overrides={"price_basis": "raw_ohlc"})
    result = _build(tmp_path, signal_path=sig)
    assert result["status"] == "blocked"
    assert "fixture_price_basis_not_adjusted_ohlc:raw_ohlc" in result["reasons"]


# 7
def test_not_financial_advice_false_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, overrides={"not_financial_advice": False})
    result = _build(tmp_path, signal_path=sig)
    assert result["status"] == "blocked"
    assert "fixture_not_financial_advice_missing" in result["reasons"]


# 8
def test_performance_metrics_not_null_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, overrides={"performance_metrics": {"sharpe": 1.2}})
    result = _build(tmp_path, signal_path=sig)
    assert result["status"] == "blocked"
    assert "fixture_performance_metrics_must_be_null" in result["reasons"]
    assert result["forbidden_performance_metrics_present"] is True


# 9
def test_requested_symbol_missing_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, symbols=("FPT",), rows=[_signal_row("FPT")])
    result = _build(tmp_path, signal_path=sig, symbols=["FPT", "VNM"])
    assert result["status"] == "blocked"
    assert "requested_symbol_missing:VNM" in result["reasons"]


# 10
def test_signal_rows_missing_blocks(tmp_path: Path) -> None:
    sig = _write_fixture_signal(tmp_path, overrides={"signal_rows": []})
    result = _build(tmp_path, signal_path=sig)
    assert result["status"] == "blocked"
    assert "signal_rows_missing" in result["reasons"]


# 11
def test_forbidden_action_buy_blocks(tmp_path: Path) -> None:
    row = _signal_row("FPT")
    row["fixture_signal_action"] = "BUY"
    sig = _write_fixture_signal(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, signal_path=sig, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_action_present:BUY" in result["reasons"]


# 12
def test_forbidden_action_sell_blocks(tmp_path: Path) -> None:
    row = _signal_row("FPT")
    row["fixture_signal_action"] = "SELL"
    sig = _write_fixture_signal(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, signal_path=sig, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_action_present:SELL" in result["reasons"]


# 13
def test_forbidden_action_hold_blocks(tmp_path: Path) -> None:
    row = _signal_row("FPT")
    row["fixture_signal_action"] = "HOLD"
    sig = _write_fixture_signal(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, signal_path=sig, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_action_present:HOLD" in result["reasons"]


# 14
def test_row_with_performance_field_blocks(tmp_path: Path) -> None:
    row = _signal_row("FPT")
    row["pnl"] = 123.0
    sig = _write_fixture_signal(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, signal_path=sig, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_row_field_present:pnl" in result["reasons"]
    assert result["forbidden_performance_metrics_present"] is True


# 15
def test_valid_no_position_fixture_ok(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["status"] == "ok"
    assert result["report_stage"] == "fixture_diagnostic_metrics"
    assert result["price_basis"] == "adjusted_ohlc"
    assert result["forbidden_performance_metrics_present"] is False
    assert result["not_financial_advice"] is True


# 16
def test_metrics_include_row_and_symbol_count(tmp_path: Path) -> None:
    result = _build(tmp_path)
    metrics = result["diagnostic_metrics"]
    assert metrics["row_count"] == 3
    assert metrics["symbol_count"] == 3


# 17
def test_metrics_include_action_counts(tmp_path: Path) -> None:
    result = _build(tmp_path)
    metrics = result["diagnostic_metrics"]
    assert metrics["signal_action_counts"] == {"NO_POSITION": 3}
    assert metrics["fixture_no_position_ratio"] == 1.0


# 18
def test_metrics_include_first_and_last_date(tmp_path: Path) -> None:
    rows = [
        _signal_row("FPT", "2026-01-02"),
        _signal_row("VNM", "2026-01-05"),
        _signal_row("VCB", "2026-01-03"),
    ]
    sig = _write_fixture_signal(tmp_path, rows=rows)
    result = _build(tmp_path, signal_path=sig)
    metrics = result["diagnostic_metrics"]
    assert metrics["first_date"] == "2026-01-02"
    assert metrics["last_date"] == "2026-01-05"


# 19
def test_no_forbidden_performance_metric_keys_in_output(tmp_path: Path) -> None:
    result = _build(tmp_path)
    metrics_text = json.dumps(result["diagnostic_metrics"]).lower()
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in metrics_text
    # The whole result must not echo a profitability/risk metric anywhere either.
    full_text = json.dumps(result).lower()
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in full_text


# 20
def test_markdown_report_renders(tmp_path: Path) -> None:
    result = _build(tmp_path)
    md = render_fixture_metrics_markdown(result)
    assert "# Adjusted OHLC Fixture Diagnostic Metrics" in md
    assert "row_count" in md
    lower = md.lower()
    for word in ["buy", "sell", "hold"]:
        assert word not in lower


# 21
def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path)
    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


# 22
def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--fixture-signal-json", str(tmp_path / "missing.json"))
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "fixture_signal_missing" in completed.stdout


def test_cli_writes_markdown(tmp_path: Path) -> None:
    out_md = tmp_path / "metrics.md"
    completed = _run_cli(tmp_path, "--output-md", str(out_md))
    assert completed.returncode == 0
    assert out_md.exists()
    assert "Fixture Diagnostic Metrics" in out_md.read_text(encoding="utf-8")


# 23
def test_no_backtrader_import() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")).lower()
    assert "import backtrader" not in text
    assert "backtrader." not in text
    assert "cerebro" not in text


# 24
def test_no_optimizer_code() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")).lower()
    for token in ["def optimize", "grid_search", "gridsearch", "itertools.product", "scipy.optimize"]:
        assert token not in text


# 25
def test_no_network_imports() -> None:
    text = SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")
    assert all(name not in text for name in ["requests", "httpx", "urllib", "socket"])


# 26
def test_no_db_mutation_code() -> None:
    text = SOURCE.read_text(encoding="utf-8").lower()
    for token in ["insert into", "update ", "delete from", "create table", "sqlite3", "execute("]:
        assert token not in text


def test_no_engine_call() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "run_backtest" not in text
    assert "mvp_engine" not in text


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    sig = _write_fixture_signal(tmp_path)
    args = [
        sys.executable,
        str(SCRIPT),
        "--fixture-signal-json",
        str(sig),
        "--symbols",
        "FPT,VNM,VCB",
    ]
    for index in range(0, len(overrides), 2):
        flag = overrides[index]
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
