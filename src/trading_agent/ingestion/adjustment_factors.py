from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


FACTOR_METHODS = frozenset({"adjusted_close_ratio", "corporate_action_derived", "unknown"})
STATUS_RANK = {"ok": 0, "missing": 1, "invalid": 2}


@dataclass(frozen=True)
class AdjustmentFactorRecord:
    symbol: str
    trade_date: str
    factor: float | None
    source_id: str | None
    method: str
    raw_path: str | None
    status: str
    reasons: tuple[str, ...]


def normalize_adjusted_close_factor(
    *,
    symbol: str,
    trade_date: str,
    raw_close: float | int | str | None,
    adjusted_close: float | int | str | None,
    source_id: str | None,
    raw_path: str | None,
) -> AdjustmentFactorRecord:
    close_value = _to_float(raw_close)
    adjusted_value = _to_float(adjusted_close)
    reasons: list[str] = []

    if close_value is None:
        reasons.append("raw_close_missing_or_non_finite")
    elif close_value <= 0:
        reasons.append("raw_close_must_be_positive")

    if adjusted_value is None:
        reasons.append("adjusted_close_missing")
        factor = None
    elif adjusted_value <= 0:
        reasons.append("adjusted_close_must_be_positive")
        factor = None
    elif close_value is None or close_value <= 0:
        factor = None
    else:
        factor = adjusted_value / close_value
        if factor <= 0 or not math.isfinite(factor):
            reasons.append("factor_must_be_positive_and_finite")
            factor = None

    return _record(
        symbol=symbol,
        trade_date=trade_date,
        factor=factor,
        source_id=source_id,
        raw_path=raw_path,
        method="adjusted_close_ratio",
        reasons=reasons,
        missing_status="missing" if adjusted_value is None else "invalid",
    )


def normalize_corporate_action_factor(
    *,
    symbol: str,
    trade_date: str,
    factor: float | int | str | None,
    source_id: str | None,
    raw_path: str | None,
) -> AdjustmentFactorRecord:
    factor_value = _to_float(factor)
    reasons: list[str] = []
    missing_status = "invalid"
    if factor_value is None:
        reasons.append("factor_missing_or_non_finite")
        missing_status = "missing"
    elif factor_value <= 0:
        reasons.append("factor_must_be_positive")
        factor_value = None

    return _record(
        symbol=symbol,
        trade_date=trade_date,
        factor=factor_value,
        source_id=source_id,
        raw_path=raw_path,
        method="corporate_action_derived",
        reasons=reasons,
        missing_status=missing_status,
    )


def make_adjustment_factor_record(
    *,
    symbol: str,
    trade_date: str,
    factor: float | int | str | None,
    source_id: str | None,
    method: str,
    raw_path: str | None,
    status: str,
    reasons: Iterable[str] = (),
) -> AdjustmentFactorRecord:
    if method not in FACTOR_METHODS:
        raise ValueError(f"Unsupported adjustment factor method: {method}")
    normalized_symbol = _normalize_symbol(symbol)
    normalized_trade_date = str(trade_date or "").strip()
    if not normalized_symbol:
        raise ValueError("Adjustment factor symbol is required.")
    if not normalized_trade_date:
        raise ValueError("Adjustment factor trade_date is required.")

    factor_value = _to_float(factor)
    normalized_reasons = _normalize_reasons(reasons)
    if factor_value is not None and factor_value <= 0:
        normalized_reasons = _normalize_reasons([*normalized_reasons, "factor_must_be_positive"])
        factor_value = None
        status = "invalid"
    if status not in STATUS_RANK:
        raise ValueError(f"Unsupported adjustment factor status: {status}")
    if status == "ok":
        ok_errors = []
        if method == "unknown":
            ok_errors.append("method_cannot_be_unknown")
        if factor_value is None or factor_value <= 0:
            ok_errors.append("factor_must_be_positive")
        if not _clean_optional(source_id):
            ok_errors.append("source_id_required")
        if not _clean_optional(raw_path):
            ok_errors.append("raw_path_required")
        if normalized_reasons:
            ok_errors.append("ok_record_cannot_have_reasons")
        if ok_errors:
            raise ValueError(f"Invalid ok adjustment factor record: {', '.join(ok_errors)}")
    return AdjustmentFactorRecord(
        symbol=normalized_symbol,
        trade_date=normalized_trade_date,
        factor=factor_value,
        source_id=_clean_optional(source_id),
        method=method,
        raw_path=_clean_optional(raw_path),
        status=status,
        reasons=normalized_reasons,
    )


def merge_factor_records(records: Iterable[AdjustmentFactorRecord]) -> list[AdjustmentFactorRecord]:
    best: dict[tuple[str, str, str], AdjustmentFactorRecord] = {}
    for record in records:
        key = (record.symbol, record.trade_date, record.method)
        existing = best.get(key)
        if existing is None or _record_sort_key(record) < _record_sort_key(existing):
            best[key] = record
    return sorted(best.values(), key=lambda item: (item.symbol, item.trade_date, item.method))


def _record(
    *,
    symbol: str,
    trade_date: str,
    factor: float | None,
    source_id: str | None,
    raw_path: str | None,
    method: str,
    reasons: list[str],
    missing_status: str,
) -> AdjustmentFactorRecord:
    if factor is None and not reasons:
        reasons.append("factor_missing")
    if factor is not None:
        if not _clean_optional(source_id):
            reasons.append("source_id_required")
        if not _clean_optional(raw_path):
            reasons.append("raw_path_required")

    status = "ok" if factor is not None and not reasons else missing_status
    if factor is not None and reasons:
        status = "invalid"
    return make_adjustment_factor_record(
        symbol=symbol,
        trade_date=trade_date,
        factor=factor,
        source_id=source_id,
        method=method,
        raw_path=raw_path,
        status=status,
        reasons=reasons,
    )


def _record_sort_key(record: AdjustmentFactorRecord) -> tuple[int, int, str]:
    source_score = 0 if record.source_id and record.raw_path else 1
    return (STATUS_RANK[record.status], source_score, "|".join(record.reasons))


def _normalize_symbol(value: str) -> str:
    return str(value or "").strip().upper()


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_reasons(reasons: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(reason).strip() for reason in reasons if str(reason).strip()}))


def _to_float(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result
