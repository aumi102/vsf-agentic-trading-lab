from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.fred_observation_parser import parse_fred_observations_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse the latest FRED observations probe payload into dry-run canonical CSV outputs.")
    parser.add_argument("--raw-path", default="", help="Optional raw FRED observations JSON path.")
    parser.add_argument("--metadata-path", default="", help="Optional FRED metadata JSON path.")
    parser.add_argument("--raw-base-dir", default="data/raw/source_probe/source=fred")
    parser.add_argument("--output-base-dir", default="data/processed/dry_run/fred_observations")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw_path, metadata_path = resolve_inputs(args)
        result = parse_fred_observations_payload(raw_path=raw_path, metadata_path=metadata_path)
    except Exception as exc:
        print(f"fred_observations_dry_run_failed={exc}", file=sys.stderr)
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_base_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    macro_series_path = output_dir / "macro_series.csv"
    macro_observations_path = output_dir / "macro_observations.csv"
    report_path = output_dir / "validation_report.md"
    summary_path = output_dir / "validation_summary.json"

    result.macro_series.to_csv(macro_series_path, index=False)
    result.macro_observations.to_csv(macro_observations_path, index=False)
    summary = {**result.validation_summary, "run_id": run_id, "output_dir": str(output_dir)}
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(build_validation_report(summary, macro_series_path, macro_observations_path), encoding="utf-8")

    print(f"run_id={run_id}")
    print(f"raw_path={raw_path}")
    print(f"metadata_path={metadata_path}")
    print(f"macro_series={macro_series_path}")
    print(f"macro_observations={macro_observations_path}")
    print(f"validation_report={report_path}")
    print(f"validation_summary={summary_path}")
    print(f"quality_pass_count={summary['quality_pass_count']}")
    print(f"quality_warn_count={summary['quality_warn_count']}")
    print(f"quality_fail_count={summary['quality_fail_count']}")
    return 0


def resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    raw_path = Path(args.raw_path) if args.raw_path else None
    metadata_path = Path(args.metadata_path) if args.metadata_path else None

    if raw_path is not None and metadata_path is None:
        metadata_path = raw_path.parent / "metadata.json"
    if metadata_path is not None and raw_path is None:
        metadata = _read_metadata(metadata_path)
        raw_path = Path(metadata.get("raw_path", metadata_path.parent / "payload.json"))
    if raw_path is not None and metadata_path is not None:
        return raw_path, metadata_path

    return find_latest_verified_fred_payload(Path(args.raw_base_dir))


def find_latest_verified_fred_payload(base_dir: Path) -> tuple[Path, Path]:
    candidates: list[tuple[str, Path, Path]] = []
    for metadata_path in base_dir.glob("run_id=*/**/metadata.json"):
        metadata = _read_metadata(metadata_path)
        if metadata.get("source_name") != "fred":
            continue
        if metadata.get("access_status") != "verified" or metadata.get("status") != "success":
            continue
        raw_path = Path(metadata.get("raw_path", ""))
        if not raw_path.exists():
            raw_path = metadata_path.parent / "payload.json"
        if raw_path.exists():
            candidates.append((str(metadata.get("crawled_at") or metadata_path.stat().st_mtime), raw_path, metadata_path))

    if not candidates:
        raise FileNotFoundError(f"No verified FRED source probe payload found under {base_dir}.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, raw_path, metadata_path = candidates[0]
    return raw_path, metadata_path


def _read_metadata(metadata_path: Path) -> dict[str, Any]:
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def build_validation_report(summary: dict[str, Any], macro_series_path: Path, macro_observations_path: Path) -> str:
    reason_counts = summary.get("quality_reason_counts", {})
    lines = [
        "# FRED Observations Dry-Run Validation Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- source_name: `{summary['source_name']}`",
        f"- dataset: `{summary['dataset']}`",
        f"- series_id: `{summary.get('series_id')}`",
        f"- raw_path: `{summary['raw_path']}`",
        f"- metadata_path: `{summary['metadata_path']}`",
        f"- raw_content_hash: `{summary['raw_content_hash']}`",
        f"- parser_version: `{summary['parser_version']}`",
        f"- schema_version: `{summary['schema_version']}`",
        f"- macro_series: `{macro_series_path}`",
        f"- macro_observations: `{macro_observations_path}`",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| JSON observations | {summary['json_observation_count']} |",
        f"| Macro series rows | {summary['macro_series_count']} |",
        f"| Macro observation rows | {summary['macro_observation_count']} |",
        f"| Quality pass rows | {summary['quality_pass_count']} |",
        f"| Quality warn rows | {summary['quality_warn_count']} |",
        f"| Quality fail rows | {summary['quality_fail_count']} |",
        f"| Exact duplicate macro observation rows | {summary['exact_duplicate_macro_observation_count']} |",
        f"| Row count matches JSON observations | {summary['row_count_matches_json_observations']} |",
        "",
        "## Quality Reasons",
        "",
    ]
    if reason_counts:
        lines.extend(["| Reason | Count |", "|---|---:|"])
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Point-In-Time Notes",
            "",
            "- FRED `realtime_start` and `realtime_end` are preserved for vintage-aware joins.",
            "- Do not use revised macro observations in future backtests unless the revision was available as of the simulated date.",
            "",
            "## Terms Notes",
            "",
            summary.get("terms_notes") or "none",
            "",
            "## Limitations",
            "",
            "- This is a dry run only. No database write or migration was performed.",
            "- The current raw sample is a tiny configured probe, not a full macro ingestion run.",
            "- FRED is global macro context only and is not stock OHLCV.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
