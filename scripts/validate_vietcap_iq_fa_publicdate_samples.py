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
PRESERVED_STATUSES = frozenset({"official_not_found", "ambiguous_basis", "not_comparable"})
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


def summarize_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    status_counts = Counter(row["match_status"] for row in rows)
    confidence_counts = Counter(row["confidence"] for row in rows)
    credible_comparable = [
        row for row in rows
        if row["match_status"] in COMPARABLE_STATUSES
        and row["confidence"] in CREDIBLE_CONFIDENCE
    ]
    red_flags = [
        row for row in rows
        if row["match_status"] == "vietcap_before_official"
        and row["confidence"] in CREDIBLE_CONFIDENCE
    ]
    comparable_ratio = len(credible_comparable) / len(rows) if rows else 0.0

    if red_flags:
        pit_status = "pit_red_flags_found"
    elif comparable_ratio >= 0.70:
        pit_status = "pit_supported_small_sample"
    else:
        pit_status = "pit_inconclusive"

    return {
        "total_samples": len(rows),
        "match_status_counts": {status: status_counts.get(status, 0) for status in MATCH_STATUSES},
        "confidence_counts": {
            confidence: confidence_counts.get(confidence, 0)
            for confidence in ("high", "medium", "low", "none")
        },
        "credible_comparable_count": len(credible_comparable),
        "credible_comparable_ratio": comparable_ratio,
        "red_flag_count": len(red_flags),
        "pit_sample_status": pit_status,
    }


def load_and_validate(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
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
    args = parser.parse_args(argv)

    rows, summary = load_and_validate(args.input)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(build_markdown_report(rows, summary), encoding="utf-8")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
