from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from trading_agent.db.paths import DEFAULT_DB_PATH


ADJUSTED_COLUMNS = [
    "adjustment_factor",
    "adjusted_open",
    "adjusted_high",
    "adjusted_low",
    "adjusted_close",
]


def get_adjusted_ohlc_readiness(
    db_path: str | Path = DEFAULT_DB_PATH,
    symbols: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    path = Path(db_path)
    requested = _normalize_symbols(symbols or [])
    base = {
        "status": "missing_store",
        "db_path": str(path),
        "symbols": requested,
        "coverage": _empty_coverage(),
        "by_symbol": [],
        "backtest_gate": "blocked",
        "caveats": [],
    }
    if not path.exists():
        base["caveats"] = [f"MVP store not found: {path}"]
        return base

    try:
        with _connect_readonly(path) as con:
            tables = _table_names(con)
            if "daily_prices" not in tables:
                return {
                    **base,
                    "status": "empty_store",
                    "caveats": ["daily_prices table not found."],
                }

            columns = _column_names(con, "daily_prices")
            total_rows = _count_rows(con, requested, start_date, end_date)
            if total_rows == 0:
                rows_in_range = _count_rows(con, [], start_date, end_date)
                if requested and rows_in_range:
                    return {
                        **base,
                        "status": "not_ready",
                        "symbols": [],
                        "coverage": _empty_coverage(),
                        "caveats": _caveats(_empty_coverage(), requested),
                    }
                return {
                    **base,
                    "status": "empty_store",
                    "symbols": requested,
                    "caveats": ["No daily_prices rows found for the selected filters."],
                }

            missing_columns = [column for column in ADJUSTED_COLUMNS if column not in columns]
            if missing_columns:
                coverage = {
                    **_empty_coverage(),
                    "total_rows": total_rows,
                    "missing_adjusted_rows": total_rows,
                }
                return {
                    **base,
                    "status": "not_ready",
                    "symbols": _symbols_from_rows(con, requested, start_date, end_date),
                    "coverage": coverage,
                    "by_symbol": _by_symbol_missing_columns(con, requested, start_date, end_date),
                    "caveats": [f"Missing adjusted OHLC columns: {', '.join(missing_columns)}."],
                }

            coverage = _coverage(con, requested, start_date, end_date)
            by_symbol = _by_symbol(con, requested, start_date, end_date)
            symbols_found = [item["symbol"] for item in by_symbol]
            missing_symbols = [symbol for symbol in requested if symbol not in set(symbols_found)]
            caveats = _caveats(coverage, missing_symbols)
            status = _status(coverage, missing_symbols)
            return {
                "status": status,
                "db_path": str(path),
                "symbols": symbols_found,
                "coverage": coverage,
                "by_symbol": by_symbol,
                "backtest_gate": "pass" if status == "ok" else "blocked",
                "caveats": caveats,
            }
    except sqlite3.Error as exc:
        return {
            **base,
            "status": "empty_store",
            "caveats": [f"Unable to inspect adjusted OHLC readiness: {exc}"],
        }


def _connect_readonly(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def _column_names(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _count_rows(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> int:
    where, params = _filters(symbols, start_date, end_date)
    row = con.execute(f"SELECT COUNT(*) AS rows FROM daily_prices {where}", params).fetchone()
    return int(row["rows"] or 0)


def _coverage(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> dict[str, int]:
    where, params = _filters(symbols, start_date, end_date)
    row = con.execute(
        f"""
        SELECT
            COUNT(*) AS total_rows,
            SUM(CASE WHEN {_adjusted_present_sql()} THEN 1 ELSE 0 END) AS adjusted_rows,
            SUM(CASE WHEN NOT ({_adjusted_present_sql()}) THEN 1 ELSE 0 END) AS missing_adjusted_rows,
            SUM(CASE WHEN adjustment_factor IS NOT NULL AND adjustment_factor <= 0 THEN 1 ELSE 0 END) AS invalid_factor_rows,
            SUM(CASE WHEN {_invalid_adjusted_ohlc_sql()} THEN 1 ELSE 0 END) AS invalid_ohlc_rows,
            SUM(CASE WHEN quality_status = 'fail' THEN 1 ELSE 0 END) AS fail_quality_rows
        FROM daily_prices
        {where}
        """,
        params,
    ).fetchone()
    return _coverage_from_row(row)


def _by_symbol(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    where, params = _filters(symbols, start_date, end_date)
    rows = con.execute(
        f"""
        SELECT
            symbol,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN {_adjusted_present_sql()} THEN 1 ELSE 0 END) AS adjusted_rows,
            SUM(CASE WHEN NOT ({_adjusted_present_sql()}) THEN 1 ELSE 0 END) AS missing_adjusted_rows,
            SUM(CASE WHEN adjustment_factor IS NOT NULL AND adjustment_factor <= 0 THEN 1 ELSE 0 END) AS invalid_factor_rows,
            SUM(CASE WHEN {_invalid_adjusted_ohlc_sql()} THEN 1 ELSE 0 END) AS invalid_ohlc_rows,
            SUM(CASE WHEN quality_status = 'fail' THEN 1 ELSE 0 END) AS fail_quality_rows,
            MIN(trade_date) AS start_date,
            MAX(trade_date) AS end_date
        FROM daily_prices
        {where}
        GROUP BY symbol
        ORDER BY symbol
        """,
        params,
    ).fetchall()
    return [
        {
            "symbol": row["symbol"],
            **_coverage_from_row(row),
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "backtest_gate": "pass" if _status(_coverage_from_row(row), []) == "ok" else "blocked",
        }
        for row in rows
    ]


def _by_symbol_missing_columns(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    where, params = _filters(symbols, start_date, end_date)
    rows = con.execute(
        f"""
        SELECT symbol, COUNT(*) AS total_rows, MIN(trade_date) AS start_date, MAX(trade_date) AS end_date
        FROM daily_prices
        {where}
        GROUP BY symbol
        ORDER BY symbol
        """,
        params,
    ).fetchall()
    return [
        {
            "symbol": row["symbol"],
            "total_rows": int(row["total_rows"] or 0),
            "adjusted_rows": 0,
            "missing_adjusted_rows": int(row["total_rows"] or 0),
            "invalid_factor_rows": 0,
            "invalid_ohlc_rows": 0,
            "fail_quality_rows": 0,
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "backtest_gate": "blocked",
        }
        for row in rows
    ]


def _symbols_from_rows(
    con: sqlite3.Connection,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    where, params = _filters(symbols, start_date, end_date)
    rows = con.execute(f"SELECT DISTINCT symbol FROM daily_prices {where} ORDER BY symbol", params).fetchall()
    return [str(row["symbol"]) for row in rows]


def _adjusted_present_sql() -> str:
    return """
        adjustment_factor IS NOT NULL
        AND adjusted_open IS NOT NULL
        AND adjusted_high IS NOT NULL
        AND adjusted_low IS NOT NULL
        AND adjusted_close IS NOT NULL
    """


def _invalid_adjusted_ohlc_sql() -> str:
    present = _adjusted_present_sql()
    return f"""
        ({present})
        AND (
            adjusted_high < MAX(adjusted_open, adjusted_close)
            OR adjusted_low > MIN(adjusted_open, adjusted_close)
            OR adjusted_high < adjusted_low
        )
    """


def _coverage_from_row(row: sqlite3.Row) -> dict[str, int]:
    return {
        "total_rows": int(row["total_rows"] or 0),
        "adjusted_rows": int(row["adjusted_rows"] or 0),
        "missing_adjusted_rows": int(row["missing_adjusted_rows"] or 0),
        "invalid_factor_rows": int(row["invalid_factor_rows"] or 0),
        "invalid_ohlc_rows": int(row["invalid_ohlc_rows"] or 0),
        "fail_quality_rows": int(row["fail_quality_rows"] or 0),
    }


def _status(coverage: dict[str, int], missing_symbols: list[str]) -> str:
    if missing_symbols:
        return "not_ready"
    if coverage["missing_adjusted_rows"] or coverage["invalid_factor_rows"] or coverage["invalid_ohlc_rows"]:
        return "not_ready"
    if coverage["fail_quality_rows"]:
        return "quality_warn"
    return "ok"


def _caveats(coverage: dict[str, int], missing_symbols: list[str]) -> list[str]:
    caveats: list[str] = []
    if missing_symbols:
        caveats.append(f"Requested symbols not found in selected rows: {', '.join(missing_symbols)}.")
    if coverage["missing_adjusted_rows"]:
        caveats.append(f"{coverage['missing_adjusted_rows']} rows are missing adjusted OHLC fields.")
    if coverage["invalid_factor_rows"]:
        caveats.append(f"{coverage['invalid_factor_rows']} rows have adjustment_factor <= 0.")
    if coverage["invalid_ohlc_rows"]:
        caveats.append(f"{coverage['invalid_ohlc_rows']} rows have inconsistent adjusted OHLC values.")
    if coverage["fail_quality_rows"]:
        caveats.append(f"{coverage['fail_quality_rows']} rows have quality_status=fail.")
    caveats.append("Adjusted OHLC readiness only; not production monitoring and not financial advice.")
    return caveats


def _filters(
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if symbols:
        placeholders = ", ".join(["?"] * len(symbols))
        clauses.append(f"symbol IN ({placeholders})")
        params.extend(symbols)
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)
    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", params)


def _empty_coverage() -> dict[str, int]:
    return {
        "total_rows": 0,
        "adjusted_rows": 0,
        "missing_adjusted_rows": 0,
        "invalid_factor_rows": 0,
        "invalid_ohlc_rows": 0,
        "fail_quality_rows": 0,
    }


def _normalize_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for item in symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized
