from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.backtest.adjusted_ohlc_feed_readiness import build_adjusted_ohlc_feed_preview


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview the adjusted OHLC backtest feed contract.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--audit-report", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--allow-demo-db", action="store_true")
    args = parser.parse_args()

    result = build_adjusted_ohlc_feed_preview(
        db_path=Path(args.db_path),
        symbols=_parse_symbols(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
        audit_report_path=Path(args.audit_report),
        max_rows=args.max_rows,
        allow_demo_db=args.allow_demo_db,
    )
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
