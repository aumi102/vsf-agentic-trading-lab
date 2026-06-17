from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = "mvp_db_tool_demo_v1"

SECURITIES_COLUMNS = [
    "security_id",
    "symbol",
    "exchange",
    "issuer_name",
    "source_id",
    "raw_path",
    "first_seen_at",
    "quality_status",
]

DAILY_PRICES_COLUMNS = [
    "security_id",
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value",
    "price_basis",
    "adjustment_status",
    "source_id",
    "raw_path",
    "quality_status",
]

FEATURE_SNAPSHOTS_COLUMNS = [
    "security_id",
    "symbol",
    "as_of_date",
    "return_1d",
    "return_5d",
    "return_20d",
    "ma_20",
    "ma_50",
    "volatility_20d",
    "volume_ratio_20d",
    "feature_version",
    "lookback_coverage",
    "quality_status",
]

SIGNALS_COLUMNS = [
    "security_id",
    "symbol",
    "as_of_date",
    "strategy_id",
    "action",
    "score",
    "reason_code",
    "reason_text",
    "signal_version",
    "quality_status",
]

SOURCE_RUNS_COLUMNS = [
    "run_id",
    "source",
    "mode",
    "status",
    "started_at",
    "completed_at",
    "symbols_requested_json",
    "symbols_loaded_json",
    "symbols_failed_json",
    "allow_network",
    "caveats_json",
]

RAW_SOURCE_PAYLOADS_COLUMNS = [
    "payload_id",
    "run_id",
    "source",
    "symbol",
    "observed_at",
    "content_hash",
    "raw_path",
    "metadata_path",
    "logical_path",
    "row_count",
    "status",
]

INGESTION_WATERMARKS_COLUMNS = [
    "source",
    "symbol",
    "last_trade_date",
    "last_run_id",
    "updated_at",
    "row_count",
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS securities (
            security_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            issuer_name TEXT NOT NULL,
            source_id TEXT NOT NULL,
            raw_path TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            quality_status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_prices (
            security_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            value REAL,
            price_basis TEXT NOT NULL,
            adjustment_status TEXT NOT NULL,
            source_id TEXT NOT NULL,
            raw_path TEXT NOT NULL,
            quality_status TEXT NOT NULL,
            PRIMARY KEY (security_id, trade_date, source_id)
        );

        CREATE TABLE IF NOT EXISTS feature_snapshots (
            security_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            return_1d REAL,
            return_5d REAL,
            return_20d REAL,
            ma_20 REAL,
            ma_50 REAL,
            volatility_20d REAL,
            volume_ratio_20d REAL,
            feature_version TEXT NOT NULL,
            lookback_coverage INTEGER NOT NULL,
            quality_status TEXT NOT NULL,
            PRIMARY KEY (security_id, as_of_date, feature_version)
        );

        CREATE TABLE IF NOT EXISTS signals (
            security_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            action TEXT NOT NULL,
            score REAL NOT NULL,
            reason_code TEXT NOT NULL,
            reason_text TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            quality_status TEXT NOT NULL,
            PRIMARY KEY (security_id, as_of_date, strategy_id, signal_version)
        );

        CREATE TABLE IF NOT EXISTS source_runs (
            run_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            symbols_requested_json TEXT NOT NULL,
            symbols_loaded_json TEXT NOT NULL,
            symbols_failed_json TEXT NOT NULL,
            allow_network INTEGER NOT NULL,
            caveats_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS raw_source_payloads (
            payload_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            source TEXT NOT NULL,
            symbol TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            raw_path TEXT NOT NULL,
            metadata_path TEXT NOT NULL,
            logical_path TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES source_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS ingestion_watermarks (
            source TEXT NOT NULL,
            symbol TEXT NOT NULL,
            last_trade_date TEXT,
            last_run_id TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            PRIMARY KEY (source, symbol)
        );
        """
    )
    con.commit()


def replace_table(con: sqlite3.Connection, table: str, rows: list[dict[str, object]]) -> None:
    con.execute(f"DELETE FROM {table}")
    if not rows:
        con.commit()
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    values = [tuple(row.get(column) for column in columns) for row in rows]
    con.executemany(f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})", values)
    con.commit()
