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

from trading_agent.ingestion.parsers.vbma_auction_parser import (
    _clean_number_value,
    header_key,
    is_xlsx_payload,
    normalize_header,
    parse_vbma_auction_payload,
)


def test_vbma_parser_detects_xlsx_with_txt_extension(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, suffix=".txt")

    assert is_xlsx_payload(raw_path) is True

    result = parse_vbma_auction_payload(raw_path, metadata_path)

    assert len(result.bond_auction_results) == 2
    assert result.bond_auction_results.loc[0, "bond_code"] == "TD2631008"


def test_vietnamese_header_normalization() -> None:
    assert normalize_header(" Giá trị gọi thầu\n(tỷ đồng) ") == "Giá trị gọi thầu (tỷ đồng)"
    assert header_key("Kỳ hạn\n(năm)") == "ky han (nam)"


def test_dash_becomes_null_and_numeric_values_convert(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path, suffix=".csv")

    result = parse_vbma_auction_payload(raw_path, metadata_path)
    rows = result.bond_auction_results

    assert pd.isna(rows.loc[1, "winning_amount_billion_vnd"])
    assert pd.isna(rows.loc[1, "winning_yield_pct"])
    assert rows.loc[0, "offered_amount_billion_vnd"] == 6000
    assert rows.loc[0, "bid_yield_min_pct"] == 3.98
    assert rows.loc[0, "tenor_years"] == 5


def test_bid_to_cover_ratio_is_derived(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    result = parse_vbma_auction_payload(raw_path, metadata_path)

    assert result.bond_auction_results.loc[0, "bid_to_cover_ratio"] == 11000 / 6000
    assert result.bond_auction_results.loc[1, "bid_to_cover_ratio"] == 0.0


def test_validation_catches_missing_required_fields(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            {
                "Mã trái phiếu": "",
                "Tổ chức phát hành": "KBNN",
                "Kỳ hạn\n(năm)": 5,
                "Ngày TCPH": "2026-05-27",
                " Giá trị gọi thầu\n(tỷ đồng) ": 6000,
                " Giá trị đặt thầu\n(tỷ đồng) ": 11000,
                " Giá trị trúng thầu\n(tỷ đồng) ": 6000,
                "Lãi suất trúng thầu (%/y)": 4.0,
                "Lãi suất đấu thầu max": 4.3,
                "Lãi suất đấu thầu min": 3.98,
            }
        ],
    )

    result = parse_vbma_auction_payload(raw_path, metadata_path)

    assert result.bond_auction_results.loc[0, "quality_status"] == "fail"
    assert "missing_required_bond_code" in result.bond_auction_results.loc[0, "quality_reasons"]


def test_deterministic_ids_are_stable(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(tmp_path)

    first = parse_vbma_auction_payload(raw_path, metadata_path)
    second = parse_vbma_auction_payload(raw_path, metadata_path)

    assert first.bond_instruments["bond_id"].tolist() == second.bond_instruments["bond_id"].tolist()
    assert first.bond_auction_results["auction_result_id"].tolist() == second.bond_auction_results["auction_result_id"].tolist()


def test_decimal_comma_and_thousands_separator_parsing() -> None:
    assert _clean_number_value("3,60", "winning_yield_pct") == "3.60"
    assert _clean_number_value("1,500", "offered_amount_billion_vnd") == "1500"
    assert _clean_number_value("1.500,25", "offered_amount_billion_vnd") == "1500.25"
    assert _clean_number_value("1,500.25", "offered_amount_billion_vnd") == "1500.25"


def test_dayfirst_date_parsing_for_ambiguous_dates(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            {
                "MÃ£ trÃ¡i phiáº¿u": "TD2030001",
                "Tá»• chá»©c phÃ¡t hÃ nh": "KBNN",
                "Ká»³ háº¡n\n(nÄƒm)": 5,
                "NgÃ y TCPH": "03/04/2020",
                " GiÃ¡ trá»‹ gá»i tháº§u\n(tá»· Ä‘á»“ng) ": "1,500",
                " GiÃ¡ trá»‹ Ä‘áº·t tháº§u\n(tá»· Ä‘á»“ng) ": "2,000",
                " GiÃ¡ trá»‹ trÃºng tháº§u\n(tá»· Ä‘á»“ng) ": "1,000",
                "LÃ£i suáº¥t trÃºng tháº§u (%/y)": "3,60",
                "LÃ£i suáº¥t Ä‘áº¥u tháº§u max": "3,80",
                "LÃ£i suáº¥t Ä‘áº¥u tháº§u min": "3,50",
            }
        ],
    )

    result = parse_vbma_auction_payload(raw_path, metadata_path)

    row = result.bond_auction_results.iloc[0]
    assert row["auction_or_issue_date"] == "2020-04-03"
    assert row["offered_amount_billion_vnd"] == 1500
    assert row["winning_yield_pct"] == 3.6


def test_bid_yield_min_greater_than_max_is_warning_not_fail(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            {
                "MÃ£ trÃ¡i phiáº¿u": "TD2333119",
                "Tá»• chá»©c phÃ¡t hÃ nh": "KBNN",
                "Ká»³ háº¡n\n(nÄƒm)": 10,
                "NgÃ y TCPH": "2023-05-31",
                " GiÃ¡ trá»‹ gá»i tháº§u\n(tá»· Ä‘á»“ng) ": 1500,
                " GiÃ¡ trá»‹ Ä‘áº·t tháº§u\n(tá»· Ä‘á»“ng) ": 3651,
                " GiÃ¡ trá»‹ trÃºng tháº§u\n(tá»· Ä‘á»“ng) ": 300,
                "LÃ£i suáº¥t trÃºng tháº§u (%/y)": 2.95,
                "LÃ£i suáº¥t Ä‘áº¥u tháº§u max": 2.95,
                "LÃ£i suáº¥t Ä‘áº¥u tháº§u min": 3.6,
            }
        ],
    )

    result = parse_vbma_auction_payload(raw_path, metadata_path)

    assert result.bond_auction_results.loc[0, "quality_status"] == "warn"
    assert "warning_bid_yield_min_greater_than_max" in result.bond_auction_results.loc[0, "quality_reasons"]


def test_duplicate_bond_date_is_warning_unless_exact_duplicate(tmp_path: Path) -> None:
    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _fixture_row("BVBS18171", "2018-10-01", 500, 501, 500, 5.05, 6.1, 5.07),
            _fixture_row("BVBS18171", "2018-10-01", 500, 501, 500, 5.05, 6.1, 4.77),
        ],
    )
    result = parse_vbma_auction_payload(raw_path, metadata_path)

    assert set(result.bond_auction_results["quality_status"]) == {"warn"}
    assert all("warning_duplicate_bond_code_auction_or_issue_date" in value for value in result.bond_auction_results["quality_reasons"])

    raw_path, metadata_path = _write_fixture(
        tmp_path,
        rows=[
            _fixture_row("BVBS18171", "2018-10-01", 500, 501, 500, 5.05, 6.1, 5.07),
            _fixture_row("BVBS18171", "2018-10-01", 500, 501, 500, 5.05, 6.1, 5.07),
        ],
    )
    result = parse_vbma_auction_payload(raw_path, metadata_path)

    assert set(result.bond_auction_results["quality_status"]) == {"fail"}
    assert all("exact_duplicate_bond_auction_result_identity" in value for value in result.bond_auction_results["quality_reasons"])


def _fixture_row(
    bond_code: str,
    date: str,
    offered: object,
    bid: object,
    winning: object,
    winning_yield: object,
    max_yield: object,
    min_yield: object,
) -> dict[str, object]:
    return {
        "MÃ£ trÃ¡i phiáº¿u": bond_code,
        "Tá»• chá»©c phÃ¡t hÃ nh": "KBNN",
        "Ká»³ háº¡n\n(nÄƒm)": 5,
        "NgÃ y TCPH": date,
        " GiÃ¡ trá»‹ gá»i tháº§u\n(tá»· Ä‘á»“ng) ": offered,
        " GiÃ¡ trá»‹ Ä‘áº·t tháº§u\n(tá»· Ä‘á»“ng) ": bid,
        " GiÃ¡ trá»‹ trÃºng tháº§u\n(tá»· Ä‘á»“ng) ": winning,
        "LÃ£i suáº¥t trÃºng tháº§u (%/y)": winning_yield,
        "LÃ£i suáº¥t Ä‘áº¥u tháº§u max": max_yield,
        "LÃ£i suáº¥t Ä‘áº¥u tháº§u min": min_yield,
    }


def _write_fixture(tmp_path: Path, suffix: str = ".xlsx", rows: list[dict[str, object]] | None = None) -> tuple[Path, Path]:
    rows = rows or [
        {
            "Mã trái phiếu": " TD2631008 ",
            "Tổ chức phát hành": " KBNN ",
            "Kỳ hạn\n(năm)": 5,
            "Ngày TCPH": "2026-05-27",
            " Giá trị gọi thầu\n(tỷ đồng) ": 6000,
            " Giá trị đặt thầu\n(tỷ đồng) ": 11000,
            " Giá trị trúng thầu\n(tỷ đồng) ": 6000,
            "Lãi suất trúng thầu (%/y)": "4",
            "Lãi suất đấu thầu max": "4.3",
            "Lãi suất đấu thầu min": "3.98",
        },
        {
            "Mã trái phiếu": "TD2646057",
            "Tổ chức phát hành": "KBNN",
            "Kỳ hạn\n(năm)": 20,
            "Ngày TCPH": "2026-05-20",
            " Giá trị gọi thầu\n(tỷ đồng) ": 500,
            " Giá trị đặt thầu\n(tỷ đồng) ": 0,
            " Giá trị trúng thầu\n(tỷ đồng) ": "-",
            "Lãi suất trúng thầu (%/y)": "-",
            "Lãi suất đấu thầu max": "-",
            "Lãi suất đấu thầu min": "-",
        },
    ]
    raw_path = tmp_path / f"vbma_payload{suffix}"
    pd.DataFrame(rows).to_excel(raw_path, index=False, sheet_name="Kết quả đấu thầu theo đợt Eng")
    content_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source_name": "vbma",
                "dataset": "vbma_primary_market_auction_results",
                "raw_path": str(raw_path),
                "content_hash": content_hash,
                "terms_notes": "synthetic test fixture",
            }
        ),
        encoding="utf-8",
    )
    return raw_path, metadata_path
