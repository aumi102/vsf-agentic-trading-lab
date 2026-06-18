from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.adjusted_readiness import get_adjusted_ohlc_readiness
from trading_agent.tools._store import DEFAULT_DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Check adjusted OHLC readiness for backtests.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols, e.g. FPT,VNM,VCB.")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()

    result = get_adjusted_ohlc_readiness(
        db_path=args.db_path,
        symbols=_parse_symbols(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    _print_coverage(result)
    _print_by_symbol(result)
    return 0 if result.get("backtest_gate") == "pass" else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _print_coverage(result: dict[str, object]) -> None:
    coverage = result.get("coverage")
    if not isinstance(coverage, dict):
        return
    print()
    print("coverage")
    print("metric | rows")
    print("--- | ---:")
    for key in [
        "total_rows",
        "adjusted_rows",
        "missing_adjusted_rows",
        "invalid_factor_rows",
        "invalid_ohlc_rows",
        "fail_quality_rows",
    ]:
        print(f"{key} | {coverage.get(key)}")


def _print_by_symbol(result: dict[str, object]) -> None:
    rows = result.get("by_symbol")
    if not isinstance(rows, list):
        return
    print()
    print("by_symbol")
    print("symbol | total | adjusted | missing | invalid_factor | invalid_ohlc | gate")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---")
    for item in rows:
        if not isinstance(item, dict):
            continue
        print(
            f"{item.get('symbol')} | {item.get('total_rows')} | {item.get('adjusted_rows')} | "
            f"{item.get('missing_adjusted_rows')} | {item.get('invalid_factor_rows')} | "
            f"{item.get('invalid_ohlc_rows')} | {item.get('backtest_gate')}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
