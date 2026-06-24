"""Ingest parsed official disclosure event/news probe records into QuestDB.

This creates/writes only:
  - event_news_raw_payloads
  - event_news_items

It does not mutate market, FA, feature, signal, or backtest tables.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.storage import questdb_client as qdb  # noqa: E402

DEFAULT_BRONZE_ROOT = ROOT / "data" / "processed" / "dry_run" / "event_news_probe" / "bronze"
TABLES = ("event_news_raw_payloads", "event_news_items")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
RAW_COLUMNS = [
    "captured_at",
    "run_id",
    "raw_id",
    "symbol",
    "source",
    "source_url",
    "raw_path",
    "metadata_path",
    "body_sha256",
    "parser_version",
    "schema_version",
    "quality_status",
]
ITEM_COLUMNS = [
    "published_at",
    "symbol",
    "title",
    "summary",
    "source",
    "source_url",
    "category",
    "raw_id",
    "run_id",
    "quality_status",
]


def _parse_symbols(value: str) -> set[str]:
    symbols = {part.strip().upper() for part in value.split(",") if part.strip()}
    invalid = [symbol for symbol in symbols if not SYMBOL_RE.fullmatch(symbol)]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid symbols: {', '.join(invalid)}")
    return symbols


def _ddl(table: str) -> str:
    if table == "event_news_raw_payloads":
        return """CREATE TABLE IF NOT EXISTS event_news_raw_payloads (
            captured_at TIMESTAMP,
            run_id SYMBOL CAPACITY 4096 CACHE,
            raw_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            source SYMBOL CAPACITY 512 CACHE,
            source_url STRING,
            raw_path STRING,
            metadata_path STRING,
            body_sha256 SYMBOL CAPACITY 4096 CACHE,
            parser_version SYMBOL CAPACITY 512 CACHE,
            schema_version SYMBOL CAPACITY 512 CACHE,
            quality_status SYMBOL CAPACITY 256 CACHE
        ) TIMESTAMP(captured_at) PARTITION BY YEAR WAL"""
    if table == "event_news_items":
        return """CREATE TABLE IF NOT EXISTS event_news_items (
            published_at TIMESTAMP,
            symbol SYMBOL CAPACITY 4096 CACHE,
            title STRING,
            summary STRING,
            source SYMBOL CAPACITY 512 CACHE,
            source_url STRING,
            category SYMBOL CAPACITY 512 CACHE,
            raw_id SYMBOL CAPACITY 4096 CACHE,
            run_id SYMBOL CAPACITY 4096 CACHE,
            quality_status SYMBOL CAPACITY 256 CACHE
        ) TIMESTAMP(published_at) PARTITION BY YEAR WAL"""
    raise ValueError(f"unknown event table: {table}")


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return out.getvalue().encode("utf-8")


def _timestamp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text}T00:00:00.000000Z"
    return text.replace("+00:00", "Z")


def _latest_run_id(bronze_root: Path) -> str:
    candidates = [path.name for path in bronze_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no event/news probe bronze runs under {bronze_root}")
    return sorted(candidates)[-1]


def _record_paths(bronze_root: Path, run_id: str) -> list[Path]:
    run_dir = bronze_root / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"bronze run not found: {run_dir}")
    return sorted(run_dir.rglob("disclosure_record*.json"))


def _load_rows(bronze_root: Path, run_id: str, symbols: set[str], limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows: list[dict[str, Any]] = []
    item_rows: list[dict[str, Any]] = []
    for path in _record_paths(bronze_root, run_id):
        record = json.loads(path.read_text(encoding="utf-8"))
        symbol = str(record.get("symbol") or "").upper()
        if symbols and symbol not in symbols:
            continue
        raw_id = str(record.get("disclosure_id") or path.stem)
        source = f"{record.get('source_family') or 'unknown'}:{record.get('adapter_name') or 'unknown'}"
        published_at = _timestamp(record.get("published_at") or record.get("published_date") or record.get("crawled_at"))
        raw_rows.append(
            {
                "captured_at": _timestamp(record.get("crawled_at")),
                "run_id": run_id,
                "raw_id": raw_id,
                "symbol": symbol,
                "source": source,
                "source_url": record.get("page_url") or record.get("document_url") or "",
                "raw_path": record.get("raw_path") or "",
                "metadata_path": record.get("metadata_path") or "",
                "body_sha256": record.get("body_sha256") or "",
                "parser_version": record.get("parser_version") or "",
                "schema_version": record.get("schema_version") or "",
                "quality_status": record.get("quality_status") or "",
            }
        )
        item_rows.append(
            {
                "published_at": published_at,
                "symbol": symbol,
                "title": record.get("title") or "",
                "summary": record.get("attachment_name") or record.get("title") or "",
                "source": source,
                "source_url": record.get("document_url") or record.get("page_url") or "",
                "category": record.get("document_category") or "disclosure",
                "raw_id": raw_id,
                "run_id": run_id,
                "quality_status": record.get("quality_status") or "",
            }
        )
        if limit and len(item_rows) >= limit:
            break
    return raw_rows, item_rows


def ingest(
    *,
    questdb_url: str,
    bronze_root: Path,
    run_id: str,
    symbols: set[str],
    limit: int,
    replace_table: bool,
) -> dict[str, Any]:
    raw_rows, item_rows = _load_rows(bronze_root, run_id, symbols, limit)
    base = questdb_url.rstrip("/")
    with qdb.open_client(timeout_seconds=180.0) as client:
        if replace_table:
            print("REPLACING ONLY event_news_* TABLES; market/FA/backtest tables untouched")
            for table in TABLES:
                qdb.exec_query(client, base, f"DROP TABLE IF EXISTS {table}")
        for table in TABLES:
            qdb.exec_query(client, base, _ddl(table))
        raw_inserted = qdb.imp_csv(client, base, "event_news_raw_payloads", _csv_bytes(raw_rows, RAW_COLUMNS), timeout_seconds=180.0) if raw_rows else 0
        item_inserted = qdb.imp_csv(client, base, "event_news_items", _csv_bytes(item_rows, ITEM_COLUMNS), timeout_seconds=180.0) if item_rows else 0
        for table in TABLES:
            qdb.wait_wal_applied(client, base, table, attempts=120)
    return {
        "run_id": run_id,
        "symbols_requested": sorted(symbols),
        "raw_payload_rows_inserted": raw_inserted,
        "event_news_rows_inserted": item_inserted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest parsed event/news disclosure records into QuestDB.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    parser.add_argument("--bronze-root", default=str(DEFAULT_BRONZE_ROOT))
    parser.add_argument("--run-id", default="latest")
    parser.add_argument("--symbols", default="FPT,VNM,HPG")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--replace-table", action="store_true")
    args = parser.parse_args()
    bronze_root = Path(args.bronze_root)
    if not bronze_root.is_absolute():
        bronze_root = ROOT / bronze_root
    run_id = _latest_run_id(bronze_root) if args.run_id == "latest" else args.run_id
    symbols = _parse_symbols(args.symbols)
    result = ingest(
        questdb_url=args.questdb_url,
        bronze_root=bronze_root,
        run_id=run_id,
        symbols=symbols,
        limit=max(1, int(args.limit)),
        replace_table=args.replace_table,
    )
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
