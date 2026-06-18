from __future__ import annotations

import math
from typing import Any


def compute_adjustment_factor(close: float, adjusted_close: float | None) -> dict[str, Any]:
    """Compute an OHLC adjustment factor from close and adjusted close."""
    close_value = _to_float(close)
    adjusted_close_value = _to_float(adjusted_close)
    reasons: list[str] = []

    if close_value is None:
        reasons.append("close_missing")
    elif close_value <= 0:
        reasons.append("close_must_be_positive")

    if adjusted_close_value is None:
        reasons.append("adjusted_close_missing")
        status = "missing"
    elif adjusted_close_value <= 0:
        reasons.append("adjusted_close_must_be_positive")
        status = "invalid"
    else:
        status = "invalid" if reasons else "ok"

    if reasons:
        return {"status": status, "factor": None, "reasons": sorted(set(reasons))}

    factor = adjusted_close_value / close_value
    if factor <= 0:
        return {"status": "invalid", "factor": factor, "reasons": ["factor_must_be_positive"]}
    return {"status": "ok", "factor": factor, "reasons": []}


def adjust_ohlc(
    open_: float,
    high: float,
    low: float,
    close: float,
    factor: float,
) -> dict[str, Any]:
    """Apply a positive adjustment factor to all OHLC fields."""
    factor_value = _to_float(factor)
    reasons: list[str] = []
    values = {
        "open": _to_float(open_),
        "high": _to_float(high),
        "low": _to_float(low),
        "close": _to_float(close),
    }
    for field, value in values.items():
        if value is None:
            reasons.append(f"{field}_missing")
    if factor_value is None:
        reasons.append("factor_missing")
    elif factor_value <= 0:
        reasons.append("factor_must_be_positive")

    if reasons:
        return {
            "status": "invalid",
            "adjusted_open": None,
            "adjusted_high": None,
            "adjusted_low": None,
            "adjusted_close": None,
            "reasons": sorted(set(reasons)),
        }

    adjusted = {
        "adjusted_open": values["open"] * factor_value,
        "adjusted_high": values["high"] * factor_value,
        "adjusted_low": values["low"] * factor_value,
        "adjusted_close": values["close"] * factor_value,
    }
    validation_reasons = validate_adjusted_ohlc(
        adjusted["adjusted_open"],
        adjusted["adjusted_high"],
        adjusted["adjusted_low"],
        adjusted["adjusted_close"],
        factor_value,
    )
    return {
        "status": "ok" if not validation_reasons else "invalid",
        **adjusted,
        "reasons": validation_reasons,
    }


def validate_adjusted_ohlc(
    adjusted_open: float | None,
    adjusted_high: float | None,
    adjusted_low: float | None,
    adjusted_close: float | None,
    factor: float | None,
) -> list[str]:
    """Return validation errors for an adjusted OHLC row."""
    reasons: list[str] = []
    open_value = _to_float(adjusted_open)
    high_value = _to_float(adjusted_high)
    low_value = _to_float(adjusted_low)
    close_value = _to_float(adjusted_close)
    factor_value = _to_float(factor)

    values = {
        "adjusted_open": open_value,
        "adjusted_high": high_value,
        "adjusted_low": low_value,
        "adjusted_close": close_value,
    }
    for field, value in values.items():
        if value is None:
            reasons.append(f"{field}_missing")

    if factor_value is None:
        reasons.append("factor_missing")
    elif factor_value <= 0:
        reasons.append("factor_must_be_positive")

    if reasons:
        return sorted(set(reasons))

    if high_value < max(open_value, close_value):
        reasons.append("adjusted_high_below_open_or_close")
    if low_value > min(open_value, close_value):
        reasons.append("adjusted_low_above_open_or_close")
    if high_value < low_value:
        reasons.append("adjusted_high_below_low")
    return sorted(set(reasons))


def _to_float(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result
