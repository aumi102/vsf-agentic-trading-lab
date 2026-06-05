from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from parse_vietcap_iq_gap_chart_dry_run import build_combined_summary
from trading_agent.ingestion.parsers.vietcap_iq_gap_chart_parser import (
    BAR_INTERVAL,
    PRICE_BASIS,
    ADJUSTMENT_TYPE,
    make_price_bar_id,
    parse_vietcap_iq_gap_chart_payload,
)


def test_top_level_array_parsing_and_aligned_arrays_explode_to_rows(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, [_symbol_object("FPT")])

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)

    assert len(result.daily_price_bars) == 2
    assert result.validation_summary["top_level_object_count"] == 1
    assert result.validation_summary["daily_price_bars_count"] == 2
    row = result.daily_price_bars.iloc[0]
    assert row["symbol"] == "FPT"
    assert row["bar_interval"] == BAR_INTERVAL
    assert row["price_basis"] == PRICE_BASIS
    assert row["adjustment_type"] == ADJUSTMENT_TYPE
    assert row["open_price"] == 10.0
    assert row["high_price"] == 11.0
    assert row["low_price"] == 9.0
    assert row["close_price"] == 10.5
    assert row["volume"] == 1000.0
    assert row["accumulated_volume"] == 1000.0
    assert row["trading_value"] == 10500.0


def test_mismatched_aligned_array_length_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, [_symbol_object("FPT", c=[10.5])])

    with pytest.raises(ValueError, match="aligned array length mismatch"):
        parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)


def test_ohlc_validation_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        [_symbol_object("FPT", o=[12, 10], h=[11, 11], l=[9, 9], c=[8, 10.5])],
    )

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)
    first = result.daily_price_bars.iloc[0]

    assert first["quality_status"] == "fail"
    assert "open_price_outside_high_low" in first["quality_reasons"]
    assert "close_price_outside_high_low" in first["quality_reasons"]


def test_duplicate_bar_key_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        [_symbol_object("FPT", t=[1749081600, 1749081600])],
    )

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)

    assert set(result.daily_price_bars["quality_status"]) == {"fail"}
    assert all("duplicate_symbol_bar_ts_price_basis_bar_interval" in value for value in result.daily_price_bars["quality_reasons"])


def test_missing_volume_warns_not_fails(tmp_path: Path) -> None:
    item = _symbol_object("FPT")
    item.pop("v")
    raw_path, metadata_path = _write_fixture(tmp_path, [item])

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)

    assert set(result.daily_price_bars["quality_status"]) == {"warn"}
    assert all("warning_missing_volume" in value for value in result.daily_price_bars["quality_reasons"])
    assert result.validation_summary["quality_fail_count"] == 0


def test_invalid_optional_volume_warns_not_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, [_symbol_object("FPT", v=["bad-number", 2000])])

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)
    first = result.daily_price_bars.iloc[0]

    assert first["quality_status"] == "warn"
    assert "warning_invalid_optional_numeric_volume" in first["quality_reasons"]
    assert result.validation_summary["quality_fail_count"] == 0


def test_required_numeric_empty_value_fails_without_zero_fill(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, [_symbol_object("FPT", o=["", 10])])

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)
    first = result.daily_price_bars.iloc[0]

    assert first["quality_status"] == "fail"
    assert "invalid_numeric_open_price" in first["quality_reasons"]
    assert "missing_required_open_price" in first["quality_reasons"]
    assert pd.isna(first["open_price"])
    assert first["open_price"] != 0


def test_deterministic_ids_are_stable(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, [_symbol_object("FPT")])

    first = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)
    second = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)

    expected_id = make_price_bar_id(
        "vietcap_iq",
        "FPT",
        "2025-06-05T00:00:00+00:00",
        BAR_INTERVAL,
        PRICE_BASIS,
        ADJUSTMENT_TYPE,
    )
    assert first.daily_price_bars.loc[0, "price_bar_id"] == second.daily_price_bars.loc[0, "price_bar_id"]
    assert first.daily_price_bars.loc[0, "price_bar_id"] == expected_id


def test_epoch_seconds_convert_to_bar_ts_and_trading_date(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, [_symbol_object("FPT", t=["1749081600", "1749168000"])])

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)
    row = result.daily_price_bars.iloc[0]

    assert row["bar_ts"] == "2025-06-05T00:00:00+00:00"
    assert row["trading_date"] == "2025-06-05"


def test_countback_250_is_limited_history_warning(tmp_path: Path) -> None:
    item = _symbol_object(
        "FPT",
        t=list(range(1749081600, 1749081600 + 250 * 86400, 86400)),
        o=[10] * 250,
        h=[11] * 250,
        l=[9] * 250,
        c=[10.5] * 250,
        v=[1000] * 250,
        accumulatedVolume=[1000] * 250,
        accumulatedValue=[10500] * 250,
    )
    raw_path, metadata_path = _write_fixture(tmp_path, [item])

    result = parse_vietcap_iq_gap_chart_payload(raw_path, metadata_path)

    assert result.validation_summary["count_back"] == 250
    assert result.validation_summary["quality_warn_count"] == 250
    assert "warning_limited_history_countback_250" in result.daily_price_bars.iloc[0]["quality_reasons"]


def test_script_combined_summary_aggregates_coverage(tmp_path: Path) -> None:
    first_raw, first_metadata = _write_fixture(tmp_path / "first", [_symbol_object("FPT")], dataset="vietcap_iq_gap_chart_fpt")
    second_raw, second_metadata = _write_fixture(tmp_path / "second", [_symbol_object("VNM")], dataset="vietcap_iq_gap_chart_vnm")
    results = [
        parse_vietcap_iq_gap_chart_payload(first_raw, first_metadata),
        parse_vietcap_iq_gap_chart_payload(second_raw, second_metadata),
    ]

    summary = build_combined_summary(
        results,
        inputs=[
            ("vietcap_iq_gap_chart_fpt", first_raw, first_metadata),
            ("vietcap_iq_gap_chart_vnm", second_raw, second_metadata),
        ],
        run_id="20260605T000000Z",
        output_dir=tmp_path / "out",
    )

    assert summary["parsed_symbol_count"] == 2
    assert summary["total_bar_count"] == 4
    assert summary["coverage_by_symbol"]["FPT"]["bar_count"] == 2
    assert summary["coverage_by_symbol"]["VNM"]["bar_count"] == 2


def _write_fixture(tmp_path: Path, objects: list[dict[str, object]], *, dataset: str = "vietcap_iq_gap_chart_fpt") -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw_path = tmp_path / "payload.json"
    raw_path.write_text(json.dumps(objects, ensure_ascii=False), encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "vietcap_iq",
                "dataset": dataset,
                "raw_path": str(raw_path),
                "content_hash": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "access_status": "verified",
                "status": "success",
                "symbol": "FPT",
                "terms_notes": "synthetic fixture",
            }
        ),
        encoding="utf-8",
    )
    return raw_path, metadata_path


def _symbol_object(
    symbol: object,
    *,
    t: list[object] | None = None,
    o: list[object] | None = None,
    h: list[object] | None = None,
    l: list[object] | None = None,
    c: list[object] | None = None,
    v: list[object] | None = None,
    accumulatedVolume: list[object] | None = None,
    accumulatedValue: list[object] | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "t": t if t is not None else [1749081600, 1749168000],
        "o": o if o is not None else [10, 10.2],
        "h": h if h is not None else [11, 11.2],
        "l": l if l is not None else [9, 9.2],
        "c": c if c is not None else [10.5, 10.8],
        "v": v if v is not None else [1000, 2000],
        "accumulatedVolume": accumulatedVolume if accumulatedVolume is not None else [1000, 2000],
        "accumulatedValue": accumulatedValue if accumulatedValue is not None else [10500, 21600],
        "minBatchTruncTime": 1749081600,
    }
