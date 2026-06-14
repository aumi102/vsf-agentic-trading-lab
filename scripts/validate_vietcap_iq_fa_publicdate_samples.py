from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "docs/data_sources/vietcap_iq_fa_publicdate_validation_samples.csv"

MATCH_STATUSES = (
    "exact_match",
    "near_match_1_3_days",
    "vietcap_after_official",
    "vietcap_before_official",
    "official_not_found",
    "manual_only",
    "blocked",
    "network_error",
    "ambiguous_basis",
    "not_comparable",
)
REQUIRED_COLUMNS = (
    "sample_id",
    "symbol",
    "section",
    "run_id",
    "payload_path",
    "fiscal_year",
    "length_report",
    "period_type",
    "period_label",
    "vietcap_public_date",
    "vietcap_update_date",
    "server_datetime",
    "crawled_at",
    "official_source_type",
    "official_source_url",
    "official_disclosure_date",
    "official_document_title",
    "official_date_basis",
    "date_delta_days",
    "match_status",
    "confidence",
    "reviewer_note",
)
PRESERVED_STATUSES = frozenset({
    "official_not_found",
    "manual_only",
    "blocked",
    "network_error",
    "ambiguous_basis",
    "not_comparable",
})
COMPARABLE_STATUSES = frozenset({
    "exact_match",
    "near_match_1_3_days",
    "vietcap_after_official",
    "vietcap_before_official",
})
CREDIBLE_CONFIDENCE = frozenset({"high", "medium"})
CONFIDENCE_VALUES = frozenset({"high", "medium", "low", "none"})


def parse_date(value: str, *, field_name: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError as exc:
        raise ValueError(f"Malformed {field_name}: {value!r}") from exc


def classify_delta(delta_days: int) -> str:
    if delta_days == 0:
        return "exact_match"
    if 1 <= delta_days <= 3:
        return "near_match_1_3_days"
    if delta_days > 3:
        return "vietcap_after_official"
    return "vietcap_before_official"


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    explicit_status = (normalized.get("match_status") or "").strip()
    confidence = (normalized.get("confidence") or "").strip().lower()
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError(f"Invalid confidence for {normalized.get('sample_id', '')}: {confidence!r}")
    normalized["confidence"] = confidence

    if explicit_status and explicit_status not in MATCH_STATUSES:
        raise ValueError(
            f"Invalid match_status for {normalized.get('sample_id', '')}: {explicit_status!r}"
        )

    if explicit_status in PRESERVED_STATUSES:
        normalized["match_status"] = explicit_status
        return normalized

    vietcap_date = parse_date(
        normalized.get("vietcap_public_date", ""),
        field_name="vietcap_public_date",
    )
    official_date = parse_date(
        normalized.get("official_disclosure_date", ""),
        field_name="official_disclosure_date",
    )
    if official_date is None:
        if explicit_status and explicit_status in COMPARABLE_STATUSES:
            raise ValueError(
                f"official_disclosure_date missing for comparable status "
                f"{normalized.get('sample_id', '')}: {explicit_status!r}"
            )
        normalized["match_status"] = explicit_status or "official_not_found"
        return normalized
    if vietcap_date is None:
        raise ValueError(f"Missing vietcap_public_date for {normalized.get('sample_id', '')}")

    computed_delta = (vietcap_date - official_date).days
    existing_delta = (normalized.get("date_delta_days") or "").strip()
    if existing_delta and int(existing_delta) != computed_delta:
        raise ValueError(
            f"date_delta_days mismatch for {normalized.get('sample_id', '')}: "
            f"csv={existing_delta}, computed={computed_delta}"
        )
    normalized["date_delta_days"] = str(computed_delta)

    computed_status = classify_delta(computed_delta)
    if explicit_status and explicit_status != computed_status:
        raise ValueError(
            f"match_status mismatch for {normalized.get('sample_id', '')}: "
            f"csv={explicit_status}, computed={computed_status}"
        )
    normalized["match_status"] = computed_status
    return normalized


def _normalized_evidence_value(value: str) -> str:
    return (value or "").strip()


def _normalized_evidence_url(value: str) -> str:
    return _normalized_evidence_value(value).rstrip("/")


def _make_evidence_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        _normalized_evidence_value(row.get("symbol", "")),
        _normalized_evidence_value(row.get("period_label", "")),
        _normalized_evidence_url(row.get("official_source_url", "")),
        _normalized_evidence_value(row.get("official_disclosure_date", "")),
        _normalized_evidence_value(row.get("official_document_title", "")),
    )


def _has_evidence_identity(row: dict[str, str]) -> bool:
    key = _make_evidence_key(row)
    return all(value for value in key)


def _period_bucket(row: dict[str, str]) -> str:
    period_type = _normalized_evidence_value(row.get("period_type", "")).lower()
    period_label = _normalized_evidence_value(row.get("period_label", "")).lower()
    if period_type in {"annual", "year", "yearly"} or period_label.endswith("y"):
        return "annual"
    if period_type in {"quarter", "quarterly"} or "q" in period_label:
        return "quarterly"
    return ""


def summarize_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    status_counts = Counter(row["match_status"] for row in rows)
    confidence_counts = Counter(row["confidence"] for row in rows)
    credible_comparable = [
        row for row in rows
        if row["match_status"] in COMPARABLE_STATUSES
        and row["confidence"] in CREDIBLE_CONFIDENCE
        and _has_evidence_identity(row)
    ]
    red_flags = [
        row for row in rows
        if row["match_status"] == "vietcap_before_official"
        and row["confidence"] in CREDIBLE_CONFIDENCE
    ]
    credible_statement_ratio = len(credible_comparable) / len(rows) if rows else 0.0

    comparable_with_identity = [
        r for r in rows if r["match_status"] in COMPARABLE_STATUSES and _has_evidence_identity(r)
    ]
    all_comparable_events: set[tuple] = {_make_evidence_key(r) for r in comparable_with_identity}
    credible_events: set[tuple] = {_make_evidence_key(r) for r in credible_comparable}
    credible_issuers: set[str] = {
        _normalized_evidence_value(r.get("symbol", "")) for r in credible_comparable
    }
    issuer_period_events: set[tuple[str, str]] = {
        (
            _normalized_evidence_value(r.get("symbol", "")),
            _normalized_evidence_value(r.get("period_label", "")),
        )
        for r in rows
        if r["match_status"] in COMPARABLE_STATUSES
    }
    credible_symbols_by_event = {
        _make_evidence_key(r): _normalized_evidence_value(r.get("symbol", ""))
        for r in credible_comparable
    }
    credible_sectors_by_event = {
        _make_evidence_key(r): _normalized_evidence_value(r.get("sector", ""))
        for r in credible_comparable
    }
    credible_periods_by_event = {
        _make_evidence_key(r): _period_bucket(r)
        for r in credible_comparable
    }
    credible_status_by_event = {
        _make_evidence_key(r): r["match_status"]
        for r in credible_comparable
    }

    unique_evidence_events = len(all_comparable_events)
    credible_unique_evidence_events = len(credible_events)
    credible_evidence_ratio = (
        credible_unique_evidence_events / unique_evidence_events
        if unique_evidence_events
        else 0.0
    )
    unique_issuers = len(credible_issuers)
    unique_issuer_period_events = len(issuer_period_events)
    total_target_issuers = len({
        _normalized_evidence_value(r.get("symbol", ""))
        for r in rows
        if _normalized_evidence_value(r.get("symbol", ""))
    })
    total_sectors = len({
        _normalized_evidence_value(r.get("sector", ""))
        for r in rows
        if _normalized_evidence_value(r.get("sector", ""))
    })
    verified_issuers = len({symbol for symbol in credible_symbols_by_event.values() if symbol})
    verified_sectors = len({sector for sector in credible_sectors_by_event.values() if sector})
    annual_evidence_events = sum(1 for key in credible_events if credible_periods_by_event.get(key) == "annual")
    quarterly_evidence_events = sum(1 for key in credible_events if credible_periods_by_event.get(key) == "quarterly")
    exact_match_events = sum(1 for key in credible_events if credible_status_by_event.get(key) == "exact_match")
    near_match_events = sum(1 for key in credible_events if credible_status_by_event.get(key) == "near_match_1_3_days")
    vietcap_after_official_events = sum(
        1 for key in credible_events if credible_status_by_event.get(key) == "vietcap_after_official"
    )
    vietcap_before_official_red_flags = len({
        _make_evidence_key(r) for r in red_flags if _has_evidence_identity(r)
    })
    blocked_manual_unresolved_targets = sum(
        1 for row in rows
        if row["match_status"] in {"official_not_found", "manual_only", "blocked", "network_error", "ambiguous_basis", "not_comparable"}
    )

    if red_flags:
        pit_status = "pit_red_flags_found"
    elif (
        unique_issuers >= 6
        and verified_sectors >= 5
        and credible_unique_evidence_events >= 12
        and annual_evidence_events > 0
        and quarterly_evidence_events > 0
        and credible_evidence_ratio >= 0.80
    ):
        pit_status = "pit_supported_breadth_sample"
    elif (
        credible_statement_ratio >= 0.70
        and credible_evidence_ratio >= 0.70
        and unique_issuers >= 2
        and credible_unique_evidence_events >= 4
    ):
        pit_status = "pit_supported_small_sample"
    else:
        pit_status = "pit_inconclusive"

    return {
        "total_samples": len(rows),
        "total_statement_rows": len(rows),
        "match_status_counts": {status: status_counts.get(status, 0) for status in MATCH_STATUSES},
        "confidence_counts": {
            confidence: confidence_counts.get(confidence, 0)
            for confidence in ("high", "medium", "low", "none")
        },
        "credible_comparable_count": len(credible_comparable),
        "credible_comparable_ratio": credible_statement_ratio,
        "credible_statement_rows": len(credible_comparable),
        "credible_statement_ratio": credible_statement_ratio,
        "unique_evidence_events": unique_evidence_events,
        "credible_unique_evidence_events": credible_unique_evidence_events,
        "credible_evidence_ratio": credible_evidence_ratio,
        "unique_issuers": unique_issuers,
        "unique_issuer_period_events": unique_issuer_period_events,
        "total_target_issuers": total_target_issuers,
        "verified_issuers": verified_issuers,
        "total_sectors": total_sectors,
        "verified_sectors": verified_sectors,
        "total_unique_evidence_events": unique_evidence_events,
        "annual_evidence_events": annual_evidence_events,
        "quarterly_evidence_events": quarterly_evidence_events,
        "exact_match_events": exact_match_events,
        "near_match_events": near_match_events,
        "vietcap_after_official_events": vietcap_after_official_events,
        "vietcap_before_official_red_flags": vietcap_before_official_red_flags,
        "blocked_manual_unresolved_targets": blocked_manual_unresolved_targets,
        "red_flag_count": len(red_flags),
        "pit_sample_status": pit_status,
    }


def load_and_validate(
    path: Path, *, check_payload_paths: bool = False
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing required column(s): {missing}")
        rows = [normalize_row(row) for row in reader]
    sample_ids = [row.get("sample_id", "") for row in rows]
    duplicates = sorted({sid for sid in sample_ids if sample_ids.count(sid) > 1})
    if duplicates:
        raise ValueError(f"Duplicate sample_id value(s): {duplicates}")
    if check_payload_paths:
        for row in rows:
            pp = ROOT / row["payload_path"]
            if not pp.exists():
                raise FileNotFoundError(
                    f"Payload path not found: {row['payload_path']!r} "
                    f"(sample_id={row['sample_id']!r})"
                )
    return rows, summarize_rows(rows)


def build_markdown_report(rows: list[dict[str, str]], summary: dict[str, Any]) -> str:
    counts = summary["match_status_counts"]
    conf = summary["confidence_counts"]
    lines = [
        "# Vietcap IQ FA publicDate Sample Validation",
        "",
        f"Final PIT sample status: `{summary['pit_sample_status']}`.",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Total samples | {summary['total_samples']} |",
        f"| `exact_match` | {counts['exact_match']} |",
        f"| `near_match_1_3_days` | {counts['near_match_1_3_days']} |",
        f"| `vietcap_after_official` | {counts['vietcap_after_official']} |",
        f"| `vietcap_before_official` | {counts['vietcap_before_official']} |",
        f"| `official_not_found` | {counts['official_not_found']} |",
        f"| `ambiguous_basis` | {counts['ambiguous_basis']} |",
        f"| `not_comparable` | {counts['not_comparable']} |",
        "",
        "## Confidence",
        "",
        "| Confidence | Count |",
        "|---|---:|",
        f"| high | {conf['high']} |",
        f"| medium | {conf['medium']} |",
        f"| low | {conf['low']} |",
        f"| none | {conf['none']} |",
        "",
        "## Samples",
        "",
        "| sample_id | status | confidence | delta |",
        "|---|---|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['sample_id']}` | `{row['match_status']}` | "
            f"`{row['confidence']}` | {row.get('date_delta_days', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate offline Vietcap IQ FA publicDate PIT sample CSV."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--check-payload-paths",
        action="store_true",
        help="Verify each payload_path exists under repo root.",
    )
    args = parser.parse_args(argv)

    rows, summary = load_and_validate(args.input, check_payload_paths=args.check_payload_paths)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(build_markdown_report(rows, summary), encoding="utf-8")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
