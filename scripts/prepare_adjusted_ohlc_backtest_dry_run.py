from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.backtest.adjusted_ohlc_backtest_dry_run_preparation import (
    build_backtest_input_preview,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an adjusted OHLC feed preview into a backtest input dry-run preview."
    )
    parser.add_argument("--feed-preview", required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--transaction-cost-bps", type=float, required=True)
    parser.add_argument("--slippage-bps", type=float, required=True)
    parser.add_argument("--exchange", required=True)
    parser.add_argument("--max-rows", type=int, default=20)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--fixture-signal-mode", action="store_true")
    args = parser.parse_args()

    result = build_backtest_input_preview(
        feed_preview_path=Path(args.feed_preview),
        symbols=_parse_symbols(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
        transaction_cost_bps=args.transaction_cost_bps,
        slippage_bps=args.slippage_bps,
        exchange=args.exchange,
        max_rows=args.max_rows,
        fixture_signal_mode=args.fixture_signal_mode,
    )
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
