from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ENGINE_STAGE = "fixture_roundtrip_engine"
SOURCE_PRICE_BASIS = "adjusted_ohlc"
PREP_READY_STATUS = "ready_for_research_dry_run"
SIGNAL_STAGE = "fixture_signal_preview"
METRICS_STAGE = "fixture_diagnostic_metrics"

# Only deterministic, synthetic fixture actions are allowed. These are NOT
# buy/sell/hold and carry no trading meaning.
ALLOWED_ACTIONS = ("NO_POSITION", "FIXTURE_ENTER", "FIXTURE_EXIT")
FORBIDDEN_ACTIONS = ("BUY", "SELL", "HOLD")

STATE_OUT = "OUT"
STATE_IN = "IN_FIXTURE"

# Performance / profitability fields must never leak into the round-trip engine.
# This layer proves engine/reporting plumbing only; it is not strategy
# performance and must not compute PnL, equity, returns, Sharpe, drawdown, etc.
FORBIDDEN_ROW_FIELDS = (
    "pnl",
    "trade_pnl",
    "equity",
    "equity_curve",
    "portfolio_value",
    "return",
    "returns",
    "sharpe",
    "sortino",
    "profit_factor",
    "max_drawdown",
    "drawdown",
    "win_rate",
    "alpha",
    "performance",
)


def load_json_object(path: str | Path, label: str) -> dict[str, Any]:
    """Load a JSON object file without raising on bad input."""
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {"ok": False, "reason": f"{label}_missing", "payload": None}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": f"json_invalid:{label}", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": f"json_must_be_object:{label}", "payload": None}
    return {"ok": True, "reason": None, "payload": payload}


def validate_roundtrip_inputs(
    preparation: dict[str, Any],
    fixture_signal: dict[str, Any],
    fixture_metrics: dict[str, Any],
    *,
    requested_symbols: list[str],
    max_rows: int,
) -> list[str]:
    """Return block reasons; empty means the three inputs are usable."""
    reasons: list[str] = []

    # --- Preparation (PR #49) ---
    if preparation.get("status") != "ok":
        reasons.append(f"preparation_status_not_ok:{preparation.get('status')}")
    if preparation.get("backtest_input_status") != PREP_READY_STATUS:
        reasons.append(f"preparation_input_status_not_ready:{preparation.get('backtest_input_status')}")
    if preparation.get("price_basis") != SOURCE_PRICE_BASIS:
        reasons.append(f"preparation_price_basis_not_adjusted_ohlc:{preparation.get('price_basis')}")
    if preparation.get("not_financial_advice") is not True:
        reasons.append("preparation_not_financial_advice_missing")
    prep_symbols = _upper_set(preparation.get("represented_symbols"))
    for symbol in requested_symbols:
        if symbol not in prep_symbols:
            reasons.append(f"requested_symbol_missing:{symbol}")

    # --- Fixture signal (PR #50) ---
    if fixture_signal.get("status") != "ok":
        reasons.append(f"signal_status_not_ok:{fixture_signal.get('status')}")
    if fixture_signal.get("dry_run_stage") != SIGNAL_STAGE:
        reasons.append(f"fixture_signal_stage_invalid:{fixture_signal.get('dry_run_stage')}")
    if fixture_signal.get("price_basis") != SOURCE_PRICE_BASIS:
        reasons.append(f"fixture_signal_price_basis_not_adjusted_ohlc:{fixture_signal.get('price_basis')}")
    if fixture_signal.get("not_financial_advice") is not True:
        reasons.append("fixture_signal_not_financial_advice_missing")
    if fixture_signal.get("performance_metrics") is not None:
        reasons.append("signal_performance_metrics_must_be_null")

    signal_rows = fixture_signal.get("signal_rows")
    if not isinstance(signal_rows, list) or not signal_rows:
        reasons.append("signal_rows_missing")
        signal_rows = []

    signal_symbols = {
        str(row.get("symbol") or "").strip().upper()
        for row in signal_rows
        if isinstance(row, dict)
    }
    signal_symbols |= _upper_set(fixture_signal.get("represented_symbols"))
    for symbol in requested_symbols:
        if symbol not in signal_symbols:
            reasons.append(f"requested_symbol_missing:{symbol}")

    for row in signal_rows:
        if not isinstance(row, dict):
            reasons.append("signal_row_not_object")
            continue
        action = str(row.get("fixture_signal_action") or "").strip().upper()
        if action in FORBIDDEN_ACTIONS:
            reasons.append(f"forbidden_action_present:{action}")
        elif action not in ALLOWED_ACTIONS:
            reasons.append(f"unknown_fixture_action:{action}")
        for field in FORBIDDEN_ROW_FIELDS:
            if field in row:
                reasons.append(f"forbidden_row_field_present:{field}")

    # --- Fixture metrics (PR #51) ---
    if fixture_metrics.get("status") != "ok":
        reasons.append(f"metrics_status_not_ok:{fixture_metrics.get('status')}")
    if fixture_metrics.get("report_stage") != METRICS_STAGE:
        reasons.append(f"fixture_metrics_stage_invalid:{fixture_metrics.get('report_stage')}")
    if fixture_metrics.get("price_basis") != SOURCE_PRICE_BASIS:
        reasons.append(f"fixture_metrics_price_basis_not_adjusted_ohlc:{fixture_metrics.get('price_basis')}")
    if fixture_metrics.get("not_financial_advice") is not True:
        reasons.append("fixture_metrics_not_financial_advice_missing")
    if fixture_metrics.get("forbidden_performance_metrics_present") is not False:
        reasons.append("metrics_forbidden_performance_metrics_present")
    metrics_symbols = _upper_set(fixture_metrics.get("symbols"))
    for symbol in requested_symbols:
        if symbol not in metrics_symbols:
            reasons.append(f"requested_symbol_missing:{symbol}")

    # --- General ---
    try:
        rows = int(max_rows)
    except (TypeError, ValueError):
        rows = 0
    if rows <= 0:
        reasons.append("max_rows_must_be_positive")

    return _dedupe(reasons)


def run_fixture_roundtrip_engine(
    *,
    preparation_path: str | Path,
    fixture_signal_path: str | Path,
    fixture_metrics_path: str | Path,
    symbols: list[str],
    max_rows: int = 20,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)

    reasons: list[str] = []
    if not requested:
        reasons.append("explicit_symbols_required")

    prep_loaded = load_json_object(preparation_path, "preparation")
    signal_loaded = load_json_object(fixture_signal_path, "fixture_signal")
    metrics_loaded = load_json_object(fixture_metrics_path, "fixture_metrics")
    for loaded in (prep_loaded, signal_loaded, metrics_loaded):
        if not loaded["ok"]:
            reasons.append(str(loaded["reason"]))
    if reasons:
        return _result(status="blocked", symbols=requested, diagnostics={}, reasons=reasons)

    preparation = prep_loaded["payload"]
    fixture_signal = signal_loaded["payload"]
    fixture_metrics = metrics_loaded["payload"]

    reasons.extend(
        validate_roundtrip_inputs(
            preparation,
            fixture_signal,
            fixture_metrics,
            requested_symbols=requested,
            max_rows=max_rows,
        )
    )
    reasons = _dedupe(reasons)

    diagnostics: dict[str, Any] = {}
    if not reasons:
        diagnostics = _compute_roundtrip_diagnostics(preparation, fixture_signal, max_rows)

    status = "ok" if not reasons else "blocked"
    return _result(status=status, symbols=requested, diagnostics=diagnostics, reasons=reasons)


def _compute_roundtrip_diagnostics(
    preparation: dict[str, Any],
    fixture_signal: dict[str, Any],
    max_rows: int,
) -> dict[str, Any]:
    all_rows = [row for row in (fixture_signal.get("signal_rows") or []) if isinstance(row, dict)]
    processed = all_rows[: int(max_rows)]

    actions = [str(row.get("fixture_signal_action") or "").strip().upper() for row in processed]
    dates = sorted(str(row.get("datetime")) for row in processed if row.get("datetime"))

    state: dict[str, str] = {}
    fixture_enter_count = 0
    fixture_exit_count = 0
    duplicate_enter_count = 0
    unmatched_exit_count = 0
    for row in processed:
        symbol = str(row.get("symbol") or "").strip().upper()
        action = str(row.get("fixture_signal_action") or "").strip().upper()
        current = state.get(symbol, STATE_OUT)
        if action == "FIXTURE_ENTER":
            if current == STATE_OUT:
                state[symbol] = STATE_IN
                fixture_enter_count += 1
            else:
                duplicate_enter_count += 1
        elif action == "FIXTURE_EXIT":
            if current == STATE_IN:
                state[symbol] = STATE_OUT
                fixture_exit_count += 1
            else:
                unmatched_exit_count += 1
        # NO_POSITION: no state change.

    open_fixture_state_count = sum(1 for value in state.values() if value == STATE_IN)

    input_row_count = (
        int(preparation.get("row_count"))
        if isinstance(preparation.get("row_count"), int)
        else len([r for r in (preparation.get("rows_preview") or []) if isinstance(r, dict)])
    )
    signal_row_count = (
        int(fixture_signal.get("row_count"))
        if isinstance(fixture_signal.get("row_count"), int)
        else len(all_rows)
    )

    return {
        "input_row_count": input_row_count,
        "signal_row_count": signal_row_count,
        "processed_row_count": len(processed),
        "action_counts": dict(sorted(Counter(actions).items())),
        "state_transition_counts": {
            "fixture_enter_count": fixture_enter_count,
            "fixture_exit_count": fixture_exit_count,
            "duplicate_enter_count": duplicate_enter_count,
            "unmatched_exit_count": unmatched_exit_count,
            "open_fixture_state_count": open_fixture_state_count,
        },
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "input_price_basis": fixture_signal.get("price_basis"),
        "assumptions": _echo_assumptions(preparation.get("assumptions")),
    }


def render_fixture_roundtrip_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Adjusted OHLC Fixture Round-Trip Engine",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Engine stage: `{result.get('engine_stage')}`",
        f"- Price basis: `{result.get('price_basis')}`",
        f"- Symbols: {', '.join(result.get('symbols') or []) or '(none)'}",
        f"- Forbidden performance metrics present: `{result.get('forbidden_performance_metrics_present')}`",
        f"- Not financial advice: `{result.get('not_financial_advice')}`",
        "",
    ]
    reasons = result.get("reasons") or []
    if reasons:
        lines.append("## Blocked Reasons")
        lines.append("")
        lines.extend(f"- `{reason}`" for reason in reasons)
        lines.append("")

    diagnostics = result.get("roundtrip_diagnostics") or {}
    if diagnostics:
        lines.append("## Round-Trip Diagnostics")
        lines.append("")
        lines.append("| diagnostic | value |")
        lines.append("|---|---|")
        for key, value in diagnostics.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

    caveats = result.get("caveats") or []
    if caveats:
        lines.append("## Caveats")
        lines.append("")
        lines.extend(f"- {caveat}" for caveat in caveats)
        lines.append("")
    return "\n".join(lines)


def _result(
    *,
    status: str,
    symbols: list[str],
    diagnostics: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    forbidden_present = any(
        reason.startswith("forbidden_row_field_present:")
        or reason.startswith("forbidden_action_present:")
        or reason.endswith("_performance_metrics_must_be_null")
        or reason == "metrics_forbidden_performance_metrics_present"
        for reason in reasons
    )
    caveats = [
        "Fixture round-trip diagnostics only; not strategy performance.",
        "No profitability or risk-performance metrics are computed.",
        "No Backtrader, optimizer, engine optimization, or full VN100.",
        "No investment advice and no production-readiness claim.",
    ]
    return {
        "status": status,
        "engine_stage": ENGINE_STAGE,
        "price_basis": SOURCE_PRICE_BASIS,
        "symbols": symbols,
        "roundtrip_diagnostics": diagnostics,
        "forbidden_performance_metrics_present": forbidden_present,
        "reasons": reasons,
        "caveats": caveats,
        "not_financial_advice": True,
    }


def _echo_assumptions(assumptions: Any) -> dict[str, Any]:
    if not isinstance(assumptions, dict):
        return {}
    keys = ("transaction_cost_bps", "slippage_bps", "exchange", "slippage_band_bps")
    return {key: assumptions.get(key) for key in keys if key in assumptions}


def _upper_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value).strip().upper() for value in values}


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
