from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.apply_adjustment_factors import ERROR_STATUSES, apply_adjustment_factors_to_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply local verified adjustment factors to adjusted OHLC columns.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--factors", required=True)
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol allowlist.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only. This is the default.")
    parser.add_argument("--execute", action="store_true", help="Mutate adjusted columns for rows with usable factors.")
    args = parser.parse_args()

    if args.dry_run and args.execute:
        result = {
            "status": "invalid_request",
            "reasons": ["Use either --dry-run or --execute, not both."],
            "dry_run": True,
            "db_mutation_made": False,
        }
    else:
        result = apply_adjustment_factors_to_db(
            db_path=args.db_path,
            factor_path=args.factors,
            symbols=_parse_symbols(args.symbols),
            dry_run=not args.execute,
        )

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    if result["status"] in ERROR_STATUSES:
        return 1
    return 0


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
