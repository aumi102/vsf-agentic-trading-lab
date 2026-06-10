from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.analyze_vietcap_iq_fa_metric_mapping_union import (
    _COVERAGE_COLUMNS,
    _UNION_COLUMNS,
    build_union_code_set,
    build_union_index,
    build_union_mapping,
    build_vci_only_index,
    compute_union_coverage,
    count_conflicts,
    discover_mapping_payloads,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MAPPING_VCI: dict[str, Any] = {
    "data": {
        "BALANCE_SHEET": [
            {"field": "bsa1", "titleEn": "Current Assets", "titleVi": "", "level": 1, "parent": None, "name": "BSA1", "fullTitleEn": "", "fullTitleVi": ""},
            {"field": "bsa2", "titleEn": "Cash", "titleVi": "", "level": 2, "parent": "bsa1", "name": "BSA2", "fullTitleEn": "", "fullTitleVi": ""},
            {"field": "bss1", "titleEn": "Securities assets", "titleVi": "", "level": 1, "parent": None, "name": "BSS1", "fullTitleEn": "", "fullTitleVi": ""},
        ],
        "INCOME_STATEMENT": [
            {"field": "isa1", "titleEn": "Revenue", "titleVi": "", "level": 1, "parent": None, "name": "ISA1", "fullTitleEn": "", "fullTitleVi": ""},
            {"field": "iss1", "titleEn": "Brokerage revenue", "titleVi": "", "level": 2, "parent": "isa1", "name": "ISS1", "fullTitleEn": "", "fullTitleVi": ""},
        ],
    }
}

_MAPPING_VCB: dict[str, Any] = {
    "data": {
        "BALANCE_SHEET": [
            {"field": "bsa1", "titleEn": "Current Assets", "titleVi": "", "level": 1, "parent": None, "name": "BSA1", "fullTitleEn": "", "fullTitleVi": ""},
            {"field": "bsb1", "titleEn": "Loans to customers", "titleVi": "", "level": 1, "parent": None, "name": "BSB1", "fullTitleEn": "", "fullTitleVi": ""},
        ],
        "INCOME_STATEMENT": [
            {"field": "isb1", "titleEn": "Interest income", "titleVi": "", "level": 1, "parent": None, "name": "ISB1", "fullTitleEn": "", "fullTitleVi": ""},
        ],
    }
}

_MAPPING_CONFLICT: dict[str, Any] = {
    "data": {
        "BALANCE_SHEET": [
            # bsa2 has DIFFERENT titleEn from VCI (Cash vs Cash Equivalents)
            {"field": "bsa2", "titleEn": "Cash Equivalents", "titleVi": "", "level": 2, "parent": "bsa1", "name": "BSA2", "fullTitleEn": "", "fullTitleVi": ""},
        ],
    }
}

_FA_PAYLOAD: dict[str, Any] = {
    "data": {
        "quarters": [
            {
                "yearReport": 2024,
                "lengthReport": 1,
                "publicDate": "2024-04-30T00:00:00",
                "bsa1": 1000.0,
                "bsa2": 500.0,
                "bss1": 200.0,
                "bsb1": None,
                "bsa99": None,  # not in any mapping
            }
        ],
        "years": [],
    }
}


def _write_mapping_probe(
    probe_root: Path,
    run_id: str,
    dataset: str,
    symbol: str,
    mapping: dict[str, Any],
    access_status: str = "verified",
) -> Path:
    d = probe_root / f"run_id={run_id}" / dataset
    d.mkdir(parents=True, exist_ok=True)
    (d / "payload.json").write_text(json.dumps(mapping), encoding="utf-8")
    meta = {"symbol": symbol, "section": "BALANCE_SHEET", "access_status": access_status, "http_status": 200}
    (d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


def _write_fa_probe(
    probe_root: Path,
    run_id: str,
    dataset: str,
    symbol: str,
    section: str,
    fa_payload: dict[str, Any],
) -> Path:
    d = probe_root / f"run_id={run_id}" / dataset
    d.mkdir(parents=True, exist_ok=True)
    (d / "payload.json").write_text(json.dumps(fa_payload), encoding="utf-8")
    meta = {"symbol": symbol, "section": section, "access_status": "verified", "http_status": 200}
    (d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# discover_mapping_payloads
# ---------------------------------------------------------------------------


def test_discover_finds_mapping_payloads(tmp_path: Path) -> None:
    _write_mapping_probe(tmp_path, "20260610T000001Z", "mapping_vci", "VCI", _MAPPING_VCI)
    results = discover_mapping_payloads(tmp_path)
    assert len(results) == 1
    assert results[0][0] == "VCI"


def test_discover_skips_fa_payloads(tmp_path: Path) -> None:
    _write_fa_probe(tmp_path, "20260610T000002Z", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    results = discover_mapping_payloads(tmp_path)
    assert len(results) == 0


def test_discover_skips_unverified(tmp_path: Path) -> None:
    _write_mapping_probe(tmp_path, "20260610T000001Z", "mapping_vci", "VCI", _MAPPING_VCI,
                         access_status="auth_required")
    results = discover_mapping_payloads(tmp_path)
    assert len(results) == 0


def test_discover_multiple_symbols(tmp_path: Path) -> None:
    _write_mapping_probe(tmp_path, "20260610T000001Z", "mapping_vci", "VCI", _MAPPING_VCI)
    _write_mapping_probe(tmp_path, "20260610T000002Z", "mapping_vcb", "VCB", _MAPPING_VCB)
    results = discover_mapping_payloads(tmp_path)
    assert len(results) == 2
    symbols = {r[0] for r in results}
    assert symbols == {"VCI", "VCB"}


# ---------------------------------------------------------------------------
# build_union_mapping
# ---------------------------------------------------------------------------


def test_build_union_returns_list() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    assert isinstance(rows, list)


def test_build_union_has_all_columns() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    for r in rows:
        for col in _UNION_COLUMNS:
            assert col in r, f"column {col!r} missing"


def test_build_union_single_symbol_no_conflict() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    assert all(r["conflict"] == "false" for r in rows)


def test_build_union_conflict_detected() -> None:
    # bsa2 appears in VCI as "Cash" and in _MAPPING_CONFLICT as "Cash Equivalents"
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "ALT": _MAPPING_CONFLICT})
    conflict_rows = [r for r in rows if r["conflict"] == "true"]
    assert len(conflict_rows) == 1
    assert conflict_rows[0]["line_item_code"] == "bsa2"


def test_build_union_conflict_consensus_empty() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "ALT": _MAPPING_CONFLICT})
    bsa2 = next(r for r in rows if r["line_item_code"] == "bsa2")
    assert bsa2["line_item_name_en_consensus"] == ""


def test_build_union_non_conflict_has_name() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    bsa1 = next(r for r in rows if r["line_item_code"] == "bsa1")
    assert bsa1["line_item_name_en_consensus"] == "Current Assets"
    assert bsa1["conflict"] == "false"


def test_build_union_union_has_codes_from_all_symbols() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    codes = {r["line_item_code"] for r in rows}
    assert "bss1" in codes   # VCI-only
    assert "bsb1" in codes   # VCB-only
    assert "isb1" in codes   # VCB IS


def test_build_union_sources_field_lists_symbols() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    bsa1 = next(r for r in rows if r["line_item_code"] == "bsa1")
    # bsa1 appears in both
    assert "VCI" in bsa1["sources"]
    assert "VCB" in bsa1["sources"]


def test_build_union_is_deterministic() -> None:
    rows_a = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    rows_b = build_union_mapping({"VCB": _MAPPING_VCB, "VCI": _MAPPING_VCI})
    assert rows_a == rows_b


def test_build_union_sorted_by_section_then_code() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    keys = [(r["section"], r["line_item_code"]) for r in rows]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# build_union_code_set
# ---------------------------------------------------------------------------


def test_build_union_code_set_includes_conflicting_codes() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "ALT": _MAPPING_CONFLICT})
    code_set = build_union_code_set(rows)
    # bsa2 is conflicting but must be in the set
    assert "bsa2" in code_set


def test_build_union_code_set_size() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    code_set = build_union_code_set(rows)
    # All unique codes across both payloads
    assert "bsa1" in code_set
    assert "bsb1" in code_set
    assert "bss1" in code_set
    assert "isb1" in code_set


# ---------------------------------------------------------------------------
# build_union_index
# ---------------------------------------------------------------------------


def test_build_union_index_excludes_conflicts() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "ALT": _MAPPING_CONFLICT})
    idx = build_union_index(rows)
    assert "bsa2" not in idx  # conflict


def test_build_union_index_includes_non_conflicts() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    idx = build_union_index(rows)
    assert "bsa1" in idx
    assert idx["bsa1"] == "Current Assets"


# ---------------------------------------------------------------------------
# build_vci_only_index
# ---------------------------------------------------------------------------


def test_build_vci_only_index_returns_only_vci_codes() -> None:
    idx = build_vci_only_index({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    assert "bsa1" in idx
    assert "bss1" in idx
    assert "bsb1" not in idx  # VCB-only


# ---------------------------------------------------------------------------
# count_conflicts
# ---------------------------------------------------------------------------


def test_count_conflicts_zero_when_no_conflict() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    assert count_conflicts(rows) == 0


def test_count_conflicts_positive_when_conflict() -> None:
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "ALT": _MAPPING_CONFLICT})
    assert count_conflicts(rows) == 1


# ---------------------------------------------------------------------------
# compute_union_coverage
# ---------------------------------------------------------------------------


def test_compute_union_coverage_returns_list(tmp_path: Path) -> None:
    _write_fa_probe(tmp_path, "run1", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    all_codes = build_union_code_set(rows)
    idx = build_union_index(rows)
    vci_idx = build_vci_only_index({"VCI": _MAPPING_VCI})
    result = compute_union_coverage(vci_idx, all_codes, idx, tmp_path)
    assert isinstance(result, list)


def test_compute_union_coverage_correct_counts(tmp_path: Path) -> None:
    _write_fa_probe(tmp_path, "run1", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    rows = build_union_mapping({"VCI": _MAPPING_VCI, "VCB": _MAPPING_VCB})
    all_codes = build_union_code_set(rows)
    idx = build_union_index(rows)
    vci_idx = build_vci_only_index({"VCI": _MAPPING_VCI})
    result = compute_union_coverage(vci_idx, all_codes, idx, tmp_path)
    assert len(result) == 1
    r = result[0]
    # FA has 5 codes: bsa1, bsa2, bss1, bsb1, bsa99
    # VCI mapping covers: bsa1, bsa2, bss1 (3 of 5 = 60%)
    # Union all codes covers: bsa1, bsa2, bss1, bsb1 (4 of 5 = 80%)
    # Union consensus covers: bsa1, bsa2, bss1, bsb1 (all non-conflicting = 4 of 5 = 80%)
    assert r["total_codes"] == "5"
    assert r["vci_only_covered"] == "3"
    assert r["union_covered"] == "4"


def test_compute_union_coverage_has_all_columns(tmp_path: Path) -> None:
    _write_fa_probe(tmp_path, "run1", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    all_codes = build_union_code_set(rows)
    idx = build_union_index(rows)
    vci_idx = build_vci_only_index({"VCI": _MAPPING_VCI})
    result = compute_union_coverage(vci_idx, all_codes, idx, tmp_path)
    for col in _COVERAGE_COLUMNS:
        assert col in result[0], f"column {col!r} missing"


def test_compute_union_coverage_skips_unverified(tmp_path: Path) -> None:
    d = tmp_path / "run_id=20260610T000001Z" / "fa_bs_vci"
    d.mkdir(parents=True, exist_ok=True)
    (d / "payload.json").write_text(json.dumps(_FA_PAYLOAD), encoding="utf-8")
    meta = {"symbol": "VCI", "section": "BALANCE_SHEET", "access_status": "auth_required"}
    (d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    all_codes = build_union_code_set(rows)
    idx = build_union_index(rows)
    vci_idx = build_vci_only_index({"VCI": _MAPPING_VCI})
    result = compute_union_coverage(vci_idx, all_codes, idx, tmp_path)
    assert len(result) == 0


def test_compute_union_coverage_skips_mapping_payloads(tmp_path: Path) -> None:
    # A mapping payload has no quarters/years — should be skipped
    _write_mapping_probe(tmp_path, "20260610T000001Z", "mapping_vci", "VCI", _MAPPING_VCI)
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    all_codes = build_union_code_set(rows)
    idx = build_union_index(rows)
    vci_idx = build_vci_only_index({"VCI": _MAPPING_VCI})
    result = compute_union_coverage(vci_idx, all_codes, idx, tmp_path)
    assert len(result) == 0


def test_compute_union_coverage_sorted(tmp_path: Path) -> None:
    _write_fa_probe(tmp_path, "run1", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    _write_fa_probe(tmp_path, "run2", "fa_bs_fpt", "FPT", "BALANCE_SHEET", _FA_PAYLOAD)
    rows = build_union_mapping({"VCI": _MAPPING_VCI})
    all_codes = build_union_code_set(rows)
    idx = build_union_index(rows)
    vci_idx = build_vci_only_index({"VCI": _MAPPING_VCI})
    result = compute_union_coverage(vci_idx, all_codes, idx, tmp_path)
    symbols = [r["symbol"] for r in result]
    assert symbols == sorted(symbols)


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


def test_main_creates_union_csv(tmp_path: Path) -> None:
    _write_mapping_probe(tmp_path / "probes", "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    out_union = tmp_path / "union.csv"
    out_cov = tmp_path / "coverage.csv"
    main(["--probe-dir", str(tmp_path / "probes"),
          "--output-union", str(out_union),
          "--output-coverage", str(out_cov)])
    assert out_union.exists()


def test_main_creates_coverage_csv(tmp_path: Path) -> None:
    probe_root = tmp_path / "probes"
    _write_mapping_probe(probe_root, "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    _write_fa_probe(probe_root, "run2", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    out_union = tmp_path / "union.csv"
    out_cov = tmp_path / "coverage.csv"
    main(["--probe-dir", str(probe_root),
          "--output-union", str(out_union),
          "--output-coverage", str(out_cov)])
    assert out_cov.exists()


def test_main_union_csv_has_correct_headers(tmp_path: Path) -> None:
    _write_mapping_probe(tmp_path / "probes", "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    out_union = tmp_path / "union.csv"
    out_cov = tmp_path / "coverage.csv"
    main(["--probe-dir", str(tmp_path / "probes"),
          "--output-union", str(out_union),
          "--output-coverage", str(out_cov)])
    with out_union.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert list(reader.fieldnames or []) == _UNION_COLUMNS


def test_main_coverage_csv_has_correct_headers(tmp_path: Path) -> None:
    probe_root = tmp_path / "probes"
    _write_mapping_probe(probe_root, "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    _write_fa_probe(probe_root, "run2", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    out_union = tmp_path / "union.csv"
    out_cov = tmp_path / "coverage.csv"
    main(["--probe-dir", str(probe_root),
          "--output-union", str(out_union),
          "--output-coverage", str(out_cov)])
    with out_cov.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert list(reader.fieldnames or []) == _COVERAGE_COLUMNS


def test_main_missing_probe_dir_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--probe-dir", str(tmp_path / "nonexistent"),
              "--output-union", str(tmp_path / "u.csv"),
              "--output-coverage", str(tmp_path / "c.csv")])
    assert exc_info.value.code != 0


def test_main_no_mapping_payloads_exits(tmp_path: Path) -> None:
    probe_root = tmp_path / "probes"
    probe_root.mkdir()
    # Only an FA payload, no mapping
    _write_fa_probe(probe_root, "run1", "fa_bs_vci", "VCI", "BALANCE_SHEET", _FA_PAYLOAD)
    with pytest.raises(SystemExit) as exc_info:
        main(["--probe-dir", str(probe_root),
              "--output-union", str(tmp_path / "u.csv"),
              "--output-coverage", str(tmp_path / "c.csv")])
    assert exc_info.value.code != 0


def test_main_is_deterministic(tmp_path: Path) -> None:
    probe_root = tmp_path / "probes"
    _write_mapping_probe(probe_root, "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    _write_mapping_probe(probe_root, "run2", "mapping_vcb", "VCB", _MAPPING_VCB)
    out_a = tmp_path / "a.csv"
    out_b = tmp_path / "b.csv"
    cov_a = tmp_path / "ca.csv"
    cov_b = tmp_path / "cb.csv"
    main(["--probe-dir", str(probe_root), "--output-union", str(out_a), "--output-coverage", str(cov_a)])
    main(["--probe-dir", str(probe_root), "--output-union", str(out_b), "--output-coverage", str(cov_b)])
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")


def test_main_creates_parent_directory(tmp_path: Path) -> None:
    _write_mapping_probe(tmp_path / "probes", "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    out_union = tmp_path / "nested" / "deep" / "union.csv"
    out_cov = tmp_path / "coverage.csv"
    main(["--probe-dir", str(tmp_path / "probes"),
          "--output-union", str(out_union),
          "--output-coverage", str(out_cov)])
    assert out_union.exists()


# ---------------------------------------------------------------------------
# No DB / no network side effects
# ---------------------------------------------------------------------------


def test_no_db_files_created(tmp_path: Path) -> None:
    probe_root = tmp_path / "probes"
    _write_mapping_probe(probe_root, "run1", "mapping_vci", "VCI", _MAPPING_VCI)
    out_union = tmp_path / "union.csv"
    out_cov = tmp_path / "coverage.csv"
    main(["--probe-dir", str(probe_root), "--output-union", str(out_union), "--output-coverage", str(out_cov)])
    db_suffixes = {".db", ".sqlite", ".sqlite3", ".duckdb", ".parquet"}
    created = {p.suffix for p in tmp_path.rglob("*") if p.is_file()}
    assert created.isdisjoint(db_suffixes)


def test_no_httpx_import_in_module() -> None:
    import scripts.analyze_vietcap_iq_fa_metric_mapping_union as mod
    assert not hasattr(mod, "httpx"), "module must not import httpx"


def test_no_requests_import_in_module() -> None:
    import scripts.analyze_vietcap_iq_fa_metric_mapping_union as mod
    assert not hasattr(mod, "requests"), "module must not import requests"


def test_no_network_imports_in_source() -> None:
    import scripts.analyze_vietcap_iq_fa_metric_mapping_union as mod
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import httpx" not in source
    assert "import requests" not in source
    assert "urllib.request" not in source
