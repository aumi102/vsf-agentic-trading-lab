from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from trading_agent.ingestion.adjustment_factors import (
    AdjustmentFactorRecord,
    normalize_adjusted_close_factor,
)
from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness
from trading_agent.ingestion.apply_adjustment_factors import apply_adjustment_factors_to_db


ERROR_STATUSES = {
    "invalid_request",
    "missing_payload",
    "invalid_json",
    "not_ready",
    "missing_store",
    "invalid_factor_json",
}


def load_adjusted_price_payload(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def build_factor_records_from_adjusted_price_payload(
    payload: Any,
    *,
    source_id: str | None,
    raw_path: str | None,
    symbols: list[str],
) -> list[AdjustmentFactorRecord]:
    requested = _normalize_symbols(symbols)
    rows = _payload_rows(payload)
    records = [
        normalize_adjusted_close_factor(
            symbol=str(row.get("symbol") or ""),
            trade_date=str(row.get("trade_date") or ""),
            raw_close=row.get("close"),
            adjusted_close=row.get("adjusted_close"),
            source_id=source_id,
            raw_path=raw_path,
        )
        for row in rows
    ]
    if not requested:
        return records
    wanted = set(requested)
    return [record for record in records if record.symbol in wanted]


def write_factor_records(records: list[AdjustmentFactorRecord], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [_record_to_json(record) for record in records]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return path


def run_adjusted_price_evidence_pipeline(
    *,
    payload_path: str | Path,
    source_id: str | None,
    raw_path: str | None,
    symbols: list[str],
    factor_output_path: str | Path | None = None,
    db_path: str | Path | None = None,
    dry_run: bool = True,
    execute: bool = False,
    max_symbols: int = 3,
    allow_network: bool = False,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    validation_errors = _validate_request(
        symbols=requested,
        source_id=source_id,
        raw_path=raw_path,
        max_symbols=max_symbols,
        dry_run=dry_run,
        execute=execute,
        db_path=db_path,
        factor_output_path=factor_output_path,
        allow_network=allow_network,
    )
    if validation_errors:
        return _summary(
            status="invalid_request",
            symbols=requested,
            reasons=validation_errors,
            factor_output_path=factor_output_path,
            db_mutation_made=False,
        )

    try:
        payload = load_adjusted_price_payload(payload_path)
    except FileNotFoundError:
        return _summary(
            status="missing_payload",
            symbols=requested,
            reasons=[f"Payload not found: {payload_path}"],
            factor_output_path=factor_output_path,
            db_mutation_made=False,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _summary(
            status="invalid_json",
            symbols=requested,
            reasons=[f"Invalid JSON payload: {exc}"],
            factor_output_path=factor_output_path,
            db_mutation_made=False,
        )

    records = build_factor_records_from_adjusted_price_payload(
        payload,
        source_id=source_id,
        raw_path=raw_path,
        symbols=requested,
    )
    usable = [record for record in records if _is_usable(record)]
    invalid = [record for record in records if record.status == "invalid"]
    missing = [record for record in records if record.status == "missing"]

    written_path: Path | None = None
    if factor_output_path is not None:
        written_path = write_factor_records(records, factor_output_path)

    reasons = sorted({reason for record in records for reason in record.reasons})
    if not usable:
        reasons.append("no_usable_factor_records")

    apply_result: dict[str, Any] | None = None
    readiness_result: dict[str, Any] | None = None
    db_mutation_made = False
    if execute and usable and db_path is not None and written_path is not None:
        apply_result = apply_adjustment_factors_to_db(
            db_path=db_path,
            factor_path=written_path,
            symbols=requested,
            dry_run=False,
        )
        db_mutation_made = bool(apply_result.get("db_mutation_made"))
        readiness_result = get_adjusted_ohlc_readiness(db_path, symbols=requested)

    status = "ok" if usable else "not_ready"
    if apply_result and apply_result.get("status") in ERROR_STATUSES:
        status = str(apply_result["status"])
        reasons.extend(str(reason) for reason in apply_result.get("reasons", []))
    elif execute and usable:
        readiness_status = readiness_result.get("status") if readiness_result else None
        backtest_gate = readiness_result.get("backtest_gate") if readiness_result else None
        if readiness_status != "ok":
            status = "not_ready"
            reasons.append("adjusted_readiness_not_ready")
        if backtest_gate != "pass":
            status = "not_ready"
            reasons.append("backtest_gate_blocked")

    return _summary(
        status=status,
        symbols=sorted({record.symbol for record in records}) if records else requested,
        records_total=len(records),
        usable_records=len(usable),
        invalid_records=len(invalid),
        missing_records=len(missing),
        reasons=sorted(set(reasons)),
        factor_output_path=written_path or factor_output_path,
        db_mutation_made=db_mutation_made,
        readiness_status=readiness_result.get("status") if readiness_result else None,
        backtest_gate=readiness_result.get("backtest_gate") if readiness_result else None,
        apply_result=apply_result,
    )


def _validate_request(
    *,
    symbols: list[str],
    source_id: str | None,
    raw_path: str | None,
    max_symbols: int,
    dry_run: bool,
    execute: bool,
    db_path: str | Path | None,
    factor_output_path: str | Path | None,
    allow_network: bool,
) -> list[str]:
    reasons: list[str] = []
    if allow_network:
        reasons.append("network_not_implemented")
    if not symbols:
        reasons.append("explicit_symbols_required")
    if max_symbols <= 0:
        reasons.append("max_symbols_must_be_positive")
    if len(symbols) > max_symbols:
        reasons.append(f"too_many_symbols:max={max_symbols}")
    if not _clean_optional(source_id):
        reasons.append("source_id_required")
    if not _clean_optional(raw_path):
        reasons.append("raw_path_required")
    if dry_run and execute:
        reasons.append("choose_dry_run_or_execute")
    if execute and not db_path:
        reasons.append("db_path_required_for_execute")
    if execute and not factor_output_path:
        reasons.append("factor_output_path_required_for_execute")
    return reasons


def _summary(
    *,
    status: str,
    symbols: list[str],
    records_total: int = 0,
    usable_records: int = 0,
    invalid_records: int = 0,
    missing_records: int = 0,
    reasons: list[str] | None = None,
    factor_output_path: str | Path | None = None,
    db_mutation_made: bool,
    readiness_status: str | None = None,
    backtest_gate: str | None = None,
    apply_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": status,
        "symbols": symbols,
        "records_total": records_total,
        "usable_records": usable_records,
        "invalid_records": invalid_records,
        "missing_records": missing_records,
        "factor_output_path": str(factor_output_path) if factor_output_path else None,
        "db_mutation_made": bool(db_mutation_made),
        "readiness_status": readiness_status,
        "backtest_gate": backtest_gate,
        "reasons": reasons or [],
        "caveats": [
            "Local adjusted-price payload only; no network request made.",
            "No factor=1 fallback is used.",
            "Raw close is never treated as adjusted close.",
            "Backtrader/VN100 remains blocked until adjusted readiness passes.",
        ],
    }
    if apply_result is not None:
        result["apply_result"] = apply_result
    return result


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return [payload]
    return []


def _record_to_json(record: AdjustmentFactorRecord) -> dict[str, Any]:
    item = asdict(record)
    item["reasons"] = list(record.reasons)
    return item


def _is_usable(record: AdjustmentFactorRecord) -> bool:
    return record.status == "ok" and record.factor is not None and record.factor > 0 and not record.reasons


def _normalize_symbols(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
