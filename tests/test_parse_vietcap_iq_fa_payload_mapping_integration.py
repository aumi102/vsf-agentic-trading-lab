"""Integration tests for FA parser mapping enrichment.

All tests use tiny inline or temp-file fixtures.
No live network. No DB. Parser not modified for backtest/DB.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

# Allow sibling script imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from parse_vietcap_iq_fa_payloads_dry_run import (
    _LONG_FORMAT_COLUMNS,
    _MAPPING_DEFAULTS,
    _NAME_BEARING_STATUSES,
    _NON_NAME_BEARING_STATUSES,
    _SUMMARY_COLUMNS,
    _check_no_invented_names,
    _check_no_invented_names_en,
    _check_mapping_status_consistency,
    _load_firm_type_plan,
    _build_symbol_resolver,
    apply_mapping_to_facts,
    build_mapping_summary,
    melt_period_rows,
)
from resolve_vietcap_iq_fa_metric_mapping import VALID_MAPPING_STATUSES


# ---------------------------------------------------------------------------
# Inline fixture helpers
# ---------------------------------------------------------------------------


def _make_wide_row(
    ticker: str = "TST",
    organ_code: str = "TST",
    year: int = 2024,
    length: int = 1,
    public_date: str = "2024-04-25T00:00:00",
    **metrics,
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


def _make_meta(symbol: str = "TST", section: str = "BALANCE_SHEET") -> dict:
    return {"symbol": symbol, "section": section, "run_id": "run1",
            "dataset": "test", "content_hash": "abc", "raw_path": "",
            "crawled_at": "2026-06-10T00:00:00Z"}


def _make_facts(
    symbol: str = "TST",
    section: str = "BALANCE_SHEET",
    codes: list[str] | None = None,
) -> list[dict]:
    """Produce minimal long-format fact rows using melt_period_rows."""
    if codes is None:
        codes = ["bsa1", "bsa2"]
    row = _make_wide_row(ticker=symbol, organ_code=symbol, **{c: 100 for c in codes})
    meta = _make_meta(symbol=symbol, section=section)
    facts, _ = melt_period_rows([row], "quarter", meta, "2026-06-10T00:00:00")
    return facts


def _make_primary_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "primary.csv"
    cols = ["section", "line_item_code", "line_item_name_en", "line_item_name_vi", "level", "parent"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    return p


def _make_union_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "union.csv"
    cols = ["section", "line_item_code", "line_item_name_en_consensus",
            "conflict", "sources", "names_per_source", "level", "parent"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    return p


def _make_firm_plan_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "firm_plan.csv"
    cols = ["symbol", "proposed_firm_type", "mapping_source_symbol",
            "mapping_group", "confidence", "evidence", "fallback_policy", "notes"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    return p


# Shared small data
_PRIMARY_BSA1 = {"section": "BALANCE_SHEET", "line_item_code": "bsa1",
                 "line_item_name_en": "Total assets", "line_item_name_vi": "Tổng tài sản"}
_PRIMARY_BSA2 = {"section": "BALANCE_SHEET", "line_item_code": "bsa2",
                 "line_item_name_en": "Cash and cash equivalents", "line_item_name_vi": "Tiền"}
_PRIMARY_ISA1 = {"section": "INCOME_STATEMENT", "line_item_code": "isa1",
                 "line_item_name_en": "Net revenue", "line_item_name_vi": "Doanh thu thuần"}
_UNION_CFA1 = {"section": "CASH_FLOW", "line_item_code": "cfa1",
               "line_item_name_en_consensus": "Cash from operations", "conflict": "false"}
_UNION_CONFLICT = {"section": "BALANCE_SHEET", "line_item_code": "bsa2",
                   "line_item_name_en_consensus": "", "conflict": "true",
                   "names_per_source": "VCI=Cash;VCB=Cash and precious metals"}
_PLAN_VCI = {"symbol": "VCI", "mapping_group": "securities", "mapping_source_symbol": "VCI",
             "proposed_firm_type": "securities"}
_PLAN_FPT = {"symbol": "FPT", "mapping_group": "general", "mapping_source_symbol": "FPT",
             "proposed_firm_type": "general"}
_PLAN_FPT_UNION_ONLY = {"symbol": "FPT", "mapping_group": "general", "mapping_source_symbol": "",
                        "proposed_firm_type": "general"}


# ---------------------------------------------------------------------------
# 1. No mapping inputs — backward compatible
# ---------------------------------------------------------------------------


class TestNoMappingInputsBackwardCompat:
    def test_new_columns_in_long_format_columns(self):
        for col in ["line_item_name_en", "line_item_name_vi", "mapping_status",
                    "mapping_source_symbol", "mapping_source_run_id",
                    "mapping_conflict", "mapping_group"]:
            assert col in _LONG_FORMAT_COLUMNS, f"Missing: {col}"

    def test_legacy_column_still_present(self):
        assert "line_item_name" in _LONG_FORMAT_COLUMNS

    def test_facts_have_new_columns_with_empty_defaults(self):
        facts = _make_facts()
        for row in facts:
            for col in _MAPPING_DEFAULTS:
                assert col in row, f"Missing column: {col}"
                assert row[col] == "", f"Expected empty default for {col}, got {row[col]!r}"

    def test_legacy_line_item_name_remains_empty(self):
        facts = _make_facts()
        for row in facts:
            assert row["line_item_name"] == ""

    def test_no_mapping_status_by_default(self):
        facts = _make_facts()
        for row in facts:
            assert row.get("mapping_status") == ""

    def test_no_names_by_default(self):
        facts = _make_facts()
        for row in facts:
            assert row.get("line_item_name_en") == ""
            assert row.get("line_item_name_vi") == ""

    def test_existing_columns_unchanged(self):
        facts = _make_facts(codes=["bsa1"])
        row = facts[0]
        assert row["symbol"] == "TST"
        assert row["section"] == "BALANCE_SHEET"
        assert row["line_item_code"] == "bsa1"
        assert row["value"] == 100
        assert row["source_name"] == "vietcap_iq"

    def test_check_no_invented_names_passes_with_no_mapping(self):
        facts = _make_facts()
        result = _check_no_invented_names(facts)
        assert all(r["severity"] != "error" for r in result)

    def test_check_no_invented_names_en_passes_with_empty_status(self):
        facts = _make_facts()
        result = _check_no_invented_names_en(facts)
        assert all(r["severity"] != "error" for r in result)


# ---------------------------------------------------------------------------
# 2. Primary lookup hit
# ---------------------------------------------------------------------------


class TestPrimaryLookupHit:
    def test_status_is_primary(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["mapping_status"] == "primary"

    def test_name_en_populated(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["line_item_name_en"] == "Total assets"

    def test_name_vi_populated(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["line_item_name_vi"] == "Tổng tài sản"

    def test_source_symbol_set(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "runX", [])
        assert facts[0]["mapping_source_symbol"] == "VCI"
        assert facts[0]["mapping_source_run_id"] == "runX"

    def test_mapping_conflict_false(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["mapping_conflict"] == "false"

    def test_mapping_group_set(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["mapping_group"] == "securities"

    def test_legacy_line_item_name_still_empty(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["line_item_name"] == ""


# ---------------------------------------------------------------------------
# 3. Primary miss → consensus fallback
# ---------------------------------------------------------------------------


class TestGeneralPrimaryMapping:
    def test_general_symbol_uses_fpt_primary_mapping(self, tmp_path):
        facts = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_FPT["symbol"]: _PLAN_FPT}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "FPT", "runFPT", [])
        assert facts[0]["mapping_status"] == "primary"
        assert facts[0]["mapping_source_symbol"] == "FPT"
        assert facts[0]["mapping_group"] == "general"
        assert facts[0]["line_item_name_en"] == "Total assets"
        assert facts[0]["line_item_name"] == ""

    def test_general_primary_rescues_union_conflict(self, tmp_path):
        facts = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["bsa2"])
        plan = {_PLAN_FPT["symbol"]: _PLAN_FPT}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA2])
        upath = _make_union_csv(tmp_path, [_UNION_CONFLICT])
        apply_mapping_to_facts(
            facts,
            plan,
            load_primary_mapping(ppath),
            "FPT",
            "runFPT",
            load_union_mapping(upath),
        )
        assert facts[0]["mapping_status"] == "primary"
        assert facts[0]["mapping_conflict"] == "false"
        assert facts[0]["line_item_name_en"] == "Cash and cash equivalents"

    def test_general_primary_miss_uses_union_consensus(self, tmp_path):
        facts = _make_facts(symbol="FPT", section="CASH_FLOW", codes=["cfa1"])
        plan = {_PLAN_FPT["symbol"]: _PLAN_FPT}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        upath = _make_union_csv(tmp_path, [_UNION_CFA1])
        apply_mapping_to_facts(
            facts,
            plan,
            load_primary_mapping(ppath),
            "FPT",
            "runFPT",
            load_union_mapping(upath),
        )
        assert facts[0]["mapping_status"] == "consensus_fallback"
        assert facts[0]["mapping_source_symbol"] == "union"
        assert facts[0]["line_item_name_en"] == "Cash from operations"

    def test_general_primary_miss_not_in_union_is_not_covered(self, tmp_path):
        facts = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["PHANTOM"])
        plan = {_PLAN_FPT["symbol"]: _PLAN_FPT}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "FPT", "runFPT", [])
        assert facts[0]["mapping_status"] == "not_covered"
        assert facts[0]["line_item_name_en"] == ""

    def test_general_empty_source_symbol_preserves_union_only_behavior(self, tmp_path):
        facts = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["bsa2"])
        plan = {_PLAN_FPT_UNION_ONLY["symbol"]: _PLAN_FPT_UNION_ONLY}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA2])
        upath = _make_union_csv(tmp_path, [_UNION_CONFLICT])
        apply_mapping_to_facts(
            facts,
            plan,
            load_primary_mapping(ppath),
            "FPT",
            "runFPT",
            load_union_mapping(upath),
        )
        assert facts[0]["mapping_status"] == "conflict_skipped"
        assert facts[0]["line_item_name_en"] == ""


class TestConsensusFallback:
    def test_status_is_consensus_fallback(self, tmp_path):
        # VCI primary has bsa1 only; cfa1 falls through to union
        facts = _make_facts(symbol="VCI", section="CASH_FLOW", codes=["cfa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])  # no cfa1 here
        upath = _make_union_csv(tmp_path, [_UNION_CFA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1",
                                load_union_mapping(upath))
        assert facts[0]["mapping_status"] == "consensus_fallback"

    def test_name_en_from_union(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="CASH_FLOW", codes=["cfa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        upath = _make_union_csv(tmp_path, [_UNION_CFA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1",
                                load_union_mapping(upath))
        assert facts[0]["line_item_name_en"] == "Cash from operations"

    def test_source_symbol_is_union(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="CASH_FLOW", codes=["cfa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        upath = _make_union_csv(tmp_path, [_UNION_CFA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1",
                                load_union_mapping(upath))
        assert facts[0]["mapping_source_symbol"] == "union"
        assert facts[0]["mapping_source_run_id"] == ""

    def test_legacy_line_item_name_still_empty(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="CASH_FLOW", codes=["cfa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        upath = _make_union_csv(tmp_path, [_UNION_CFA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1",
                                load_union_mapping(upath))
        assert facts[0]["line_item_name"] == ""


# ---------------------------------------------------------------------------
# 4. Conflict skipped
# ---------------------------------------------------------------------------


class TestConflictSkipped:
    def _setup(self, tmp_path):
        # Primary has isa1 only; bsa2 falls through to union where conflict=true
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa2"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_ISA1])  # isa1 only
        upath = _make_union_csv(tmp_path, [_UNION_CONFLICT])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1",
                                load_union_mapping(upath))
        return facts

    def test_status_is_conflict_skipped(self, tmp_path):
        facts = self._setup(tmp_path)
        assert facts[0]["mapping_status"] == "conflict_skipped"

    def test_name_en_empty(self, tmp_path):
        facts = self._setup(tmp_path)
        assert facts[0]["line_item_name_en"] == ""

    def test_name_vi_empty(self, tmp_path):
        facts = self._setup(tmp_path)
        assert facts[0]["line_item_name_vi"] == ""

    def test_mapping_conflict_true(self, tmp_path):
        facts = self._setup(tmp_path)
        assert facts[0]["mapping_conflict"] == "true"

    def test_legacy_line_item_name_still_empty(self, tmp_path):
        facts = self._setup(tmp_path)
        assert facts[0]["line_item_name"] == ""


# ---------------------------------------------------------------------------
# 5. Not covered
# ---------------------------------------------------------------------------


class TestNotCovered:
    def test_status_is_not_covered(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["PHANTOM"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["mapping_status"] == "not_covered"

    def test_names_empty_when_not_covered(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["PHANTOM"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["line_item_name_en"] == ""
        assert facts[0]["line_item_name_vi"] == ""

    def test_general_firm_not_in_union_is_not_covered(self, tmp_path):
        # General firm (FPT) code not in union → not_covered (not no_mapping_available)
        facts = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["PHANTOM"])
        plan = {_PLAN_FPT["symbol"]: _PLAN_FPT}
        apply_mapping_to_facts(facts, plan, None, "", "", [])
        assert facts[0]["mapping_status"] == "not_covered"


# ---------------------------------------------------------------------------
# 6. Section mismatch
# ---------------------------------------------------------------------------


class TestSectionMismatch:
    def test_primary_section_mismatch(self, tmp_path):
        # bsa1 is in primary under BALANCE_SHEET; query with INCOME_STATEMENT
        facts = _make_facts(symbol="VCI", section="INCOME_STATEMENT", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["mapping_status"] == "section_mismatch"

    def test_name_empty_on_section_mismatch(self, tmp_path):
        facts = _make_facts(symbol="VCI", section="INCOME_STATEMENT", codes=["bsa1"])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["line_item_name_en"] == ""


# ---------------------------------------------------------------------------
# 7. No primary mapping available (no_mapping_available)
# ---------------------------------------------------------------------------


class TestNoMappingAvailable:
    def test_no_primary_csv_for_non_general_firm(self, tmp_path):
        # VCB (bank) but no primary CSV provided → no_mapping_available
        plan_vcb = {"symbol": "VCB", "mapping_group": "bank",
                    "mapping_source_symbol": "VCB", "proposed_firm_type": "bank"}
        facts = _make_facts(symbol="VCB", section="BALANCE_SHEET", codes=["bsa1"])
        # primary_rows=None with primary_source_symbol != sym_source_symbol → no_mapping_available
        apply_mapping_to_facts(facts, {"VCB": plan_vcb}, None, "VCI", "run1", [])
        assert facts[0]["mapping_status"] == "no_mapping_available"

    def test_names_empty_on_no_mapping_available(self, tmp_path):
        plan_vcb = {"symbol": "VCB", "mapping_group": "bank",
                    "mapping_source_symbol": "VCB", "proposed_firm_type": "bank"}
        facts = _make_facts(symbol="VCB", section="BALANCE_SHEET", codes=["bsa1"])
        apply_mapping_to_facts(facts, {"VCB": plan_vcb}, None, "VCI", "run1", [])
        assert facts[0]["line_item_name_en"] == ""

    def test_general_firm_unknown_code_is_not_covered_not_no_mapping(self):
        facts = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["bsa1"])
        plan = {_PLAN_FPT["symbol"]: _PLAN_FPT}
        apply_mapping_to_facts(facts, plan, None, "", "", [])
        # General firms → has_primary=False → absent from union → not_covered
        assert facts[0]["mapping_status"] == "not_covered"
        assert facts[0]["mapping_status"] != "no_mapping_available"


# ---------------------------------------------------------------------------
# 8. Deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    def test_same_input_same_mapping_output(self, tmp_path):
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1, _PRIMARY_ISA1])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}

        facts1 = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1", "bsa2"])
        apply_mapping_to_facts(facts1, plan, load_primary_mapping(ppath), "VCI", "run1", [])

        facts2 = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1", "bsa2"])
        apply_mapping_to_facts(facts2, plan, load_primary_mapping(ppath), "VCI", "run1", [])

        assert [f["mapping_status"] for f in facts1] == [f["mapping_status"] for f in facts2]
        assert [f["line_item_name_en"] for f in facts1] == [f["line_item_name_en"] for f in facts2]

    def test_column_order_is_deterministic(self):
        cols1 = list(_LONG_FORMAT_COLUMNS)
        cols2 = list(_LONG_FORMAT_COLUMNS)
        assert cols1 == cols2

    def test_all_long_format_columns_present_in_facts(self):
        facts = _make_facts()
        for col in _LONG_FORMAT_COLUMNS:
            assert col in facts[0], f"Column missing from fact row: {col}"


# ---------------------------------------------------------------------------
# 9. No invented names guard
# ---------------------------------------------------------------------------


class TestNoInventedNames:
    def test_empty_status_cannot_have_name(self):
        # Directly build a fact with empty mapping_status but non-empty name
        row = {"line_item_name_en": "Some name", "mapping_status": "",
               "line_item_name": "", "line_item_name_vi": ""}
        result = _check_no_invented_names_en([row])
        assert any(r["severity"] == "error" for r in result)

    def test_not_covered_cannot_have_name(self):
        row = {"line_item_name_en": "Some name", "mapping_status": "not_covered",
               "line_item_name": ""}
        result = _check_no_invented_names_en([row])
        assert any(r["severity"] == "error" for r in result)

    def test_conflict_skipped_cannot_have_name(self):
        row = {"line_item_name_en": "Some name", "mapping_status": "conflict_skipped",
               "line_item_name": ""}
        result = _check_no_invented_names_en([row])
        assert any(r["severity"] == "error" for r in result)

    def test_section_mismatch_cannot_have_name(self):
        row = {"line_item_name_en": "Some name", "mapping_status": "section_mismatch",
               "line_item_name": ""}
        result = _check_no_invented_names_en([row])
        assert any(r["severity"] == "error" for r in result)

    def test_primary_may_have_name(self):
        row = {"line_item_name_en": "Total assets", "mapping_status": "primary",
               "line_item_name": ""}
        result = _check_no_invented_names_en([row])
        assert all(r["severity"] != "error" for r in result)

    def test_consensus_fallback_may_have_name(self):
        row = {"line_item_name_en": "Cash from operations",
               "mapping_status": "consensus_fallback", "line_item_name": ""}
        result = _check_no_invented_names_en([row])
        assert all(r["severity"] != "error" for r in result)

    def test_legacy_line_item_name_always_empty(self, tmp_path):
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        result = _check_no_invented_names(facts)
        assert all(r["severity"] != "error" for r in result)

    def test_unknown_code_gets_no_name(self, tmp_path):
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        facts = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["PHANTOM_CODE"])
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI}
        apply_mapping_to_facts(facts, plan, load_primary_mapping(ppath), "VCI", "run1", [])
        assert facts[0]["line_item_name_en"] == ""


# ---------------------------------------------------------------------------
# 10. Summary output
# ---------------------------------------------------------------------------


class TestSummaryOutput:
    def _make_enriched_facts(self, tmp_path):
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping, load_union_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        upath = _make_union_csv(tmp_path, [_UNION_CFA1, _UNION_CONFLICT])
        plan = {_PLAN_VCI["symbol"]: _PLAN_VCI, _PLAN_FPT["symbol"]: _PLAN_FPT}
        # Mix of: primary(bsa1@BS/VCI), fallback(cfa1@CF/VCI), conflict(bsa2@BS/VCI-via-union), general(FPT)
        facts_vci_bs = _make_facts(symbol="VCI", section="BALANCE_SHEET", codes=["bsa1"])
        facts_vci_cf = _make_facts(symbol="VCI", section="CASH_FLOW", codes=["cfa1"])
        facts_fpt_bs = _make_facts(symbol="FPT", section="BALANCE_SHEET", codes=["cfa1"])
        all_facts = facts_vci_bs + facts_vci_cf + facts_fpt_bs
        apply_mapping_to_facts(all_facts, plan, load_primary_mapping(ppath), "VCI", "run1",
                                load_union_mapping(upath))
        return all_facts

    def test_summary_rows_created(self, tmp_path):
        facts = self._make_enriched_facts(tmp_path)
        summary = build_mapping_summary(facts)
        assert len(summary) > 0

    def test_summary_has_all_columns(self, tmp_path):
        facts = self._make_enriched_facts(tmp_path)
        summary = build_mapping_summary(facts)
        for col in _SUMMARY_COLUMNS:
            assert col in summary[0], f"Missing summary column: {col}"

    def test_summary_counts_correct(self, tmp_path):
        facts = self._make_enriched_facts(tmp_path)
        summary = build_mapping_summary(facts)
        by_key = {(r["symbol"], r["section"]): r for r in summary}
        # VCI BALANCE_SHEET: bsa1 → primary
        assert int(by_key[("VCI", "BALANCE_SHEET")]["primary_count"]) == 1
        # VCI CASH_FLOW: cfa1 → consensus_fallback
        assert int(by_key[("VCI", "CASH_FLOW")]["consensus_fallback_count"]) == 1

    def test_summary_deterministic(self, tmp_path):
        facts = self._make_enriched_facts(tmp_path)
        s1 = build_mapping_summary(facts)
        s2 = build_mapping_summary(facts)
        assert s1 == s2

    def test_summary_written_to_file(self, tmp_path):
        facts = self._make_enriched_facts(tmp_path)
        summary = build_mapping_summary(facts)
        out = tmp_path / "summary.csv"
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=_SUMMARY_COLUMNS)
            w.writeheader()
            w.writerows(summary)
        assert out.exists()
        with open(out, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == len(summary)


# ---------------------------------------------------------------------------
# 11. No DB / no backtest / no network imports or side effects
# ---------------------------------------------------------------------------


class TestNoDBNoBacktestNoNetwork:
    def test_no_httpx_import(self):
        import importlib
        spec = importlib.util.find_spec("parse_vietcap_iq_fa_payloads_dry_run")
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "import httpx" not in source
        assert "import requests" not in source

    def test_no_db_import(self):
        import importlib
        spec = importlib.util.find_spec("parse_vietcap_iq_fa_payloads_dry_run")
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "questdb" not in source.lower()
        for line in source.splitlines():
            s = line.strip()
            if s.startswith("#"):
                continue
            assert ".sqlite" not in s

    def test_no_db_files_written(self, tmp_path):
        facts = _make_facts()
        apply_mapping_to_facts(facts, {}, None, "", "", [])
        assert list(tmp_path.glob("*.db")) == []
        assert list(tmp_path.glob("*.sqlite")) == []

    def test_apply_mapping_has_no_network_call(self):
        facts = _make_facts()
        # Just call it — if it attempted a network call it would raise or hang
        apply_mapping_to_facts(facts, {_PLAN_FPT["symbol"]: _PLAN_FPT}, None, "", "", [])


# ---------------------------------------------------------------------------
# 12. Mapping status consistency check
# ---------------------------------------------------------------------------


class TestMappingStatusConsistency:
    def test_valid_statuses_pass(self):
        facts = [{"mapping_status": s} for s in VALID_MAPPING_STATUSES]
        result = _check_mapping_status_consistency(facts)
        assert all(r["severity"] != "error" for r in result)

    def test_empty_status_passes(self):
        facts = [{"mapping_status": ""}]
        result = _check_mapping_status_consistency(facts)
        assert all(r["severity"] != "error" for r in result)

    def test_invalid_status_raises_error(self):
        facts = [{"mapping_status": "primary_mapped"}]  # old stale name
        result = _check_mapping_status_consistency(facts)
        assert any(r["severity"] == "error" for r in result)

    def test_name_bearing_statuses_constant(self):
        assert "primary" in _NAME_BEARING_STATUSES
        assert "consensus_fallback" in _NAME_BEARING_STATUSES

    def test_non_name_bearing_statuses_constant(self):
        assert "conflict_skipped" in _NON_NAME_BEARING_STATUSES
        assert "not_covered" in _NON_NAME_BEARING_STATUSES
        assert "no_mapping_available" in _NON_NAME_BEARING_STATUSES
        assert "section_mismatch" in _NON_NAME_BEARING_STATUSES


# ---------------------------------------------------------------------------
# 13. Load firm-type plan CSV
# ---------------------------------------------------------------------------


class TestLoadFirmTypePlan:
    def test_loads_by_symbol(self, tmp_path):
        path = _make_firm_plan_csv(tmp_path, [_PLAN_VCI, _PLAN_FPT])
        plan = _load_firm_type_plan(path)
        assert "VCI" in plan
        assert plan["VCI"]["mapping_group"] == "securities"
        assert "FPT" in plan
        assert plan["FPT"]["mapping_group"] == "general"

    def test_skips_empty_symbol_rows(self, tmp_path):
        rows = [{"symbol": "", "mapping_group": "general"}, _PLAN_VCI]
        path = _make_firm_plan_csv(tmp_path, rows)
        plan = _load_firm_type_plan(path)
        assert "" not in plan
        assert "VCI" in plan

    def test_empty_file_returns_empty(self, tmp_path):
        path = _make_firm_plan_csv(tmp_path, [])
        plan = _load_firm_type_plan(path)
        assert plan == {}


# ---------------------------------------------------------------------------
# 14. build_symbol_resolver for different firm types
# ---------------------------------------------------------------------------


class TestBuildSymbolResolver:
    def test_general_firm_has_no_primary(self, tmp_path):
        r = _build_symbol_resolver("FPT", {_PLAN_FPT["symbol"]: _PLAN_FPT}, None, "", "", [])
        assert r is not None
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "not_covered"

    def test_general_firm_with_matching_primary_uses_primary(self, tmp_path):
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        primary_rows = load_primary_mapping(ppath)
        r = _build_symbol_resolver(
            "FPT",
            {_PLAN_FPT["symbol"]: _PLAN_FPT},
            primary_rows,
            "FPT",
            "runFPT",
            [],
        )
        assert r is not None
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "primary"
        assert result.mapping_source_symbol == "FPT"
        assert result.mapping_group == "general"

    def test_securities_firm_with_matching_primary(self, tmp_path):
        from resolve_vietcap_iq_fa_metric_mapping import load_primary_mapping
        ppath = _make_primary_csv(tmp_path, [_PRIMARY_BSA1])
        primary_rows = load_primary_mapping(ppath)
        r = _build_symbol_resolver("VCI", {_PLAN_VCI["symbol"]: _PLAN_VCI},
                                    primary_rows, "VCI", "run1", [])
        assert r is not None
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "primary"

    def test_bank_without_primary_gives_no_mapping_available(self):
        plan_vcb = {"symbol": "VCB", "mapping_group": "bank",
                    "mapping_source_symbol": "VCB", "proposed_firm_type": "bank"}
        r = _build_symbol_resolver("VCB", {"VCB": plan_vcb}, None, "VCI", "run1", [])
        assert r is not None
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "no_mapping_available"

    def test_unknown_symbol_defaults_to_general(self):
        r = _build_symbol_resolver("UNKNOWN", {}, None, "", "", [])
        assert r is not None
        result = r.resolve("BALANCE_SHEET", "bsa1")
        assert result.mapping_status == "not_covered"
