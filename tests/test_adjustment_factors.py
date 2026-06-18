from __future__ import annotations

from pathlib import Path

import pytest

from trading_agent.ingestion.adjustment_factors import (
    AdjustmentFactorRecord,
    make_adjustment_factor_record,
    merge_factor_records,
    normalize_adjusted_close_factor,
    normalize_corporate_action_factor,
)


def test_adjusted_close_ratio_factor() -> None:
    record = normalize_adjusted_close_factor(
        symbol="fpt",
        trade_date="2026-01-02",
        raw_close=100.0,
        adjusted_close=80.0,
        source_id="trusted:payload",
        raw_path="raw/fpt.json",
    )

    assert record.symbol == "FPT"
    assert record.method == "adjusted_close_ratio"
    assert record.status == "ok"
    assert record.factor == 0.8
    assert record.reasons == ()


def test_factor_must_be_positive() -> None:
    record = normalize_corporate_action_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        factor=0,
        source_id="corp:event",
        raw_path="raw/corp.json",
    )

    assert record.status == "invalid"
    assert record.factor is None
    assert "factor_must_be_positive" in record.reasons


def test_missing_adjusted_close_is_explicit() -> None:
    record = normalize_adjusted_close_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        raw_close=100.0,
        adjusted_close=None,
        source_id="trusted:payload",
        raw_path="raw/fpt.json",
    )

    assert record.status == "missing"
    assert record.factor is None
    assert record.reasons == ("adjusted_close_missing",)


def test_missing_source_id_or_raw_path_blocks_usable_status() -> None:
    record = normalize_adjusted_close_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        raw_close=100.0,
        adjusted_close=80.0,
        source_id="",
        raw_path=None,
    )

    assert record.status == "invalid"
    assert record.factor == 0.8
    assert record.reasons == ("raw_path_required", "source_id_required")


def test_method_enum_validation() -> None:
    with pytest.raises(ValueError, match="Unsupported adjustment factor method"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="2026-01-02",
            factor=1.0,
            source_id="source",
            method="raw_close_is_adjusted",
            raw_path="raw.json",
            status="ok",
        )


def test_ok_record_requires_non_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol is required"):
        make_adjustment_factor_record(
            symbol=" ",
            trade_date="2026-01-02",
            factor=1.0,
            source_id="source",
            method="adjusted_close_ratio",
            raw_path="raw.json",
            status="ok",
        )


def test_ok_record_requires_non_empty_trade_date() -> None:
    with pytest.raises(ValueError, match="trade_date is required"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="",
            factor=1.0,
            source_id="source",
            method="adjusted_close_ratio",
            raw_path="raw.json",
            status="ok",
        )


def test_unknown_method_cannot_be_ok() -> None:
    with pytest.raises(ValueError, match="method_cannot_be_unknown"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="2026-01-02",
            factor=1.0,
            source_id="source",
            method="unknown",
            raw_path="raw.json",
            status="ok",
        )


def test_ok_record_requires_factor_provenance_and_no_reasons() -> None:
    with pytest.raises(ValueError, match="factor_must_be_positive"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="2026-01-02",
            factor=float("nan"),
            source_id="source",
            method="adjusted_close_ratio",
            raw_path="raw.json",
            status="ok",
        )
    with pytest.raises(ValueError, match="source_id_required"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="2026-01-02",
            factor=1.0,
            source_id="",
            method="adjusted_close_ratio",
            raw_path="raw.json",
            status="ok",
        )
    with pytest.raises(ValueError, match="raw_path_required"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="2026-01-02",
            factor=1.0,
            source_id="source",
            method="adjusted_close_ratio",
            raw_path="",
            status="ok",
        )
    with pytest.raises(ValueError, match="ok_record_cannot_have_reasons"):
        make_adjustment_factor_record(
            symbol="FPT",
            trade_date="2026-01-02",
            factor=1.0,
            source_id="source",
            method="adjusted_close_ratio",
            raw_path="raw.json",
            status="ok",
            reasons=["manual_reason"],
        )


def test_adjusted_close_ratio_rejects_non_finite_values() -> None:
    close_record = normalize_adjusted_close_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        raw_close=float("inf"),
        adjusted_close=80.0,
        source_id="trusted:payload",
        raw_path="raw/fpt.json",
    )
    adjusted_record = normalize_adjusted_close_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        raw_close=100.0,
        adjusted_close=float("nan"),
        source_id="trusted:payload",
        raw_path="raw/fpt.json",
    )

    assert close_record.status == "invalid"
    assert "raw_close_missing_or_non_finite" in close_record.reasons
    assert adjusted_record.status == "missing"
    assert "adjusted_close_missing" in adjusted_record.reasons


def test_corporate_action_factor_rejects_non_finite_factor() -> None:
    record = normalize_corporate_action_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        factor=float("nan"),
        source_id="corp:event",
        raw_path="raw/corp.json",
    )

    assert record.status == "missing"
    assert record.factor is None
    assert "factor_missing_or_non_finite" in record.reasons


def test_merge_deduplicates_and_prefers_usable_record() -> None:
    invalid = AdjustmentFactorRecord(
        symbol="FPT",
        trade_date="2026-01-02",
        factor=0.8,
        source_id=None,
        method="adjusted_close_ratio",
        raw_path=None,
        status="invalid",
        reasons=("source_id_required",),
    )
    usable = normalize_adjusted_close_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        raw_close=100.0,
        adjusted_close=80.0,
        source_id="trusted:payload",
        raw_path="raw/fpt.json",
    )

    assert merge_factor_records([invalid, usable, usable]) == [usable]


def test_merge_prefers_ok_then_missing_then_invalid() -> None:
    missing = AdjustmentFactorRecord(
        symbol="FPT",
        trade_date="2026-01-02",
        factor=None,
        source_id="source",
        method="adjusted_close_ratio",
        raw_path="raw.json",
        status="missing",
        reasons=("adjusted_close_missing",),
    )
    invalid = AdjustmentFactorRecord(
        symbol="FPT",
        trade_date="2026-01-02",
        factor=None,
        source_id="source",
        method="adjusted_close_ratio",
        raw_path="raw.json",
        status="invalid",
        reasons=("factor_must_be_positive",),
    )
    usable = normalize_adjusted_close_factor(
        symbol="FPT",
        trade_date="2026-01-02",
        raw_close=100.0,
        adjusted_close=80.0,
        source_id="source",
        raw_path="raw.json",
    )

    assert merge_factor_records([invalid, missing]) == [missing]
    assert merge_factor_records([invalid, missing, usable]) == [usable]


def test_adjustment_factor_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjustment_factors.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_adjustment_factor_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/adjustment_factors.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)


def test_source_review_uses_tracked_evidence_language() -> None:
    text = Path("docs/data_platform/adjusted_factor_source_review.md").read_text(encoding="utf-8")

    assert "tracked repo code, parser tests, and docs only" in text
    assert "No tracked fixture currently proves" in text
    assert "tracked gap-chart field" in text
