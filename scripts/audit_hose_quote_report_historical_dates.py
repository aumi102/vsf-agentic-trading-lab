from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from trading_agent.ingestion.parsers.hose_quote_report_parser import DATA_STATUS_FINAL, parse_hose_quote_report_payload
from trading_agent.source_adapters.base import AccessStatus
from trading_agent.source_adapters.config import ProbeTarget, load_probe_targets
from trading_agent.source_adapters.hose_adapter import HoseAdapter
from trading_agent.source_adapters.raw_store import RawProbeStore

from build_hose_quote_report_stock_only_dry_run import latest_run_dir, normalize_symbol_series


DEFAULT_OUTPUT_BASE = ROOT / "data/processed/dry_run/hose_quote_report_historical_audit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit HOSE quote-report availability across requested dates.")
    parser.add_argument("--dates", required=True, help="Comma-separated dates such as 2026-06-02,2026-06-03,2026-05-30.")
    parser.add_argument("--targets-config", default="config/source_probe_targets.local.json")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to data/processed/dry_run/hose_quote_report_historical_audit/<run_id>.")
    parser.add_argument("--listed-universe-dir", default="", help="Optional HOSE listed-universe all-pages dry-run directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_BASE / run_id
    dates = parse_dates(args.dates)

    try:
        targets = load_probe_targets(args.targets_config)
        base_target = select_quote_report_target(targets.get("hose", []))
        listed_universe_dir = Path(args.listed_universe_dir) if args.listed_universe_dir else discover_listed_universe_dir()
        summary = run_historical_audit(
            dates=dates,
            base_target=base_target,
            output_dir=output_dir,
            run_id=run_id,
            listed_universe_dir=listed_universe_dir,
        )
    except Exception as exc:
        print(f"hose_quote_report_historical_audit_failed={exc}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "historical_audit_summary.json"
    report_path = output_dir / "historical_audit_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(build_report(summary), encoding="utf-8")

    print(f"run_id={summary['run_id']}")
    print(f"output_dir={output_dir}")
    print(f"historical_audit_summary={summary_path}")
    print(f"historical_audit_report={report_path}")
    for date_result in summary["date_results"]:
        print(
            "date={date} status={status} full_rows={rows} stock_only_rows={stock_rows} fail_count={fail_count}".format(
                date=date_result["date"],
                status=date_result["status"],
                rows=date_result.get("full_row_count"),
                stock_rows=date_result.get("stock_only_row_count"),
                fail_count=date_result.get("quality_fail_count"),
            )
        )
    return 0


def parse_dates(value: str) -> list[str]:
    dates = [item.strip() for item in value.split(",") if item.strip()]
    if not dates:
        raise ValueError("At least one date is required.")
    for date in dates:
        datetime.strptime(date, "%Y-%m-%d")
    return dates


def select_quote_report_target(targets: list[ProbeTarget]) -> ProbeTarget:
    candidates = [
        target
        for target in targets
        if "quote_report" in target.dataset
        and "current_day" not in target.dataset
        and "quote_report" in target.name
        and "current_day" not in target.name
    ]
    if not candidates:
        candidates = [target for target in targets if "quote" in target.dataset or "quote" in target.name]
    if not candidates:
        raise ValueError("No HOSE quote-report target found in targets config.")
    return candidates[0]


def discover_listed_universe_dir() -> Path | None:
    base = ROOT / "data/processed/dry_run/hose_listed_universe_all_pages"
    if not base.exists():
        return None
    try:
        return latest_run_dir(base)
    except FileNotFoundError:
        return None


def run_historical_audit(
    *,
    dates: list[str],
    base_target: ProbeTarget,
    output_dir: Path,
    run_id: str,
    listed_universe_dir: Path | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_store = RawProbeStore(output_dir / "raw")
    adapter = HoseAdapter(raw_store=raw_store)
    listed_symbols = load_listed_symbols(listed_universe_dir) if listed_universe_dir else set()

    date_results = []
    for date in dates:
        target = target_for_date(base_target, date)
        result = adapter._probe_configured_target(target, symbols=[], start=date, end=date, run_id=run_id)
        date_result = summarize_probe_result(date=date, result=result)
        if result.access_status == AccessStatus.VERIFIED:
            date_result.update(parse_verified_payload(date=date, result=result, output_dir=output_dir, listed_symbols=listed_symbols))
        elif result.access_status == AccessStatus.REJECTED_RESPONSE:
            date_result.update(classify_empty_payload_if_present(result=result))
        date_results.append(date_result)

    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "requested_dates": dates,
        "targets_config": base_target.config_file,
        "target_name": base_target.name,
        "listed_universe_dir": str(listed_universe_dir) if listed_universe_dir else "",
        "live_data_fetched": True,
        "date_results": date_results,
        "status_counts": {str(key): int(value) for key, value in pd.Series([item["status"] for item in date_results]).value_counts().sort_index().items()},
        "db_backtest_blockers": [
            "source_units_unconfirmed",
            "final_eod_semantics_unconfirmed",
            "historical_non_trading_day_behavior_needs_review",
            "tradingBy_VNINDEX_coverage_unconfirmed",
        ],
    }


def target_for_date(base_target: ProbeTarget, date: str) -> ProbeTarget:
    return replace(
        base_target,
        name=f"{base_target.name}_{date}",
        dataset=f"{base_target.dataset}_{date}",
        url=replace_query_param(base_target.url, "date", date),
        expected_content_type_contains=base_target.expected_content_type_contains or ["application/json"],
        expected_body_startswith_json=True,
        reject_body_contains=base_target.reject_body_contains or ["Request Rejected", "The requested URL was rejected"],
        min_body_bytes=base_target.min_body_bytes or 2,
    )


def replace_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query_items = [(existing_key, existing_value) for existing_key, existing_value in parse_qsl(parts.query, keep_blank_values=True) if existing_key != key]
    query_items.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def summarize_probe_result(*, date: str, result: Any) -> dict[str, Any]:
    if result.access_status == AccessStatus.VERIFIED:
        status = "verified_json"
    elif result.access_status == AccessStatus.REJECTED_RESPONSE:
        status = "rejected_response"
    else:
        status = "error"
    return {
        "date": date,
        "status": status,
        "access_status": result.access_status.value,
        "http_status": result.http_status,
        "content_type": result.content_type,
        "raw_paths": result.raw_paths,
        "metadata_paths": result.metadata_paths,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def parse_verified_payload(*, date: str, result: Any, output_dir: Path, listed_symbols: set[str]) -> dict[str, Any]:
    if not result.raw_paths or not result.metadata_paths:
        return {"status": "error", "errors": ["verified_probe_missing_raw_or_metadata_path"]}

    raw_path = Path(result.raw_paths[0])
    metadata_path = Path(result.metadata_paths[0])
    payload = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    rows = payload.get("data")
    if isinstance(rows, list) and len(rows) == 0:
        return {
            "status": "empty_data",
            "full_row_count": 0,
            "full_unique_symbol_count": 0,
            "stock_only_row_count": 0,
            "stock_only_unique_symbol_count": 0,
            "excluded_symbol_count": 0,
        }
    if not isinstance(rows, list):
        return {"status": "error", "errors": ["verified_json_without_data_list"]}

    parse_result = parse_hose_quote_report_payload(raw_path=raw_path, metadata_path=metadata_path, data_status=DATA_STATUS_FINAL)
    quote_reports = parse_result.daily_quote_reports
    stock_symbols = normalize_symbol_series(quote_reports["symbol"])
    duplicate_count = int(quote_reports.assign(symbol_norm=stock_symbols).duplicated(
        subset=["symbol_norm", "trading_date", "data_status"],
        keep=False,
    ).sum())

    stock_only_count = None
    stock_only_unique = None
    excluded_count = None
    if listed_symbols:
        matched_mask = stock_symbols.isin(listed_symbols)
        stock_only = quote_reports[matched_mask]
        excluded = quote_reports[~matched_mask]
        stock_only_count = int(len(stock_only))
        stock_only_unique = int(normalize_symbol_series(stock_only["symbol"]).nunique())
        excluded_count = int(normalize_symbol_series(excluded["symbol"]).nunique())

    parsed_summary = {
        "date": date,
        "status": "verified_json",
        "full_row_count": int(len(quote_reports)),
        "full_unique_symbol_count": int(stock_symbols.nunique()),
        "stock_only_row_count": stock_only_count,
        "stock_only_unique_symbol_count": stock_only_unique,
        "excluded_symbol_count": excluded_count,
        "quality_pass_count": parse_result.validation_summary["quality_pass_count"],
        "quality_warn_count": parse_result.validation_summary["quality_warn_count"],
        "quality_fail_count": parse_result.validation_summary["quality_fail_count"],
        "duplicate_symbol_date_status_count": duplicate_count,
        "warning_reason_counts": parse_result.validation_summary.get("quality_warning_reason_counts", {}),
    }
    date_dir = output_dir / f"date={date}"
    date_dir.mkdir(parents=True, exist_ok=True)
    (date_dir / "parsed_summary.json").write_text(json.dumps(parsed_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return parsed_summary


def classify_empty_payload_if_present(*, result: Any) -> dict[str, Any]:
    if not result.raw_paths:
        return {}
    try:
        payload = json.loads(Path(result.raw_paths[0]).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(rows, list) and len(rows) == 0:
        return {
            "status": "empty_data",
            "full_row_count": 0,
            "full_unique_symbol_count": 0,
            "stock_only_row_count": 0,
            "stock_only_unique_symbol_count": 0,
            "excluded_symbol_count": 0,
        }
    return {}


def load_listed_symbols(listed_universe_dir: Path | None) -> set[str]:
    if listed_universe_dir is None:
        return set()
    path = listed_universe_dir / "symbol_universe.csv"
    if not path.exists():
        return set()
    frame = pd.read_csv(path)
    if "symbol" not in frame.columns:
        return set()
    return set(normalize_symbol_series(frame["symbol"]))


def build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# HOSE Quote Report Historical Availability Audit",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- output_dir: `{summary['output_dir']}`",
        f"- target_name: `{summary['target_name']}`",
        f"- listed_universe_dir: `{summary['listed_universe_dir'] or 'not available'}`",
        "",
        "## Date Results",
        "",
        "| Date | Status | HTTP | Full rows | Stock-only rows | Fail count |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in summary["date_results"]:
        lines.append(
            f"| `{item['date']}` | `{item['status']}` | {item.get('http_status')} | "
            f"{item.get('full_row_count')} | {item.get('stock_only_row_count')} | {item.get('quality_fail_count')} |"
        )
    lines.extend(
        [
            "",
            "## Blockers",
            "",
        ]
    )
    for blocker in summary["db_backtest_blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(
        [
            "",
            "No database migration, database write, or backtest is performed by this audit.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
