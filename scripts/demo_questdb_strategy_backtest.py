"""Demo: pull adjusted OHLCV from QuestDB and run the MA-cross backtest.

  python scripts/demo_questdb_strategy_backtest.py --symbol FPT \
      --start-date 2020-01-01 --end-date 2025-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

import pandas as pd  # noqa: E402

from trading_agent.strategies.simple_ma_cross import format_report, run_ma_cross_backtest  # noqa: E402
from trading_agent.tools import questdb_market_data_tool as tool  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="QuestDB-backed MA-cross backtest demo.")
    p.add_argument("--symbol", required=True)
    p.add_argument("--start-date", default="2020-01-01")
    p.add_argument("--end-date", default="2025-12-31")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=50)
    p.add_argument("--cost-bps", type=float, default=15.0)
    p.add_argument("--raw", action="store_true", help="Use raw OHLC instead of adjusted.")
    p.add_argument("--questdb-url", default=tool.DEFAULT_URL)
    p.add_argument("--show-trades", type=int, default=0, help="Print the last N trades.")
    args = p.parse_args()

    symbol = args.symbol.strip().upper()
    fetched = tool.get_ohlcv_window(
        symbol, args.start_date, args.end_date, adjusted=not args.raw, url=args.questdb_url
    )
    if fetched["status"] != "ok":
        print(f"QuestDB error: {fetched['caveats']}", file=sys.stderr)
        return 1
    if fetched["row_count"] == 0:
        print(f"No data for {symbol} in {args.start_date}..{args.end_date}. {fetched['caveats']}", file=sys.stderr)
        return 1

    df = pd.DataFrame(fetched["rows"])
    print(f"Loaded {len(df)} bars for {symbol} from QuestDB ({'raw' if args.raw else 'adjusted'} close).")
    result = run_ma_cross_backtest(df, fast=args.fast, slow=args.slow, cost_bps=args.cost_bps)
    print()
    print(format_report(symbol, result))

    if args.show_trades > 0 and result.get("status") == "ok":
        trades = result["trades"][-args.show_trades :]
        print(f"\nLast {len(trades)} trades:")
        print(f"  {'entry':<12} {'exit':<12} {'ret%':>8} {'bars':>5}")
        for t in trades:
            print(f"  {t['entry_date']:<12} {t['exit_date']:<12} {t['return_pct']:>8.2f} {t['bars_held']:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
