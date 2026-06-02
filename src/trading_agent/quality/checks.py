from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_agent.ingestion.contracts import KNOWN_EXCHANGES


@dataclass
class QualityResult:
    table: str
    row_count: int
    quality_status: str
    failed_gates: list[str]
    warning_reasons: list[str]
    duplicate_count: int = 0
    ohlc_error_count: int = 0
    missing_required_columns: list[str] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "row_count": self.row_count,
            "quality_status": self.quality_status,
            "failed_gates": self.failed_gates,
            "warning_reasons": self.warning_reasons,
            "duplicate_count": self.duplicate_count,
            "ohlc_error_count": self.ohlc_error_count,
            "missing_required_columns": self.missing_required_columns or [],
        }


def _status(failed: list[str], warnings: list[str]) -> str:
    if failed:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def check_securities(df: pd.DataFrame) -> QualityResult:
    required = ["security_id", "symbol", "exchange", "source_id", "crawled_at", "schema_version"]
    missing = [col for col in required if col not in df.columns]
    failed: list[str] = []
    warnings: list[str] = []
    duplicate_count = 0

    if missing:
        failed.append("missing_required_columns")
    else:
        if df["symbol"].isna().any() or (df["symbol"].astype(str).str.strip() == "").any():
            failed.append("symbol_missing")
        if df["security_id"].isna().any() or (df["security_id"].astype(str).str.strip() == "").any():
            failed.append("security_id_missing")
        duplicate_count = int(df.duplicated(["security_id"]).sum())
        if duplicate_count:
            failed.append("duplicate_security_id")
        bad_exchange = ~df["exchange"].fillna("UNKNOWN").isin(KNOWN_EXCHANGES)
        if bad_exchange.any():
            warnings.append("unknown_exchange_value")
        if (df["exchange"].fillna("UNKNOWN") == "UNKNOWN").any():
            warnings.append("exchange_unknown")
        for col in ["source_id", "crawled_at", "schema_version"]:
            if df[col].isna().any() or (df[col].astype(str).str.strip() == "").any():
                failed.append(f"{col}_missing")

    return QualityResult(
        table="securities",
        row_count=len(df),
        quality_status=_status(failed, warnings),
        failed_gates=sorted(set(failed)),
        warning_reasons=sorted(set(warnings)),
        duplicate_count=duplicate_count,
        missing_required_columns=missing,
    )


def check_daily_prices(df: pd.DataFrame) -> QualityResult:
    required = [
        "security_id",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source_id",
        "adjusted_close",
        "exchange",
    ]
    missing = [col for col in required if col not in df.columns]
    failed: list[str] = []
    warnings: list[str] = []
    duplicate_count = 0
    ohlc_error_count = 0

    if missing:
        failed.append("missing_required_columns")
    else:
        parsed_dates = pd.to_datetime(df["trade_date"], errors="coerce")
        if parsed_dates.isna().any():
            failed.append("trade_date_unparseable")

        for col in ["open", "high", "low", "close", "volume"]:
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.isna().any():
                failed.append(f"{col}_not_numeric")

        open_values = pd.to_numeric(df["open"], errors="coerce")
        high_values = pd.to_numeric(df["high"], errors="coerce")
        low_values = pd.to_numeric(df["low"], errors="coerce")
        close_values = pd.to_numeric(df["close"], errors="coerce")
        volume_values = pd.to_numeric(df["volume"], errors="coerce")

        ohlc_bad = (high_values < pd.concat([open_values, close_values], axis=1).max(axis=1)) | (
            low_values > pd.concat([open_values, close_values], axis=1).min(axis=1)
        )
        ohlc_error_count = int(ohlc_bad.fillna(False).sum())
        if ohlc_error_count:
            failed.append("ohlc_inconsistent")
        if (volume_values < 0).fillna(False).any():
            failed.append("volume_negative")

        duplicate_count = int(df.duplicated(["security_id", "trade_date"]).sum())
        if duplicate_count:
            failed.append("duplicate_security_id_trade_date")

        if df["source_id"].isna().any() or (df["source_id"].astype(str).str.strip() == "").any():
            failed.append("source_id_missing")

        sort_bad = False
        tmp = df.assign(_trade_date=parsed_dates)
        for _, group in tmp.groupby("security_id", dropna=False):
            if not group["_trade_date"].is_monotonic_increasing:
                sort_bad = True
                break
        if sort_bad:
            failed.append("dates_not_sorted_per_symbol")

        if df["adjusted_close"].isna().all():
            warnings.append("adjusted_close_missing_or_unclear")
        if (df["exchange"].fillna("UNKNOWN") == "UNKNOWN").any():
            warnings.append("exchange_unknown")

    return QualityResult(
        table="daily_prices",
        row_count=len(df),
        quality_status=_status(failed, warnings),
        failed_gates=sorted(set(failed)),
        warning_reasons=sorted(set(warnings)),
        duplicate_count=duplicate_count,
        ohlc_error_count=ohlc_error_count,
        missing_required_columns=missing,
    )


def check_corporate_events(df: pd.DataFrame) -> QualityResult:
    required = ["event_id", "security_id", "symbol", "source_id", "crawled_at", "schema_version"]
    missing = [col for col in required if col not in df.columns]
    failed: list[str] = []
    warnings: list[str] = []
    duplicate_count = 0

    if missing:
        failed.append("missing_required_columns")
    elif len(df):
        if df["event_id"].isna().any() or (df["event_id"].astype(str).str.strip() == "").any():
            failed.append("event_id_missing")
        duplicate_count = int(df.duplicated(["event_id"]).sum())
        if duplicate_count:
            failed.append("duplicate_event_id")
        date_cols = ["announcement_date", "ex_date", "record_date", "payment_date", "effective_date"]
        existing_date_cols = [col for col in date_cols if col in df.columns]
        if existing_date_cols and df[existing_date_cols].isna().all(axis=None):
            warnings.append("event_dates_missing")
        if "event_type" in df.columns and (df["event_type"].isna() | (df["event_type"].astype(str).str.strip() == "")).any():
            warnings.append("event_type_missing_or_unclear")

    return QualityResult(
        table="corporate_events",
        row_count=len(df),
        quality_status=_status(failed, warnings),
        failed_gates=sorted(set(failed)),
        warning_reasons=sorted(set(warnings)),
        duplicate_count=duplicate_count,
        missing_required_columns=missing,
    )
