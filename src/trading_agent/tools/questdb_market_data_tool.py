"""Read-only QuestDB market-data tool layer for the agent / backend / backtest.

Every function returns a structured dict:
  {
    "status": "ok" | "error",
    "rows": [ {col: value, ...}, ... ],
    "row_count": int,
    "source": "questdb",
    "sql": "<executed sql>",
    "caveats": [ ... ],
  }

Only SELECT / SHOW statements are allowed through query_questdb so the agent
cannot mutate the table by accident.
"""
from __future__ import annotations

import os
import re
from typing import Any

from trading_agent.storage import questdb_client as qdb

DEFAULT_TABLE = os.environ.get("QUESTDB_TABLE", "daily_prices")
DEFAULT_URL = os.environ.get("QUESTDB_URL", qdb.DEFAULT_QUESTDB_URL)

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_READ_ONLY_RE = re.compile(r"^\s*(select|show|with|explain)\b", re.IGNORECASE)


def _result(status: str, rows: list[dict[str, Any]], sql: str, caveats: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "rows": rows,
        "row_count": len(rows),
        "source": "questdb",
        "sql": sql,
        "caveats": caveats,
    }


def _rows_to_dicts(columns: list[str], dataset: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row)) for row in dataset]


def query_questdb(sql: str, *, url: str = DEFAULT_URL) -> dict[str, Any]:
    """Run a read-only SQL statement and return structured rows."""
    if not _READ_ONLY_RE.match(sql or ""):
        return _result("error", [], sql, ["Only SELECT/SHOW/WITH/EXPLAIN statements are permitted."])
    try:
        with qdb.open_client() as client:
            columns, dataset = qdb.exec_rows(client, url, sql)
        return _result("ok", _rows_to_dicts(columns, dataset), sql, [])
    except Exception as exc:
        return _result("error", [], sql, [f"query_failed: {exc}"])


def get_universe(limit: int = 20, *, url: str = DEFAULT_URL, table: str = DEFAULT_TABLE) -> dict[str, Any]:
    """Distinct symbols present in the table with their row counts and date span."""
    limit = max(1, int(limit))
    sql = (
        f"SELECT symbol, count() AS rows, min(trade_date) AS first_date, "
        f"max(trade_date) AS last_date FROM {table} ORDER BY symbol LIMIT {limit}"
    )
    return query_questdb(sql, url=url)


def get_latest_ohlcv(symbol: str, *, url: str = DEFAULT_URL, table: str = DEFAULT_TABLE) -> dict[str, Any]:
    """Most recent bar for a symbol."""
    sym = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        return _result("error", [], "", [f"invalid_symbol: {symbol!r}"])
    sql = (
        f"SELECT trade_date, symbol, exchange, open, high, low, close, "
        f"adjusted_close, volume, value, adjustment_status, quality_status "
        f"FROM {table} WHERE symbol = '{sym}' ORDER BY trade_date DESC LIMIT 1"
    )
    result = query_questdb(sql, url=url)
    if result["status"] == "ok" and result["row_count"] == 0:
        result["caveats"].append(f"No rows for symbol '{sym}'. Has it been ingested?")
    return result


def get_ohlcv_window(
    symbol: str,
    start_date: str,
    end_date: str,
    adjusted: bool = True,
    *,
    url: str = DEFAULT_URL,
    table: str = DEFAULT_TABLE,
) -> dict[str, Any]:
    """OHLCV bars for a symbol over [start_date, end_date] inclusive, ascending."""
    sym = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        return _result("error", [], "", [f"invalid_symbol: {symbol!r}"])
    if not _DATE_RE.match(start_date or "") or not _DATE_RE.match(end_date or ""):
        return _result("error", [], "", ["dates must be YYYY-MM-DD"])
    price_cols = (
        "adjusted_open AS open, adjusted_high AS high, adjusted_low AS low, adjusted_close AS close"
        if adjusted
        else "open, high, low, close"
    )
    sql = (
        f"SELECT trade_date, symbol, {price_cols}, volume, value, adjustment_status "
        f"FROM {table} WHERE symbol = '{sym}' "
        f"AND trade_date >= '{start_date}' AND trade_date <= '{end_date}T23:59:59.999999Z' "
        f"AND quality_status = 'pass' ORDER BY trade_date ASC"
    )
    result = query_questdb(sql, url=url)
    caveat = "prices are adjusted_* columns" if adjusted else "prices are raw OHLC columns"
    if result["status"] == "ok":
        result["caveats"].append(caveat)
        if result["row_count"] == 0:
            result["caveats"].append(f"No pass-quality rows for '{sym}' in range.")
    return result


def get_table_health(*, url: str = DEFAULT_URL, table: str = DEFAULT_TABLE) -> dict[str, Any]:
    """One-row health summary: totals, symbol count, date span, adjustment mix."""
    sql = (
        f"SELECT count() AS total_rows, count_distinct(symbol) AS symbols, "
        f"min(trade_date) AS first_date, max(trade_date) AS last_date FROM {table}"
    )
    result = query_questdb(sql, url=url)
    if result["status"] == "ok":
        adj = query_questdb(f"SELECT adjustment_status, count() AS rows FROM {table}", url=url)
        if adj["status"] == "ok" and result["rows"]:
            result["rows"][0]["adjustment_status_breakdown"] = adj["rows"]
        result["caveats"].append(f"table={table}")
    return result
