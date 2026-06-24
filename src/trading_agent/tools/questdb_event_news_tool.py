"""Read-only QuestDB tools for event/news/disclosure items."""
from __future__ import annotations

import re
from typing import Any

from trading_agent.tools import questdb_market_data_tool as market

DEFAULT_URL = market.DEFAULT_URL
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")


def _envelope(status: str, rows: list[dict[str, Any]], sql: Any, caveats: list[str], tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "rows": rows,
        "data": rows,
        "row_count": len(rows),
        "source": "questdb",
        "sql": sql,
        "tool_calls": [{"tool": tool_name, "args": args, "status": status, "row_count": len(rows)}],
        "caveats": list(dict.fromkeys(caveats)),
    }


def _validate_symbol(symbol: str) -> str | None:
    sym = (symbol or "").strip().upper()
    return sym if SYMBOL_RE.fullmatch(sym) else None


def _table_exists(table: str, url: str) -> bool:
    res = market.query_questdb("SHOW TABLES", url=url)
    return res.get("status") == "ok" and table in {str(row.get("table_name")) for row in res.get("rows", [])}


def get_symbol_event_news(symbol: str, limit: int = 5, url: str = DEFAULT_URL) -> dict[str, Any]:
    """Return latest parsed official disclosure/event records for a symbol.

    These records are official disclosure items when available, not broad market
    news. The function never uses OHLCV as a proxy.
    """
    sym = _validate_symbol(symbol)
    args = {"symbol": symbol, "limit": limit}
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"], "get_symbol_event_news", args)
    if not _table_exists("event_news_items", url):
        return _envelope(
            "unavailable",
            [],
            "",
            ["event/news table unavailable; run scripts/probe_event_news_sources.py and scripts/ingest_event_news_to_questdb.py first"],
            "get_symbol_event_news",
            args,
        )
    safe_limit = max(1, min(int(limit), 50))
    sql = (
        "SELECT published_at, symbol, title, summary, source, source_url, category, raw_id, run_id, quality_status "
        "FROM event_news_items "
        f"WHERE symbol = '{sym}' ORDER BY published_at DESC LIMIT {safe_limit}"
    )
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok":
        return _envelope("error", [], sql, res.get("caveats", []), "get_symbol_event_news", args)
    rows = res.get("rows", [])
    if not rows:
        return _envelope(
            "unavailable",
            [],
            sql,
            [f"event/news data not ingested for {sym}; OHLCV was not used as a proxy"],
            "get_symbol_event_news",
            {"symbol": sym, "limit": safe_limit},
        )
    caveats = [
        "event/news layer currently contains official disclosure records only, not general news",
        "records are sourced from controlled probe output and remain demo-scope",
    ]
    return _envelope("ok", rows, sql, caveats, "get_symbol_event_news", {"symbol": sym, "limit": safe_limit})
