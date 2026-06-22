from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPORT_STAGE = "fixture_diagnostic_metrics"
SOURCE_PRICE_BASIS = "adjusted_ohlc"
FIXTURE_SIGNAL_STAGE = "fixture_signal_preview"
NO_POSITION = "NO_POSITION"

# Real trading actions are not allowed in a fixture diagnostic report.
FORBIDDEN_ACTIONS = ("BUY", "SELL", "HOLD")

# Performance / profitability fields must never leak into a fixture diagnostic
# report. This layer proves reporting plumbing only; it is not strategy
# performance and must not compute Sharpe, Sortino, PnL, equity, etc.
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


def load_fixture_signal_preview(path: str | Path) -> dict[str, Any]:
    """Load a PR #50 fixture signal JSON file without raising on bad input."""
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {"ok": False, "reason": f"fixture_signal_missing:{file_path}", "payload": None}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": "fixture_signal_invalid_json", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "fixture_signal_must_be_object", "payload": None}
    return {"ok": True, "reason": None, "payload": payload}


def validate_fixture_signal_for_metrics(
    payload: dict[str, Any],
    *,
    requested_symbols: list[str],
) -> list[str]:
    """Return block reasons; empty means the fixture signal is usable as input."""
    reasons: list[str] = []

    if payload.get("status") != "ok":
        reasons.append(f"fixture_signal_status_not_ok:{payload.get('status')}")
    if payload.get("dry_run_stage") != FIXTURE_SIGNAL_STAGE:
        reasons.append(f"fixture_signal_stage_invalid:{payload.get('dry_run_stage')}")
    if payload.get("price_basis") != SOURCE_PRICE_BASIS:
        reasons.append(f"fixture_price_basis_not_adjusted_ohlc:{payload.get('price_basis')}")
    if payload.get("not_financial_advice") is not True:
        reasons.append("fixture_not_financial_advice_missing")
    if payload.get("performance_metrics") is not None:
        reasons.append("fixture_performance_metrics_must_be_null")

    signal_rows = payload.get("signal_rows")
    if not isinstance(signal_rows, list) or not signal_rows:
        reasons.append("signal_rows_missing")
        signal_rows = []

    represented = {str(symbol).strip().upper() for symbol in (payload.get("represented_symbols") or [])}
    row_symbols = {str(row.get("symbol") or "").strip().upper() for row in signal_rows if isinstance(row, dict)}
    covered = represented | row_symbols
    for symbol in requested_symbols:
        if symbol not in covered:
            reasons.append(f"requested_symbol_missing:{symbol}")

    for row in signal_rows:
        if not isinstance(row, dict):
            reasons.append("signal_row_not_object")
            continue
        action = str(row.get("fixture_signal_action") or "").strip().upper()
        if action in FORBIDDEN_ACTIONS:
            reasons.append(f"forbidden_action_present:{action}")
        for field in FORBIDDEN_ROW_FIELDS:
            if field in row:
                reasons.append(f"forbidden_row_field_present:{field}")

    return _dedupe(reasons)


def compute_fixture_diagnostic_metrics(
    payload: dict[str, Any],
    requested_symbols: list[str],
) -> dict[str, Any]:
    """Deterministic fixture diagnostics only. No profitability metrics."""
    signal_rows = [row for row in (payload.get("signal_rows") or []) if isinstance(row, dict)]
    actions = [str(row.get("fixture_signal_action") or "").strip().upper() for row in signal_rows]
    dates = sorted(str(row.get("datetime")) for row in signal_rows if row.get("datetime"))
    symbols = {str(row.get("symbol") or "").strip().upper() for row in signal_rows}
    row_count = len(signal_rows)
    no_position = sum(1 for action in actions if action == NO_POSITION)
    return {
        "row_count": row_count,
        "symbol_count": len(symbols),
        "signal_action_counts": dict(sorted(Counter(actions).items())),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "fixture_no_position_ratio": round(no_position / row_count, 6) if row_count else None,
        "input_price_basis": payload.get("price_basis"),
    }


def build_fixture_metrics_report(
    *,
    fixture_signal_path: str | Path,
    symbols: list[str],
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)

    reasons: list[str] = []
    if not requested:
        reasons.append("explicit_symbols_required")

    loaded = load_fixture_signal_preview(fixture_signal_path)
    if not loaded["ok"]:
        reasons.append(str(loaded["reason"]))
        return _result(status="blocked", symbols=requested, metrics={}, reasons=reasons)

    payload = loaded["payload"]
    reasons.extend(validate_fixture_signal_for_metrics(payload, requested_symbols=requested))
    reasons = _dedupe(reasons)

    metrics: dict[str, Any] = {}
    if not reasons:
        metrics = compute_fixture_diagnostic_metrics(payload, requested)

    status = "ok" if not reasons else "blocked"
    return _result(status=status, symbols=requested, metrics=metrics, reasons=reasons)


def render_fixture_metrics_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Adjusted OHLC Fixture Diagnostic Metrics",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Report stage: `{result.get('report_stage')}`",
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

    metrics = result.get("diagnostic_metrics") or {}
    if metrics:
        lines.append("## Fixture Diagnostic Metrics")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|---|---|")
        for key, value in metrics.items():
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
    metrics: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    forbidden_present = any(
        reason.startswith("forbidden_row_field_present:")
        or reason.startswith("forbidden_action_present:")
        or reason == "fixture_performance_metrics_must_be_null"
        for reason in reasons
    )
    caveats = [
        "Fixture diagnostics only; not strategy performance.",
        "No profitability or risk-performance metrics are computed.",
        "No Backtrader, optimizer, engine call, or full VN100.",
        "No investment advice and no production-readiness claim.",
    ]
    return {
        "status": status,
        "report_stage": REPORT_STAGE,
        "price_basis": SOURCE_PRICE_BASIS,
        "symbols": symbols,
        "diagnostic_metrics": metrics,
        "forbidden_performance_metrics_present": forbidden_present,
        "reasons": reasons,
        "caveats": caveats,
        "not_financial_advice": True,
    }


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
