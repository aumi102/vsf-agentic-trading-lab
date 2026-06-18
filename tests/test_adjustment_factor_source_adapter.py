from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness
from trading_agent.ingestion.apply_adjustment_factors import apply_adjustment_factors_to_db
from trading_agent.ingestion.sources.adjustment_factor_source import (
    build_factor_records_from_adjusted_close_payload,
    build_factor_records_from_corporate_action_payload,
    parse_adjustment_factor_payload,
)


FIXTURE_DIR = Path("tests/fixtures/adjustment_factors")


def test_adjusted_close_payload_produces_ok_factor_record() -> None:
    payload_path = FIXTURE_DIR / "adjusted_close_payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    result = build_factor_records_from_adjusted_close_payload(
        payload,
        source_id="fixture:adjusted_close",
        raw_path=str(payload_path),
    )

    assert result.status == "ok"
    record = result.records[0]
    assert record.status == "ok"
    assert record.symbol == "FPT"
    assert record.trade_date == "2026-01-02"
    assert record.factor == 0.8
    assert record.source_id == "fixture:adjusted_close"
    assert record.raw_path == str(payload_path)
    assert record.method == "adjusted_close_ratio"
    assert record.reasons == ()


def test_corporate_action_payload_produces_ok_factor_record() -> None:
    payload_path = FIXTURE_DIR / "corporate_action_factor_payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    result = build_factor_records_from_corporate_action_payload(
        payload,
        source_id="fixture:corporate_action",
        raw_path=str(payload_path),
    )

    assert result.status == "ok"
    record = result.records[0]
    assert record.status == "ok"
    assert record.factor == 0.8
    assert record.method == "corporate_action_derived"


def test_missing_adjusted_close_returns_not_ready_record() -> None:
    result = build_factor_records_from_adjusted_close_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 100.0}],
        source_id="fixture:adjusted_close",
        raw_path="fixtures/missing_adjusted_close.json",
    )

    assert result.status == "not_ready"
    assert result.records[0].status == "missing"
    assert "adjusted_close_missing" in result.records[0].reasons


def test_missing_source_id_or_raw_path_blocks_usable_status() -> None:
    result = build_factor_records_from_adjusted_close_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 100.0, "adjusted_close": 80.0}],
        source_id="",
        raw_path="",
    )

    assert result.status == "not_ready"
    assert result.records[0].status == "invalid"
    assert "source_id_required" in result.records[0].reasons
    assert "raw_path_required" in result.records[0].reasons


def test_parse_dispatches_by_method() -> None:
    result = parse_adjustment_factor_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 100.0, "adjusted_close": 80.0}],
        source_id="fixture:adjusted_close",
        raw_path="fixtures/fpt_adjusted.json",
        method="adjusted_close_ratio",
    )

    assert result.status == "ok"
    assert result.records[0].factor == 0.8


def test_adapter_records_can_feed_local_factor_application_and_readiness(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    payload_path = FIXTURE_DIR / "adjusted_close_payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    result = build_factor_records_from_adjusted_close_payload(
        payload,
        source_id="fixture:adjusted_close",
        raw_path=str(payload_path),
    )
    factor_path = tmp_path / "factors.json"
    factor_path.write_text(json.dumps([asdict(record) for record in result.records]), encoding="utf-8")

    apply_result = apply_adjustment_factors_to_db(db_path, factor_path, symbols=["FPT"], dry_run=False)
    readiness = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert apply_result["rows_updated"] == 1
    assert readiness["status"] == "ok"
    assert readiness["backtest_gate"] == "pass"


def test_adapter_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/sources/adjustment_factor_source.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_adapter_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/sources/adjustment_factor_source.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        con.execute(
            """
            INSERT INTO daily_prices (
                security_id, symbol, trade_date, open, high, low, close,
                volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "vietcap_iq:HOSE:FPT",
                "FPT",
                "2026-01-02",
                100.0,
                110.0,
                90.0,
                100.0,
                1000.0,
                100000.0,
                "source_reported",
                "unknown",
                "fixture:daily_prices",
                "fixtures/fpt_raw_ohlc.json",
                "ok",
            ),
        )
        con.commit()
    return db_path
