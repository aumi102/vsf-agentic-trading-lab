"""Rule-based agent CLI demo over the QuestDB market-data tools.

This is intentionally NOT an LLM yet — it proves the tool layer is real and
callable: it parses a simple intent, calls the QuestDB market-data tool and/or
the backtest, and prints the returned rows/metrics.

  python scripts/demo_deep_agent_questdb_cli.py "show latest FPT data"
  python scripts/demo_deep_agent_questdb_cli.py "backtest MA strategy for FPT from 2020 to 2025"
  python scripts/demo_deep_agent_questdb_cli.py "how many rows are in QuestDB"
  python scripts/demo_deep_agent_questdb_cli.py "list universe"
"""
from __future__ import annotations

import json
import re
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

_STOPWORDS = {
    "MA", "FROM", "TO", "IN", "HOW", "MANY", "ROWS", "ROW", "ARE", "THE", "DATA",
    "SHOW", "LATEST", "LAST", "PRICE", "FOR", "OF", "QUESTDB", "DB", "STRATEGY",
    "BACKTEST", "RUN", "GET", "LIST", "UNIVERSE", "SYMBOLS", "AND", "WITH", "A",
    "COUNT", "TOTAL", "HEALTH", "TABLE", "IS", "WHAT",
}


def extract_symbol(query: str) -> str | None:
    for token in re.findall(r"[A-Za-z0-9]{2,12}", query.upper()):
        if token in _STOPWORDS:
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", token) and not token.isdigit():
            return token
    return None


def extract_years(query: str) -> tuple[str, str]:
    years = re.findall(r"(20\d{2})", query)
    if len(years) >= 2:
        return f"{years[0]}-01-01", f"{years[1]}-12-31"
    if len(years) == 1:
        return f"{years[0]}-01-01", f"{years[0]}-12-31"
    return "2020-01-01", "2025-12-31"


def classify(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ("how many", "row count", "count(", "health", "total rows")):
        return "table_health"
    if any(k in q for k in ("backtest", "strategy", "ma cross", "ma strategy", "moving average")):
        return "backtest"
    if any(k in q for k in ("universe", "list symbol", "what symbols", "which symbols")):
        return "universe"
    if any(k in q for k in ("latest", "last", "current", "price", "show", "data", "quote")):
        return "latest_ohlcv"
    return "help"


def _emit(intent: str, tool_name: str, args: dict) -> None:
    print(f"[agent] intent={intent}  tool={tool_name}  args={json.dumps(args, ensure_ascii=False)}")


def handle(query: str) -> int:
    intent = classify(query)

    if intent == "table_health":
        _emit(intent, "get_table_health", {})
        res = tool.get_table_health()
        if res["status"] != "ok" or not res["rows"]:
            print(f"  error: {res['caveats']}")
            return 1
        row = res["rows"][0]
        print(f"  total_rows = {row.get('total_rows'):,}")
        print(f"  symbols    = {row.get('symbols'):,}")
        print(f"  date_range = {str(row.get('first_date'))[:10]} .. {str(row.get('last_date'))[:10]}")
        for adj in row.get("adjustment_status_breakdown", []):
            print(f"  adjustment[{adj.get('adjustment_status')}] = {adj.get('rows'):,}")
        return 0

    if intent == "universe":
        _emit(intent, "get_universe", {"limit": 20})
        res = tool.get_universe(20)
        if res["status"] != "ok":
            print(f"  error: {res['caveats']}")
            return 1
        print(f"  {'symbol':<8} {'rows':>7}  first        last")
        for row in res["rows"]:
            print(f"  {row['symbol']:<8} {row['rows']:>7}  {str(row['first_date'])[:10]}  {str(row['last_date'])[:10]}")
        return 0

    symbol = extract_symbol(query)
    if intent == "latest_ohlcv":
        if not symbol:
            print("  could not find a symbol in the request.")
            return 1
        _emit(intent, "get_latest_ohlcv", {"symbol": symbol})
        res = tool.get_latest_ohlcv(symbol)
        if res["status"] != "ok" or res["row_count"] == 0:
            print(f"  no data for {symbol}: {res['caveats']}")
            return 1
        r = res["rows"][0]
        print(f"  {symbol} @ {str(r['trade_date'])[:10]} ({r.get('exchange')})")
        print(f"    open={r['open']} high={r['high']} low={r['low']} close={r['close']}")
        print(f"    adjusted_close={r['adjusted_close']} volume={r['volume']} value={r['value']}")
        print(f"    adjustment_status={r['adjustment_status']} quality={r['quality_status']}")
        return 0

    if intent == "backtest":
        if not symbol:
            print("  could not find a symbol in the request.")
            return 1
        start, end = extract_years(query)
        _emit(intent, "get_ohlcv_window+run_ma_cross_backtest", {"symbol": symbol, "start": start, "end": end})
        fetched = tool.get_ohlcv_window(symbol, start, end, adjusted=True)
        if fetched["status"] != "ok" or fetched["row_count"] == 0:
            print(f"  no data for {symbol} in {start}..{end}: {fetched['caveats']}")
            return 1
        df = pd.DataFrame(fetched["rows"])
        print(f"  loaded {len(df)} adjusted bars from QuestDB")
        result = run_ma_cross_backtest(df)
        print()
        print(format_report(symbol, result))
        return 0

    print("I can: 'show latest <SYM> data', 'backtest MA strategy for <SYM> from <Y1> to <Y2>',")
    print("       'how many rows are in QuestDB', 'list universe'.")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print('Usage: demo_deep_agent_questdb_cli.py "show latest FPT data"')
        return 1
    query = " ".join(argv)
    print(f'> "{query}"')
    return handle(query)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
