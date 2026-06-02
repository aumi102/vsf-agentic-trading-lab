from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.quality.checks import check_daily_prices, check_securities


def test_duplicate_detection_for_daily_prices() -> None:
    df = pd.DataFrame(
        {
            "security_id": ["vnstock:HOSE:FPT", "vnstock:HOSE:FPT"],
            "symbol": ["FPT", "FPT"],
            "exchange": ["HOSE", "HOSE"],
            "trade_date": ["2024-01-02", "2024-01-02"],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1100],
            "adjusted_close": [None, None],
            "source_id": ["src1", "src1"],
        }
    )

    result = check_daily_prices(df)

    assert result.quality_status == "fail"
    assert result.duplicate_count == 1
    assert "duplicate_security_id_trade_date" in result.failed_gates


def test_ohlc_invalid_row_detection() -> None:
    df = pd.DataFrame(
        {
            "security_id": ["vnstock:HOSE:FPT"],
            "symbol": ["FPT"],
            "exchange": ["HOSE"],
            "trade_date": ["2024-01-02"],
            "open": [100.0],
            "high": [99.0],
            "low": [98.0],
            "close": [101.0],
            "volume": [1000],
            "adjusted_close": [None],
            "source_id": ["src1"],
        }
    )

    result = check_daily_prices(df)

    assert result.quality_status == "fail"
    assert result.ohlc_error_count == 1
    assert "ohlc_inconsistent" in result.failed_gates


def test_missing_adjusted_close_is_warning() -> None:
    df = pd.DataFrame(
        {
            "security_id": ["vnstock:HOSE:FPT"],
            "symbol": ["FPT"],
            "exchange": ["HOSE"],
            "trade_date": ["2024-01-02"],
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
            "volume": [1000],
            "adjusted_close": [None],
            "source_id": ["src1"],
        }
    )

    result = check_daily_prices(df)

    assert result.quality_status == "warn"
    assert "adjusted_close_missing_or_unclear" in result.warning_reasons


def test_securities_unknown_exchange_warning() -> None:
    df = pd.DataFrame(
        {
            "security_id": ["vnstock:UNKNOWN:FPT"],
            "symbol": ["FPT"],
            "exchange": ["UNKNOWN"],
            "source_id": ["src1"],
            "crawled_at": ["2026-06-01T00:00:00+00:00"],
            "schema_version": ["vnstock_ingestion_v1"],
        }
    )

    result = check_securities(df)

    assert result.quality_status == "warn"
    assert "exchange_unknown" in result.warning_reasons
