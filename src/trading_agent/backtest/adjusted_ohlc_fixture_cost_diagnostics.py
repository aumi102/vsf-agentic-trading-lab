from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DIAGNOSTIC_STAGE = "fixture_cost_slippage_diagnostics"
ROUNDTRIP_STAGE = "fixture_roundtrip_engine"
PRICE_BASIS = "adjusted_ohlc"
PREP_READY_STATUS = "ready_for_research_dry_run"
EXCHANGE_BANDS_BPS = {"HOSE": 700, "HSX": 700, "UPCOM": 1500}
FORBIDDEN_KEYS = {
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
    "trades",
    "trade_list",
}


def load_json_object(path: str | Path, label: str) -> dict[str, Any]:
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


def validate_cost_diagnostic_inputs(
    preparation: dict[str, Any],
    roundtrip: dict[str, Any],
    *,
    requested_symbols: list[str],
    max_rows: int,
) -> list[str]:
    reasons: list[str] = []
    if preparation.get("status") != "ok":
        reasons.append(f"preparation_status_not_ok:{preparation.get('status')}")
    if preparation.get("backtest_input_status") != PREP_READY_STATUS:
        reasons.append(f"preparation_input_status_not_ready:{preparation.get('backtest_input_status')}")
    if preparation.get("price_basis") != PRICE_BASIS:
        reasons.append(f"preparation_price_basis_not_adjusted_ohlc:{preparation.get('price_basis')}")
    if preparation.get("not_financial_advice") is not True:
        reasons.append("preparation_not_financial_advice_missing")

    assumptions = preparation.get("assumptions")
    if not isinstance(assumptions, dict):
        assumptions = {}
    transaction_cost = _nonnegative_number(assumptions.get("transaction_cost_bps"))
    slippage = _nonnegative_number(assumptions.get("slippage_bps"))
    band = _nonnegative_number(assumptions.get("slippage_band_bps"))
    exchange = str(assumptions.get("exchange") or "").strip().upper()
    if "transaction_cost_bps" not in assumptions:
        reasons.append("transaction_cost_bps_missing")
    elif transaction_cost is None:
        reasons.append("transaction_cost_bps_must_be_nonnegative")
    if "slippage_bps" not in assumptions:
        reasons.append("slippage_bps_missing")
    elif slippage is None:
        reasons.append("slippage_bps_must_be_nonnegative")
    if not exchange:
        reasons.append("exchange_missing")
    if "slippage_band_bps" not in assumptions:
        reasons.append("slippage_band_bps_missing")
    elif band is None:
        reasons.append("slippage_band_bps_must_be_nonnegative")
    expected_band = EXCHANGE_BANDS_BPS.get(exchange)
    if exchange and expected_band is None:
        reasons.append(f"unknown_exchange:{exchange}")
    elif band is not None and expected_band is not None and band != expected_band:
        reasons.append(f"slippage_band_bps_mismatch:{band}/{expected_band}")
    if slippage is not None and band is not None and slippage > band:
        reasons.append(f"slippage_bps_exceeds_exchange_band:{slippage}/{band}")

    if roundtrip.get("status") != "ok":
        reasons.append(f"roundtrip_status_not_ok:{roundtrip.get('status')}")
    if roundtrip.get("engine_stage") != ROUNDTRIP_STAGE:
        reasons.append(f"roundtrip_engine_stage_invalid:{roundtrip.get('engine_stage')}")
    if roundtrip.get("price_basis") != PRICE_BASIS:
        reasons.append(f"roundtrip_price_basis_not_adjusted_ohlc:{roundtrip.get('price_basis')}")
    if roundtrip.get("not_financial_advice") is not True:
        reasons.append("roundtrip_not_financial_advice_missing")
    if roundtrip.get("forbidden_performance_metrics_present") is not False:
        reasons.append("roundtrip_forbidden_performance_metrics_present")
    for key in sorted(_find_forbidden_keys(roundtrip)):
        reasons.append(f"forbidden_roundtrip_field_present:{key}")

    preparation_symbols = _upper_set(preparation.get("represented_symbols"))
    roundtrip_symbols = _upper_set(roundtrip.get("symbols"))
    for symbol in requested_symbols:
        if symbol not in preparation_symbols or symbol not in roundtrip_symbols:
            reasons.append(f"requested_symbol_missing:{symbol}")

    try:
        rows = int(max_rows)
    except (TypeError, ValueError):
        rows = 0
    if rows <= 0:
        reasons.append("max_rows_must_be_positive")

    counts = ((roundtrip.get("roundtrip_diagnostics") or {}).get("state_transition_counts") or {})
    for name in ("fixture_enter_count", "fixture_exit_count"):
        value = counts.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            reasons.append(f"roundtrip_transition_count_invalid:{name}")
    return _dedupe(reasons)


def compute_fixture_cost_diagnostics(
    *,
    preparation_path: str | Path,
    roundtrip_path: str | Path,
    symbols: list[str],
    max_rows: int = 20,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)
    reasons = [] if requested else ["explicit_symbols_required"]
    preparation_loaded = load_json_object(preparation_path, "preparation")
    roundtrip_loaded = load_json_object(roundtrip_path, "roundtrip")
    for loaded in (preparation_loaded, roundtrip_loaded):
        if not loaded["ok"]:
            reasons.append(str(loaded["reason"]))
    if reasons:
        return _result("blocked", requested, {}, reasons)

    preparation = preparation_loaded["payload"]
    roundtrip = roundtrip_loaded["payload"]
    reasons = validate_cost_diagnostic_inputs(
        preparation,
        roundtrip,
        requested_symbols=requested,
        max_rows=max_rows,
    )
    diagnostics: dict[str, Any] = {}
    if not reasons:
        assumptions = preparation["assumptions"]
        counts = roundtrip["roundtrip_diagnostics"]["state_transition_counts"]
        event_count = counts["fixture_enter_count"] + counts["fixture_exit_count"]
        transaction_cost = assumptions["transaction_cost_bps"]
        slippage = assumptions["slippage_bps"]
        total_transaction = event_count * transaction_cost
        total_slippage = event_count * slippage
        diagnostics = {
            "estimated_cost_event_count": event_count,
            "estimated_slippage_event_count": event_count,
            "transaction_cost_bps": transaction_cost,
            "slippage_bps": slippage,
            "exchange": assumptions["exchange"],
            "slippage_band_bps": assumptions["slippage_band_bps"],
            "total_transaction_cost_bps_units": total_transaction,
            "total_slippage_bps_units": total_slippage,
            "total_friction_bps_units": total_transaction + total_slippage,
        }
    return _result("ok" if not reasons else "blocked", requested, diagnostics, reasons)


def render_fixture_cost_diagnostics_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Adjusted OHLC Fixture Cost/Slippage Diagnostics",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Diagnostic stage: `{result.get('diagnostic_stage')}`",
        f"- Price basis: `{result.get('price_basis')}`",
        f"- Symbols: {', '.join(result.get('symbols') or []) or '(none)'}",
        f"- Not financial advice: `{result.get('not_financial_advice')}`",
        "",
    ]
    reasons = result.get("reasons") or []
    if reasons:
        lines.extend(["## Blocked Reasons", ""])
        lines.extend(f"- `{reason}`" for reason in reasons)
        lines.append("")
    diagnostics = result.get("cost_diagnostics") or {}
    if diagnostics:
        lines.extend(["## Bps-Units Diagnostics", "", "| diagnostic | value |", "|---|---|"])
        lines.extend(f"| {key} | {value} |" for key, value in diagnostics.items())
        lines.append("")
    lines.extend(["## Caveats", ""])
    lines.extend(f"- {caveat}" for caveat in result.get("caveats") or [])
    lines.append("")
    return "\n".join(lines)


def _result(status: str, symbols: list[str], diagnostics: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "diagnostic_stage": DIAGNOSTIC_STAGE,
        "price_basis": PRICE_BASIS,
        "symbols": symbols,
        "cost_diagnostics": diagnostics,
        "not_financial_advice": True,
        "forbidden_performance_metrics_present": any(
            reason.startswith("forbidden_roundtrip_field_present:")
            or reason == "roundtrip_forbidden_performance_metrics_present"
            for reason in reasons
        ),
        "reasons": _dedupe(reasons),
        "caveats": ["Fixture cost/slippage diagnostics only; not PnL or returns."],
    }


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_KEYS:
                found.add(normalized)
            found.update(_find_forbidden_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_find_forbidden_keys(nested))
    return found


def _nonnegative_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value


def _upper_set(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value).strip().upper() for value in values}


def _normalize_symbols(symbols: list[str]) -> list[str]:
    return list(dict.fromkeys(str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
