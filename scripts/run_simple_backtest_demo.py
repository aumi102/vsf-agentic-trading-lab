"""Run the transparent self-implemented backtest engine and compare to Backtrader.

  python scripts\run_simple_backtest_demo.py --symbol FPT --strategy ma20_ma50 \
      --start-date 2020-01-01 --end-date 2025-12-31 --slippage-bps 0

Read-only: loads persisted adjusted OHLCV from QuestDB, runs the self-implemented
engine in-process, and looks up the persisted Backtrader metrics for the same
symbol/strategy/slippage to show a side-by-side comparison. It NEVER runs live
Backtrader and never mutates QuestDB.
"""
from __future__ import annotations

import argparse
import json
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

from trading_agent.backtest import simple_engine as engine  # noqa: E402
from trading_agent.tools import questdb_backtest_result_tool as bt_tool  # noqa: E402


def _fmt(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):,.2f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _compare_table(simple_metrics: dict, persisted: dict | None) -> str:
    rows = [
        ("final_value", "final_value", ""),
        ("total_return_pct", "total_return_pct", "%"),
        ("annualized_return_pct", "annualized_return_pct", "%"),
        ("max_drawdown_pct", "max_drawdown_pct", "%"),
        ("sharpe_ratio", "sharpe_ratio", ""),
        ("closed_trades", "closed_trades", ""),
        ("win_rate_pct", "win_rate_pct", "%"),
    ]
    lines = [
        "",
        "Comparison: self-implemented engine vs persisted Backtrader (same symbol/strategy/slippage)",
        f"  {'metric':<22} | {'simple_engine':>16} | {'backtrader':>16}",
        "  " + "-" * 60,
    ]
    for label, key, suffix in rows:
        simple_val = simple_metrics.get(key)
        persisted_val = persisted.get(key) if persisted else None
        lines.append(f"  {label:<22} | {_fmt(simple_val, suffix):>16} | {_fmt(persisted_val, suffix):>16}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the transparent backtest engine and compare to Backtrader.")
    parser.add_argument("--symbol", default="FPT")
    parser.add_argument("--strategy", default="ma20_ma50", choices=sorted(engine.STRATEGIES))
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--commission", type=float, default=engine.DEFAULT_COMMISSION)
    parser.add_argument("--start-cash", type=float, default=engine.DEFAULT_START_CASH)
    parser.add_argument("--target-percent", type=float, default=engine.DEFAULT_TARGET_PERCENT)
    parser.add_argument("--questdb-url", default=engine.DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbol = args.symbol.strip().upper()
    try:
        bars, data_caveats = engine.load_bars_from_questdb(
            symbol, args.start_date, args.end_date, adjusted=True, url=args.questdb_url
        )
        if not bars:
            print(f"error=no bars for {symbol} in {args.start_date}..{args.end_date}", file=sys.stderr)
            return 2
        exchange = engine.fetch_exchange(symbol, url=args.questdb_url)
        out = engine.run_simple_backtest(
            bars,
            symbol=symbol,
            strategy=args.strategy,
            start_cash=args.start_cash,
            commission=args.commission,
            slippage_bps=args.slippage_bps,
            target_percent=args.target_percent,
            exchange=exchange,
        )
    except Exception as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    persisted_res = bt_tool.get_latest_backtest_metrics(
        symbol, strategy_id=args.strategy, slippage_bps=args.slippage_bps, url=args.questdb_url
    )
    persisted = persisted_res["rows"][0] if persisted_res.get("status") == "ok" and persisted_res.get("rows") else None

    if args.json:
        payload = {
            "simple_engine": out.to_dict(),
            "backtrader_persisted": persisted,
            "data_caveats": data_caveats,
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(engine.format_report(out))
    print(_compare_table(out.metrics, persisted))
    print("")
    print("Why the two differ (expected, explainable):")
    print("  * Backtrader marks/sizes via its broker; the simple engine sizes from close[t] and fills at open[t+1].")
    print("  * Trade counting differs: Backtrader counts closed Trade objects; the simple engine counts long round trips.")
    print("  * Both use the SAME adjusted daily_prices rows, 0.95 target, 0.1% commission and bps slippage.")
    if persisted is None:
        print("  * No persisted Backtrader row found for this exact symbol/strategy/slippage; comparison column is n/a.")
    print("")
    print("Caveats:")
    for caveat in out.caveats:
        print(f"  - {caveat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
