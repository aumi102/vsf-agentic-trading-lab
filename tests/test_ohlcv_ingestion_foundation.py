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

from trading_agent.ingestion.ohlcv_ingestion import run_ohlcv_ingestion


def test_cached_ingestion_returns_ok(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    result = run_ohlcv_ingestion(["FPT"], db_path=tmp_path / "demo.sqlite", raw_base_dir=raw_base)

    assert result["status"] == "ok"
    assert result["symbols_loaded"] == ["FPT"]
    assert result["canonical_rows"]["daily_prices_upserted"] == 60
    assert result["feature_rows"] == 60
    assert result["signal_rows"] == 60


def test_source_run_row_is_recorded(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    result = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    with sqlite3.connect(db_path) as con:
        row = con.execute("SELECT source, mode, status FROM source_runs WHERE run_id = ?", (result["run_id"],)).fetchone()

    assert row == ("vietcap_iq_gap_chart", "cached", "ok")


def test_raw_payload_metadata_is_recorded(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    result = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    with sqlite3.connect(db_path) as con:
        row = con.execute(
            """
            SELECT symbol, content_hash, raw_path, metadata_path, row_count, status
            FROM raw_source_payloads
            WHERE run_id = ?
            """,
            (result["run_id"],),
        ).fetchone()

    assert row[0] == "FPT"
    assert len(row[1]) == 64
    assert row[2].endswith("payload.json")
    assert row[3].endswith("metadata.json")
    assert row[4] == 60
    assert row[5] == "success"


def test_daily_prices_retain_source_lineage(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"
    run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    with sqlite3.connect(db_path) as con:
        row = con.execute(
            """
            SELECT COUNT(*) AS rows,
                   SUM(CASE WHEN source_id = '' OR raw_path = '' THEN 1 ELSE 0 END) AS missing
            FROM daily_prices
            WHERE symbol = 'FPT'
            """
        ).fetchone()

    assert row[0] == 60
    assert row[1] == 0


def test_feature_refresh_excludes_failed_ohlc_rows(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(
        tmp_path,
        "FPT",
        closes=[float(10 + i) for i in range(60)],
        fail_indexes={10},
    )
    db_path = tmp_path / "demo.sqlite"
    result = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    assert result["quality"]["daily_prices"]["fail_count"] == 1
    assert result["feature_rows"] == 59


def test_signal_refresh_excludes_failed_ohlc_rows(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(
        tmp_path,
        "FPT",
        closes=[float(10 + i) for i in range(60)],
        fail_indexes={10},
    )
    db_path = tmp_path / "demo.sqlite"
    result = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    assert result["signal_rows"] == 59
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM signals WHERE symbol = 'FPT'").fetchone()[0] == 59


def test_repeated_cached_ingestion_is_canonical_deterministic(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "demo.sqlite"

    first = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)
    second = run_ohlcv_ingestion(["FPT"], db_path=db_path, raw_base_dir=raw_base)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM daily_prices WHERE symbol = 'FPT'").fetchone()[0] == 60
        assert con.execute("SELECT COUNT(*) FROM feature_snapshots WHERE symbol = 'FPT'").fetchone()[0] == 60
        assert con.execute("SELECT COUNT(*) FROM signals WHERE symbol = 'FPT'").fetchone()[0] == 60


def test_unknown_symbol_returns_clean_error(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    result = run_ohlcv_ingestion(["HPG"], db_path=tmp_path / "demo.sqlite", raw_base_dir=raw_base)

    assert result["status"] == "error"
    assert result["symbols_loaded"] == []
    assert result["symbols_failed"] == ["HPG"]
    assert "No cached gap-chart payload found for: HPG." in result["caveats"]


def test_partial_unknown_symbol_returns_partial_ok(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    result = run_ohlcv_ingestion(["FPT", "HPG"], db_path=tmp_path / "demo.sqlite", raw_base_dir=raw_base)

    assert result["status"] == "partial_ok"
    assert result["symbols_loaded"] == ["FPT"]
    assert result["symbols_failed"] == ["HPG"]


def test_live_mode_without_allow_network_returns_clear_error(tmp_path: Path) -> None:
    result = run_ohlcv_ingestion(["FPT"], db_path=tmp_path / "demo.sqlite", mode="live", allow_network=False)

    assert result["status"] == "error"
    assert "No network request was made." in result["caveats"][0]


def test_live_mode_with_allow_network_is_not_implemented_without_traceback(tmp_path: Path) -> None:
    result = run_ohlcv_ingestion(["FPT"], db_path=tmp_path / "demo.sqlite", mode="live", allow_network=True)

    assert result["status"] == "error"
    assert any("not implemented" in caveat for caveat in result["caveats"])


def test_cli_cached_mode_smoke(tmp_path: Path) -> None:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "cli.sqlite"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_ohlcv_ingestion.py",
            "--symbols",
            "FPT",
            "--mode",
            "cached",
            "--db-path",
            str(db_path),
            "--raw-base-dir",
            str(raw_base),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    assert '"status": "ok"' in completed.stdout
    assert "quality_table" in completed.stdout


def test_cli_live_mode_without_allow_network_has_no_traceback(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_ohlcv_ingestion.py",
            "--symbols",
            "FPT",
            "--mode",
            "live",
            "--db-path",
            str(tmp_path / "cli.sqlite"),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "error"' in completed.stdout
    assert "Traceback" not in completed.stderr


def _write_gap_chart_fixture(
    tmp_path: Path,
    symbol: str,
    *,
    closes: list[float],
    fail_indexes: set[int] | None = None,
) -> Path:
    raw_base = tmp_path / "data" / "raw" / "controlled_fetch" / "source=vietcap_iq"
    dataset_dir = raw_base / "20260616T000000Z" / f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000"
    dataset_dir.mkdir(parents=True)
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    fail_indexes = fail_indexes or set()
    highs = [value + 1 for value in closes]
    for index in fail_indexes:
        highs[index] = closes[index] - 1
    payload = [
        {
            "symbol": symbol,
            "t": [int(date.timestamp()) for date in dates],
            "o": closes,
            "h": highs,
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
