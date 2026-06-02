from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.data_sources.vnstock_client import FetchResult
from trading_agent.ingestion.contracts import RawRecord, make_security_id
from trading_agent.ingestion.vnstock_ingestion import (
    VnstockIngestion,
    normalize_corporate_events,
    normalize_daily_prices,
    normalize_securities,
)


def test_security_id_generation() -> None:
    assert make_security_id("HOSE", "fpt") == "vnstock:HOSE:FPT"
    assert make_security_id(None, "vnm") == "vnstock:UNKNOWN:VNM"
    assert make_security_id("HSX", "fpt") == "vnstock:HOSE:FPT"


def test_daily_ohlcv_normalization_handles_column_variants() -> None:
    raw = RawRecord(
        dataset="ohlcv",
        data=pd.DataFrame(
            {
                "time": ["2024-01-02"],
                "Open": [100],
                "High": [102],
                "Low": [99],
                "Close": [101],
                "Volume": [1000],
            }
        ),
        source_id="vnstock:ohlcv:FPT:run1",
        raw_path="data/raw/vnstock/run_id=run1/ohlcv/symbol=FPT/data.csv",
        crawled_at="2026-06-01T00:00:00+00:00",
        original_columns=["time", "Open", "High", "Low", "Close", "Volume"],
    )

    df = normalize_daily_prices([raw], {"FPT": "HOSE"})

    assert list(df["security_id"]) == ["vnstock:HOSE:FPT"]
    assert list(df["symbol"]) == ["FPT"]
    assert list(df["exchange"]) == ["HOSE"]
    assert float(df.loc[0, "close"]) == 101.0
    assert "value" in df.columns
    assert "adjusted_close" in df.columns
    assert pd.isna(df.loc[0, "adjusted_close"])


def test_company_events_normalization_uses_vnstock_event_columns() -> None:
    raw = RawRecord(
        dataset="company_events",
        data=pd.DataFrame(
            {
                "id": [1001, 1002],
                "ticker": ["FPT", "FPT"],
                "event_code": ["DIVIDEND", "RIGHTS"],
                "event_title_en": ["Cash dividend", "Share issuance"],
                "public_date": ["2024-01-02", "2024-02-03"],
                "exright_date": ["2024-01-10", "2024-02-10"],
                "record_date": ["2024-01-11", "2024-02-11"],
                "payout_date": ["2024-01-20", "2024-02-20"],
                "value_per_share": [1000, None],
                "exercise_ratio": [None, "10:1"],
            }
        ),
        source_id="vnstock:company_events:FPT:run1",
        raw_path="raw.csv",
        crawled_at="2026-06-01T00:00:00+00:00",
        original_columns=[],
    )

    df = normalize_corporate_events([raw], {"FPT": "HOSE"})

    assert len(df) == 2
    assert df["event_id"].nunique() == 2
    assert df.loc[0, "event_type"] == "DIVIDEND"
    assert df.loc[0, "title"] == "Cash dividend"
    assert str(df.loc[0, "ex_date"]) == "2024-01-10"


def test_securities_normalization_uses_exchange_listing() -> None:
    listing = RawRecord(
        dataset="listing_symbols_by_exchange",
        data=pd.DataFrame({"ticker": ["FPT"], "floor": ["HOSE"], "organName": ["FPT Corp"], "type": ["stock"]}),
        source_id="vnstock:listing_symbols_by_exchange:run1",
        raw_path="raw.csv",
        crawled_at="2026-06-01T00:00:00+00:00",
        original_columns=["ticker", "floor", "organName", "type"],
    )

    df = normalize_securities([listing], ["FPT"], "run1", "2026-06-01T00:00:00+00:00")

    assert df.loc[0, "security_id"] == "vnstock:HOSE:FPT"
    assert df.loc[0, "company_name"] == "FPT Corp"


def test_securities_prefer_known_exchange_and_drop_duplicate_unknown() -> None:
    listing_all = RawRecord(
        dataset="listing_all_symbols",
        data=pd.DataFrame({"symbol": ["FPT", "VNM"], "organ_name": ["FPT Corp", "Vinamilk"]}),
        source_id="vnstock:listing_all_symbols:run1",
        raw_path="all.csv",
        crawled_at="2026-06-01T00:00:00+00:00",
        original_columns=["symbol", "organ_name"],
    )
    listing_by_exchange = RawRecord(
        dataset="listing_symbols_by_exchange",
        data=pd.DataFrame(
            {
                "symbol": ["FPT", "FPT", "VNM"],
                "exchange": [None, "HOSE", "HOSE"],
                "type": ["stock", "stock", "stock"],
            }
        ),
        source_id="vnstock:listing_symbols_by_exchange:run1",
        raw_path="exchange.csv",
        crawled_at="2026-06-01T00:00:00+00:00",
        original_columns=["symbol", "exchange", "type"],
    )

    df = normalize_securities([listing_all, listing_by_exchange], ["FPT", "VNM"], "run1", "2026-06-01T00:00:00+00:00")

    assert set(df["security_id"]) == {"vnstock:HOSE:FPT", "vnstock:HOSE:VNM"}
    assert set(df["exchange"]) == {"HOSE"}
    assert df.loc[df["symbol"] == "FPT", "company_name"].iloc[0] == "FPT Corp"
    assert df.loc[df["symbol"] == "VNM", "company_name"].iloc[0] == "Vinamilk"


def test_daily_prices_inherit_exchange_from_normalized_securities_lookup() -> None:
    securities = pd.DataFrame({"symbol": ["FPT", "VNM"], "exchange": ["HOSE", "HOSE"]})
    lookup = VnstockIngestion._symbol_exchange_lookup_from_securities(securities)
    raw = RawRecord(
        dataset="ohlcv",
        data=pd.DataFrame(
            {
                "time": ["2024-01-02", "2024-01-02"],
                "ticker": ["FPT", "VNM"],
                "open": [100, 80],
                "high": [102, 82],
                "low": [99, 79],
                "close": [101, 81],
                "volume": [1000, 2000],
            }
        ),
        source_id="vnstock:ohlcv:FPT:run1",
        raw_path="prices.csv",
        crawled_at="2026-06-01T00:00:00+00:00",
        original_columns=[],
    )

    df = normalize_daily_prices([raw], lookup)

    assert set(df["security_id"]) == {"vnstock:HOSE:FPT", "vnstock:HOSE:VNM"}
    assert set(df["exchange"]) == {"HOSE"}


class FakeClient:
    def get_listing_all_symbols(self) -> FetchResult:
        return FetchResult(
            dataset="listing_all_symbols",
            status="success",
            data=pd.DataFrame({"symbol": ["FPT"], "company_name": ["FPT Corp"]}),
        )

    def get_listing_symbols_by_exchange(self) -> FetchResult:
        return FetchResult(
            dataset="listing_symbols_by_exchange",
            status="success",
            data=pd.DataFrame({"symbol": ["FPT"], "exchange": ["HOSE"], "security_type": ["stock"]}),
        )

    def get_ohlcv(self, symbol: str, start: str, end: str) -> FetchResult:
        return FetchResult(
            dataset="ohlcv",
            status="success",
            symbol=symbol,
            data=pd.DataFrame(
                {
                    "time": ["2024-01-02"],
                    "open": [100],
                    "high": [102],
                    "low": [99],
                    "close": [101],
                    "volume": [1000],
                }
            ),
        )

    def get_company_events(self, symbol: str) -> FetchResult:
        return FetchResult(dataset="company_events", status="failure", symbol=symbol, error="not available")


def test_company_events_optional_failure_does_not_fail_ingestion(tmp_path: Path) -> None:
    result = VnstockIngestion(
        client=FakeClient(),
        raw_base_dir=tmp_path / "raw",
        silver_dir=tmp_path / "silver",
        reports_dir=tmp_path / "reports",
    ).run(symbols=["FPT"], start="2024-01-01", end="2024-01-31")

    assert "securities" in result.outputs
    assert "daily_prices" in result.outputs
    assert "corporate_events" not in result.outputs
    assert any("company_events unavailable" in warning for warning in result.warnings)
    assert (tmp_path / "reports" / "data_inventory.md").exists()
    assert (tmp_path / "reports" / "data_quality_report.md").exists()
