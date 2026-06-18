from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness


def test_missing_db_returns_missing_store_and_cli_exit_1(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.sqlite"

    result = get_adjusted_ohlc_readiness(db_path)
    completed = _run_cli(db_path)

    assert result["status"] == "missing_store"
    assert result["backtest_gate"] == "blocked"
    assert completed.returncode == 1
    assert '"status": "missing_store"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_empty_db_returns_empty_store(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)

    result = get_adjusted_ohlc_readiness(db_path)

    assert result["status"] == "empty_store"
    assert result["backtest_gate"] == "blocked"


def test_current_cached_ingestion_shape_is_not_ready_when_adjusted_columns_null(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT")

    result = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"
    assert result["coverage"]["missing_adjusted_rows"] == 1


def test_legacy_daily_prices_without_adjusted_columns_is_not_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE daily_prices (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                quality_status TEXT
            )
            """
        )
        con.execute(
            """
            INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, quality_status)
            VALUES ('FPT', '2026-01-01', 100.0, 110.0, 90.0, 105.0, 'pass')
            """
        )
        con.commit()

    result = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"
    assert result["coverage"]["total_rows"] == 1
    assert result["coverage"]["missing_adjusted_rows"] == 1
    assert "Missing adjusted OHLC/provenance columns" in result["caveats"][0]


def test_populated_adjusted_rows_are_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "ready.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True)

    result = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert result["status"] == "ok"
    assert result["backtest_gate"] == "pass"
    assert result["coverage"]["adjusted_rows"] == 1
    assert result["coverage"]["missing_adjusted_rows"] == 0


def test_invalid_factor_blocks_readiness(tmp_path: Path) -> None:
    db_path = tmp_path / "bad_factor.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True, factor=0.0)

    result = get_adjusted_ohlc_readiness(db_path)

    assert result["status"] == "not_ready"
    assert result["coverage"]["invalid_factor_rows"] == 1
    assert result["backtest_gate"] == "blocked"


def test_adjusted_rows_without_factor_provenance_block_readiness(tmp_path: Path) -> None:
    db_path = tmp_path / "missing_provenance.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True, with_provenance=False)

    result = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"
    assert result["coverage"]["missing_provenance_rows"] == 1
    assert "missing adjustment-factor provenance" in result["caveats"][0]


def test_inconsistent_adjusted_ohlc_blocks_readiness(tmp_path: Path) -> None:
    db_path = tmp_path / "bad_ohlc.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True, adjusted_high=70.0, adjusted_low=90.0)

    result = get_adjusted_ohlc_readiness(db_path)

    assert result["status"] == "not_ready"
    assert result["coverage"]["invalid_ohlc_rows"] == 1


def test_symbols_filter_works(tmp_path: Path) -> None:
    db_path = tmp_path / "symbols.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True)
        _insert_price(con, "VNM", adjusted=False)

    result = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert result["status"] == "ok"
    assert result["symbols"] == ["FPT"]
    assert result["coverage"]["total_rows"] == 1


def test_missing_requested_symbol_blocks_readiness(tmp_path: Path) -> None:
    db_path = tmp_path / "missing_symbol.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True)

    result = get_adjusted_ohlc_readiness(db_path, symbols=["msn"])

    assert result["status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"
    assert result["symbols"] == []
    assert "MSN" in result["caveats"][0]


def test_failed_quality_rows_block_with_quality_warn(tmp_path: Path) -> None:
    db_path = tmp_path / "quality.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True, quality_status="fail")

    result = get_adjusted_ohlc_readiness(db_path, symbols=["FPT"])

    assert result["status"] == "quality_warn"
    assert result["backtest_gate"] == "blocked"
    assert result["coverage"]["fail_quality_rows"] == 1


def test_date_range_filter_works(tmp_path: Path) -> None:
    db_path = tmp_path / "dates.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", trade_date="2026-01-01", adjusted=False)
        _insert_price(con, "FPT", trade_date="2026-01-02", adjusted=True)

    result = get_adjusted_ohlc_readiness(
        db_path,
        symbols=["FPT"],
        start_date="2026-01-02",
        end_date="2026-01-02",
    )

    assert result["status"] == "ok"
    assert result["coverage"]["total_rows"] == 1
    assert result["by_symbol"][0]["start_date"] == "2026-01-02"


def test_cli_not_ready_exits_1_without_traceback(tmp_path: Path) -> None:
    db_path = tmp_path / "not_ready.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT")

    completed = _run_cli(db_path, "--symbols", "FPT")

    assert completed.returncode == 1
    assert '"status": "not_ready"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_ready_exits_0(tmp_path: Path) -> None:
    db_path = tmp_path / "ready.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True)

    completed = _run_cli(db_path, "--symbols", "FPT")

    assert completed.returncode == 0
    assert '"backtest_gate": "pass"' in completed.stdout
    assert "coverage" in completed.stdout


def test_cli_date_filters_and_lowercase_symbols_work(tmp_path: Path) -> None:
    db_path = tmp_path / "cli_filters.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", trade_date="2026-01-01", adjusted=False)
        _insert_price(con, "FPT", trade_date="2026-01-02", adjusted=True)

    completed = _run_cli(
        db_path,
        "--symbols",
        "fpt",
        "--start-date",
        "2026-01-02",
        "--end-date",
        "2026-01-02",
    )

    assert completed.returncode == 0
    assert '"symbols": [' in completed.stdout
    assert '"FPT"' in completed.stdout
    assert "2026-01-02" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_readiness_module_has_no_network_imports() -> None:
    text = Path("src/trading_agent/ingestion/adjusted_readiness.py").read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])
    assert "trading_agent.tools" not in text


def test_readiness_check_does_not_mutate_db(tmp_path: Path) -> None:
    db_path = tmp_path / "readonly.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        _insert_price(con, "FPT", adjusted=True)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    result = get_adjusted_ohlc_readiness(db_path)
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()

    assert result["status"] == "ok"
    assert after == before


def _insert_price(
    con: sqlite3.Connection,
    symbol: str,
    *,
    trade_date: str = "2026-01-01",
    adjusted: bool = False,
    factor: float = 0.8,
    adjusted_high: float = 88.0,
    adjusted_low: float = 72.0,
    quality_status: str = "pass",
    with_provenance: bool = True,
) -> None:
    adjusted_values = {
        "adjustment_factor": factor,
        "adjusted_open": 80.0,
        "adjusted_high": adjusted_high,
        "adjusted_low": adjusted_low,
        "adjusted_close": 84.0,
        "adjustment_source_id": "fixture:adjusted_close" if with_provenance else None,
        "adjustment_raw_path": "fixtures/fpt_adjusted.json" if with_provenance else None,
        "adjustment_method": "adjusted_close_ratio" if with_provenance else None,
    } if adjusted else {
        "adjustment_factor": None,
        "adjusted_open": None,
        "adjusted_high": None,
        "adjusted_low": None,
        "adjusted_close": None,
        "adjustment_source_id": None,
        "adjustment_raw_path": None,
        "adjustment_method": None,
    }
    con.execute(
        """
        INSERT INTO daily_prices (
            security_id, symbol, trade_date, open, high, low, close,
            adjustment_factor, adjusted_open, adjusted_high, adjusted_low, adjusted_close,
            adjustment_source_id, adjustment_raw_path, adjustment_method,
            volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"vietcap_iq:HOSE:{symbol}",
            symbol,
            trade_date,
            100.0,
            110.0,
            90.0,
            105.0,
            adjusted_values["adjustment_factor"],
            adjusted_values["adjusted_open"],
            adjusted_values["adjusted_high"],
            adjusted_values["adjusted_low"],
            adjusted_values["adjusted_close"],
            adjusted_values["adjustment_source_id"],
            adjusted_values["adjustment_raw_path"],
            adjusted_values["adjustment_method"],
            1000.0,
            100000.0,
            "source_reported",
            "unknown",
            f"test:{symbol}",
            "raw.json",
            quality_status,
        ),
    )
    con.commit()


def _run_cli(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/check_adjusted_ohlc_readiness.py",
            "--db-path",
            str(db_path),
            *args,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
