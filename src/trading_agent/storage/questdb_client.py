"""Minimal QuestDB REST client used by ingestion and the agent tool layer.

QuestDB is reached over its HTTP REST API (default http://localhost:9000):
  * /exec -> run SQL (DDL + queries), JSON response
  * /imp  -> bulk CSV load (append into an existing WAL table; DEDUP keys make
             re-runs idempotent)

This module is deliberately small and dependency-light (httpx only) so both the
batch ingestion script and the read-only market-data tool can share it.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

DEFAULT_QUESTDB_URL = "http://localhost:9000"


class QuestDBError(RuntimeError):
    """Raised when QuestDB returns an error payload or an unexpected response."""


def open_client(timeout_seconds: float = 60.0) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds)


def exec_query(client: httpx.Client, base_url: str, sql: str) -> dict[str, Any]:
    """Run SQL via /exec and return the parsed JSON payload (raises on error)."""
    resp = client.get(f"{base_url.rstrip('/')}/exec", params={"query": sql})
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise QuestDBError(f"QuestDB /exec error for [{sql[:120]}]: {payload['error']}")
    return payload


def exec_rows(client: httpx.Client, base_url: str, sql: str) -> tuple[list[str], list[list[Any]]]:
    """Return (column_names, dataset_rows) for a query."""
    payload = exec_query(client, base_url, sql)
    columns = [col["name"] for col in payload.get("columns", [])]
    dataset = payload.get("dataset") or []
    return columns, dataset


def exec_scalar(client: httpx.Client, base_url: str, sql: str, default: Any = 0) -> Any:
    _, dataset = exec_rows(client, base_url, sql)
    if not dataset or not dataset[0]:
        return default
    return dataset[0][0]


def table_exists(client: httpx.Client, base_url: str, table: str) -> bool:
    _, dataset = exec_rows(client, base_url, "SHOW TABLES")
    names = {str(row[0]) for row in dataset if row}
    return table in names


def column_names(client: httpx.Client, base_url: str, table: str) -> list[str]:
    if not table_exists(client, base_url, table):
        return []
    _, dataset = exec_rows(client, base_url, f"SHOW COLUMNS FROM {table}")
    return [str(row[0]) for row in dataset if row]


def imp_csv(
    client: httpx.Client,
    base_url: str,
    table: str,
    csv_bytes: bytes,
    *,
    timeout_seconds: float = 120.0,
) -> int:
    """Bulk-load a CSV (with header row) into an existing table; return row count."""
    files = {"data": (f"{table}.csv", csv_bytes, "text/csv")}
    resp = client.post(
        f"{base_url.rstrip('/')}/imp",
        params={"name": table, "overwrite": "false", "forceHeader": "true"},
        files=files,
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    text = resp.text
    # QuestDB returns a text table; a hard failure has "error" without a rows summary.
    if "error" in text.lower() and "rows handled" not in text.lower() and "imported" not in text.lower():
        raise QuestDBError(f"QuestDB /imp failed for table '{table}': {text[:500]}")
    return max(csv_bytes.count(b"\n") - 1, 0)


def wait_wal_applied(client: httpx.Client, base_url: str, table: str, attempts: int = 60) -> bool:
    """Block until the WAL writer has applied pending transactions for `table`.

    QuestDB applies WAL writes asynchronously, so a count() immediately after
    /imp can undercount. Returns True if caught up, False if it timed out.
    """
    sql = f"SELECT writerTxn, sequencerTxn FROM wal_tables() WHERE name = '{table}'"
    for _ in range(attempts):
        try:
            _, dataset = exec_rows(client, base_url, sql)
        except (QuestDBError, httpx.HTTPError):
            return False
        if dataset and dataset[0] and dataset[0][0] == dataset[0][1]:
            return True
        time.sleep(0.25)
    return False
