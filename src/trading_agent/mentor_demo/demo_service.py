from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from trading_agent.mentor_demo.decision_capture import (
    REQUIRED_DECISION_FIELDS,
    build_pending_contract_draft,
    get_decision_fields,
)
from trading_agent.mentor_demo.demo_readiness import (
    build_demo_readiness_report,
    get_five_minute_demo_script,
)
from trading_agent.strategy.strategy_adapter import run_strategy_adapter_preview
from trading_agent.strategy.strategy_adapter_registry import (
    REGISTRY_VERSION,
    list_strategy_adapters,
)
from trading_agent.strategy.strategy_contract import validate_strategy_contract_file


ROOT = Path(__file__).resolve().parents[3]
BRIEF_PATH = "docs/mentor/mentor_call_brief_2026_06_22.md"
PROGRESS_PATH = "docs/reports/progress_report.md"
CONTRACT_TEMPLATE_PATH = "docs/strategy/examples/strategy_contract_template.json"
CONTRACT_SYMBOLS = ["FPT", "VNM", "VCB"]
EXTRA_PREPARED_SYMBOL = "HPG"

DEMO_CAVEATS = [
    "Research only.",
    "Not investment advice.",
    "No real strategy execution.",
    "No Backtrader.",
    "No optimizer.",
    "No full VN100.",
]


def get_demo_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "brief_path": BRIEF_PATH,
        "progress_report_path": PROGRESS_PATH,
        "current_stage": "mentor_demo_strategy_gate",
        "caveats": list(DEMO_CAVEATS),
    }


def get_upload_recommendation() -> dict[str, Any]:
    return {
        "status": "ok",
        "primary_file": BRIEF_PATH,
        "optional_file": PROGRESS_PATH,
        "blocked_upload_classes": [
            "raw data",
            "secrets",
            "database files",
            "build/temp artifacts",
        ],
    }


def get_decision_field_schema() -> dict[str, Any]:
    return {
        "status": "ok",
        "fields": get_decision_fields(),
        "persistence": "none",
        "mentor_approval_status": "pending",
    }


def get_decision_template() -> dict[str, Any]:
    return build_pending_contract_draft({field: "" for field in REQUIRED_DECISION_FIELDS})


def get_decision_example() -> dict[str, Any]:
    return build_pending_contract_draft(
        {
            "strategy_family": "moving_average",
            "universe": "mentor_selected_small_symbol_universe",
            "symbols": ["FPT", "VNM", "VCB"],
            "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
            "execution_price": "next_adjusted_open",
            "transaction_cost_bps": 15,
            "slippage_bps": 10,
            "exchange": "HOSE",
            "rebalance_rule": "mentor_to_confirm_daily_review",
            "risk_rule": "mentor_to_confirm_no_leverage",
            "position_sizing": "mentor_to_confirm_equal_weight",
            "max_holding_period": "mentor_to_confirm_20_sessions",
        }
    )


def get_demo_readiness() -> dict[str, Any]:
    return build_demo_readiness_report()


def get_demo_script() -> dict[str, Any]:
    return get_five_minute_demo_script()


def run_pending_contract_validation() -> dict[str, Any]:
    return validate_strategy_contract_file(ROOT / CONTRACT_TEMPLATE_PATH)


def list_registry_status() -> dict[str, Any]:
    families = list_strategy_adapters()
    return {
        "status": "ok",
        "registry_version": REGISTRY_VERSION,
        "families": families,
        "enabled_families": [entry["family"] for entry in families if entry["enabled"]],
        "disabled_families": [entry["family"] for entry in families if not entry["enabled"]],
        "not_financial_advice": True,
    }


def run_noop_adapter_preview() -> dict[str, Any]:
    return _run_adapter_fixture("noop")


def run_disabled_family_preview() -> dict[str, Any]:
    result = _run_adapter_fixture("moving_average")
    reasons = [str(reason) for reason in result.get("reasons") or []]
    return {**result, "reason": reasons[0] if reasons else None}


def build_demo_summary() -> dict[str, Any]:
    pending = run_pending_contract_validation()
    registry = list_registry_status()
    noop = run_noop_adapter_preview()
    disabled = run_disabled_family_preview()
    upload = get_upload_recommendation()
    readiness = get_demo_readiness()
    return {
        "status": "ok",
        "checks": {
            "pending_contract": {
                "status": pending["status"],
                "reasons": pending.get("reasons", []),
            },
            "registry": {
                "status": registry["status"],
                "enabled_families": registry["enabled_families"],
                "disabled_families": registry["disabled_families"],
            },
            "noop_preview": {
                "status": noop["status"],
                "symbols": sorted({row["symbol"] for row in noop["signal_intent_rows"]}),
                "signal_intent_actions": sorted(
                    {row["signal_intent_action"] for row in noop["signal_intent_rows"]}
                ),
            },
            "disabled_family": {
                "status": disabled["status"],
                "reason": disabled["reason"],
            },
        },
        "upload_files": {
            "primary": upload["primary_file"],
            "optional": upload["optional_file"],
        },
        "decision_capture": {
            "status": "available",
            "mentor_approval_status": "pending",
            "persistence": "none",
        },
        "demo_readiness": {
            "status": readiness["status"],
            "demo_command": readiness["demo_command"],
            "browser_url": readiness["browser_url"],
        },
        "mentor_decisions_needed": [
            "first strategy family",
            "universe",
            "execution price",
            "transaction cost/slippage",
            "rebalance/risk rule",
        ],
        "caveats": list(DEMO_CAVEATS),
    }


def _run_adapter_fixture(family: str) -> dict[str, Any]:
    contract = _approved_contract(family)
    prepared = _prepared_adjusted_ohlc_fixture()
    with tempfile.TemporaryDirectory(prefix="vsf_mentor_demo_") as temp_dir:
        work_dir = Path(temp_dir)
        contract_path = work_dir / "contract.json"
        prepared_path = work_dir / "prepared.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        prepared_path.write_text(json.dumps(prepared), encoding="utf-8")
        return run_strategy_adapter_preview(
            contract_path=contract_path,
            prepared_input_path=prepared_path,
        )


def _approved_contract(family: str) -> dict[str, Any]:
    return {
        "strategy_id": "mentor_demo_noop_v1",
        "strategy_family": family,
        "universe": "mentor_approved_small_symbol_research",
        "symbols": list(CONTRACT_SYMBOLS),
        "date_range": {"start": "2025-01-01", "end": "2025-01-31"},
        "price_basis": "adjusted_ohlc",
        "feature_inputs": ["prior_adjusted_close"],
        "entry_rule": "interface preview emits no signal intent",
        "exit_rule": "interface preview emits no signal intent",
        "rebalance_rule": "evaluate after a completed daily bar",
        "execution_price": "next_adjusted_open",
        "transaction_cost_bps": 15,
        "slippage_bps": 10,
        "exchange": "HOSE",
        "slippage_band_bps": 700,
        "position_sizing": "no position in interface preview",
        "risk_rule": "no leverage and no position in interface preview",
        "max_holding_period": "one research session",
        "lookahead_policy": "inputs available before evaluation",
        "data_quality_gates": ["adjusted_ohlc_ready", "symbols_covered"],
        "expected_outputs": ["signal_intent_report"],
        "caveats": ["synthetic local interface preview only"],
        "mentor_approval_status": "approved",
    }


def _prepared_adjusted_ohlc_fixture() -> dict[str, Any]:
    symbols = CONTRACT_SYMBOLS + [EXTRA_PREPARED_SYMBOL]
    return {
        "status": "ok",
        "backtest_input_status": "ready_for_research_dry_run",
        "price_basis": "adjusted_ohlc",
        "represented_symbols": symbols,
        "rows_preview": [
            {
                "symbol": symbol,
                "datetime": "2025-01-02",
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "fixture_only": True,
            }
            for index, symbol in enumerate(symbols)
        ],
    }
