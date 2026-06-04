from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_hose_quote_report_stock_only_dry_run as stock_filter


def test_symbol_normalization() -> None:
    values = pd.Series([" fpt ", "vNm", None, ""])

    normalized = stock_filter.normalize_symbol_series(values)

    assert normalized.tolist() == ["FPT", "VNM", "", ""]


def test_stock_only_join_keeps_matched_symbols(tmp_path: Path) -> None:
    quote_dir, listed_dir = write_fixture_dirs(tmp_path)

    outputs = stock_filter.build_stock_only_outputs(quote_dir=quote_dir, listed_dir=listed_dir)

    stock_quotes = outputs["daily_quote_reports_stock_only"]
    assert stock_quotes["symbol"].tolist() == ["FPT", "VNM"]
    assert stock_quotes["security_id"].tolist() == ["hose:FPT", "hose:VNM"]
    assert stock_quotes["company_name"].tolist() == ["FPT Corp", "Vinamilk"]
    assert outputs["summary"]["stock_only_rows"] == 2
    assert outputs["summary"]["stock_only_unique_symbols"] == 2


def test_excluded_symbols_are_preserved_separately(tmp_path: Path) -> None:
    quote_dir, listed_dir = write_fixture_dirs(tmp_path)

    outputs = stock_filter.build_stock_only_outputs(quote_dir=quote_dir, listed_dir=listed_dir)
    excluded = outputs["excluded_non_stock_symbols"]

    assert excluded["symbol"].tolist() == ["CFPT2517"]
    assert excluded["exclusion_reason"].tolist() == ["not_in_hose_listed_stock_universe"]
    assert outputs["summary"]["excluded_rows"] == 1
    assert outputs["summary"]["excluded_unique_symbols"] == 1


def test_duplicate_quote_report_symbol_detection(tmp_path: Path) -> None:
    quote_dir, listed_dir = write_fixture_dirs(
        tmp_path,
        quote_symbols=["FPT", " fpt "],
        listed_symbols=["FPT"],
    )

    with pytest.raises(ValueError, match="Duplicate quote-report"):
        stock_filter.build_stock_only_outputs(quote_dir=quote_dir, listed_dir=listed_dir)


def test_duplicate_listed_universe_warns_and_keeps_first(tmp_path: Path) -> None:
    quote_dir, listed_dir = write_fixture_dirs(
        tmp_path,
        quote_symbols=["FPT"],
        listed_symbols=["FPT", " fpt "],
        company_names=["First FPT", "Duplicate FPT"],
    )

    outputs = stock_filter.build_stock_only_outputs(quote_dir=quote_dir, listed_dir=listed_dir)

    assert outputs["daily_quote_reports_stock_only"].loc[0, "company_name"] == "First FPT"
    assert outputs["summary"]["duplicate_symbol_count_listed_universe"] == 2
    assert outputs["summary"]["warnings"] == ["warning_duplicate_listed_universe_symbols_kept_first:2"]
    assert outputs["summary"]["run_quality_status"] == "warn"


def test_summary_counts(tmp_path: Path) -> None:
    quote_dir, listed_dir = write_fixture_dirs(tmp_path)

    outputs = stock_filter.build_stock_only_outputs(quote_dir=quote_dir, listed_dir=listed_dir)
    summary = outputs["summary"]

    assert summary["quote_report_rows"] == 3
    assert summary["quote_report_unique_symbols"] == 3
    assert summary["listed_universe_rows"] == 2
    assert summary["listed_universe_unique_symbols"] == 2
    assert summary["stock_only_rows"] == 2
    assert summary["excluded_rows"] == 1
    assert summary["data_status_counts"] == {"final_candidate": 3}
    assert summary["quality_status_counts_after_filter"] == {"warn": 2}


def write_fixture_dirs(
    tmp_path: Path,
    *,
    quote_symbols: list[str] | None = None,
    listed_symbols: list[str] | None = None,
    company_names: list[str] | None = None,
) -> tuple[Path, Path]:
    quote_symbols = quote_symbols or ["FPT", "VNM", "CFPT2517"]
    listed_symbols = listed_symbols or ["FPT", "VNM"]
    company_names = company_names or ["FPT Corp", "Vinamilk"]

    quote_dir = tmp_path / "quote"
    listed_dir = tmp_path / "listed"
    quote_dir.mkdir()
    listed_dir.mkdir()

    quote_reports = pd.DataFrame([quote_row(symbol) for symbol in quote_symbols])
    price_bars = quote_reports[
        [
            "symbol",
            "exchange",
            "trading_date",
            "data_status",
            "prior_close_price",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "matched_volume",
            "trading_value",
            "quality_status",
            "quality_reasons",
        ]
    ].copy()
    snapshots = quote_reports[
        [
            "symbol",
            "exchange",
            "trading_date",
            "data_status",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "average_price",
            "matched_volume",
            "trading_value",
            "quality_status",
            "quality_reasons",
        ]
    ].copy()
    quote_reports.to_csv(quote_dir / "daily_quote_reports.csv", index=False)
    price_bars.to_csv(quote_dir / "daily_price_bars.csv", index=False)
    snapshots.to_csv(quote_dir / "market_ohlcv_snapshots.csv", index=False)
    (quote_dir / "validation_summary.json").write_text(
        json.dumps({"quality_reason_counts": {"warning_source_units_unconfirmed": len(quote_reports)}}),
        encoding="utf-8",
    )

    symbol_universe = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "display_text": f"{str(symbol).strip().upper()} | {company_names[index]}",
                "company_name": company_names[index],
                "security_type_code": 1,
                "listing_status_id": 11,
            }
            for index, symbol in enumerate(listed_symbols)
        ]
    )
    securities = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "security_id": f"hose:{str(symbol).strip().upper()}",
                "company_name": company_names[index],
                "outstanding_volume": 1000 + index,
            }
            for index, symbol in enumerate(listed_symbols)
        ]
    )
    listings = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "security_type_code": 1,
                "listing_status_id": 11,
                "listed_volume": 2000 + index,
            }
            for index, symbol in enumerate(listed_symbols)
        ]
    )
    symbol_universe.to_csv(listed_dir / "symbol_universe.csv", index=False)
    securities.to_csv(listed_dir / "securities_master.csv", index=False)
    listings.to_csv(listed_dir / "exchange_listings.csv", index=False)
    return quote_dir, listed_dir


def quote_row(symbol: str) -> dict[str, object]:
    return {
        "quote_report_id": f"qr:{symbol}",
        "symbol": symbol,
        "exchange": "HOSE",
        "trading_date": "2026-06-02",
        "data_status": "final_candidate",
        "security_name": "",
        "isin": "",
        "bloomberg_id": "",
        "prior_close_price": 10.0,
        "ceiling_price": 11.0,
        "floor_price": 9.0,
        "open_price": 10.0,
        "high_price": 10.5,
        "low_price": 9.8,
        "close_price": 10.2,
        "average_price": 10.1,
        "price_change": 0.2,
        "price_change_pct": 2.0,
        "matched_volume": 1000.0,
        "trading_value": 10200.0,
        "source_name": "hose",
        "source_row_id": f"row:{symbol}",
        "source_payload_id": "hose:payload",
        "raw_content_hash": "hash",
        "raw_row_index": 0,
        "parser_version": "test",
        "schema_version": "test",
        "quality_status": "warn",
        "quality_reasons": "warning_source_units_unconfirmed",
    }
