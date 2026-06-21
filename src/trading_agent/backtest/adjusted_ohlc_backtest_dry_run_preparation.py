from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


FEED_CONTRACT_VERSION = "adjusted_ohlc_feed_v1"
SOURCE_PRICE_BASIS = "adjusted_ohlc"
DRY_RUN_STAGE = "backtest_input_preparation"
READY_STATUS = "ready_for_research_dry_run"
FIXTURE_SIGNAL_LABEL = "research_fixture_signal"

# Exchange daily price bands. Slippage assumptions must stay within these bands.
EXCHANGE_SLIPPAGE_BANDS_BPS = {
    "HOSE": 700,
    "HSX": 700,
    "UPCOM": 1500,
}

REQUIRED_ROW_PRICE_FIELDS = ("open", "high", "low", "close", "volume")

# Fields that must never appear in a backtest input row. Raw OHLC must not be
# reused as a trading price, and no signal/trade/performance field may leak into
# the prepared input.
FORBIDDEN_ROW_FIELDS = (
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "signal",
    "signal_action",
    "signal_id",
    "trade",
    "trade_id",
    "action",
    "pnl",
    "equity",
    "portfolio_value",
    "return",
    "sharpe",
    "strategy",
    "strategy_id",
)

_ALLOWED_ROW_FIELDS = (
    "symbol",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source_price_basis",
    "adjustment_factor",
    "adjustment_source_id",
    "adjustment_raw_path",
    "adjustment_method",
)


def load_feed_preview(path: str | Path) -> dict[str, Any]:
    """Load a PR #48 feed preview JSON file without raising on bad input."""
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {"ok": False, "reason": f"feed_preview_missing:{file_path}", "payload": None}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": "feed_preview_invalid_json", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "feed_preview_must_be_object", "payload": None}
    return {"ok": True, "reason": None, "payload": payload}


def validate_feed_preview_for_backtest(
    payload: dict[str, Any],
    *,
    requested_symbols: list[str],
    start_date: str | None,
    end_date: str | None,
    transaction_cost_bps: float,
    slippage_bps: float,
    exchange: str,
    max_rows: int,
) -> list[str]:
    """Return a list of block reasons; empty means the feed preview is usable."""
    reasons: list[str] = []

    if payload.get("status") != "ok":
        reasons.append(f"feed_status_not_ok:{payload.get('status')}")
    if payload.get("feed_contract_version") != FEED_CONTRACT_VERSION:
        reasons.append(f"feed_contract_version_mismatch:{payload.get('feed_contract_version')}")
    if payload.get("source_price_basis") != SOURCE_PRICE_BASIS:
        reasons.append(f"feed_source_price_basis_not_adjusted_ohlc:{payload.get('source_price_basis')}")

    feed_symbols = {str(symbol).strip().upper() for symbol in (payload.get("symbols") or [])}
    for symbol in requested_symbols:
        if symbol not in feed_symbols:
            reasons.append(f"requested_symbol_missing_from_feed:{symbol}")

    reasons.extend(_validate_date_and_rows(start_date, end_date, max_rows))
    reasons.extend(_validate_assumptions(transaction_cost_bps, slippage_bps, exchange))
    reasons.extend(_validate_rows(payload.get("rows") or []))

    return _dedupe(reasons)


def build_backtest_input_preview(
    *,
    feed_preview_path: str | Path,
    symbols: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_cost_bps: float,
    slippage_bps: float,
    exchange: str,
    max_rows: int = 20,
    fixture_signal_mode: bool = False,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    exchange_key = str(exchange or "").strip().upper()
    slippage_band = EXCHANGE_SLIPPAGE_BANDS_BPS.get(exchange_key)
    assumptions = {
        "transaction_cost_bps": transaction_cost_bps,
        "slippage_bps": slippage_bps,
        "exchange": exchange,
        "slippage_band_bps": slippage_band,
    }

    reasons: list[str] = []
    if not requested:
        reasons.append("explicit_symbols_required")

    loaded = load_feed_preview(feed_preview_path)
    if not loaded["ok"]:
        reasons.append(str(loaded["reason"]))
        return _result(
            status="blocked",
            requested=requested,
            represented=[],
            assumptions=assumptions,
            rows_preview=[],
            reasons=reasons,
            fixture_signal_mode=fixture_signal_mode,
        )

    payload = loaded["payload"]
    reasons.extend(
        validate_feed_preview_for_backtest(
            payload,
            requested_symbols=requested,
            start_date=start_date,
            end_date=end_date,
            transaction_cost_bps=transaction_cost_bps,
            slippage_bps=slippage_bps,
            exchange=exchange,
            max_rows=max_rows,
        )
    )
    reasons = _dedupe(reasons)

    rows_preview: list[dict[str, Any]] = []
    represented: list[str] = []
    if not reasons:
        # Structural and assumption checks passed. Now confirm every requested
        # symbol survives the date-range filter and the max_rows limit, so a
        # prepared input never silently drops a requested symbol.
        filtered = _filter_rows(payload.get("rows") or [], requested, start_date, end_date)
        represented_after_filter = _ordered_symbols(filtered, requested)
        for symbol in requested:
            if symbol not in represented_after_filter:
                reasons.append(f"prepared_input_missing_symbol_after_filter:{symbol}")

        limited = filtered[: int(max_rows)]
        represented_after_limit = _ordered_symbols(limited, requested)
        for symbol in requested:
            if symbol in represented_after_filter and symbol not in represented_after_limit:
                reasons.append(f"prepared_input_missing_symbol_after_limit:{symbol}")

        reasons = _dedupe(reasons)
        represented = represented_after_limit
        if not reasons:
            rows_preview = [_clean_row(row) for row in limited]

    status = "ok" if not reasons else "blocked"
    return _result(
        status=status,
        requested=requested,
        represented=represented,
        assumptions=assumptions,
        rows_preview=rows_preview,
        reasons=reasons,
        fixture_signal_mode=fixture_signal_mode,
    )


def prepare_fixture_signal_dry_run() -> dict[str, Any]:
    """Deterministic, research-only fixture signal placeholder.

    This does not run any engine, produce trades, or make a performance or
    recommendation claim. It only labels a deterministic all-cash intent.
    """
    return {
        "mode": FIXTURE_SIGNAL_LABEL,
        "deterministic_plan": "all_cash",
        "executes_engine": False,
        "produces_performance": False,
        "note": "Deterministic all-cash research fixture only; not a recommendation.",
    }


def _result(
    *,
    status: str,
    requested: list[str],
    represented: list[str],
    assumptions: dict[str, Any],
    rows_preview: list[dict[str, Any]],
    reasons: list[str],
    fixture_signal_mode: bool,
) -> dict[str, Any]:
    caveats = [
        "Preparation only; no Backtrader execution.",
        "No optimizer and no full VN100.",
        "No live trading and no broker execution.",
        "No investment advice and no performance claim.",
    ]
    missing_symbols = [symbol for symbol in requested if symbol not in represented]
    return {
        "status": status,
        "dry_run_stage": DRY_RUN_STAGE,
        "backtest_input_status": READY_STATUS if status == "ok" else "blocked",
        "price_basis": SOURCE_PRICE_BASIS,
        "symbols": requested,
        "requested_symbols": requested,
        "represented_symbols": represented,
        "missing_symbols": missing_symbols,
        "row_count": len(rows_preview),
        "assumptions": assumptions,
        "rows_preview": rows_preview,
        "fixture_signal": prepare_fixture_signal_dry_run() if fixture_signal_mode else None,
        "reasons": reasons,
        "caveats": caveats,
        "not_financial_advice": True,
    }


def _validate_assumptions(transaction_cost_bps: float, slippage_bps: float, exchange: str) -> list[str]:
    reasons: list[str] = []
    if not _is_number(transaction_cost_bps) or float(transaction_cost_bps) < 0:
        reasons.append("transaction_cost_bps_must_be_non_negative")
    if not _is_number(slippage_bps) or float(slippage_bps) < 0:
        reasons.append("slippage_bps_must_be_non_negative")
    exchange_key = str(exchange or "").strip().upper()
    band = EXCHANGE_SLIPPAGE_BANDS_BPS.get(exchange_key)
    if band is None:
        reasons.append(f"unknown_exchange:{exchange}")
    elif _is_number(slippage_bps) and float(slippage_bps) > band:
        reasons.append(f"slippage_bps_exceeds_exchange_band:{slippage_bps}/{band}")
    return reasons


def _validate_rows(rows: list[Any]) -> list[str]:
    reasons: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            reasons.append("feed_row_not_object")
            continue
        for field in REQUIRED_ROW_PRICE_FIELDS:
            if row.get(field) is None:
                reasons.append(f"row_missing_price_field:{field}")
        for field in FORBIDDEN_ROW_FIELDS:
            if field in row:
                reasons.append(f"forbidden_row_field:{field}")
        if "source_price_basis" in row and row.get("source_price_basis") != SOURCE_PRICE_BASIS:
            reasons.append(f"row_source_price_basis_not_adjusted_ohlc:{row.get('source_price_basis')}")
    return _dedupe(reasons)


def _validate_date_and_rows(
    start_date: str | None,
    end_date: str | None,
    max_rows: int,
) -> list[str]:
    reasons: list[str] = []
    if start_date is not None and not _is_iso_date(start_date):
        reasons.append(f"invalid_start_date_format:{start_date}")
    if end_date is not None and not _is_iso_date(end_date):
        reasons.append(f"invalid_end_date_format:{end_date}")
    if (
        start_date is not None
        and end_date is not None
        and _is_iso_date(start_date)
        and _is_iso_date(end_date)
        and start_date > end_date
    ):
        reasons.append("invalid_date_range:start_after_end")
    try:
        rows = int(max_rows)
    except (TypeError, ValueError):
        reasons.append("max_rows_must_be_positive")
        return reasons
    if rows <= 0:
        reasons.append("max_rows_must_be_positive")
    return reasons


def _filter_rows(
    rows: list[Any],
    requested: list[str],
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    """Keep only requested-symbol rows inside the date range (ISO order)."""
    requested_set = set(requested)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if requested_set and symbol not in requested_set:
            continue
        datetime_value = str(row.get("datetime") or "")
        if start_date and datetime_value and datetime_value < start_date:
            continue
        if end_date and datetime_value and datetime_value > end_date:
            continue
        filtered.append(row)
    return filtered


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in _ALLOWED_ROW_FIELDS if field in row}


def _ordered_symbols(rows: list[dict[str, Any]], requested: list[str]) -> list[str]:
    present = {str(row.get("symbol") or "").strip().upper() for row in rows}
    return [symbol for symbol in requested if symbol in present]


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
    except (TypeError, ValueError):
        return False
    return True


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in symbols:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
