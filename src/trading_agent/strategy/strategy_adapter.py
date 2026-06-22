from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading_agent.strategy.strategy_contract import (
    load_strategy_contract,
    validate_strategy_contract_file,
)


ADAPTER_STAGE = "strategy_adapter_preview"
PRICE_BASIS = "adjusted_ohlc"
PREPARED_STATUS = "ready_for_research_dry_run"


def load_json_object(path: str | Path, label: str) -> dict[str, Any]:
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {"ok": False, "reason": f"{label}_missing", "payload": None}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": f"{label}_invalid_json", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": f"{label}_must_be_object", "payload": None}
    return {"ok": True, "reason": None, "payload": payload}


def run_strategy_adapter_preview(
    *,
    contract_path: str | Path,
    prepared_input_path: str | Path,
) -> dict[str, Any]:
    contract_validation = validate_strategy_contract_file(contract_path)
    if contract_validation["status"] != "ok":
        reasons = [f"contract_not_ready:{contract_validation['status']}"]
        reasons.extend(str(reason) for reason in contract_validation.get("reasons") or [])
        return _result(None, [], [], reasons)

    contract_loaded = load_strategy_contract(contract_path)
    if not contract_loaded["ok"]:
        return _result(None, [], [], [str(contract_loaded["reason"])])
    contract = contract_loaded["payload"]
    symbols = _normalize_symbols(contract.get("symbols"))

    prepared_loaded = load_json_object(prepared_input_path, "prepared_input")
    if not prepared_loaded["ok"]:
        return _result(contract.get("strategy_id"), symbols, [], [str(prepared_loaded["reason"])])
    prepared = prepared_loaded["payload"]
    reasons = _validate_prepared_input(prepared, symbols)
    if reasons:
        return _result(contract.get("strategy_id"), symbols, [], reasons)

    intent_rows = [
        {
            "symbol": str(row["symbol"]).strip().upper(),
            "datetime": row.get("datetime"),
            "signal_intent_action": "NO_SIGNAL",
            "reason": "noop_adapter_interface_only",
        }
        for row in prepared["rows_preview"]
        if isinstance(row, dict) and str(row.get("symbol") or "").strip().upper() in symbols
    ]
    return _result(contract.get("strategy_id"), symbols, intent_rows, [])


def _validate_prepared_input(prepared: dict[str, Any], symbols: list[str]) -> list[str]:
    reasons: list[str] = []
    if prepared.get("status") != "ok":
        reasons.append(f"prepared_input_status_not_ok:{prepared.get('status')}")
    if prepared.get("backtest_input_status") != PREPARED_STATUS:
        reasons.append(f"prepared_input_not_ready:{prepared.get('backtest_input_status')}")
    if prepared.get("price_basis") != PRICE_BASIS:
        reasons.append(f"prepared_input_price_basis_not_adjusted_ohlc:{prepared.get('price_basis')}")
    prepared_symbols = set(_normalize_symbols(prepared.get("represented_symbols")))
    for symbol in symbols:
        if symbol not in prepared_symbols:
            reasons.append(f"prepared_input_symbol_missing:{symbol}")
    rows = prepared.get("rows_preview")
    if not isinstance(rows, list) or not rows:
        reasons.append("prepared_input_rows_missing")
    else:
        row_symbols = {
            str(row.get("symbol") or "").strip().upper()
            for row in rows
            if isinstance(row, dict)
        }
        for symbol in symbols:
            if symbol not in row_symbols:
                reasons.append(f"prepared_input_symbol_row_missing:{symbol}")
    return list(dict.fromkeys(reasons))


def _result(strategy_id: Any, symbols: list[str], rows: list[dict[str, Any]], reasons: list[str]) -> dict[str, Any]:
    return {
        "status": "ok" if not reasons else "blocked",
        "adapter_stage": ADAPTER_STAGE,
        "strategy_id": strategy_id,
        "price_basis": PRICE_BASIS,
        "symbols": symbols,
        "signal_intent_rows": rows,
        "not_financial_advice": True,
        "reasons": reasons,
        "caveats": ["No-op adapter preview only; not strategy performance."],
    }


def _normalize_symbols(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value or "").strip().upper() for value in values if str(value or "").strip()))
