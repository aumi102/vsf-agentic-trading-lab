from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.backtest.adjusted_ohlc_feed_readiness import check_adjusted_ohlc_feed_readiness
from trading_agent.db.schema import create_schema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/preview_adjusted_ohlc_backtest_feed.py")
SOURCE = Path("src/trading_agent/backtest/adjusted_ohlc_feed_readiness.py")


def test_missing_audit_report_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=tmp_path / "missing_audit.json",
    )

    assert result["status"] == "not_ready"
    assert any(reason.startswith("audit_report_missing:") for reason in result["reasons"])


def test_audit_report_not_ok_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, status="not_ready", gate="blocked"),
    )

    assert result["status"] == "not_ready"
    assert "audit_status_not_ok:not_ready" in result["reasons"]


def test_audit_report_without_planning_gate_pass_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, gate="blocked"),
    )

    assert result["status"] == "not_ready"
    assert "audit_backtest_planning_gate_not_pass:blocked" in result["reasons"]


def test_missing_adjusted_price_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path, null_column="adjusted_close"),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert "missing_adjusted_rows:1" in result["reasons"]


def test_missing_provenance_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path, null_column="adjustment_raw_path"),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "not_ready"
    assert "missing_provenance_rows:1" in result["reasons"]


def test_successful_feed_preview_uses_adjusted_ohlc_as_price_fields(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "ok"
    row = result["rows"][0]
    assert row["open"] == 76.0
    assert row["high"] == 84.0
    assert row["low"] == 72.0
    assert row["close"] == 80.0
    assert row["source_price_basis"] == "adjusted_ohlc"


def test_raw_ohlc_not_used_as_trading_price(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    row = result["rows"][0]
    assert row["open"] != 95.0
    assert "raw_open" not in row
    assert "raw_close" not in row


def test_date_range_filters(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path, include_second_date=True),
        symbols=["FPT"],
        start_date="2026-01-03",
        end_date="2026-01-03",
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "ok"
    assert [row["datetime"] for row in result["rows"]] == ["2026-01-03"]


def test_symbol_whitelist_filters(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["VNM"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "ok"
    assert {row["symbol"] for row in result["rows"]} == {"VNM"}


def test_max_rows_enforced(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path, include_second_date=True),
        symbols=["FPT", "VNM", "VCB"],
        audit_report_path=_write_audit(tmp_path),
        max_rows=2,
    )

    assert result["status"] == "ok"
    assert result["row_count"] == 2


def test_demo_db_refused_by_default(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=Path("data/demo/mvp_trading_agent.sqlite"),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "invalid_request"
    assert "demo_db_blocked" in result["reasons"]


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path)

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--audit-report", str(tmp_path / "missing.json"))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "audit_report_missing" in completed.stdout


def test_output_json_written(tmp_path: Path) -> None:
    output = tmp_path / "feed_preview.json"

    completed = _run_cli(tmp_path, "--output-json", str(output))

    assert completed.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"


def test_no_backtrader_import() -> None:
    text = SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")

    assert "import backtrader" not in text.lower()


def test_no_strategy_execution_code() -> None:
    text = SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")

    assert "run_backtest" not in text
    assert "strategy_id" not in text


def test_no_network_imports() -> None:
    text = SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])


def test_no_db_mutation(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    before = _raw_rows(db_path)

    result = check_adjusted_ohlc_feed_readiness(
        db_path=db_path,
        symbols=["FPT", "VNM", "VCB"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] == "ok"
    assert _raw_rows(db_path) == before


# --- Phase C: symbol coverage -------------------------------------------------


def test_missing_requested_symbol_blocks(tmp_path: Path) -> None:
    db_path = _make_db_with_rows(tmp_path, [_eligible_row("FPT")])

    result = check_adjusted_ohlc_feed_readiness(
        db_path=db_path,
        symbols=["FPT", "VNM"],
        audit_report_path=_write_audit(tmp_path, symbols=("FPT", "VNM")),
    )

    assert result["status"] == "not_ready"
    assert "missing_requested_symbol:VNM" in result["reasons"]
    assert result["missing_symbols"] == ["VNM"]
    assert result["symbols_with_eligible_rows"] == ["FPT"]


def test_symbol_with_null_adjusted_ohlc_is_missing(tmp_path: Path) -> None:
    db_path = _make_db_with_rows(tmp_path, [_eligible_row("VNM", adjusted_close=None)])

    result = check_adjusted_ohlc_feed_readiness(
        db_path=db_path,
        symbols=["VNM"],
        audit_report_path=_write_audit(tmp_path, symbols=("VNM",)),
    )

    assert result["status"] == "not_ready"
    assert "missing_requested_symbol:VNM" in result["reasons"]
    assert result["missing_symbols"] == ["VNM"]


def test_symbol_with_non_ok_quality_is_missing(tmp_path: Path) -> None:
    db_path = _make_db_with_rows(tmp_path, [_eligible_row("VNM", quality_status="ohlc_fail")])

    result = check_adjusted_ohlc_feed_readiness(
        db_path=db_path,
        symbols=["VNM"],
        audit_report_path=_write_audit(tmp_path, symbols=("VNM",)),
    )

    assert result["status"] == "not_ready"
    assert "missing_requested_symbol:VNM" in result["reasons"]


def test_symbol_with_missing_provenance_is_missing(tmp_path: Path) -> None:
    db_path = _make_db_with_rows(tmp_path, [_eligible_row("VNM", adjustment_raw_path=None)])

    result = check_adjusted_ohlc_feed_readiness(
        db_path=db_path,
        symbols=["VNM"],
        audit_report_path=_write_audit(tmp_path, symbols=("VNM",)),
    )

    assert result["status"] == "not_ready"
    assert "missing_requested_symbol:VNM" in result["reasons"]


# --- Phase D: stale audit report gate -----------------------------------------


def test_audit_missing_requested_symbol_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT", "VNM"],
        audit_report_path=_write_audit(tmp_path, symbols=("FPT",)),
    )

    assert result["status"] == "not_ready"
    assert "audit_missing_symbol:VNM" in result["reasons"]


def test_audit_evidence_mode_not_strict_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"evidence_mode": "incomplete"}),
    )

    assert result["status"] == "not_ready"
    assert "audit_evidence_mode_not_strict:incomplete" in result["reasons"]


def test_audit_required_evidence_not_present_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"required_evidence_present": False}),
    )

    assert result["status"] == "not_ready"
    assert "audit_required_evidence_not_present" in result["reasons"]


def test_audit_db_path_mismatch_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"db_path": "/other/place/elsewhere.sqlite"}),
    )

    assert result["status"] == "not_ready"
    assert "audit_db_path_mismatch" in result["reasons"]


def test_audit_unadjusted_rows_present_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"unadjusted_rows": 1}),
    )

    assert result["status"] == "not_ready"
    assert "audit_unadjusted_rows_present:1" in result["reasons"]


def test_audit_readiness_status_not_ok_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"readiness_status": "not_ready"}),
    )

    assert result["status"] == "not_ready"
    assert "audit_readiness_status_not_ok:not_ready" in result["reasons"]


def test_audit_validation_status_not_ok_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"validation_status": "not_ready"}),
    )

    assert result["status"] == "not_ready"
    assert "audit_validation_status_not_ok:not_ready" in result["reasons"]


def test_audit_db_mutation_not_made_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path, overrides={"db_mutation_made": False}),
    )

    assert result["status"] == "not_ready"
    assert "audit_db_mutation_not_made" in result["reasons"]


def test_audit_missing_required_metadata_blocks(tmp_path: Path) -> None:
    audit = _write_raw_audit(
        tmp_path,
        {"status": "ok", "backtest_planning_gate": "pass", "reasons": []},
    )

    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=audit,
    )

    assert result["status"] == "not_ready"
    assert any(reason.startswith("audit_missing_required_field:") for reason in result["reasons"])


# --- Phase E: date and max_rows validation ------------------------------------


def test_invalid_date_format_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        start_date="2026/01/01",
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] != "ok"
    assert "invalid_start_date_format:2026/01/01" in result["reasons"]


def test_start_date_after_end_date_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        start_date="2026-01-05",
        end_date="2026-01-01",
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["status"] != "ok"
    assert "invalid_date_range:start_after_end" in result["reasons"]


def test_max_rows_zero_blocks(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
        max_rows=0,
    )

    assert result["status"] != "ok"
    assert "max_rows_must_be_positive" in result["reasons"]


def test_cli_max_rows_zero_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--max-rows", "0")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "max_rows_must_be_positive" in completed.stdout


# --- Phase F: feed output contract --------------------------------------------


def test_feed_contract_version_in_output(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    assert result["feed_contract_version"] == "adjusted_ohlc_feed_v1"
    assert result["source_price_basis"] == "adjusted_ohlc"
    assert result["missing_symbols"] == []


def test_rows_have_no_raw_or_signal_fields(tmp_path: Path) -> None:
    result = check_adjusted_ohlc_feed_readiness(
        db_path=_make_db(tmp_path),
        symbols=["FPT"],
        audit_report_path=_write_audit(tmp_path),
    )

    forbidden = {
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "signal",
        "signal_id",
        "trade",
        "trade_id",
        "pnl",
        "equity",
        "strategy",
        "strategy_id",
    }
    for row in result["rows"]:
        assert forbidden.isdisjoint(row.keys())
        assert row["source_price_basis"] == "adjusted_ohlc"


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    db_path = _make_db(tmp_path)
    audit = _write_audit(tmp_path)
    args = [
        sys.executable,
        str(SCRIPT),
        "--db-path",
        str(db_path),
        "--symbols",
        "FPT,VNM,VCB",
        "--audit-report",
        str(audit),
    ]
    for index in range(0, len(overrides), 2):
        flag = overrides[index]
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _make_db(tmp_path: Path, *, null_column: str | None = None, include_second_date: bool = False) -> Path:
    db_path = tmp_path / "feed_readiness.sqlite"
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        for trade_date in ["2026-01-02", *([] if not include_second_date else ["2026-01-03"])]:
            for symbol, close in {"FPT": 100.0, "VNM": 200.0, "VCB": 50.0}.items():
                _insert_daily_price(con, _row(symbol, trade_date, close, null_column=null_column if symbol == "FPT" else None))
        con.commit()
    return db_path


def _row(symbol: str, trade_date: str, close: float, *, null_column: str | None = None) -> dict[str, object]:
    factor = 0.8
    row: dict[str, object] = {
        "security_id": f"fixture:feed:{symbol}:{trade_date}",
        "symbol": symbol,
        "trade_date": trade_date,
        "open": close * 0.95,
        "high": close * 1.05,
        "low": close * 0.9,
        "close": close,
        "adjustment_factor": factor,
        "adjusted_open": close * 0.95 * factor,
        "adjusted_high": close * 1.05 * factor,
        "adjusted_low": close * 0.9 * factor,
        "adjusted_close": close * factor,
        "adjustment_source_id": "fixture:reviewed_evidence_package",
        "adjustment_raw_path": "payload.json",
        "adjustment_method": "adjusted_close_ratio",
        "volume": 1000.0,
        "value": close * 1000.0,
        "price_basis": "source_reported",
        "adjustment_status": "adjusted",
        "source_id": "fixture:daily_prices_feed",
        "raw_path": f"synthetic://feed/{symbol.lower()}/{trade_date}",
        "quality_status": "ok",
    }
    if null_column:
        row[null_column] = None
    return row


def _insert_daily_price(con: sqlite3.Connection, row: dict[str, object]) -> None:
    columns = list(row.keys())
    placeholders = ", ".join(["?"] * len(columns))
    con.execute(
        f"INSERT INTO daily_prices ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def _write_audit(
    tmp_path: Path,
    *,
    status: str = "ok",
    gate: str = "pass",
    db_path: Path | None = None,
    symbols: tuple[str, ...] | list[str] = ("FPT", "VNM", "VCB"),
    overrides: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / "adjusted_ohlc_audit.json"
    if db_path is None:
        db_path = tmp_path / "feed_readiness.sqlite"
    report: dict[str, object] = {
        "status": status,
        "backtest_planning_gate": gate,
        "evidence_mode": "strict",
        "required_evidence_present": True,
        "symbols": list(symbols),
        "db_path": str(db_path),
        "unadjusted_rows": 0,
        "readiness_status": "ok",
        "backtest_gate": "pass",
        "validation_status": "ok",
        "db_mutation_made": True,
        "reasons": [],
    }
    if overrides:
        report.update(overrides)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _write_raw_audit(tmp_path: Path, report: dict[str, object]) -> Path:
    path = tmp_path / "adjusted_ohlc_audit.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _make_db_with_rows(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    db_path = tmp_path / "feed_readiness.sqlite"
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        for row in rows:
            _insert_daily_price(con, row)
        con.commit()
    return db_path


def _eligible_row(symbol: str, *, trade_date: str = "2026-01-02", close: float = 100.0, **overrides: object) -> dict[str, object]:
    row = _row(symbol, trade_date, close)
    row.update(overrides)
    return row


def _raw_rows(db_path: Path) -> dict[str, tuple[float, float, float, float]]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT symbol, open, high, low, close FROM daily_prices ORDER BY symbol").fetchall()
    return {str(row["symbol"]): (row["open"], row["high"], row["low"], row["close"]) for row in rows}
