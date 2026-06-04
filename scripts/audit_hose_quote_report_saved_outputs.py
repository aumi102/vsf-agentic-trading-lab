from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUOTE_REPORT_BASE = ROOT / "data/processed/dry_run/hose_quote_report"
DEFAULT_OUTPUT_PATH = ROOT / "data/processed/dry_run/hose_quote_report_saved_outputs_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit saved HOSE quote-report dry-run outputs without fetching live data.")
    parser.add_argument("--quote-report-base-dir", default=str(DEFAULT_QUOTE_REPORT_BASE))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(args.quote_report_base_dir)
    output_path = Path(args.output_path)
    summary = build_saved_outputs_audit(base_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"quote_report_base_dir={base_dir}")
    print(f"audit_output={output_path}")
    print(f"run_count={summary['run_count']}")
    print(f"units_unconfirmed_any={str(summary['units_unconfirmed_any']).lower()}")
    for run in summary["runs"]:
        print(
            "run_id={run_id} trading_dates={dates} data_statuses={statuses} rows={rows} stock_only_rows={stock_rows}".format(
                run_id=run["run_id"],
                dates=",".join(run["trading_dates"]) if run["trading_dates"] else "unknown",
                statuses=",".join(run["data_statuses"]) if run["data_statuses"] else "unknown",
                rows=run["daily_quote_reports_count"],
                stock_rows=run.get("stock_only_rows"),
            )
        )
    return 0


def build_saved_outputs_audit(base_dir: Path) -> dict[str, Any]:
    if not base_dir.exists():
        raise FileNotFoundError(f"Missing HOSE quote-report dry-run directory: {base_dir}")

    runs = []
    for run_dir in sorted(path for path in base_dir.iterdir() if path.is_dir() and path.name != "stock_only"):
        summary_path = run_dir / "validation_summary.json"
        if not summary_path.exists():
            continue
        runs.append(summarize_run(run_dir, summary_path))

    return {
        "quote_report_base_dir": str(base_dir),
        "run_count": len(runs),
        "runs": runs,
        "units_unconfirmed_any": any(run["units_unconfirmed"] for run in runs),
        "final_eod_semantics_confirmed": False,
        "historical_availability_confirmed": False,
        "live_data_fetched": False,
        "notes": [
            "This audit reads saved dry-run outputs only.",
            "Source units remain unconfirmed until HOSE UI/source documentation or mentor confirmation is recorded.",
            "Final EOD semantics and historical date availability remain unconfirmed.",
        ],
    }


def summarize_run(run_dir: Path, summary_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    parsed_payloads = summary.get("parsed_payloads") if isinstance(summary.get("parsed_payloads"), list) else []
    trading_dates = sorted({str(item.get("trading_date")) for item in parsed_payloads if item.get("trading_date")})
    data_statuses = sorted({str(item.get("data_status")) for item in parsed_payloads if item.get("data_status")})
    reason_counts = summary.get("quality_reason_counts") or {}
    stock_only_summary = read_stock_only_summary(run_dir / "stock_only" / "stock_only_filter_summary.json")

    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "validation_summary_path": str(summary_path),
        "trading_dates": trading_dates,
        "data_statuses": data_statuses,
        "daily_price_bars_count": int(summary.get("daily_price_bars_count", 0)),
        "daily_quote_reports_count": int(summary.get("daily_quote_reports_count", 0)),
        "market_ohlcv_snapshots_count": int(summary.get("market_ohlcv_snapshots_count", 0)),
        "quality_pass_count": int(summary.get("quality_pass_count", 0)),
        "quality_warn_count": int(summary.get("quality_warn_count", 0)),
        "quality_fail_count": int(summary.get("quality_fail_count", 0)),
        "quality_reason_counts": reason_counts,
        "units_unconfirmed": "warning_source_units_unconfirmed" in reason_counts,
        "stock_only_exists": stock_only_summary is not None,
        "stock_only_rows": stock_only_summary.get("stock_only_rows") if stock_only_summary else None,
        "stock_only_unique_symbols": stock_only_summary.get("stock_only_unique_symbols") if stock_only_summary else None,
        "excluded_rows": stock_only_summary.get("excluded_rows") if stock_only_summary else None,
        "excluded_unique_symbols": stock_only_summary.get("excluded_unique_symbols") if stock_only_summary else None,
        "stock_only_run_quality_status": stock_only_summary.get("run_quality_status") if stock_only_summary else None,
        "limitations": summary.get("limitations", []),
    }


def read_stock_only_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
