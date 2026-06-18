from __future__ import annotations

from typing import Any


SUPPORTED_CANDIDATE_SOURCES = frozenset(
    {"vietcap_iq_gap_chart", "vietcap_iq_company_events", "tracked_fixtures"}
)
ADJUSTED_CLOSE_FIELDS = frozenset({"adjusted_close", "adj_close", "adjustedClose", "adjClose"})
ADJUSTMENT_FACTOR_FIELDS = frozenset({"adjustment_factor", "adjust_factor", "factor"})
CORPORATE_ACTION_TERMS = frozenset(
    {"dividend", "split", "bonus", "rights", "ex_date", "record_date"}
)


def plan_adjusted_factor_probe(
    symbols: list[str],
    candidate_sources: list[str],
    allow_network: bool = False,
    max_symbols: int = 3,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    candidates = _normalize_sources(candidate_sources)
    blocked_reasons = _validate_plan(
        symbols=requested,
        candidate_sources=candidates,
        allow_network=allow_network,
        max_symbols=max_symbols,
    )
    status = "blocked" if blocked_reasons else "ok"
    return {
        "status": status,
        "mode": "dry_run",
        "symbols_requested": requested,
        "candidate_sources": candidates,
        "max_symbols": int(max_symbols),
        "allow_network": bool(allow_network),
        "probe_objectives": [
            "adjusted_close_field",
            "adjustment_factor_field",
            "corporate_action_terms",
            "source_id_raw_path_provenance",
            "factor_derivation_possible",
        ],
        "planned_steps": _planned_steps(requested, candidates) if status == "ok" else [],
        "blocked_reasons": blocked_reasons,
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
        "caveats": [
            "Dry-run plan only; no network request made.",
            "No DB mutation and no adjusted OHLC population.",
            "Backtrader remains blocked until adjusted OHLC readiness passes.",
        ],
    }


def inspect_payload_for_adjustment_evidence(payload: Any) -> dict[str, Any]:
    fields = _walk_fields(payload)
    adjusted_close = sorted(field for field in fields if field in ADJUSTED_CLOSE_FIELDS)
    factors = sorted(field for field in fields if field in ADJUSTMENT_FACTOR_FIELDS)
    corporate_terms = sorted(field for field in fields if field.lower() in CORPORATE_ACTION_TERMS)
    evidence_found = bool(adjusted_close or factors or corporate_terms)
    return {
        "status": "evidence_found" if evidence_found else "no_evidence",
        "adjusted_close_fields": adjusted_close,
        "adjustment_factor_fields": factors,
        "corporate_action_terms": corporate_terms,
        "can_derive_factor": bool(adjusted_close or factors),
        "network_request_made": False,
        "db_mutation_made": False,
        "adjusted_ohlc_populated": False,
        "caveats": [
            "Local payload inspection only.",
            "Evidence here does not populate adjusted OHLC.",
        ],
    }


def _validate_plan(
    *,
    symbols: list[str],
    candidate_sources: list[str],
    allow_network: bool,
    max_symbols: int,
) -> list[str]:
    reasons: list[str] = []
    if not symbols:
        reasons.append("At least one symbol is required.")
    if max_symbols <= 0:
        reasons.append("max_symbols must be positive.")
    if len(symbols) > max_symbols:
        reasons.append(f"Requested {len(symbols)} symbols; max per probe is {max_symbols}.")
    if not candidate_sources:
        reasons.append("At least one candidate source is required.")
    unknown = [source for source in candidate_sources if source not in SUPPORTED_CANDIDATE_SOURCES]
    if unknown:
        reasons.append(f"Unknown candidate source: {', '.join(unknown)}.")
    if allow_network:
        reasons.append("Live adjusted-factor source probing is not implemented in this PR.")
    return reasons


def _planned_steps(symbols: list[str], candidate_sources: list[str]) -> list[dict[str, Any]]:
    steps = []
    for source in candidate_sources:
        steps.append(
            {
                "candidate_source": source,
                "symbols": symbols,
                "checks": [
                    "inspect tracked fixtures or approved local payloads",
                    "search for adjusted-close field names",
                    "search for adjustment-factor field names",
                    "search for dividend/split/bonus/rights/ex-date/record-date terms",
                    "verify source_id and raw_path provenance before ETL integration",
                ],
            }
        )
    return steps


def _walk_fields(payload: Any) -> set[str]:
    fields: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            fields.add(str(key))
            fields.update(_walk_fields(value))
    elif isinstance(payload, list):
        for item in payload:
            fields.update(_walk_fields(item))
    return fields


def _normalize_symbols(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values or []:
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized


def _normalize_sources(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values or []:
        source = str(value or "").strip()
        if source and source not in seen:
            seen.add(source)
            normalized.append(source)
    return normalized
