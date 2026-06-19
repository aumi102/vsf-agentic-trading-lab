from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.adjusted_price_evidence_pipeline import (
    build_factor_records_from_adjusted_price_payload,
    run_adjusted_price_evidence_pipeline,
    write_factor_records,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path("tests/fixtures/adjustment_factors/adjusted_close_payload.json")


def test_dry_run_builds_factor_records_from_adjusted_close(tmp_path: Path) -> None:
    output_path = tmp_path / "factors.json"

    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=["FPT"],
        factor_output_path=output_path,
    )

    assert result["status"] == "ok"
    assert result["records_total"] == 1
    assert result["usable_records"] == 1
    assert result["invalid_records"] == 0
    assert result["db_mutation_made"] is False
    records = json.loads(output_path.read_text(encoding="utf-8"))
    assert records[0]["factor"] == 0.8
    assert records[0]["method"] == "adjusted_close_ratio"


def test_explicit_symbols_required() -> None:
    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=[],
    )

    assert result["status"] == "invalid_request"
    assert "explicit_symbols_required" in result["reasons"]


def test_max_symbol_guard_blocks_more_than_three() -> None:
    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=["FPT", "VNM", "VCB", "HPG"],
    )

    assert result["status"] == "invalid_request"
    assert "too_many_symbols:max=3" in result["reasons"]


def test_missing_payload_clean_error(tmp_path: Path) -> None:
    result = run_adjusted_price_evidence_pipeline(
        payload_path=tmp_path / "missing.json",
        source_id="fixture:adjusted_close",
        raw_path="fixtures/missing.json",
        symbols=["FPT"],
    )

    assert result["status"] == "missing_payload"
    assert result["db_mutation_made"] is False


def test_invalid_json_clean_error(tmp_path: Path) -> None:
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("{bad json", encoding="utf-8")

    result = run_adjusted_price_evidence_pipeline(
        payload_path=payload_path,
        source_id="fixture:adjusted_close",
        raw_path=str(payload_path),
        symbols=["FPT"],
    )

    assert result["status"] == "invalid_json"
    assert result["db_mutation_made"] is False


def test_close_less_than_or_equal_zero_rejected() -> None:
    records = build_factor_records_from_adjusted_price_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 0, "adjusted_close": 80}],
        source_id="fixture:adjusted_close",
        raw_path="fixtures/fpt.json",
        symbols=["FPT"],
    )

    assert records[0].status == "invalid"
    assert "raw_close_must_be_positive" in records[0].reasons


def test_adjusted_close_less_than_or_equal_zero_rejected() -> None:
    records = build_factor_records_from_adjusted_price_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 100, "adjusted_close": 0}],
        source_id="fixture:adjusted_close",
        raw_path="fixtures/fpt.json",
        symbols=["FPT"],
    )

    assert records[0].status == "invalid"
    assert "adjusted_close_must_be_positive" in records[0].reasons


def test_missing_source_id_or_raw_path_rejected() -> None:
    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="",
        raw_path="",
        symbols=["FPT"],
    )

    assert result["status"] == "invalid_request"
    assert "source_id_required" in result["reasons"]
    assert "raw_path_required" in result["reasons"]


def test_no_factor_one_fallback_for_missing_adjusted_close() -> None:
    records = build_factor_records_from_adjusted_price_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 100}],
        source_id="fixture:adjusted_close",
        raw_path="fixtures/fpt.json",
        symbols=["FPT"],
    )

    assert records[0].factor is None
    assert records[0].status == "missing"
    assert "adjusted_close_missing" in records[0].reasons


def test_output_factor_json_only_written_when_requested(tmp_path: Path) -> None:
    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=["FPT"],
    )

    assert result["status"] == "ok"
    assert result["factor_output_path"] is None
    assert list(tmp_path.iterdir()) == []


def test_execute_mode_applies_to_temp_db_and_readiness_passes(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    output_path = tmp_path / "factors.json"

    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=["FPT"],
        factor_output_path=output_path,
        db_path=db_path,
        execute=True,
        dry_run=False,
    )

    assert result["status"] == "ok"
    assert result["db_mutation_made"] is True
    assert result["readiness_status"] == "ok"
    assert result["backtest_gate"] == "pass"
    row = _daily_row(db_path)
    assert row["adjustment_factor"] == 0.8
    assert row["adjusted_close"] == 80.0


def test_missing_factors_keep_readiness_blocked(tmp_path: Path) -> None:
    db_path = _make_db(
        tmp_path,
        [
            {"symbol": "FPT", "trade_date": "2026-01-02"},
            {"symbol": "FPT", "trade_date": "2026-01-03"},
        ],
    )
    output_path = tmp_path / "factors.json"

    result = run_adjusted_price_evidence_pipeline(
        payload_path=FIXTURE,
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=["FPT"],
        factor_output_path=output_path,
        db_path=db_path,
        execute=True,
        dry_run=False,
    )

    assert result["status"] == "ok"
    assert result["readiness_status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"
    assert result["apply_result"]["rows_missing_factor"] == 1


def test_module_has_no_network_imports() -> None:
    text = Path("src/trading_agent/ingestion/adjusted_price_evidence_pipeline.py").read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])


def test_module_has_no_backtrader_docker_questdb_imports_or_behavior() -> None:
    text = Path("src/trading_agent/ingestion/adjusted_price_evidence_pipeline.py").read_text(encoding="utf-8")
    cli = Path("scripts/run_adjusted_price_evidence_pipeline.py").read_text(encoding="utf-8")

    blocked = ["backtrader", "docker", "questdb", "QuestDB"]
    assert all(name not in text for name in blocked)
    assert all(name not in cli for name in blocked)


def test_cli_success_dry_run_exits_zero(tmp_path: Path) -> None:
    output_path = tmp_path / "factors.json"

    completed = _run_cli(
        "--payload",
        str(FIXTURE),
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(FIXTURE),
        "--symbols",
        "FPT",
        "--factor-output",
        str(output_path),
        "--dry-run",
    )

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout
    assert output_path.exists()


def test_cli_expected_errors_exit_one_without_traceback(tmp_path: Path) -> None:
    output_path = tmp_path / "factors.json"
    completed = _run_cli(
        "--payload",
        str(tmp_path / "missing.json"),
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        "fixtures/missing.json",
        "--symbols",
        "FPT",
        "--factor-output",
        str(output_path),
    )

    assert completed.returncode == 1
    assert '"status": "missing_payload"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_allow_network_is_blocked(tmp_path: Path) -> None:
    output_path = tmp_path / "factors.json"
    completed = _run_cli(
        "--payload",
        str(FIXTURE),
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(FIXTURE),
        "--symbols",
        "FPT",
        "--factor-output",
        str(output_path),
        "--allow-network",
    )

    assert completed.returncode == 1
    assert '"network_not_implemented"' in completed.stdout
    assert not output_path.exists()


def test_write_factor_records_round_trips_payload(tmp_path: Path) -> None:
    records = build_factor_records_from_adjusted_price_payload(
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        source_id="fixture:adjusted_close",
        raw_path=str(FIXTURE),
        symbols=["FPT"],
    )
    path = write_factor_records(records, tmp_path / "factors.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[0]["symbol"] == "FPT"
    assert payload[0]["factor"] == 0.8


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_adjusted_price_evidence_pipeline.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _make_db(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as con:
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
                    f"vietcap_iq:HOSE:{symbol}:{trade_date}",
                    symbol,
                    trade_date,
                    90.0,
                    110.0,
                    80.0,
                    100.0,
                    1000.0,
                    100000.0,
                    "source_reported",
                    "unknown",
                    "fixture:daily_prices",
                    f"fixtures/{symbol.lower()}_{trade_date}.json",
                    "ok",
                ),
            )
        con.commit()
    return db_path


def _daily_row(db_path: Path) -> sqlite3.Row:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        return con.execute("SELECT * FROM daily_prices ORDER BY trade_date LIMIT 1").fetchone()
