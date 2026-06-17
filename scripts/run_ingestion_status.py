from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.status import get_ingestion_status
from trading_agent.tools._store import DEFAULT_DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local ingestion/store status.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols, e.g. FPT,VNM,VCB.")
    args = parser.parse_args()

    result = get_ingestion_status(db_path=args.db_path, symbols=_parse_symbols(args.symbols))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    _print_table_counts(result)
    _print_latest_runs(result)
    _print_watermarks(result)
    _print_freshness(result)
    return 0 if result["status"] in {"ok", "quality_warn"} else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _print_table_counts(result: dict[str, object]) -> None:
    counts = result.get("table_counts")
    if not isinstance(counts, dict):
        return
    print()
    print("table_counts")
    print("table | rows")
    print("--- | ---:")
    for table, rows in counts.items():
        print(f"{table} | {rows}")


def _print_latest_runs(result: dict[str, object]) -> None:
    runs = result.get("latest_source_runs")
    if not isinstance(runs, list):
        return
    print()
    print("latest_source_runs")
    print("started_at | source | mode | status | symbols_loaded")
    print("--- | --- | --- | --- | ---")
    for item in runs:
        if not isinstance(item, dict):
            continue
        print(
            f"{item.get('started_at')} | {item.get('source')} | {item.get('mode')} | "
            f"{item.get('status')} | {','.join(item.get('symbols_loaded') or [])}"
        )


def _print_watermarks(result: dict[str, object]) -> None:
    watermarks = result.get("watermarks")
    if not isinstance(watermarks, list):
        return
    print()
    print("watermarks")
    print("symbol | source | last_trade_date | row_count")
    print("--- | --- | --- | ---:")
    for item in watermarks:
        if not isinstance(item, dict):
            continue
        print(f"{item.get('symbol')} | {item.get('source')} | {item.get('last_trade_date')} | {item.get('row_count')}")


def _print_freshness(result: dict[str, object]) -> None:
    freshness = result.get("freshness")
    if not isinstance(freshness, dict):
        return
    stale = freshness.get("symbols_stale") or []
    print()
    print("freshness")
    print(f"latest_trade_date={freshness.get('latest_trade_date')}")
    print(f"symbols_stale={','.join(stale) if stale else '-'}")


if __name__ == "__main__":
    raise SystemExit(main())
