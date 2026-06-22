from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.backtest.adjusted_ohlc_fixture_roundtrip_engine import (
    render_fixture_roundtrip_markdown,
    run_fixture_roundtrip_engine,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/run_adjusted_ohlc_fixture_roundtrip_engine.py")
SOURCE = Path("src/trading_agent/backtest/adjusted_ohlc_fixture_roundtrip_engine.py")

FORBIDDEN_METRIC_KEYS = (
    "sharpe",
    "sortino",
    "profit_factor",
    "max_drawdown",
    "drawdown",
    "pnl",
    "equity",
    "win_rate",
    "alpha",
    "returns",
)

SYMBOLS = ("FPT", "VNM", "VCB")


def _signal_row(symbol: str, action: str = "NO_POSITION", datetime_value: str = "2026-01-02") -> dict[str, object]:
    return {
        "symbol": symbol,
        "datetime": datetime_value,
        "fixture_signal_action": action,
        "reason": "research_fixture_all_cash",
    }


def _write_preparation(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> Path:
    payload: dict[str, object] = {
        "status": "ok",
        "dry_run_stage": "backtest_input_preparation",
        "backtest_input_status": "ready_for_research_dry_run",
        "price_basis": "adjusted_ohlc",
        "symbols": list(SYMBOLS),
        "requested_symbols": list(SYMBOLS),
        "represented_symbols": list(SYMBOLS),
        "missing_symbols": [],
        "row_count": 3,
        "assumptions": {
            "transaction_cost_bps": 15,
            "slippage_bps": 10,
            "exchange": "HOSE",
            "slippage_band_bps": 700,
        },
        "rows_preview": [{"symbol": s, "datetime": "2026-01-02"} for s in SYMBOLS],
        "fixture_signal": None,
        "reasons": [],
        "caveats": [],
        "not_financial_advice": True,
    }
    if overrides:
        payload.update(overrides)
    path = tmp_path / "preparation.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_signal(
    tmp_path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
    symbols: tuple[str, ...] = SYMBOLS,
    overrides: dict[str, object] | None = None,
) -> Path:
    if rows is None:
        rows = [_signal_row(s) for s in symbols]
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


def _write_metrics(tmp_path: Path, *, symbols: tuple[str, ...] = SYMBOLS, overrides: dict[str, object] | None = None) -> Path:
    payload: dict[str, object] = {
        "status": "ok",
        "report_stage": "fixture_diagnostic_metrics",
        "price_basis": "adjusted_ohlc",
        "symbols": list(symbols),
        "diagnostic_metrics": {
            "row_count": 3,
            "symbol_count": 3,
            "signal_action_counts": {"NO_POSITION": 3},
            "first_date": "2026-01-02",
            "last_date": "2026-01-02",
            "fixture_no_position_ratio": 1.0,
            "input_price_basis": "adjusted_ohlc",
        },
        "forbidden_performance_metrics_present": False,
        "reasons": [],
        "caveats": [],
        "not_financial_advice": True,
    }
    if overrides:
        payload.update(overrides)
    path = tmp_path / "fixture_metrics.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _build(
    tmp_path: Path,
    *,
    prep: Path | None = None,
    signal: Path | None = None,
    metrics: Path | None = None,
    **kwargs: object,
) -> dict[str, object]:
    prep = prep or _write_preparation(tmp_path)
    signal = signal or _write_signal(tmp_path)
    metrics = metrics or _write_metrics(tmp_path)
    params: dict[str, object] = {
        "preparation_path": prep,
        "fixture_signal_path": signal,
        "fixture_metrics_path": metrics,
        "symbols": list(SYMBOLS),
    }
    params.update(kwargs)
    return run_fixture_roundtrip_engine(**params)  # type: ignore[arg-type]


def _alt_rows() -> list[dict[str, object]]:
    return [
        _signal_row("FPT", "FIXTURE_ENTER", "2026-01-02"),
        _signal_row("FPT", "FIXTURE_EXIT", "2026-01-03"),
        _signal_row("VNM", "FIXTURE_ENTER", "2026-01-02"),
        _signal_row("VCB", "FIXTURE_ENTER", "2026-01-02"),
    ]


# 1
def test_missing_preparation_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, prep=tmp_path / "nope.json")
    assert result["status"] == "blocked"
    assert any(str(r).startswith("preparation_missing:") for r in result["reasons"])


# 2
def test_missing_signal_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, signal=tmp_path / "nope.json")
    assert result["status"] == "blocked"
    assert any(str(r).startswith("fixture_signal_missing:") for r in result["reasons"])


# 3
def test_missing_metrics_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, metrics=tmp_path / "nope.json")
    assert result["status"] == "blocked"
    assert any(str(r).startswith("fixture_metrics_missing:") for r in result["reasons"])


# 4
def test_invalid_json_blocks_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = _build(tmp_path, prep=bad)
    assert result["status"] == "blocked"
    assert "preparation_invalid_json" in result["reasons"]


# 5
def test_preparation_status_not_ok_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(tmp_path, overrides={"status": "blocked"})
    result = _build(tmp_path, prep=prep)
    assert result["status"] == "blocked"
    assert "preparation_status_not_ok:blocked" in result["reasons"]


# 6
def test_preparation_price_basis_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(tmp_path, overrides={"price_basis": "raw_ohlc"})
    result = _build(tmp_path, prep=prep)
    assert result["status"] == "blocked"
    assert "preparation_price_basis_not_adjusted_ohlc:raw_ohlc" in result["reasons"]


# 7
def test_signal_status_not_ok_blocks(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, overrides={"status": "blocked"})
    result = _build(tmp_path, signal=signal)
    assert result["status"] == "blocked"
    assert "fixture_signal_status_not_ok:blocked" in result["reasons"]


# 8
def test_signal_performance_metrics_not_null_blocks(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, overrides={"performance_metrics": {"sharpe": 1.0}})
    result = _build(tmp_path, signal=signal)
    assert result["status"] == "blocked"
    assert "fixture_signal_performance_metrics_must_be_null" in result["reasons"]


# 9
def test_metrics_status_not_ok_blocks(tmp_path: Path) -> None:
    metrics = _write_metrics(tmp_path, overrides={"status": "blocked"})
    result = _build(tmp_path, metrics=metrics)
    assert result["status"] == "blocked"
    assert "fixture_metrics_status_not_ok:blocked" in result["reasons"]


# 10
def test_metrics_forbidden_performance_present_blocks(tmp_path: Path) -> None:
    metrics = _write_metrics(tmp_path, overrides={"forbidden_performance_metrics_present": True})
    result = _build(tmp_path, metrics=metrics)
    assert result["status"] == "blocked"
    assert "fixture_metrics_forbidden_performance_metrics_present" in result["reasons"]


# 11
def test_requested_symbol_missing_across_inputs_blocks(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, symbols=("FPT", "VNM"), rows=[_signal_row("FPT"), _signal_row("VNM")])
    result = _build(tmp_path, signal=signal, symbols=["FPT", "VNM", "VCB"])
    assert result["status"] == "blocked"
    assert "requested_symbol_missing_from_signal:VCB" in result["reasons"]


# 12
def test_max_rows_zero_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, max_rows=0)
    assert result["status"] == "blocked"
    assert "max_rows_must_be_positive" in result["reasons"]


# 13/14/15
def test_forbidden_action_buy_blocks(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, symbols=("FPT",), rows=[_signal_row("FPT", "BUY")])
    result = _build(tmp_path, signal=signal, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_action_present:BUY" in result["reasons"]


def test_forbidden_action_sell_blocks(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, symbols=("FPT",), rows=[_signal_row("FPT", "SELL")])
    result = _build(tmp_path, signal=signal, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_action_present:SELL" in result["reasons"]


def test_forbidden_action_hold_blocks(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, symbols=("FPT",), rows=[_signal_row("FPT", "HOLD")])
    result = _build(tmp_path, signal=signal, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_action_present:HOLD" in result["reasons"]


# 16
def test_forbidden_row_field_blocks(tmp_path: Path) -> None:
    for field in ("pnl", "equity", "return", "sharpe", "drawdown"):
        row = _signal_row("FPT")
        row[field] = 1.0
        signal = _write_signal(tmp_path, symbols=("FPT",), rows=[row])
        result = _build(tmp_path, signal=signal, symbols=["FPT"])
        assert result["status"] == "blocked"
        assert f"forbidden_row_field_present:{field}" in result["reasons"]


# 17
def test_all_cash_no_position_ok(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["status"] == "ok"
    assert result["engine_stage"] == "fixture_roundtrip_engine"
    assert result["price_basis"] == "adjusted_ohlc"
    diag = result["roundtrip_diagnostics"]
    assert diag["action_counts"] == {"NO_POSITION": 3}
    assert diag["state_transition_counts"]["fixture_enter_count"] == 0
    assert diag["state_transition_counts"]["open_fixture_state_count"] == 0


# 18
def test_alternating_enter_exit_counts(tmp_path: Path) -> None:
    signal = _write_signal(tmp_path, rows=_alt_rows())
    result = _build(tmp_path, signal=signal)
    assert result["status"] == "ok"
    counts = result["roundtrip_diagnostics"]["state_transition_counts"]
    assert counts["fixture_enter_count"] == 3
    assert counts["fixture_exit_count"] == 1


# 19
def test_duplicate_enter_count(tmp_path: Path) -> None:
    rows = [
        _signal_row("FPT", "FIXTURE_ENTER", "2026-01-02"),
        _signal_row("FPT", "FIXTURE_ENTER", "2026-01-03"),
    ]
    signal = _write_signal(tmp_path, symbols=("FPT",), rows=rows)
    result = _build(tmp_path, signal=signal, symbols=["FPT"])
    assert result["status"] == "ok"
    counts = result["roundtrip_diagnostics"]["state_transition_counts"]
    assert counts["duplicate_enter_count"] == 1
    assert counts["fixture_enter_count"] == 1


# 20
def test_unmatched_exit_count(tmp_path: Path) -> None:
    rows = [_signal_row("FPT", "FIXTURE_EXIT", "2026-01-02")]
    signal = _write_signal(tmp_path, symbols=("FPT",), rows=rows)
    result = _build(tmp_path, signal=signal, symbols=["FPT"])
    assert result["status"] == "ok"
    counts = result["roundtrip_diagnostics"]["state_transition_counts"]
    assert counts["unmatched_exit_count"] == 1


# 21
def test_open_fixture_state_count(tmp_path: Path) -> None:
    rows = [_signal_row("FPT", "FIXTURE_ENTER", "2026-01-02")]
    signal = _write_signal(tmp_path, symbols=("FPT",), rows=rows)
    result = _build(tmp_path, signal=signal, symbols=["FPT"])
    assert result["status"] == "ok"
    counts = result["roundtrip_diagnostics"]["state_transition_counts"]
    assert counts["open_fixture_state_count"] == 1


# 22
def test_output_has_no_performance_metrics(tmp_path: Path) -> None:
    result = _build(tmp_path)
    diag_text = json.dumps(result["roundtrip_diagnostics"]).lower()
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in diag_text
    full_text = json.dumps(result).lower()
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in full_text


# 23
def test_output_not_financial_advice_true(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["not_financial_advice"] is True
    assert result["forbidden_performance_metrics_present"] is False


# 24
def test_markdown_report_renders(tmp_path: Path) -> None:
    result = _build(tmp_path)
    md = render_fixture_roundtrip_markdown(result)
    assert "# Adjusted OHLC Fixture Round-Trip Engine" in md
    assert "processed_row_count" in md
    lower = md.lower()
    for word in ["buy", "sell", "hold"]:
        assert word not in lower


# 25
def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path)
    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


# 26
def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--preparation-json", str(tmp_path / "missing.json"))
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "preparation_missing" in completed.stdout


def test_cli_writes_markdown(tmp_path: Path) -> None:
    out_md = tmp_path / "roundtrip.md"
    completed = _run_cli(tmp_path, "--output-md", str(out_md))
    assert completed.returncode == 0
    assert out_md.exists()
    assert "Round-Trip" in out_md.read_text(encoding="utf-8")


# 27
def test_no_backtrader_import() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + Path(SCRIPT).read_text(encoding="utf-8")).lower()
    assert "import backtrader" not in text
    assert "backtrader." not in text
    assert "cerebro" not in text


# 28
def test_no_optimizer_code() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + Path(SCRIPT).read_text(encoding="utf-8")).lower()
    for token in ["def optimize", "grid_search", "gridsearch", "itertools.product", "scipy.optimize"]:
        assert token not in text


# 29
def test_no_network_imports() -> None:
    text = SOURCE.read_text(encoding="utf-8") + Path(SCRIPT).read_text(encoding="utf-8")
    assert all(name not in text for name in ["requests", "httpx", "urllib", "socket"])


# 30
def test_no_db_mutation_code() -> None:
    text = SOURCE.read_text(encoding="utf-8").lower()
    for token in ["insert into", "update ", "delete from", "create table", "sqlite3", "execute("]:
        assert token not in text


def test_no_engine_call() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "run_backtest" not in text
    assert "mvp_engine" not in text


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    prep = _write_preparation(tmp_path)
    signal = _write_signal(tmp_path)
    metrics = _write_metrics(tmp_path)
    args = [
        sys.executable,
        str(SCRIPT),
        "--preparation-json",
        str(prep),
        "--fixture-signal-json",
        str(signal),
        "--fixture-metrics-json",
        str(metrics),
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
