from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness
from trading_agent.ingestion.apply_adjustment_factors import apply_adjustment_factors_to_db


ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_summarizes_without_db_mutation(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=True)

    assert result["status"] == "ok"
    assert result["rows_with_usable_factor"] == 1
    assert result["rows_updated"] == 0
    assert result["db_mutation_made"] is False
    row = _daily_row(db_path)
    assert row["adjustment_factor"] is None
    assert row["adjusted_open"] is None
    assert row["adjustment_source_id"] is None
    assert row["adjustment_raw_path"] is None
    assert row["adjustment_method"] is None


def test_execute_mode_updates_adjusted_columns(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["rows_updated"] == 1
    assert result["db_mutation_made"] is True
    row = _daily_row(db_path)
    assert row["adjustment_factor"] == 0.8
    assert row["adjusted_open"] == 8.0
    assert row["adjusted_high"] == 8.8
    assert row["adjusted_low"] == 7.2
    assert row["adjusted_close"] == 8.4
    assert row["adjustment_status"] == "adjusted"
    assert row["adjustment_source_id"] == "fixture:adjusted_close"
    assert row["adjustment_raw_path"] == "fixtures/fpt_adjusted.json"
    assert row["adjustment_method"] == "adjusted_close_ratio"


def test_raw_ohlc_columns_remain_unchanged(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    row = _daily_row(db_path)
    assert row["open"] == 10.0
    assert row["high"] == 11.0
    assert row["low"] == 9.0
    assert row["close"] == 10.5
    assert row["source_id"] == "fixture:daily_prices"
    assert row["raw_path"] == "fixtures/fpt_2026-01-02.json"


def test_missing_factor_leaves_row_unadjusted_and_reported(tmp_path: Path) -> None:
    db_path = _make_db(
        tmp_path,
        [
            {"symbol": "FPT", "trade_date": "2026-01-02"},
            {"symbol": "FPT", "trade_date": "2026-01-03"},
        ],
    )
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["rows_with_usable_factor"] == 1
    assert result["rows_missing_factor"] == 1
    assert result["rows_updated"] == 1
    readiness = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])
    assert readiness["status"] == "not_ready"
    assert readiness["backtest_gate"] == "blocked"


def test_invalid_factor_record_is_skipped_and_reported(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_raw_factors(
        tmp_path,
        [
            {
                "symbol": "FPT",
                "trade_date": "2026-01-02",
                "factor": -0.8,
                "source_id": "fixture:adjusted_close",
                "method": "adjusted_close_ratio",
                "raw_path": "fixtures/fpt_adjusted.json",
                "status": "ok",
                "reasons": [],
            }
        ],
    )

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["invalid_factor_records"] == 1
    assert result["rows_missing_factor"] == 1
    assert result["rows_updated"] == 0


def test_factor_without_source_id_or_raw_path_is_rejected(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_raw_factors(
        tmp_path,
        [
            {
                "symbol": "FPT",
                "trade_date": "2026-01-02",
                "factor": 0.8,
                "source_id": "",
                "method": "adjusted_close_ratio",
                "raw_path": "",
                "status": "ok",
                "reasons": [],
            }
        ],
    )

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["invalid_factor_records"] == 1
    assert result["rows_missing_factor"] == 1
    assert result["rows_updated"] == 0


def test_method_unknown_factor_record_is_rejected(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_raw_factors(
        tmp_path,
        [
            {
                "symbol": "FPT",
                "trade_date": "2026-01-02",
                "factor": 0.8,
                "source_id": "fixture:adjusted_close",
                "method": "unknown",
                "raw_path": "fixtures/fpt_adjusted.json",
                "status": "ok",
                "reasons": [],
            }
        ],
    )

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["invalid_factor_records"] == 1
    assert result["rows_missing_factor"] == 1
    assert result["rows_updated"] == 0


def test_duplicate_factor_records_are_reported_and_not_applied(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_raw_factors(
        tmp_path,
        [
            _factor_record("FPT", "2026-01-02", 0.8, raw_path="fixtures/a.json"),
            _factor_record("FPT", "2026-01-02", 0.7, raw_path="fixtures/b.json"),
        ],
    )

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["duplicate_factor_records"] == 2
    assert result["rows_missing_factor"] == 1
    assert result["rows_updated"] == 0


def test_no_factor_one_fallback(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_raw_factors(tmp_path, [])

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["rows_missing_factor"] == 1
    assert result["rows_updated"] == 0
    assert _daily_row(db_path)["adjustment_factor"] is None


def test_adjusted_high_low_consistency_is_validated(tmp_path: Path) -> None:
    db_path = _make_db(
        tmp_path,
        [{"symbol": "FPT", "trade_date": "2026-01-02", "open": 10.0, "high": 9.0, "low": 8.0, "close": 10.5}],
    )
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["rows_invalid"] == 1
    assert result["rows_updated"] == 0
    assert "adjusted_high_below_open_or_close" in result["results"][0]["reasons"]


def test_readiness_gate_passes_after_fully_covered_execute(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    readiness = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])
    assert readiness["status"] == "ok"
    assert readiness["backtest_gate"] == "pass"


def test_cli_missing_factor_file_returns_clean_error(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    missing_path = tmp_path / "missing.json"

    completed = _run_cli("--db-path", str(db_path), "--factors", str(missing_path), "--symbols", "FPT")

    assert completed.returncode == 1
    assert '"status": "missing_factor_file"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_invalid_factor_json_returns_clean_error(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = tmp_path / "bad.json"
    factor_path.write_text("{bad-json", encoding="utf-8")

    completed = _run_cli("--db-path", str(db_path), "--factors", str(factor_path), "--symbols", "FPT")

    assert completed.returncode == 1
    assert '"status": "invalid_factor_json"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_requires_explicit_symbols_to_avoid_broad_mutation(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    completed = _run_cli("--db-path", str(db_path), "--factors", str(factor_path))

    assert completed.returncode == 1
    assert '"status": "invalid_request"' in completed.stdout
    assert _daily_row(db_path)["adjustment_factor"] is None


def test_cli_dry_run_and_execute_together_is_invalid_request(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    completed = _run_cli(
        "--db-path",
        str(db_path),
        "--factors",
        str(factor_path),
        "--symbols",
        "FPT",
        "--dry-run",
        "--execute",
    )

    assert completed.returncode == 1
    assert '"status": "invalid_request"' in completed.stdout
    assert _daily_row(db_path)["adjustment_factor"] is None


def test_cli_execute_updates_only_with_execute_flag(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    dry_run = _run_cli("--db-path", str(db_path), "--factors", str(factor_path), "--symbols", "FPT", "--dry-run")
    execute = _run_cli("--db-path", str(db_path), "--factors", str(factor_path), "--symbols", "FPT", "--execute")

    assert dry_run.returncode == 0
    assert '"db_mutation_made": false' in dry_run.stdout
    assert execute.returncode == 0
    assert '"db_mutation_made": true' in execute.stdout
    assert _daily_row(db_path)["adjustment_factor"] == 0.8


def test_duplicate_daily_price_rows_update_precise_row_identity(tmp_path: Path) -> None:
    db_path = _make_db(
        tmp_path,
        [
            {
                "security_id": "vietcap_iq:HOSE:FPT:A",
                "symbol": "FPT",
                "trade_date": "2026-01-02",
                "source_id": "fixture:daily_prices:a",
            },
            {
                "security_id": "vietcap_iq:HOSE:FPT:B",
                "symbol": "FPT",
                "trade_date": "2026-01-02",
                "source_id": "fixture:daily_prices:b",
            },
        ],
    )
    factor_path = _write_factors(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02", "factor": 0.8}])

    result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)

    assert result["rows_updated"] == 2
    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT source_id, adjustment_factor FROM daily_prices ORDER BY source_id"
        ).fetchall()
    assert rows == [("fixture:daily_prices:a", 0.8), ("fixture:daily_prices:b", 0.8)]


def test_apply_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/apply_adjustment_factors.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/apply_adjustment_factors.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _make_db(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        create_schema(con)
        for row in rows:
            symbol = str(row.get("symbol", "FPT"))
            trade_date = str(row.get("trade_date", "2026-01-02"))
            con.execute(
                """
                INSERT INTO daily_prices (
                    security_id, symbol, trade_date, open, high, low, close,
                    volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("security_id", symbol),
                    symbol,
                    trade_date,
                    float(row.get("open", 10.0)),
                    float(row.get("high", 11.0)),
                    float(row.get("low", 9.0)),
                    float(row.get("close", 10.5)),
                    1000.0,
                    10500.0,
                    "source_reported",
                    "unknown",
                    row.get("source_id", "fixture:daily_prices"),
                    row.get("raw_path", f"fixtures/{symbol.lower()}_{trade_date}.json"),
                    "ok",
                ),
            )
        con.commit()
    return db_path


def _write_factors(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    normalized = []
    for record in records:
        normalized.append(
            {
                "symbol": record["symbol"],
                "trade_date": record["trade_date"],
                "factor": record["factor"],
                "source_id": "fixture:adjusted_close",
                "method": "adjusted_close_ratio",
                "raw_path": f"fixtures/{str(record['symbol']).lower()}_adjusted.json",
                "status": "ok",
                "reasons": [],
            }
        )
    return _write_raw_factors(tmp_path, normalized)


def _write_raw_factors(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    factor_path = tmp_path / "factors.json"
    factor_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return factor_path


def _factor_record(symbol: str, trade_date: str, factor: float, *, raw_path: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "factor": factor,
        "source_id": "fixture:adjusted_close",
        "method": "adjusted_close_ratio",
        "raw_path": raw_path,
        "status": "ok",
        "reasons": [],
    }


def _daily_row(db_path: Path) -> sqlite3.Row:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        return con.execute("SELECT * FROM daily_prices ORDER BY trade_date LIMIT 1").fetchone()
