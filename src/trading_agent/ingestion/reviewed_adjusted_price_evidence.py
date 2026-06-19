from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any

from trading_agent.ingestion.adjusted_price_evidence_pipeline import (
    ERROR_STATUSES as PIPELINE_ERROR_STATUSES,
    run_adjusted_price_evidence_pipeline,
)


ACCEPTED_EVIDENCE_BASIS = {
    "adjusted_price_vendor_export",
    "corporate_action_derived",
    "manual_curated_for_dev_only",
}
ERROR_STATUSES = {
    *PIPELINE_ERROR_STATUSES,
    "missing_manifest",
    "invalid_manifest_json",
    "invalid_manifest",
    "missing_payload",
    "invalid_payload_json",
    "invalid_payload",
}
REQUIRED_FIELDS = ("symbol", "trade_date", "close", "adjusted_close")
REQUIRED_METADATA = ("source_id", "raw_path", "reviewer", "reviewed_at", "evidence_basis")


def load_reviewed_evidence_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Reviewed evidence manifest must be a JSON object.")
    return payload


def load_reviewed_evidence_payload(path: str | Path) -> Any:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    return json.loads(source.read_text(encoding="utf-8-sig"))


def normalize_reviewed_evidence_rows(payload_or_csv: Any) -> list[dict[str, Any]]:
    if isinstance(payload_or_csv, list):
        return [dict(item) for item in payload_or_csv if isinstance(item, dict)]
    if isinstance(payload_or_csv, dict):
        data = payload_or_csv.get("data")
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        return [dict(payload_or_csv)]
    return []


def validate_reviewed_evidence_manifest(manifest: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in REQUIRED_METADATA:
        if not _clean_optional(manifest.get(field)):
            reasons.append(f"{field}_required")
    basis = _clean_optional(manifest.get("evidence_basis"))
    if basis and basis not in ACCEPTED_EVIDENCE_BASIS:
        reasons.append(f"unsupported_evidence_basis:{basis}")
    if basis == "raw_close_as_adjusted_close":
        reasons.append("raw_close_as_adjusted_close_blocked")
    if bool(manifest.get("allow_network")):
        reasons.append("live_network_fetch_blocked")
    return reasons


def validate_reviewed_evidence_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    *,
    symbols: list[str],
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    wanted = set(requested)
    selected = [row for row in rows if _normalize_symbol(row.get("symbol")) in wanted]
    found = {_normalize_symbol(row.get("symbol")) for row in selected}
    missing_symbols = [symbol for symbol in requested if symbol not in found]

    row_errors: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        reasons: list[str] = []
        for field in REQUIRED_FIELDS:
            if not _clean_optional(row.get(field)):
                reasons.append(f"{field}_required")

        close = _to_float(row.get("close"))
        adjusted_close = _to_float(row.get("adjusted_close"))
        if close is None:
            reasons.append("close_missing_or_non_finite")
        elif close <= 0:
            reasons.append("close_must_be_positive")
        if adjusted_close is None:
            reasons.append("adjusted_close_missing_or_non_finite")
        elif adjusted_close <= 0:
            reasons.append("adjusted_close_must_be_positive")
        if close is not None and adjusted_close is not None and close == adjusted_close:
            if not _explicit_factor_one_reason(row):
                reasons.append("factor_1_requires_explicit_evidence_reason")
            if _clean_optional(manifest.get("evidence_basis")) == "manual_curated_for_dev_only":
                reasons.append("raw_close_as_adjusted_close_blocked")

        if reasons:
            row_errors.append(
                {
                    "index": index,
                    "symbol": _normalize_symbol(row.get("symbol")),
                    "trade_date": str(row.get("trade_date") or "").strip(),
                    "reasons": sorted(set(reasons)),
                }
            )

    return {
        "status": "ok" if selected and not missing_symbols and not row_errors else "not_ready",
        "rows_total": len(selected),
        "selected_rows": selected,
        "missing_symbols": missing_symbols,
        "row_errors": row_errors,
    }


def run_reviewed_adjusted_price_evidence_intake(
    *,
    manifest_path: str | Path,
    payload_path: str | Path,
    symbols: list[str],
    validation_output_path: str | Path | None = None,
    factor_output_path: str | Path | None = None,
    db_path: str | Path | None = None,
    dry_run: bool = True,
    execute: bool = False,
    max_symbols: int = 3,
    allow_network: bool = False,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    request_errors = _validate_request(
        symbols=requested,
        max_symbols=max_symbols,
        dry_run=dry_run,
        execute=execute,
        db_path=db_path,
        factor_output_path=factor_output_path,
        allow_network=allow_network,
    )
    if request_errors:
        return _write_report(
            _summary(status="invalid_request", symbols=requested, reasons=request_errors),
            validation_output_path,
        )

    try:
        manifest = load_reviewed_evidence_manifest(manifest_path)
    except FileNotFoundError:
        return _write_report(
            _summary(
                status="missing_manifest",
                symbols=requested,
                manifest_status="missing_manifest",
                reasons=[f"Manifest not found: {manifest_path}"],
            ),
            validation_output_path,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return _write_report(
            _summary(
                status="invalid_manifest_json",
                symbols=requested,
                manifest_status="invalid_manifest_json",
                reasons=[f"Invalid manifest JSON: {exc}"],
            ),
            validation_output_path,
        )

    manifest_errors = validate_reviewed_evidence_manifest(manifest)
    if manifest_errors:
        return _write_report(
            _summary(
                status="invalid_manifest",
                symbols=requested,
                manifest_status="invalid_manifest",
                reasons=manifest_errors,
            ),
            validation_output_path,
        )

    try:
        payload = load_reviewed_evidence_payload(payload_path)
    except FileNotFoundError:
        return _write_report(
            _summary(
                status="missing_payload",
                symbols=requested,
                manifest_status="ok",
                reasons=[f"Payload not found: {payload_path}"],
            ),
            validation_output_path,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, csv.Error) as exc:
        return _write_report(
            _summary(
                status="invalid_payload_json",
                symbols=requested,
                manifest_status="ok",
                reasons=[f"Invalid payload: {exc}"],
            ),
            validation_output_path,
        )

    rows = normalize_reviewed_evidence_rows(payload)
    row_validation = validate_reviewed_evidence_rows(rows, manifest, symbols=requested)
    if row_validation["status"] != "ok":
        reasons = (
            [f"requested_symbols_missing:{','.join(row_validation['missing_symbols'])}"]
            if row_validation["missing_symbols"]
            else []
        )
        reasons.extend(reason for error in row_validation["row_errors"] for reason in error["reasons"])
        return _write_report(
            _summary(
                status="not_ready",
                symbols=requested,
                manifest_status="ok",
                rows_total=row_validation["rows_total"],
                invalid_records=len(row_validation["row_errors"]),
                missing_records=len(row_validation["missing_symbols"]),
                reasons=sorted(set(reasons or ["reviewed_evidence_not_ready"])),
                row_errors=row_validation["row_errors"],
            ),
            validation_output_path,
        )

    with tempfile.TemporaryDirectory(prefix="vsf_reviewed_adjusted_price_", ignore_cleanup_errors=True) as temp_dir:
        normalized_payload = Path(temp_dir) / "reviewed_adjusted_price_payload.json"
        normalized_payload.write_text(
            json.dumps(row_validation["selected_rows"], indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        pipeline_result = run_adjusted_price_evidence_pipeline(
            payload_path=normalized_payload,
            source_id=str(manifest.get("source_id")),
            raw_path=str(manifest.get("raw_path")),
            symbols=requested,
            factor_output_path=factor_output_path,
            db_path=db_path,
            dry_run=dry_run,
            execute=execute,
        )

    result = _summary(
        status=str(pipeline_result.get("status")),
        symbols=requested,
        manifest_status="ok",
        rows_total=row_validation["rows_total"],
        usable_records=int(pipeline_result.get("usable_records") or 0),
        invalid_records=int(pipeline_result.get("invalid_records") or 0),
        missing_records=int(pipeline_result.get("missing_records") or 0),
        validation_report_path=validation_output_path,
        factor_output_path=pipeline_result.get("factor_output_path"),
        db_mutation_made=bool(pipeline_result.get("db_mutation_made")),
        readiness_status=pipeline_result.get("readiness_status"),
        backtest_gate=pipeline_result.get("backtest_gate"),
        reasons=list(pipeline_result.get("reasons") or []),
    )
    result["pipeline_result"] = pipeline_result
    return _write_report(result, validation_output_path)


def _validate_request(
    *,
    symbols: list[str],
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
    manifest_status: str | None = None,
    rows_total: int = 0,
    usable_records: int = 0,
    invalid_records: int = 0,
    missing_records: int = 0,
    validation_report_path: str | Path | None = None,
    factor_output_path: str | Path | None = None,
    db_mutation_made: bool = False,
    readiness_status: str | None = None,
    backtest_gate: str | None = None,
    reasons: list[str] | None = None,
    row_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = {
        "status": status,
        "symbols": symbols,
        "manifest_status": manifest_status,
        "rows_total": rows_total,
        "usable_records": usable_records,
        "invalid_records": invalid_records,
        "missing_records": missing_records,
        "validation_report_path": str(validation_report_path) if validation_report_path else None,
        "factor_output_path": str(factor_output_path) if factor_output_path else None,
        "db_mutation_made": bool(db_mutation_made),
        "readiness_status": readiness_status,
        "backtest_gate": backtest_gate,
        "reasons": reasons or [],
        "caveats": [
            "Reviewed local adjusted-price evidence only; no network request made.",
            "No factor=1 fallback is created.",
            "Raw close is never treated as adjusted close.",
            "Backtrader/VN100 remains blocked until reviewed evidence and adjusted readiness pass.",
        ],
    }
    if row_errors is not None:
        result["row_errors"] = row_errors
    return result


def _write_report(result: dict[str, Any], output_path: str | Path | None) -> dict[str, Any]:
    if output_path is None:
        return result
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result["validation_report_path"] = str(path)
    path.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return result


def _explicit_factor_one_reason(row: dict[str, Any]) -> bool:
    for field in ("factor_evidence_reason", "evidence_reason", "corporate_action_note"):
        if _clean_optional(row.get(field)):
            return True
    return False


def _normalize_symbols(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        symbol = _normalize_symbol(value)
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
