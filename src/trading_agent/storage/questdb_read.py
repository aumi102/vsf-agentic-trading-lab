"""Unified read-only query dispatcher: REST `/exec` vs PGWire.

Selectable via the ``QUESTDB_QUERY_MODE`` backend setting (``rest`` default, or
``pgwire``). Both paths return the same envelope shape and per-call timing so the
FastAPI demo can show ``query_mode`` / ``execute_ms`` / ``total_ms`` and the
benchmark can compare them fairly.

REST timing uses QuestDB's ``timings=true`` flag, which returns the real
server-side ``execute`` time in nanoseconds (this is what the Web Console's
"Execute 72.98ms" line reports). PGWire timing is measured around psycopg.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

import httpx

from trading_agent.storage import questdb_client as qdb
from trading_agent.storage import questdb_pgwire_client as pg

DEFAULT_URL = os.environ.get("QUESTDB_URL", qdb.DEFAULT_QUESTDB_URL)
_READ_ONLY_RE = re.compile(r"^\s*(select|show|with|explain|table)\b", re.IGNORECASE)

_rest_lock = threading.Lock()
_rest_client: httpx.Client | None = None


def resolve_mode(requested: str | None = None) -> str:
    mode = (requested or os.environ.get("QUESTDB_QUERY_MODE", "rest")).strip().lower()
    return mode if mode in {"rest", "pgwire"} else "rest"


def _get_rest_client() -> httpx.Client:
    global _rest_client
    with _rest_lock:
        if _rest_client is None or _rest_client.is_closed:
            _rest_client = httpx.Client(timeout=60.0)
        return _rest_client


def _envelope(status: str, rows: list[dict[str, Any]], sql: str, query_mode: str, caveats: list[str], timing: dict[str, float]) -> dict[str, Any]:
    return {
        "status": status,
        "rows": rows,
        "row_count": len(rows),
        "source": "questdb",
        "query_mode": query_mode,
        "sql": sql,
        "timing": timing,
        "caveats": caveats,
    }


def query_rest_timed(sql: str, *, url: str = DEFAULT_URL) -> dict[str, Any]:
    """Run read-only SQL over REST `/exec` with server-side timings; reuse the client."""
    timing = {"connect_ms": 0.0, "execute_ms": 0.0, "fetch_ms": 0.0, "total_ms": 0.0}
    if not _READ_ONLY_RE.match(sql or ""):
        return _envelope("error", [], sql, "rest", ["Only SELECT/SHOW/WITH/EXPLAIN statements are permitted."], timing)
    client = _get_rest_client()
    url = qdb.to_ipv4_localhost(url)
    start = time.perf_counter()
    try:
        resp = client.get(f"{url.rstrip('/')}/exec", params={"query": sql, "timings": "true"})
        resp.raise_for_status()
        payload = resp.json()
        timing["total_ms"] = (time.perf_counter() - start) * 1000.0
    except Exception as exc:
        timing["total_ms"] = (time.perf_counter() - start) * 1000.0
        return _envelope("error", [], sql, "rest", [f"rest_query_failed: {type(exc).__name__}: {exc}"], timing)
    if isinstance(payload, dict) and payload.get("error"):
        return _envelope("error", [], sql, "rest", [f"questdb_error: {payload['error']}"], timing)
    server = payload.get("timings") or {}
    timing["execute_ms"] = float(server.get("execute", 0)) / 1e6
    timing["compile_ms"] = float(server.get("compiler", 0)) / 1e6
    columns = [col["name"] for col in payload.get("columns", [])]
    dataset = payload.get("dataset") or []
    rows = [dict(zip(columns, record)) for record in dataset]
    return _envelope("ok", rows, sql, "rest", [], timing)


def run_read_query(
    sql: str,
    *,
    mode: str | None = None,
    url: str = DEFAULT_URL,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Dispatch a read-only query to REST or PGWire based on the resolved mode.

    Falls back to REST (with a caveat) if PGWire is requested but unavailable.
    """
    resolved = resolve_mode(mode)
    if resolved == "pgwire":
        if not pg.pgwire_available():
            res = query_rest_timed(sql, url=url)
            res["caveats"] = list(res.get("caveats", [])) + ["pgwire requested but psycopg unavailable; used REST"]
            return res
        return pg.query_pgwire(sql, dsn=dsn)
    return query_rest_timed(sql, url=url)


def close_all() -> None:
    global _rest_client
    with _rest_lock:
        if _rest_client is not None and not _rest_client.is_closed:
            _rest_client.close()
        _rest_client = None
    pg.close_all()
