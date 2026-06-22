from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from trading_agent.backtest.adjusted_ohlc_fixture_cost_diagnostics import (
    compute_fixture_cost_diagnostics,
    render_fixture_cost_diagnostics_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/trading_agent/backtest/adjusted_ohlc_fixture_cost_diagnostics.py")
SCRIPT = Path("scripts/report_adjusted_ohlc_fixture_cost_diagnostics.py")
SYMBOLS = ["FPT", "VNM", "VCB"]


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _preparation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ok",
        "backtest_input_status": "ready_for_research_dry_run",
        "price_basis": "adjusted_ohlc",
        "represented_symbols": SYMBOLS,
        "assumptions": {
            "transaction_cost_bps": 15,
            "slippage_bps": 10,
            "exchange": "HOSE",
            "slippage_band_bps": 700,
        },
        "not_financial_advice": True,
    }
    payload.update(overrides)
    return payload


def _roundtrip(enter: int = 0, exit_: int = 0, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ok",
        "engine_stage": "fixture_roundtrip_engine",
        "price_basis": "adjusted_ohlc",
        "symbols": SYMBOLS,
        "roundtrip_diagnostics": {
            "state_transition_counts": {
                "fixture_enter_count": enter,
                "fixture_exit_count": exit_,
                "duplicate_enter_count": 0,
                "unmatched_exit_count": 0,
                "open_fixture_state_count": 0,
            }
        },
        "forbidden_performance_metrics_present": False,
        "not_financial_advice": True,
    }
    payload.update(overrides)
    return payload


def _build(
    tmp_path: Path,
    *,
    preparation: dict[str, object] | None = None,
    roundtrip: dict[str, object] | None = None,
    preparation_path: Path | None = None,
    roundtrip_path: Path | None = None,
    symbols: list[str] | None = None,
    max_rows: int = 20,
) -> dict[str, object]:
    prep_path = preparation_path or _write(tmp_path / "preparation.json", preparation or _preparation())
    rt_path = roundtrip_path or _write(tmp_path / "roundtrip.json", roundtrip or _roundtrip())
    return compute_fixture_cost_diagnostics(
        preparation_path=prep_path,
        roundtrip_path=rt_path,
        symbols=symbols or SYMBOLS,
        max_rows=max_rows,
    )


def test_missing_preparation_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, preparation_path=tmp_path / "missing.json")
    assert "preparation_missing" in result["reasons"]


def test_missing_roundtrip_file_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, roundtrip_path=tmp_path / "missing.json")
    assert "roundtrip_missing" in result["reasons"]


def test_invalid_json_blocks(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    assert "json_invalid:preparation" in _build(tmp_path, preparation_path=bad)["reasons"]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"status": "blocked"}, "preparation_status_not_ok:blocked"),
        ({"price_basis": "raw_ohlc"}, "preparation_price_basis_not_adjusted_ohlc:raw_ohlc"),
    ],
)
def test_preparation_contract_blocks(tmp_path: Path, overrides: dict[str, object], reason: str) -> None:
    assert reason in _build(tmp_path, preparation=_preparation(**overrides))["reasons"]


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("transaction_cost_bps", None, "transaction_cost_bps_missing"),
        ("transaction_cost_bps", -1, "transaction_cost_bps_must_be_nonnegative"),
        ("slippage_bps", None, "slippage_bps_missing"),
        ("slippage_bps", -1, "slippage_bps_must_be_nonnegative"),
        ("exchange", None, "exchange_missing"),
        ("slippage_band_bps", None, "slippage_band_bps_missing"),
    ],
)
def test_assumption_contract_blocks(tmp_path: Path, key: str, value: object, reason: str) -> None:
    prep = _preparation()
    assumptions = dict(prep["assumptions"])  # type: ignore[arg-type]
    if value is None:
        assumptions.pop(key)
    else:
        assumptions[key] = value
    prep["assumptions"] = assumptions
    assert reason in _build(tmp_path, preparation=prep)["reasons"]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"status": "blocked"}, "roundtrip_status_not_ok:blocked"),
        ({"engine_stage": "wrong"}, "roundtrip_engine_stage_invalid:wrong"),
        ({"price_basis": "raw_ohlc"}, "roundtrip_price_basis_not_adjusted_ohlc:raw_ohlc"),
        (
            {"forbidden_performance_metrics_present": True},
            "roundtrip_forbidden_performance_metrics_present",
        ),
    ],
)
def test_roundtrip_contract_blocks(tmp_path: Path, overrides: dict[str, object], reason: str) -> None:
    assert reason in _build(tmp_path, roundtrip=_roundtrip(**overrides))["reasons"]


def test_requested_symbol_missing_blocks(tmp_path: Path) -> None:
    result = _build(tmp_path, roundtrip=_roundtrip(symbols=["FPT", "VNM"]))
    assert "requested_symbol_missing:VCB" in result["reasons"]


def test_max_rows_zero_blocks(tmp_path: Path) -> None:
    assert "max_rows_must_be_positive" in _build(tmp_path, max_rows=0)["reasons"]


def test_all_cash_has_zero_bps_units(tmp_path: Path) -> None:
    result = _build(tmp_path)
    assert result["status"] == "ok"
    assert result["cost_diagnostics"]["total_friction_bps_units"] == 0


def test_enter_exit_counts_events(tmp_path: Path) -> None:
    diagnostics = _build(tmp_path, roundtrip=_roundtrip(enter=3, exit_=2))["cost_diagnostics"]
    assert diagnostics["estimated_cost_event_count"] == 5
    assert diagnostics["estimated_slippage_event_count"] == 5


def test_total_friction_bps_units(tmp_path: Path) -> None:
    diagnostics = _build(tmp_path, roundtrip=_roundtrip(enter=2, exit_=2))["cost_diagnostics"]
    assert diagnostics["total_transaction_cost_bps_units"] == 60
    assert diagnostics["total_slippage_bps_units"] == 40
    assert diagnostics["total_friction_bps_units"] == 100


def test_output_has_no_performance_or_currency_fields(tmp_path: Path) -> None:
    result = _build(tmp_path)
    keys = _all_keys(result)
    assert not {"pnl", "equity", "return", "returns", "currency_loss", "trade_list", "trades"} & keys


def test_output_never_multiplies_by_price(tmp_path: Path) -> None:
    baseline = _build(tmp_path, roundtrip=_roundtrip(enter=1, exit_=1))
    changed = _roundtrip(enter=1, exit_=1)
    changed["diagnostic_price"] = 999999
    second = _build(tmp_path, roundtrip=changed)
    assert baseline["cost_diagnostics"] == second["cost_diagnostics"]
    assert "price" not in _all_keys(second["cost_diagnostics"])


def test_markdown_report_written(tmp_path: Path) -> None:
    markdown = render_fixture_cost_diagnostics_markdown(_build(tmp_path))
    assert "Bps-Units Diagnostics" in markdown
    assert "not PnL or returns" in markdown


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path)
    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


def test_cli_failure_exits_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, missing=True)
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr


def test_no_backtrader_imports() -> None:
    assert "backtrader" not in _implementation_text().lower()


def test_no_optimizer_code() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("grid_search", "gridsearch", "scipy.optimize", "def optimize"))


def test_no_network_imports() -> None:
    text = _implementation_text()
    assert all(token not in text for token in ("requests", "httpx", "urllib", "socket"))


def test_no_db_mutation() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("sqlite3", "insert into", "delete from", "create table", ".execute("))


def test_no_trade_list_output(tmp_path: Path) -> None:
    assert not {"trade", "trades", "trade_list"} & _all_keys(_build(tmp_path))


def _run_cli(tmp_path: Path, *, missing: bool = False) -> subprocess.CompletedProcess[str]:
    prep = _write(tmp_path / "preparation.json", _preparation())
    roundtrip = _write(tmp_path / "roundtrip.json", _roundtrip())
    if missing:
        prep = tmp_path / "missing.json"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--preparation-json",
            str(prep),
            "--roundtrip-json",
            str(roundtrip),
            "--symbols",
            "FPT,VNM,VCB",
            "--output-md",
            str(tmp_path / "report.md"),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | set().union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _implementation_text() -> str:
    return SOURCE.read_text(encoding="utf-8") + SCRIPT.read_text(encoding="utf-8")
