from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

from scripts.plan_vietcap_iq_fa_full_history_manifest import (
    ALLOWED_SECTIONS,
    ENDPOINT_TEMPLATE,
    _MANIFEST_COLUMNS,
    _build_manifest,
    _parse_csv_list,
    _planned_raw_storage_prefix,
    main,
)


# ---------------------------------------------------------------------------
# _parse_csv_list
# ---------------------------------------------------------------------------


def test_parse_csv_list_splits_on_comma() -> None:
    assert _parse_csv_list("VCI,FPT") == ["VCI", "FPT"]


def test_parse_csv_list_strips_whitespace() -> None:
    assert _parse_csv_list(" VCI , FPT ") == ["VCI", "FPT"]


def test_parse_csv_list_single_item() -> None:
    assert _parse_csv_list("VCI") == ["VCI"]


def test_parse_csv_list_ignores_empty_tokens() -> None:
    assert _parse_csv_list("VCI,,FPT,") == ["VCI", "FPT"]


# ---------------------------------------------------------------------------
# _planned_raw_storage_prefix
# ---------------------------------------------------------------------------


def test_planned_raw_storage_prefix_contains_symbol_and_section() -> None:
    prefix = _planned_raw_storage_prefix("VCI", "BALANCE_SHEET")
    assert "VCI" in prefix
    assert "BALANCE_SHEET" in prefix


def test_planned_raw_storage_prefix_starts_with_data() -> None:
    prefix = _planned_raw_storage_prefix("FPT", "INCOME_STATEMENT")
    assert prefix.startswith("data/")


# ---------------------------------------------------------------------------
# _build_manifest — determinism
# ---------------------------------------------------------------------------


def test_build_manifest_is_deterministic() -> None:
    rows_a = _build_manifest(["FPT", "VCI"], ["BALANCE_SHEET", "INCOME_STATEMENT"])
    rows_b = _build_manifest(["VCI", "FPT"], ["INCOME_STATEMENT", "BALANCE_SHEET"])
    assert rows_a == rows_b


def test_build_manifest_sorted_by_symbol_then_section() -> None:
    rows = _build_manifest(["VCI", "AAA"], ["INCOME_STATEMENT", "BALANCE_SHEET"])
    symbols_sections = [(r["symbol"], r["section"]) for r in rows]
    assert symbols_sections == sorted(symbols_sections)


def test_build_manifest_row_count() -> None:
    rows = _build_manifest(["VCI", "FPT"], ["BALANCE_SHEET", "INCOME_STATEMENT"])
    assert len(rows) == 4  # 2 symbols × 2 sections


def test_build_manifest_single_symbol_single_section() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "VCI"
    assert rows[0]["section"] == "BALANCE_SHEET"


# ---------------------------------------------------------------------------
# _build_manifest — column correctness
# ---------------------------------------------------------------------------


def test_build_manifest_all_required_columns_present() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    for col in _MANIFEST_COLUMNS:
        assert col in rows[0], f"column {col!r} missing from manifest row"


def test_build_manifest_request_type_is_get() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all(r["request_type"] == "GET" for r in rows)


def test_build_manifest_status_is_planned_pending_gates() -> None:
    rows = _build_manifest(["VCI", "FPT"], list(ALLOWED_SECTIONS))
    assert all(r["status"] == "planned_pending_gates" for r in rows)


def test_build_manifest_requires_network_yes() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all(r["requires_network"] == "yes" for r in rows)


def test_build_manifest_requires_mapping_yes() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all(r["requires_mapping"] == "yes" for r in rows)


def test_build_manifest_requires_pit_validation_yes() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all(r["requires_pit_validation"] == "yes" for r in rows)


def test_build_manifest_reason_contains_mapping_gate() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all("metric_mapping_incomplete" in r["reason"] for r in rows)


def test_build_manifest_reason_contains_pit_gate() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all("publicDate_PIT_unconfirmed" in r["reason"] for r in rows)


def test_build_manifest_reason_contains_db_write_gate() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all("db_write_not_implemented" in r["reason"] for r in rows)


def test_build_manifest_endpoint_template_contains_symbol_placeholder() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all("{symbol}" in r["endpoint_template_or_name"] for r in rows)


def test_build_manifest_endpoint_template_contains_section_placeholder() -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert all("{section}" in r["endpoint_template_or_name"] for r in rows)


def test_build_manifest_planned_raw_storage_prefix_per_row() -> None:
    rows = _build_manifest(["VCI", "FPT"], ["BALANCE_SHEET", "INCOME_STATEMENT"])
    prefixes = {r["planned_raw_storage_prefix"] for r in rows}
    assert len(prefixes) == 4  # each (symbol, section) has a unique prefix


def test_build_manifest_no_db_language_in_notes_or_reason() -> None:
    rows = _build_manifest(["VCI"], list(ALLOWED_SECTIONS))
    for row in rows:
        combined = (row["notes"] + row["reason"] + row["status"]).lower()
        assert "db write" not in combined or "not_implemented" in combined or "db_write" in combined
        assert "backtest" not in combined


def test_build_manifest_no_side_effects(tmp_path: Path) -> None:
    rows = _build_manifest(["VCI"], ["BALANCE_SHEET"])
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert not any(tmp_path.iterdir())  # no files created


# ---------------------------------------------------------------------------
# main() CLI — valid input
# ---------------------------------------------------------------------------


def test_main_creates_csv_output(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI,FPT", "--sections", "BALANCE_SHEET,INCOME_STATEMENT",
          "--output", str(output)])
    assert output.exists()


def test_main_csv_has_correct_headers(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert list(reader.fieldnames or []) == _MANIFEST_COLUMNS


def test_main_csv_row_count(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI,FPT", "--sections", "BALANCE_SHEET,INCOME_STATEMENT",
          "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4  # 2 symbols × 2 sections


def test_main_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "deep" / "manifest.csv"
    assert not output.parent.exists()
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    assert output.exists()


def test_main_output_is_deterministic(tmp_path: Path) -> None:
    out_a = tmp_path / "a.csv"
    out_b = tmp_path / "b.csv"
    main(["--symbols", "FPT,VCI", "--sections", "INCOME_STATEMENT,BALANCE_SHEET",
          "--output", str(out_a)])
    main(["--symbols", "VCI,FPT", "--sections", "BALANCE_SHEET,INCOME_STATEMENT",
          "--output", str(out_b)])
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")


def test_main_all_allowed_sections(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    sections_arg = ",".join(ALLOWED_SECTIONS)
    main(["--symbols", "VCI", "--sections", sections_arg, "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(ALLOWED_SECTIONS)


# ---------------------------------------------------------------------------
# main() CLI — invalid input
# ---------------------------------------------------------------------------


def test_main_unknown_section_exits_with_error(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    with pytest.raises(SystemExit) as exc_info:
        main(["--symbols", "VCI", "--sections", "UNKNOWN_SECTION",
              "--output", str(output)])
    assert exc_info.value.code != 0


def test_main_unknown_section_error_message(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    output = tmp_path / "manifest.csv"
    with pytest.raises(SystemExit):
        main(["--symbols", "VCI", "--sections", "NOT_A_SECTION",
              "--output", str(output)])
    captured = capsys.readouterr()
    assert "NOT_A_SECTION" in captured.err or "Unknown" in captured.err


def test_main_mixed_valid_and_invalid_sections_exits(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    with pytest.raises(SystemExit) as exc_info:
        main(["--symbols", "VCI",
              "--sections", "BALANCE_SHEET,INVALID_SECTION",
              "--output", str(output)])
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# No httpx / requests import
# ---------------------------------------------------------------------------


def test_no_httpx_import_in_manifest_planner_module() -> None:
    import scripts.plan_vietcap_iq_fa_full_history_manifest as planner_mod
    assert not hasattr(planner_mod, "httpx"), (
        "manifest planner must not import httpx — it makes no network requests"
    )


def test_no_requests_import_in_manifest_planner_module() -> None:
    import scripts.plan_vietcap_iq_fa_full_history_manifest as planner_mod
    assert not hasattr(planner_mod, "requests"), (
        "manifest planner must not import requests — it makes no network requests"
    )


def test_httpx_not_in_module_source() -> None:
    import scripts.plan_vietcap_iq_fa_full_history_manifest as planner_mod
    source_path = Path(planner_mod.__file__)
    source = source_path.read_text(encoding="utf-8")
    assert "import httpx" not in source
    assert "import requests" not in source


# ---------------------------------------------------------------------------
# Readiness flags in CSV output
# ---------------------------------------------------------------------------


def test_csv_output_has_requires_mapping_column(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert "requires_mapping" in (reader.fieldnames or [])
        for row in reader:
            assert row["requires_mapping"] == "yes"


def test_csv_output_has_requires_pit_validation_column(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert "requires_pit_validation" in (reader.fieldnames or [])
        for row in reader:
            assert row["requires_pit_validation"] == "yes"


def test_csv_output_has_requires_network_column(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert "requires_network" in (reader.fieldnames or [])
        for row in reader:
            assert row["requires_network"] == "yes"


def test_csv_reason_contains_mapping_gate(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            assert "metric_mapping_incomplete" in row["reason"]


def test_csv_reason_contains_pit_gate(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "INCOME_STATEMENT", "--output", str(output)])
    with output.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            assert "publicDate_PIT_unconfirmed" in row["reason"]


# ---------------------------------------------------------------------------
# No DB / backtest side effects
# ---------------------------------------------------------------------------


def test_main_does_not_write_db_files(tmp_path: Path) -> None:
    output = tmp_path / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    db_suffixes = {".db", ".sqlite", ".sqlite3", ".duckdb", ".parquet"}
    created = {p.suffix for p in tmp_path.rglob("*") if p.is_file()}
    assert created.isdisjoint(db_suffixes), (
        f"manifest planner must not create DB files; found: {created & db_suffixes}"
    )


def test_main_only_creates_expected_csv(tmp_path: Path) -> None:
    output = tmp_path / "subdir" / "manifest.csv"
    main(["--symbols", "VCI", "--sections", "BALANCE_SHEET", "--output", str(output)])
    all_files = list(tmp_path.rglob("*"))
    file_paths = [f for f in all_files if f.is_file()]
    assert len(file_paths) == 1
    assert file_paths[0].suffix == ".csv"
