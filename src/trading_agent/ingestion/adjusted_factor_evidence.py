from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from trading_agent.ingestion.adjusted_factor_probe import inspect_payload_for_adjustment_evidence


def build_adjusted_factor_evidence_record(
    *,
    symbol: str,
    source: str,
    payload_path: str | Path,
    payload: Any,
    payload_bytes: bytes | None = None,
) -> dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_source = str(source or "").strip()
    normalized_payload_path = str(payload_path or "").strip()
    reasons: list[str] = []
    if not normalized_symbol:
        reasons.append("symbol_required")
    if not normalized_source:
        reasons.append("source_required")
    if not normalized_payload_path:
        reasons.append("payload_path_required")

    inspection = inspect_payload_for_adjustment_evidence(payload)
    content_hash = _hash_payload(payload=payload, payload_bytes=payload_bytes)
    status = _record_status(inspection["evidence_strength"], reasons)
    can_derive_factor = bool(inspection["can_derive_factor"]) and not reasons
    return {
        "symbol": normalized_symbol,
        "source": normalized_source,
        "payload_path": normalized_payload_path,
        "content_hash": content_hash,
        "evidence_strength": inspection["evidence_strength"],
        "evidence_summary": inspection["evidence_summary"],
        "candidate_fields": inspection["candidate_fields"],
        "adjusted_close_fields": inspection["adjusted_close_fields"],
        "adjustment_factor_fields": inspection["adjustment_factor_fields"],
        "generic_factor_fields": inspection["generic_factor_fields"],
        "corporate_action_terms": inspection["corporate_action_terms"],
        "can_derive_factor": can_derive_factor,
        "status": status,
        "reasons": reasons,
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
        "caveats": [
            "Local payload evidence capture only.",
            "Evidence does not populate adjusted OHLC.",
            "Source provenance must be reviewed before ETL integration.",
        ],
    }


def capture_payload_adjustment_evidence(
    *,
    symbol: str,
    source: str,
    payload_path: str | Path,
) -> dict[str, Any]:
    path = Path(payload_path)
    try:
        payload_bytes = path.read_bytes()
    except FileNotFoundError:
        return _error_record(
            status="missing_payload",
            symbol=symbol,
            source=source,
            payload_path=payload_path,
            reason=f"Payload not found: {path}",
        )
    try:
        payload = json.loads(payload_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error_record(
            status="invalid_json",
            symbol=symbol,
            source=source,
            payload_path=payload_path,
            reason=f"Invalid JSON payload: {exc}",
        )
    return build_adjusted_factor_evidence_record(
        symbol=symbol,
        source=source,
        payload_path=path,
        payload=payload,
        payload_bytes=payload_bytes,
    )


def summarize_adjusted_factor_evidence(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    by_status = _count_by(rows, "status")
    by_strength = _count_by(rows, "evidence_strength")
    return {
        "status": "empty" if not rows else "ok",
        "total_records": len(rows),
        "records_with_derivable_factor_candidate": sum(1 for row in rows if row.get("can_derive_factor") is True),
        "by_status": by_status,
        "by_evidence_strength": by_strength,
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
    }


def _record_status(evidence_strength: str, reasons: list[str]) -> str:
    if reasons:
        return "invalid"
    if evidence_strength == "none":
        return "no_evidence"
    return "candidate_evidence"


def _hash_payload(*, payload: Any, payload_bytes: bytes | None) -> str:
    if payload_bytes is None:
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


def _error_record(
    *,
    status: str,
    symbol: str,
    source: str,
    payload_path: str | Path,
    reason: str,
) -> dict[str, Any]:
    return {
        "symbol": str(symbol or "").strip().upper(),
        "source": str(source or "").strip(),
        "payload_path": str(payload_path or "").strip(),
        "content_hash": None,
        "evidence_strength": "none",
        "adjusted_close_fields": [],
        "adjustment_factor_fields": [],
        "corporate_action_terms": [],
        "can_derive_factor": False,
        "status": status,
        "reasons": [reason],
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
