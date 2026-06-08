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

from trading_agent.ingestion.parsers.vietcap_iq_gap_chart_parser import parse_vietcap_iq_gap_chart_payload


DEFAULT_DATASETS = [
    "vietcap_iq_gap_chart_fpt",
    "vietcap_iq_gap_chart_vnm",
    "vietcap_iq_gap_chart_vcb",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse saved Vietcap IQ gap-chart payloads into dry-run daily price bars.")
    parser.add_argument("--raw-base-dir", default="data/raw/source_probe/source=vietcap_iq")
    parser.add_argument("--output-base-dir", default="data/processed/dry_run/vietcap_iq_gap_chart")
    parser.add_argument("--datasets", default=",".join(DEFAULT_DATASETS), help="Comma-separated saved gap-chart datasets to parse.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    datasets = [item.strip() for item in str(args.datasets).split(",") if item.strip()]
    try:
        inputs = resolve_inputs(Path(args.raw_base_dir), datasets=datasets)
        results = [
            parse_vietcap_iq_gap_chart_payload(raw_path=raw_path, metadata_path=metadata_path)
            for _, raw_path, metadata_path in inputs
        ]
    except Exception as exc:
        print(f"vietcap_iq_gap_chart_dry_run_failed={exc}", file=sys.stderr)
        return 1

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_base_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_price_bars = pd.concat([result.daily_price_bars for result in results], ignore_index=True)
    price_bars_path = output_dir / "daily_price_bars.csv"
    report_path = output_dir / "validation_report.md"
    summary_path = output_dir / "validation_summary.json"

    daily_price_bars.to_csv(price_bars_path, index=False)
    summary = build_combined_summary(results, inputs=inputs, run_id=run_id, output_dir=output_dir)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(build_validation_report(summary, price_bars_path), encoding="utf-8")

    print(f"run_id={run_id}")
    print(f"output_dir={output_dir}")
    print(f"daily_price_bars={price_bars_path}")
    print(f"validation_report={report_path}")
    print(f"validation_summary={summary_path}")
    print(f"parsed_symbol_count={summary['parsed_symbol_count']}")
    print(f"total_bar_count={summary['total_bar_count']}")
    print(f"quality_pass_count={summary['quality_pass_count']}")
    print(f"quality_warn_count={summary['quality_warn_count']}")
    print(f"quality_fail_count={summary['quality_fail_count']}")
    print(f"coverage_by_symbol={json.dumps(summary['coverage_by_symbol'], ensure_ascii=False, sort_keys=True)}")
    return 0


def resolve_inputs(raw_base_dir: Path, *, datasets: list[str]) -> list[tuple[str, Path, Path]]:
    inputs: list[tuple[str, Path, Path]] = []
    missing: list[str] = []
    for dataset in datasets:
        found = find_latest_verified_gap_chart_payload(raw_base_dir, dataset=dataset)
        if found is None:
            missing.append(dataset)
            continue
        inputs.append((dataset, found[0], found[1]))
    if not inputs:
        raise FileNotFoundError(f"No verified Vietcap IQ gap-chart payloads found under {raw_base_dir}. Missing datasets: {', '.join(missing)}.")
    return inputs


def find_latest_verified_gap_chart_payload(base_dir: Path, *, dataset: str) -> tuple[Path, Path] | None:
    candidates: list[tuple[str, Path, Path]] = []
    metadata_paths = {
        *base_dir.glob(f"run_id=*/{dataset}/metadata.json"),
        *base_dir.glob(f"*/{dataset}/metadata.json"),
    }
    for metadata_path in metadata_paths:
        metadata = _read_metadata(metadata_path)
        if metadata.get("source_name") != "vietcap_iq":
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
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, raw_path, metadata_path = candidates[0]
    return raw_path, metadata_path


def build_combined_summary(
    results: list[Any],
    *,
    inputs: list[tuple[str, Path, Path]],
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    source_summaries = [result.validation_summary for result in results]
    reason_counts: dict[str, int] = {}
    warning_reason_counts: dict[str, int] = {}
    failure_reason_counts: dict[str, int] = {}
    coverage_by_symbol: dict[str, dict[str, Any]] = {}
    raw_paths: dict[str, str] = {}
    metadata_paths: dict[str, str] = {}

    for dataset, raw_path, metadata_path in inputs:
        raw_paths[dataset] = str(raw_path)
        metadata_paths[dataset] = str(metadata_path)

    for summary in source_summaries:
        for key, destination in [
            ("quality_reason_counts", reason_counts),
            ("quality_warning_reason_counts", warning_reason_counts),
            ("quality_failure_reason_counts", failure_reason_counts),
        ]:
            for reason, count in summary.get(key, {}).items():
                destination[reason] = destination.get(reason, 0) + int(count)
        for symbol, coverage in summary.get("coverage_by_symbol", {}).items():
            existing = coverage_by_symbol.get(symbol)
            if existing is None:
                coverage_by_symbol[symbol] = dict(coverage)
                continue
            existing["bar_count"] = int(existing.get("bar_count", 0)) + int(coverage.get("bar_count", 0))
            existing["start_trading_date"] = min(filter(None, [existing.get("start_trading_date"), coverage.get("start_trading_date")]))
            existing["end_trading_date"] = max(filter(None, [existing.get("end_trading_date"), coverage.get("end_trading_date")]))
            existing["quality_pass_count"] = int(existing.get("quality_pass_count", 0)) + int(coverage.get("quality_pass_count", 0))
            existing["quality_warn_count"] = int(existing.get("quality_warn_count", 0)) + int(coverage.get("quality_warn_count", 0))
            existing["quality_fail_count"] = int(existing.get("quality_fail_count", 0)) + int(coverage.get("quality_fail_count", 0))

    total_bar_count = sum(int(summary.get("daily_price_bars_count", 0)) for summary in source_summaries)
    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "source_name": "vietcap_iq",
        "parser_version": source_summaries[0].get("parser_version") if source_summaries else None,
        "schema_version": source_summaries[0].get("schema_version") if source_summaries else None,
        "datasets": [dataset for dataset, _, _ in inputs],
        "raw_paths": raw_paths,
        "metadata_paths": metadata_paths,
        "parsed_payloads": source_summaries,
        "parsed_symbol_count": len(coverage_by_symbol),
        "total_bar_count": total_bar_count,
        "daily_price_bars_count": total_bar_count,
        "coverage_by_symbol": coverage_by_symbol,
        "quality_pass_count": sum(int(summary.get("quality_pass_count", 0)) for summary in source_summaries),
        "quality_warn_count": sum(int(summary.get("quality_warn_count", 0)) for summary in source_summaries),
        "quality_fail_count": sum(int(summary.get("quality_fail_count", 0)) for summary in source_summaries),
        "quality_reason_counts": reason_counts,
        "quality_warning_reason_counts": warning_reason_counts,
        "quality_failure_reason_counts": failure_reason_counts,
        "limitations": [
            "Saved-payload parser only; no live endpoint call was performed.",
            "Adjusted and unadjusted price values are not separated in the observed payload.",
            "Dividend, split, corporate-action, and adjustment-factor fields are not visible.",
            "countBack=250 is limited recent history, not full history.",
            "No full-universe fetch, database write, migration, or backtest was performed.",
        ],
    }


def build_validation_report(summary: dict[str, Any], price_bars_path: Path) -> str:
    lines = [
        "# Vietcap IQ Gap-Chart Dry-Run Validation Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- output_dir: `{summary['output_dir']}`",
        f"- source_name: `{summary['source_name']}`",
        f"- parser_version: `{summary['parser_version']}`",
        f"- schema_version: `{summary['schema_version']}`",
        f"- daily_price_bars: `{price_bars_path}`",
        "",
        "## Inputs",
        "",
        "| Dataset | Raw path | Metadata path |",
        "|---|---|---|",
    ]
    for dataset in summary.get("datasets", []):
        lines.append(f"| `{dataset}` | `{summary['raw_paths'].get(dataset)}` | `{summary['metadata_paths'].get(dataset)}` |")

    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| Parsed symbols | {summary['parsed_symbol_count']} |",
            f"| Daily price bars | {summary['daily_price_bars_count']} |",
            f"| Quality pass rows | {summary['quality_pass_count']} |",
            f"| Quality warn rows | {summary['quality_warn_count']} |",
            f"| Quality fail rows | {summary['quality_fail_count']} |",
            "",
            "## Coverage By Symbol",
            "",
            "| Symbol | Bars | Start | End | Pass | Warn | Fail |",
            "|---|---:|---|---|---:|---:|---:|",
        ]
    )
    for symbol, coverage in sorted(summary.get("coverage_by_symbol", {}).items()):
        lines.append(
            f"| `{symbol}` | {coverage.get('bar_count')} | `{coverage.get('start_trading_date')}` | "
            f"`{coverage.get('end_trading_date')}` | {coverage.get('quality_pass_count')} | "
            f"{coverage.get('quality_warn_count')} | {coverage.get('quality_fail_count')} |"
        )

    lines.extend(["", "## Quality Reasons", ""])
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
    return "\n".join(lines) + "\n"


def _read_metadata(metadata_path: Path) -> dict[str, Any]:
    return json.loads(metadata_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
