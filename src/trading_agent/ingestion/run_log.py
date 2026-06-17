from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id(source: str, mode: str, started_at: str | None = None) -> str:
    timestamp = started_at or utc_now_iso()
    compact = (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace("+00:00", "Z")
        .replace(".", "")
    )
    return f"{source}:{mode}:{compact}"


def start_source_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    source: str,
    mode: str,
    symbols_requested: list[str],
    allow_network: bool,
    caveats: list[str] | None = None,
    started_at: str | None = None,
) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO source_runs (
            run_id, source, mode, status, started_at, completed_at,
            symbols_requested_json, symbols_loaded_json, symbols_failed_json,
            allow_network, caveats_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source,
            mode,
            "running",
            started_at or utc_now_iso(),
            None,
            _json(symbols_requested),
            _json([]),
            _json([]),
            1 if allow_network else 0,
            _json(caveats or []),
        ),
    )
    con.commit()


def complete_source_run(
    con: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    symbols_loaded: list[str],
    symbols_failed: list[str],
    caveats: list[str],
    completed_at: str | None = None,
) -> None:
    con.execute(
        """
        UPDATE source_runs
        SET status = ?,
            completed_at = ?,
            symbols_loaded_json = ?,
            symbols_failed_json = ?,
            caveats_json = ?
        WHERE run_id = ?
        """,
        (
            status,
            completed_at or utc_now_iso(),
            _json(symbols_loaded),
            _json(symbols_failed),
            _json(caveats),
            run_id,
        ),
    )
    con.commit()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
