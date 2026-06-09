from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.parse_vietcap_iq_fa_payloads_dry_run import (
    AVAILABILITY_STATUS,
    METADATA_FIELDS,
    PUBLIC_DATE_SEMANTICS,
    WARNING_CODE_TICKER_DIFFER,
    WARNING_NO_NAME,
    WARNING_PIT,
    _LONG_FORMAT_COLUMNS,
    _check_duplicate_keys,
    _check_mapping_coverage,
    _check_no_invented_names,
    _check_nos_pattern,
    _check_publicdate_format,
    _check_value_status_validity,
    _get_metric_columns,
    _section_from_metadata_or_url,
    _sort_facts,
    _value_status,
    discover_payloads,
    generate_report,
    melt_period_rows,
    parse_payload,
    validate_parse_result,
    write_outputs,
)


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------


def _make_row(
    ticker: str = "TST",
    organ_code: str = "TST",
    year: int = 2024,
    length: int = 1,
    public_date: str = "2024-04-25T00:00:00",
    **metrics: object,
) -> dict:
    return {
        "ticker": ticker,
        "organCode": organ_code,
        "yearReport": year,
        "lengthReport": length,
        "publicDate": public_date,
        "updateDate": "2024-05-01T00:00:00",
        "createDate": None,
        **metrics,
    }


def _make_payload(
    quarters: list[dict] | None = None,
    years: list[dict] | None = None,
    server_dt: str = "2026-06-09T00:00:00",
) -> dict:
    return {
        "status": 200,
        "code": 0,
        "successful": True,
        "msg": "Successful",
        "exception": None,
        "serverDateTime": server_dt,
        "traceId": "test-trace",
        "data": {
            "quarters": quarters or [],
            "years": years or [],
        },
    }


def _write_payload(tmp_path: Path, payload: dict) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "payload.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _make_meta(
    tmp_path: Path,
    payload: dict,
    run_id: str = "testrun",
    symbol: str = "TST",
    section: str = "BALANCE_SHEET",
    target_url: str = "",
) -> dict:
    payload_path = _write_payload(tmp_path, payload)
    return {
        "run_id": run_id,
        "source_name": "vietcap_iq",
        "symbol": symbol,
        "section": section,
        "diagnostic_target": "fa-direct",
        "target_url": target_url or f"https://iq.vietcap.com.vn/.../financial-statement?section={section}",
        "dataset": "test_dataset",
        "http_status": 200,
        "access_status": "verified",
        "raw_path": str(payload_path),
        "content_hash": "abc123",
        "crawled_at": "2026-06-09T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# _value_status
# ---------------------------------------------------------------------------


def test_value_status_none_is_missing() -> None:
    assert _value_status(None) == "missing"


def test_value_status_zero_float_is_zero() -> None:
    assert _value_status(0.0) == "zero"


def test_value_status_zero_int_is_zero() -> None:
    assert _value_status(0) == "zero"


def test_value_status_nonzero_is_present() -> None:
    assert _value_status(1000000.0) == "present"
    assert _value_status(-500.0) == "present"


# ---------------------------------------------------------------------------
# _get_metric_columns
# ---------------------------------------------------------------------------


def test_metric_columns_excludes_all_metadata_fields() -> None:
    row = _make_row(bsa1=100.0, bss1=0.0, nos1=None)
    cols = _get_metric_columns(row)
    for field in METADATA_FIELDS:
        assert field not in cols
    assert "bsa1" in cols
    assert "bss1" in cols
    assert "nos1" in cols


# ---------------------------------------------------------------------------
# _section_from_metadata_or_url
# ---------------------------------------------------------------------------


def test_section_from_metadata_field() -> None:
    meta = {"section": "INCOME_STATEMENT", "target_url": "https://example.com?section=OTHER"}
    assert _section_from_metadata_or_url(meta) == "INCOME_STATEMENT"


def test_section_from_url_when_metadata_section_empty() -> None:
    meta = {"section": "", "target_url": "https://iq.vietcap.com.vn/.../financial-statement?section=BALANCE_SHEET"}
    assert _section_from_metadata_or_url(meta) == "BALANCE_SHEET"


def test_section_empty_string_when_neither_present() -> None:
    meta = {"section": "", "target_url": "https://example.com/no-section"}
    assert _section_from_metadata_or_url(meta) == ""


# ---------------------------------------------------------------------------
# melt_period_rows — quarters
# ---------------------------------------------------------------------------


def test_melt_quarters_produces_one_fact_per_metric_column() -> None:
    rows = [_make_row(length=1, bsa1=100.0, bsa2=0.0, nos1=None)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, errors = melt_period_rows(rows, "quarter", meta, "2026-06-09")

    assert errors == []
    assert len(facts) == 3  # bsa1, bsa2, nos1


def test_melt_quarters_period_type_is_quarter() -> None:
    rows = [_make_row(length=2, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert all(f["period_type"] == "quarter" for f in facts)


def test_lengthreport_1_to_4_maps_to_fiscal_quarter() -> None:
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    for q in (1, 2, 3, 4):
        rows = [_make_row(length=q, bsa1=1.0)]
        facts, errors = melt_period_rows(rows, "quarter", meta, "")
        assert errors == []
        assert facts[0]["fiscal_quarter"] == q
        assert facts[0]["source_period_label"] == f"2024Q{q}"


def test_melt_quarters_source_period_label_format() -> None:
    rows = [_make_row(year=2025, length=4, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert facts[0]["source_period_label"] == "2025Q4"


# ---------------------------------------------------------------------------
# melt_period_rows — years
# ---------------------------------------------------------------------------


def test_melt_years_period_type_is_year() -> None:
    rows = [_make_row(length=5, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, errors = melt_period_rows(rows, "year", meta, "")
    assert errors == []
    assert all(f["period_type"] == "year" for f in facts)


def test_lengthreport_5_gives_empty_fiscal_quarter() -> None:
    rows = [_make_row(length=5, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "year", meta, "")
    assert facts[0]["fiscal_quarter"] == ""
    assert facts[0]["source_period_label"] == "2024Y"


def test_melt_years_source_period_label_format() -> None:
    rows = [_make_row(year=2023, length=5, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "year", meta, "")
    assert facts[0]["source_period_label"] == "2023Y"


# ---------------------------------------------------------------------------
# value_status in facts
# ---------------------------------------------------------------------------


def test_null_value_gives_missing_status_in_facts() -> None:
    rows = [_make_row(length=1, nos1=None)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    nos_facts = [f for f in facts if f["line_item_code"] == "nos1"]
    assert nos_facts[0]["value_status"] == "missing"
    assert nos_facts[0]["value"] == ""


def test_zero_value_gives_zero_status_in_facts() -> None:
    rows = [_make_row(length=1, bsa2=0.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert facts[0]["value_status"] == "zero"
    assert facts[0]["value"] == 0.0


def test_nonzero_value_gives_present_status_in_facts() -> None:
    rows = [_make_row(length=1, bsa1=1234567.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert facts[0]["value_status"] == "present"
    assert facts[0]["value"] == 1234567.0


# ---------------------------------------------------------------------------
# Metadata fields not melted as metrics
# ---------------------------------------------------------------------------


def test_metadata_fields_not_in_line_item_codes() -> None:
    rows = [_make_row(length=1, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    item_codes = {f["line_item_code"] for f in facts}
    for field in METADATA_FIELDS:
        assert field not in item_codes, f"metadata field {field!r} was melted as a metric"


# ---------------------------------------------------------------------------
# publicDate and availability_status
# ---------------------------------------------------------------------------


def test_publicdate_copied_to_public_date_field() -> None:
    rows = [_make_row(length=1, public_date="2024-04-25T00:00:00", bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert facts[0]["public_date"] == "2024-04-25T00:00:00"


def test_availability_status_is_unknown() -> None:
    rows = [_make_row(length=1, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert facts[0]["availability_status"] == AVAILABILITY_STATUS


def test_public_date_semantics_is_unconfirmed_constant() -> None:
    rows = [_make_row(length=1, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert facts[0]["public_date_semantics"] == PUBLIC_DATE_SEMANTICS


# ---------------------------------------------------------------------------
# parser_warning contents
# ---------------------------------------------------------------------------


def test_warning_no_name_always_present() -> None:
    rows = [_make_row(length=1, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert WARNING_NO_NAME in facts[0]["parser_warning"]


def test_warning_pit_present_when_public_date_set() -> None:
    rows = [_make_row(length=1, public_date="2024-04-25T00:00:00", bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert WARNING_PIT in facts[0]["parser_warning"]


def test_warning_pit_absent_when_no_public_date() -> None:
    rows = [_make_row(length=1, public_date="", bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert WARNING_PIT not in facts[0]["parser_warning"]


def test_warning_code_ticker_differ_when_organcode_ne_ticker() -> None:
    rows = [_make_row(ticker="VCI", organ_code="VCSC", length=1, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "VCI", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert WARNING_CODE_TICKER_DIFFER in facts[0]["parser_warning"]


def test_no_code_ticker_warning_when_organcode_eq_ticker() -> None:
    rows = [_make_row(ticker="FPT", organ_code="FPT", length=1, bsa1=1.0)]
    meta = {"run_id": "r1", "symbol": "FPT", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert WARNING_CODE_TICKER_DIFFER not in facts[0]["parser_warning"]


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------


def test_missing_year_report_produces_error_and_skips_row() -> None:
    row = _make_row(length=1, bsa1=1.0)
    row.pop("yearReport")
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, errors = melt_period_rows([row], "quarter", meta, "")
    assert facts == []
    assert len(errors) == 1
    assert errors[0]["error"] == "missing_yearReport"


def test_unexpected_length_report_for_quarter_produces_error() -> None:
    rows = [_make_row(length=5, bsa1=1.0)]  # 5 is annual, not valid for quarter
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, errors = melt_period_rows(rows, "quarter", meta, "")
    assert facts == []
    assert len(errors) == 1
    assert "unexpected_lengthReport_for_quarter" in errors[0]["error"]


def test_unexpected_length_report_for_year_produces_error() -> None:
    rows = [_make_row(length=2, bsa1=1.0)]  # 2 = Q2, not valid for year
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, errors = melt_period_rows(rows, "year", meta, "")
    assert facts == []
    assert len(errors) == 1
    assert "unexpected_lengthReport_for_year" in errors[0]["error"]


# ---------------------------------------------------------------------------
# parse_payload
# ---------------------------------------------------------------------------


def test_parse_payload_produces_stats(tmp_path: Path) -> None:
    quarters = [
        _make_row(length=1, bsa1=1.0, bsa2=0.0),
        _make_row(length=2, bsa1=2.0, bsa2=0.0),
    ]
    years = [_make_row(year=2023, length=5, bsa1=900.0, bsa2=0.0)]
    payload = _make_payload(quarters=quarters, years=years)
    meta = _make_meta(tmp_path, payload, symbol="TST", section="BALANCE_SHEET")

    facts, errors, stats = parse_payload(meta)

    assert stats["quarter_rows_read"] == 2
    assert stats["year_rows_read"] == 1
    assert stats["metric_column_count"] == 2
    assert stats["output_fact_rows"] == (2 + 1) * 2  # 3 period rows × 2 metric cols
    assert stats["section"] == "BALANCE_SHEET"
    assert stats["symbol"] == "TST"
    assert errors == []


def test_parse_payload_quarters_and_years_both_included(tmp_path: Path) -> None:
    quarters = [_make_row(length=1, bsa1=1.0)]
    years = [_make_row(year=2023, length=5, bsa1=900.0)]
    payload = _make_payload(quarters=quarters, years=years)
    meta = _make_meta(tmp_path, payload)

    facts, _, _ = parse_payload(meta)

    period_types = {f["period_type"] for f in facts}
    assert period_types == {"quarter", "year"}


def test_parse_payload_fail_on_missing_public_date_raises(tmp_path: Path) -> None:
    row = _make_row(length=1, public_date="", bsa1=1.0)
    payload = _make_payload(quarters=[row])
    meta = _make_meta(tmp_path, payload)

    with pytest.raises(ValueError, match="missing publicDate"):
        parse_payload(meta, fail_on_missing_public_date=True)


def test_parse_payload_no_fail_on_missing_public_date_by_default(tmp_path: Path) -> None:
    row = _make_row(length=1, public_date="", bsa1=1.0)
    payload = _make_payload(quarters=[row])
    meta = _make_meta(tmp_path, payload)

    facts, errors, _ = parse_payload(meta)  # should not raise
    assert len(facts) == 1


# ---------------------------------------------------------------------------
# discover_payloads
# ---------------------------------------------------------------------------


def _write_discover_fixture(
    root: Path,
    run_id: str,
    dataset: str,
    diagnostic_target: str = "fa-direct",
    access_status: str = "verified",
    with_payload: bool = True,
) -> None:
    d = root / f"run_id={run_id}" / dataset
    d.mkdir(parents=True, exist_ok=True)
    payload_path = d / "payload.json"
    if with_payload:
        payload_path.write_text(json.dumps({"data": {"quarters": [], "years": []}}), encoding="utf-8")
    meta = {
        "run_id": run_id,
        "diagnostic_target": diagnostic_target,
        "access_status": access_status,
        "raw_path": str(payload_path) if with_payload else "",
        "section": "BALANCE_SHEET",
        "symbol": "TST",
    }
    (d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")


def test_discover_returns_only_fa_direct_verified(tmp_path: Path) -> None:
    _write_discover_fixture(tmp_path, "r1", "ds1", diagnostic_target="fa-direct", access_status="verified")
    _write_discover_fixture(tmp_path, "r2", "ds2", diagnostic_target="search-bar", access_status="verified")
    _write_discover_fixture(tmp_path, "r3", "ds3", diagnostic_target="fa-direct", access_status="auth_required")

    found = discover_payloads(tmp_path, [], [])
    assert len(found) == 1
    assert found[0]["run_id"] == "r1"


def test_discover_filters_by_run_id(tmp_path: Path) -> None:
    _write_discover_fixture(tmp_path, "r1", "ds1")
    _write_discover_fixture(tmp_path, "r2", "ds1")

    found = discover_payloads(tmp_path, ["r1"], [])
    assert len(found) == 1
    assert found[0]["run_id"] == "r1"


def test_discover_skips_missing_payload_file(tmp_path: Path) -> None:
    _write_discover_fixture(tmp_path, "r1", "ds1", with_payload=False)
    found = discover_payloads(tmp_path, [], [])
    assert found == []


def test_discover_returns_empty_for_nonexistent_root(tmp_path: Path) -> None:
    found = discover_payloads(tmp_path / "nonexistent", [], [])
    assert found == []


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


def test_generate_report_contains_pit_warning() -> None:
    stats = [{"run_id": "r1", "symbol": "TST", "section": "BS", "dataset": "ds",
               "quarter_rows_read": 2, "year_rows_read": 1, "metric_column_count": 3,
               "output_fact_rows": 9, "q_publicdate_nonnull": 2, "y_publicdate_nonnull": 1}]
    report = generate_report(stats, [], [])
    assert "publicDate" in report
    assert "backtest" in report.lower()
    assert "PIT" in report or "point-in-time" in report.lower()


def test_generate_report_contains_no_db_write_statement() -> None:
    report = generate_report([], [], [])
    assert "DB write" in report or "No DB" in report


def test_generate_report_fact_counts() -> None:
    facts = [
        {"value_status": "present"},
        {"value_status": "zero"},
        {"value_status": "zero"},
        {"value_status": "missing"},
    ]
    stats = [{"run_id": "r1", "symbol": "T", "section": "S", "dataset": "d",
               "quarter_rows_read": 2, "year_rows_read": 0, "metric_column_count": 2,
               "output_fact_rows": 4, "q_publicdate_nonnull": 2, "y_publicdate_nonnull": 0}]
    report = generate_report(stats, facts, [])
    assert "1" in report   # 1 present
    assert "2" in report   # 2 zero
    assert "missing" in report


# ---------------------------------------------------------------------------
# write_outputs
# ---------------------------------------------------------------------------


def test_write_outputs_creates_csv_and_report(tmp_path: Path) -> None:
    facts = [
        {col: "" for col in _LONG_FORMAT_COLUMNS}
        | {"line_item_code": "bsa1", "value_status": "present", "value": 1.0}
    ]
    paths = write_outputs(facts, [], "# Report", tmp_path / "out", "csv")

    assert Path(paths["facts"]).exists()
    assert Path(paths["facts"]).suffix == ".csv"
    assert Path(paths["report"]).exists()
    assert "errors" not in paths


def test_write_outputs_creates_errors_csv_when_errors_present(tmp_path: Path) -> None:
    errors = [{"run_id": "r1", "symbol": "T", "section": "S", "period_type": "quarter",
                "row_index": 0, "error": "missing_yearReport"}]
    paths = write_outputs([], errors, "# Report", tmp_path / "out", "csv")
    assert "errors" in paths
    assert Path(paths["errors"]).exists()


def test_write_outputs_jsonl_format(tmp_path: Path) -> None:
    facts = [
        {col: "" for col in _LONG_FORMAT_COLUMNS}
        | {"line_item_code": "bsa1", "value": None, "value_status": "missing"}
    ]
    paths = write_outputs(facts, [], "# Report", tmp_path / "out", "jsonl")
    assert Path(paths["facts"]).suffix == ".jsonl"
    line = Path(paths["facts"]).read_text(encoding="utf-8").splitlines()[0]
    row = json.loads(line)
    assert row["value"] is None


def test_write_outputs_csv_has_all_long_format_columns(tmp_path: Path) -> None:
    facts = [{col: "" for col in _LONG_FORMAT_COLUMNS}]
    paths = write_outputs(facts, [], "# Report", tmp_path / "out", "csv")
    with Path(paths["facts"]).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
    assert list(headers) == _LONG_FORMAT_COLUMNS


# ---------------------------------------------------------------------------
# No DB write / no live network
# ---------------------------------------------------------------------------


def test_no_db_file_created_by_parser(tmp_path: Path) -> None:
    quarters = [_make_row(length=1, bsa1=1.0)]
    payload = _make_payload(quarters=quarters)
    meta = _make_meta(tmp_path / "input", payload)
    output_root = tmp_path / "output"

    parse_payload(meta)
    write_outputs([], [], "# Report", output_root, "csv")

    # Only .csv and .md files should exist in output — no database files.
    if output_root.exists():
        suffixes = {p.suffix for p in output_root.iterdir()}
        db_suffixes = {".db", ".sqlite", ".sqlite3", ".duckdb", ".parquet"}
        assert suffixes.isdisjoint(db_suffixes)


def test_no_httpx_import_in_parser_module() -> None:
    import importlib
    import scripts.parse_vietcap_iq_fa_payloads_dry_run as parser_mod
    # The parser must not depend on httpx — it reads local files only.
    assert not hasattr(parser_mod, "httpx"), "parser module must not import httpx"


# ---------------------------------------------------------------------------
# _sort_facts
# ---------------------------------------------------------------------------


def test_sort_facts_is_deterministic() -> None:
    # Two orderings of the same facts — sorted result must be identical.
    base = {"value_status": "present", "value": 1.0, "source_run_id": "r1",
            "section": "BS", "source_period_label": "2024Q1", "line_item_code": "bsa1"}

    f_a = dict(base) | {"symbol": "AAA"}
    f_b = dict(base) | {"symbol": "BBB"}
    f_a2 = dict(base) | {"symbol": "AAA", "line_item_code": "bsa2"}

    unordered = [f_b, f_a2, f_a]
    sorted_once = _sort_facts(unordered)
    sorted_twice = _sort_facts(list(reversed(unordered)))

    assert sorted_once == sorted_twice
    assert sorted_once[0]["symbol"] == "AAA"
    assert sorted_once[0]["line_item_code"] == "bsa1"
    assert sorted_once[1]["symbol"] == "AAA"
    assert sorted_once[1]["line_item_code"] == "bsa2"
    assert sorted_once[2]["symbol"] == "BBB"


# ---------------------------------------------------------------------------
# _check_duplicate_keys
# ---------------------------------------------------------------------------


def _make_fact(
    symbol: str = "TST",
    section: str = "BS",
    period_label: str = "2024Q1",
    code: str = "bsa1",
    run_id: str = "r1",
) -> dict:
    return {
        "symbol": symbol,
        "section": section,
        "source_period_label": period_label,
        "line_item_code": code,
        "source_run_id": run_id,
        "line_item_name": "",
        "value_status": "present",
    }


def test_check_duplicate_keys_no_dupes_returns_info() -> None:
    facts = [_make_fact(code="bsa1"), _make_fact(code="bsa2")]
    findings = _check_duplicate_keys(facts)
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"
    assert findings[0]["check"] == "duplicate_keys"


def test_check_duplicate_keys_detects_exact_duplicate() -> None:
    facts = [_make_fact(code="bsa1"), _make_fact(code="bsa1")]
    findings = _check_duplicate_keys(facts)
    assert any(f["severity"] == "error" for f in findings)
    assert "duplicate" in findings[0]["detail"].lower()


def test_check_duplicate_keys_different_run_ids_not_duplicate() -> None:
    facts = [_make_fact(code="bsa1", run_id="r1"), _make_fact(code="bsa1", run_id="r2")]
    findings = _check_duplicate_keys(facts)
    assert all(f["severity"] == "info" for f in findings)


# ---------------------------------------------------------------------------
# _check_publicdate_format
# ---------------------------------------------------------------------------


def test_check_publicdate_format_valid_iso_passes() -> None:
    facts = [
        _make_fact() | {"public_date": "2024-04-25T00:00:00"},
        _make_fact() | {"public_date": "2023-12-31"},
    ]
    findings = _check_publicdate_format(facts)
    assert all(f["severity"] == "info" for f in findings)


def test_check_publicdate_format_empty_is_ok() -> None:
    facts = [_make_fact() | {"public_date": ""}]
    findings = _check_publicdate_format(facts)
    assert all(f["severity"] == "info" for f in findings)


def test_check_publicdate_format_bad_format_is_warning() -> None:
    facts = [_make_fact() | {"public_date": "25/04/2024"}]
    findings = _check_publicdate_format(facts)
    assert any(f["severity"] == "warning" for f in findings)
    assert any("ISO" in f["detail"] or "format" in f["detail"].lower() for f in findings)


def test_check_publicdate_format_slash_date_is_warning() -> None:
    facts = [_make_fact() | {"public_date": "2024/04/25"}]
    findings = _check_publicdate_format(facts)
    assert any(f["severity"] == "warning" for f in findings)


# ---------------------------------------------------------------------------
# _check_mapping_coverage
# ---------------------------------------------------------------------------


def test_check_mapping_coverage_zero_when_no_names() -> None:
    facts = [
        _make_fact(code="bsa1") | {"line_item_name": ""},
        _make_fact(code="bsa2") | {"line_item_name": ""},
    ]
    findings = _check_mapping_coverage(facts)
    assert len(findings) == 1
    assert findings[0]["check"] == "mapping_coverage"
    assert "0.0%" in findings[0]["detail"] or "0/" in findings[0]["detail"]


def test_check_mapping_coverage_reports_unique_codes() -> None:
    facts = [_make_fact(code=c) | {"line_item_name": ""} for c in ("bsa1", "bsa2", "bsa3")]
    findings = _check_mapping_coverage(facts)
    assert "3" in findings[0]["detail"]  # 3 unique codes


def test_check_mapping_coverage_empty_facts_does_not_crash() -> None:
    findings = _check_mapping_coverage([])
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# _check_no_invented_names
# ---------------------------------------------------------------------------


def test_check_no_invented_names_passes_when_all_empty() -> None:
    facts = [
        _make_fact() | {"line_item_name": ""},
        _make_fact(code="bsa2") | {"line_item_name": ""},
    ]
    findings = _check_no_invented_names(facts)
    assert all(f["severity"] == "info" for f in findings)


def test_check_no_invented_names_error_when_name_present() -> None:
    facts = [_make_fact() | {"line_item_name": "Total Assets"}]
    findings = _check_no_invented_names(facts)
    assert any(f["severity"] == "error" for f in findings)
    assert any("invented" in f["detail"].lower() or "non-empty" in f["detail"] for f in findings)


# ---------------------------------------------------------------------------
# _check_value_status_validity
# ---------------------------------------------------------------------------


def test_check_value_status_validity_passes_for_valid_values() -> None:
    facts = [
        _make_fact() | {"value_status": "present"},
        _make_fact(code="bsa2") | {"value_status": "zero"},
        _make_fact(code="nos1") | {"value_status": "missing"},
    ]
    findings = _check_value_status_validity(facts)
    assert all(f["severity"] == "info" for f in findings)


def test_check_value_status_validity_error_for_bad_value() -> None:
    facts = [_make_fact() | {"value_status": "unknown_garbage"}]
    findings = _check_value_status_validity(facts)
    assert any(f["severity"] == "error" for f in findings)


# ---------------------------------------------------------------------------
# _check_nos_pattern
# ---------------------------------------------------------------------------


def test_check_nos_pattern_all_null_is_info() -> None:
    facts = [
        _make_fact(code="nos1", symbol="FPT") | {"value_status": "missing"},
        _make_fact(code="nos2", symbol="FPT") | {"value_status": "missing"},
    ]
    findings = _check_nos_pattern(facts)
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"
    assert "100%" in findings[0]["detail"]
    assert "non-securities" in findings[0]["detail"]


def test_check_nos_pattern_zero_null_is_info() -> None:
    facts = [
        _make_fact(code="nos1", symbol="VCI") | {"value_status": "present"},
        _make_fact(code="nos2", symbol="VCI") | {"value_status": "zero"},
    ]
    findings = _check_nos_pattern(facts)
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"
    assert "securities" in findings[0]["detail"].lower()


def test_check_nos_pattern_mixed_is_warning() -> None:
    facts = [
        _make_fact(code="nos1", symbol="MIX") | {"value_status": "missing"},
        _make_fact(code="nos2", symbol="MIX") | {"value_status": "present"},
    ]
    findings = _check_nos_pattern(facts)
    assert any(f["severity"] == "warning" for f in findings)
    assert any("Mixed" in f["detail"] or "mixed" in f["detail"] for f in findings)


def test_check_nos_pattern_no_nos_columns_returns_info() -> None:
    facts = [_make_fact(code="bsa1") | {"value_status": "present"}]
    findings = _check_nos_pattern(facts)
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"
    assert "No nos*" in findings[0]["detail"]


def test_check_nos_pattern_non_nos_columns_not_counted() -> None:
    facts = [
        _make_fact(code="bsa1", symbol="FPT") | {"value_status": "missing"},
        _make_fact(code="nos1", symbol="FPT") | {"value_status": "missing"},
    ]
    findings = _check_nos_pattern(facts)
    # Only nos1 counted; bsa1 is not a nos* column.
    assert "1/1" in findings[0]["detail"]


# ---------------------------------------------------------------------------
# validate_parse_result (composite)
# ---------------------------------------------------------------------------


def _make_stats(
    run_id: str = "r1",
    symbol: str = "TST",
    section: str = "BS",
    metric_col_count: int = 2,
) -> dict:
    return {
        "run_id": run_id,
        "symbol": symbol,
        "section": section,
        "dataset": "ds",
        "quarter_rows_read": 1,
        "year_rows_read": 0,
        "metric_column_count": metric_col_count,
        "output_fact_rows": 2,
        "q_publicdate_nonnull": 1,
        "y_publicdate_nonnull": 0,
    }


def test_validate_clean_input_has_no_errors() -> None:
    facts = [
        _make_fact(code="bsa1") | {"line_item_name": "", "public_date": "2024-04-25T00:00:00",
                                    "value_status": "present"},
        _make_fact(code="bsa2") | {"line_item_name": "", "public_date": "2024-04-25T00:00:00",
                                    "value_status": "zero"},
    ]
    stats = [_make_stats()]
    findings = validate_parse_result(facts, stats)
    errors = [f for f in findings if f["severity"] == "error"]
    assert errors == []


def test_validate_detects_zero_metric_columns_as_error() -> None:
    facts = [_make_fact() | {"line_item_name": "", "public_date": "", "value_status": "present"}]
    stats = [_make_stats(metric_col_count=0)]
    findings = validate_parse_result(facts, stats)
    assert any(f["check"] == "metric_columns_detected" and f["severity"] == "error" for f in findings)


def test_validate_empty_facts_returns_error() -> None:
    findings = validate_parse_result([], [_make_stats()])
    assert any(f["check"] == "facts_produced" and f["severity"] == "error" for f in findings)


def test_validate_duplicate_key_surfaces_as_error() -> None:
    dup = _make_fact() | {"line_item_name": "", "public_date": "", "value_status": "present"}
    stats = [_make_stats()]
    findings = validate_parse_result([dup, dup], stats)
    assert any(f["check"] == "duplicate_keys" and f["severity"] == "error" for f in findings)


def test_validate_invented_name_surfaces_as_error() -> None:
    fact = _make_fact() | {"line_item_name": "Total Assets", "public_date": "", "value_status": "present"}
    stats = [_make_stats()]
    findings = validate_parse_result([fact], stats)
    assert any(f["check"] == "no_invented_names" and f["severity"] == "error" for f in findings)


def test_validate_mapping_coverage_finding_always_present() -> None:
    facts = [_make_fact() | {"line_item_name": "", "public_date": "", "value_status": "present"}]
    stats = [_make_stats()]
    findings = validate_parse_result(facts, stats)
    checks = [f["check"] for f in findings]
    assert "mapping_coverage" in checks


def test_validate_preserves_null_vs_zero_distinction() -> None:
    """Null (missing) and zero must be distinct value_status values — parser must not collapse them."""
    null_fact = _make_fact(code="nos1") | {"line_item_name": "", "public_date": "", "value_status": "missing"}
    zero_fact = _make_fact(code="bsa1") | {"line_item_name": "", "public_date": "", "value_status": "zero"}
    stats = [_make_stats()]
    findings = validate_parse_result([null_fact, zero_fact], stats)
    # No value_status_validity errors
    vs_errors = [f for f in findings if f["check"] == "value_status_validity" and f["severity"] == "error"]
    assert vs_errors == []
    # The distinct statuses are preserved
    statuses = {null_fact["value_status"], zero_fact["value_status"]}
    assert "missing" in statuses
    assert "zero" in statuses
    assert statuses != {"zero"}  # null must not be mapped to zero


def test_validate_does_not_fill_fake_metric_names() -> None:
    """Parser must never populate line_item_name without a real mapping."""
    rows = [_make_row(length=1, bsa1=1.0, bsa2=None)]
    meta = {"run_id": "r1", "symbol": "TST", "section": "BALANCE_SHEET"}
    facts, _ = melt_period_rows(rows, "quarter", meta, "")
    assert all(f.get("line_item_name", "") == "" for f in facts), (
        "line_item_name must be empty — parser must not invent metric names"
    )


# ---------------------------------------------------------------------------
# generate_report with validation_findings
# ---------------------------------------------------------------------------


def test_generate_report_includes_validation_section_when_findings_passed() -> None:
    stats = [{"run_id": "r1", "symbol": "T", "section": "S", "dataset": "d",
               "quarter_rows_read": 1, "year_rows_read": 0, "metric_column_count": 2,
               "output_fact_rows": 2, "q_publicdate_nonnull": 1, "y_publicdate_nonnull": 0}]
    findings = [
        {"check": "duplicate_keys", "severity": "info", "detail": "No duplicates."},
        {"check": "mapping_coverage", "severity": "info", "detail": "0 rows named."},
    ]
    report = generate_report(stats, [], [], validation_findings=findings)
    assert "Validation" in report
    assert "duplicate_keys" in report
    assert "mapping_coverage" in report


def test_generate_report_no_validation_section_when_no_findings() -> None:
    stats = [{"run_id": "r1", "symbol": "T", "section": "S", "dataset": "d",
               "quarter_rows_read": 0, "year_rows_read": 0, "metric_column_count": 0,
               "output_fact_rows": 0, "q_publicdate_nonnull": 0, "y_publicdate_nonnull": 0}]
    report = generate_report(stats, [], [], validation_findings=None)
    # No validation section when findings is None (backward compat).
    assert "## Validation" not in report
