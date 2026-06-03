from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import parse_hose_listed_universe_all_pages_dry_run as all_pages


def test_fetches_all_pages_from_total_pages_metadata(tmp_path: Path, monkeypatch) -> None:
    calls: list[int] = []

    def fake_fetch(url: str, *, timeout: int) -> tuple[bytes, int, str]:
        page = int(parse_qs(urlparse(url).query)["pageIndex"][0])
        calls.append(page)
        return _payload_bytes(page, total_count=4, total_pages=2), 200, "application/json"

    monkeypatch.setattr(all_pages, "_fetch_url", fake_fetch)

    manifest = all_pages.fetch_all_pages(
        endpoint="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2&alphabet=&sectorId=&api_key=SECRET",
        page_size=2,
        total_pages=2,
        raw_pages_dir=tmp_path,
    )

    assert calls == [1, 2]
    assert len([page for page in manifest["pages"] if page["status"] == "success"]) == 2
    assert (tmp_path / "page_001.json").exists()
    assert (tmp_path / "page_002.json").exists()


def test_combines_rows_across_pages(tmp_path: Path, monkeypatch) -> None:
    _write_fetched_pages(tmp_path, monkeypatch, total_pages=2)
    combined = all_pages.parse_collected_pages(raw_pages_dir=tmp_path, run_id="test_run")

    assert len(combined["securities_master"]) == 4
    assert len(combined["exchange_listings"]) == 4
    assert len(combined["symbol_universe"]) == 4
    assert combined["securities_master"]["page_index"].tolist() == [1, 1, 2, 2]
    assert combined["securities_master"]["global_row_index"].tolist() == [0, 1, 2, 3]
    assert set(combined["securities_master"]["all_pages_run_id"]) == {"test_run"}


def test_detects_missing_pages(tmp_path: Path, monkeypatch) -> None:
    def fake_fetch(url: str, *, timeout: int) -> tuple[bytes, int, str]:
        page = int(parse_qs(urlparse(url).query)["pageIndex"][0])
        if page == 2:
            raise TimeoutError("synthetic timeout")
        return _payload_bytes(page, total_count=6, total_pages=3), 200, "application/json"

    monkeypatch.setattr(all_pages, "_fetch_url", fake_fetch)
    manifest = all_pages.fetch_all_pages(
        endpoint="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2",
        page_size=2,
        total_pages=3,
        raw_pages_dir=tmp_path,
    )
    combined = all_pages.parse_collected_pages(raw_pages_dir=tmp_path, run_id="test_run")
    summary = _summary(tmp_path, manifest, combined, total_count=6, total_pages=3)

    assert summary["missing_pages"] == [2]
    assert summary["fetched_page_count"] == 2
    assert summary["run_quality_status"] == "warn"
    assert "warning_missing_pages" in summary["run_quality_reasons"]


def test_detects_duplicate_symbols_across_pages(tmp_path: Path, monkeypatch) -> None:
    def fake_fetch(url: str, *, timeout: int) -> tuple[bytes, int, str]:
        page = int(parse_qs(urlparse(url).query)["pageIndex"][0])
        rows = [_row("AAA"), _row("BBB")] if page == 1 else [_row("AAA"), _row("CCC")]
        return _payload_bytes(page, total_count=4, total_pages=2, rows=rows), 200, "application/json"

    monkeypatch.setattr(all_pages, "_fetch_url", fake_fetch)
    manifest = all_pages.fetch_all_pages(
        endpoint="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2",
        page_size=2,
        total_pages=2,
        raw_pages_dir=tmp_path,
    )
    combined = all_pages.parse_collected_pages(raw_pages_dir=tmp_path, run_id="test_run")
    summary = _summary(tmp_path, manifest, combined, total_count=4, total_pages=2)

    duplicated = combined["securities_master"][combined["securities_master"]["symbol"] == "AAA"]
    assert set(duplicated["quality_status"]) == {"fail"}
    assert all("duplicate_symbol_across_pages" in value for value in duplicated["quality_reasons"])
    assert summary["duplicate_symbol_count"] == 2
    assert summary["quality_fail_count"] == 2


def test_summary_row_count_matches_expected_total_count(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_fetched_pages(tmp_path, monkeypatch, total_pages=2)
    combined = all_pages.parse_collected_pages(raw_pages_dir=tmp_path, run_id="test_run")
    summary = _summary(tmp_path, manifest, combined, total_count=4, total_pages=2)

    assert summary["parsed_total_rows"] == 4
    assert summary["expected_total_count"] == 4
    assert summary["row_count_matches_expected_total_count"] is True
    assert summary["run_quality_status"] == "pass"


def test_does_not_leak_secrets_in_report_or_summary(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_fetched_pages(tmp_path, monkeypatch, total_pages=1, endpoint="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2&api_key=SECRET")
    combined = all_pages.parse_collected_pages(raw_pages_dir=tmp_path, run_id="test_run")
    summary = _summary(tmp_path, manifest, combined, total_count=2, total_pages=1, endpoint="https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2&api_key=SECRET")
    report = all_pages.build_validation_report(
        summary,
        tmp_path / "securities_master.csv",
        tmp_path / "exchange_listings.csv",
        tmp_path / "symbol_universe.csv",
        tmp_path,
    )
    metadata_text = (tmp_path / "page_001_metadata.json").read_text(encoding="utf-8")

    assert "SECRET" not in json.dumps(summary)
    assert "SECRET" not in report
    assert "SECRET" not in metadata_text
    assert "%3Credacted%3E" in metadata_text or "<redacted>" in metadata_text


def _write_fetched_pages(
    tmp_path: Path,
    monkeypatch,
    *,
    total_pages: int,
    endpoint: str = "https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2",
):
    def fake_fetch(url: str, *, timeout: int) -> tuple[bytes, int, str]:
        page = int(parse_qs(urlparse(url).query)["pageIndex"][0])
        return _payload_bytes(page, total_count=total_pages * 2, total_pages=total_pages), 200, "application/json"

    monkeypatch.setattr(all_pages, "_fetch_url", fake_fetch)
    return all_pages.fetch_all_pages(endpoint=endpoint, page_size=2, total_pages=total_pages, raw_pages_dir=tmp_path)


def _summary(
    tmp_path: Path,
    manifest: dict,
    combined: dict,
    *,
    total_count: int,
    total_pages: int,
    endpoint: str = "https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=2",
) -> dict:
    return all_pages.build_all_pages_summary(
        page1_metadata={"endpoint_or_surface": endpoint, "terms_notes": "synthetic"},
        page1_metadata_path=tmp_path / "page_001_metadata.json",
        page_size=2,
        total_pages=total_pages,
        total_count=total_count,
        manifest=manifest,
        combined=combined,
        run_id="test_run",
        output_dir=tmp_path,
    )


def _payload_bytes(page: int, *, total_count: int, total_pages: int, rows: list[dict] | None = None) -> bytes:
    rows = rows or [_row(f"P{page}A"), _row(f"P{page}B")]
    payload = {
        "data": {
            "list": rows,
            "object": None,
            "paging": {
                "pageIndex": page,
                "pageSize": 2,
                "totalCount": total_count,
                "totalPages": total_pages,
            },
        },
        "success": True,
        "message": None,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _row(code: str) -> dict[str, object]:
    return {
        "id": abs(hash(code)) % 10000,
        "name": f"{code} Company",
        "code": code,
        "brief": code,
        "capital": 1000000,
        "securitiesType": 1,
        "displayText": f"{code} | {code} Company",
        "isin": "VN000000AAA4",
        "bloomberg": "BBG000BB42R4",
        "parValue": 10000,
        "regDate": 1475712000,
        "ftdate": 1480032000,
        "acceptDate": 1475712000,
        "listDate": 1466640000,
        "listingStatusId": 11,
        "listingVolume": "1,000",
        "listingValue": "10,000,000",
        "outStanding": "900",
        "adjOutStanding": "0",
        "foreignOwnedRatio": "0.00",
        "stateOwnedRatio": "0.00",
        "treasuryVol": "0",
    }
