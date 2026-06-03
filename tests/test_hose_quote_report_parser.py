from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.hose_quote_report_parser import (
    DATA_STATUS_PROVISIONAL,
    extract_trading_date,
    make_price_bar_id,
    parse_hose_quote_report_payload,
)


def test_quote_report_parses_top_level_data_list(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    result = parse_hose_quote_report_payload(raw_path, metadata_path)

    assert len(result.daily_price_bars) == 2
    assert len(result.daily_quote_reports) == 2
    assert len(result.market_ohlcv_snapshots) == 2
    assert result.validation_summary["json_row_count"] == 2


def test_trading_date_extracted_from_metadata_request_url(tmp_path: Path) -> None:
    _, metadata_path = _write_fixture(tmp_path, date="2026-06-02")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert extract_trading_date(metadata) == "2026-06-02"


def test_numeric_strings_with_commas_parse(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_row(mainVolume="6,756.00", mainValue="4,734.69")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)
    row = result.daily_quote_reports.iloc[0]

    assert row["matched_volume"] == 6756.0
    assert row["trading_value"] == 4734.69


def test_zero_no_trade_behavior_warns_not_fail(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _row(
                openPrice="0.00",
                highPrice="0.00",
                lowPrice="0.00",
                averagePrice="0.00",
                priorClosePrice="10.00",
                closePrice="10.00",
            )
        ],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)
    row = result.daily_price_bars.iloc[0]

    assert row["quality_status"] == "warn"
    assert "warning_no_trade_zero_ohlc" in row["quality_reasons"]


def test_high_low_validation_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_row(highPrice="9.00", lowPrice="10.00")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)

    assert result.daily_price_bars.iloc[0]["quality_status"] == "fail"
    assert "high_price_less_than_low_price" in result.daily_price_bars.iloc[0]["quality_reasons"]


def test_close_and_open_within_high_low_validation_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_row(openPrice="12.00", highPrice="11.00", lowPrice="9.00", closePrice="8.00")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)
    reasons = result.daily_price_bars.iloc[0]["quality_reasons"]

    assert result.daily_price_bars.iloc[0]["quality_status"] == "fail"
    assert "open_price_outside_high_low" in reasons
    assert "close_price_outside_high_low" in reasons


def test_duplicate_symbol_trading_date_data_status_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_row(securitySymbol="FPT", id="1"), _row(securitySymbol=" fpt ", id="2")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)

    assert set(result.daily_price_bars["quality_status"]) == {"fail"}
    assert all("duplicate_symbol_trading_date_data_status" in value for value in result.daily_price_bars["quality_reasons"])


def test_current_day_provisional_warning(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        dataset="hose_daily_quote_report_current_day",
        date="2026-06-03",
        rows=[_row(securitySymbol="FPT")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)

    row = result.daily_price_bars.iloc[0]
    assert row["data_status"] == DATA_STATUS_PROVISIONAL
    assert row["quality_status"] == "warn"
    assert "warning_provisional_current_day" in row["quality_reasons"]


def test_deterministic_ids_are_stable(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, rows=[_row(securitySymbol="FPT")])

    first = parse_hose_quote_report_payload(raw_path, metadata_path)
    second = parse_hose_quote_report_payload(raw_path, metadata_path)

    assert first.daily_price_bars.loc[0, "price_bar_id"] == second.daily_price_bars.loc[0, "price_bar_id"]
    assert first.daily_quote_reports.loc[0, "quote_report_id"] == second.daily_quote_reports.loc[0, "quote_report_id"]
    assert first.market_ohlcv_snapshots.loc[0, "snapshot_id"] == second.market_ohlcv_snapshots.loc[0, "snapshot_id"]
    assert first.daily_price_bars.loc[0, "price_bar_id"] == make_price_bar_id("hose", "FPT", "2026-06-02", "final_candidate")


def test_invalid_numeric_value_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_row(openPrice="bad-number")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)

    assert result.daily_price_bars.iloc[0]["quality_status"] == "fail"
    assert "invalid_numeric_open_price" in result.daily_price_bars.iloc[0]["quality_reasons"]


def test_missing_required_symbol_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_row(securitySymbol="")],
    )

    result = parse_hose_quote_report_payload(raw_path, metadata_path)

    assert result.daily_price_bars.iloc[0]["quality_status"] == "fail"
    assert "missing_required_symbol" in result.daily_price_bars.iloc[0]["quality_reasons"]


def _write_fixture(
    tmp_path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
    dataset: str = "hose_daily_quote_report",
    date: str = "2026-06-02",
) -> tuple[Path, Path]:
    payload = {
        "data": rows or [_row(securitySymbol="AAA", id="1"), _row(securitySymbol="AAM", id="2")],
        "success": True,
        "message": None,
    }
    raw_path = tmp_path / "payload.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    content_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "hose",
                "dataset": dataset,
                "endpoint_or_surface": f"https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date={date}",
                "raw_path": str(raw_path),
                "content_hash": content_hash,
                "access_status": "verified",
                "status": "success",
                "terms_notes": "synthetic fixture",
            }
        ),
        encoding="utf-8",
    )
    return raw_path, metadata_path


def _row(
    *,
    id: object = "source-row-1",
    securitySymbol: object = "AAA",
    securityName: object = None,
    isin: object = None,
    bloomberg: object = None,
    changePrice: object = "0.10",
    priorClosePrice: object = "10.00",
    openPrice: object = "10.10",
    highPrice: object = "10.50",
    lowPrice: object = "9.80",
    closePrice: object = "10.20",
    changePriceRatio: object = "1.00",
    mainVolume: object = "1,000.00",
    mainValue: object = "10,200.00",
    averagePrice: object = "10.20",
    ceiling: object = "11.00",
    floor: object = "9.00",
) -> dict[str, object]:
    return {
        "id": id,
        "securitySymbol": securitySymbol,
        "securityName": securityName,
        "isin": isin,
        "bloomberg": bloomberg,
        "changePrice": changePrice,
        "priorClosePrice": priorClosePrice,
        "openPrice": openPrice,
        "highPrice": highPrice,
        "lowPrice": lowPrice,
        "closePrice": closePrice,
        "changePriceRatio": changePriceRatio,
        "mainVolume": mainVolume,
        "mainValue": mainValue,
        "averagePrice": averagePrice,
        "ceiling": ceiling,
        "floor": floor,
    }
