from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.parse_vietcap_iq_fa_metric_mapping_dry_run import (
    _COVERAGE_COLUMNS,
    _DEFAULT_MAPPING_PAYLOAD,
    _FA_META_KEYS,
    _MAPPING_COLUMNS,
    _extract_run_id,
    _metric_codes_from_fa_payload,
    build_mapping_index,
    compute_coverage,
    load_mapping_payload,
    main,
    parse_mapping_entries,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_MAPPING_PAYLOAD: dict[str, Any] = {
    "data": {
        "BALANCE_SHEET": [
            {
                "level": 1,
                "parent": None,
                "titleEn": "CURRENT ASSETS",
                "titleVi": "Tai san ngan han",
                "fullTitleVi": "Tai san ngan han",
                "fullTitleEn": "CURRENT ASSETS",
                "field": "bsa1",
                "name": "BSA1",
            },
            {
                "level": 2,
                "parent": "bsa1",
                "titleEn": "Cash",
                "titleVi": "Tien mat",
                "fullTitleVi": "Tien mat",
                "fullTitleEn": "Cash",
                "field": "bsa2",
                "name": "BSA2",
            },
            {
                "level": 0,
                "parent": None,
                "titleEn": "OFF-BALANCE SHEET ITEMS",
                "titleVi": "Ngoai bang",
                "fullTitleVi": "Ngoai bang",
                "fullTitleEn": "OFF-BALANCE SHEET ITEMS",
                "field": None,  # header entry — no metric code
                "name": "",
            },
        ],
        "INCOME_STATEMENT": [
            {
                "level": 1,
                "parent": None,
                "titleEn": "Revenue",
                "titleVi": "Doanh thu",
                "fullTitleVi": "Doanh thu",
                "fullTitleEn": "Revenue",
                "field": "isa1",
                "name": "ISA1",
            },
        ],
    }
}

_MINIMAL_FA_PAYLOAD: dict[str, Any] = {
    "data": {
        "quarters": [
            {
                "yearReport": 2024,
                "lengthReport": 1,
                "publicDate": "2024-04-30T00:00:00",
                "bsa1": 1000.0,
                "bsa2": 500.0,
                "bsa99": None,  # code not in mapping
            }
        ],
        "years": [
            {
                "yearReport": 2024,
                "lengthReport": 5,
                "publicDate": "2024-04-30T00:00:00",
                "bsa1": 2000.0,
                "bsa2": 1000.0,
                "bsa99": None,
            }
        ],
    }
}


def _write_mapping_fixture(tmp_path: Path, payload: dict[str, Any] | None = None) -> Path:
    """Write a mapping payload.json to tmp_path and return its path."""
    p = tmp_path / "mapping_payload.json"
    p.write_text(json.dumps(payload or _MINIMAL_MAPPING_PAYLOAD), encoding="utf-8")
    return p


def _write_probe_fixture(
    probe_root: Path,
    run_id: str,
    probe_name: str,
    symbol: str,
    section: str,
    fa_payload: dict[str, Any],
    access_status: str = "verified",
    http_status: int = 200,
) -> Path:
    """Write a probe payload.json + metadata.json under probe_root/<run_id>/<probe_name>/."""
    probe_dir = probe_root / f"run_id={run_id}" / probe_name
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "payload.json").write_text(json.dumps(fa_payload), encoding="utf-8")
    meta = {
        "symbol": symbol,
        "section": section,
        "access_status": access_status,
        "http_status": http_status,
    }
    (probe_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return probe_dir


# ---------------------------------------------------------------------------
# load_mapping_payload
# ---------------------------------------------------------------------------


def test_load_mapping_payload_returns_dict(tmp_path: Path) -> None:
    p = _write_mapping_fixture(tmp_path)
    result = load_mapping_payload(p)
    assert isinstance(result, dict)


def test_load_mapping_payload_has_data_key(tmp_path: Path) -> None:
    p = _write_mapping_fixture(tmp_path)
    result = load_mapping_payload(p)
    assert "data" in result


def test_load_mapping_payload_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mapping_payload(tmp_path / "nonexistent.json")


def test_load_mapping_payload_accepts_path_and_str(tmp_path: Path) -> None:
    p = _write_mapping_fixture(tmp_path)
    assert load_mapping_payload(p) == load_mapping_payload(str(p))


# ---------------------------------------------------------------------------
# parse_mapping_entries
# ---------------------------------------------------------------------------


def test_parse_mapping_entries_returns_list(tmp_path: Path) -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    assert isinstance(rows, list)


def test_parse_mapping_entries_row_count() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    # BS has 3 entries (2 real + 1 header), IS has 1 → total 4
    assert len(rows) == 4


def test_parse_mapping_entries_has_all_columns() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    for row in rows:
        for col in _MAPPING_COLUMNS:
            assert col in row, f"column {col!r} missing"


def test_parse_mapping_entries_null_field_marked_as_header() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    header_rows = [r for r in rows if r["is_header"] == "true"]
    assert len(header_rows) == 1
    assert header_rows[0]["line_item_code"] == ""


def test_parse_mapping_entries_non_null_field_marked_not_header() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    non_headers = [r for r in rows if r["is_header"] == "false"]
    assert len(non_headers) == 3
    assert all(r["line_item_code"] for r in non_headers)


def test_parse_mapping_entries_section_preserved() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    bs_rows = [r for r in rows if r["section"] == "BALANCE_SHEET"]
    is_rows = [r for r in rows if r["section"] == "INCOME_STATEMENT"]
    assert len(bs_rows) == 3
    assert len(is_rows) == 1


def test_parse_mapping_entries_name_en_populated() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    bsa1 = next(r for r in rows if r["line_item_code"] == "bsa1")
    assert bsa1["line_item_name_en"] == "CURRENT ASSETS"


def test_parse_mapping_entries_level_and_parent_preserved() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    bsa2 = next(r for r in rows if r["line_item_code"] == "bsa2")
    assert bsa2["level"] == "2"
    assert bsa2["parent"] == "bsa1"


def test_parse_mapping_entries_is_deterministic() -> None:
    rows_a = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    rows_b = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    assert rows_a == rows_b


def test_parse_mapping_entries_sorted_by_section_then_code() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    sort_keys = [(r["section"], r["is_header"], r["line_item_code"]) for r in rows]
    assert sort_keys == sorted(sort_keys)


def test_parse_mapping_entries_invalid_data_raises() -> None:
    with pytest.raises(ValueError):
        parse_mapping_entries({"data": "not_a_dict"})


def test_parse_mapping_entries_empty_sections() -> None:
    rows = parse_mapping_entries({"data": {}})
    assert rows == []


def test_parse_mapping_entries_name_field_in_row() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    bsa1 = next(r for r in rows if r["line_item_code"] == "bsa1")
    assert bsa1["name"] == "BSA1"


# ---------------------------------------------------------------------------
# build_mapping_index
# ---------------------------------------------------------------------------


def test_build_mapping_index_returns_dict() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    idx = build_mapping_index(rows)
    assert isinstance(idx, dict)


def test_build_mapping_index_excludes_header_entries() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    idx = build_mapping_index(rows)
    # Empty string key must not appear (from null-field header entry)
    assert "" not in idx


def test_build_mapping_index_includes_real_codes() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    idx = build_mapping_index(rows)
    assert "bsa1" in idx
    assert "bsa2" in idx
    assert "isa1" in idx


def test_build_mapping_index_maps_to_name_en() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    idx = build_mapping_index(rows)
    assert idx["bsa1"] == "CURRENT ASSETS"
    assert idx["bsa2"] == "Cash"


def test_build_mapping_index_length() -> None:
    rows = parse_mapping_entries(_MINIMAL_MAPPING_PAYLOAD)
    idx = build_mapping_index(rows)
    assert len(idx) == 3  # bsa1, bsa2, isa1 (not the null-field header)


# ---------------------------------------------------------------------------
# _metric_codes_from_fa_payload
# ---------------------------------------------------------------------------


def test_metric_codes_excludes_meta_keys() -> None:
    codes = _metric_codes_from_fa_payload(_MINIMAL_FA_PAYLOAD)
    for key in _FA_META_KEYS:
        assert key not in codes


def test_metric_codes_includes_real_codes() -> None:
    codes = _metric_codes_from_fa_payload(_MINIMAL_FA_PAYLOAD)
    assert "bsa1" in codes
    assert "bsa2" in codes
    assert "bsa99" in codes  # null value but key present → still a code


def test_metric_codes_deduplicates_across_periods() -> None:
    # bsa1 appears in both quarters and years; should appear once
    codes = _metric_codes_from_fa_payload(_MINIMAL_FA_PAYLOAD)
    # It's a set, so duplicates are gone
    assert len([c for c in codes if c == "bsa1"]) == 1


def test_metric_codes_empty_payload() -> None:
    codes = _metric_codes_from_fa_payload({"data": {}})
    assert codes == set()


# ---------------------------------------------------------------------------
# _extract_run_id
# ---------------------------------------------------------------------------


def test_extract_run_id_finds_run_id_part(tmp_path: Path) -> None:
    p = tmp_path / "run_id=20260610T025420Z" / "probe_name" / "payload.json"
    assert _extract_run_id(p) == "20260610T025420Z"


def test_extract_run_id_returns_empty_when_absent(tmp_path: Path) -> None:
    p = tmp_path / "some" / "other" / "path.json"
    assert _extract_run_id(p) == ""


# ---------------------------------------------------------------------------
# compute_coverage
# ---------------------------------------------------------------------------


def test_compute_coverage_returns_list(tmp_path: Path) -> None:
    mapping_path = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_path)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)
    result = compute_coverage(idx, tmp_path)
    assert isinstance(result, list)


def test_compute_coverage_counts_correctly(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_payload)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)

    # Write one probe: 3 codes total, bsa1+bsa2 in mapping, bsa99 not
    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T000000Z", "fa_bs_vci_probe",
        "VCI", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
    )

    results = compute_coverage(idx, probe_root)
    assert len(results) == 1
    r = results[0]
    assert r["symbol"] == "VCI"
    assert r["section"] == "BALANCE_SHEET"
    assert r["total_codes"] == "3"
    assert r["covered_codes"] == "2"
    assert r["coverage_pct"] == "66.7"


def test_compute_coverage_skips_unverified_probes(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_payload)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)

    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T000000Z", "fa_bs_vci_probe",
        "VCI", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
        access_status="auth_required",
    )

    results = compute_coverage(idx, probe_root)
    assert len(results) == 0


def test_compute_coverage_skips_mapping_payloads(tmp_path: Path) -> None:
    # A probe with quarters/years absent should be skipped
    mapping_payload = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_payload)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)

    probe_root = tmp_path / "probes"
    non_fa_payload = {"data": {"BALANCE_SHEET": []}}  # no quarters/years
    _write_probe_fixture(
        probe_root, "20260610T000000Z", "metrics_mapping_probe",
        "VCI", "BALANCE_SHEET", non_fa_payload,
    )

    results = compute_coverage(idx, probe_root)
    assert len(results) == 0


def test_compute_coverage_multiple_probes_sorted(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_payload)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)

    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T000001Z", "fa_bs_vci_probe",
        "VCI", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
    )
    _write_probe_fixture(
        probe_root, "20260610T000002Z", "fa_bs_fpt_probe",
        "FPT", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
    )

    results = compute_coverage(idx, probe_root)
    assert len(results) == 2
    symbols = [r["symbol"] for r in results]
    assert symbols == sorted(symbols)


def test_compute_coverage_has_required_columns(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_payload)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)

    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T000000Z", "fa_bs_vci_probe",
        "VCI", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
    )

    results = compute_coverage(idx, probe_root)
    assert len(results) == 1
    for col in _COVERAGE_COLUMNS:
        assert col in results[0], f"column {col!r} missing from coverage row"


def test_compute_coverage_run_id_extracted(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    payload = load_mapping_payload(mapping_payload)
    rows = parse_mapping_entries(payload)
    idx = build_mapping_index(rows)

    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T025429Z", "fa_cf_vci_probe",
        "VCI", "CASH_FLOW", _MINIMAL_FA_PAYLOAD,
    )

    results = compute_coverage(idx, probe_root)
    assert results[0]["probe_run_id"] == "20260610T025429Z"


# ---------------------------------------------------------------------------
# main() — mapping CSV output
# ---------------------------------------------------------------------------


def test_main_creates_mapping_csv(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    output = tmp_path / "mapping.csv"
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(output)])
    assert output.exists()


def test_main_mapping_csv_has_correct_headers(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    output = tmp_path / "mapping.csv"
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert list(reader.fieldnames or []) == _MAPPING_COLUMNS


def test_main_mapping_csv_row_count(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    output = tmp_path / "mapping.csv"
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4  # 3 BS (inc. 1 header) + 1 IS


def test_main_mapping_csv_is_deterministic(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    out_a = tmp_path / "a.csv"
    out_b = tmp_path / "b.csv"
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(out_a)])
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(out_b)])
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")


def test_main_creates_parent_directory(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    output = tmp_path / "nested" / "deep" / "mapping.csv"
    assert not output.parent.exists()
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(output)])
    assert output.exists()


def test_main_missing_payload_exits_nonzero(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([
            "--mapping-payload", str(tmp_path / "does_not_exist.json"),
            "--output-mapping", str(tmp_path / "out.csv"),
        ])
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# main() — coverage CSV output
# ---------------------------------------------------------------------------


def test_main_with_probe_dir_creates_coverage_csv(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T000000Z", "fa_bs_vci_probe",
        "VCI", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
    )
    out_mapping = tmp_path / "mapping.csv"
    out_coverage = tmp_path / "coverage.csv"
    main([
        "--mapping-payload", str(mapping_payload),
        "--output-mapping", str(out_mapping),
        "--probe-dir", str(probe_root),
        "--output-coverage", str(out_coverage),
    ])
    assert out_coverage.exists()


def test_main_coverage_csv_has_correct_headers(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    probe_root = tmp_path / "probes"
    _write_probe_fixture(
        probe_root, "20260610T000000Z", "fa_bs_vci_probe",
        "VCI", "BALANCE_SHEET", _MINIMAL_FA_PAYLOAD,
    )
    out_mapping = tmp_path / "mapping.csv"
    out_coverage = tmp_path / "coverage.csv"
    main([
        "--mapping-payload", str(mapping_payload),
        "--output-mapping", str(out_mapping),
        "--probe-dir", str(probe_root),
        "--output-coverage", str(out_coverage),
    ])
    with out_coverage.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert list(reader.fieldnames or []) == _COVERAGE_COLUMNS


def test_main_without_probe_dir_does_not_create_coverage_csv(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    out_mapping = tmp_path / "mapping.csv"
    out_coverage = tmp_path / "coverage.csv"
    main([
        "--mapping-payload", str(mapping_payload),
        "--output-mapping", str(out_mapping),
        # no --probe-dir
    ])
    assert not out_coverage.exists()


# ---------------------------------------------------------------------------
# No DB / no network side effects
# ---------------------------------------------------------------------------


def test_main_no_db_files_created(tmp_path: Path) -> None:
    mapping_payload = _write_mapping_fixture(tmp_path)
    out_mapping = tmp_path / "mapping.csv"
    main(["--mapping-payload", str(mapping_payload), "--output-mapping", str(out_mapping)])
    db_suffixes = {".db", ".sqlite", ".sqlite3", ".duckdb", ".parquet"}
    created = {p.suffix for p in tmp_path.rglob("*") if p.is_file()}
    assert created.isdisjoint(db_suffixes)


def test_no_httpx_import_in_module() -> None:
    import scripts.parse_vietcap_iq_fa_metric_mapping_dry_run as mod
    assert not hasattr(mod, "httpx"), "module must not import httpx"


def test_no_requests_import_in_module() -> None:
    import scripts.parse_vietcap_iq_fa_metric_mapping_dry_run as mod
    assert not hasattr(mod, "requests"), "module must not import requests"


def test_no_network_imports_in_source() -> None:
    import scripts.parse_vietcap_iq_fa_metric_mapping_dry_run as mod
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import httpx" not in source
    assert "import requests" not in source
    assert "urllib.request" not in source


# ---------------------------------------------------------------------------
# Default mapping payload path points to the real probe run
# ---------------------------------------------------------------------------


def test_default_mapping_payload_path_ends_with_payload_json() -> None:
    assert _DEFAULT_MAPPING_PAYLOAD.endswith("payload.json")


def test_default_mapping_payload_contains_expected_run_id() -> None:
    assert "20260610T025420Z" in _DEFAULT_MAPPING_PAYLOAD
