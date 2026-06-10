"""Tests for scripts/plan_vietcap_iq_fa_firm_type_mapping.py.

All tests are offline — no network, no DB, no live probes.
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from plan_vietcap_iq_fa_firm_type_mapping import (
    OUTPUT_COLUMNS,
    _COMPANY_TYPE_TO_GROUP,
    _EXPLICIT_OVERRIDES,
    _GROUP_TO_FALLBACK_POLICY,
    _GROUP_TO_SOURCE_SYMBOL,
    classify_symbol,
    classify_universe,
    load_universe,
    main,
    write_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_universe_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "instrument_universe.csv"
    fieldnames = ["symbol", "company_type_code", "is_bank", "is_index"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return p


# ---------------------------------------------------------------------------
# classify_symbol — explicit overrides
# ---------------------------------------------------------------------------


class TestClassifySymbolExplicitOverrides:
    def test_vci_is_securities(self):
        row = classify_symbol("VCI")
        assert row["mapping_group"] == "securities"
        assert row["confidence"] == "high"
        assert row["mapping_source_symbol"] == "VCI"

    def test_ssi_is_securities(self):
        row = classify_symbol("SSI")
        assert row["mapping_group"] == "securities"

    def test_vcb_is_bank(self):
        row = classify_symbol("VCB")
        assert row["mapping_group"] == "bank"
        assert row["mapping_source_symbol"] == "VCB"

    def test_bvh_is_insurance(self):
        row = classify_symbol("BVH")
        assert row["mapping_group"] == "insurance"
        assert row["mapping_source_symbol"] == "BVH"

    def test_override_takes_precedence_over_metadata(self):
        # Even with wrong metadata, explicit override wins
        row = classify_symbol("VCI", company_type_code="NH", is_bank="True")
        assert row["mapping_group"] == "securities"
        assert row["confidence"] == "high"
        # Should note the disagreement
        assert "NOTE" in row["notes"]


# ---------------------------------------------------------------------------
# classify_symbol — company_type_code path
# ---------------------------------------------------------------------------


class TestClassifySymbolCompanyTypeCode:
    def test_nh_is_bank(self):
        row = classify_symbol("MBB", company_type_code="NH", is_bank="True")
        assert row["mapping_group"] == "bank"
        assert row["confidence"] == "high"
        assert "NH" in row["evidence"]

    def test_bh_is_insurance(self):
        row = classify_symbol("BMI", company_type_code="BH", is_bank="False")
        assert row["mapping_group"] == "insurance"
        assert row["mapping_source_symbol"] == "BVH"

    def test_ck_is_securities(self):
        row = classify_symbol("EVS", company_type_code="CK", is_bank="False")
        assert row["mapping_group"] == "securities"
        assert row["mapping_source_symbol"] == "VCI"

    def test_ct_is_general(self):
        row = classify_symbol("FPT", company_type_code="CT", is_bank="False")
        assert row["mapping_group"] == "general"
        assert row["mapping_source_symbol"] == ""

    def test_qu_is_general(self):
        row = classify_symbol("FUETPVND", company_type_code="QU", is_bank="False")
        assert row["mapping_group"] == "general"
        assert "fund" in row["notes"].lower()

    def test_nh_false_isbank_emits_warning(self):
        row = classify_symbol("XYZ", company_type_code="NH", is_bank="False")
        assert row["mapping_group"] == "bank"
        assert "WARNING" in row["notes"]

    def test_isbank_true_not_nh_emits_warning(self):
        row = classify_symbol("XYZ", company_type_code="CT", is_bank="True")
        assert "WARNING" in row["notes"]

    def test_empty_company_type_code_with_isbank_true(self):
        row = classify_symbol("XYZ", company_type_code="", is_bank="True")
        assert row["mapping_group"] == "bank"
        assert row["confidence"] == "medium"


# ---------------------------------------------------------------------------
# classify_symbol — fallback/default path
# ---------------------------------------------------------------------------


class TestClassifySymbolFallback:
    def test_unknown_symbol_no_metadata_defaults_to_general(self):
        row = classify_symbol("UNKNOWN")
        assert row["mapping_group"] == "general"
        assert row["confidence"] == "none"
        assert row["mapping_source_symbol"] == ""

    def test_unknown_company_type_code_defaults_to_general(self):
        row = classify_symbol("XYZ", company_type_code="XX", is_bank="False")
        assert row["mapping_group"] == "general"
        assert row["confidence"] == "none"

    def test_general_fallback_policy_says_no_primary(self):
        row = classify_symbol("FPT", company_type_code="CT")
        assert "no_primary_mapping" in row["fallback_policy"]

    def test_bank_fallback_policy_says_vcb(self):
        row = classify_symbol("MBB", company_type_code="NH", is_bank="True")
        assert "VCB_mapping" in row["fallback_policy"]

    def test_insurance_fallback_policy_says_bvh(self):
        row = classify_symbol("BMI", company_type_code="BH")
        assert "BVH_mapping" in row["fallback_policy"]


# ---------------------------------------------------------------------------
# classify_symbol — FPT must not be falsely classified as bank/insurance/securities
# ---------------------------------------------------------------------------


class TestFPTNotMisclassified:
    def test_fpt_with_correct_metadata_is_general(self):
        row = classify_symbol("FPT", company_type_code="CT", is_bank="False")
        assert row["mapping_group"] == "general"

    def test_fpt_no_metadata_is_general(self):
        row = classify_symbol("FPT")
        assert row["mapping_group"] == "general"

    def test_fpt_general_has_no_primary_source_symbol(self):
        row = classify_symbol("FPT", company_type_code="CT")
        assert row["mapping_source_symbol"] == ""


# ---------------------------------------------------------------------------
# classify_symbol — output shape
# ---------------------------------------------------------------------------


class TestClassifySymbolOutputShape:
    def test_all_output_columns_present(self):
        row = classify_symbol("VCI")
        for col in OUTPUT_COLUMNS:
            assert col in row, f"Missing column: {col}"

    def test_proposed_firm_type_equals_mapping_group(self):
        for sym, meta in [
            ("VCI", {}),
            ("VCB", {"company_type_code": "NH", "is_bank": "True"}),
            ("FPT", {"company_type_code": "CT"}),
        ]:
            row = classify_symbol(sym, **meta)
            assert row["proposed_firm_type"] == row["mapping_group"]

    def test_notes_is_string(self):
        row = classify_symbol("VCI")
        assert isinstance(row["notes"], str)


# ---------------------------------------------------------------------------
# load_universe
# ---------------------------------------------------------------------------


class TestLoadUniverse:
    def test_loads_key_fields(self, tmp_path):
        p = _make_universe_csv(
            tmp_path,
            [
                {"symbol": "VCI", "company_type_code": "CK", "is_bank": "False"},
                {"symbol": "VCB", "company_type_code": "NH", "is_bank": "True"},
            ],
        )
        u = load_universe(p)
        assert u["VCI"]["company_type_code"] == "CK"
        assert u["VCB"]["is_bank"] == "True"

    def test_skips_empty_symbol(self, tmp_path):
        p = _make_universe_csv(
            tmp_path,
            [
                {"symbol": "", "company_type_code": "CT"},
                {"symbol": "FPT", "company_type_code": "CT"},
            ],
        )
        u = load_universe(p)
        assert "" not in u
        assert "FPT" in u

    def test_missing_columns_default_to_empty(self, tmp_path):
        # Write a CSV that is missing the optional columns
        p = tmp_path / "instrument_universe.csv"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["symbol"])
            writer.writeheader()
            writer.writerow({"symbol": "XYZ"})
        u = load_universe(p)
        assert u["XYZ"]["company_type_code"] == ""
        assert u["XYZ"]["is_bank"] == ""


# ---------------------------------------------------------------------------
# classify_universe
# ---------------------------------------------------------------------------


class TestClassifyUniverse:
    def test_skips_index_rows(self, tmp_path):
        p = _make_universe_csv(
            tmp_path,
            [
                {"symbol": "VCI", "company_type_code": "CK", "is_index": "False"},
                {"symbol": "VNINDEX", "company_type_code": "", "is_index": "True"},
            ],
        )
        u = load_universe(p)
        rows = classify_universe(u)
        syms = [r["symbol"] for r in rows]
        assert "VCI" in syms
        assert "VNINDEX" not in syms

    def test_symbol_filter(self, tmp_path):
        p = _make_universe_csv(
            tmp_path,
            [
                {"symbol": "VCI", "company_type_code": "CK"},
                {"symbol": "FPT", "company_type_code": "CT"},
                {"symbol": "MBB", "company_type_code": "NH", "is_bank": "True"},
            ],
        )
        u = load_universe(p)
        rows = classify_universe(u, symbol_filter=["VCI", "FPT"])
        syms = [r["symbol"] for r in rows]
        assert "VCI" in syms
        assert "FPT" in syms
        assert "MBB" not in syms

    def test_deterministic_output_order(self, tmp_path):
        p = _make_universe_csv(
            tmp_path,
            [
                {"symbol": "ZZZ", "company_type_code": "CT"},
                {"symbol": "AAA", "company_type_code": "CT"},
            ],
        )
        u = load_universe(p)
        rows = classify_universe(u)
        assert rows[0]["symbol"] == "AAA"
        assert rows[1]["symbol"] == "ZZZ"


# ---------------------------------------------------------------------------
# write_output
# ---------------------------------------------------------------------------


class TestWriteOutput:
    def test_writes_all_columns(self, tmp_path):
        rows = [classify_symbol("VCI"), classify_symbol("FPT", company_type_code="CT")]
        out = tmp_path / "out.csv"
        write_output(rows, out)
        with open(out, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            written = list(reader)
        assert len(written) == 2
        for col in OUTPUT_COLUMNS:
            assert col in written[0], f"Missing column: {col}"

    def test_creates_parent_dir(self, tmp_path):
        rows = [classify_symbol("VCI")]
        out = tmp_path / "nested" / "deep" / "out.csv"
        write_output(rows, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------


class TestMain:
    def test_symbols_flag_classifies_known_symbols(self, tmp_path):
        out = tmp_path / "out.csv"
        rc = main(["--symbols", "VCI", "SSI", "VCB", "BVH", "FPT", "--output", str(out)])
        assert rc == 0
        with open(out, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        by_sym = {r["symbol"]: r for r in rows}
        assert by_sym["VCI"]["mapping_group"] == "securities"
        assert by_sym["SSI"]["mapping_group"] == "securities"
        assert by_sym["VCB"]["mapping_group"] == "bank"
        assert by_sym["BVH"]["mapping_group"] == "insurance"
        assert by_sym["FPT"]["mapping_group"] == "general"

    def test_universe_flag(self, tmp_path):
        univ = _make_universe_csv(
            tmp_path,
            [
                {"symbol": "VCI", "company_type_code": "CK", "is_bank": "False"},
                {"symbol": "VCB", "company_type_code": "NH", "is_bank": "True"},
                {"symbol": "BVH", "company_type_code": "BH", "is_bank": "False"},
                {"symbol": "FPT", "company_type_code": "CT", "is_bank": "False"},
            ],
        )
        out = tmp_path / "out.csv"
        rc = main(["--universe", str(univ), "--output", str(out)])
        assert rc == 0
        with open(out, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        by_sym = {r["symbol"]: r for r in rows}
        assert by_sym["VCB"]["mapping_group"] == "bank"
        assert by_sym["BVH"]["mapping_group"] == "insurance"
        assert by_sym["FPT"]["mapping_group"] == "general"

    def test_symbols_and_universe_mutually_exclusive(self, tmp_path):
        univ = _make_universe_csv(tmp_path, [])
        out = tmp_path / "out.csv"
        rc = main(
            ["--symbols", "VCI", "--universe", str(univ), "--output", str(out)]
        )
        assert rc == 1

    def test_missing_universe_file_returns_error(self, tmp_path):
        out = tmp_path / "out.csv"
        rc = main(["--universe", str(tmp_path / "nonexistent.csv"), "--output", str(out)])
        assert rc == 1

    def test_no_flags_returns_error(self, tmp_path):
        out = tmp_path / "out.csv"
        rc = main(["--output", str(out)])
        assert rc == 1

    def test_output_is_deterministically_sorted(self, tmp_path):
        out = tmp_path / "out.csv"
        main(["--symbols", "ZZZ", "AAA", "MMM", "--output", str(out)])
        with open(out, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        syms = [r["symbol"] for r in rows]
        assert syms == sorted(syms)


# ---------------------------------------------------------------------------
# No network / no DB guards
# ---------------------------------------------------------------------------


class TestNoNetworkNoDB:
    def test_no_httpx_import(self):
        import importlib
        spec = importlib.util.find_spec("plan_vietcap_iq_fa_firm_type_mapping")
        assert spec is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "import httpx" not in source
        assert "import requests" not in source

    def test_no_db_import(self):
        import importlib
        spec = importlib.util.find_spec("plan_vietcap_iq_fa_firm_type_mapping")
        source = Path(spec.origin).read_text(encoding="utf-8")
        assert "questdb" not in source.lower()
        assert "sqlite3" not in source
        # No DB file writes — check no .db/.sqlite extension in open() calls
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert ".sqlite" not in stripped, f"sqlite file reference: {stripped!r}"
            if ".db" in stripped:
                assert "DictWriter" in stripped or "DictReader" in stripped, (
                    f"Possible DB file reference: {stripped!r}"
                )

    def test_no_db_file_written(self, tmp_path):
        out = tmp_path / "out.csv"
        main(["--symbols", "VCI", "VCB", "--output", str(out)])
        db_files = list(tmp_path.glob("*.db")) + list(tmp_path.glob("*.sqlite"))
        assert db_files == []


# ---------------------------------------------------------------------------
# Configuration integrity
# ---------------------------------------------------------------------------


class TestConfigIntegrity:
    def test_all_groups_have_source_symbol(self):
        for group in ("bank", "insurance", "securities", "general"):
            assert group in _GROUP_TO_SOURCE_SYMBOL

    def test_all_groups_have_fallback_policy(self):
        for group in ("bank", "insurance", "securities", "general"):
            assert group in _GROUP_TO_FALLBACK_POLICY

    def test_general_source_symbol_is_empty(self):
        assert _GROUP_TO_SOURCE_SYMBOL["general"] == ""

    def test_explicit_overrides_are_consistent_with_group_table(self):
        for sym, group in _EXPLICIT_OVERRIDES.items():
            assert group in _GROUP_TO_SOURCE_SYMBOL, f"{sym}: unknown group {group!r}"

    def test_company_type_codes_all_map_to_valid_groups(self):
        for ctc, group in _COMPANY_TYPE_TO_GROUP.items():
            assert group in _GROUP_TO_SOURCE_SYMBOL, f"{ctc}: unknown group {group!r}"
