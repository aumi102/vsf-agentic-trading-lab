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

from trading_agent.db.build_mvp_store import build_mvp_store
from scripts.run_mentor_demo_suite import BACKTEST_SCRIPT, DEMO_SCENARIOS, BUILD_ARGS, BUILD_SCRIPT


# ---------------------------------------------------------------------------
# Fixtures
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
    db_path = tmp_path / "suite.sqlite"
    build_mvp_store(symbols=symbols, raw_base_dir=raw_base, db_path=db_path)
    return db_path


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_demo_scenarios_list_has_expected_scenarios() -> None:
    labels = [s["label"] for s in DEMO_SCENARIOS]
    assert any("market_brief" in lbl for lbl in labels)
    assert any("risk_check" in lbl for lbl in labels)
    assert any("compare" in lbl for lbl in labels)
    assert any("backtest" in lbl for lbl in labels)
    assert any("ASCII fallback" in lbl for lbl in labels)


def test_backtest_commands_are_included_in_suite_scenarios() -> None:
    backtests = [s for s in DEMO_SCENARIOS if s["script"] == BACKTEST_SCRIPT]
    labels = [s["label"] for s in backtests]
    assert "backtest --symbols FPT,VNM,VCB" in labels
    assert "backtest --symbols FPT,HPG" in labels
    assert any("2030-01-01" in label for label in labels)


def test_demo_scenarios_specify_exit_codes() -> None:
    for scenario in DEMO_SCENARIOS:
        assert "expect_exit" in scenario
        assert scenario["expect_exit"] in (0, 1)
        assert scenario["expect_status"] in ("ok", "not_found")


def test_backtest_expected_success_and_edge_case_statuses() -> None:
    by_label = {scenario["label"]: scenario for scenario in DEMO_SCENARIOS}
    assert by_label["backtest --symbols FPT,VNM,VCB"]["expect_exit"] == 0
    assert by_label["backtest --symbols FPT,VNM,VCB"]["expect_status"] == "ok"
    assert by_label["backtest --symbols FPT,HPG"]["expect_exit"] == 0
    assert by_label["backtest --symbols FPT,HPG"]["expect_status"] == "ok"
    no_data = by_label["backtest --symbols FPT --start-date 2030-01-01 --end-date 2030-12-31"]
    assert no_data["expect_exit"] == 1
    assert no_data["expect_status"] == "not_found"


def test_demo_scenarios_contain_no_network_args() -> None:
    for scenario in DEMO_SCENARIOS:
        for arg in scenario["args"]:
            assert "http" not in arg.lower()
            assert "curl" not in arg.lower()
            assert "fetch" not in arg.lower()
            assert "crawl" not in arg.lower()
            assert "network" not in arg.lower()


def test_build_cmd_does_not_contain_network_flags() -> None:
    build_str = " ".join([BUILD_SCRIPT] + list(BUILD_ARGS))
    assert "http" not in build_str.lower()
    assert "--fetch" not in build_str
    assert "--crawl" not in build_str


# ---------------------------------------------------------------------------
# CLI smoke test on fixture DB
# ---------------------------------------------------------------------------

def _run_suite_cli(*extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_mentor_demo_suite.py", *extra_args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_suite_cli_passes_on_fixture_db(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = _run_suite_cli("--db-path", str(db_path), "--skip-build")
    assert result.returncode == 0
    assert "[OK]" in result.stdout
    assert "FAIL" not in result.stdout


def test_suite_cli_shows_status_for_each_scenario(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = _run_suite_cli("--db-path", str(db_path), "--skip-build")
    assert "market_brief" in result.stdout
    assert "risk_check" in result.stdout
    assert "compare" in result.stdout
    assert "backtest" in result.stdout
    assert "Key result" in result.stdout


def test_suite_cli_includes_backtest_status_rows(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = _run_suite_cli("--db-path", str(db_path), "--skip-build")
    assert "backtest --symbols FPT,VNM,VCB" in result.stdout
    assert "backtest --symbols FPT,HPG" in result.stdout
    assert "no usable rows" in result.stdout
    assert "missing=HPG" in result.stdout


def test_suite_cli_expected_nonzero_backtest_edge_case_keeps_suite_green(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = _run_suite_cli("--db-path", str(db_path), "--skip-build")
    assert result.returncode == 0
    assert "backtest --symbols FPT --start-date 2030-01-01 --end-da" in result.stdout
    assert "not_found" in result.stdout
    assert "[OK] all scenarios exited/statused as expected" in result.stdout


def test_suite_cli_no_traceback_on_missing_symbols(tmp_path: Path) -> None:
    db_path = _build_multi_fixture_db(tmp_path, ["FPT", "VNM", "VCB"])
    result = _run_suite_cli("--db-path", str(db_path), "--skip-build")
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout
