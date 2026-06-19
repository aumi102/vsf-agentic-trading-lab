from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.reviewed_adjusted_price_evidence import (
    ERROR_STATUSES,
    run_reviewed_adjusted_price_evidence_intake,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reviewed adjusted-price evidence intake.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--validation-output", default=None)
    parser.add_argument("--factor-output", default=None)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Plan only. This is the default.")
    parser.add_argument("--execute", action="store_true", help="Apply factors to a local DB and run readiness.")
    parser.add_argument("--allow-network", action="store_true", help="Blocked; live evidence intake is not implemented.")
    args = parser.parse_args()

    result = run_reviewed_adjusted_price_evidence_intake(
        manifest_path=args.manifest,
        payload_path=args.payload,
        symbols=_parse_symbols(args.symbols),
        validation_output_path=args.validation_output,
        factor_output_path=args.factor_output,
        db_path=args.db_path,
        dry_run=args.dry_run or not args.execute,
        execute=args.execute,
        allow_network=args.allow_network,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 1 if result["status"] in ERROR_STATUSES else 0


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
