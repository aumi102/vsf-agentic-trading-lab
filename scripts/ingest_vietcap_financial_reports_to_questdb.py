"""Fetch Vietcap IQ financial statements and load long-format facts into QuestDB.

This script does not touch OHLCV ingestion and never mutates ``daily_prices``.
Raw payloads and metadata are cached under ignored ``data/raw`` paths.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_vietcap_iq_fa_payloads_dry_run import parse_payload  # noqa: E402
from probe_vietcap_iq_fa_httpx_session import (  # noqa: E402
    build_default_api_url,
    run_fa_direct_parity_diagnostic,
)
from trading_agent.storage import questdb_client as qdb  # noqa: E402

STATEMENTS = {
    "balance_sheet": ("BALANCE_SHEET", "fa_balance_sheet"),
    "income_statement": ("INCOME_STATEMENT", "fa_income_statement"),
    "cash_flow": ("CASH_FLOW", "fa_cash_flow"),
    "notes": ("NOTE", "fa_notes"),
    "note": ("NOTE", "fa_notes"),
}
FA_TABLES = {table for _, table in STATEMENTS.values()} | {"fa_raw_payloads"}
RAW_ROOT = ROOT / "data/raw/vietcap_iq_financial_reports"
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    symbols = list(dict.fromkeys(s.strip().upper() for s in raw.split(",") if s.strip()))
    invalid = [s for s in symbols if not SYMBOL_RE.fullmatch(s)]
    if invalid:
        raise ValueError(f"invalid symbols: {', '.join(invalid)}")
    return symbols


def _parse_statements(raw: str) -> list[tuple[str, str, str]]:
    names = [s.strip().lower() for s in raw.split(",") if s.strip()]
    invalid = [s for s in names if s not in STATEMENTS]
    if invalid:
        raise ValueError(f"invalid statements: {', '.join(invalid)}")
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name in names:
        section, table = STATEMENTS[name]
        if section not in seen:
            out.append((name, section, table))
            seen.add(section)
    return out


def _select_symbols(client, base_url: str, explicit: list[str], limit: int | None) -> list[str]:
    if explicit:
        return explicit
    if limit is None:
        raise ValueError("provide --symbols or --limit-symbols")
    _, rows = qdb.exec_rows(client, base_url, f"SELECT DISTINCT symbol FROM securities ORDER BY symbol LIMIT {limit}")
    return [str(row[0]) for row in rows if row]


def _ddl(table: str) -> str:
    if table == "fa_raw_payloads":
        return """CREATE TABLE IF NOT EXISTS fa_raw_payloads (
            crawled_at TIMESTAMP,
            symbol SYMBOL CAPACITY 4096 CACHE,
            statement_type SYMBOL CAPACITY 256 CACHE,
            source SYMBOL CAPACITY 256 CACHE,
            run_id SYMBOL CAPACITY 4096 CACHE,
            raw_payload_ref STRING,
            metadata_ref STRING,
            http_status INT,
            access_status SYMBOL CAPACITY 256 CACHE,
            content_hash SYMBOL CAPACITY 4096 CACHE,
            quality_status SYMBOL CAPACITY 256 CACHE
        ) TIMESTAMP(crawled_at) PARTITION BY YEAR WAL"""
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        public_date TIMESTAMP,
        security_id SYMBOL CAPACITY 4096 CACHE,
        symbol SYMBOL CAPACITY 4096 CACHE,
        statement_type SYMBOL CAPACITY 256 CACHE,
        period_type SYMBOL CAPACITY 256 CACHE,
        fiscal_year INT,
        fiscal_quarter INT,
        period_end_date TIMESTAMP,
        metric_code SYMBOL CAPACITY 4096 CACHE,
        metric_name STRING,
        metric_value DOUBLE,
        metric_value_raw STRING,
        currency SYMBOL CAPACITY 256 CACHE,
        unit SYMBOL CAPACITY 256 CACHE,
        source SYMBOL CAPACITY 256 CACHE,
        run_id SYMBOL CAPACITY 4096 CACHE,
        raw_payload_ref STRING,
        quality_status SYMBOL CAPACITY 256 CACHE
    ) TIMESTAMP(public_date) PARTITION BY YEAR WAL"""


def _ensure_tables(client, base_url: str) -> None:
    for table in sorted(FA_TABLES):
        qdb.exec_query(client, base_url, _ddl(table))


def _period_end(fiscal_year: int, fiscal_quarter: int | None) -> str:
    if fiscal_quarter == 1:
        return f"{fiscal_year}-03-31T00:00:00.000000Z"
    if fiscal_quarter == 2:
        return f"{fiscal_year}-06-30T00:00:00.000000Z"
    if fiscal_quarter == 3:
        return f"{fiscal_year}-09-30T00:00:00.000000Z"
    return f"{fiscal_year}-12-31T00:00:00.000000Z"


def _timestamp(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10] + "T00:00:00.000000Z"
    return fallback


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    return out.getvalue().encode("utf-8")


FA_COLUMNS = [
    "public_date", "security_id", "symbol", "statement_type", "period_type", "fiscal_year",
    "fiscal_quarter", "period_end_date", "metric_code", "metric_name", "metric_value",
    "metric_value_raw", "currency", "unit", "source", "run_id", "raw_payload_ref", "quality_status",
]
RAW_COLUMNS = [
    "crawled_at", "symbol", "statement_type", "source", "run_id", "raw_payload_ref",
    "metadata_ref", "http_status", "access_status", "content_hash", "quality_status",
]


def _normalize_facts(facts: list[dict[str, Any]], table: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fact in facts:
        try:
            year = int(fact.get("fiscal_year") or 0)
        except (TypeError, ValueError):
            continue
        quarter_raw = fact.get("fiscal_quarter")
        try:
            quarter = int(quarter_raw) if str(quarter_raw).strip() else None
        except (TypeError, ValueError):
            quarter = None
        period_end = _period_end(year, quarter)
        value_raw = fact.get("value")
        value = ""
        if value_raw not in (None, ""):
            try:
                value = float(value_raw)
            except (TypeError, ValueError):
                value = ""
        rows.append({
            "public_date": _timestamp(fact.get("public_date"), period_end),
            "security_id": f"vietcap_iq:{str(fact.get('symbol') or '').upper()}",
            "symbol": str(fact.get("symbol") or "").upper(),
            "statement_type": str(fact.get("statement_type") or ""),
            "period_type": "QUARTER" if fact.get("period_type") == "quarter" else "YEAR",
            "fiscal_year": year,
            "fiscal_quarter": quarter if quarter is not None else "",
            "period_end_date": period_end,
            "metric_code": fact.get("line_item_code") or "",
            "metric_name": fact.get("line_item_name_en") or "",
            "metric_value": value,
            "metric_value_raw": "" if value_raw is None else str(value_raw),
            "currency": fact.get("currency") or "",
            "unit": fact.get("unit") or "",
            "source": "vietcap_iq",
            "run_id": fact.get("source_run_id") or "",
            "raw_payload_ref": fact.get("source_payload_path") or "",
            "quality_status": "metric_mapping_unverified",
        })
    return rows


def _fetch_with_retry(symbol: str, section: str, run_id: str, output_root: Path, timeout: float, retries: int) -> dict[str, Any]:
    dataset = f"vietcap_iq_fa_{section.lower()}_{symbol.lower()}"
    for attempt in range(retries + 1):
        result = run_fa_direct_parity_diagnostic(
            symbol=symbol,
            section=section,
            target_url=build_default_api_url(symbol, section),
            dataset=dataset,
            output_root=output_root,
            timeout_seconds=timeout,
            run_id=run_id,
        )
        if result.get("http_status") != 429:
            return result
        sleep_s = min(30, 2 ** attempt)
        print(f"rate_limited symbol={symbol} section={section} retry_in={sleep_s}s")
        time.sleep(sleep_s)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Vietcap IQ financial statements into QuestDB FA tables.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbols")
    group.add_argument("--limit-symbols", type=int)
    parser.add_argument("--statements", default="balance_sheet,income_statement,cash_flow,notes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    try:
        explicit = _parse_symbols(args.symbols)
        statements = _parse_statements(args.statements)
    except ValueError as exc:
        parser.error(str(exc))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_url = args.questdb_url.rstrip("/")
    failures: list[dict[str, Any]] = []
    row_counts_by_table = {table: 0 for _, _, table in statements}
    raw_rows: list[dict[str, Any]] = []
    with qdb.open_client(timeout_seconds=300.0) as client:
        symbols = _select_symbols(client, base_url, explicit, args.limit_symbols)
        if not args.dry_run:
            _ensure_tables(client, base_url)
        for symbol in symbols:
            for _, section, table in statements:
                result = _fetch_with_retry(symbol, section, run_id, RAW_ROOT, args.timeout_seconds, args.retries)
                raw_rows.append({
                    "crawled_at": result.get("crawled_at") or datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "statement_type": section,
                    "source": "vietcap_iq",
                    "run_id": run_id,
                    "raw_payload_ref": result.get("raw_path") or "",
                    "metadata_ref": result.get("metadata_path") or "",
                    "http_status": result.get("http_status") or "",
                    "access_status": result.get("access_status") or "",
                    "content_hash": result.get("content_hash") or "",
                    "quality_status": "raw_verified" if result.get("access_status") == "verified" else "fetch_failed",
                })
                if result.get("access_status") != "verified" or not result.get("raw_path"):
                    failures.append({"symbol": symbol, "section": section, "status": result.get("access_status"), "http": result.get("http_status"), "errors": result.get("errors")})
                    continue
                facts, errors, stats = parse_payload(result)
                if errors:
                    failures.extend({"symbol": symbol, "section": section, **err} for err in errors[:5])
                rows = _normalize_facts(facts, table)
                if not args.dry_run and rows:
                    qdb.imp_csv(client, base_url, table, _csv_bytes(rows, FA_COLUMNS), timeout_seconds=180.0)
                    qdb.wait_wal_applied(client, base_url, table, attempts=240)
                row_counts_by_table[table] += len(rows)
                print(f"symbol={symbol} section={section} facts={len(rows)} q_rows={stats.get('quarter_rows_read')} y_rows={stats.get('year_rows_read')}")
        if not args.dry_run and raw_rows:
            qdb.imp_csv(client, base_url, "fa_raw_payloads", _csv_bytes(raw_rows, RAW_COLUMNS), timeout_seconds=120.0)
            qdb.wait_wal_applied(client, base_url, "fa_raw_payloads", attempts=240)
    print(f"run_id={run_id}")
    print(f"symbols_processed={','.join(symbols)}")
    suffix = "rows_prepared" if args.dry_run else "rows_inserted"
    for table, count in row_counts_by_table.items():
        print(f"{table}_{suffix}={count}")
    print(f"raw_payload_rows={len(raw_rows)}")
    print(f"failures={json.dumps(failures, ensure_ascii=False)}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
