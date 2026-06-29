"""Audit QuestDB event tables for corporate action data quality.

Does NOT use vnstock. Inspects:
  - event_news_items
  - event_news_raw_payloads

Outputs structured assessment per symbol:
  - table existence, columns, row counts
  - candidate corporate action detection by title/summary keywords
  - source_status classification
  - adjustment_feasibility

Usage:
  python scripts/audit_questdb_event_tables_for_corporate_actions.py --symbols FPT,VNM --json
  python scripts/audit_questdb_event_tables_for_corporate_actions.py --limit 100 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage.questdb_client import (
    DEFAULT_QUESTDB_URL,
    column_names,
    exec_query,
    exec_rows,
    exec_scalar,
    open_client,
    table_exists,
)

# Keyword groups for corporate action detection
CASH_DIVIDEND_KEYWORDS = [
    "cash dividend",
    "dividend",
    "cổ tức",
    "remaining 2025 cash dividend",
    "payment of",
]

EXRIGHT_KEYWORDS = [
    "ex-right",
    "exright",
    "ex date",
    "ngày giao dịch không hưởng quyền",
]

STOCK_SPLIT_KEYWORDS = [
    "stock dividend",
    "bonus shares",
    "split",
    "chia cổ phiếu",
    "phát hành cổ phiếu",
    "quyền mua",
]

# General news to ignore
IGNORE_KEYWORDS = [
    "annual report",
    "esg report",
    "personnel change",
    "financial statements",
    "quarterly results",
    "audited financial",
    "unaudited financial",
    "agm",
    "annual general meeting",
    "board member",
    "ceo",
    "appointment",
    "resignation",
]


def _matches_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


def _has_ignore_keywords(text: str) -> bool:
    return _matches_any(text, IGNORE_KEYWORDS)


def _classify_event(title: str, summary: str) -> dict[str, Any]:
    full = f"{title} {summary}"
    is_dividend = _matches_any(full, CASH_DIVIDEND_KEYWORDS)
    is_exright = _matches_any(full, EXRIGHT_KEYWORDS)
    is_stock_split = _matches_any(full, STOCK_SPLIT_KEYWORDS)
    is_ignored = _has_ignore_keywords(full)
    return {
        "candidate_corporate_action": bool(
            (is_dividend or is_exright or is_stock_split) and not is_ignored
        ),
        "candidate_dividend": is_dividend and not is_ignored,
        "candidate_exright": is_exright,
        "candidate_stock_split": is_stock_split,
        "likely_general_news": is_ignored,
    }


def _get_table_info(client, base_url: str, table: str) -> dict[str, Any]:
    """Get table existence, columns, row count."""
    if not table_exists(client, base_url, table):
        return {"exists": False, "columns": [], "row_count": 0}
    cols = column_names(client, base_url, table)
    count = exec_scalar(client, base_url, f"SELECT count() FROM {table}")
    return {"exists": True, "columns": cols, "row_count": count}


def _sample_rows(
    client, base_url: str, table: str, limit: int = 5, symbol: str | None = None
) -> list[dict[str, Any]]:
    """Get sample rows from a table, optionally filtered by symbol."""
    sym_filter = f"WHERE symbol = '{symbol}'" if symbol else ""
    sql = f"SELECT * FROM {table} {sym_filter} LIMIT {limit}"
    headers, rows = exec_rows(client, base_url, sql)
    return [dict(zip(headers, r)) for r in rows]


def audit_symbol(
    client, base_url: str, symbol: str
) -> dict[str, Any]:
    """Audit both event tables for a single symbol."""
    items_info = _get_table_info(client, base_url, "event_news_items")
    payloads_info = _get_table_info(client, base_url, "event_news_raw_payloads")

    result = {
        "symbol": symbol,
        "event_news_items": items_info,
        "event_news_raw_payloads": payloads_info,
    }

    # Get raw counts for this symbol
    items_count = 0
    payloads_count = 0
    if items_info["exists"]:
        items_count = exec_scalar(
            client,
            base_url,
            f"SELECT count() FROM event_news_items WHERE symbol = '{symbol}'",
        )
    if payloads_info["exists"]:
        payloads_count = exec_scalar(
            client,
            base_url,
            f"SELECT count() FROM event_news_raw_payloads WHERE symbol = '{symbol}'",
        )

    result["event_news_count"] = items_count
    result["raw_payload_count"] = payloads_count

    # Get candidate corporate action rows
    candidates = []
    if items_info["exists"] and items_count > 0:
        headers, rows = exec_rows(
            client,
            base_url,
            f"""
            SELECT raw_id, symbol, title, summary, source, published_at, quality_status
            FROM event_news_items
            WHERE symbol = '{symbol}'
            LIMIT 200
            """,
        )
        for row in rows:
            rec = dict(zip(headers, row))
            classification = _classify_event(
                rec.get("title", ""), rec.get("summary", "")
            )
            rec.update(classification)
            if classification["candidate_corporate_action"]:
                candidates.append(rec)

    result["candidate_corporate_action_count"] = len(candidates)
    result["candidates"] = candidates[:20]  # Cap at 20

    # Check which raw_paths are joinable
    candidate_raw_ids = [c["raw_id"] for c in candidates]
    result["candidate_raw_ids"] = candidate_raw_ids

    raw_paths_found = []
    if candidate_raw_ids and payloads_info["exists"]:
        ids_list = ",".join(f"'{rid}'" for rid in candidate_raw_ids[:20])
        raw_headers, raw_rows = exec_rows(
            client,
            base_url,
            f"SELECT raw_id, raw_path FROM event_news_raw_payloads WHERE raw_id IN ({ids_list})",
        )
        path_map = {r[0]: r[1] for r in raw_rows}
        raw_paths_found = [path_map.get(rid) for rid in candidate_raw_ids if path_map.get(rid)]
    result["candidate_raw_paths"] = raw_paths_found

    # Determine source_status
    has_items = items_count > 0
    has_payloads = payloads_count > 0
    has_structured_ca = any(
        c.get("candidate_dividend") or c.get("candidate_exright") or c.get("candidate_stock_split")
        for c in candidates
    )

    if not has_items and not has_payloads:
        result["source_status"] = "NO_DB_EVENT_ROWS"
    elif not has_items and has_payloads:
        result["source_status"] = "DB_RAW_PAYLOAD_UNSUPPORTED"
    elif has_items and not payloads_info.get("exists", False):
        result["source_status"] = "DB_NEWS_ONLY"
    elif has_items and payloads_info.get("exists", False):
        # Has both tables
        if has_structured_ca:
            result["source_status"] = "DB_DISCLOSURE_TEXT_CANDIDATE"
        else:
            result["source_status"] = "DB_NEWS_ONLY"
    else:
        result["source_status"] = "DB_NEWS_ONLY"

    # Determine adjustment_feasibility
    # Requires structured ex_date + cash_amount/ratio fields
    has_ex_date = any("ex-date" in str(c.get("title", "")).lower() or
                       "exright" in str(c.get("title", "")).lower() or
                       "ngày giao dịch không hưởng" in str(c.get("title", "")).lower()
                      for c in candidates)
    has_amount = any("$" in str(c.get("summary", "")) or
                      "vnd" in str(c.get("summary", "")).lower() or
                      "đồng" in str(c.get("summary", "")).lower() or
                      "%" in str(c.get("summary", ""))
                      for c in candidates)

    if result["source_status"] == "NO_DB_EVENT_ROWS":
        result["adjustment_feasibility"] = "NO_CORPORATE_ACTION_SOURCE"
    elif result["source_status"] == "DB_DISCLOSURE_TEXT_CANDIDATE":
        # Disclosure text exists but no structured fields
        if has_structured_ca:
            result["adjustment_feasibility"] = "NEEDS_RAW_PAYLOAD_PARSER"
        else:
            result["adjustment_feasibility"] = "INSUFFICIENT_FIELDS"
    else:
        result["adjustment_feasibility"] = "INSUFFICIENT_FIELDS"

    # Available fields check
    result["available_fields"] = items_info["columns"] if items_info["exists"] else []
    # Structured corporate action requires: ex_date, cash_dividend_per_share, currency
    required_for_adjust = {"ex_date", "record_date", "cash_dividend_per_share", "currency"}
    available = set(c.lower() for c in items_info["columns"]) if items_info["exists"] else set()
    result["missing_required_fields"] = sorted(required_for_adjust - available)
    result["source_tables"] = [
        t for t in ["event_news_items", "event_news_raw_payloads"]
        if (t == "event_news_items" and items_info["exists"]) or
           (t == "event_news_raw_payloads" and payloads_info["exists"])
    ]

    return result


def _safe_print_json(obj) -> None:
    """Print JSON with UTF-8 encoding on Windows."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit QuestDB event tables")
    parser.add_argument("--symbols", default="FPT,VNM,HPG,VCB,CTG,VHM")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--questdb-url", default=DEFAULT_QUESTDB_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]

    with open_client() as client:
        # Global table audit
        global_audit = {
            "event_news_items": _get_table_info(client, args.questdb_url, "event_news_items"),
            "event_news_raw_payloads": _get_table_info(client, args.questdb_url, "event_news_raw_payloads"),
        }

        results = []
        for sym in symbols:
            r = audit_symbol(client, args.questdb_url, sym)
            results.append(r)

    output = {
        "global": global_audit,
        "symbols": results,
    }

    if args.json:
        _safe_print_json(output)
    else:
        print("=== QuestDB Event Table Audit ===")
        print(f"event_news_items: exists={global_audit['event_news_items']['exists']}, "
              f"rows={global_audit['event_news_items']['row_count']}, "
              f"cols={global_audit['event_news_items']['columns']}")
        print(f"event_news_raw_payloads: exists={global_audit['event_news_raw_payloads']['exists']}, "
              f"rows={global_audit['event_news_raw_payloads']['row_count']}")
        print()
        for r in results:
            print(f"Symbol: {r['symbol']}")
            print(f"  event_news_count:    {r['event_news_count']}")
            print(f"  raw_payload_count:   {r['raw_payload_count']}")
            print(f"  candidates:           {r['candidate_corporate_action_count']}")
            print(f"  source_status:        {r['source_status']}")
            print(f"  adjustment_feasible: {r['adjustment_feasibility']}")
            print(f"  missing fields:      {r['missing_required_fields']}")
            print(f"  source_tables:       {r['source_tables']}")
            for c in r.get("candidates", [])[:3]:
                print(f"    -> [{c.get('published_at','')}] {c.get('title','')[:80]}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
