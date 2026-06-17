from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from trading_agent.tools._store import DEFAULT_DB_PATH


OBSERVED_TABLES = [
    "source_runs",
    "raw_source_payloads",
    "ingestion_watermarks",
    "securities",
    "daily_prices",
    "feature_snapshots",
    "signals",
]


def get_ingestion_status(
    db_path: str | Path = DEFAULT_DB_PATH,
    symbols: list[str] | None = None,
    latest_runs_limit: int = 5,
) -> dict[str, Any]:
    path = Path(db_path)
    requested = _normalize_symbols(symbols or [])
    base = {
        "status": "missing_store",
        "db_path": str(path),
        "latest_source_runs": [],
        "watermarks": [],
        "symbols": [],
        "table_counts": {},
        "lineage": {"daily_prices_missing_source_id_raw_path": 0},
        "freshness": {"latest_trade_date": None, "symbols_stale": []},
        "tool_readiness": {
            "market_data": "missing_store",
            "features": "missing_store",
            "signals": "missing_store",
            "backtest": "missing_store",
        },
        "caveats": [],
    }
    if not path.exists():
        base["caveats"] = [f"MVP store not found: {path}"]
        return base

    try:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        with con:
            tables = _table_names(con)
            missing_tables = [table for table in OBSERVED_TABLES if table not in tables]
            counts = {
                table: _count_table(con, table) if table in tables else None
                for table in OBSERVED_TABLES
            }
            base["table_counts"] = counts
            if missing_tables:
                base["status"] = "empty_store"
                base["caveats"] = [f"Missing expected tables: {', '.join(missing_tables)}."]
                return base

            symbols_rows = _symbols(con, requested)
            latest_trade_date = _latest_trade_date(symbols_rows)
            stale_symbols = [
                item["symbol"]
                for item in symbols_rows
                if latest_trade_date and item.get("latest_trade_date") and item["latest_trade_date"] < latest_trade_date
            ]
            missing_lineage = _missing_lineage(con, requested)
            readiness = _tool_readiness(con, requested, symbols_rows)
            caveats = _caveats(counts, requested, symbols_rows, missing_lineage)
            status = _overall_status(counts, missing_lineage)

            return {
                "status": status,
                "db_path": str(path),
                "latest_source_runs": _latest_source_runs(con, latest_runs_limit),
                "watermarks": _watermarks(con, requested),
                "symbols": symbols_rows,
                "table_counts": counts,
                "lineage": {"daily_prices_missing_source_id_raw_path": missing_lineage},
                "freshness": {
                    "latest_trade_date": latest_trade_date,
                    "symbols_stale": stale_symbols,
                },
                "tool_readiness": readiness,
                "caveats": caveats,
            }
    except sqlite3.Error as exc:
        base["status"] = "empty_store"
        base["caveats"] = [f"Unable to inspect store: {exc}"]
        return base


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def _count_table(con: sqlite3.Connection, table: str) -> int:
    row = con.execute(f"SELECT COUNT(*) AS rows FROM {table}").fetchone()
    return int(row["rows"] or 0)


def _latest_source_runs(con: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT run_id, source, mode, status, started_at, completed_at,
               symbols_requested_json, symbols_loaded_json, symbols_failed_json,
               allow_network
        FROM source_runs
        ORDER BY started_at DESC, run_id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [
        {
            "run_id": row["run_id"],
            "source": row["source"],
            "mode": row["mode"],
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "symbols_requested": _json_list(row["symbols_requested_json"]),
            "symbols_loaded": _json_list(row["symbols_loaded_json"]),
            "symbols_failed": _json_list(row["symbols_failed_json"]),
            "allow_network": bool(row["allow_network"]),
        }
        for row in rows
    ]


def _watermarks(con: sqlite3.Connection, symbols: list[str]) -> list[dict[str, Any]]:
    where, params = _symbol_filter_sql("symbol", symbols)
    rows = con.execute(
        f"""
        SELECT source, symbol, last_trade_date, last_run_id, updated_at, row_count
        FROM ingestion_watermarks
        {where}
        ORDER BY symbol, source
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _symbols(con: sqlite3.Connection, symbols: list[str]) -> list[dict[str, Any]]:
    where, params = _symbol_filter_sql("s.symbol", symbols)
    rows = con.execute(
        f"""
        SELECT s.symbol,
               s.security_id,
               s.exchange,
               s.issuer_name,
               COUNT(d.trade_date) AS daily_rows,
               MIN(d.trade_date) AS start_date,
               MAX(d.trade_date) AS latest_trade_date,
               SUM(CASE WHEN d.quality_status = 'fail' THEN 1 ELSE 0 END) AS fail_rows
        FROM securities s
        LEFT JOIN daily_prices d ON d.security_id = s.security_id AND d.symbol = s.symbol
        {where}
        GROUP BY s.symbol, s.security_id, s.exchange, s.issuer_name
        ORDER BY s.symbol
        """,
        params,
    ).fetchall()
    return [
        {
            "symbol": row["symbol"],
            "security_id": row["security_id"],
            "exchange": row["exchange"],
            "issuer_name": row["issuer_name"],
            "daily_rows": int(row["daily_rows"] or 0),
            "start_date": row["start_date"],
            "latest_trade_date": row["latest_trade_date"],
            "fail_rows": int(row["fail_rows"] or 0),
        }
        for row in rows
    ]


def _missing_lineage(con: sqlite3.Connection, symbols: list[str]) -> int:
    where, params = _symbol_filter_sql("symbol", symbols)
    prefix = "WHERE" if not where else f"{where} AND"
    row = con.execute(
        f"""
        SELECT COUNT(*) AS rows
        FROM daily_prices
        {prefix} (
            source_id IS NULL OR TRIM(source_id) = ''
            OR raw_path IS NULL OR TRIM(raw_path) = ''
        )
        """,
        params,
    ).fetchone()
    return int(row["rows"] or 0)


def _tool_readiness(
    con: sqlite3.Connection,
    requested: list[str],
    symbol_rows: list[dict[str, Any]],
) -> dict[str, str]:
    symbols = requested or [str(item["symbol"]) for item in symbol_rows]
    if not symbols:
        return {
            "market_data": "empty_store",
            "features": "empty_store",
            "signals": "empty_store",
            "backtest": "empty_store",
        }
    return {
        "market_data": _table_symbol_readiness(con, "daily_prices", "trade_date", symbols),
        "features": _table_symbol_readiness(con, "feature_snapshots", "as_of_date", symbols),
        "signals": _table_symbol_readiness(con, "signals", "as_of_date", symbols),
        "backtest": _backtest_readiness(con, symbols),
    }


def _table_symbol_readiness(con: sqlite3.Connection, table: str, date_column: str, symbols: list[str]) -> str:
    placeholders = ", ".join(["?"] * len(symbols))
    rows = con.execute(
        f"""
        SELECT symbol, COUNT({date_column}) AS rows
        FROM {table}
        WHERE symbol IN ({placeholders})
        GROUP BY symbol
        """,
        symbols,
    ).fetchall()
    found = {row["symbol"] for row in rows if int(row["rows"] or 0) > 0}
    return "ok" if set(symbols) <= found else "not_found"


def _backtest_readiness(con: sqlite3.Connection, symbols: list[str]) -> str:
    placeholders = ", ".join(["?"] * len(symbols))
    row = con.execute(
        f"""
        SELECT COUNT(*) AS rows
        FROM daily_prices
        WHERE symbol IN ({placeholders}) AND quality_status != 'fail'
        """,
        symbols,
    ).fetchone()
    return "ok" if int(row["rows"] or 0) > 0 else "not_found"


def _caveats(
    counts: dict[str, int | None],
    requested: list[str],
    symbol_rows: list[dict[str, Any]],
    missing_lineage: int,
) -> list[str]:
    caveats: list[str] = []
    if not counts.get("daily_prices"):
        caveats.append("No daily_prices rows found.")
    if not counts.get("source_runs"):
        caveats.append("No source_runs rows found; DB may have been built by deterministic demo builder.")
    if not counts.get("ingestion_watermarks"):
        caveats.append("No ingestion_watermarks rows found; run cached/live ingestion to populate audit watermarks.")
    if requested:
        found = {str(row["symbol"]) for row in symbol_rows}
        missing = [symbol for symbol in requested if symbol not in found]
        if missing:
            caveats.append(f"Requested symbols not found: {', '.join(missing)}.")
    if missing_lineage:
        caveats.append(f"{missing_lineage} daily_prices rows are missing source_id or raw_path.")
    caveats.append("Read-only status report; not production monitoring and not financial advice.")
    return caveats


def _overall_status(counts: dict[str, int | None], missing_lineage: int) -> str:
    if not counts.get("daily_prices") and not counts.get("securities"):
        return "empty_store"
    if missing_lineage or not counts.get("source_runs") or not counts.get("ingestion_watermarks"):
        return "quality_warn"
    return "ok"


def _latest_trade_date(symbols: list[dict[str, Any]]) -> str | None:
    dates = [str(item["latest_trade_date"]) for item in symbols if item.get("latest_trade_date")]
    return max(dates) if dates else None


def _symbol_filter_sql(column: str, symbols: list[str]) -> tuple[str, list[str]]:
    if not symbols:
        return "", []
    placeholders = ", ".join(["?"] * len(symbols))
    return f"WHERE {column} IN ({placeholders})", symbols


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _normalize_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for item in symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized
