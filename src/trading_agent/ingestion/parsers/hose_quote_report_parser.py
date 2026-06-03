from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd


SOURCE_NAME = "hose"
EXCHANGE = "HOSE"
SCHEMA_VERSION = "hose_quote_report_dry_run_v1"
PARSER_VERSION = "hose_quote_report_parser_v1"
DATA_STATUS_FINAL = "final_candidate"
DATA_STATUS_PROVISIONAL = "provisional"
VALID_DATA_STATUSES = {DATA_STATUS_FINAL, DATA_STATUS_PROVISIONAL}

DAILY_PRICE_BARS_COLUMNS = [
    "price_bar_id",
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
    "source_name",
    "source_row_id",
    "source_payload_id",
    "raw_content_hash",
    "raw_row_index",
    "parser_version",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

DAILY_QUOTE_REPORTS_COLUMNS = [
    "quote_report_id",
    "symbol",
    "exchange",
    "trading_date",
    "data_status",
    "security_name",
    "isin",
    "bloomberg_id",
    "prior_close_price",
    "ceiling_price",
    "floor_price",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "average_price",
    "price_change",
    "price_change_pct",
    "matched_volume",
    "trading_value",
    "source_name",
    "source_row_id",
    "source_payload_id",
    "raw_content_hash",
    "raw_row_index",
    "parser_version",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

MARKET_OHLCV_SNAPSHOTS_COLUMNS = [
    "snapshot_id",
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
    "source_name",
    "source_row_id",
    "source_payload_id",
    "raw_content_hash",
    "raw_row_index",
    "parser_version",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

NUMERIC_FIELD_MAP = {
    "priorClosePrice": "prior_close_price",
    "openPrice": "open_price",
    "highPrice": "high_price",
    "lowPrice": "low_price",
    "closePrice": "close_price",
    "changePrice": "price_change",
    "changePriceRatio": "price_change_pct",
    "mainVolume": "matched_volume",
    "mainValue": "trading_value",
    "averagePrice": "average_price",
    "ceiling": "ceiling_price",
    "floor": "floor_price",
}


@dataclass(frozen=True)
class HoseQuoteReportParseResult:
    daily_price_bars: pd.DataFrame
    daily_quote_reports: pd.DataFrame
    market_ohlcv_snapshots: pd.DataFrame
    validation_summary: dict[str, Any]


def parse_hose_quote_report_payload(
    raw_path: str | Path,
    metadata_path: str | Path,
    data_status: str | None = None,
) -> HoseQuoteReportParseResult:
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_text = raw_path.read_text(encoding="utf-8-sig")
    raw_content_hash = metadata.get("content_hash") or hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_payload_id = f"{SOURCE_NAME}:{str(raw_content_hash)[:16]}"
    payload = json.loads(raw_text)

    rows = _extract_rows(payload)
    resolved_data_status = data_status or infer_data_status(metadata=metadata, raw_path=raw_path)
    if resolved_data_status not in VALID_DATA_STATUSES:
        raise ValueError(f"data_status must be one of {sorted(VALID_DATA_STATUSES)}.")
    trading_date = extract_trading_date(metadata)

    normalized = _normalize_rows(
        rows,
        trading_date=trading_date,
        data_status=resolved_data_status,
        raw_content_hash=raw_content_hash,
        source_payload_id=source_payload_id,
    )
    validated = _validate_rows(normalized)

    daily_price_bars = validated[DAILY_PRICE_BARS_COLUMNS].copy()
    daily_quote_reports = validated[DAILY_QUOTE_REPORTS_COLUMNS].copy()
    market_ohlcv_snapshots = validated[MARKET_OHLCV_SNAPSHOTS_COLUMNS].copy()
    summary = _build_validation_summary(
        raw_path=raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        payload=payload,
        rows=validated,
        raw_content_hash=raw_content_hash,
        trading_date=trading_date,
        data_status=resolved_data_status,
    )
    return HoseQuoteReportParseResult(
        daily_price_bars=daily_price_bars,
        daily_quote_reports=daily_quote_reports,
        market_ohlcv_snapshots=market_ohlcv_snapshots,
        validation_summary=summary,
    )


def infer_data_status(*, metadata: dict[str, Any], raw_path: str | Path | None = None) -> str:
    dataset = str(metadata.get("dataset") or "")
    if dataset == "hose_daily_quote_report_current_day":
        return DATA_STATUS_PROVISIONAL
    if dataset == "hose_daily_quote_report":
        return DATA_STATUS_FINAL
    if raw_path and "current_day" in str(raw_path):
        return DATA_STATUS_PROVISIONAL
    return DATA_STATUS_FINAL


def extract_trading_date(metadata: dict[str, Any]) -> str | None:
    endpoint = metadata.get("endpoint_or_surface") or metadata.get("url") or ""
    if endpoint:
        query = parse_qs(urlparse(str(endpoint)).query)
        values = query.get("date")
        if values:
            return _parse_iso_date(values[0])
    request_params = metadata.get("request_params")
    if isinstance(request_params, dict):
        value = request_params.get("date") or request_params.get("trading_date")
        if _has_value(value):
            return _parse_iso_date(value)
    return None


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("HOSE quote-report payload must be a JSON object.")
    if "data" not in payload or "success" not in payload or "message" not in payload:
        raise ValueError("HOSE quote-report payload must include data, success, and message.")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("HOSE quote-report payload data must be a list.")
    return [row if isinstance(row, dict) else {} for row in rows]


def _normalize_rows(
    rows: list[dict[str, Any]],
    *,
    trading_date: str | None,
    data_status: str,
    raw_content_hash: str,
    source_payload_id: str,
) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        symbol = _clean_symbol(row.get("securitySymbol"))
        source_row_id = _clean_text(row.get("id"))
        base = {
            "symbol": symbol,
            "exchange": EXCHANGE,
            "trading_date": trading_date,
            "data_status": data_status,
            "source_row_id": source_row_id,
            "security_name": _clean_text(row.get("securityName")),
            "isin": _clean_text(row.get("isin")),
            "bloomberg_id": _clean_text(row.get("bloomberg")),
            "source_name": SOURCE_NAME,
            "source_payload_id": source_payload_id,
            "raw_content_hash": raw_content_hash,
            "raw_row_index": index,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        numeric_reasons: list[str] = []
        for raw_field, canonical_field in NUMERIC_FIELD_MAP.items():
            value, reason = _parse_numeric(row.get(raw_field), canonical_field)
            base[canonical_field] = value
            if reason:
                numeric_reasons.append(reason)

        base["price_bar_id"] = make_price_bar_id(SOURCE_NAME, symbol, trading_date, data_status)
        base["quote_report_id"] = make_quote_report_id(SOURCE_NAME, symbol, trading_date, data_status, source_row_id, index)
        base["snapshot_id"] = make_snapshot_id(SOURCE_NAME, symbol, trading_date, data_status)
        base["_numeric_quality_reasons"] = numeric_reasons
        normalized.append(base)
    return pd.DataFrame(normalized)


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    if rows.empty:
        rows["quality_status"] = []
        rows["quality_reasons"] = []
        return rows

    duplicate_mask = rows.duplicated(subset=["symbol", "trading_date", "data_status"], keep=False)
    statuses: list[str] = []
    reasons_all: list[str] = []

    for index, row in rows.iterrows():
        fail_reasons: list[str] = []
        warn_reasons: list[str] = ["warning_source_units_unconfirmed"]

        if not _has_value(row.get("symbol")):
            fail_reasons.append("missing_required_symbol")
        if not _has_value(row.get("trading_date")):
            fail_reasons.append("missing_required_trading_date")
        if not _has_value(row.get("data_status")):
            fail_reasons.append("missing_required_data_status")
        elif row.get("data_status") == DATA_STATUS_PROVISIONAL:
            warn_reasons.append("warning_provisional_current_day")

        for reason in row.get("_numeric_quality_reasons") or []:
            fail_reasons.append(reason)

        if bool(duplicate_mask.loc[index]) and _has_value(row.get("symbol")):
            fail_reasons.append("duplicate_symbol_trading_date_data_status")

        no_trade_zero_ohlc = _is_no_trade_zero_ohlc(row)
        if no_trade_zero_ohlc:
            warn_reasons.append("warning_no_trade_zero_ohlc")

        high_price = row.get("high_price")
        low_price = row.get("low_price")
        open_price = row.get("open_price")
        close_price = row.get("close_price")
        ceiling_price = row.get("ceiling_price")
        floor_price = row.get("floor_price")
        matched_volume = row.get("matched_volume")
        trading_value = row.get("trading_value")

        if _has_value(high_price) and _has_value(low_price) and high_price != 0 and low_price != 0:
            if high_price < low_price:
                fail_reasons.append("high_price_less_than_low_price")
            if _has_value(close_price) and not no_trade_zero_ohlc and not (low_price <= close_price <= high_price):
                fail_reasons.append("close_price_outside_high_low")
            if _has_value(open_price) and not no_trade_zero_ohlc and not (low_price <= open_price <= high_price):
                fail_reasons.append("open_price_outside_high_low")

        if _has_value(matched_volume) and matched_volume < 0:
            fail_reasons.append("negative_matched_volume")
        if _has_value(trading_value) and trading_value < 0:
            fail_reasons.append("negative_trading_value")
        if _has_value(ceiling_price) and _has_value(floor_price) and ceiling_price < floor_price:
            fail_reasons.append("ceiling_price_less_than_floor_price")

        if fail_reasons:
            statuses.append("fail")
        elif warn_reasons:
            statuses.append("warn")
        else:
            statuses.append("pass")
        reasons_all.append(";".join(sorted(set(fail_reasons + warn_reasons))))

    rows["quality_status"] = statuses
    rows["quality_reasons"] = reasons_all
    return rows.drop(columns=["_numeric_quality_reasons"])


def _build_validation_summary(
    *,
    raw_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    payload: dict[str, Any],
    rows: pd.DataFrame,
    raw_content_hash: str,
    trading_date: str | None,
    data_status: str,
) -> dict[str, Any]:
    fail_count = int((rows["quality_status"] == "fail").sum()) if not rows.empty else 0
    warn_count = int((rows["quality_status"] == "warn").sum()) if not rows.empty else 0
    pass_count = int((rows["quality_status"] == "pass").sum()) if not rows.empty else 0
    reason_counts: dict[str, int] = {}
    warning_reason_counts: dict[str, int] = {}
    failure_reason_counts: dict[str, int] = {}
    if not rows.empty:
        for value in rows["quality_reasons"].dropna():
            for reason in str(value).split(";"):
                if reason:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                    if reason.startswith("warning_"):
                        warning_reason_counts[reason] = warning_reason_counts.get(reason, 0) + 1
                    else:
                        failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1

    duplicate_count = int(rows.duplicated(subset=["symbol", "trading_date", "data_status"], keep=False).sum()) if not rows.empty else 0
    return {
        "source_name": SOURCE_NAME,
        "dataset": metadata.get("dataset", "hose_daily_quote_report"),
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "success": payload.get("success"),
        "message": payload.get("message"),
        "trading_date": trading_date,
        "data_status": data_status,
        "json_row_count": len(payload.get("data", [])) if isinstance(payload.get("data"), list) else None,
        "daily_price_bars_count": int(len(rows)),
        "daily_quote_reports_count": int(len(rows)),
        "market_ohlcv_snapshots_count": int(len(rows)),
        "quality_pass_count": pass_count,
        "quality_warn_count": warn_count,
        "quality_fail_count": fail_count,
        "duplicate_symbol_trading_date_data_status_count": duplicate_count,
        "row_count_matches_json_data": int(len(rows)) == len(payload.get("data", [])) if isinstance(payload.get("data"), list) else False,
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "terms_notes": metadata.get("terms_notes", ""),
        "limitations": [
            "Source units are not fully confirmed.",
            "Final EOD semantics are not fully confirmed.",
            "tradingBy=VNINDEX coverage is not fully confirmed.",
            "This dry run writes local files only; no database or backtest is performed.",
        ],
    }


def _parse_numeric(value: Any, canonical_field: str) -> tuple[float | None, str]:
    if not _has_value(value):
        return None, ""
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "-"}:
            return None, ""
        normalized = text.replace(",", "")
    else:
        normalized = value
    try:
        return float(normalized), ""
    except (TypeError, ValueError):
        return None, f"invalid_numeric_{canonical_field}"


def _clean_text(value: Any) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip()
    if text in {"", "-"}:
        return None
    return text


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _parse_iso_date(value: Any) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _is_no_trade_zero_ohlc(row: pd.Series) -> bool:
    zero_fields = ["open_price", "high_price", "low_price", "average_price"]
    if not all(_has_value(row.get(column)) and row.get(column) == 0 for column in zero_fields):
        return False
    return _has_value(row.get("close_price")) and _has_value(row.get("prior_close_price")) and row["close_price"] == row["prior_close_price"]


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return str(value).strip() != ""


def make_price_bar_id(source_name: str, symbol: str | None, trading_date: str | None, data_status: str | None) -> str:
    return _make_id("price_bar", source_name, symbol, trading_date, data_status)


def make_quote_report_id(
    source_name: str,
    symbol: str | None,
    trading_date: str | None,
    data_status: str | None,
    source_row_id: str | None,
    raw_row_index: int,
) -> str:
    return _make_id("quote_report", source_name, symbol, trading_date, data_status, source_row_id or str(raw_row_index))


def make_snapshot_id(source_name: str, symbol: str | None, trading_date: str | None, data_status: str | None) -> str:
    return _make_id("snapshot", source_name, symbol, trading_date, data_status)


def _make_id(kind: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{SOURCE_NAME}:{kind}:{digest}"
