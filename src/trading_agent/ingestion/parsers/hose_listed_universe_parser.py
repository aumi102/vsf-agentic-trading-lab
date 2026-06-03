from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_NAME = "hose"
EXCHANGE = "HOSE"
SCHEMA_VERSION = "hose_listed_universe_dry_run_v1"
PARSER_VERSION = "hose_listed_universe_parser_v1"

SECURITIES_MASTER_COLUMNS = [
    "security_id",
    "source_security_id",
    "symbol",
    "exchange",
    "company_name",
    "short_name",
    "isin",
    "bloomberg_id",
    "charter_capital_vnd",
    "par_value_vnd",
    "outstanding_volume",
    "adjusted_outstanding_volume",
    "treasury_volume",
    "foreign_owned_ratio_pct",
    "state_owned_ratio_pct",
    "source_name",
    "source_payload_id",
    "raw_content_hash",
    "raw_row_index",
    "parser_version",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

EXCHANGE_LISTINGS_COLUMNS = [
    "listing_id",
    "security_id",
    "symbol",
    "exchange",
    "security_type_code",
    "listing_status_id",
    "registration_date",
    "first_trading_date",
    "acceptance_date",
    "listing_date",
    "listed_volume",
    "listed_value_vnd",
    "source_name",
    "source_payload_id",
    "raw_content_hash",
    "raw_row_index",
    "parser_version",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

SYMBOL_UNIVERSE_COLUMNS = [
    "universe_row_id",
    "symbol",
    "exchange",
    "display_text",
    "company_name",
    "security_type_code",
    "listing_status_id",
    "is_active_candidate",
    "source_name",
    "source_payload_id",
    "raw_content_hash",
    "raw_row_index",
    "parser_version",
    "schema_version",
    "quality_status",
    "quality_reasons",
]

INTEGER_FIELDS = [
    "capital",
    "parValue",
    "listingVolume",
    "listingValue",
    "outStanding",
    "adjOutStanding",
    "treasuryVol",
]
RATIO_FIELDS = ["foreignOwnedRatio", "stateOwnedRatio"]
DATE_FIELDS = {
    "regDate": "registration_date",
    "ftdate": "first_trading_date",
    "acceptDate": "acceptance_date",
    "listDate": "listing_date",
}


@dataclass(frozen=True)
class HoseListedUniverseParseResult:
    securities_master: pd.DataFrame
    exchange_listings: pd.DataFrame
    symbol_universe: pd.DataFrame
    validation_summary: dict[str, Any]


def parse_hose_listed_universe_payload(raw_path: str | Path, metadata_path: str | Path) -> HoseListedUniverseParseResult:
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_text = raw_path.read_text(encoding="utf-8")
    raw_content_hash = metadata.get("content_hash") or hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_payload_id = f"{SOURCE_NAME}:{str(raw_content_hash)[:16]}"
    payload = json.loads(raw_text)

    rows, paging = _extract_shape(payload)
    normalized = _normalize_rows(rows, raw_content_hash=raw_content_hash, source_payload_id=source_payload_id)
    validated = _validate_rows(normalized)

    securities_master = validated[SECURITIES_MASTER_COLUMNS].copy()
    exchange_listings = validated[EXCHANGE_LISTINGS_COLUMNS].copy()
    symbol_universe = validated[SYMBOL_UNIVERSE_COLUMNS].copy()
    summary = _build_validation_summary(
        raw_path=raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        payload=payload,
        paging=paging,
        rows=validated,
        raw_content_hash=raw_content_hash,
    )
    return HoseListedUniverseParseResult(
        securities_master=securities_master,
        exchange_listings=exchange_listings,
        symbol_universe=symbol_universe,
        validation_summary=summary,
    )


def _extract_shape(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("HOSE listed universe payload must be a JSON object.")
    if "data" not in payload or "success" not in payload or "message" not in payload:
        raise ValueError("HOSE listed universe payload must include data, success, and message.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("HOSE listed universe payload data must be an object.")
    rows = data.get("list")
    paging = data.get("paging")
    if not isinstance(rows, list):
        raise ValueError("HOSE listed universe payload data.list must be a list.")
    if not isinstance(paging, dict):
        raise ValueError("HOSE listed universe payload data.paging must be an object.")
    normalized_rows = [row if isinstance(row, dict) else {} for row in rows]
    return normalized_rows, paging


def _normalize_rows(rows: list[dict[str, Any]], *, raw_content_hash: str, source_payload_id: str) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        symbol = _clean_symbol(row.get("code"))
        company_name = _clean_text(row.get("name"))
        security_id = f"{SOURCE_NAME}:{symbol}" if _has_value(symbol) else None
        source_security_id = _clean_integer(row.get("id"))
        date_values: dict[str, Any] = {}
        date_reasons: list[str] = []
        for raw_field, canonical_field in DATE_FIELDS.items():
            parsed, reason = _parse_epoch_date(row.get(raw_field), raw_field)
            date_values[canonical_field] = parsed
            if reason:
                date_reasons.append(reason)

        listed_volume = _clean_integer(row.get("listingVolume"))
        outstanding_volume = _clean_integer(row.get("outStanding"))
        security_type_code = _clean_integer(row.get("securitiesType"))
        listing_status_id = _clean_integer(row.get("listingStatusId"))
        base = {
            "security_id": security_id,
            "source_security_id": source_security_id,
            "symbol": symbol,
            "exchange": EXCHANGE,
            "company_name": company_name,
            "short_name": _clean_text(row.get("brief")),
            "isin": _clean_text(row.get("isin")),
            "bloomberg_id": _clean_text(row.get("bloomberg")),
            "charter_capital_vnd": _clean_integer(row.get("capital")),
            "par_value_vnd": _clean_integer(row.get("parValue")),
            "outstanding_volume": outstanding_volume,
            "adjusted_outstanding_volume": _clean_integer(row.get("adjOutStanding")),
            "treasury_volume": _clean_integer(row.get("treasuryVol")),
            "foreign_owned_ratio_pct": _clean_float(row.get("foreignOwnedRatio")),
            "state_owned_ratio_pct": _clean_float(row.get("stateOwnedRatio")),
            "listing_id": _make_listing_id(symbol, source_payload_id, index),
            "security_type_code": security_type_code,
            "listing_status_id": listing_status_id,
            "listed_volume": listed_volume,
            "listed_value_vnd": _clean_integer(row.get("listingValue")),
            "universe_row_id": _make_universe_row_id(symbol, source_payload_id, index),
            "display_text": _clean_text(row.get("displayText")),
            "is_active_candidate": listing_status_id == 11 if listing_status_id is not None else None,
            "source_name": SOURCE_NAME,
            "source_payload_id": source_payload_id,
            "raw_content_hash": raw_content_hash,
            "raw_row_index": index,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "_date_quality_reasons": date_reasons,
        }
        base.update(date_values)
        normalized.append(base)
    return pd.DataFrame(normalized)


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    if rows.empty:
        rows["quality_status"] = []
        rows["quality_reasons"] = []
        return rows

    duplicate_symbol_mask = rows.duplicated(subset=["symbol"], keep=False)
    statuses: list[str] = []
    reasons_all: list[str] = []

    for index, row in rows.iterrows():
        fail_reasons: list[str] = []
        warn_reasons: list[str] = []

        if not _has_value(row["symbol"]):
            fail_reasons.append("missing_required_symbol")
        if not _has_value(row["company_name"]):
            warn_reasons.append("warning_missing_company_name")
        if bool(duplicate_symbol_mask.loc[index]) and _has_value(row["symbol"]):
            fail_reasons.append("duplicate_symbol_in_page_sample")

        isin = row.get("isin")
        if _has_value(isin) and not _valid_isin(str(isin)):
            warn_reasons.append("warning_invalid_isin")

        for column in [
            "charter_capital_vnd",
            "par_value_vnd",
            "outstanding_volume",
            "adjusted_outstanding_volume",
            "treasury_volume",
            "listed_volume",
            "listed_value_vnd",
        ]:
            if _has_value(row.get(column)) and row[column] < 0:
                fail_reasons.append(f"negative_{column}")

        if _has_value(row.get("listed_volume")) and _has_value(row.get("outstanding_volume")):
            if row["listed_volume"] < row["outstanding_volume"]:
                warn_reasons.append("warning_listed_volume_less_than_outstanding_volume")

        warn_reasons.extend(row.get("_date_quality_reasons") or [])

        if fail_reasons:
            statuses.append("fail")
        elif warn_reasons:
            statuses.append("warn")
        else:
            statuses.append("pass")
        reasons_all.append(";".join(sorted(set(fail_reasons + warn_reasons))))

    rows["quality_status"] = statuses
    rows["quality_reasons"] = reasons_all
    return rows.drop(columns=["_date_quality_reasons"])


def _build_validation_summary(
    *,
    raw_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    payload: dict[str, Any],
    paging: dict[str, Any],
    rows: pd.DataFrame,
    raw_content_hash: str,
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
    return {
        "source_name": SOURCE_NAME,
        "dataset": metadata.get("dataset", "hose_listed_stock_universe"),
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "success": payload.get("success"),
        "message": payload.get("message"),
        "page_index": _clean_integer(paging.get("pageIndex")),
        "page_size": _clean_integer(paging.get("pageSize")),
        "total_count": _clean_integer(paging.get("totalCount")),
        "total_pages": _clean_integer(paging.get("totalPages")),
        "page_row_count": int(len(rows)),
        "securities_master_count": int(len(rows)),
        "exchange_listings_count": int(len(rows)),
        "symbol_universe_count": int(len(rows)),
        "quality_pass_count": pass_count,
        "quality_warn_count": warn_count,
        "quality_fail_count": fail_count,
        "duplicate_symbol_count": int(rows.duplicated(subset=["symbol"], keep=False).sum()) if not rows.empty else 0,
        "page_only_limitation": "This dry run parses only the saved page-1 sample, not all HOSE pages.",
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "terms_notes": metadata.get("terms_notes", ""),
    }


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


def _clean_integer(value: Any) -> int | None:
    if not _has_value(value):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in {"", "-"}:
            return None
    else:
        text = value
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _clean_float(value: Any) -> float | None:
    if not _has_value(value):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in {"", "-"}:
            return None
    else:
        text = value
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_epoch_date(value: Any, raw_field: str) -> tuple[str | None, str | None]:
    if not _has_value(value):
        return None, ""
    epoch = _clean_integer(value)
    if epoch is None:
        return None, f"invalid_date_{raw_field}"
    if epoch < 0:
        return None, f"warning_sentinel_date_{raw_field}"
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat(), ""
    except (OverflowError, OSError, ValueError):
        return None, f"invalid_date_{raw_field}"


def _valid_isin(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", value.strip().upper()))


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return str(value).strip() != ""


def _make_listing_id(symbol: str | None, source_payload_id: str, raw_row_index: int) -> str:
    return _make_id("listing", symbol, source_payload_id, raw_row_index)


def _make_universe_row_id(symbol: str | None, source_payload_id: str, raw_row_index: int) -> str:
    return _make_id("universe", symbol, source_payload_id, raw_row_index)


def _make_id(kind: str, symbol: str | None, source_payload_id: str, raw_row_index: int) -> str:
    parts = [SOURCE_NAME, kind, str(symbol or ""), source_payload_id, str(raw_row_index)]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{SOURCE_NAME}:{kind}:{digest}"
