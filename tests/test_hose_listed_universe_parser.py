from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.ingestion.parsers.hose_listed_universe_parser import parse_hose_listed_universe_payload


def test_hose_parser_parses_json_shape_with_list_and_paging(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)

    assert len(result.securities_master) == 2
    assert len(result.exchange_listings) == 2
    assert len(result.symbol_universe) == 2
    assert result.validation_summary["page_index"] == 1
    assert result.validation_summary["total_count"] == 403


def test_symbol_normalization_and_security_id(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _fixture_row(code=" fpt ", name="FPT Corp", isin="VN000000FPT1"),
        ],
    )

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)

    row = result.securities_master.iloc[0]
    assert row["symbol"] == "FPT"
    assert row["exchange"] == "HOSE"
    assert row["security_id"] == "hose:FPT"


def test_numeric_string_with_commas_parses(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _fixture_row(
                code="FPT",
                listingVolume="1,234,567",
                listingValue="12,345,670,000",
                outStanding="1,000,000",
                adjOutStanding="999,999",
                treasuryVol="123",
            )
        ],
    )

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)

    securities = result.securities_master.iloc[0]
    listing = result.exchange_listings.iloc[0]
    assert listing["listed_volume"] == 1234567
    assert listing["listed_value_vnd"] == 12345670000
    assert securities["outstanding_volume"] == 1000000
    assert securities["adjusted_outstanding_volume"] == 999999
    assert securities["treasury_volume"] == 123


def test_positive_epoch_date_parses(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _fixture_row(code="FPT", regDate=1466553600, ftdate=1467158400, acceptDate=1466553600, listDate=1460332800),
        ],
    )

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)
    listing = result.exchange_listings.iloc[0]

    assert listing["registration_date"] == "2016-06-22"
    assert listing["first_trading_date"] == "2016-06-29"
    assert listing["acceptance_date"] == "2016-06-22"
    assert listing["listing_date"] == "2016-04-11"


def test_sentinel_negative_date_becomes_null_with_warning(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_fixture_row(code="FPT", listDate=-62135596800)],
    )

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)
    listing = result.exchange_listings.iloc[0]

    assert pd.isna(listing["listing_date"])
    assert listing["quality_status"] == "warn"
    assert "warning_sentinel_date_listDate" in listing["quality_reasons"]


def test_duplicate_symbol_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _fixture_row(code="FPT", name="FPT Corp", isin="VN000000FPT1"),
            _fixture_row(code=" fpt ", name="FPT Duplicate", isin="VN000000FPT1"),
        ],
    )

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)

    assert set(result.securities_master["quality_status"]) == {"fail"}
    assert all("duplicate_symbol_in_page_sample" in value for value in result.securities_master["quality_reasons"])


def test_invalid_isin_warns(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[_fixture_row(code="FPT", isin="BAD-ISIN")],
    )

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)

    assert result.securities_master.loc[0, "quality_status"] == "warn"
    assert "warning_invalid_isin" in result.securities_master.loc[0, "quality_reasons"]


def test_deterministic_ids_are_stable(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    first = parse_hose_listed_universe_payload(raw_path, metadata_path)
    second = parse_hose_listed_universe_payload(raw_path, metadata_path)

    assert first.securities_master["security_id"].tolist() == second.securities_master["security_id"].tolist()
    assert first.exchange_listings["listing_id"].tolist() == second.exchange_listings["listing_id"].tolist()
    assert first.symbol_universe["universe_row_id"].tolist() == second.symbol_universe["universe_row_id"].tolist()


def test_pagination_metadata_appears_in_summary(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, paging={"pageIndex": 1, "pageSize": 30, "totalCount": 403, "totalPages": 14})

    result = parse_hose_listed_universe_payload(raw_path, metadata_path)

    assert result.validation_summary["page_index"] == 1
    assert result.validation_summary["page_size"] == 30
    assert result.validation_summary["total_count"] == 403
    assert result.validation_summary["total_pages"] == 14
    assert result.validation_summary["page_row_count"] == 2


def _write_fixture(
    tmp_path: Path,
    rows: list[dict[str, object]] | None = None,
    paging: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    rows = rows or [
        _fixture_row(code="AAA", name="An Phat Bioplastics", isin="VN000000AAA4", bloomberg="BBG000BB42R4"),
        _fixture_row(code="AAM", name="Mekong Fish", isin="VN000000AAM9", bloomberg="BBG000PDD0V4"),
    ]
    payload = {
        "data": {
            "list": rows,
            "object": None,
            "paging": paging or {"pageIndex": 1, "pageSize": 30, "totalCount": 403, "totalPages": 14},
        },
        "success": True,
        "message": None,
    }
    raw_path = tmp_path / "payload.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    content_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "hose",
                "dataset": "hose_listed_stock_universe",
                "raw_path": str(raw_path),
                "content_hash": content_hash,
                "access_status": "verified",
                "status": "success",
                "terms_notes": "synthetic test fixture",
            }
        ),
        encoding="utf-8",
    )
    return raw_path, metadata_path


def _fixture_row(
    *,
    code: str,
    name: str = "Company",
    isin: str = "VN000000AAA4",
    bloomberg: str = "BBG000BB42R4",
    listingVolume: object = "393,742,730",
    listingValue: object = "3,937,427,300,000",
    outStanding: object = "393,742,730",
    adjOutStanding: object = "0",
    treasuryVol: object = "0",
    regDate: object = 1475712000,
    ftdate: object = 1480032000,
    acceptDate: object = 1475712000,
    listDate: object = 1466640000,
) -> dict[str, object]:
    return {
        "id": 2896,
        "name": name,
        "code": code,
        "brief": "Short Name",
        "address": "Address",
        "phone": None,
        "fax": None,
        "webUrl": "https://example.com",
        "director": None,
        "spokesman": None,
        "capital": 3937427300000,
        "securitiesType": 1,
        "displayText": f"{code.strip().upper()} | {name}",
        "reason": None,
        "isin": isin,
        "bloomberg": bloomberg,
        "parValue": 10000,
        "regDate": regDate,
        "ftdate": ftdate,
        "affectDate": -62135596800,
        "acceptDate": acceptDate,
        "listDate": listDate,
        "listingStatusId": 11,
        "listingVolume": listingVolume,
        "listingValue": listingValue,
        "outStanding": outStanding,
        "adjOutStanding": adjOutStanding,
        "turnoverRatio": "0.00",
        "foreignOwnedRatio": "100.00",
        "stateOwnedRatio": "0.00",
        "avgOutStanding": "0",
        "changeOutStanding": "0",
        "treasuryVol": treasuryVol,
    }
