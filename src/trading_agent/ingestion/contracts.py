from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


SCHEMA_VERSION = "vnstock_ingestion_v1"
SOURCE = "vnstock"
KNOWN_EXCHANGES = {"HOSE", "HNX", "UPCOM", "UNKNOWN"}

SECURITIES_COLUMNS = [
    "security_id",
    "symbol",
    "exchange",
    "company_name",
    "security_type",
    "industry",
    "market_cap",
    "foreign_room",
    "source",
    "source_id",
    "crawled_at",
    "schema_version",
]

DAILY_PRICES_COLUMNS = [
    "security_id",
    "symbol",
    "exchange",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value",
    "adjusted_close",
    "source",
    "source_id",
    "raw_path",
    "crawled_at",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

CORPORATE_EVENTS_COLUMNS = [
    "event_id",
    "security_id",
    "symbol",
    "event_type",
    "title",
    "description",
    "announcement_date",
    "ex_date",
    "record_date",
    "payment_date",
    "effective_date",
    "cash_dividend",
    "stock_dividend_ratio",
    "issue_ratio",
    "source",
    "source_id",
    "raw_path",
    "crawled_at",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

COLUMN_VARIANTS = {
    "symbol": ["symbol", "ticker", "code", "stock_code", "stockCode"],
    "exchange": ["exchange", "comGroupCode", "floor", "exchange_name", "exchangeName"],
    "company_name": ["company_name", "organName", "organ_name", "name", "companyName"],
    "security_type": ["security_type", "type", "stockType", "securityType"],
    "industry": ["industry", "industryName", "icbName", "sector"],
    "market_cap": ["market_cap", "marketCap", "market_capitalization"],
    "foreign_room": ["foreign_room", "foreignRoom", "foreign_percent"],
    "trade_date": ["trade_date", "trading_date", "date", "time"],
    "open": ["open", "Open"],
    "high": ["high", "High"],
    "low": ["low", "Low"],
    "close": ["close", "Close"],
    "volume": ["volume", "Volume"],
    "value": ["value", "trading_value", "tradingValue", "matchValue"],
    "adjusted_close": ["adjusted_close", "adjustedClose", "adj_close", "adClose"],
    "event_source_id": ["event_source_id", "eventSourceId", "id"],
    "event_type": ["event_type", "eventType", "event_code", "eventCode", "action_type_en", "action_type_vi", "type"],
    "title": ["title", "event_title", "event_title_en", "event_title_vi", "eventName", "event_name_en", "event_name_vi", "name"],
    "description": ["description", "content", "event_desc", "event_name_en", "event_name_vi", "desc"],
    "announcement_date": ["announcement_date", "announcedDate", "publicDate", "public_date"],
    "ex_date": ["ex_date", "exrightDate", "exright_date", "exRightDate", "exDate"],
    "record_date": ["record_date", "recordDate"],
    "payment_date": ["payment_date", "paymentDate", "payout_date", "payoutDate"],
    "effective_date": ["effective_date", "effectiveDate", "issue_date", "listing_date"],
    "cash_dividend": ["cash_dividend", "cashDividend", "cash", "value_per_share"],
    "stock_dividend_ratio": ["stock_dividend_ratio", "stockDividendRatio", "stockDividend"],
    "issue_ratio": ["issue_ratio", "issueRatio", "rightIssueRatio", "exercise_ratio"],
}


@dataclass(frozen=True)
class RawRecord:
    dataset: str
    data: pd.DataFrame
    source_id: str
    raw_path: str
    crawled_at: str
    original_columns: list[str]
    status: str = "success"
    error: str | None = None


def first_present(df: pd.DataFrame, canonical_name: str) -> str | None:
    for candidate in COLUMN_VARIANTS.get(canonical_name, [canonical_name]):
        if candidate in df.columns:
            return candidate
    lower_map = {str(col).lower(): col for col in df.columns}
    for candidate in COLUMN_VARIANTS.get(canonical_name, [canonical_name]):
        match = lower_map.get(candidate.lower())
        if match is not None:
            return str(match)
    return None


def get_series(df: pd.DataFrame, canonical_name: str, default: Any = None) -> pd.Series:
    column = first_present(df, canonical_name)
    if column is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[column]


def normalize_symbol(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    return text or None


def normalize_exchange(value: Any) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    text = str(value).strip().upper()
    if not text:
        return "UNKNOWN"
    aliases = {
        "HSX": "HOSE",
        "HO": "HOSE",
        "HOSE": "HOSE",
        "HNX": "HNX",
        "UPCOM": "UPCOM",
        "UPCoM".upper(): "UPCOM",
    }
    return aliases.get(text, text if text in KNOWN_EXCHANGES else "UNKNOWN")


def make_security_id(exchange: Any, symbol: Any) -> str:
    normalized_symbol = normalize_symbol(symbol) or "UNKNOWN"
    normalized_exchange = normalize_exchange(exchange)
    return f"{SOURCE}:{normalized_exchange}:{normalized_symbol}"


def source_id_for(dataset: str, run_id: str, symbol: str | None = None) -> str:
    if symbol:
        return f"{SOURCE}:{dataset}:{symbol.upper()}:{run_id}"
    return f"{SOURCE}:{dataset}:{run_id}"


def quality_reasons_to_string(reasons: list[str]) -> str:
    return ";".join(sorted(set(reasons)))
