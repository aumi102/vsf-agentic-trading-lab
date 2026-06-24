"""Probe event/news/disclosure sources for a minimal QuestDB event layer.

This is a controlled source probe. Raw payload evidence is saved under an
ignored data path; only the summary document is intended to be tracked.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT_DIR = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from probe_official_disclosures import (  # noqa: E402
    DEFAULT_MAX_RECORDS_PER_TARGET,
    apply_targets_config,
    build_default_targets,
    load_targets_config,
    parse_symbols,
    run_disclosure_probe,
)

REPORT_PATH = ROOT / "docs" / "data_sources" / "event_news_source_probe.md"
DEFAULT_TARGETS_CONFIG = ROOT / "config" / "official_disclosure_targets.example.json"
DEFAULT_OUTPUT_BASE = ROOT / "data" / "processed" / "dry_run" / "event_news_probe" / "raw"
DEFAULT_BRONZE_BASE = ROOT / "data" / "processed" / "dry_run" / "event_news_probe" / "bronze"


def _write_report(result: dict[str, Any], *, execute: bool) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = result.get("summary", {})
    parse_summaries = result.get("parse_summaries") or result.get("plan", {}).get("parse_summaries") or []
    bronze_records = result.get("bronze_records", [])
    usable_records = [
        item.get("record", {})
        for item in bronze_records
        if isinstance(item, dict) and item.get("record")
    ]
    record_counts_by_dataset: Counter[str] = Counter()
    for item in bronze_records:
        if not isinstance(item, dict):
            continue
        record = item.get("record") if isinstance(item.get("record"), dict) else {}
        dataset = (
            item.get("dataset")
            or item.get("target_id")
            or (item.get("target") or {}).get("dataset")
            or (item.get("target") or {}).get("target_id")
        )
        if not dataset:
            metadata_path = str(record.get("metadata_path") or "")
            marker = f"{result.get('summary', {}).get('run_id', '')}\\"
            if metadata_path and marker in metadata_path:
                tail = metadata_path.split(marker, 1)[1]
                dataset = tail.split("\\", 1)[0]
        if dataset:
            record_counts_by_dataset[str(dataset)] += 1
    lines = [
        "# Event/news source probe",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- execute_mode: `{execute}`",
        f"- raw_evidence_root: `{DEFAULT_OUTPUT_BASE.parent}`",
        f"- plan_path: `{result.get('plan_path')}`",
        f"- report_path: `{result.get('report_path')}`",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## Candidate source status",
        "",
        "| Dataset | Source family | Symbol | Access/parse status | Records | Candidate fields | Limitation |",
        "|---|---|---|---|---:|---|---|",
    ]
    for item in parse_summaries:
        fields = item.get("candidate_fields") or ["symbol", "title", "published_at/published_date", "document_url"]
        limitation = "; ".join(item.get("warning_codes") or item.get("error_codes") or [])
        dataset = str(item.get("dataset") or "")
        record_count = int(item.get("record_count") or record_counts_by_dataset.get(dataset, 0))
        lines.append(
            f"| `{item.get('dataset')}` | `{item.get('source_family')}` | `{item.get('symbol')}` | "
            f"`{item.get('access_status') or item.get('parse_status')}` | {record_count} | "
            f"{', '.join(str(field) for field in fields)} | {limitation} |"
        )
    if not parse_summaries:
        lines.append("| n/a | n/a | n/a | `probe_not_executed_or_no_parse_summaries` | 0 | n/a | n/a |")
    lines.extend(["", "## Usability decision", ""])
    if usable_records:
        lines.append(
            "A minimal `event_news_items` ingestion can be built from parsed official disclosure records. "
            "These are disclosure/event records, not general news."
        )
    else:
        lines.append(
            "No usable event/news records were parsed in this probe. Agent event/news answers should remain unsupported, "
            "and OHLCV must not be used as a proxy."
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Official disclosure records are event-like evidence, not broad market news.",
            "- HOSE/HNX parent pages can be JS/AJAX shells; those are not ingested as records.",
            "- Raw payloads are intentionally kept under ignored `data/processed/dry_run/event_news_probe/`.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_probe(
    *,
    symbols: list[str],
    targets_config: Path,
    execute: bool,
    max_requests: int,
    max_records: int,
    run_id: str,
) -> dict[str, Any]:
    targets = build_default_targets(symbols)
    if targets_config.exists():
        targets = apply_targets_config(targets, load_targets_config(targets_config))
    result = run_disclosure_probe(
        targets=targets,
        max_requests=max_requests,
        sleep_min_seconds=2.0,
        sleep_max_seconds=2.0,
        execute=execute,
        force=True,
        run_id=run_id,
        output_base=DEFAULT_OUTPUT_BASE,
        bronze_base=DEFAULT_BRONZE_BASE,
        max_records=max_records,
    )
    _write_report(result, execute=execute)
    result["tracked_summary_report"] = str(REPORT_PATH)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe event/news/disclosure sources safely.")
    parser.add_argument("--symbols", default="FPT,VNM,HPG")
    parser.add_argument("--targets-config", default=str(DEFAULT_TARGETS_CONFIG))
    parser.add_argument("--execute", action="store_true", help="Make sequential HTTP requests.")
    parser.add_argument("--max-requests", type=int, default=3)
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS_PER_TARGET)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    symbols = parse_symbols(args.symbols)
    config = Path(args.targets_config)
    if not config.is_absolute():
        config = ROOT / config
    result = run_probe(
        symbols=symbols,
        targets_config=config,
        execute=args.execute,
        max_requests=args.max_requests,
        max_records=args.max_records,
        run_id=args.run_id,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        summary = result.get("summary", {})
        print(f"run_id={args.run_id}")
        print(f"execute={args.execute}")
        print(f"configured_targets={summary.get('configured_targets')}")
        print(f"completed_datasets={','.join(summary.get('completed_datasets', []))}")
        print(f"failed_datasets={','.join(summary.get('failed_datasets', []))}")
        print(f"bronze_records={len(result.get('bronze_records', []))}")
        print(f"summary_report={result['tracked_summary_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
