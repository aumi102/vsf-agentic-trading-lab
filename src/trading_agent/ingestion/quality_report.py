from __future__ import annotations

import sqlite3


def build_ingestion_quality_report(con: sqlite3.Connection, *, symbols: list[str]) -> dict[str, object]:
    normalized = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not normalized:
        return {
            "symbols": {},
            "lineage": {"missing_source_id_raw_path": 0, "status": "pass"},
            "daily_prices": _empty_distribution("daily_prices"),
            "feature_snapshots": _empty_distribution("feature_snapshots"),
            "signals": _empty_distribution("signals"),
        }
    placeholders = ", ".join(["?"] * len(normalized))
    symbol_rows = con.execute(
        f"""
        SELECT symbol,
               COUNT(*) AS daily_rows,
               MIN(trade_date) AS start_date,
               MAX(trade_date) AS end_date,
               SUM(CASE WHEN quality_status = 'fail' THEN 1 ELSE 0 END) AS fail_rows
        FROM daily_prices
        WHERE symbol IN ({placeholders})
        GROUP BY symbol
        ORDER BY symbol
        """,
        normalized,
    ).fetchall()
    symbols_report = {
        str(row["symbol"]): {
            "daily_rows": int(row["daily_rows"] or 0),
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "fail_rows": int(row["fail_rows"] or 0),
        }
        for row in symbol_rows
    }
    lineage_missing = con.execute(
        f"""
        SELECT COUNT(*) AS missing_count
        FROM daily_prices
        WHERE symbol IN ({placeholders})
          AND (
            source_id IS NULL OR TRIM(source_id) = ''
            OR raw_path IS NULL OR TRIM(raw_path) = ''
          )
        """,
        normalized,
    ).fetchone()
    missing_count = int(lineage_missing["missing_count"] or 0)
    return {
        "symbols": symbols_report,
        "lineage": {
            "missing_source_id_raw_path": missing_count,
            "status": "fail" if missing_count else "pass",
        },
        "daily_prices": _quality_distribution(con, "daily_prices", "trade_date", normalized),
        "feature_snapshots": _quality_distribution(con, "feature_snapshots", "as_of_date", normalized),
        "signals": _quality_distribution(con, "signals", "as_of_date", normalized),
    }


def _quality_distribution(
    con: sqlite3.Connection,
    table: str,
    date_column: str,
    symbols: list[str],
) -> dict[str, object]:
    placeholders = ", ".join(["?"] * len(symbols))
    rows = con.execute(
        f"""
        SELECT quality_status, COUNT(*) AS rows
        FROM {table}
        WHERE symbol IN ({placeholders})
        GROUP BY quality_status
        """,
        symbols,
    ).fetchall()
    counts = {str(row["quality_status"]): int(row["rows"] or 0) for row in rows}
    date_row = con.execute(
        f"""
        SELECT MIN({date_column}) AS start_date, MAX({date_column}) AS end_date, COUNT(*) AS rows
        FROM {table}
        WHERE symbol IN ({placeholders})
        """,
        symbols,
    ).fetchone()
    return {
        "table": table,
        "row_count": int(date_row["rows"] or 0),
        "start_date": date_row["start_date"],
        "end_date": date_row["end_date"],
        "pass_count": counts.get("pass", 0),
        "warn_count": counts.get("warn", 0),
        "fail_count": counts.get("fail", 0),
    }


def _empty_distribution(table: str) -> dict[str, object]:
    return {
        "table": table,
        "row_count": 0,
        "start_date": None,
        "end_date": None,
        "pass_count": 0,
        "warn_count": 0,
        "fail_count": 0,
    }
