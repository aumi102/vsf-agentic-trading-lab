"""Bounded official FPT dividend candidate extraction.

Scope: FPT dividend candidate only (no broad crawling).
Does NOT use vnstock.
Uses existing QuestDB event_news_items to locate the raw HTML, extracts PDF link,
fetches exactly one PDF, extracts text with pdftotext (poppler CLI),
tries to parse structured fields.

Does NOT OCR. Does NOT stage the downloaded PDF.

Usage:
  python scripts/extract_official_fpt_dividend_candidate.py --json
  python scripts/extract_official_fpt_dividend_candidate.py --dry-run --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage.questdb_client import (
    DEFAULT_QUESTDB_URL,
    exec_rows,
    open_client,
)

# Required fields for adjustment
REQUIRED_FIELDS = [
    "ex_date",
    "record_date",
    "payment_date",
    "cash_dividend_per_share",
    "currency",
]

# Raw output dir (not committed)
DEFAULT_RAW_ROOT = ROOT / "data" / "processed" / "approved_source_probe" / "fpt_dividend_2026"
PDFTOTEXT_BIN = "pdftotext"


def _safe_print_json(obj) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _check_pdftotext() -> dict[str, Any]:
    """Check if pdftotext is available."""
    try:
        r = subprocess.run(
            [PDFTOTEXT_BIN, "-v"],
            capture_output=True, text=True, timeout=5,
        )
        version = r.stderr.strip() if r.stderr else r.stdout.strip()
        return {"available": True, "version": version}
    except FileNotFoundError:
        return {"available": False, "error": "pdftotext not found in PATH"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def _find_dividend_pdf_link(html_content: str) -> str | None:
    """Extract PDF link from FPT IR HTML listing page near 'dividend' keyword."""
    # Find all PDF hrefs
    pdf_hrefs = re.findall(r'<a[^>]+href=["\']([^"\']+\.pdf)["\'][^>]*>(.*?)</a>', html_content, re.I | re.DOTALL)
    for href, text in pdf_hrefs:
        clean_text = re.sub(r"<[^>]+>", "", text).strip().lower()
        if "dividend" in clean_text or "cổ tức" in clean_text:
            return href
    # Fallback: any PDF with dividend in href
    for href, _ in pdf_hrefs:
        if "dividend" in href.lower():
            return href
    return None


def _parse_vietnamese_numbers(text: str) -> list[str]:
    """Find Vietnamese-format numbers (e.g. 1.000, 10.500, VND amounts)."""
    # Match numbers with dot separators (thousands) or comma decimals
    return re.findall(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?", text)


def _parse_vnd_amounts(text: str) -> list[dict[str, Any]]:
    """Find VND dividend amounts."""
    # Pattern: number followed by VND or đồng within ~30 chars
    amounts = []
    pattern = re.compile(
        r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:VND|vnd|đồng|đ)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        raw = m.group(1).replace(",", ".")
        try:
            val = float(raw)
            if val > 0 and val < 1_000_000:  # Reasonable dividend range
                amounts.append({
                    "amount": val,
                    "unit": "VND",
                    "raw_text": m.group(0),
                    "context": text[max(0, m.start()-50):m.end()+50],
                })
        except ValueError:
            pass
    return amounts


def _parse_dates(text: str) -> list[dict[str, str]]:
    """Find Vietnamese date patterns."""
    dates = []
    # DD/MM/YYYY or YYYY-MM-DD or similar
    patterns = [
        (r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", "DD/MM/YYYY"),
        (r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", "YYYY/MM/DD"),
        (r"\d{1,2}\.\d{1,2}\.\d{4}", "DD.MM.YYYY"),
    ]
    for pattern, fmt in patterns:
        for m in re.finditer(pattern, text):
            dates.append({"text": m.group(0), "format": fmt})
    return dates


def _extract_fields(text: str, title: str) -> dict[str, Any]:
    """Try to extract structured fields from PDF text."""
    full = f"{title}\n{text}"

    fields: dict[str, Any] = {}
    missing: list[str] = []
    extracted: list[str] = []

    # Event type: cash dividend
    if re.search(r"(dividend|cổ tức|cash)", full, re.I):
        fields["event_type"] = "cash_dividend"
        extracted.append("event_type")

    # VND amounts
    amounts = _parse_vnd_amounts(full)
    if amounts:
        # Take the most likely dividend amount (largest reasonable one)
        fields["candidate_amounts"] = amounts[:5]
        fields["cash_dividend_per_share"] = amounts[0]["amount"] if amounts else None
        if fields["cash_dividend_per_share"]:
            extracted.append("cash_dividend_per_share")
    else:
        missing.append("cash_dividend_per_share")

    fields["currency"] = "VND"
    extracted.append("currency")

    # Dates
    all_dates = _parse_dates(full)
    date_texts = {d["text"] for d in all_dates}

    # Keywords near dates
    ex_date_kw = re.compile(
        r"(ex.?date|ngày không hưởng quyền|ex.right|ngày giao dịch không hưởng quyền)[:\s]+(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.I,
    )
    record_kw = re.compile(
        r"(record|date|ngày chốt|ngày đăng ký|đăng ký cuối cùng)[:\s]+(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.I,
    )
    pay_kw = re.compile(
        r"(payment|ngày thanh toán|thanh toán|cổ tức)[:\s]+(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.I,
    )

    for kw_re, label in [(ex_date_kw, "ex_date"), (record_kw, "record_date"), (pay_kw, "payment_date")]:
        for m in kw_re.finditer(full):
            date_str = m.group(2)
            fields[label] = date_str
            if label not in extracted:
                extracted.append(label)
            break

    # Also find dates near dividend keyword
    div_idx = re.search(r"(dividend|cổ tức)", full, re.I)
    if div_idx and not fields.get("ex_date"):
        window = full[max(0, div_idx.start()-200):div_idx.end()+200]
        dates_in_window = _parse_dates(window)
        if dates_in_window:
            fields["ex_date"] = dates_in_window[0]["text"]
            if "ex_date" not in extracted:
                extracted.append("ex_date")

    for fld in REQUIRED_FIELDS:
        if fld not in fields and fld not in extracted:
            missing.append(fld)

    confidence = len(extracted) / len(REQUIRED_FIELDS) if REQUIRED_FIELDS else 0

    return {
        "extracted_fields": extracted,
        "missing_fields": missing,
        "fields": fields,
        "confidence": round(confidence, 2),
        "candidate_amounts": amounts[:3],
    }


def extract_fpt_dividend(dry_run: bool = False) -> dict[str, Any]:
    """Main extraction pipeline."""
    result: dict[str, Any] = {
        "status": "PENDING",
        "raw_path": None,
        "pdf_sha256": None,
        "text_path": None,
        "fields": None,
        "extraction_status": "PENDING",
        "blocker": None,
    }

    with open_client() as client:
        # 1. Get FPT dividend candidate from QuestDB
        sql = """
        SELECT raw_id, symbol, title, summary, source, published_at
        FROM event_news_items
        WHERE symbol = 'FPT'
        LIMIT 50
        """
        headers, rows = exec_rows(client, DEFAULT_QUESTDB_URL, sql)

        candidate = None
        for row in rows:
            rec = dict(zip(headers, row))
            full = f"{rec.get('title','')} {rec.get('summary','')}"
            if "dividend" in full.lower():
                candidate = rec
                break

        if not candidate:
            result["status"] = "NO_CANDIDATE"
            result["blocker"] = "No dividend candidate in event_news_items"
            return result

        result["candidate"] = {
            "raw_id": candidate["raw_id"],
            "symbol": candidate["symbol"],
            "title": candidate["title"],
            "published_at": str(candidate["published_at"]),
        }

        # 2. Join to raw_payloads
        raw_id = candidate["raw_id"]
        sql2 = f"""
        SELECT raw_path, metadata_path, body_sha256
        FROM event_news_raw_payloads
        WHERE raw_id = '{raw_id}'
        LIMIT 1
        """
        h2, r2 = exec_rows(client, DEFAULT_QUESTDB_URL, sql2)
        if not r2:
            result["status"] = "NO_RAW_PAYLOAD"
            result["blocker"] = "raw_id not found in event_news_raw_payloads"
            return result

        payload = dict(zip(h2, r2[0]))
        raw_html_path = payload.get("raw_path")

        result["source_html_path"] = raw_html_path

        # 3. Read HTML and find PDF link
        if not raw_html_path or not Path(raw_html_path).exists():
            result["status"] = "HTML_FILE_MISSING"
            result["blocker"] = f"HTML file not found: {raw_html_path}"
            return result

        with open(raw_html_path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()

        pdf_rel = _find_dividend_pdf_link(html_content)
        if not pdf_rel:
            result["status"] = "PDF_LINK_NOT_FOUND"
            result["blocker"] = "No PDF link found near dividend keyword in HTML"
            return result

        # Construct full URL
        if pdf_rel.startswith("/"):
            pdf_url = "https://fpt.com" + pdf_rel
        else:
            pdf_url = pdf_rel

        result["pdf_url"] = pdf_url
        result["pdf_rel_path"] = pdf_rel

        if dry_run:
            result["status"] = "DRY_RUN"
            result["extraction_status"] = "DRY_RUN_SKIPPED"
            return result

        # 4. Fetch PDF
        try:
            import httpx
            resp = httpx.get(pdf_url, timeout=30.0, follow_redirects=True)
            if resp.status_code != 200:
                result["status"] = "PDF_FETCH_FAILED"
                result["blocker"] = f"PDF fetch failed: HTTP {resp.status_code}"
                return result
            pdf_bytes = resp.content
            result["pdf_size"] = len(pdf_bytes)
            result["pdf_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
        except Exception as e:
            result["status"] = "PDF_FETCH_FAILED"
            result["blocker"] = f"PDF fetch error: {e}"
            return result

        # 5. Save PDF locally
        raw_root = DEFAULT_RAW_ROOT
        raw_root.mkdir(parents=True, exist_ok=True)
        pdf_path = raw_root / "fpt_dividend_2026_bod_resolution.pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        result["raw_path"] = str(pdf_path)
        result["status"] = "PDF_FETCHED"

        # 6. Check pdftotext
        pdftotext_status = _check_pdftotext()
        result["pdftotext"] = pdftotext_status

        if not pdftotext_status["available"]:
            result["status"] = "PDF_PARSER_MISSING"
            result["extraction_status"] = "INSUFFICIENT_FIELDS"
            result["blocker"] = f"pdftotext not available: {pdftotext_status.get('error', 'unknown')}"
            return result

        # 7. Extract text
        text_path = raw_root / "fpt_dividend_2026_bod_resolution.txt"
        try:
            r = subprocess.run(
                [PDFTOTEXT_BIN, "-layout", "-nopgbrk", str(pdf_path), str(text_path)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                result["status"] = "PDF_TEXT_EXTRACTION_FAILED"
                result["blocker"] = f"pdftotext failed: {r.stderr}"
                return result
            text = text_path.read_text(encoding="utf-8", errors="ignore")
            result["text_size"] = len(text)
            result["text_path"] = str(text_path)

            # Detect scanned/image-based PDF
            if len(text.strip()) < 200:
                result["status"] = "PDF_IMAGE_BASED"
                result["extraction_status"] = "INSUFFICIENT_FIELDS"
                result["blocker"] = (
                    f"PDF appears to be scanned/image-based (only {len(text.strip())} chars of text extracted). "
                    "pdftotext cannot extract text from image layers. "
                    "No OCR available. "
                    "Required fields cannot be extracted without OCR or a text-based PDF."
                )
                result["pdf_is_image_based"] = True
                result["extracted_text_preview"] = text[:500]
                result["missing_required_fields"] = REQUIRED_FIELDS[:]
                return result
        except Exception as e:
            result["status"] = "PDF_TEXT_EXTRACTION_FAILED"
            result["blocker"] = f"Text extraction error: {e}"
            return result

        # 8. Parse fields
        fields_result = _extract_fields(text, candidate["title"])
        result["fields"] = fields_result["fields"]
        result["extraction_status"] = "INSUFFICIENT_FIELDS" if fields_result["missing_fields"] else "PARSEABLE"
        result["confidence"] = fields_result["confidence"]

        # Count missing required fields
        missing_req = [f for f in fields_result["missing_fields"] if f in REQUIRED_FIELDS]
        if missing_req:
            result["status"] = "INSUFFICIENT_FIELDS"
            result["blocker"] = f"Missing required fields: {missing_req}"
            result["missing_required_fields"] = missing_req
        else:
            result["status"] = "EXTRACTED"
            result["extraction_status"] = "PARSEABLE"

        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded official FPT dividend candidate extraction."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Stop before fetching PDF (read-only probe)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = extract_fpt_dividend(dry_run=args.dry_run)

    if args.json:
        _safe_print_json(result)
    else:
        print(f"Status:    {result['status']}")
        print(f"PDF URL:   {result.get('pdf_url', 'N/A')}")
        print(f"PDF Size:  {result.get('pdf_size', 'N/A')}")
        print(f"SHA256:    {result.get('pdf_sha256', 'N/A')}")
        print(f"Raw path:  {result.get('raw_path', 'N/A')}")
        print(f"pdftotext: {result.get('pdftotext', {})}")
        if result.get("fields"):
            print(f"Fields:    {result['fields']}")
        print(f"Confidence: {result.get('confidence', 0)}")
        print(f"Blocker:   {result.get('blocker', 'N/A')}")
        if result.get("missing_required_fields"):
            print(f"Missing:   {result['missing_required_fields']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
