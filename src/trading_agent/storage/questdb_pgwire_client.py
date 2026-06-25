"""Direct QuestDB PGWire query path via psycopg (mentor suggestion).

QuestDB speaks the PostgreSQL wire protocol on port 8812. For repeated, low-latency
read queries this avoids the REST `/exec` JSON round trip and — crucially — lets us
reuse a warm connection instead of paying a fresh TCP/handshake cost per query.

This module is read-only by design (only SELECT/SHOW/WITH/EXPLAIN pass the guard),
returns rows as dictionaries, and reports per-call timing:
    connect_ms, execute_ms, fetch_ms, total_ms

Connection reuse:
  * If ``psycopg_pool`` is installed, a small ConnectionPool is used.
  * Otherwise a thread-safe persistent-connection cache keyed by DSN is used so the
    expensive first connect (~seconds, cold) is amortized across many queries.

Defaults match a local QuestDB:  host=localhost port=8812 user=admin
password=quest dbname=qdb. Everything is overridable via environment variables.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

try:  # psycopg 3
    import psycopg
except Exception as exc:  # pragma: no cover - import guard
    psycopg = None  # type: ignore[assignment]
    _IMPORT_ERROR: Exception | None = exc
else:
    _IMPORT_ERROR = None

try:  # optional pool
    import logging

    from psycopg_pool import ConnectionPool  # type: ignore

    # QuestDB closes idle PGWire connections; the pool then discards the dead
    # connection and transparently reconnects. That self-healing logs a noisy
    # "discarding closed connection" WARNING — harmless, so quiet it for the demo
    # (errors still surface).
    logging.getLogger("psycopg.pool").setLevel(logging.ERROR)
except Exception:  # pragma: no cover - pool is optional
    ConnectionPool = None  # type: ignore[assignment]

_READ_ONLY_RE = re.compile(r"^\s*(select|show|with|explain|table)\b", re.IGNORECASE)

DEFAULT_HOST = "127.0.0.1"  # IPv4 avoids the Windows localhost->::1 connect penalty
DEFAULT_PORT = 8812
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "quest"
DEFAULT_DB = "qdb"

_lock = threading.Lock()
_conn_cache: dict[str, Any] = {}
_pool_cache: dict[str, Any] = {}


def pgwire_available() -> bool:
    return psycopg is not None


def build_dsn() -> str:
    """Resolve the PGWire DSN from environment (or sensible local defaults)."""
    explicit = os.environ.get("QUESTDB_PGWIRE_DSN")
    if explicit:
        return explicit
    host = os.environ.get("QUESTDB_PGWIRE_HOST", DEFAULT_HOST)
    port = os.environ.get("QUESTDB_PGWIRE_PORT", str(DEFAULT_PORT))
    user = os.environ.get("QUESTDB_PGWIRE_USER", DEFAULT_USER)
    password = os.environ.get("QUESTDB_PGWIRE_PASSWORD", DEFAULT_PASSWORD)
    dbname = os.environ.get("QUESTDB_PGWIRE_DB", DEFAULT_DB)
    return f"host={host} port={port} user={user} password={password} dbname={dbname}"


def _result(
    status: str,
    rows: list[dict[str, Any]],
    sql: str,
    caveats: list[str],
    timing: dict[str, float],
) -> dict[str, Any]:
    return {
        "status": status,
        "rows": rows,
        "row_count": len(rows),
        "source": "questdb",
        "query_mode": "pgwire",
        "sql": sql,
        "timing": timing,
        "caveats": caveats,
    }


def _get_persistent_conn(dsn: str):
    """Return a cached, autocommit connection for the DSN (reconnect if closed)."""
    with _lock:
        conn = _conn_cache.get(dsn)
        if conn is not None and not getattr(conn, "closed", True):
            return conn, 0.0
        t0 = time.perf_counter()
        conn = psycopg.connect(dsn, autocommit=True, connect_timeout=10)  # type: ignore[union-attr]
        connect_ms = (time.perf_counter() - t0) * 1000.0
        _conn_cache[dsn] = conn
        return conn, connect_ms


def _get_pool(dsn: str):
    pool = _pool_cache.get(dsn)
    if pool is None:
        # check=check_connection validates a borrowed connection (and replaces a dead
        # one) before handing it out, so QuestDB's idle-close does not surface as a
        # mid-query failure. max_idle proactively recycles idle connections.
        pool = ConnectionPool(  # type: ignore[operator]
            dsn,
            min_size=1,
            max_size=4,
            max_idle=30.0,
            check=ConnectionPool.check_connection,  # type: ignore[attr-defined]
            kwargs={"autocommit": True},
            open=True,
        )
        _pool_cache[dsn] = pool
    return pool


def query_pgwire(
    sql: str,
    *,
    dsn: str | None = None,
    use_pool: bool = True,
) -> dict[str, Any]:
    """Run a read-only SQL statement over PGWire and return structured rows + timing."""
    timing = {"connect_ms": 0.0, "execute_ms": 0.0, "fetch_ms": 0.0, "total_ms": 0.0}
    if psycopg is None:
        return _result("error", [], sql, [f"psycopg unavailable: {_IMPORT_ERROR}"], timing)
    if not _READ_ONLY_RE.match(sql or ""):
        return _result("error", [], sql, ["Only SELECT/SHOW/WITH/EXPLAIN statements are permitted."], timing)

    dsn = dsn or build_dsn()
    start = time.perf_counter()
    try:
        if use_pool and ConnectionPool is not None:
            pool = _get_pool(dsn)
            t0 = time.perf_counter()
            with pool.connection() as conn:
                timing["connect_ms"] = (time.perf_counter() - t0) * 1000.0
                rows, exec_ms, fetch_ms = _execute(conn, sql)
        else:
            conn, connect_ms = _get_persistent_conn(dsn)
            timing["connect_ms"] = connect_ms
            try:
                rows, exec_ms, fetch_ms = _execute(conn, sql)
            except Exception:
                # Drop a possibly-stale cached connection and retry once.
                with _lock:
                    _conn_cache.pop(dsn, None)
                    try:
                        conn.close()
                    except Exception:
                        pass
                conn, connect_ms = _get_persistent_conn(dsn)
                timing["connect_ms"] = connect_ms
                rows, exec_ms, fetch_ms = _execute(conn, sql)
        timing["execute_ms"] = exec_ms
        timing["fetch_ms"] = fetch_ms
        timing["total_ms"] = (time.perf_counter() - start) * 1000.0
        return _result("ok", rows, sql, [], timing)
    except Exception as exc:
        timing["total_ms"] = (time.perf_counter() - start) * 1000.0
        return _result("error", [], sql, [f"pgwire_query_failed: {type(exc).__name__}: {exc}"], timing)


def _execute(conn, sql: str) -> tuple[list[dict[str, Any]], float, float]:
    with conn.cursor() as cur:
        t0 = time.perf_counter()
        cur.execute(sql)
        exec_ms = (time.perf_counter() - t0) * 1000.0
        t1 = time.perf_counter()
        columns = [desc.name for desc in cur.description] if cur.description else []
        dataset = cur.fetchall() if cur.description else []
        fetch_ms = (time.perf_counter() - t1) * 1000.0
    rows = [dict(zip(columns, record)) for record in dataset]
    return rows, exec_ms, fetch_ms


def ping(*, dsn: str | None = None) -> dict[str, Any]:
    """Lightweight health check used by the benchmark and FastAPI status route."""
    return query_pgwire("SELECT 1", dsn=dsn, use_pool=False)


def close_all() -> None:
    """Close any cached connections/pools (used on shutdown / tests)."""
    with _lock:
        for conn in _conn_cache.values():
            try:
                conn.close()
            except Exception:
                pass
        _conn_cache.clear()
        for pool in _pool_cache.values():
            try:
                pool.close()
            except Exception:
                pass
        _pool_cache.clear()
