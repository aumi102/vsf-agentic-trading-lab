from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.db.build_mvp_store import build_mvp_store
from trading_agent.db.schema import create_schema
from trading_agent.ingestion.ohlcv_ingestion import run_ohlcv_ingestion
from trading_agent.ingestion.status import get_ingestion_status
from trading_agent.tools.ingestion_status_tool import inspect_ingestion_status


def test_missing_db_returns_missing_store(tmp_path: Path) -> None:
    result = get_ingestion_status(tmp_path / "missing.sqlite")

    assert result["status"] == "missing_store"
    assert result["tool_readiness"]["market_data"] == "missing_store"
    assert "MVP store not found" in result["caveats"][0]


def test_empty_db_returns_empty_store(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)

    result = get_ingestion_status(db_path)

    assert result["status"] == "empty_store"
    assert result["table_counts"]["daily_prices"] == 0
    assert result["tool_readiness"]["backtest"] == "empty_store"


def test_build_mvp_store_status_is_tool_ready_without_source_runs(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "builder.sqlite"
    build_mvp_store(symbols=["FPT"], raw_base_dir=raw_base, db_path=db_path)

    result = get_ingestion_status(db_path, symbols=["FPT"])

    assert result["status"] == "ok"
    assert result["table_counts"]["source_runs"] == 0
    assert result["table_counts"]["daily_prices"] == 60
    assert result["tool_readiness"] == {
        "market_data": "ok",
        "features": "ok",
        "signals": "ok",
        "backtest": "ok",
    }
    assert any("No source_runs rows found" in caveat for caveat in result["caveats"])


def test_cached_ingestion_status_has_audit_rows_and_watermarks(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    result = inspect_ingestion_status(["FPT"], db_path)

    assert result["status"] == "ok"
    assert result["latest_source_runs"][0]["run_id"] == run["run_id"]
    assert result["table_counts"]["source_runs"] == 1
    assert result["table_counts"]["raw_source_payloads"] == 1
    assert result["watermarks"][0]["last_run_id"] == run["run_id"]
    assert result["watermarks"][0]["last_trade_date"] == "2026-03-01"


def test_lineage_missing_count_zero_for_ingested_rows(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    result = get_ingestion_status(db_path, symbols=["FPT"])

    assert result["lineage"]["daily_prices_missing_source_id_raw_path"] == 0


def test_symbols_filter_limits_status_rows(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    _write_gap_chart_fixture(tmp_path, "VNM", closes=[float(20 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run_ohlcv_ingestion(["FPT", "VNM"], db_path=db_path, raw_base_dir=raw_base)

    result = get_ingestion_status(db_path, symbols=["VNM"])

    assert [item["symbol"] for item in result["symbols"]] == ["VNM"]
    assert [item["symbol"] for item in result["watermarks"]] == ["VNM"]


def test_latest_source_runs_sorted_newest_first(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    first = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)
    second = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    result = get_ingestion_status(db_path, symbols=["FPT"])

    assert [item["run_id"] for item in result["latest_source_runs"][:2]] == [second["run_id"], first["run_id"]]


def test_tool_readiness_ok_after_cached_ingestion(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    result = get_ingestion_status(db_path, symbols=["FPT"])

    assert result["tool_readiness"]["market_data"] == "ok"
    assert result["tool_readiness"]["features"] == "ok"
    assert result["tool_readiness"]["signals"] == "ok"
    assert result["tool_readiness"]["backtest"] == "ok"


def test_cli_missing_db_no_traceback(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_ingestion_status.py",
            "--db-path",
            str(tmp_path / "missing.sqlite"),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "missing_store"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_cached_ingested_db_prints_watermarks(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_ingestion_status.py",
            "--db-path",
            str(db_path),
            "--symbols",
            "FPT",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    assert '"status": "ok"' in completed.stdout
    assert "watermarks" in completed.stdout
    assert "FPT | vietcap_iq_gap_chart | 2026-03-01" in completed.stdout


def test_status_module_has_no_network_fetch_code() -> None:
    text = Path("src/trading_agent/ingestion/status.py").read_text(encoding="utf-8")

    assert "urlopen" not in text
    assert "requests" not in text
    assert "httpx" not in text


def test_generated_artifacts_not_required_outside_tmp_dirs(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    result = get_ingestion_status(db_path)

    assert result["status"] == "ok"
    assert str(db_path).startswith(str(tmp_path))
    assert str(raw_base).startswith(str(tmp_path))


def _write_gap_chart_fixture(
    tmp_path: Path,
    symbol: str,
    *,
    closes: list[float],
) -> Path:
    raw_base = tmp_path / "data" / "raw" / "controlled_fetch" / "source=vietcap_iq"
    dataset_dir = raw_base / "20260616T000000Z" / f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    payload = [
        {
            "symbol": symbol,
            "t": [int(date.timestamp()) for date in dates],
            "o": closes,
            "h": [value + 1 for value in closes],
            "l": [value - 1 for value in closes],
            "c": closes,
            "v": [1000 + i for i in range(len(closes))],
            "accumulatedVolume": [1000 + i for i in range(len(closes))],
            "accumulatedValue": [10000 + i for i in range(len(closes))],
        }
    ]
    raw_path = dataset_dir / "payload.json"
    raw_path.write_text(json.dumps(payload), encoding="utf-8")
    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "vietcap_iq",
                "dataset": f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000",
                "symbol": symbol,
                "run_id": "20260616T000000Z",
                "raw_path": str(raw_path),
                "access_status": "verified",
                "status": "success",
                "content_hash": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "crawled_at": "2026-06-16T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return raw_base
