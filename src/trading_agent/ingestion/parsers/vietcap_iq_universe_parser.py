from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_NAME = "vietcap_iq"
SCHEMA_VERSION = "vietcap_iq_universe_dry_run_v1"
PARSER_VERSION = "vietcap_iq_universe_parser_v1"

SECURITIES_MASTER_COLUMNS = [
    "security_id",
    "symbol",
    "company_name",
    "short_name",
    "tax_code",
    "organ_code",
    "is_bank",
    "is_index",
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

EXCHANGE_LISTINGS_COLUMNS = [
    "listing_id",
    "security_id",
    "symbol",
    "exchange_or_floor",
    "floor_raw",
    "company_type_code",
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

SYMBOL_UNIVERSE_COLUMNS = [
    "universe_row_id",
    "symbol",
    "exchange_or_floor",
    "display_name",
    "company_name",
    "short_name",
    "company_type_code",
    "is_bank",
    "is_index",
    "active_status_candidate",
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

INSTRUMENT_UNIVERSE_COLUMNS = [
    "instrument_id",
    "symbol",
    "exchange_or_floor",
    "company_type_code",
    "is_bank",
    "is_index",
    "bank_raw",
    "index_raw",
    "icb_lv1_raw",
    "icb_lv2_raw",
    "icb_lv3_raw",
    "icb_lv4_raw",
    "current_price",
    "target_price",
    "upside_to_tp_pct",
    "projected_tsr_pct",
    "dividend_per_share_tsr",
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
    "currentPrice": "current_price",
    "targetPrice": "target_price",
    "upsideToTpPercentage": "upside_to_tp_pct",
    "projectedTsrPercentage": "projected_tsr_pct",
    "dividendPerShareTsr": "dividend_per_share_tsr",
}

SPECIAL_FLOORS = {"OTC", "OTHER", "STOP"}


@dataclass(frozen=True)
class VietcapIqUniverseParseResult:
    securities_master: pd.DataFrame
    exchange_listings: pd.DataFrame
    symbol_universe: pd.DataFrame
    instrument_universe: pd.DataFrame
    validation_summary: dict[str, Any]


def parse_vietcap_iq_universe_payload(raw_path: str | Path, metadata_path: str | Path) -> VietcapIqUniverseParseResult:
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_content_hash = metadata.get("content_hash") or hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_payload_id = f"{SOURCE_NAME}:{str(raw_content_hash)[:16]}"
    payload = json.loads(raw_path.read_text(encoding="utf-8-sig"))

    rows = _extract_rows(payload)
    normalized = _normalize_rows(rows, raw_content_hash=raw_content_hash, source_payload_id=source_payload_id)
    validated = _validate_rows(normalized)
    summary = _build_validation_summary(
        raw_path=raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        payload=payload,
        rows=validated,
        raw_content_hash=raw_content_hash,
    )
    return VietcapIqUniverseParseResult(
        securities_master=validated[SECURITIES_MASTER_COLUMNS].copy(),
        exchange_listings=validated[EXCHANGE_LISTINGS_COLUMNS].copy(),
        symbol_universe=validated[SYMBOL_UNIVERSE_COLUMNS].copy(),
        instrument_universe=validated[INSTRUMENT_UNIVERSE_COLUMNS].copy(),
        validation_summary=summary,
    )


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Vietcap IQ universe payload must be a JSON object.")
    required = ["serverDateTime", "traceId", "status", "code", "msg", "exception", "successful", "data"]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Vietcap IQ universe payload missing top-level fields: {', '.join(missing)}.")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("Vietcap IQ universe payload data must be a list.")
    return [row if isinstance(row, dict) else {} for row in rows]


def _normalize_rows(rows: list[dict[str, Any]], *, raw_content_hash: str, source_payload_id: str) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        symbol = _clean_symbol(row.get("code"))
        exchange_or_floor = _clean_symbol(row.get("floor"))
        source_row_id = _clean_text(row.get("id"))
        company_name = _clean_text(row.get("name"))
        short_name = _clean_text(row.get("shortName"))
        company_type_code = _clean_symbol(row.get("comTypeCode"))
        numeric_reasons: list[str] = []

        base: dict[str, Any] = {
            "security_id": make_security_id(SOURCE_NAME, symbol),
            "listing_id": make_listing_id(SOURCE_NAME, symbol, exchange_or_floor),
            "universe_row_id": make_universe_row_id(SOURCE_NAME, symbol, exchange_or_floor),
            "instrument_id": make_instrument_id(SOURCE_NAME, symbol, exchange_or_floor, source_row_id, index),
            "symbol": symbol,
            "company_name": company_name,
            "security_name": company_name,
            "short_name": short_name,
            "display_name": short_name or company_name,
            "exchange_or_floor": exchange_or_floor,
            "floor_raw": _clean_text(row.get("floor")),
            "tax_code": _clean_text(row.get("tax")),
            "organ_code": _clean_text(row.get("organCode")),
            "phone": _clean_text(row.get("phone")),
            "fax": _clean_text(row.get("fax")),
            "logo_url": _clean_text(row.get("logoUrl")),
            "company_type_code": company_type_code,
            "instrument_type_code": company_type_code,
            "is_bank": _clean_bool(row.get("isBank")),
            "is_index": _clean_bool(row.get("isIndex")),
            "bank_raw": _json_or_scalar(row.get("bank")),
            "index_raw": _json_or_scalar(row.get("index")),
            "icb_lv1_raw": _json_or_scalar(row.get("icbLv1")),
            "icb_lv2_raw": _json_or_scalar(row.get("icbLv2")),
            "icb_lv3_raw": _json_or_scalar(row.get("icbLv3")),
            "icb_lv4_raw": _json_or_scalar(row.get("icbLv4")),
            "active_status_candidate": False if exchange_or_floor == "STOP" else None,
            "source_name": SOURCE_NAME,
            "source_row_id": source_row_id,
            "source_payload_id": source_payload_id,
            "raw_content_hash": raw_content_hash,
            "raw_row_index": index,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        for raw_field, canonical_field in NUMERIC_FIELD_MAP.items():
            value, reason = _parse_optional_numeric(row.get(raw_field), canonical_field)
            base[canonical_field] = value
            if reason:
                numeric_reasons.append(reason)
        base["_numeric_quality_reasons"] = numeric_reasons
        normalized.append(base)
    return pd.DataFrame(normalized)


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    if rows.empty:
        rows["quality_status"] = []
        rows["quality_reasons"] = []
        return rows

    duplicate_symbol_floor = rows.duplicated(subset=["symbol", "exchange_or_floor"], keep=False)
    duplicate_source_row_id = rows["source_row_id"].notna() & rows.duplicated(subset=["source_row_id"], keep=False)
    statuses: list[str] = []
    reasons_all: list[str] = []

    for index, row in rows.iterrows():
        fail_reasons: list[str] = []
        warn_reasons: list[str] = []

        if not _has_value(row.get("symbol")):
            fail_reasons.append("missing_required_symbol")
        if not _has_value(row.get("company_name")) and not _has_value(row.get("short_name")):
            fail_reasons.append("missing_required_company_name_or_short_name")
        elif not _has_value(row.get("company_name")):
            warn_reasons.append("warning_missing_company_name")
        if not _has_value(row.get("exchange_or_floor")):
            fail_reasons.append("missing_required_exchange_or_floor")

        if bool(duplicate_symbol_floor.loc[index]) and _has_value(row.get("symbol")) and _has_value(row.get("exchange_or_floor")):
            fail_reasons.append("duplicate_symbol_exchange_or_floor")
        if bool(duplicate_source_row_id.loc[index]):
            warn_reasons.append("warning_duplicate_source_row_id")

        exchange_or_floor = row.get("exchange_or_floor")
        if exchange_or_floor == "STOP":
            warn_reasons.append("warning_stop_floor_status_candidate")
        if exchange_or_floor in SPECIAL_FLOORS:
            warn_reasons.append("warning_non_listed_or_special_floor_candidate")
        if row.get("is_index") is True:
            warn_reasons.append("warning_non_stock_index_candidate")

        warn_reasons.extend(row.get("_numeric_quality_reasons") or [])

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
) -> dict[str, Any]:
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

    floor_counts = {}
    if "exchange_or_floor" in rows:
        floor_counts = {str(key): int(value) for key, value in rows["exchange_or_floor"].fillna("UNKNOWN").value_counts().sort_index().items()}

    return {
        "source_name": SOURCE_NAME,
        "dataset": metadata.get("dataset", "vietcap_iq_company_search_bar"),
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "serverDateTime": payload.get("serverDateTime"),
        "traceId": payload.get("traceId"),
        "status": payload.get("status"),
        "code": payload.get("code"),
        "successful": payload.get("successful"),
        "json_row_count": int(len(payload.get("data", []))) if isinstance(payload.get("data"), list) else None,
        "securities_master_count": int(len(rows)),
        "exchange_listings_count": int(len(rows)),
        "symbol_universe_count": int(len(rows)),
        "instrument_universe_count": int(len(rows)),
        "unique_symbol_count": int(rows["symbol"].nunique(dropna=True)) if not rows.empty else 0,
        "floor_counts": floor_counts,
        "quality_pass_count": int((rows["quality_status"] == "pass").sum()) if not rows.empty else 0,
        "quality_warn_count": int((rows["quality_status"] == "warn").sum()) if not rows.empty else 0,
        "quality_fail_count": int((rows["quality_status"] == "fail").sum()) if not rows.empty else 0,
        "duplicate_symbol_exchange_or_floor_count": int(rows.duplicated(subset=["symbol", "exchange_or_floor"], keep=False).sum()) if not rows.empty else 0,
        "duplicate_source_row_id_count": int((rows["source_row_id"].notna() & rows.duplicated(subset=["source_row_id"], keep=False)).sum()) if not rows.empty else 0,
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "terms_notes": metadata.get("terms_notes", ""),
        "limitations": [
            "This is a dry run only. No database write or migration was performed.",
            "Vietcap IQ field semantics for floor, comTypeCode, inCu, bank, index, and icbLv* need review before canonical promotion.",
            "Rows are not filtered; index, OTC, OTHER, and STOP candidates are preserved with warnings.",
        ],
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


def _clean_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _parse_optional_numeric(value: Any, canonical_field: str) -> tuple[float | None, str]:
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
        return None, f"warning_invalid_optional_numeric_{canonical_field}"


def _json_or_scalar(value: Any) -> str | None:
    if not _has_value(value):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip() != ""


def make_security_id(source_name: str, symbol: str | None) -> str | None:
    if not _has_value(symbol):
        return None
    return f"{source_name}:{symbol}"


def make_listing_id(source_name: str, symbol: str | None, exchange_or_floor: str | None) -> str:
    return _make_id("listing", source_name, symbol, exchange_or_floor)


def make_universe_row_id(source_name: str, symbol: str | None, exchange_or_floor: str | None) -> str:
    return _make_id("universe", source_name, symbol, exchange_or_floor)


def make_instrument_id(source_name: str, symbol: str | None, exchange_or_floor: str | None, source_row_id: str | None, raw_row_index: int) -> str:
    return _make_id("instrument", source_name, symbol, exchange_or_floor, source_row_id or str(raw_row_index))


def _make_id(kind: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{SOURCE_NAME}:{kind}:{digest}"
