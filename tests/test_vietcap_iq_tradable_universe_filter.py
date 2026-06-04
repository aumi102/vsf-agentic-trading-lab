from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_vietcap_iq_tradable_universe_dry_run import build_filter_decisions, build_tradable_universe


def test_filter_keeps_hose_hnx_upcom_rows() -> None:
    frame = pd.DataFrame(
        [
            row("FPT", "HOSE"),
            row("ACB", "HNX"),
            row("ABC", "UPCOM"),
        ]
    )

    result = build_filter_decisions(frame)

    assert result["include_tradable_candidate"].tolist() == [True, True, True]
    assert result["exclusion_reasons"].tolist() == ["", "", ""]


def test_filter_excludes_otc_other_stop_index_and_fail_rows() -> None:
    frame = pd.DataFrame(
        [
            row("OTC1", "OTC"),
            row("OTH1", "OTHER"),
            row("STP1", "STOP"),
            row("VNINDEX", "HOSE", is_index=True),
            row("BAD", "HOSE", quality_status="fail"),
            row("", "HOSE"),
            row("MISSFLOOR", ""),
        ]
    )

    result = build_filter_decisions(frame)

    assert result["include_tradable_candidate"].tolist() == [False, False, False, False, False, False, False]
    reasons = ";".join(result["exclusion_reasons"])
    assert "excluded_non_tradable_floor" in reasons
    assert "excluded_index_candidate" in reasons
    assert "excluded_quality_fail" in reasons
    assert "excluded_missing_symbol" in reasons
    assert "excluded_missing_floor" in reasons


def test_build_tradable_universe_preserves_excluded_rows_and_counts(tmp_path: Path) -> None:
    input_dir = write_input_dir(
        tmp_path,
        [
            row("FPT", "HOSE"),
            row("ACB", "HNX"),
            row("UP1", "UPCOM"),
            row("OTC1", "OTC"),
            row("VNINDEX", "HOSE", is_index=True),
            row("BAD", "HOSE", quality_status="fail", quality_reasons="duplicate_symbol_exchange_or_floor"),
        ],
    )

    result = build_tradable_universe(input_dir=input_dir, output_dir=input_dir / "tradable_universe")
    summary = result["summary"]
    excluded = pd.read_csv(input_dir / "tradable_universe" / "excluded_universe_rows.csv")

    assert summary["run_status"] == "warn"
    assert summary["tradable_row_count"] == 3
    assert summary["tradable_unique_symbols"] == 3
    assert summary["excluded_row_count"] == 3
    assert summary["excluded_unique_symbols"] == 3
    assert summary["included_floor_counts"] == {"HNX": 1, "HOSE": 1, "UPCOM": 1}
    assert summary["excluded_floor_counts"] == {"HOSE": 2, "OTC": 1}
    assert summary["excluded_reason_counts"]["excluded_non_tradable_floor"] == 1
    assert summary["excluded_reason_counts"]["excluded_index_candidate"] == 1
    assert summary["excluded_reason_counts"]["excluded_quality_fail"] == 1
    assert set(excluded["symbol"]) == {"OTC1", "VNINDEX", "BAD"}


def test_duplicate_after_filter_fails_run(tmp_path: Path) -> None:
    input_dir = write_input_dir(
        tmp_path,
        [
            row("FPT", "HOSE", raw_row_index=0),
            row("FPT", "HOSE", raw_row_index=1),
        ],
    )

    result = build_tradable_universe(input_dir=input_dir, output_dir=input_dir / "tradable_universe")

    assert result["summary"]["run_status"] == "fail"
    assert result["summary"]["duplicate_symbol_floor_after_filter_count"] == 2


def row(
    symbol: str,
    floor: str,
    *,
    is_index: bool = False,
    quality_status: str = "pass",
    quality_reasons: str = "",
    raw_row_index: int | None = None,
) -> dict[str, object]:
    index = 0 if raw_row_index is None else raw_row_index
    return {
        "raw_row_index": index,
        "symbol": symbol,
        "exchange_or_floor": floor,
        "display_name": symbol,
        "company_name": f"{symbol} name" if symbol else "",
        "short_name": symbol,
        "company_type_code": "CT",
        "is_bank": False,
        "is_index": is_index,
        "quality_status": quality_status,
        "quality_reasons": quality_reasons,
    }


def write_input_dir(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    input_dir = tmp_path / "vietcap"
    input_dir.mkdir()
    symbol_universe = pd.DataFrame([{**item, "source_name": "vietcap_iq"} for item in rows])
    raw_indexes = set(symbol_universe["raw_row_index"])
    if len(raw_indexes) < len(symbol_universe):
        symbol_universe["raw_row_index"] = range(len(symbol_universe))

    security_rows = []
    listing_rows = []
    instrument_rows = []
    for _, item in symbol_universe.iterrows():
        common = {
            "raw_row_index": item["raw_row_index"],
            "symbol": item["symbol"],
            "source_name": "vietcap_iq",
            "quality_status": item["quality_status"],
            "quality_reasons": item["quality_reasons"],
        }
        security_rows.append({**common, "security_id": f"vietcap_iq:{item['symbol']}"})
        listing_rows.append({**common, "exchange_or_floor": item["exchange_or_floor"], "listing_id": f"listing:{item['symbol']}:{item['exchange_or_floor']}"})
        instrument_rows.append({**common, "exchange_or_floor": item["exchange_or_floor"], "instrument_id": f"instrument:{item['symbol']}:{item['exchange_or_floor']}"})

    pd.DataFrame(security_rows).to_csv(input_dir / "securities_master.csv", index=False)
    pd.DataFrame(listing_rows).to_csv(input_dir / "exchange_listings.csv", index=False)
    symbol_universe.to_csv(input_dir / "symbol_universe.csv", index=False)
    pd.DataFrame(instrument_rows).to_csv(input_dir / "instrument_universe.csv", index=False)
    (input_dir / "validation_summary.json").write_text(json.dumps({"run_id": "source_run"}), encoding="utf-8")
    return input_dir
