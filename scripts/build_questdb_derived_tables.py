"""Build deterministic QuestDB side tables from the read-only daily_prices table.

Examples (Windows-friendly):
  python scripts\build_questdb_derived_tables.py --mode all
  python scripts\build_questdb_derived_tables.py --mode securities
  python scripts\build_questdb_derived_tables.py --mode features --symbols FPT,VNM,HPG
  python scripts\build_questdb_derived_tables.py --mode all --limit-symbols 50

Only the derived tables in DERIVED_TABLES may be dropped. ``daily_prices`` is
queried but is never altered. Feature rows with insufficient history are kept;
their unavailable rolling fields are NULL.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage import questdb_client as qdb  # noqa: E402

SOURCE_TABLE = "daily_prices"
DERIVED_TABLES = {"securities", "feature_snapshots", "signals"}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    symbols = list(dict.fromkeys(part.strip().upper() for part in raw.split(",") if part.strip()))
    invalid = [symbol for symbol in symbols if not SYMBOL_RE.fullmatch(symbol)]
    if invalid:
        raise ValueError(f"invalid symbols: {', '.join(invalid)}")
    return symbols


def _selected_symbols(client, base_url: str, explicit: list[str], limit: int | None) -> list[str]:
    if explicit:
        return explicit
    if limit is None:
        return []
    _, rows = qdb.exec_rows(
        client,
        base_url,
        f"SELECT DISTINCT symbol FROM {SOURCE_TABLE} ORDER BY symbol LIMIT {int(limit)}",
    )
    return [str(row[0]) for row in rows if row]


def _where(symbols: list[str], alias: str = "") -> str:
    if not symbols:
        return ""
    prefix = f"{alias}." if alias else ""
    quoted = ", ".join(f"'{symbol}'" for symbol in symbols)
    return f"WHERE {prefix}symbol IN ({quoted})"


def _drop_derived(client, base_url: str, table: str) -> None:
    if table not in DERIVED_TABLES:
        raise ValueError(f"refusing to drop non-derived table: {table}")
    qdb.exec_query(client, base_url, f"DROP TABLE IF EXISTS {table}")


def _await_and_count(client, base_url: str, table: str) -> tuple[int, int]:
    _, wal_rows = qdb.exec_rows(client, base_url, f"SELECT name FROM wal_tables() WHERE name = '{table}'")
    if wal_rows:
        qdb.wait_wal_applied(client, base_url, table, attempts=1200)
    rows = int(qdb.exec_scalar(client, base_url, f"SELECT count() FROM {table}", 0))
    symbols = int(qdb.exec_scalar(client, base_url, f"SELECT count_distinct(symbol) FROM {table}", 0))
    return rows, symbols


def build_securities(client, base_url: str, symbols: list[str]) -> tuple[int, int]:
    _drop_derived(client, base_url, "securities")
    qdb.exec_query(
        client,
        base_url,
        """CREATE TABLE securities (
            security_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            exchange SYMBOL CAPACITY 256 CACHE,
            first_trade_date TIMESTAMP,
            last_trade_date TIMESTAMP,
            row_count LONG,
            source_family SYMBOL CAPACITY 256 CACHE,
            quality_status SYMBOL CAPACITY 256 CACHE,
            updated_at TIMESTAMP
        )""",
    )
    where = _where(symbols)
    qdb.exec_query(
        client,
        base_url,
        f"""INSERT INTO securities
        SELECT security_id,
               symbol,
               first(exchange) AS exchange,
               min(trade_date) AS first_trade_date,
               max(trade_date) AS last_trade_date,
               count() AS row_count,
               cast('vietcap' AS symbol) AS source_family,
               first(quality_status) AS quality_status,
               now() AS updated_at
        FROM {SOURCE_TABLE}
        {where}
        GROUP BY security_id, symbol""",
    )
    return _await_and_count(client, base_url, "securities")


def build_features(client, base_url: str, symbols: list[str]) -> tuple[int, int]:
    _drop_derived(client, base_url, "feature_snapshots")
    qdb.exec_query(
        client,
        base_url,
        """CREATE TABLE feature_snapshots (
            trade_date TIMESTAMP,
            security_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            adjusted_close DOUBLE,
            volume DOUBLE,
            return_1d DOUBLE,
            ma20 DOUBLE,
            ma50 DOUBLE,
            volatility20 DOUBLE,
            volume_ma20 DOUBLE,
            close_to_ma20 DOUBLE,
            close_to_ma50 DOUBLE,
            feature_version SYMBOL CAPACITY 256 CACHE,
            quality_status SYMBOL CAPACITY 256 CACHE,
            source_table SYMBOL CAPACITY 256 CACHE
        ) TIMESTAMP(trade_date) PARTITION BY YEAR WAL""",
    )
    where = _where(symbols)
    qdb.exec_query(
        client,
        base_url,
        f"""INSERT INTO feature_snapshots
        SELECT trade_date,
               security_id,
               symbol,
               px AS adjusted_close,
               volume,
               return_1d,
               ma20,
               ma50,
               volatility20,
               volume_ma20,
               CASE WHEN ma20 IS NULL OR ma20 = 0 THEN null ELSE px / ma20 - 1 END AS close_to_ma20,
               CASE WHEN ma50 IS NULL OR ma50 = 0 THEN null ELSE px / ma50 - 1 END AS close_to_ma50,
               cast('mvp_v1' AS symbol) AS feature_version,
               quality_status,
               cast('daily_prices' AS symbol) AS source_table
        FROM (
            SELECT trade_date,
                   security_id,
                   symbol,
                   px,
                   volume,
                   return_1d,
                   CASE WHEN px_count20 = 20 THEN raw_ma20 ELSE null END AS ma20,
                   CASE WHEN px_count50 = 50 THEN raw_ma50 ELSE null END AS ma50,
                   CASE WHEN return_count20 = 20 THEN raw_volatility20 ELSE null END AS volatility20,
                   CASE WHEN volume_count20 = 20 THEN raw_volume_ma20 ELSE null END AS volume_ma20,
                   quality_status
            FROM (
                SELECT trade_date,
                       security_id,
                       symbol,
                       px,
                       volume,
                       return_1d,
                       quality_status,
                       count(px) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS px_count20,
                       avg(px) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS raw_ma20,
                       count(px) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                       ) AS px_count50,
                       avg(px) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                       ) AS raw_ma50,
                       count(return_1d) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS return_count20,
                       stddev_samp(return_1d) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS raw_volatility20,
                       count(volume) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS volume_count20,
                       avg(volume) OVER (
                           PARTITION BY symbol ORDER BY trade_date
                           ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                       ) AS raw_volume_ma20
                FROM (
                    SELECT trade_date,
                           security_id,
                           symbol,
                           px,
                           volume,
                           quality_status,
                           CASE WHEN prev_px IS NULL OR prev_px = 0
                                THEN null ELSE px / prev_px - 1 END AS return_1d
                    FROM (
                        SELECT trade_date,
                               security_id,
                               symbol,
                               coalesce(adjusted_close, close) AS px,
                               volume,
                               quality_status,
                               lag(coalesce(adjusted_close, close)) OVER (
                                   PARTITION BY symbol ORDER BY trade_date
                               ) AS prev_px
                        FROM {SOURCE_TABLE}
                        {where}
                    )
                )
            )
        )""",
    )
    return _await_and_count(client, base_url, "feature_snapshots")


def build_signals(client, base_url: str, symbols: list[str]) -> tuple[int, int]:
    if not qdb.table_exists(client, base_url, "feature_snapshots"):
        raise RuntimeError("feature_snapshots does not exist; build features first")
    _drop_derived(client, base_url, "signals")
    qdb.exec_query(
        client,
        base_url,
        """CREATE TABLE signals (
            trade_date TIMESTAMP,
            security_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            strategy_id SYMBOL CAPACITY 256 CACHE,
            signal SYMBOL CAPACITY 256 CACHE,
            score DOUBLE,
            reason_code SYMBOL CAPACITY 256 CACHE,
            intended_execution SYMBOL CAPACITY 256 CACHE,
            feature_version SYMBOL CAPACITY 256 CACHE,
            signal_version SYMBOL CAPACITY 256 CACHE,
            quality_status SYMBOL CAPACITY 256 CACHE
        ) TIMESTAMP(trade_date) PARTITION BY YEAR WAL""",
    )
    where = _where(symbols)
    qdb.exec_query(
        client,
        base_url,
        f"""INSERT INTO signals
        SELECT trade_date,
               security_id,
               symbol,
               cast('ma20_ma50_v1' AS symbol) AS strategy_id,
               CASE WHEN ma20 IS NULL OR ma50 IS NULL THEN cast('INSUFFICIENT_DATA' AS symbol)
                    WHEN ma20 > ma50 THEN cast('BUY' AS symbol)
                    ELSE cast('CASH' AS symbol) END AS signal,
               CASE WHEN ma20 IS NULL OR ma50 IS NULL OR ma50 = 0 THEN 0.0
                    ELSE ma20 / ma50 - 1 END AS score,
               CASE WHEN ma20 IS NULL OR ma50 IS NULL THEN cast('missing_ma' AS symbol)
                    WHEN ma20 > ma50 THEN cast('ma20_above_ma50' AS symbol)
                    ELSE cast('ma20_below_or_equal_ma50' AS symbol) END AS reason_code,
               cast('next_day_close' AS symbol) AS intended_execution,
               feature_version,
               cast('mvp_v1' AS symbol) AS signal_version,
               quality_status
        FROM feature_snapshots
        {where}""",
    )
    return _await_and_count(client, base_url, "signals")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic QuestDB derived tables.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--mode", choices=("all", "securities", "features", "signals"), default="all")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--symbols", help="Comma-separated ticker symbols.")
    selection.add_argument("--limit-symbols", type=int, help="Build only the first N symbols alphabetically.")
    args = parser.parse_args()
    if args.limit_symbols is not None and args.limit_symbols < 1:
        parser.error("--limit-symbols must be >= 1")

    try:
        explicit = _parse_symbols(args.symbols)
    except ValueError as exc:
        parser.error(str(exc))

    base_url = args.questdb_url.rstrip("/")
    started = time.monotonic()
    with qdb.open_client(timeout_seconds=900.0) as client:
        if not qdb.table_exists(client, base_url, SOURCE_TABLE):
            print(f"ERROR: source table {SOURCE_TABLE!r} does not exist", file=sys.stderr)
            return 1
        symbols = _selected_symbols(client, base_url, explicit, args.limit_symbols)
        scope = ",".join(symbols) if symbols else "ALL"
        print(f"QuestDB       : {base_url}")
        print(f"source table  : {SOURCE_TABLE} (read-only)")
        print(f"mode          : {args.mode}")
        print(f"symbol scope  : {scope}")
        builders = []
        if args.mode in {"all", "securities"}:
            builders.append(("securities", build_securities))
        if args.mode in {"all", "features"}:
            builders.append(("feature_snapshots", build_features))
        if args.mode in {"all", "signals"}:
            builders.append(("signals", build_signals))
        for name, builder in builders:
            table_started = time.monotonic()
            rows, covered = builder(client, base_url, symbols)
            print(f"{name:<18}: rows={rows:,} symbols={covered:,} elapsed={time.monotonic()-table_started:.1f}s")
    print(f"done in {time.monotonic()-started:.1f}s; {SOURCE_TABLE} was not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
