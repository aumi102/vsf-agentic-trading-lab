from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.hose_quote_report_parser import (
    DATA_STATUS_FINAL,
    DATA_STATUS_PROVISIONAL,
    parse_hose_quote_report_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse saved HOSE quote-report probe payloads into dry-run canonical CSV outputs.")
    parser.add_argument("--raw-path", default="", help="Optional raw HOSE quote-report JSON path.")
    parser.add_argument("--metadata-path", default="", help="Optional HOSE quote-report metadata JSON path.")
    parser.add_argument("--data-status", choices=[DATA_STATUS_FINAL, DATA_STATUS_PROVISIONAL], default="", help="Optional data status override.")
    parser.add_argument("--include-current-day", action="store_true", help="Also parse latest saved current-day quote-report sample as provisional.")
    parser.add_argument("--raw-base-dir", default="data/raw/source_probe/source=hose")
    parser.add_argument("--output-base-dir", default="data/processed/dry_run/hose_quote_report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inputs = [resolve_inputs(args, dataset="hose_daily_quote_report")]
        if args.include_current_day:
            inputs.append(resolve_inputs(args, dataset="hose_daily_quote_report_current_day", force_latest=True))

        results = []
        for raw_path, metadata_path, data_status in inputs:
            results.append(parse_hose_quote_report_payload(raw_path=raw_path, metadata_path=metadata_path, data_status=data_status))
    except Exception as exc:
        print(f"hose_quote_report_dry_run_failed={exc}", file=sys.stderr)
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_base_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_price_bars = pd.concat([result.daily_price_bars for result in results], ignore_index=True)
    daily_quote_reports = pd.concat([result.daily_quote_reports for result in results], ignore_index=True)
    market_ohlcv_snapshots = pd.concat([result.market_ohlcv_snapshots for result in results], ignore_index=True)

    price_bars_path = output_dir / "daily_price_bars.csv"
    quote_reports_path = output_dir / "daily_quote_reports.csv"
    snapshots_path = output_dir / "market_ohlcv_snapshots.csv"
    report_path = output_dir / "validation_report.md"
    summary_path = output_dir / "validation_summary.json"

    daily_price_bars.to_csv(price_bars_path, index=False)
    daily_quote_reports.to_csv(quote_reports_path, index=False)
    market_ohlcv_snapshots.to_csv(snapshots_path, index=False)

    summary = build_combined_summary(results, run_id=run_id, output_dir=output_dir)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(
        build_validation_report(summary, price_bars_path, quote_reports_path, snapshots_path),
        encoding="utf-8",
    )

    print(f"run_id={run_id}")
    print(f"output_dir={output_dir}")
    print(f"daily_price_bars={price_bars_path}")
    print(f"daily_quote_reports={quote_reports_path}")
    print(f"market_ohlcv_snapshots={snapshots_path}")
    print(f"validation_report={report_path}")
    print(f"validation_summary={summary_path}")
    print(f"daily_price_bars_count={summary['daily_price_bars_count']}")
    print(f"daily_quote_reports_count={summary['daily_quote_reports_count']}")
    print(f"market_ohlcv_snapshots_count={summary['market_ohlcv_snapshots_count']}")
    print(f"quality_pass_count={summary['quality_pass_count']}")
    print(f"quality_warn_count={summary['quality_warn_count']}")
    print(f"quality_fail_count={summary['quality_fail_count']}")
    return 0


def resolve_inputs(args: argparse.Namespace, *, dataset: str, force_latest: bool = False) -> tuple[Path, Path, str | None]:
    if not force_latest:
        raw_path = Path(args.raw_path) if args.raw_path else None
        metadata_path = Path(args.metadata_path) if args.metadata_path else None
        if raw_path is not None and metadata_path is None:
            metadata_path = raw_path.parent / "metadata.json"
        if metadata_path is not None and raw_path is None:
            metadata = _read_metadata(metadata_path)
            raw_path = Path(metadata.get("raw_path", metadata_path.parent / "payload.json"))
        if raw_path is not None and metadata_path is not None:
            return raw_path, metadata_path, args.data_status or None

    raw_path, metadata_path = find_latest_verified_hose_quote_report_payload(Path(args.raw_base_dir), dataset=dataset)
    if dataset == "hose_daily_quote_report_current_day":
        return raw_path, metadata_path, DATA_STATUS_PROVISIONAL
    return raw_path, metadata_path, args.data_status or None


def find_latest_verified_hose_quote_report_payload(base_dir: Path, *, dataset: str) -> tuple[Path, Path]:
    candidates: list[tuple[str, Path, Path]] = []
    for metadata_path in base_dir.glob("run_id=*/**/metadata.json"):
        metadata = _read_metadata(metadata_path)
        if metadata.get("source_name") != "hose":
            continue
        if metadata.get("dataset") != dataset:
            continue
        if metadata.get("access_status") != "verified" or metadata.get("status") != "success":
            continue
        raw_path = Path(metadata.get("raw_path", ""))
        if not raw_path.exists():
            raw_path = metadata_path.parent / "payload.json"
        if raw_path.exists():
            candidates.append((str(metadata.get("crawled_at") or metadata_path.stat().st_mtime), raw_path, metadata_path))

    if not candidates:
        raise FileNotFoundError(f"No verified HOSE quote-report source probe payload found for dataset={dataset} under {base_dir}.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, raw_path, metadata_path = candidates[0]
    return raw_path, metadata_path


def _read_metadata(metadata_path: Path) -> dict[str, Any]:
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def build_combined_summary(results: list[Any], *, run_id: str, output_dir: Path) -> dict[str, Any]:
    source_summaries = [result.validation_summary for result in results]
    reason_counts: dict[str, int] = {}
    warning_reason_counts: dict[str, int] = {}
    failure_reason_counts: dict[str, int] = {}
    for summary in source_summaries:
        for key, destination in [
            ("quality_reason_counts", reason_counts),
            ("quality_warning_reason_counts", warning_reason_counts),
            ("quality_failure_reason_counts", failure_reason_counts),
        ]:
            for reason, count in summary.get(key, {}).items():
                destination[reason] = destination.get(reason, 0) + int(count)

    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "source_name": "hose",
        "parser_version": source_summaries[0].get("parser_version") if source_summaries else None,
        "schema_version": source_summaries[0].get("schema_version") if source_summaries else None,
        "parsed_payloads": source_summaries,
        "daily_price_bars_count": sum(int(summary.get("daily_price_bars_count", 0)) for summary in source_summaries),
        "daily_quote_reports_count": sum(int(summary.get("daily_quote_reports_count", 0)) for summary in source_summaries),
        "market_ohlcv_snapshots_count": sum(int(summary.get("market_ohlcv_snapshots_count", 0)) for summary in source_summaries),
        "quality_pass_count": sum(int(summary.get("quality_pass_count", 0)) for summary in source_summaries),
        "quality_warn_count": sum(int(summary.get("quality_warn_count", 0)) for summary in source_summaries),
        "quality_fail_count": sum(int(summary.get("quality_fail_count", 0)) for summary in source_summaries),
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "limitations": [
            "Source units are not fully confirmed.",
            "Final EOD semantics are not fully confirmed.",
            "tradingBy=VNINDEX coverage is not fully confirmed.",
            "This dry run writes local files only; no database or backtest is performed.",
        ],
    }


def build_validation_report(summary: dict[str, Any], price_bars_path: Path, quote_reports_path: Path, snapshots_path: Path) -> str:
    lines = [
        "# HOSE Quote Report Dry-Run Validation Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- output_dir: `{summary['output_dir']}`",
        f"- source_name: `{summary['source_name']}`",
        f"- parser_version: `{summary['parser_version']}`",
        f"- schema_version: `{summary['schema_version']}`",
        f"- daily_price_bars: `{price_bars_path}`",
        f"- daily_quote_reports: `{quote_reports_path}`",
        f"- market_ohlcv_snapshots: `{snapshots_path}`",
        "",
        "## Parsed Payloads",
        "",
        "| Dataset | Trading date | Data status | JSON rows | Raw path |",
        "|---|---|---|---:|---|",
    ]
    for parsed in summary.get("parsed_payloads", []):
        lines.append(
            f"| `{parsed.get('dataset')}` | `{parsed.get('trading_date')}` | `{parsed.get('data_status')}` | "
            f"{parsed.get('json_row_count')} | `{parsed.get('raw_path')}` |"
        )

    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| Daily price bars | {summary['daily_price_bars_count']} |",
            f"| Daily quote reports | {summary['daily_quote_reports_count']} |",
            f"| Market OHLCV snapshots | {summary['market_ohlcv_snapshots_count']} |",
            f"| Quality pass rows | {summary['quality_pass_count']} |",
            f"| Quality warn rows | {summary['quality_warn_count']} |",
            f"| Quality fail rows | {summary['quality_fail_count']} |",
            "",
            "## Quality Reasons",
            "",
        ]
    )
    reason_counts = summary.get("quality_reason_counts", {})
    if reason_counts:
        lines.extend(["| Reason | Count |", "|---|---:|"])
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("- none")

    lines.extend(["", "## Limitations", ""])
    for limitation in summary.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "- Current-day rows must be tagged `provisional`.",
            "- Completed-day rows are `final_candidate`, not confirmed final EOD data.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
