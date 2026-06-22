from __future__ import annotations

from datetime import date
from typing import Any


DECISION_STAGE = "mentor_decision_capture"
PENDING_APPROVAL = "pending"
PRICE_BASIS = "adjusted_ohlc"
STRATEGY_FAMILIES = (
    "moving_average",
    "momentum",
    "breakout",
    "mean_reversion",
)
EXCHANGE_BANDS_BPS = {"HOSE": 700, "HSX": 700, "UPCOM": 1500}
REQUIRED_DECISION_FIELDS = (
    "strategy_family",
    "universe",
    "symbols",
    "date_range",
    "execution_price",
    "transaction_cost_bps",
    "slippage_bps",
    "exchange",
    "rebalance_rule",
    "risk_rule",
    "position_sizing",
    "max_holding_period",
)
DRAFT_CAVEAT = (
    "Draft only; mentor approval must be recorded manually before validation can return ok."
)
DEMO_TALK_TRACK = (
    "This UI captures mentor decisions into a pending contract draft. "
    "It does not approve the contract, enable a family, run a strategy, "
    "compute performance, or provide investment advice."
)


def get_decision_fields() -> list[dict[str, Any]]:
    return [
        _field("strategy_family", "Strategy family", "select", options=list(STRATEGY_FAMILIES)),
        _field("universe", "Universe", "text"),
        _field("symbols", "Symbols", "symbols"),
        _field("date_range", "Date range", "date_range"),
        _field("execution_price", "Execution price", "text"),
        _field("transaction_cost_bps", "Transaction cost (bps)", "number"),
        _field("slippage_bps", "Slippage (bps)", "number"),
        _field("exchange", "Exchange", "select", options=list(EXCHANGE_BANDS_BPS)),
        _field("rebalance_rule", "Rebalance rule", "text"),
        _field("risk_rule", "Risk rule", "text"),
        _field("position_sizing", "Position sizing", "text"),
        _field("max_holding_period", "Max holding period", "text"),
    ]


def get_demo_talk_track() -> dict[str, Any]:
    return {
        "status": "ok",
        "talk_track": DEMO_TALK_TRACK,
        "not_financial_advice": True,
    }


def validate_decision_completeness(decisions: dict[str, Any]) -> dict[str, Any]:
    payload = decisions if isinstance(decisions, dict) else {}
    missing_fields = [
        field for field in REQUIRED_DECISION_FIELDS if not _has_value(payload.get(field))
    ]
    invalid_fields: list[str] = []

    family = str(payload.get("strategy_family") or "").strip().lower()
    if family and family not in STRATEGY_FAMILIES:
        invalid_fields.append("strategy_family")
    if _has_value(payload.get("symbols")) and not _normalize_symbols(payload.get("symbols")):
        invalid_fields.append("symbols")
    if _has_value(payload.get("date_range")) and not _valid_date_range(payload.get("date_range")):
        invalid_fields.append("date_range")
    for field in ("transaction_cost_bps", "slippage_bps"):
        if _has_value(payload.get(field)) and _nonnegative_number(payload.get(field)) is None:
            invalid_fields.append(field)
    exchange = str(payload.get("exchange") or "").strip().upper()
    if exchange and exchange not in EXCHANGE_BANDS_BPS:
        invalid_fields.append("exchange")

    ready = not missing_fields and not invalid_fields
    return {
        "status": "draft_ready" if ready else "not_ready",
        "decision_stage": DECISION_STAGE,
        "missing_fields": missing_fields,
        "invalid_fields": list(dict.fromkeys(invalid_fields)),
        "mentor_approval_status": PENDING_APPROVAL,
    }


def build_pending_contract_draft(decisions: dict[str, Any]) -> dict[str, Any]:
    payload = decisions if isinstance(decisions, dict) else {}
    completeness = validate_decision_completeness(payload)
    exchange = str(payload.get("exchange") or "").strip().upper()
    contract = {
        "strategy_id": "PENDING_MENTOR_DECISION_DRAFT",
        "strategy_family": str(payload.get("strategy_family") or "").strip().lower(),
        "universe": str(payload.get("universe") or "").strip(),
        "symbols": _normalize_symbols(payload.get("symbols")),
        "date_range": _normalize_date_range(payload.get("date_range")),
        "price_basis": PRICE_BASIS,
        "feature_inputs": ["PENDING_MENTOR_APPROVAL"],
        "entry_rule": "PENDING_MENTOR_APPROVAL",
        "exit_rule": "PENDING_MENTOR_APPROVAL",
        "rebalance_rule": str(payload.get("rebalance_rule") or "").strip(),
        "execution_price": str(payload.get("execution_price") or "").strip(),
        "transaction_cost_bps": _number_or_none(payload.get("transaction_cost_bps")),
        "slippage_bps": _number_or_none(payload.get("slippage_bps")),
        "exchange": exchange,
        "slippage_band_bps": EXCHANGE_BANDS_BPS.get(exchange),
        "position_sizing": str(payload.get("position_sizing") or "").strip(),
        "risk_rule": str(payload.get("risk_rule") or "").strip(),
        "max_holding_period": str(payload.get("max_holding_period") or "").strip(),
        "lookahead_policy": "Inputs must be available before execution.",
        "data_quality_gates": ["adjusted_ohlc_ready", "provenance_present", "symbols_covered"],
        "expected_outputs": ["pending_contract_review"],
        "caveats": [DRAFT_CAVEAT, "Not investment advice."],
        "mentor_approval_status": PENDING_APPROVAL,
    }
    return {
        **completeness,
        "contract_draft": contract,
        "caveats": [DRAFT_CAVEAT, "No execution and not investment advice."],
        "not_financial_advice": True,
    }


def build_decision_summary(decisions: dict[str, Any]) -> dict[str, Any]:
    result = build_pending_contract_draft(decisions)
    contract = result["contract_draft"]
    return {
        "status": result["status"],
        "decision_stage": DECISION_STAGE,
        "missing_fields": result["missing_fields"],
        "invalid_fields": result["invalid_fields"],
        "selected_family": contract["strategy_family"] or None,
        "symbols": contract["symbols"],
        "price_basis": PRICE_BASIS,
        "mentor_approval_status": PENDING_APPROVAL,
        "caveats": result["caveats"],
    }


def _field(name: str, label: str, field_type: str, *, options: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "label": label,
        "type": field_type,
        "required": True,
    }
    if options is not None:
        result["options"] = options
    return result


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return value is not None


def _normalize_symbols(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return []
    return list(
        dict.fromkeys(
            str(symbol or "").strip().upper()
            for symbol in values
            if str(symbol or "").strip()
        )
    )


def _normalize_date_range(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {"start": "", "end": ""}
    return {
        "start": str(value.get("start") or "").strip(),
        "end": str(value.get("end") or "").strip(),
    }


def _valid_date_range(value: Any) -> bool:
    normalized = _normalize_date_range(value)
    try:
        start = date.fromisoformat(normalized["start"])
        end = date.fromisoformat(normalized["end"])
    except ValueError:
        return False
    return start <= end


def _nonnegative_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _number_or_none(value: Any) -> int | float | None:
    return _nonnegative_number(value)
