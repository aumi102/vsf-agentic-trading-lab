from __future__ import annotations

from typing import Any

from trading_agent.ingestion.adjustment_factors import AdjustmentFactorRecord
from trading_agent.ingestion.sources.adjustment_factor_source import (
    parse_adjustment_factor_payload,
)


CANDIDATE_METHODS = frozenset({"adjusted_close_ratio", "corporate_action_derived"})
REQUIRED_PROVENANCE = ("source_id", "raw_path", "method")


def plan_factor_source_verification(
    symbols: list[str],
    *,
    candidate_methods: list[str] | None = None,
    allow_network: bool = False,
    max_symbols: int = 3,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    methods = _normalize_methods(candidate_methods)
    blocked_reasons = _validate_plan(
        symbols=requested,
        methods=methods,
        allow_network=allow_network,
        max_symbols=max_symbols,
    )
    status = "blocked" if blocked_reasons else "ok"
    return {
        "status": status,
        "mode": "plan_only",
        "symbols_requested": requested,
        "candidate_methods": methods,
        "required_provenance": list(REQUIRED_PROVENANCE),
        "max_symbols": int(max_symbols),
        "allow_network": bool(allow_network),
        "planned_steps": _planned_steps(requested, methods) if status == "ok" else [],
        "blocked_reasons": blocked_reasons,
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
        "caveats": [
            "Plan only; no network request made.",
            "No approved live/vendor source is wired in yet.",
            "No DB mutation and no adjusted OHLC population.",
            "Backtrader remains blocked until adjusted OHLC readiness passes.",
        ],
    }


def verify_factor_source_payload(
    payload: Any,
    *,
    method: str,
    source_id: str | None,
    raw_path: str | None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols or [])
    if method not in CANDIDATE_METHODS:
        return {
            "status": "invalid",
            "records_total": 0,
            "usable_records": 0,
            "missing_records": 0,
            "invalid_records": 0,
            "symbols": requested,
            "method": method,
            "source_id": _clean_optional(source_id),
            "raw_path": _clean_optional(raw_path),
            "reasons": [f"unsupported_factor_source_method:{method}"],
            "network_request_made": False,
            "db_mutation_made": False,
            "adjusted_ohlc_populated": False,
            "caveats": _caveats(),
        }

    parsed = parse_adjustment_factor_payload(
        payload,
        source_id=source_id,
        raw_path=raw_path,
        method=method,
    )
    records = _filter_records(parsed.records, requested)
    usable = [record for record in records if record.status == "ok"]
    missing = [record for record in records if record.status == "missing"]
    invalid = [record for record in records if record.status == "invalid"]

    reasons = list(parsed.reasons)
    if not usable:
        reasons.append("no_usable_factor_records")

    return {
        "status": "ok" if usable else "not_ready",
        "records_total": len(records),
        "usable_records": len(usable),
        "missing_records": len(missing),
        "invalid_records": len(invalid),
        "symbols": sorted({record.symbol for record in usable}) if usable else requested,
        "method": method,
        "source_id": parsed.source_id,
        "raw_path": parsed.raw_path,
        "reasons": reasons,
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
        "caveats": _caveats(),
    }


def _validate_plan(
    *,
    symbols: list[str],
    methods: list[str],
    allow_network: bool,
    max_symbols: int,
) -> list[str]:
    reasons: list[str] = []
    if not symbols:
        reasons.append("At least one symbol is required.")
    if max_symbols <= 0:
        reasons.append("max_symbols must be positive.")
    if len(symbols) > max_symbols:
        reasons.append(f"Requested {len(symbols)} symbols; max per check is {max_symbols}.")
    if not methods:
        reasons.append("At least one candidate method is required.")
    unknown = [method for method in methods if method not in CANDIDATE_METHODS]
    if unknown:
        reasons.append(f"Unknown candidate method: {', '.join(unknown)}.")
    if allow_network:
        reasons.append("Live factor-source verification is not implemented in this PR.")
    return reasons


def _planned_steps(symbols: list[str], methods: list[str]) -> list[dict[str, Any]]:
    steps = []
    for method in methods:
        steps.append(
            {
                "method": method,
                "symbols": symbols,
                "checks": [
                    "load an approved local payload (no network)",
                    "parse payload into factor records via the source adapter",
                    "require source_id, raw_path, and method provenance",
                    "confirm at least one usable factor record per requested symbol",
                    "apply records with local factor application and confirm adjusted readiness",
                ],
            }
        )
    return steps


def _filter_records(
    records: tuple[AdjustmentFactorRecord, ...],
    symbols: list[str],
) -> list[AdjustmentFactorRecord]:
    if not symbols:
        return list(records)
    wanted = set(symbols)
    return [record for record in records if record.symbol in wanted]


def _caveats() -> list[str]:
    return [
        "Local payload verification only; no network request made.",
        "No DB mutation and no adjusted OHLC population.",
        "Usable here means parseable provenance-backed factor records, not an approved live source.",
    ]


def _normalize_symbols(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values or []:
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized


def _normalize_methods(values: list[str] | None) -> list[str]:
    if values is None:
        return sorted(CANDIDATE_METHODS)
    seen = set()
    normalized = []
    for value in values:
        method = str(value or "").strip()
        if method and method not in seen:
            seen.add(method)
            normalized.append(method)
    return normalized


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
