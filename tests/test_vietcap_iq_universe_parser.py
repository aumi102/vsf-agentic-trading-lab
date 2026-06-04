from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from parse_vietcap_iq_universe_dry_run import build_hose_overlap_summary
from trading_agent.ingestion.parsers.vietcap_iq_universe_parser import parse_vietcap_iq_universe_payload


def test_parses_top_level_data_list_and_normalizes_symbol_floor(tmp_path: Path) -> None:
    raw_path, metadata_path = write_fixture(tmp_path, [vietcap_row(" fpt ", floor=" hose ")])

    result = parse_vietcap_iq_universe_payload(raw_path, metadata_path)

    assert len(result.symbol_universe) == 1
    row = result.symbol_universe.iloc[0]
    assert row["symbol"] == "FPT"
    assert row["exchange_or_floor"] == "HOSE"
    assert row["company_name"] == "FPT Corp"
    assert result.validation_summary["floor_counts"] == {"HOSE": 1}


def test_duplicate_symbol_floor_fails_affected_rows(tmp_path: Path) -> None:
    raw_path, metadata_path = write_fixture(tmp_path, [vietcap_row("FPT"), vietcap_row("FPT")])

    result = parse_vietcap_iq_universe_payload(raw_path, metadata_path)

    assert result.validation_summary["quality_fail_count"] == 2
    assert result.validation_summary["duplicate_symbol_exchange_or_floor_count"] == 2
    assert set(result.symbol_universe["quality_status"]) == {"fail"}
    assert all("duplicate_symbol_exchange_or_floor" in value for value in result.symbol_universe["quality_reasons"])


def test_index_and_special_floors_are_warnings_not_dropped(tmp_path: Path) -> None:
    rows = [
        vietcap_row("VNINDEX", floor="HOSE", is_index=True),
        vietcap_row("ABC", floor="OTC"),
        vietcap_row("DEF", floor="OTHER"),
        vietcap_row("GHI", floor="STOP"),
    ]
    raw_path, metadata_path = write_fixture(tmp_path, rows)

    result = parse_vietcap_iq_universe_payload(raw_path, metadata_path)

    assert len(result.instrument_universe) == 4
    assert result.validation_summary["quality_warn_count"] == 4
    reasons = ";".join(result.instrument_universe["quality_reasons"])
    assert "warning_non_stock_index_candidate" in reasons
    assert "warning_non_listed_or_special_floor_candidate" in reasons
    assert "warning_stop_floor_status_candidate" in reasons


def test_optional_numeric_parse_error_warns(tmp_path: Path) -> None:
    raw_path, metadata_path = write_fixture(tmp_path, [vietcap_row("FPT", currentPrice="not-a-number")])

    result = parse_vietcap_iq_universe_payload(raw_path, metadata_path)

    assert result.validation_summary["quality_warn_count"] == 1
    assert result.validation_summary["quality_fail_count"] == 0
    assert "warning_invalid_optional_numeric_current_price" in result.instrument_universe.iloc[0]["quality_reasons"]


def test_missing_required_symbol_fails(tmp_path: Path) -> None:
    raw_path, metadata_path = write_fixture(tmp_path, [vietcap_row("", floor="HOSE")])

    result = parse_vietcap_iq_universe_payload(raw_path, metadata_path)

    assert result.validation_summary["quality_fail_count"] == 1
    assert "missing_required_symbol" in result.symbol_universe.iloc[0]["quality_reasons"]


def test_deterministic_ids_are_stable(tmp_path: Path) -> None:
    raw_path, metadata_path = write_fixture(tmp_path, [vietcap_row("FPT", floor="HOSE", source_id="123")])

    first = parse_vietcap_iq_universe_payload(raw_path, metadata_path)
    second = parse_vietcap_iq_universe_payload(raw_path, metadata_path)

    assert first.securities_master.iloc[0]["security_id"] == "vietcap_iq:FPT"
    assert first.exchange_listings.iloc[0]["listing_id"] == second.exchange_listings.iloc[0]["listing_id"]
    assert first.instrument_universe.iloc[0]["instrument_id"] == second.instrument_universe.iloc[0]["instrument_id"]


def test_hose_overlap_summary_computes_counts(tmp_path: Path) -> None:
    hose_dir = tmp_path / "hose"
    hose_dir.mkdir()
    pd.DataFrame({"symbol": ["FPT", "VNM", "HPG"]}).to_csv(hose_dir / "symbol_universe.csv", index=False)

    summary = build_hose_overlap_summary(pd.Series(["FPT", "VNM", "ABC"]), hose_dir)

    assert summary["status"] == "computed"
    assert summary["vietcap_total_symbols"] == 3
    assert summary["hose_symbols"] == 3
    assert summary["overlap_count"] == 2
    assert summary["hose_symbols_missing_from_vietcap_count"] == 1
    assert summary["vietcap_symbols_not_in_hose_count"] == 1


def write_fixture(tmp_path: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    payload = {
        "serverDateTime": "2026-06-04T00:00:00Z",
        "traceId": "trace-test",
        "status": 200,
        "code": "OK",
        "msg": None,
        "exception": None,
        "successful": True,
        "data": rows,
    }
    raw_path = tmp_path / "payload.json"
    metadata_path = tmp_path / "metadata.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    metadata = {
        "source_name": "vietcap_iq",
        "dataset": "vietcap_iq_company_search_bar",
        "raw_path": str(raw_path),
        "content_hash": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "terms_notes": "test fixture",
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return raw_path, metadata_path


def vietcap_row(symbol: str, *, floor: str = "HOSE", is_index: bool = False, currentPrice: object = "10.5", source_id: str = "1") -> dict[str, object]:
    return {
        "id": source_id,
        "name": "FPT Corp",
        "floor": floor,
        "phone": "123",
        "fax": "456",
        "code": symbol,
        "shortName": "FPT",
        "logoUrl": "https://example.test/logo.webp",
        "tax": "tax",
        "organCode": "FPT",
        "icbLv1": {"code": "1000", "name": "Technology"},
        "icbLv2": {"code": "1100", "name": "Software"},
        "icbLv3": None,
        "icbLv4": None,
        "isBank": False,
        "isIndex": is_index,
        "comTypeCode": "CT",
        "inCu": None,
        "upsideToTpPercentage": "1.2",
        "projectedTsrPercentage": "3.4",
        "currentPrice": currentPrice,
        "dividendPerShareTsr": "-",
        "targetPrice": "12.3",
        "bank": False,
        "index": is_index,
    }
