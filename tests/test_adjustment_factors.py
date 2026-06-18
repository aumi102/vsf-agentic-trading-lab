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


def test_adjustment_factor_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjustment_factors.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_adjustment_factor_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/adjustment_factors.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)
