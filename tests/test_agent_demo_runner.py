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

from trading_agent.agent.demo_runner import run_demo
from trading_agent.db.build_mvp_store import build_mvp_store


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_gap_chart_fixture(tmp_path: Path, symbol: str, *, closes: list[float]) -> Path:
    raw_base = tmp_path / "data" / "raw" / "controlled_fetch" / "source=vietcap_iq"
    dataset_dir = (
        raw_base / "20260616T000000Z" / f"vietcap_iq_gap_chart_{symbol.lower()}_countback_5000"
    )
    dataset_dir.mkdir(parents=True)
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    payload = [
        {
            "symbol": symbol,
            "t": [int(date.timestamp()) for date in dates],
            "o": closes,
            "h": [v + 1 for v in closes],
            "l": [v - 1 for v in closes],
            "c": closes,
            "v": [1000 + i for i in range(len(closes))],
            "accumulatedVolume": [1000 + i for i in range(len(closes))],
            "accumulatedValue": [10000 + i for i in range(len(closes))],
        }
    ]
    raw_path = dataset_dir / "payload.json"
    raw_path.write_text(json.dumps(payload), encoding="utf-8")
    (dataset_dir / "metadata.json").write_text(
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


def _build_multi_fixture_db(tmp_path: Path, symbols: list[str]) -> Path:
    raw_base = None
    for i, sym in enumerate(symbols):
        closes = [float(10 + i * 5 + j) for j in range(60)]
        raw_base = _write_gap_chart_fixture(tmp_path, sym, closes=closes)
    db_path = tmp_path / "demo.sqlite"
    build_mvp_store(symbols=symbols, raw_base_dir=raw_base, db_path=db_path)
    return db_path


def _build_single_fixture_db(tmp_path: Path, symbol: str = "FPT") -> Path:
    return _build_multi_fixture_db(tmp_path, [symbol])


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_market_brief_fpt_returns_ok(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = run_demo("market_brief", symbol="FPT", db_path=db_path)
    assert result["status"] == "ok"
    assert result["scenario"] == "market_brief"
    assert result["not_financial_advice"] is True


def test_market_brief_lowercase_query_returns_ok(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = run_demo("market_brief", query="fpt hôm nay thế nào?", db_path=db_path)
    assert result["status"] == "ok"
    assert result["scenario"] == "market_brief"


def test_risk_check_fpt_includes_risk_flags(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = run_demo("risk_check", symbol="FPT", db_path=db_path)
    assert result["status"] == "ok"
    risk_out = result["outputs"]["risk"]
    assert isinstance(risk_out["risk_flags"], list)
    assert len(risk_out["risk_flags"]) > 0
    assert any(flag in result["answer_markdown"] for flag in risk_out["risk_flags"])


def test_compare_three_symbols_returns_rows_in_input_order(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = run_demo("compare", symbols=["FPT", "VNM", "VCB"], db_path=db_path)
    assert result["status"] == "ok"
    rows = result["outputs"]["rows"]
    assert len(rows) == 3
    assert [r["symbol"] for r in rows] == ["FPT", "VNM", "VCB"]


def test_compare_fpt_hpg_includes_ok_and_not_found(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path, "FPT")
    result = run_demo("compare", symbols=["FPT", "HPG"], db_path=db_path)
    assert result["status"] == "ok"
    rows = result["outputs"]["rows"]
    assert len(rows) == 2
    fpt_row = next(r for r in rows if r["symbol"] == "FPT")
    hpg_row = next(r for r in rows if r["symbol"] == "HPG")
    assert fpt_row["status"] == "ok"
    assert hpg_row["status"] == "not_found"


def test_missing_db_returns_build_instruction_no_traceback(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.sqlite"
    result = run_demo("market_brief", symbol="FPT", db_path=missing)
    assert result["status"] == "missing_store"
    assert "build_mvp_db.py" in result["answer_markdown"]
    assert "Traceback" not in result["answer_markdown"]


def test_demo_runner_does_not_mutate_db(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    run_demo("market_brief", symbol="FPT", db_path=db_path)
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert after == before


def test_tool_call_trace_contains_expected_tools(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = run_demo("market_brief", symbol="FPT", db_path=db_path)
    tool_names = [entry["tool_name"] for entry in result["tool_call_trace"]]
    for expected in ("market_data", "features", "signal", "risk", "report"):
        assert expected in tool_names


def test_final_answer_includes_not_financial_advice_wording(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = run_demo("market_brief", symbol="FPT", db_path=db_path)
    assert "khuyến nghị đầu tư" in result["answer_markdown"]


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------

def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_agent_demo.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_cli_market_brief_symbol(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = _run_cli("--scenario", "market_brief", "--symbol", "FPT", "--db-path", str(db_path))
    assert result.returncode == 0
    assert '"status": "ok"' in result.stdout
    assert "## final_answer" in result.stdout


def test_cli_market_brief_query(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = _run_cli(
        "--scenario", "market_brief",
        "--query", "FPT hôm nay thế nào?",
        "--db-path", str(db_path),
    )
    assert result.returncode == 0
    assert '"symbol": "FPT"' in result.stdout


def test_cli_risk_check_symbol(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path)
    result = _run_cli("--scenario", "risk_check", "--symbol", "FPT", "--db-path", str(db_path))
    assert result.returncode == 0
    assert '"status": "ok"' in result.stdout


def test_cli_compare_three_symbols(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = _run_cli(
        "--scenario", "compare",
        "--symbols", "FPT,VNM,VCB",
        "--db-path", str(db_path),
    )
    assert result.returncode == 0
    assert "FPT" in result.stdout
    assert "VNM" in result.stdout
    assert "VCB" in result.stdout


def test_cli_compare_fpt_hpg(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path, "FPT")
    result = _run_cli(
        "--scenario", "compare",
        "--symbols", "FPT,HPG",
        "--db-path", str(db_path),
    )
    assert result.returncode == 0
    assert "HPG" in result.stdout
    assert "not_found" in result.stdout


def test_cli_missing_db(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    result = _run_cli(
        "--scenario", "market_brief",
        "--symbol", "FPT",
        "--db-path", str(missing),
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "build_mvp_db.py" in result.stdout


def test_compare_all_symbols_missing_returns_not_found_no_traceback(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path, "FPT")
    result = run_demo("compare", symbols=["HPG", "XYZ"], db_path=db_path)
    assert result["status"] == "not_found"
    assert result["not_financial_advice"] is True
    rows = result["outputs"]["rows"]
    assert all(r["status"] == "not_found" for r in rows)
    assert "Traceback" not in result["answer_markdown"]


def test_cli_compare_all_missing_exits_nonzero_no_traceback(tmp_path: Path) -> None:
    db_path = _build_single_fixture_db(tmp_path, "FPT")
    result = _run_cli(
        "--scenario", "compare",
        "--symbols", "HPG,XYZ",
        "--db-path", str(db_path),
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "not_found" in result.stdout
