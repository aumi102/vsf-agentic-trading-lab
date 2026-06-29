"""Inspect raw payload for a corporate action candidate.

Does NOT use vnstock. Does NOT make network calls. Does NOT OCR.
Attempts to:
  - Join event_news_items to event_news_raw_payloads
  - Read raw file (JSON/HTML/TXT)
  - Extract structured fields around keywords

Usage:
  python scripts/inspect_event_raw_payload.py --symbol FPT --keyword dividend --json
  python scripts/inspect_event_raw_payload.py --raw-id fpt_ir_b761860ff314 --json
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
    exec_rows,
    open_client,
    table_exists,
)


DIVIDEND_KW = re.compile(
    r"(dividend|cash dividend|cổ tức|record date|payment date|ex.right|"
    r"exright|ex.date|ngày giao dịch không hưởng|vnd|đồng|\d+[.,]\d+)",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(r"(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\s*(?:VND|vnd|đồng)", re.IGNORECASE)
DATE_RE = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}")


def _safe_print_json(obj) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _read_raw_file(path: str) -> dict[str, Any]:
    """Read raw file, detect type, return text."""
    p = Path(path)
    if not p.exists():
        return {"status": "file_not_found", "path": path}

    suffix = p.suffix.lower()
    if suffix in {".html", ".htm"}:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"status": "read_ok", "type": "html", "size": len(content)}
    elif suffix in {".txt", ".text"}:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"status": "read_ok", "type": "text", "size": len(content)}
    elif suffix in {".json"}:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        return {"status": "read_ok", "type": "json", "size": p.stat().st_size, "data": data}
    else:
        return {
            "status": "unsupported_type",
            "type": suffix,
            "size": p.stat().st_size,
            "note": "PDF/other binary - no parser available; see raw_path for manual inspection",
        }


def _search_html_for_pdf_links(html_content: str, keyword: str) -> list[dict[str, str]]:
    """Find PDF links near keyword in HTML."""
    links = []
    # Find all PDF hrefs
    pdf_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+\.pdf)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pdf_pattern.finditer(html_content):
        href = m.group(1)
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if keyword.lower() in text.lower() or keyword.lower() in href.lower():
            links.append({"pdf_url": href, "link_text": text[:200]})
    return links


def _extract_snippets(content: str, keyword: str, window: int = 300) -> list[dict[str, Any]]:
    """Extract text snippets around keyword matches."""
    snippets = []
    for m in re.finditer(re.escape(keyword), content, re.IGNORECASE):
        start = max(0, m.start() - window)
        end = min(len(content), m.end() + window)
        snippet = re.sub(r"\s+", " ", content[start:end]).strip()
        snippets.append(
            {
                "keyword_offset": m.start(),
                "text": snippet,
            }
        )
    return snippets


def inspect_by_keyword(
    client, base_url: str, symbol: str, keyword: str
) -> dict[str, Any]:
    """Find first candidate matching symbol+keyword, inspect its raw payload."""
    # Find candidate in event_news_items
    sql = f"""
    SELECT raw_id, symbol, title, summary, source, published_at, quality_status
    FROM event_news_items
    WHERE symbol = '{symbol}'
    LIMIT 50
    """
    headers, rows = exec_rows(client, base_url, sql)

    candidate = None
    for row in rows:
        rec = dict(zip(headers, row))
        full_text = f"{rec.get('title','')} {rec.get('summary','')}"
        if keyword.lower() in full_text.lower():
            candidate = rec
            break

    if not candidate:
        return {"status": "no_candidate_found", "symbol": symbol, "keyword": keyword}

    raw_id = candidate["raw_id"]
    return _inspect_by_raw_id(client, base_url, raw_id, candidate, keyword)


def _inspect_by_raw_id(
    client, base_url: str, raw_id: str, candidate: dict, keyword: str
) -> dict[str, Any]:
    """Inspect raw payload by raw_id."""
    # Join to raw_payloads
    sql = f"""
    SELECT raw_path, metadata_path, body_sha256, parser_version, quality_status
    FROM event_news_raw_payloads
    WHERE raw_id = '{raw_id}'
    LIMIT 1
    """
    headers, rows = exec_rows(client, base_url, sql)

    result = {
        "symbol": candidate.get("symbol"),
        "raw_id": raw_id,
        "title": candidate.get("title"),
        "summary": candidate.get("summary"),
        "published_at": candidate.get("published_at"),
        "quality_status": candidate.get("quality_status"),
    }

    if not rows:
        result["payload_status"] = "no_raw_payload_found"
        result["structured_fields"] = None
        result["extraction_status"] = "INSUFFICIENT_FIELDS"
        return result

    payload_rec = dict(zip(headers, rows[0]))
    raw_path = payload_rec.get("raw_path")
    metadata_path = payload_rec.get("metadata_path")

    result["raw_path"] = raw_path
    result["metadata_path"] = metadata_path
    result["body_sha256"] = payload_rec.get("body_sha256")
    result["parser_version"] = payload_rec.get("parser_version")

    # Read raw file
    file_info = _read_raw_file(raw_path)
    result["file_status"] = file_info.get("status")
    result["file_type"] = file_info.get("type")
    result["file_size"] = file_info.get("size")

    extraction_status = "INSUFFICIENT_FIELDS"
    structured_fields: dict[str, Any] | None = None

    if file_info.get("status") == "read_ok":
        ftype = file_info.get("type")
        if ftype in ("html", "text"):
            content = open(raw_path, "r", encoding="utf-8", errors="ignore").read()

            # Check if it's actually a disclosure listing page (not the PDF itself)
            is_listing_page = bool(
                re.search(r"(information-disclosures|download-section|\.pdf['\"])", content, re.I)
            )
            has_direct_dividend_text = keyword.lower() in content.lower()

            if is_listing_page and not has_direct_dividend_text:
                result["page_type"] = "ir_listing_page"
                result["note"] = "HTML is an IR listing page; dividend details are in a linked PDF"
                # Try to find the PDF link
                pdf_links = _search_html_for_pdf_links(content, keyword)
                result["pdf_links_found"] = pdf_links

            # Try to extract snippets
            snippets = _extract_snippets(content, keyword)
            result["keyword_snippets"] = snippets[:5]

            # Try to find structured fields
            amounts = AMOUNT_RE.findall(content)
            dates = DATE_RE.findall(content)

            if amounts or dates:
                structured_fields = {
                    "candidate_amounts_found": amounts[:5],
                    "candidate_dates_found": dates[:10],
                }
                extraction_status = "NEEDS_RAW_PAYLOAD_PARSER"
        elif ftype == "json":
            structured_fields = file_info.get("data")
            extraction_status = "PARSEABLE"
        else:
            extraction_status = "INSUFFICIENT_FIELDS"
            result["note"] = file_info.get("note", "Unsupported file type")

    elif file_info.get("status") == "unsupported_type":
        result["note"] = file_info.get("note")
        extraction_status = "INSUFFICIENT_FIELDS"

    result["structured_fields"] = structured_fields
    result["extraction_status"] = extraction_status

    # Required structured fields for adjustment
    required = ["ex_date", "record_date", "cash_dividend_per_share", "currency"]
    available = []
    missing = list(required)

    if structured_fields:
        if structured_fields.get("candidate_dates_found"):
            available.append("ex_date")
            available.append("record_date")
        if structured_fields.get("candidate_amounts_found"):
            available.append("cash_dividend_per_share")
        missing = [f for f in required if f not in available]

    result["required_structured_fields"] = required
    result["extracted_fields"] = available
    result["missing_fields"] = missing

    if extraction_status == "INSUFFICIENT_FIELDS" or missing:
        result["adjustment_feasibility"] = "INSUFFICIENT_FIELDS"
    elif extraction_status == "NEEDS_RAW_PAYLOAD_PARSER":
        result["adjustment_feasibility"] = "NEEDS_RAW_PAYLOAD_PARSER"
    else:
        result["adjustment_feasibility"] = "PARSEABLE"

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect event raw payload")
    parser.add_argument("--symbol", default="FPT")
    parser.add_argument("--keyword", default="dividend")
    parser.add_argument("--raw-id", default=None)
    parser.add_argument("--questdb-url", default=DEFAULT_QUESTDB_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    with open_client() as client:
        if args.raw_id:
            # Lookup candidate by raw_id
            sql = f"""
            SELECT raw_id, symbol, title, summary, source, published_at, quality_status
            FROM event_news_items WHERE raw_id = '{args.raw_id}' LIMIT 1
            """
            headers, rows = exec_rows(client, args.questdb_url, sql)
            if not rows:
                print(json.dumps({"error": f"raw_id {args.raw_id} not found"}))
                return 1
            candidate = dict(zip(headers, rows[0]))
            result = _inspect_by_raw_id(
                client, args.questdb_url, args.raw_id, candidate, args.keyword
            )
        else:
            result = inspect_by_keyword(
                client, args.questdb_url, args.symbol, args.keyword
            )

    if args.json:
        _safe_print_json(result)
    else:
        print(f"Symbol:        {result.get('symbol')}")
        print(f"Raw ID:        {result.get('raw_id')}")
        print(f"Title:         {result.get('title','')[:100]}")
        print(f"Raw Path:      {result.get('raw_path')}")
        print(f"File Status:   {result.get('file_status')}")
        print(f"File Type:     {result.get('file_type')}")
        print(f"Extraction:    {result.get('extraction_status')}")
        print(f"Adjustment:    {result.get('adjustment_feasibility')}")
        print(f"Extracted:     {result.get('extracted_fields')}")
        print(f"Missing:       {result.get('missing_fields')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
