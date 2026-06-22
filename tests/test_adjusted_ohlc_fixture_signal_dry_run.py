from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.backtest.adjusted_ohlc_fixture_signal_dry_run import (
    build_fixture_signal_preview,
    render_fixture_signal_report_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/run_adjusted_ohlc_fixture_signal_dry_run.py")
SOURCE = Path("src/trading_agent/backtest/adjusted_ohlc_fixture_signal_dry_run.py")


def _prep_row(symbol: str, datetime_value: str = "2026-01-02", close: float = 80.0) -> dict[str, object]:
    return {
        "symbol": symbol,
        "datetime": datetime_value,
        "open": close * 0.95,
        "high": close * 1.05,
        "low": close * 0.9,
        "close": close,
        "volume": 1000.0,
        "source_price_basis": "adjusted_ohlc",
        "adjustment_factor": 0.8,
        "adjustment_source_id": "fixture:reviewed_evidence_package",
        "adjustment_raw_path": "payload.json",
        "adjustment_method": "adjusted_close_ratio",
    }


def _write_preparation(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = ("FPT", "VNM", "VCB"),
    rows: list[dict[str, object]] | None = None,
    overrides: dict[str, object] | None = None,
) -> Path:
    if rows is None:
        rows = [_prep_row(symbol) for symbol in symbols]
    payload: dict[str, object] = {
        "status": "ok",
        "dry_run_stage": "backtest_input_preparation",
        "backtest_input_status": "ready_for_research_dry_run",
        "price_basis": "adjusted_ohlc",
        "symbols": list(symbols),
        "requested_symbols": list(symbols),
        "represented_symbols": list(symbols),
        "missing_symbols": [],
        "row_count": len(rows),
        "assumptions": {
            "transaction_cost_bps": 15,
            "slippage_bps": 10,
            "exchange": "HOSE",
            "slippage_band_bps": 700,
        },
        "rows_preview": rows,
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


def _build(tmp_path: Path, *, prep_path: Path | None = None, **kwargs: object) -> dict[str, object]:
    if prep_path is None:
        prep_path = _write_preparation(tmp_path)
    params: dict[str, object] = {
        "preparation_path": prep_path,
        "symbols": ["FPT", "VNM", "VCB"],
        "signal_mode": "all_cash",
    }
    params.update(kwargs)
    return build_fixture_signal_preview(**params)  # type: ignore[arg-type]


# 1
def test_missing_preparation_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, prep_path=tmp_path / "nope.json")
    assert result["status"] == "blocked"
    assert any(str(r).startswith("preparation_missing:") for r in result["reasons"])


# 2
def test_invalid_json_blocks(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = _build(tmp_path, prep_path=bad)
    assert result["status"] == "blocked"
    assert "preparation_invalid_json" in result["reasons"]


# 3
def test_preparation_not_object_blocks(tmp_path: Path) -> None:
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    result = _build(tmp_path, prep_path=arr)
    assert result["status"] == "blocked"
    assert "preparation_must_be_object" in result["reasons"]


# 4
def test_preparation_status_not_ok_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(tmp_path, overrides={"status": "blocked"})
    result = _build(tmp_path, prep_path=prep)
    assert result["status"] == "blocked"
    assert "preparation_status_not_ok:blocked" in result["reasons"]


# 5
def test_preparation_input_status_not_ready_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(tmp_path, overrides={"backtest_input_status": "blocked"})
    result = _build(tmp_path, prep_path=prep)
    assert result["status"] == "blocked"
    assert "preparation_input_status_not_ready:blocked" in result["reasons"]


# 6
def test_price_basis_not_adjusted_ohlc_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(tmp_path, overrides={"price_basis": "raw_ohlc"})
    result = _build(tmp_path, prep_path=prep)
    assert result["status"] == "blocked"
    assert "preparation_price_basis_not_adjusted_ohlc:raw_ohlc" in result["reasons"]


# 7
def test_missing_requested_symbol_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(
        tmp_path,
        symbols=("FPT",),
        rows=[_prep_row("FPT")],
        overrides={"represented_symbols": ["FPT"]},
    )
    result = _build(tmp_path, prep_path=prep, symbols=["FPT", "VNM"])
    assert result["status"] == "blocked"
    assert "requested_symbol_not_represented:VNM" in result["reasons"]


# 8
def test_missing_assumptions_blocks(tmp_path: Path) -> None:
    prep = _write_preparation(tmp_path, overrides={"assumptions": {"exchange": "HOSE"}})
    result = _build(tmp_path, prep_path=prep)
    assert result["status"] == "blocked"
    assert "missing_cost_slippage_assumptions" in result["reasons"]


# 9
def test_max_rows_zero_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, max_rows=0)
    assert result["status"] == "blocked"
    assert "max_rows_must_be_positive" in result["reasons"]


# 10
def test_unknown_signal_mode_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, signal_mode="magic_alpha")
    assert result["status"] == "blocked"
    assert "unknown_signal_mode:magic_alpha" in result["reasons"]


# 11
def test_valid_all_cash_fixture_ok(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["status"] == "ok"
    assert result["dry_run_stage"] == "fixture_signal_preview"
    assert result["price_basis"] == "adjusted_ohlc"
    assert result["signal_mode"] == "all_cash"
    assert result["row_count"] == 3


# 12
def test_output_uses_no_position(tmp_path: Path) -> None:
    result = _build(tmp_path)
    actions = {row["fixture_signal_action"] for row in result["signal_rows"]}
    assert actions == {"NO_POSITION"}
    for row in result["signal_rows"]:
        assert row["reason"] == "research_fixture_all_cash"


# 13
def test_output_performance_metrics_null(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["performance_metrics"] is None


# 14
def test_output_not_financial_advice_true(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["not_financial_advice"] is True


# 15 + 23
def test_output_contains_no_recommendation_language(tmp_path: Path) -> None:
    result = _build(tmp_path)
    text = json.dumps(result).lower()
    for word in ["buy", "sell", "hold", "recommend"]:
        assert word not in text


def test_alternating_mode_has_no_recommendation_language(tmp_path: Path) -> None:
    result = _build(tmp_path, signal_mode="alternating_fixture_signal")
    assert result["status"] == "ok"
    text = json.dumps(result).lower()
    for word in ["buy", "sell", "hold"]:
        assert word not in text


# 16
def test_markdown_report_renders_and_writes(tmp_path: Path) -> None:
    result = _build(tmp_path)
    md = render_fixture_signal_report_markdown(result)
    assert "# Adjusted OHLC Fixture Signal Dry-Run" in md
    assert "NO_POSITION" in md
    lower = md.lower()
    for word in ["buy", "sell", "hold"]:
        assert word not in lower


# 17
def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path)
    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


# 18
def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--preparation-json", str(tmp_path / "missing.json"))
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "preparation_missing" in completed.stdout


def test_cli_writes_markdown(tmp_path: Path) -> None:
    out_md = tmp_path / "report.md"
    completed = _run_cli(tmp_path, "--output-md", str(out_md))
    assert completed.returncode == 0
    assert out_md.exists()
    assert "Fixture Signal" in out_md.read_text(encoding="utf-8")


# 19
def test_no_backtrader_import() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")).lower()
    assert "import backtrader" not in text
    assert "backtrader." not in text
    assert "cerebro" not in text


# 20
def test_no_optimizer_code() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")).lower()
    for token in ["def optimize", "grid_search", "gridsearch", "itertools.product", "scipy.optimize"]:
        assert token not in text


# 21
def test_no_network_imports() -> None:
    text = SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")
    assert all(name not in text for name in ["requests", "httpx", "urllib", "socket"])


# 22
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
    args = [
        sys.executable,
        str(SCRIPT),
        "--preparation-json",
        str(prep),
        "--symbols",
        "FPT,VNM,VCB",
        "--signal-mode",
        "all_cash",
    ]
    for index in range(0, len(overrides), 2):
        flag = overrides[index]
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
