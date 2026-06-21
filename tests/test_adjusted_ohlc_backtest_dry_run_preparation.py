from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.backtest.adjusted_ohlc_backtest_dry_run_preparation import (
    build_backtest_input_preview,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/prepare_adjusted_ohlc_backtest_dry_run.py")
SOURCE = Path("src/trading_agent/backtest/adjusted_ohlc_backtest_dry_run_preparation.py")


def _feed_row(symbol: str, datetime_value: str = "2026-01-02", close: float = 80.0) -> dict[str, object]:
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


def _write_feed_preview(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = ("FPT", "VNM", "VCB"),
    rows: list[dict[str, object]] | None = None,
    overrides: dict[str, object] | None = None,
) -> Path:
    if rows is None:
        rows = [_feed_row(symbol) for symbol in symbols]
    payload: dict[str, object] = {
        "status": "ok",
        "feed_contract_version": "adjusted_ohlc_feed_v1",
        "source_price_basis": "adjusted_ohlc",
        "symbols": list(symbols),
        "missing_symbols": [],
        "row_count": len(rows),
        "total_eligible_rows": len(rows),
        "rows": rows,
        "reasons": [],
        "caveats": [],
    }
    if overrides:
        payload.update(overrides)
    path = tmp_path / "feed_preview.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _build(tmp_path: Path, *, feed_path: Path | None = None, **kwargs: object) -> dict[str, object]:
    if feed_path is None:
        feed_path = _write_feed_preview(tmp_path)
    params: dict[str, object] = {
        "feed_preview_path": feed_path,
        "symbols": ["FPT", "VNM", "VCB"],
        "transaction_cost_bps": 15.0,
        "slippage_bps": 10.0,
        "exchange": "HOSE",
    }
    params.update(kwargs)
    return build_backtest_input_preview(**params)  # type: ignore[arg-type]


# 1
def test_missing_feed_preview_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, feed_path=tmp_path / "nope.json")
    assert result["status"] == "blocked"
    assert any(str(r).startswith("feed_preview_missing:") for r in result["reasons"])


# 2
def test_invalid_json_blocks_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = _build(tmp_path, feed_path=bad)
    assert result["status"] == "blocked"
    assert "feed_preview_invalid_json" in result["reasons"]


# 3
def test_feed_preview_not_object_blocks(tmp_path: Path) -> None:
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    result = _build(tmp_path, feed_path=arr)
    assert result["status"] == "blocked"
    assert "feed_preview_must_be_object" in result["reasons"]


# 4
def test_feed_status_not_ok_blocks(tmp_path: Path) -> None:
    feed = _write_feed_preview(tmp_path, overrides={"status": "not_ready"})
    result = _build(tmp_path, feed_path=feed)
    assert result["status"] == "blocked"
    assert "feed_status_not_ok:not_ready" in result["reasons"]


# 5
def test_feed_contract_version_mismatch_blocks(tmp_path: Path) -> None:
    feed = _write_feed_preview(tmp_path, overrides={"feed_contract_version": "other_v2"})
    result = _build(tmp_path, feed_path=feed)
    assert result["status"] == "blocked"
    assert "feed_contract_version_mismatch:other_v2" in result["reasons"]


# 6
def test_source_price_basis_not_adjusted_ohlc_blocks(tmp_path: Path) -> None:
    feed = _write_feed_preview(tmp_path, overrides={"source_price_basis": "raw_ohlc"})
    result = _build(tmp_path, feed_path=feed)
    assert result["status"] == "blocked"
    assert "feed_source_price_basis_not_adjusted_ohlc:raw_ohlc" in result["reasons"]


# 7
def test_missing_requested_symbol_blocks(tmp_path: Path) -> None:
    feed = _write_feed_preview(tmp_path, symbols=("FPT",), rows=[_feed_row("FPT")])
    result = _build(tmp_path, feed_path=feed, symbols=["FPT", "VNM"])
    assert result["status"] == "blocked"
    assert "requested_symbol_missing_from_feed:VNM" in result["reasons"]


# 8
def test_invalid_start_date_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, start_date="2026/01/01")
    assert result["status"] == "blocked"
    assert "invalid_start_date_format:2026/01/01" in result["reasons"]


# 9
def test_start_date_after_end_date_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, start_date="2026-01-05", end_date="2026-01-01")
    assert result["status"] == "blocked"
    assert "invalid_date_range:start_after_end" in result["reasons"]


# 10
def test_negative_transaction_cost_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, transaction_cost_bps=-1.0)
    assert result["status"] == "blocked"
    assert "transaction_cost_bps_must_be_non_negative" in result["reasons"]


# 11
def test_negative_slippage_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, slippage_bps=-1.0)
    assert result["status"] == "blocked"
    assert "slippage_bps_must_be_non_negative" in result["reasons"]


# 12
def test_hose_slippage_over_band_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, exchange="HOSE", slippage_bps=701.0)
    assert result["status"] == "blocked"
    assert any(str(r).startswith("slippage_bps_exceeds_exchange_band:") for r in result["reasons"])


# 13
def test_hsx_slippage_over_band_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, exchange="HSX", slippage_bps=701.0)
    assert result["status"] == "blocked"
    assert any(str(r).startswith("slippage_bps_exceeds_exchange_band:") for r in result["reasons"])


# 14
def test_upcom_slippage_over_band_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, exchange="UPCoM", slippage_bps=1501.0)
    assert result["status"] == "blocked"
    assert any(str(r).startswith("slippage_bps_exceeds_exchange_band:") for r in result["reasons"])


def test_upcom_slippage_within_band_ok(tmp_path: Path) -> None:
    result = _build(tmp_path, exchange="UPCoM", slippage_bps=1500.0)
    assert result["status"] == "ok"
    assert result["assumptions"]["slippage_band_bps"] == 1500


# 15
def test_valid_feed_preview_ready_for_research_dry_run(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["status"] == "ok"
    assert result["backtest_input_status"] == "ready_for_research_dry_run"
    assert result["price_basis"] == "adjusted_ohlc"
    assert result["row_count"] == 3


# 16
def test_output_contains_cost_and_slippage_assumptions(tmp_path: Path) -> None:
    result = _build(tmp_path, transaction_cost_bps=15.0, slippage_bps=10.0, exchange="HOSE")
    assumptions = result["assumptions"]
    assert assumptions["transaction_cost_bps"] == 15.0
    assert assumptions["slippage_bps"] == 10.0
    assert assumptions["exchange"] == "HOSE"
    assert assumptions["slippage_band_bps"] == 700


# 17
def test_output_contains_no_recommendation_language(tmp_path: Path) -> None:
    result = _build(tmp_path, fixture_signal_mode=True)
    text = json.dumps(result).lower()
    # No actionable buy/sell/hold instruction should appear anywhere in output.
    for word in ["buy", "sell", "hold"]:
        assert word not in text
    assert result["not_financial_advice"] is True


# 18
def test_raw_ohlc_fields_not_accepted(tmp_path: Path) -> None:
    row = _feed_row("FPT")
    row["raw_close"] = 95.0
    feed = _write_feed_preview(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, feed_path=feed, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_row_field:raw_close" in result["reasons"]


def test_signal_field_in_row_blocks(tmp_path: Path) -> None:
    row = _feed_row("FPT")
    row["signal_action"] = "BUY"
    feed = _write_feed_preview(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, feed_path=feed, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "forbidden_row_field:signal_action" in result["reasons"]


def test_row_missing_price_field_blocks(tmp_path: Path) -> None:
    row = _feed_row("FPT")
    row["close"] = None
    feed = _write_feed_preview(tmp_path, symbols=("FPT",), rows=[row])
    result = _build(tmp_path, feed_path=feed, symbols=["FPT"])
    assert result["status"] == "blocked"
    assert "row_missing_price_field:close" in result["reasons"]


# 19
def test_no_backtrader_import() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")).lower()
    assert "import backtrader" not in text
    assert "backtrader." not in text
    assert "cerebro" not in text


# 20
def test_no_optimizer_code() -> None:
    text = (SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")).lower()
    # Reject actual optimizer constructs, not the negative caveat wording.
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


# 23
def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path)
    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


# 24
def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--feed-preview", str(tmp_path / "missing.json"))
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "feed_preview_missing" in completed.stdout


def test_cli_invalid_exchange_exits_one(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--exchange", "NYSE")
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "unknown_exchange:NYSE" in completed.stdout


# 25
def test_fixture_signal_mode_labels_research_fixture_signal(tmp_path: Path) -> None:
    result = _build(tmp_path, fixture_signal_mode=True)
    assert result["status"] == "ok"
    fixture = result["fixture_signal"]
    assert fixture["mode"] == "research_fixture_signal"
    assert fixture["executes_engine"] is False
    assert fixture["produces_performance"] is False


def test_output_json_written(tmp_path: Path) -> None:
    output = tmp_path / "prep.json"
    completed = _run_cli(tmp_path, "--output-json", str(output))
    assert completed.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"


DRY_RUN_DOC = Path("docs/backtest/adjusted_ohlc_feed_to_backtest_dry_run.md")
PROGRESS_DOC = Path("docs/reports/progress_report.md")


def test_dry_run_doc_has_valid_frontmatter() -> None:
    lines = (ROOT / DRY_RUN_DOC).read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    assert "title: adjusted_ohlc_feed_to_backtest_dry_run" in lines[:6]
    assert "toc_min_heading_level: 2" in lines[:6]
    assert "toc_max_heading_level: 3" in lines[:6]
    assert lines[4] == "---"


def test_no_duplicate_progress_rows() -> None:
    text = (ROOT / PROGRESS_DOC).read_text(encoding="utf-8")
    assert text.count("| Adjusted OHLC backtest feed contract |") == 1
    assert text.count("| Adjusted OHLC backtest dry-run preparation |") == 1


def test_date_filter_removing_symbol_blocks(tmp_path: Path) -> None:
    rows = [
        _feed_row("FPT", datetime_value="2026-01-02"),
        _feed_row("VNM", datetime_value="2026-01-02"),
        _feed_row("VCB", datetime_value="2026-06-01"),
    ]
    feed = _write_feed_preview(tmp_path, rows=rows)
    result = _build(tmp_path, feed_path=feed, start_date="2026-01-01", end_date="2026-01-31")
    assert result["status"] == "blocked"
    assert "prepared_input_missing_symbol_after_filter:VCB" in result["reasons"]
    assert "VCB" in result["missing_symbols"]


def test_max_rows_truncating_symbol_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, max_rows=2)
    assert result["status"] == "blocked"
    assert "prepared_input_missing_symbol_after_limit:VCB" in result["reasons"]
    assert "VCB" in result["missing_symbols"]


def test_max_rows_zero_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, max_rows=0)
    assert result["status"] == "blocked"
    assert "max_rows_must_be_positive" in result["reasons"]


def test_unknown_exchange_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, exchange="NYSE")
    assert result["status"] == "blocked"
    assert "unknown_exchange:NYSE" in result["reasons"]


def test_output_symbol_coverage_fields(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["status"] == "ok"
    assert result["requested_symbols"] == ["FPT", "VNM", "VCB"]
    assert result["represented_symbols"] == ["FPT", "VNM", "VCB"]
    assert result["missing_symbols"] == []
    assert result["not_financial_advice"] is True


def test_fixture_signal_null_when_mode_off(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["fixture_signal"] is None


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    feed = _write_feed_preview(tmp_path)
    args = [
        sys.executable,
        str(SCRIPT),
        "--feed-preview",
        str(feed),
        "--symbols",
        "FPT,VNM,VCB",
        "--transaction-cost-bps",
        "15",
        "--slippage-bps",
        "10",
        "--exchange",
        "HOSE",
    ]
    for index in range(0, len(overrides), 2):
        flag = overrides[index]
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)
