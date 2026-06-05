from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_NAME = "vietcap_iq"
BAR_INTERVAL = "ONE_DAY"
PRICE_BASIS = "source_reported"
ADJUSTMENT_TYPE = "unknown"
PARSER_VERSION = "vietcap_iq_gap_chart_parser_v1"
SCHEMA_VERSION = "vietcap_iq_gap_chart_dry_run_v1"

REQUIRED_ARRAY_FIELDS = ["t", "o", "h", "l", "c"]
PREFERRED_ARRAY_FIELDS = ["v", "accumulatedVolume", "accumulatedValue"]

DAILY_PRICE_BARS_COLUMNS = [
    "price_bar_id",
    "symbol",
    "exchange",
    "bar_ts",
    "trading_date",
    "bar_interval",
    "price_basis",
    "adjustment_type",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "accumulated_volume",
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


@dataclass(frozen=True)
class VietcapIqGapChartParseResult:
    daily_price_bars: pd.DataFrame
    validation_summary: dict[str, Any]


def parse_vietcap_iq_gap_chart_payload(
    raw_path: str | Path,
    metadata_path: str | Path,
    symbol_override: str | None = None,
) -> VietcapIqGapChartParseResult:
    raw_path = Path(raw_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_text = raw_path.read_text(encoding="utf-8-sig")
    raw_content_hash = metadata.get("content_hash") or hashlib.sha256(raw_path.read_bytes()).hexdigest()
    source_payload_id = f"{SOURCE_NAME}:{str(raw_content_hash)[:16]}"
    payload = json.loads(raw_text)

    objects = _extract_symbol_objects(payload)
    count_back = _infer_count_back(metadata=metadata, objects=objects)
    normalized = _normalize_objects(
        objects,
        raw_content_hash=raw_content_hash,
        source_payload_id=source_payload_id,
        metadata=metadata,
        symbol_override=symbol_override,
        count_back=count_back,
    )
    validated = _validate_rows(normalized)
    summary = _build_validation_summary(
        raw_path=raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        payload=payload,
        rows=validated,
        raw_content_hash=raw_content_hash,
        count_back=count_back,
    )
    return VietcapIqGapChartParseResult(
        daily_price_bars=validated[DAILY_PRICE_BARS_COLUMNS].copy(),
        validation_summary=summary,
    )


def _extract_symbol_objects(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("Vietcap IQ gap-chart payload must be a top-level JSON array.")
    objects: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Vietcap IQ gap-chart top-level item {index} must be a JSON object.")
        missing = [field for field in ["symbol", *REQUIRED_ARRAY_FIELDS] if field not in item]
        if missing:
            raise ValueError(f"Vietcap IQ gap-chart object {index} missing required fields: {', '.join(missing)}.")
        non_arrays = [field for field in REQUIRED_ARRAY_FIELDS if not isinstance(item.get(field), list)]
        if non_arrays:
            raise ValueError(f"Vietcap IQ gap-chart object {index} fields must be arrays: {', '.join(non_arrays)}.")
        lengths = {field: len(item[field]) for field in REQUIRED_ARRAY_FIELDS}
        present_preferred = [field for field in PREFERRED_ARRAY_FIELDS if field in item]
        for field in present_preferred:
            if not isinstance(item.get(field), list):
                raise ValueError(f"Vietcap IQ gap-chart object {index} field must be an array: {field}.")
            lengths[field] = len(item[field])
        if len(set(lengths.values())) > 1:
            detail = ", ".join(f"{field}={length}" for field, length in sorted(lengths.items()))
            raise ValueError(f"Vietcap IQ gap-chart object {index} aligned array length mismatch: {detail}.")
        objects.append(item)
    return objects


def _normalize_objects(
    objects: list[dict[str, Any]],
    *,
    raw_content_hash: str,
    source_payload_id: str,
    metadata: dict[str, Any],
    symbol_override: str | None,
    count_back: int | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for object_index, item in enumerate(objects):
        symbol = _resolve_symbol(item=item, metadata=metadata, symbol_override=symbol_override)
        missing_preferred = [field for field in PREFERRED_ARRAY_FIELDS if field not in item]
        length = len(item["t"])
        for bar_index in range(length):
            row: dict[str, Any] = {
                "symbol": symbol,
                "exchange": None,
                "bar_interval": BAR_INTERVAL,
                "price_basis": PRICE_BASIS,
                "adjustment_type": ADJUSTMENT_TYPE,
                "open_price": None,
                "high_price": None,
                "low_price": None,
                "close_price": None,
                "volume": None,
                "accumulated_volume": None,
                "trading_value": None,
                "source_name": SOURCE_NAME,
                "source_row_id": make_source_row_id(SOURCE_NAME, symbol, object_index, bar_index),
                "source_payload_id": source_payload_id,
                "raw_content_hash": raw_content_hash,
                "raw_row_index": bar_index,
                "parser_version": PARSER_VERSION,
                "schema_version": SCHEMA_VERSION,
            }

            row["bar_ts"], row["trading_date"], timestamp_reason = _parse_epoch_seconds(item["t"][bar_index])
            numeric_reasons: list[str] = []
            optional_numeric_reasons: list[str] = []
            if timestamp_reason:
                numeric_reasons.append(timestamp_reason)
            for source_field, canonical_field in [
                ("o", "open_price"),
                ("h", "high_price"),
                ("l", "low_price"),
                ("c", "close_price"),
                ("v", "volume"),
                ("accumulatedVolume", "accumulated_volume"),
                ("accumulatedValue", "trading_value"),
            ]:
                if source_field not in item:
                    continue
                if source_field in {"v", "accumulatedVolume", "accumulatedValue"}:
                    value, reason = _parse_optional_numeric(item[source_field][bar_index], canonical_field)
                else:
                    value, reason = _parse_numeric(item[source_field][bar_index], canonical_field)
                row[canonical_field] = value
                if reason:
                    if source_field in {"v", "accumulatedVolume", "accumulatedValue"}:
                        optional_numeric_reasons.append(reason)
                    else:
                        numeric_reasons.append(reason)

            row["price_bar_id"] = make_price_bar_id(
                SOURCE_NAME,
                symbol,
                row["bar_ts"],
                BAR_INTERVAL,
                PRICE_BASIS,
                ADJUSTMENT_TYPE,
            )
            row["_missing_preferred_fields"] = missing_preferred
            row["_numeric_quality_reasons"] = numeric_reasons
            row["_optional_numeric_quality_reasons"] = optional_numeric_reasons
            row["_count_back"] = count_back
            rows.append(row)
    return pd.DataFrame(rows)


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    if rows.empty:
        rows["quality_status"] = []
        rows["quality_reasons"] = []
        return rows

    duplicate_mask = rows.duplicated(subset=["symbol", "bar_ts", "price_basis", "bar_interval"], keep=False)
    statuses: list[str] = []
    reasons_all: list[str] = []

    for index, row in rows.iterrows():
        fail_reasons: list[str] = []
        warn_reasons: list[str] = []

        if not _has_value(row.get("symbol")):
            fail_reasons.append("missing_required_symbol")
        if not _has_value(row.get("bar_ts")):
            fail_reasons.append("missing_required_bar_ts")
        if not _has_value(row.get("trading_date")):
            fail_reasons.append("missing_required_trading_date")

        for field in ["open_price", "high_price", "low_price", "close_price"]:
            if not _has_value(row.get(field)):
                fail_reasons.append(f"missing_required_{field}")
        for reason in row.get("_numeric_quality_reasons") or []:
            fail_reasons.append(reason)
        for reason in row.get("_optional_numeric_quality_reasons") or []:
            warn_reasons.append(reason)

        for field in row.get("_missing_preferred_fields") or []:
            warn_reasons.append(f"warning_missing_preferred_{_canonical_preferred_reason(field)}")
        for field in ["volume", "accumulated_volume", "trading_value"]:
            if not _has_value(row.get(field)):
                warn_reasons.append(f"warning_missing_{field}")

        if row.get("_count_back") == 250:
            warn_reasons.append("warning_limited_history_countback_250")

        if bool(duplicate_mask.loc[index]) and _has_value(row.get("symbol")) and _has_value(row.get("bar_ts")):
            fail_reasons.append("duplicate_symbol_bar_ts_price_basis_bar_interval")

        high_price = row.get("high_price")
        low_price = row.get("low_price")
        open_price = row.get("open_price")
        close_price = row.get("close_price")
        if _has_value(high_price) and _has_value(low_price):
            if high_price < low_price:
                fail_reasons.append("high_price_less_than_low_price")
            else:
                if _has_value(open_price) and not (low_price <= open_price <= high_price):
                    fail_reasons.append("open_price_outside_high_low")
                if _has_value(close_price) and not (low_price <= close_price <= high_price):
                    fail_reasons.append("close_price_outside_high_low")

        for field in ["volume", "accumulated_volume", "trading_value"]:
            value = row.get(field)
            if _has_value(value) and value < 0:
                fail_reasons.append(f"negative_{field}")

        if fail_reasons:
            statuses.append("fail")
        elif warn_reasons:
            statuses.append("warn")
        else:
            statuses.append("pass")
        reasons_all.append(";".join(sorted(set(fail_reasons + warn_reasons))))

    rows["quality_status"] = statuses
    rows["quality_reasons"] = reasons_all
    return rows.drop(columns=["_missing_preferred_fields", "_numeric_quality_reasons", "_optional_numeric_quality_reasons", "_count_back"])


def _build_validation_summary(
    *,
    raw_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    payload: list[Any],
    rows: pd.DataFrame,
    raw_content_hash: str,
    count_back: int | None,
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

    coverage_by_symbol: dict[str, dict[str, Any]] = {}
    if not rows.empty:
        for symbol, group in rows.groupby("symbol", dropna=False):
            key = str(symbol) if _has_value(symbol) else "UNKNOWN"
            coverage_by_symbol[key] = {
                "bar_count": int(len(group)),
                "start_trading_date": _min_non_null(group["trading_date"]),
                "end_trading_date": _max_non_null(group["trading_date"]),
                "quality_pass_count": int((group["quality_status"] == "pass").sum()),
                "quality_warn_count": int((group["quality_status"] == "warn").sum()),
                "quality_fail_count": int((group["quality_status"] == "fail").sum()),
            }

    duplicate_count = int(rows.duplicated(subset=["symbol", "bar_ts", "price_basis", "bar_interval"], keep=False).sum()) if not rows.empty else 0
    return {
        "source_name": SOURCE_NAME,
        "dataset": metadata.get("dataset", "vietcap_iq_gap_chart"),
        "raw_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "raw_content_hash": raw_content_hash,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "bar_interval": BAR_INTERVAL,
        "price_basis": PRICE_BASIS,
        "adjustment_type": ADJUSTMENT_TYPE,
        "count_back": count_back,
        "top_level_object_count": len(payload),
        "daily_price_bars_count": int(len(rows)),
        "unique_symbol_count": int(rows["symbol"].nunique(dropna=True)) if not rows.empty else 0,
        "coverage_by_symbol": coverage_by_symbol,
        "quality_pass_count": int((rows["quality_status"] == "pass").sum()) if not rows.empty else 0,
        "quality_warn_count": int((rows["quality_status"] == "warn").sum()) if not rows.empty else 0,
        "quality_fail_count": int((rows["quality_status"] == "fail").sum()) if not rows.empty else 0,
        "duplicate_symbol_bar_ts_price_basis_bar_interval_count": duplicate_count,
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "terms_notes": metadata.get("terms_notes", ""),
        "limitations": [
            "Saved-payload parser only; no live endpoint call was performed.",
            "Adjusted and unadjusted price values are not separated in the observed payload.",
            "Dividend, split, corporate-action, and adjustment-factor fields are not visible.",
            "countBack=250 is limited recent history, not full history.",
            "This dry run writes local files only; no database, migration, or backtest is performed.",
        ],
    }


def _resolve_symbol(*, item: dict[str, Any], metadata: dict[str, Any], symbol_override: str | None) -> str | None:
    raw_symbol = _clean_symbol(item.get("symbol"))
    metadata_symbol = _clean_symbol(metadata.get("symbol"))
    override_symbol = _clean_symbol(symbol_override)
    if raw_symbol:
        return raw_symbol
    if metadata_symbol and "," not in metadata_symbol:
        return metadata_symbol
    return override_symbol


def _infer_count_back(*, metadata: dict[str, Any], objects: list[dict[str, Any]]) -> int | None:
    request_params = metadata.get("request_params")
    if isinstance(request_params, dict):
        for key in ["countBack", "count_back"]:
            value = request_params.get(key)
            if _has_value(value):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
    lengths = {len(item["t"]) for item in objects if isinstance(item.get("t"), list)}
    if lengths == {250}:
        return 250
    return None


def _parse_epoch_seconds(value: Any) -> tuple[str | None, str | None, str]:
    if not _has_value(value):
        return None, None, "invalid_epoch_seconds_bar_ts"
    try:
        epoch_seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None, None, "invalid_epoch_seconds_bar_ts"
    if epoch_seconds <= 0 or epoch_seconds > 99_999_999_999:
        return None, None, "invalid_epoch_seconds_bar_ts"
    try:
        parsed = datetime.fromtimestamp(epoch_seconds, timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None, None, "invalid_epoch_seconds_bar_ts"
    return parsed.isoformat(), parsed.date().isoformat(), ""


def _parse_numeric(value: Any, canonical_field: str) -> tuple[float | None, str]:
    if not _has_value(value):
        return None, f"invalid_numeric_{canonical_field}"
    normalized = value
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "-"}:
            return None, f"invalid_numeric_{canonical_field}"
        normalized = text.replace(",", "")
    try:
        return float(normalized), ""
    except (TypeError, ValueError):
        return None, f"invalid_numeric_{canonical_field}"


def _parse_optional_numeric(value: Any, canonical_field: str) -> tuple[float | None, str]:
    if not _has_value(value):
        return None, ""
    normalized = value
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "-"}:
            return None, ""
        normalized = text.replace(",", "")
    try:
        return float(normalized), ""
    except (TypeError, ValueError):
        return None, f"warning_invalid_optional_numeric_{canonical_field}"


def _clean_symbol(value: Any) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip().upper()
    return text if text else None


def _canonical_preferred_reason(field: str) -> str:
    return {
        "v": "volume",
        "accumulatedVolume": "accumulated_volume",
        "accumulatedValue": "trading_value",
    }.get(field, field)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip() != ""


def _min_non_null(values: pd.Series) -> str | None:
    cleaned = [str(value) for value in values.dropna() if str(value).strip()]
    return min(cleaned) if cleaned else None


def _max_non_null(values: pd.Series) -> str | None:
    cleaned = [str(value) for value in values.dropna() if str(value).strip()]
    return max(cleaned) if cleaned else None


def make_price_bar_id(
    source_name: str,
    symbol: str | None,
    bar_ts: str | None,
    bar_interval: str | None,
    price_basis: str | None,
    adjustment_type: str | None,
) -> str:
    return _make_id("price_bar", source_name, symbol, bar_ts, bar_interval, price_basis, adjustment_type)


def make_source_row_id(source_name: str, symbol: str | None, object_index: int, bar_index: int) -> str:
    return _make_id("source_row", source_name, symbol, object_index, bar_index)


def _make_id(kind: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{SOURCE_NAME}:{kind}:{digest}"
