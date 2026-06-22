from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


PRICE_BASIS = "adjusted_ohlc"
APPROVAL_STATUSES = {"pending", "approved", "rejected"}
EXCHANGE_BANDS_BPS = {"HOSE": 700, "HSX": 700, "UPCOM": 1500}
REQUIRED_FIELDS = (
    "strategy_id",
    "strategy_family",
    "symbols",
    "date_range",
    "price_basis",
    "entry_rule",
    "exit_rule",
    "rebalance_rule",
    "execution_price",
    "transaction_cost_bps",
    "slippage_bps",
    "exchange",
    "slippage_band_bps",
    "position_sizing",
    "risk_rule",
    "lookahead_policy",
    "mentor_approval_status",
)


def load_strategy_contract(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path)
    try:
        raw = contract_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {"ok": False, "reason": "contract_missing", "payload": None}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ok": False, "reason": "contract_invalid_json", "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "contract_must_be_object", "payload": None}
    return {"ok": True, "reason": None, "payload": payload}


def validate_strategy_contract(contract: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in contract:
            reasons.append(f"required_field_missing:{field}")

    if contract.get("price_basis") != PRICE_BASIS:
        reasons.append(f"price_basis_not_adjusted_ohlc:{contract.get('price_basis')}")

    symbols = contract.get("symbols")
    if not isinstance(symbols, list) or not any(str(symbol or "").strip() for symbol in symbols):
        reasons.append("symbols_must_be_nonempty")

    if not _valid_date_range(contract.get("date_range")):
        reasons.append("date_range_invalid")

    transaction_cost = _nonnegative_number(contract.get("transaction_cost_bps"))
    slippage = _nonnegative_number(contract.get("slippage_bps"))
    band = _nonnegative_number(contract.get("slippage_band_bps"))
    if "transaction_cost_bps" in contract and transaction_cost is None:
        reasons.append("transaction_cost_bps_must_be_nonnegative")
    if "slippage_bps" in contract and slippage is None:
        reasons.append("slippage_bps_must_be_nonnegative")
    if "slippage_band_bps" in contract and band is None:
        reasons.append("slippage_band_bps_must_be_nonnegative")

    exchange = str(contract.get("exchange") or "").strip().upper()
    expected_band = EXCHANGE_BANDS_BPS.get(exchange)
    if "exchange" in contract and expected_band is None:
        reasons.append(f"unknown_exchange:{exchange}")
    if band is not None and expected_band is not None and band != expected_band:
        reasons.append(f"slippage_band_bps_mismatch:{band}/{expected_band}")
    if slippage is not None and band is not None and slippage > band:
        reasons.append(f"slippage_bps_exceeds_exchange_band:{slippage}/{band}")

    approval = str(contract.get("mentor_approval_status") or "").strip().lower()
    if "mentor_approval_status" in contract and approval not in APPROVAL_STATUSES:
        reasons.append(f"mentor_approval_status_invalid:{approval}")

    for field in (
        "strategy_id",
        "strategy_family",
        "entry_rule",
        "exit_rule",
        "rebalance_rule",
        "execution_price",
        "position_sizing",
        "risk_rule",
        "lookahead_policy",
    ):
        if field in contract and not str(contract.get(field) or "").strip():
            reasons.append(f"required_field_empty:{field}")
    return list(dict.fromkeys(reasons))


def validate_strategy_contract_file(path: str | Path) -> dict[str, Any]:
    loaded = load_strategy_contract(path)
    if not loaded["ok"]:
        return _result("blocked", None, [str(loaded["reason"])])
    contract = loaded["payload"]
    reasons = validate_strategy_contract(contract)
    if reasons:
        return _result("blocked", contract, reasons)
    approval = str(contract["mentor_approval_status"]).strip().lower()
    if approval != "approved":
        return _result("not_ready", contract, [f"mentor_approval_not_approved:{approval}"])
    return _result("ok", contract, [])


def _result(status: str, contract: dict[str, Any] | None, reasons: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "validation_stage": "strategy_contract_validation",
        "strategy_id": contract.get("strategy_id") if contract else None,
        "price_basis": contract.get("price_basis") if contract else None,
        "mentor_approval_status": contract.get("mentor_approval_status") if contract else None,
        "reasons": reasons,
        "caveats": [
            "Contract validation only; no strategy or Backtrader execution.",
            "Small-symbol adjusted-OHLC research only after mentor approval.",
            "No performance claim and no investment advice.",
        ],
        "not_financial_advice": True,
    }


def _valid_date_range(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        start = date.fromisoformat(str(value.get("start") or ""))
        end = date.fromisoformat(str(value.get("end") or ""))
    except ValueError:
        return False
    return start <= end


def _nonnegative_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value
