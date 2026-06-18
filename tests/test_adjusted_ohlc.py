from __future__ import annotations

import math
from pathlib import Path

from trading_agent.ingestion.adjusted_ohlc import (
    adjust_ohlc,
    compute_adjustment_factor,
    validate_adjusted_ohlc,
)


def test_factor_is_adjusted_close_divided_by_close() -> None:
    result = compute_adjustment_factor(100.0, 80.0)

    assert result == {"status": "ok", "factor": 0.8, "reasons": []}


def test_adjust_ohlc_scales_all_ohlc_values() -> None:
    result = adjust_ohlc(100.0, 110.0, 90.0, 105.0, 0.8)

    assert result["status"] == "ok"
    assert result["adjusted_open"] == 80.0
    assert result["adjusted_high"] == 88.0
    assert result["adjusted_low"] == 72.0
    assert result["adjusted_close"] == 84.0
    assert result["reasons"] == []


def test_factor_one_keeps_values_unchanged() -> None:
    result = adjust_ohlc(100.0, 110.0, 90.0, 105.0, 1.0)

    assert result["status"] == "ok"
    assert result["adjusted_open"] == 100.0
    assert result["adjusted_high"] == 110.0
    assert result["adjusted_low"] == 90.0
    assert result["adjusted_close"] == 105.0


def test_missing_adjusted_close_returns_missing_status() -> None:
    result = compute_adjustment_factor(100.0, None)

    assert result == {
        "status": "missing",
        "factor": None,
        "reasons": ["adjusted_close_missing"],
    }


def test_close_not_positive_blocks_factor() -> None:
    result = compute_adjustment_factor(0.0, 80.0)

    assert result == {
        "status": "invalid",
        "factor": None,
        "reasons": ["close_must_be_positive"],
    }


def test_adjusted_close_not_positive_blocks_factor() -> None:
    result = compute_adjustment_factor(100.0, 0.0)

    assert result == {
        "status": "invalid",
        "factor": None,
        "reasons": ["adjusted_close_must_be_positive"],
    }


def test_non_finite_values_block_factor() -> None:
    assert compute_adjustment_factor(math.inf, 80.0) == {
        "status": "invalid",
        "factor": None,
        "reasons": ["close_missing"],
    }
    assert compute_adjustment_factor(100.0, math.nan) == {
        "status": "missing",
        "factor": None,
        "reasons": ["adjusted_close_missing"],
    }


def test_factor_not_positive_is_invalid() -> None:
    result = adjust_ohlc(100.0, 110.0, 90.0, 105.0, 0.0)

    assert result["status"] == "invalid"
    assert result["reasons"] == ["factor_must_be_positive"]
    assert result["adjusted_close"] is None


def test_missing_ohlc_values_are_invalid() -> None:
    result = adjust_ohlc(None, 110.0, None, 105.0, 0.8)

    assert result["status"] == "invalid"
    assert result["reasons"] == ["low_missing", "open_missing"]
    assert result["adjusted_open"] is None


def test_adjusted_high_low_consistency_passes() -> None:
    assert validate_adjusted_ohlc(80.0, 88.0, 72.0, 84.0, 0.8) == []


def test_inconsistent_adjusted_high_low_returns_errors() -> None:
    reasons = validate_adjusted_ohlc(80.0, 70.0, 90.0, 84.0, 0.8)

    assert reasons == [
        "adjusted_high_below_low",
        "adjusted_high_below_open_or_close",
        "adjusted_low_above_open_or_close",
    ]


def test_adjusted_ohlc_module_has_no_network_or_db_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_ohlc.py").read_text(encoding="utf-8")

    blocked_imports = ["sqlite3", "requests", "httpx", "urllib", "sqlalchemy"]
    assert all(name not in source for name in blocked_imports)


def test_adjusted_requirement_doc_says_gap_chart_adjusted_fields_are_empty() -> None:
    text = Path("docs/backtest/adjusted_ohlc_backtest_requirement.md").read_text(encoding="utf-8")

    assert "gap-chart ingestion keeps these fields" in text
    assert "without claiming raw prices are adjusted" in text
