from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_agent.ingestion.adjustment_factors import (
    AdjustmentFactorRecord,
    normalize_adjusted_close_factor,
    normalize_corporate_action_factor,
)


@dataclass(frozen=True)
class AdjustmentFactorSourceResult:
    status: str
    source_id: str | None
    raw_path: str | None
    method: str
    records: tuple[AdjustmentFactorRecord, ...]
    reasons: tuple[str, ...]
    network_request_made: bool = False
    db_mutation_made: bool = False
    adjusted_ohlc_populated: bool = False


def parse_adjustment_factor_payload(
    payload: Any,
    *,
    source_id: str | None,
    raw_path: str | None,
    method: str,
) -> AdjustmentFactorSourceResult:
    if method == "adjusted_close_ratio":
        return build_factor_records_from_adjusted_close_payload(
            payload,
            source_id=source_id,
            raw_path=raw_path,
        )
    if method == "corporate_action_derived":
        return build_factor_records_from_corporate_action_payload(
            payload,
            source_id=source_id,
            raw_path=raw_path,
        )
    return AdjustmentFactorSourceResult(
        status="invalid",
        source_id=_clean_optional(source_id),
        raw_path=_clean_optional(raw_path),
        method=method,
        records=(),
        reasons=(f"unsupported_factor_source_method:{method}",),
    )


def build_factor_records_from_adjusted_close_payload(
    payload: Any,
    *,
    source_id: str | None,
    raw_path: str | None,
) -> AdjustmentFactorSourceResult:
    rows = _payload_rows(payload)
    records = tuple(
        normalize_adjusted_close_factor(
            symbol=str(row.get("symbol") or ""),
            trade_date=str(row.get("trade_date") or ""),
            raw_close=row.get("close"),
            adjusted_close=row.get("adjusted_close"),
            source_id=source_id,
            raw_path=raw_path,
        )
        for row in rows
    )
    return _result(
        source_id=source_id,
        raw_path=raw_path,
        method="adjusted_close_ratio",
        records=records,
        payload_rows=len(rows),
    )


def build_factor_records_from_corporate_action_payload(
    payload: Any,
    *,
    source_id: str | None,
    raw_path: str | None,
) -> AdjustmentFactorSourceResult:
    rows = _payload_rows(payload)
    records = tuple(
        normalize_corporate_action_factor(
            symbol=str(row.get("symbol") or ""),
            trade_date=str(row.get("trade_date") or row.get("ex_date") or ""),
            factor=row.get("factor"),
            source_id=source_id,
            raw_path=raw_path,
        )
        for row in rows
    )
    return _result(
        source_id=source_id,
        raw_path=raw_path,
        method="corporate_action_derived",
        records=records,
        payload_rows=len(rows),
    )


def _result(
    *,
    source_id: str | None,
    raw_path: str | None,
    method: str,
    records: tuple[AdjustmentFactorRecord, ...],
    payload_rows: int,
) -> AdjustmentFactorSourceResult:
    reasons: list[str] = []
    if payload_rows == 0:
        reasons.append("payload_rows_missing")
    invalid_records = [record for record in records if record.status != "ok"]
    if invalid_records:
        reasons.append(f"{len(invalid_records)} factor records are not usable.")
    return AdjustmentFactorSourceResult(
        status="ok" if records and not reasons else "not_ready",
        source_id=_clean_optional(source_id),
        raw_path=_clean_optional(raw_path),
        method=method,
        records=records,
        reasons=tuple(reasons),
    )


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return [payload]
    return []


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
