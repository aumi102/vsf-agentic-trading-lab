from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.agent.orchestrator import BUILD_INSTRUCTION, TOOL_CALL_SEQUENCE, answer_market_query
from trading_agent.db.build_mvp_store import build_mvp_store


def test_direct_symbol_runs_expected_tool_sequence(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    result = answer_market_query(symbol="FPT", db_path=db_path)

    assert result["status"] == "ok"
    assert result["symbol"] == "FPT"
    assert result["tool_call_sequence"] == TOOL_CALL_SEQUENCE
    assert list(result["tool_outputs"]) == TOOL_CALL_SEQUENCE
    assert result["not_financial_advice"] is True


def test_extracts_symbol_from_vietnamese_query(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    result = answer_market_query(query="FPT hôm nay thế nào?", db_path=db_path)

    assert result["status"] == "ok"
    assert result["symbol"] == "FPT"
    assert "khuyến nghị đầu tư" in str(result["answer_markdown"])


def test_extracts_lowercase_and_phrase_query_symbols(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    lowercase = answer_market_query(query="fpt hôm nay thế nào?", db_path=db_path)
    phrase = answer_market_query(query="Cho tôi xem FPT", db_path=db_path)
    prefixed = answer_market_query(query="mã FPT hôm nay ra sao?", db_path=db_path)

    assert lowercase["status"] == "ok"
    assert lowercase["symbol"] == "FPT"
    assert phrase["status"] == "ok"
    assert phrase["symbol"] == "FPT"
    assert prefixed["status"] == "ok"
    assert prefixed["symbol"] == "FPT"


def test_unknown_query_without_symbol_returns_needs_symbol(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    result = answer_market_query(query="mã không tồn tại hôm nay thế nào?", db_path=db_path)

    assert result["status"] == "needs_symbol"
    assert result["symbol"] is None
    assert result["tool_call_sequence"] == []
    assert "chưa xác định được mã" in str(result["answer_markdown"]).lower()


def test_unknown_symbol_returns_not_found_without_traceback(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    result = answer_market_query(query="XYZ hôm nay thế nào?", db_path=db_path)

    assert result["status"] == "not_found"
    assert result["symbol"] == "XYZ"
    assert result["tool_outputs"]["market_data"]["status"] == "not_found"
    assert "traceback" not in str(result["answer_markdown"]).lower()


def test_unavailable_hpg_symbol_returns_not_found_without_traceback(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    result = answer_market_query(query="HPG hôm nay thế nào?", db_path=db_path)

    assert result["status"] == "not_found"
    assert result["symbol"] == "HPG"
    assert result["tool_outputs"]["market_data"]["status"] == "not_found"
    assert "traceback" not in str(result["answer_markdown"]).lower()


def test_missing_db_returns_build_instruction(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing.sqlite"

    result = answer_market_query(symbol="FPT", db_path=missing_db)

    assert result["status"] == "missing_store"
    assert BUILD_INSTRUCTION in str(result["answer_markdown"])
    assert result["tool_outputs"] == {}


def test_orchestrator_does_not_mutate_db(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    answer_market_query(symbol="FPT", db_path=db_path)

    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert after == before


def test_cli_symbol_and_query_smoke(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    by_symbol = _run_cli("--symbol", "FPT", "--db-path", str(db_path))
    by_query = _run_cli("--query", "FPT hôm nay thế nào?", "--db-path", str(db_path))

    assert by_symbol.returncode == 0
    assert '"status": "ok"' in by_symbol.stdout
    assert "## final_answer" in by_symbol.stdout
    assert by_query.returncode == 0
    assert '"symbol": "FPT"' in by_query.stdout


def test_cli_unknown_query_smoke(tmp_path: Path) -> None:
    db_path = _build_fixture_db(tmp_path)

    completed = _run_cli("--query", "mã không tồn tại hôm nay thế nào?", "--db-path", str(db_path))

    assert completed.returncode == 1
    assert '"status": "needs_symbol"' in completed.stdout
    assert "Traceback" not in completed.stderr


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/agent_answer_demo.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _build_fixture_db(tmp_path: Path) -> Path:
    raw_base = _write_gap_chart_fixture(tmp_path, "FPT", closes=[float(10 + i) for i in range(60)])
    db_path = tmp_path / "agent.sqlite"
    build_mvp_store(symbols=["FPT"], raw_base_dir=raw_base, db_path=db_path)
    return db_path


def _write_gap_chart_fixture(tmp_path: Path, symbol: str, *, closes: list[float]) -> Path:
    raw_base = tmp_path / "data" / "raw" / "controlled_fetch" / "source=vietcap_iq"
    dataset_dir = raw_base / "20260616T000000Z" / f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000"
    dataset_dir.mkdir(parents=True)
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
