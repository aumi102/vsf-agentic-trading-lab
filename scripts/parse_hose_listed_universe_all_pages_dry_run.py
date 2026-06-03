from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.hose_listed_universe_parser import parse_hose_listed_universe_payload


DEFAULT_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": "vsf-hose-listed-universe-dry-run/0.1",
    "Referer": "https://www.hsx.vn/",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and parse all HOSE listed-stock universe pages into dry-run canonical CSV outputs.")
    parser.add_argument("--metadata-path", default="", help="Optional page-1 HOSE listed universe metadata JSON path.")
    parser.add_argument("--raw-base-dir", default="data/raw/source_probe/source=hose")
    parser.add_argument("--output-base-dir", default="data/processed/dry_run/hose_listed_universe_all_pages")
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_base_dir) / run_id
    raw_pages_dir = output_dir / "raw_pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        page1_metadata_path = Path(args.metadata_path) if args.metadata_path else find_latest_verified_metadata(Path(args.raw_base_dir))
        page1_metadata = _read_json(page1_metadata_path)
        page1_payload_path = Path(page1_metadata.get("raw_path", page1_metadata_path.parent / "payload.json"))
        page1_payload = _read_json(page1_payload_path)
        page1_rows, page1_paging = _extract_page_payload(page1_payload)
        page_size = _clean_int(page1_paging.get("pageSize")) or 30
        total_pages = _clean_int(page1_paging.get("totalPages")) or 1
        total_count = _clean_int(page1_paging.get("totalCount")) or len(page1_rows)
        endpoint = str(page1_metadata.get("endpoint_or_surface") or "")
        if not endpoint:
            raise ValueError("HOSE listed universe metadata does not contain endpoint_or_surface.")

        manifest = fetch_all_pages(
            endpoint=endpoint,
            page_size=page_size,
            total_pages=total_pages,
            raw_pages_dir=raw_pages_dir,
            timeout=args.timeout,
        )
        manifest_path = raw_pages_dir / "page_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        combined = parse_collected_pages(raw_pages_dir=raw_pages_dir, run_id=run_id)
        summary = build_all_pages_summary(
            page1_metadata=page1_metadata,
            page1_metadata_path=page1_metadata_path,
            page_size=page_size,
            total_pages=total_pages,
            total_count=total_count,
            manifest=manifest,
            combined=combined,
            run_id=run_id,
            output_dir=output_dir,
        )
    except Exception as exc:
        print(f"hose_listed_universe_all_pages_dry_run_failed={exc}", file=sys.stderr)
        return 1

    securities_path = output_dir / "securities_master.csv"
    listings_path = output_dir / "exchange_listings.csv"
    universe_path = output_dir / "symbol_universe.csv"
    report_path = output_dir / "validation_report.md"
    summary_path = output_dir / "validation_summary.json"

    combined["securities_master"].to_csv(securities_path, index=False)
    combined["exchange_listings"].to_csv(listings_path, index=False)
    combined["symbol_universe"].to_csv(universe_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(build_validation_report(summary, securities_path, listings_path, universe_path, raw_pages_dir), encoding="utf-8")

    print(f"run_id={run_id}")
    print(f"metadata_path={page1_metadata_path}")
    print(f"raw_pages_dir={raw_pages_dir}")
    print(f"securities_master={securities_path}")
    print(f"exchange_listings={listings_path}")
    print(f"symbol_universe={universe_path}")
    print(f"validation_report={report_path}")
    print(f"validation_summary={summary_path}")
    print(f"requested_page_count={summary['requested_page_count']}")
    print(f"fetched_page_count={summary['fetched_page_count']}")
    print(f"parsed_total_rows={summary['parsed_total_rows']}")
    print(f"quality_pass_count={summary['quality_pass_count']}")
    print(f"quality_warn_count={summary['quality_warn_count']}")
    print(f"quality_fail_count={summary['quality_fail_count']}")
    return 0


def find_latest_verified_metadata(base_dir: Path) -> Path:
    candidates: list[tuple[str, Path]] = []
    for metadata_path in base_dir.glob("run_id=*/**/metadata.json"):
        metadata = _read_json(metadata_path)
        if metadata.get("source_name") != "hose":
            continue
        if metadata.get("dataset") != "hose_listed_stock_universe":
            continue
        if metadata.get("access_status") != "verified" or metadata.get("status") != "success":
            continue
        candidates.append((str(metadata.get("crawled_at") or metadata_path.stat().st_mtime), metadata_path))
    if not candidates:
        raise FileNotFoundError(f"No verified HOSE listed-stock universe metadata found under {base_dir}.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def fetch_all_pages(*, endpoint: str, page_size: int, total_pages: int, raw_pages_dir: Path, timeout: int = 30) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page_index in range(1, total_pages + 1):
        url = _page_url(endpoint, page_index=page_index, page_size=page_size)
        page_path = raw_pages_dir / f"page_{page_index:03d}.json"
        metadata_path = raw_pages_dir / f"page_{page_index:03d}_metadata.json"
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            body, http_status, content_type = _fetch_url(url, timeout=timeout)
            content_hash = hashlib.sha256(body).hexdigest()
            page_path.write_bytes(body)
            metadata = {
                "source_name": "hose",
                "dataset": "hose_listed_stock_universe",
                "page_index": page_index,
                "page_size": page_size,
                "endpoint_or_surface": _redacted_url(url),
                "http_status": http_status,
                "content_type": content_type,
                "raw_path": str(page_path),
                "content_hash": content_hash,
                "fetched_at": fetched_at,
                "status": "success",
                "error": None,
                "header_names": sorted(DEFAULT_HEADERS),
            }
            metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            pages.append({"page_index": page_index, "status": "success", "raw_path": str(page_path), "metadata_path": str(metadata_path), "content_hash": content_hash})
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            metadata = {
                "source_name": "hose",
                "dataset": "hose_listed_stock_universe",
                "page_index": page_index,
                "page_size": page_size,
                "endpoint_or_surface": _redacted_url(url),
                "raw_path": str(page_path),
                "fetched_at": fetched_at,
                "status": "error",
                "error": str(exc),
                "header_names": sorted(DEFAULT_HEADERS),
            }
            metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            pages.append({"page_index": page_index, "status": "error", "raw_path": str(page_path), "metadata_path": str(metadata_path), "error": str(exc)})
    return {"requested_page_count": total_pages, "pages": pages}


def parse_collected_pages(*, raw_pages_dir: Path, run_id: str) -> dict[str, pd.DataFrame]:
    securities_frames: list[pd.DataFrame] = []
    listing_frames: list[pd.DataFrame] = []
    universe_frames: list[pd.DataFrame] = []
    global_row_index = 0
    for metadata_path in sorted(raw_pages_dir.glob("page_*_metadata.json")):
        metadata = _read_json(metadata_path)
        if metadata.get("status") != "success":
            continue
        page_index = int(metadata["page_index"])
        raw_path = Path(metadata["raw_path"])
        result = parse_hose_listed_universe_payload(raw_path=raw_path, metadata_path=metadata_path)
        for name, frame, frames in [
            ("securities_master", result.securities_master, securities_frames),
            ("exchange_listings", result.exchange_listings, listing_frames),
            ("symbol_universe", result.symbol_universe, universe_frames),
        ]:
            enriched = frame.copy()
            enriched["all_pages_run_id"] = run_id
            enriched["page_index"] = page_index
            enriched["global_row_index"] = list(range(global_row_index, global_row_index + len(enriched)))
            frames.append(enriched)
            if name == "securities_master":
                global_row_index += len(enriched)

    combined = {
        "securities_master": pd.concat(securities_frames, ignore_index=True) if securities_frames else pd.DataFrame(),
        "exchange_listings": pd.concat(listing_frames, ignore_index=True) if listing_frames else pd.DataFrame(),
        "symbol_universe": pd.concat(universe_frames, ignore_index=True) if universe_frames else pd.DataFrame(),
    }
    _mark_cross_page_duplicate_symbols(combined)
    return combined


def build_all_pages_summary(
    *,
    page1_metadata: dict[str, Any],
    page1_metadata_path: Path,
    page_size: int,
    total_pages: int,
    total_count: int,
    manifest: dict[str, Any],
    combined: dict[str, pd.DataFrame],
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    securities = combined["securities_master"]
    fetched_pages = [page for page in manifest["pages"] if page.get("status") == "success"]
    missing_pages = [page["page_index"] for page in manifest["pages"] if page.get("status") != "success"]
    reason_counts = _reason_counts(securities)
    warn_count = int((securities["quality_status"] == "warn").sum()) if not securities.empty else 0
    fail_count = int((securities["quality_status"] == "fail").sum()) if not securities.empty else 0
    pass_count = int((securities["quality_status"] == "pass").sum()) if not securities.empty else 0
    parsed_total_rows = int(len(securities))
    row_count_matches_expected = parsed_total_rows == total_count
    run_quality_status = "pass" if row_count_matches_expected and not missing_pages else "warn"
    run_quality_reasons: list[str] = []
    if missing_pages:
        run_quality_reasons.append("warning_missing_pages")
    if not row_count_matches_expected:
        run_quality_reasons.append("warning_parsed_rows_not_equal_total_count")
    return {
        "source_name": "hose",
        "dataset": "hose_listed_stock_universe_all_pages",
        "page1_metadata_path": str(page1_metadata_path),
        "source_endpoint": _redacted_url(str(page1_metadata.get("endpoint_or_surface", ""))),
        "run_id": run_id,
        "output_dir": str(output_dir),
        "requested_page_count": total_pages,
        "fetched_page_count": len(fetched_pages),
        "expected_total_count": total_count,
        "parsed_total_rows": parsed_total_rows,
        "page_size": page_size,
        "total_pages": total_pages,
        "missing_pages": missing_pages,
        "duplicate_symbol_count": int(securities.duplicated(subset=["symbol"], keep=False).sum()) if not securities.empty else 0,
        "securities_master_count": parsed_total_rows,
        "exchange_listings_count": int(len(combined["exchange_listings"])),
        "symbol_universe_count": int(len(combined["symbol_universe"])),
        "quality_pass_count": pass_count,
        "quality_warn_count": warn_count,
        "quality_fail_count": fail_count,
        "row_count_matches_expected_total_count": row_count_matches_expected,
        "run_quality_status": run_quality_status,
        "run_quality_reasons": run_quality_reasons,
        "quality_reason_counts": reason_counts["all"],
        "quality_warning_reason_counts": reason_counts["warning"],
        "quality_failure_reason_counts": reason_counts["failure"],
        "terms_notes": page1_metadata.get("terms_notes", ""),
    }


def build_validation_report(summary: dict[str, Any], securities_path: Path, listings_path: Path, universe_path: Path, raw_pages_dir: Path) -> str:
    lines = [
        "# HOSE Listed Universe All-Pages Dry-Run Validation Report",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- source_name: `{summary['source_name']}`",
        f"- dataset: `{summary['dataset']}`",
        f"- page1_metadata_path: `{summary['page1_metadata_path']}`",
        f"- raw_pages_dir: `{raw_pages_dir}`",
        f"- securities_master: `{securities_path}`",
        f"- exchange_listings: `{listings_path}`",
        f"- symbol_universe: `{universe_path}`",
        f"- run_quality_status: `{summary['run_quality_status']}`",
        "",
        "## Pagination",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Requested pages | {summary['requested_page_count']} |",
        f"| Fetched pages | {summary['fetched_page_count']} |",
        f"| Missing pages | {len(summary['missing_pages'])} |",
        f"| Page size | {summary['page_size']} |",
        f"| Total pages | {summary['total_pages']} |",
        f"| Expected total rows | {summary['expected_total_count']} |",
        f"| Parsed total rows | {summary['parsed_total_rows']} |",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Securities master rows | {summary['securities_master_count']} |",
        f"| Exchange listing rows | {summary['exchange_listings_count']} |",
        f"| Symbol universe rows | {summary['symbol_universe_count']} |",
        f"| Quality pass rows | {summary['quality_pass_count']} |",
        f"| Quality warn rows | {summary['quality_warn_count']} |",
        f"| Quality fail rows | {summary['quality_fail_count']} |",
        f"| Duplicate symbol rows | {summary['duplicate_symbol_count']} |",
        "",
        "## Quality Reasons",
        "",
    ]
    reason_counts = summary.get("quality_reason_counts", {})
    if reason_counts:
        lines.extend(["| Reason | Count |", "|---|---:|"])
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Missing Pages",
            "",
            ", ".join(str(page) for page in summary["missing_pages"]) if summary["missing_pages"] else "none",
            "",
            "## Terms Notes",
            "",
            summary.get("terms_notes") or "none",
            "",
            "## Limitations",
            "",
            "- This is a dry run only. No database write or migration was performed.",
            "- This is listed-universe metadata only. It is not OHLCV and not quote-report data.",
            "- Quote-report samples remain out of scope because the saved bodies are request-rejection HTML.",
        ]
    )
    return "\n".join(lines) + "\n"


def _fetch_url(url: str, *, timeout: int) -> tuple[bytes, int, str]:
    request = Request(url, headers=DEFAULT_HEADERS, method="GET")
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        return body, int(response.status), response.headers.get("Content-Type", "")


def _page_url(endpoint: str, *, page_index: int, page_size: int) -> str:
    parsed = urlparse(endpoint)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["pageIndex"] = [str(page_index)]
    query["pageSize"] = [str(page_size)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _extract_page_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("HOSE listed universe payload data must be an object.")
    rows = data.get("list")
    paging = data.get("paging")
    if not isinstance(rows, list) or not isinstance(paging, dict):
        raise ValueError("HOSE listed universe payload must contain data.list and data.paging.")
    return rows, paging


def _mark_cross_page_duplicate_symbols(combined: dict[str, pd.DataFrame]) -> None:
    securities = combined["securities_master"]
    if securities.empty or "symbol" not in securities:
        return
    duplicate_mask = securities.duplicated(subset=["symbol"], keep=False) & securities["symbol"].notna()
    if not duplicate_mask.any():
        return
    duplicate_symbols = set(securities.loc[duplicate_mask, "symbol"])
    for frame in combined.values():
        if frame.empty or "symbol" not in frame:
            continue
        mask = frame["symbol"].isin(duplicate_symbols)
        frame.loc[mask, "quality_reasons"] = frame.loc[mask, "quality_reasons"].map(lambda value: _append_reason(value, "duplicate_symbol_across_pages"))
        frame.loc[mask, "quality_status"] = "fail"


def _append_reason(value: Any, reason: str) -> str:
    reasons = {item for item in str(value or "").split(";") if item}
    reasons.add(reason)
    return ";".join(sorted(reasons))


def _reason_counts(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    counts = {"all": {}, "warning": {}, "failure": {}}
    if df.empty or "quality_reasons" not in df:
        return counts
    for value in df["quality_reasons"].dropna():
        for reason in str(value).split(";"):
            if not reason:
                continue
            counts["all"][reason] = counts["all"].get(reason, 0) + 1
            bucket = "warning" if reason.startswith("warning_") else "failure"
            counts[bucket][reason] = counts[bucket].get(reason, 0) + 1
    return counts


def _redacted_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    redacted_query = {}
    for key, values in query.items():
        if any(token in key.lower() for token in ("token", "key", "secret", "password", "auth")):
            redacted_query[key] = ["<redacted>"]
        else:
            redacted_query[key] = values
    return urlunparse(parsed._replace(query=urlencode(redacted_query, doseq=True)))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
