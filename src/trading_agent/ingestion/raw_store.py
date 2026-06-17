from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from trading_agent.ingestion.run_log import utc_now_iso


def build_raw_payload_record(
    *,
    run_id: str,
    source: str,
    symbol: str,
    raw_path: str | Path,
    metadata_path: str | Path,
) -> dict[str, object]:
    raw = Path(raw_path)
    metadata = Path(metadata_path)
    meta = _read_metadata(metadata)
    content_hash = str(meta.get("content_hash") or _sha256(raw))
    row_count = _row_count(raw, meta)
    observed_at = str(meta.get("crawled_at") or utc_now_iso())
    logical_path = f"{source}/{symbol}/{content_hash[:16]}"
    status = str(meta.get("status") or meta.get("access_status") or "unknown")
    return {
        "payload_id": f"{run_id}:{symbol}:{content_hash[:16]}",
        "run_id": run_id,
        "source": source,
        "symbol": symbol,
        "observed_at": observed_at,
        "content_hash": content_hash,
        "raw_path": str(raw),
        "metadata_path": str(metadata),
        "logical_path": logical_path,
        "row_count": row_count,
        "status": status,
    }


def record_raw_payload(con: sqlite3.Connection, record: dict[str, object]) -> None:
    columns = [
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
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    update_sql = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    con.execute(
        f"""
        INSERT INTO raw_source_payloads ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT(payload_id) DO UPDATE SET {update_sql}
        """,
        tuple(record.get(column) for column in columns),
    )


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_count(raw_path: Path, metadata: dict[str, Any]) -> int:
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        value = metadata.get("row_count")
        if isinstance(value, int):
            return value
        return 0
    if isinstance(payload, list):
        count = 0
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("t"), list):
                count += len(item["t"])
            else:
                count += 1
        return count
    return 1 if payload is not None else 0
