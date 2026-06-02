from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.vnstock_ingestion import VnstockIngestion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest vnstock P0/P1 datasets into local raw and silver outputs.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, for example FPT,VNM")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    if not symbols:
        print("No valid symbols supplied.", file=sys.stderr)
        return 2

    result = VnstockIngestion().run(symbols=symbols, start=args.start, end=args.end)
    print(f"run_id={result.run_id}")
    for table, path in result.outputs.items():
        print(f"{table}={path}")
    if result.warnings:
        print("warnings:")
        for warning in result.warnings:
            print(f"- {warning}")

    blocking = [quality for quality in result.quality_results if quality.table in {"securities", "daily_prices"} and quality.quality_status == "fail"]
    if blocking:
        print("blocking quality failures:")
        for quality in blocking:
            print(f"- {quality.table}: {', '.join(quality.failed_gates)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
