from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.db.build_mvp_store import DEFAULT_DB_PATH, DEFAULT_RAW_BASE_DIR, build_mvp_store, discover_gap_chart_payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local SQLite MVP store for agent tool demos.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to all locally available gap-chart payloads.")
    parser.add_argument("--raw-base-dir", default=str(DEFAULT_RAW_BASE_DIR))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    requested = [item.strip().upper() for item in args.symbols.split(",") if item.strip()] or None
    available = sorted(discover_gap_chart_payloads(args.raw_base_dir))
    summary = build_mvp_store(symbols=requested, raw_base_dir=args.raw_base_dir, db_path=args.db_path)
    print(f"available_symbols={','.join(available)}")
    print(f"symbols_loaded={','.join(summary['symbols_loaded'])}")
    if summary["symbols_missing"]:
        print(f"symbols_missing={','.join(summary['symbols_missing'])}")
    print(f"storage={summary['storage']}")
    print(f"db_path={summary['db_path']}")
    print(f"row_counts={json.dumps(summary['row_counts'], sort_keys=True)}")
    print(f"date_ranges={json.dumps(summary['date_ranges'], sort_keys=True)}")
    print(f"quality={json.dumps(summary['quality'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
