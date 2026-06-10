"""Tests for scripts/resolve_vietcap_iq_fa_metric_mapping.py.

All tests use inline fixtures. No live network. No DB. No parser changes.
Covers all §6.6 test groups from the integration strategy doc, plus additional
safety and backwards-compatibility checks.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from resolve_vietcap_iq_fa_metric_mapping import (
    MAPPING_RESULT_COLUMNS,
    VALID_MAPPING_STATUSES,
    MappingResolver,
    MappingResult,
    build_resolver,
    load_primary_mapping,
    load_union_mapping,
)


# ---------------------------------------------------------------------------
# Inline fixture helpers
# ---------------------------------------------------------------------------


def _make_primary_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal primary mapping CSV (_MAPPING_COLUMNS schema)."""
    p = tmp_path / "primary_mapping.csv"
    fieldnames = ["section", "line_item_code", "line_item_name_en", "line_item_name_vi",
                  "level", "parent"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return p


def _make_union_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal union mapping CSV (_UNION_COLUMNS schema)."""
    p = tmp_path / "union_mapping.csv"
    fieldnames = ["section", "line_item_code", "line_item_name_en_consensus",
                  "conflict", "sources", "names_per_source", "level", "parent"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return p


def _make_resolver(
    primary_rows: list[dict] | None = None,
    union_rows: list[dict] | None = None,
    source_symbol: str = "VCI",
    run_id: str = "20260610T025420Z",
    mapping_group: str = "securities",
    has_primary: bool = True,
) -> MappingResolver:
    return MappingResolver(
        primary_rows=primary_rows,
        union_rows=union_rows or [],
        primary_source_symbol=source_symbol,
        primary_source_run_id=run_id,
        mapping_group=mapping_group,
        has_primary=has_primary,
    )


# Shared small data for many tests
_P_BS_A1 = {"section": "BALANCE_SHEET", "line_item_code": "bsa1",
             "line_item_name_en": "Total assets", "line_item_name_vi": "Tổng tài sản",
             "level": "1", "parent": ""}
_P_BS_A2 = {"section": "BALANCE_SHEET", "line_item_code": "bsa2",
             "line_item_name_en": "Cash", "line_item_name_vi": "Tiền mặt",
             "level": "2", "parent": "bsa1"}
_P_IS_A1 = {"section": "INCOME_STATEMENT", "line_item_code": "isa1",
             "line_item_name_en": "Net revenue", "line_item_name_vi": "Doanh thu thuần",
             "level": "1", "parent": ""}

_U_CONSENSUS_CF = {"section": "CASH_FLOW", "line_item_code": "cfa1",
                   "line_item_name_en_consensus": "Cash from operations",
                   "conflict": "false", "sources": "VCI;VCB"}
_U_CONFLICT_BS = {"section": "BALANCE_SHEET", "line_item_code": "bsa2",
                  "line_item_name_en_consensus": "",
                  "conflict": "true", "sources": "VCI;VCB",
                  "names_per_source": "VCI=Cash;VCB=Cash and precious metals"}
_U_CONSENSUS_BS_EXTRA = {"section": "BALANCE_SHEET", "line_item_code": "bsb1",
                          "line_item_name_en_consensus": "Bank-specific code",
                          "conflict": "false", "sources": "VCB"}


# ---------------------------------------------------------------------------
# 1. Primary lookup hit
# ---------------------------------------------------------------------------


class TestPrimaryLookupHit:
    def test_status_is_primary(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "primary"

    def test_name_en_populated(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.line_item_name_en == "Total assets"

    def test_name_vi_populated(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.line_item_name_vi == "Tổng tài sản"

    def test_source_symbol_correct(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], source_symbol="VCB")
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_source_symbol == "VCB"

    def test_source_run_id_correct(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], run_id="20260610T033851Z")
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_source_run_id == "20260610T033851Z"

    def test_mapping_conflict_false(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_conflict == "false"

    def test_mapping_group_propagated(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], mapping_group="bank")
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_group == "bank"

    def test_multiple_codes(self):
        r = _make_resolver(primary_rows=[_P_BS_A1, _P_BS_A2, _P_IS_A1])
        assert r.resolve("BALANCE_SHEET", "bsa1").mapping_status == "primary"
        assert r.resolve("BALANCE_SHEET", "bsa2").mapping_status == "primary"
        assert r.resolve("INCOME_STATEMENT", "isa1").mapping_status == "primary"


# ---------------------------------------------------------------------------
# 2. Primary miss → union consensus fallback hit
# ---------------------------------------------------------------------------


class TestPrimaryMissConsensusFallback:
    def test_status_is_consensus_fallback(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_status == "consensus_fallback"

    def test_name_en_from_consensus(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.line_item_name_en == "Cash from operations"

    def test_source_symbol_is_union(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_source_symbol == "union"

    def test_run_id_empty_for_union(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_source_run_id == ""

    def test_conflict_false_for_consensus(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_conflict == "false"

    def test_vi_name_empty_for_consensus_fallback(self):
        # Union CSV has no per-code VI names; primary has bsa1 only so cfa1 falls through
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF], has_primary=True)
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_status == "consensus_fallback"
        assert result.line_item_name_vi == ""

    def test_union_code_not_in_primary(self):
        # bsb1 is not in primary; should fall back to union
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_BS_EXTRA])
        result = r.resolve("BALANCE_SHEET", "bsb1")
        assert result.mapping_status == "consensus_fallback"
        assert result.line_item_name_en == "Bank-specific code"


# ---------------------------------------------------------------------------
# 3. Primary section mismatch
# ---------------------------------------------------------------------------


class TestPrimarySectionMismatch:
    def test_status_is_section_mismatch(self):
        # bsa1 is in BALANCE_SHEET primary but query asks INCOME_STATEMENT
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("INCOME_STATEMENT", "bsa1")
        assert result.mapping_status == "section_mismatch"

    def test_name_en_empty_on_section_mismatch(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("INCOME_STATEMENT", "bsa1")
        assert result.line_item_name_en == ""

    def test_name_vi_empty_on_section_mismatch(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("INCOME_STATEMENT", "bsa1")
        assert result.line_item_name_vi == ""

    def test_conflict_false_on_primary_section_mismatch(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("INCOME_STATEMENT", "bsa1")
        assert result.mapping_conflict == "false"

    def test_cash_flow_query_against_bs_code(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("CASH_FLOW", "bsa1")
        assert result.mapping_status == "section_mismatch"


# ---------------------------------------------------------------------------
# 4. Union section mismatch (code in union but section doesn't match query)
# ---------------------------------------------------------------------------


class TestUnionSectionMismatch:
    def test_status_is_section_mismatch(self):
        # Primary is non-empty (has isa1) but cfa1 is absent → falls through to union.
        # Union has cfa1 under CASH_FLOW; query asks BALANCE_SHEET → section_mismatch.
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONSENSUS_CF], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "cfa1")
        assert result.mapping_status == "section_mismatch"

    def test_name_empty_on_union_section_mismatch(self):
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONSENSUS_CF], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "cfa1")
        assert result.line_item_name_en == ""

    def test_general_firm_union_section_mismatch(self):
        # General firm (has_primary=False); union code section doesn't match
        r = _make_resolver(
            primary_rows=None,
            union_rows=[_U_CONSENSUS_CF],
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("BALANCE_SHEET", "cfa1")
        assert result.mapping_status == "section_mismatch"


# ---------------------------------------------------------------------------
# 5. Conflict skipped
# ---------------------------------------------------------------------------


class TestConflictSkipped:
    # Primary is non-empty (has isa1) so bsa2 falls through to union (not no_mapping_available).
    def test_status_is_conflict_skipped(self):
        # bsa2 is in union with conflict=true (VCI="Cash", VCB="Cash and precious metals")
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONFLICT_BS], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "bsa2")
        assert result.mapping_status == "conflict_skipped"

    def test_name_en_empty_for_conflict(self):
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONFLICT_BS], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "bsa2")
        assert result.line_item_name_en == ""

    def test_name_vi_empty_for_conflict(self):
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONFLICT_BS], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "bsa2")
        assert result.line_item_name_vi == ""

    def test_mapping_conflict_true(self):
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONFLICT_BS], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "bsa2")
        assert result.mapping_conflict == "true"

    def test_conflict_skipped_overrides_not_covered(self):
        # Code in union with conflict=true; must be conflict_skipped, not not_covered
        r = _make_resolver(primary_rows=[_P_IS_A1], union_rows=[_U_CONFLICT_BS], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "bsa2")
        assert result.mapping_status == "conflict_skipped"

    def test_general_firm_conflict_skipped(self):
        r = _make_resolver(
            primary_rows=None,
            union_rows=[_U_CONFLICT_BS],
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("BALANCE_SHEET", "bsa2")
        assert result.mapping_status == "conflict_skipped"
        assert result.mapping_conflict == "true"


# ---------------------------------------------------------------------------
# 6. Not covered
# ---------------------------------------------------------------------------


class TestNotCovered:
    def test_status_is_not_covered(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "NONEXISTENT_CODE")
        assert result.mapping_status == "not_covered"

    def test_name_empty_when_not_covered(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "NONEXISTENT_CODE")
        assert result.line_item_name_en == ""
        assert result.line_item_name_vi == ""

    def test_conflict_false_when_not_covered(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "NONEXISTENT_CODE")
        assert result.mapping_conflict == "false"

    def test_not_covered_with_empty_primary_and_union(self):
        r = _make_resolver(primary_rows=[], union_rows=[], has_primary=True)
        result = r.resolve("BALANCE_SHEET", "bsa1")
        # No primary loaded → no_mapping_available (not not_covered)
        assert result.mapping_status == "no_mapping_available"

    def test_not_covered_with_nonempty_primary_no_union_match(self):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        # bsZ999 not in primary or union
        result = r.resolve("BALANCE_SHEET", "bsZ999")
        assert result.mapping_status == "not_covered"


# ---------------------------------------------------------------------------
# 7. No primary mapping available — general firm, union fallback allowed
# ---------------------------------------------------------------------------


class TestNoPrimaryUnionFallback:
    def test_consensus_fallback_for_general_firm(self):
        r = _make_resolver(
            primary_rows=None,
            union_rows=[_U_CONSENSUS_CF],
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_status == "consensus_fallback"

    def test_name_populated_from_union_for_general_firm(self):
        r = _make_resolver(
            primary_rows=None,
            union_rows=[_U_CONSENSUS_CF],
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.line_item_name_en == "Cash from operations"

    def test_mapping_group_preserved_for_general(self):
        r = _make_resolver(
            primary_rows=None,
            union_rows=[_U_CONSENSUS_CF],
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_group == "general"

    def test_has_primary_false_skips_primary_index(self):
        # Even if primary_rows is passed, has_primary=False means it is ignored
        r = MappingResolver(
            primary_rows=[_P_BS_A1],  # provided but ignored
            union_rows=[_U_CONSENSUS_CF],
            primary_source_symbol="VCI",
            primary_source_run_id="run1",
            mapping_group="general",
            has_primary=False,
        )
        # bsa1 is in primary_rows but they are ignored when has_primary=False
        # so falls through to union; bsa1 is not in union → not_covered
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "not_covered"


# ---------------------------------------------------------------------------
# 8. No primary mapping available — general firm, no union fallback
# ---------------------------------------------------------------------------


class TestNoPrimaryNoUnionFallback:
    def test_not_covered_for_general_when_union_empty(self):
        r = _make_resolver(
            primary_rows=None,
            union_rows=[],
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "not_covered"

    def test_not_covered_for_general_code_absent_from_union(self):
        r = _make_resolver(
            primary_rows=None,
            union_rows=[_U_CONSENSUS_CF],  # only cfa1
            mapping_group="general",
            has_primary=False,
        )
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "not_covered"

    def test_no_mapping_available_when_has_primary_true_but_no_rows(self):
        # has_primary=True but primary_rows is empty → no_mapping_available
        r = _make_resolver(
            primary_rows=[],  # empty — primary expected but missing
            union_rows=[_U_CONSENSUS_CF],
            has_primary=True,
        )
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_status == "no_mapping_available"

    def test_no_mapping_available_when_primary_rows_none_has_primary_true(self):
        r = MappingResolver(
            primary_rows=None,  # not loaded
            union_rows=[_U_CONSENSUS_CF],
            primary_source_symbol="VCB",
            primary_source_run_id="run1",
            mapping_group="bank",
            has_primary=True,  # expected but absent
        )
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_status == "no_mapping_available"


# ---------------------------------------------------------------------------
# 9. No invented names
# ---------------------------------------------------------------------------


class TestNoInventedNames:
    _EMPTY_NAME_STATUSES = {
        "conflict_skipped",
        "not_covered",
        "no_mapping_available",
        "section_mismatch",
    }

    def _resolver_with_all_cases(self) -> MappingResolver:
        return MappingResolver(
            primary_rows=[_P_BS_A1],
            union_rows=[_U_CONFLICT_BS, _U_CONSENSUS_CF],
            primary_source_symbol="VCI",
            primary_source_run_id="run1",
            mapping_group="securities",
            has_primary=True,
        )

    def test_conflict_skipped_has_empty_name(self):
        r = self._resolver_with_all_cases()
        res = r.resolve("BALANCE_SHEET", "bsa2")
        assert res.mapping_status == "conflict_skipped"
        assert res.line_item_name_en == ""
        assert res.line_item_name_vi == ""

    def test_not_covered_has_empty_name(self):
        r = self._resolver_with_all_cases()
        res = r.resolve("BALANCE_SHEET", "PHANTOM")
        assert res.mapping_status == "not_covered"
        assert res.line_item_name_en == ""

    def test_section_mismatch_has_empty_name(self):
        r = self._resolver_with_all_cases()
        res = r.resolve("CASH_FLOW", "bsa1")
        assert res.mapping_status == "section_mismatch"
        assert res.line_item_name_en == ""

    def test_no_mapping_available_has_empty_name(self):
        r = _make_resolver(primary_rows=[], union_rows=[], has_primary=True)
        res = r.resolve("BALANCE_SHEET", "bsa1")
        assert res.mapping_status == "no_mapping_available"
        assert res.line_item_name_en == ""

    def test_all_empty_name_statuses_have_empty_names(self):
        # Build a resolver that can produce each status
        r = MappingResolver(
            primary_rows=[_P_BS_A1],
            union_rows=[_U_CONFLICT_BS, _U_CONSENSUS_CF],
            primary_source_symbol="VCI",
            primary_source_run_id="run1",
            mapping_group="securities",
            has_primary=True,
        )
        cases = [
            ("BALANCE_SHEET", "bsa2"),   # conflict_skipped
            ("BALANCE_SHEET", "PHANTOM"),  # not_covered
            ("CASH_FLOW", "bsa1"),        # section_mismatch (primary has wrong section)
        ]
        for sec, code in cases:
            res = r.resolve(sec, code)
            assert res.mapping_status in self._EMPTY_NAME_STATUSES, \
                f"Unexpected status {res.mapping_status!r} for ({sec}, {code})"
            assert res.line_item_name_en == "", \
                f"Expected empty name for status={res.mapping_status!r}, got {res.line_item_name_en!r}"


# ---------------------------------------------------------------------------
# 10. Deterministic output for batch resolver
# ---------------------------------------------------------------------------


class TestDeterministicBatch:
    def test_same_inputs_same_output(self):
        rows = [
            {"section": "BALANCE_SHEET", "line_item_code": "bsa1"},
            {"section": "CASH_FLOW", "line_item_code": "cfa1"},
            {"section": "BALANCE_SHEET", "line_item_code": "PHANTOM"},
        ]
        r = MappingResolver(
            primary_rows=[_P_BS_A1],
            union_rows=[_U_CONSENSUS_CF],
            primary_source_symbol="VCI",
            primary_source_run_id="run1",
            mapping_group="securities",
            has_primary=True,
        )
        out1 = r.resolve_many(rows)
        out2 = r.resolve_many(rows)
        assert out1 == out2

    def test_output_order_matches_input_order(self):
        codes = ["cfa1", "bsa1", "PHANTOM", "bsb1"]
        rows = [{"section": "BALANCE_SHEET", "line_item_code": c} for c in codes]
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        out = r.resolve_many(rows)
        assert [o["line_item_code"] for o in out] == codes

    def test_resolve_many_length_matches_input(self):
        rows = [{"section": "BALANCE_SHEET", "line_item_code": c}
                for c in ["bsa1", "bsa2", "UNKNOWN"]]
        r = _make_resolver(primary_rows=[_P_BS_A1, _P_BS_A2])
        out = r.resolve_many(rows)
        assert len(out) == 3

    def test_resolve_many_empty_input(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        assert r.resolve_many([]) == []

    def test_resolve_many_contains_all_mapping_columns(self):
        rows = [{"section": "BALANCE_SHEET", "line_item_code": "bsa1"}]
        r = _make_resolver(primary_rows=[_P_BS_A1])
        out = r.resolve_many(rows)
        for col in MAPPING_RESULT_COLUMNS:
            assert col in out[0], f"Missing column: {col}"


# ---------------------------------------------------------------------------
# 11. No network imports
# ---------------------------------------------------------------------------


class TestNoNetworkImports:
    def test_no_httpx_import(self):
        import importlib
        spec = importlib.util.find_spec("resolve_vietcap_iq_fa_metric_mapping")
        assert spec is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "import httpx" not in source
        assert "import requests" not in source

    def test_resolver_works_without_network_in_test_environment(self):
        # Instantiate resolver with no real files — must not attempt any IO beyond init
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        assert r.resolve("BALANCE_SHEET", "bsa1").mapping_status == "primary"


# ---------------------------------------------------------------------------
# 12. No DB / no backtest imports
# ---------------------------------------------------------------------------


class TestNoDBNoBacktest:
    def test_no_db_imports(self):
        import importlib
        spec = importlib.util.find_spec("resolve_vietcap_iq_fa_metric_mapping")
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "questdb" not in source.lower()
        assert "sqlite3" not in source
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert ".sqlite" not in stripped
            if ".db" in stripped:
                assert "DictWriter" in stripped or "DictReader" in stripped, \
                    f"Possible DB file reference: {stripped!r}"

    def test_no_db_side_effects(self, tmp_path):
        r = _make_resolver(primary_rows=[_P_BS_A1], union_rows=[_U_CONSENSUS_CF])
        r.resolve_many([{"section": "BALANCE_SHEET", "line_item_code": "bsa1"}])
        db_files = list(tmp_path.glob("*.db")) + list(tmp_path.glob("*.sqlite"))
        assert db_files == []


# ---------------------------------------------------------------------------
# 13. Backwards compatibility — resolver never touches line_item_name
# ---------------------------------------------------------------------------


class TestBackwardsCompatibility:
    def test_resolve_many_passes_through_line_item_name_unchanged(self):
        rows = [{"section": "BALANCE_SHEET", "line_item_code": "bsa1",
                 "line_item_name": ""}]
        r = _make_resolver(primary_rows=[_P_BS_A1])
        out = r.resolve_many(rows)
        # Legacy column present and unchanged
        assert "line_item_name" in out[0]
        assert out[0]["line_item_name"] == ""

    def test_resolve_many_does_not_add_line_item_name_if_absent(self):
        rows = [{"section": "BALANCE_SHEET", "line_item_code": "bsa1"}]
        r = _make_resolver(primary_rows=[_P_BS_A1])
        out = r.resolve_many(rows)
        # Resolver should not add line_item_name if not present in input
        assert "line_item_name" not in out[0]

    def test_resolve_result_does_not_contain_line_item_name(self):
        r = _make_resolver(primary_rows=[_P_BS_A1])
        result = r.resolve("BALANCE_SHEET", "bsa1")
        d = result.as_dict()
        assert "line_item_name" not in d

    def test_mapping_result_columns_excludes_line_item_name(self):
        assert "line_item_name" not in MAPPING_RESULT_COLUMNS


# ---------------------------------------------------------------------------
# 14. load_primary_mapping CSV loader
# ---------------------------------------------------------------------------


class TestLoadPrimaryMapping:
    def test_loads_rows_correctly(self, tmp_path):
        p = _make_primary_csv(tmp_path, [_P_BS_A1, _P_IS_A1])
        rows = load_primary_mapping(p)
        assert len(rows) == 2
        assert rows[0]["line_item_code"] == "bsa1"

    def test_skips_empty_code_rows(self, tmp_path):
        header_row = {"section": "BALANCE_SHEET", "line_item_code": "",
                      "line_item_name_en": "Section header", "line_item_name_vi": "",
                      "level": "0", "parent": ""}
        p = _make_primary_csv(tmp_path, [header_row, _P_BS_A1])
        rows = load_primary_mapping(p)
        codes = [r["line_item_code"] for r in rows]
        assert "" not in codes
        assert "bsa1" in codes

    def test_preserves_all_columns(self, tmp_path):
        p = _make_primary_csv(tmp_path, [_P_BS_A1])
        rows = load_primary_mapping(p)
        for key in ["section", "line_item_code", "line_item_name_en", "line_item_name_vi"]:
            assert key in rows[0]

    def test_empty_file(self, tmp_path):
        p = _make_primary_csv(tmp_path, [])
        rows = load_primary_mapping(p)
        assert rows == []


# ---------------------------------------------------------------------------
# 15. load_union_mapping CSV loader
# ---------------------------------------------------------------------------


class TestLoadUnionMapping:
    def test_loads_all_rows_including_conflicts(self, tmp_path):
        p = _make_union_csv(tmp_path, [_U_CONSENSUS_CF, _U_CONFLICT_BS])
        rows = load_union_mapping(p)
        assert len(rows) == 2

    def test_skips_empty_code_rows(self, tmp_path):
        empty_row = {"section": "BALANCE_SHEET", "line_item_code": "",
                     "line_item_name_en_consensus": "", "conflict": "false"}
        p = _make_union_csv(tmp_path, [empty_row, _U_CONSENSUS_CF])
        rows = load_union_mapping(p)
        codes = [r["line_item_code"] for r in rows]
        assert "" not in codes

    def test_preserves_conflict_flag(self, tmp_path):
        p = _make_union_csv(tmp_path, [_U_CONFLICT_BS])
        rows = load_union_mapping(p)
        assert rows[0]["conflict"] == "true"

    def test_empty_file(self, tmp_path):
        p = _make_union_csv(tmp_path, [])
        rows = load_union_mapping(p)
        assert rows == []


# ---------------------------------------------------------------------------
# 16. build_resolver convenience constructor
# ---------------------------------------------------------------------------


class TestBuildResolver:
    def test_build_with_primary(self, tmp_path):
        primary_path = _make_primary_csv(tmp_path, [_P_BS_A1])
        union_path = _make_union_csv(tmp_path, [_U_CONSENSUS_CF])
        r = build_resolver(
            primary_path=primary_path,
            union_path=union_path,
            primary_source_symbol="VCI",
            primary_source_run_id="run1",
            mapping_group="securities",
        )
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "primary"

    def test_build_without_primary_is_general(self, tmp_path):
        union_path = _make_union_csv(tmp_path, [_U_CONSENSUS_CF])
        r = build_resolver(
            primary_path=None,
            union_path=union_path,
            primary_source_symbol="",
            primary_source_run_id="",
            mapping_group="general",
        )
        result = r.resolve("CASH_FLOW", "cfa1")
        assert result.mapping_status == "consensus_fallback"


# ---------------------------------------------------------------------------
# 17. MappingResult.as_dict() and VALID_MAPPING_STATUSES
# ---------------------------------------------------------------------------


class TestMappingResultSchema:
    def test_as_dict_has_all_columns(self):
        res = MappingResult()
        d = res.as_dict()
        for col in MAPPING_RESULT_COLUMNS:
            assert col in d, f"Missing: {col}"

    def test_valid_statuses_contains_required_six(self):
        required = {
            "primary", "consensus_fallback", "conflict_skipped",
            "not_covered", "no_mapping_available", "section_mismatch",
        }
        assert required.issubset(VALID_MAPPING_STATUSES)

    def test_every_resolve_returns_valid_status(self):
        r = MappingResolver(
            primary_rows=[_P_BS_A1],
            union_rows=[_U_CONFLICT_BS, _U_CONSENSUS_CF, _U_CONSENSUS_BS_EXTRA],
            primary_source_symbol="VCI",
            primary_source_run_id="run1",
            mapping_group="securities",
            has_primary=True,
        )
        test_cases = [
            ("BALANCE_SHEET", "bsa1"),    # primary
            ("CASH_FLOW", "cfa1"),        # consensus_fallback
            ("INCOME_STATEMENT", "bsa1"), # section_mismatch
            ("BALANCE_SHEET", "bsa2"),    # conflict_skipped
            ("BALANCE_SHEET", "PHANTOM"), # not_covered
        ]
        for sec, code in test_cases:
            res = r.resolve(sec, code)
            assert res.mapping_status in VALID_MAPPING_STATUSES, \
                f"Invalid status {res.mapping_status!r} for ({sec}, {code})"

    def test_default_mapping_result_is_not_covered(self):
        res = MappingResult()
        assert res.mapping_status == "not_covered"
        assert res.line_item_name_en == ""
        assert res.mapping_conflict == "false"
