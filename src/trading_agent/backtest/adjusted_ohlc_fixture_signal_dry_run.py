from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DRY_RUN_STAGE = "fixture_signal_preview"
SOURCE_PRICE_BASIS = "adjusted_ohlc"
READY_INPUT_STATUS = "ready_for_research_dry_run"

# Deterministic, synthetic fixture signal modes. None of these is a strategy or
# a recommendation. `all_cash` always stays out of the market; the alternating
# mode is a purely synthetic on/off flag for plumbing tests only.
ALL_CASH_MODE = "all_cash"
ALTERNATING_MODE = "alternating_fixture_signal"
ALLOWED_SIGNAL_MODES = (ALL_CASH_MODE, ALTERNATING_MODE)

NO_POSITION = "NO_POSITION"
FIXTURE_ENTER = "FIXTURE_ENTER"
FIXTURE_EXIT = "FIXTURE_EXIT"

REQUIRED_ASSUMPTION_FIELDS = ("transaction_cost_bps", "slippage_bps")


def load_backtest_preparation(path: str | Path) -> dict[str, Any]:
    """Load a PR #49 preparation JSON file without raising on bad input."""
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {"ok": False, "reason": f"preparation_missing:{file_path}", "payload": None}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": "preparation_invalid_json", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "preparation_must_be_object", "payload": None}
    return {"ok": True, "reason": None, "payload": payload}


def validate_preparation_for_fixture_signal(
    payload: dict[str, Any],
    *,
    requested_symbols: list[str],
    signal_mode: str,
    max_rows: int,
) -> list[str]:
    """Return block reasons; empty means the preparation is usable as input."""
    reasons: list[str] = []

    if payload.get("status") != "ok":
        reasons.append(f"preparation_status_not_ok:{payload.get('status')}")
    if payload.get("backtest_input_status") != READY_INPUT_STATUS:
        reasons.append(f"preparation_input_status_not_ready:{payload.get('backtest_input_status')}")
    if payload.get("price_basis") != SOURCE_PRICE_BASIS:
        reasons.append(f"preparation_price_basis_not_adjusted_ohlc:{payload.get('price_basis')}")

    represented = {str(symbol).strip().upper() for symbol in (payload.get("represented_symbols") or [])}
    for symbol in requested_symbols:
        if symbol not in represented:
            reasons.append(f"requested_symbol_missing_from_preparation:{symbol}")

    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, dict) or any(
        assumptions.get(field) is None for field in REQUIRED_ASSUMPTION_FIELDS
    ):
        reasons.append("preparation_assumptions_missing")

    if signal_mode not in ALLOWED_SIGNAL_MODES:
        reasons.append(f"unknown_signal_mode:{signal_mode}")

    try:
        rows = int(max_rows)
    except (TypeError, ValueError):
        rows = 0
    if rows <= 0:
        reasons.append("max_rows_must_be_positive")

    return _dedupe(reasons)


def build_fixture_signal_preview(
    *,
    preparation_path: str | Path,
    symbols: list[str],
    signal_mode: str = ALL_CASH_MODE,
    max_rows: int = 20,
) -> dict[str, Any]:
    requested = _normalize_symbols(symbols)

    reasons: list[str] = []
    if not requested:
        reasons.append("explicit_symbols_required")

    loaded = load_backtest_preparation(preparation_path)
    if not loaded["ok"]:
        reasons.append(str(loaded["reason"]))
        return _result(
            status="blocked",
            requested=requested,
            represented=[],
            signal_mode=signal_mode,
            signal_rows=[],
            reasons=reasons,
        )

    payload = loaded["payload"]
    reasons.extend(
        validate_preparation_for_fixture_signal(
            payload,
            requested_symbols=requested,
            signal_mode=signal_mode,
            max_rows=max_rows,
        )
    )
    reasons = _dedupe(reasons)

    signal_rows: list[dict[str, Any]] = []
    represented: list[str] = []
    if not reasons:
        rows = _select_rows(payload.get("rows_preview") or [], requested, max_rows)
        signal_rows = _build_signal_rows(rows, signal_mode)
        represented = _ordered_symbols(signal_rows, requested)

    status = "ok" if not reasons else "blocked"
    return _result(
        status=status,
        requested=requested,
        represented=represented,
        signal_mode=signal_mode,
        signal_rows=signal_rows,
        reasons=reasons,
    )


def render_fixture_signal_report_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Adjusted OHLC Fixture Signal Dry-Run",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Dry-run stage: `{result.get('dry_run_stage')}`",
        f"- Price basis: `{result.get('price_basis')}`",
        f"- Signal mode: `{result.get('signal_mode')}`",
        f"- Symbols: {', '.join(result.get('symbols') or []) or '(none)'}",
        f"- Row count: {result.get('row_count')}",
        f"- Performance metrics: `{result.get('performance_metrics')}`",
        f"- Not financial advice: `{result.get('not_financial_advice')}`",
        "",
    ]
    reasons = result.get("reasons") or []
    if reasons:
        lines.append("## Blocked Reasons")
        lines.append("")
        lines.extend(f"- `{reason}`" for reason in reasons)
        lines.append("")

    signal_rows = result.get("signal_rows") or []
    if signal_rows:
        lines.append("## Fixture Signal Rows")
        lines.append("")
        lines.append("| symbol | datetime | fixture_signal_action | reason |")
        lines.append("|---|---|---|---|")
        for row in signal_rows:
            lines.append(
                f"| {row.get('symbol')} | {row.get('datetime')} | "
                f"{row.get('fixture_signal_action')} | {row.get('reason')} |"
            )
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
    requested: list[str],
    represented: list[str],
    signal_mode: str,
    signal_rows: list[dict[str, Any]],
    reasons: list[str],
) -> dict[str, Any]:
    caveats = [
        "Fixture signal preview only; deterministic and synthetic.",
        "No Backtrader, optimizer, or full VN100.",
        "No performance metrics and no engine execution.",
        "No investment advice; not a trading suggestion.",
    ]
    return {
        "status": status,
        "dry_run_stage": DRY_RUN_STAGE,
        "price_basis": SOURCE_PRICE_BASIS,
        "signal_mode": signal_mode,
        "symbols": requested,
        "requested_symbols": requested,
        "represented_symbols": represented,
        "missing_symbols": [symbol for symbol in requested if symbol not in represented],
        "row_count": len(signal_rows),
        "signal_rows": signal_rows,
        "performance_metrics": None,
        "reasons": reasons,
        "caveats": caveats,
        "not_financial_advice": True,
    }


def _build_signal_rows(rows: list[dict[str, Any]], signal_mode: str) -> list[dict[str, Any]]:
    signal_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if signal_mode == ALTERNATING_MODE:
            action = FIXTURE_ENTER if index % 2 == 0 else FIXTURE_EXIT
            reason = "research_fixture_alternating"
        else:
            action = NO_POSITION
            reason = "research_fixture_all_cash"
        signal_rows.append(
            {
                "symbol": str(row.get("symbol") or "").strip().upper(),
                "datetime": row.get("datetime"),
                "fixture_signal_action": action,
                "reason": reason,
            }
        )
    return signal_rows


def _select_rows(rows: list[Any], requested: list[str], max_rows: int) -> list[dict[str, Any]]:
    requested_set = set(requested)
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if requested_set and symbol not in requested_set:
            continue
        selected.append(row)
        if len(selected) >= int(max_rows):
            break
    return selected


def _ordered_symbols(rows: list[dict[str, Any]], requested: list[str]) -> list[str]:
    present = {str(row.get("symbol") or "").strip().upper() for row in rows}
    return [symbol for symbol in requested if symbol in present]


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
