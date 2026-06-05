from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_ohlcv_fetch_plan_dry_run import build_ohlcv_fetch_plan, validate_sleep


def test_builds_plan_from_synthetic_universe_csvs(tmp_path: Path) -> None:
    input_dir = _write_universe(
        tmp_path,
        symbols=[
            {"symbol": "AAA", "exchange_or_floor": "HOSE"},
            {"symbol": "BBB", "exchange_or_floor": "HNX"},
        ],
        instruments=[
            {"symbol": "AAA", "exchange_or_floor": "HOSE", "icb_lv1_raw": "TECH", "icb_lv2_raw": "SOFTWARE"},
            {"symbol": "BBB", "exchange_or_floor": "HNX", "icb_lv1_raw": "BANKS", "icb_lv2_raw": "BANKING"},
        ],
    )

    result = build_ohlcv_fetch_plan(
        input_dir=input_dir,
        output_dir=tmp_path / "plan",
        run_id="test_run",
        sleep_min_seconds=1.0,
        sleep_max_seconds=3.0,
    )

    plan = result["plan"]
    assert list(plan["symbol"]) == ["BBB", "AAA"]
    assert list(plan["sector_group"]) == ["BANKS", "TECH"]
    assert set(plan["fetch_scope"]) == {"full_history"}
    assert set(plan["price_bases"]) == {"adjusted_and_unadjusted_if_available"}
    assert set(plan["status"]) == {"pending"}
    assert result["summary"]["total_symbols"] == 2
    assert result["summary"]["no_live_fetch"] is True
    assert result["plan_path"].exists()
    assert result["checkpoint_path"].exists()
    assert result["summary_path"].exists()
    assert result["report_path"].exists()


def test_orders_by_sector_then_symbol(tmp_path: Path) -> None:
    input_dir = _write_universe(
        tmp_path,
        symbols=[
            {"symbol": "ZZZ", "exchange_or_floor": "HOSE"},
            {"symbol": "AAA", "exchange_or_floor": "HOSE"},
            {"symbol": "MMM", "exchange_or_floor": "HNX"},
        ],
        instruments=[
            {"symbol": "ZZZ", "exchange_or_floor": "HOSE", "icb_lv1_raw": "TECH", "icb_lv2_raw": ""},
            {"symbol": "AAA", "exchange_or_floor": "HOSE", "icb_lv1_raw": "TECH", "icb_lv2_raw": ""},
            {"symbol": "MMM", "exchange_or_floor": "HNX", "icb_lv1_raw": "BANKS", "icb_lv2_raw": ""},
        ],
    )

    result = build_ohlcv_fetch_plan(
        input_dir=input_dir,
        output_dir=tmp_path / "plan",
        run_id="test_run",
        sleep_min_seconds=1.0,
        sleep_max_seconds=3.0,
    )

    assert list(result["plan"]["symbol"]) == ["MMM", "AAA", "ZZZ"]
    assert list(result["plan"]["planned_order"]) == [1, 2, 3]


def test_writes_checkpoint_summary(tmp_path: Path) -> None:
    input_dir = _write_universe(
        tmp_path,
        symbols=[{"symbol": "AAA", "exchange_or_floor": "HOSE"}],
        instruments=[{"symbol": "AAA", "exchange_or_floor": "HOSE", "icb_lv1_raw": "TECH", "icb_lv2_raw": "SOFTWARE"}],
    )

    result = build_ohlcv_fetch_plan(
        input_dir=input_dir,
        output_dir=tmp_path / "plan",
        run_id="test_run",
        sleep_min_seconds=1.0,
        sleep_max_seconds=3.0,
    )

    checkpoint = json.loads(result["checkpoint_path"].read_text(encoding="utf-8"))
    assert checkpoint["run_id"] == "test_run"
    assert checkpoint["total_symbols"] == 1
    assert checkpoint["pending_symbols"] == 1
    assert checkpoint["completed_symbols"] == 0
    assert checkpoint["failed_symbols"] == 0
    assert checkpoint["current_sector"] == "TECH"
    assert checkpoint["next_planned_order"] == 1
    assert checkpoint["no_live_fetch"] is True


def test_validates_sleep_min_lte_sleep_max() -> None:
    with pytest.raises(ValueError, match="sleep_min_seconds"):
        validate_sleep(5.0, 1.0)


def test_resume_checkpoint_marks_completed_symbols(tmp_path: Path) -> None:
    input_dir = _write_universe(
        tmp_path,
        symbols=[
            {"symbol": "AAA", "exchange_or_floor": "HOSE"},
            {"symbol": "BBB", "exchange_or_floor": "HNX"},
        ],
        instruments=[
            {"symbol": "AAA", "exchange_or_floor": "HOSE", "icb_lv1_raw": "TECH", "icb_lv2_raw": ""},
            {"symbol": "BBB", "exchange_or_floor": "HNX", "icb_lv1_raw": "BANKS", "icb_lv2_raw": ""},
        ],
    )
    checkpoint_path = tmp_path / "old_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps({"completed_symbol_list": ["AAA"], "failed_symbol_list": []}),
        encoding="utf-8",
    )

    result = build_ohlcv_fetch_plan(
        input_dir=input_dir,
        output_dir=tmp_path / "plan",
        run_id="test_run",
        sleep_min_seconds=1.0,
        sleep_max_seconds=3.0,
        resume_checkpoint_path=checkpoint_path,
    )

    status_by_symbol = dict(zip(result["plan"]["symbol"], result["plan"]["status"], strict=True))
    assert status_by_symbol["AAA"] == "completed"
    assert status_by_symbol["BBB"] == "pending"
    assert result["summary"]["completed_symbols"] == 1
    assert result["summary"]["pending_symbols"] == 1


def test_dry_run_records_no_live_network_calls(tmp_path: Path) -> None:
    input_dir = _write_universe(
        tmp_path,
        symbols=[{"symbol": "AAA", "exchange_or_floor": "HOSE"}],
        instruments=[{"symbol": "AAA", "exchange_or_floor": "HOSE", "icb_lv1_raw": "", "icb_lv2_raw": ""}],
    )

    result = build_ohlcv_fetch_plan(
        input_dir=input_dir,
        output_dir=tmp_path / "plan",
        run_id="test_run",
        sleep_min_seconds=0.5,
        sleep_max_seconds=1.0,
    )

    assert result["summary"]["no_live_fetch"] is True
    assert "warning_sleep_min_below_one_second" in result["summary"]["warnings"]
    assert "warning_many_unknown_sector_groups" in result["summary"]["warnings"]


def _write_universe(tmp_path: Path, *, symbols: list[dict[str, object]], instruments: list[dict[str, object]]) -> Path:
    input_dir = tmp_path / "vietcap_run"
    tradable_dir = input_dir / "tradable_universe"
    tradable_dir.mkdir(parents=True)
    pd.DataFrame(symbols).to_csv(tradable_dir / "symbol_universe_tradable.csv", index=False)
    pd.DataFrame(instruments).to_csv(tradable_dir / "instrument_universe_tradable.csv", index=False)
    return input_dir
