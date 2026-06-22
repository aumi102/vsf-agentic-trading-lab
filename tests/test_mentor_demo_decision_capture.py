from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

from trading_agent.mentor_demo.decision_capture import (
    REQUIRED_DECISION_FIELDS,
    build_pending_contract_draft,
    get_decision_fields,
    validate_decision_completeness,
)


SOURCE_PATH = Path("src/trading_agent/mentor_demo/decision_capture.py")
SERVICE_PATH = Path("src/trading_agent/mentor_demo/demo_service.py")
SCRIPT_PATH = Path("scripts/run_mentor_demo_ui.py")
PROGRESS_PATH = Path("docs/reports/progress_report.md")


def _complete_decisions() -> dict[str, object]:
    return {
        "strategy_family": "moving_average",
        "universe": "mentor_small_symbol_research",
        "symbols": ["FPT", "VNM", "VCB"],
        "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
        "execution_price": "next_adjusted_open",
        "transaction_cost_bps": 15,
        "slippage_bps": 10,
        "exchange": "HOSE",
        "rebalance_rule": "daily after completed bar",
        "risk_rule": "no leverage",
        "position_sizing": "equal research weight",
        "max_holding_period": "20 sessions",
    }


def test_decision_fields_include_all_required_fields() -> None:
    assert {field["name"] for field in get_decision_fields()} == set(REQUIRED_DECISION_FIELDS)


def test_incomplete_decisions_are_not_ready() -> None:
    assert validate_decision_completeness({})["status"] == "not_ready"


def test_complete_decisions_are_draft_ready() -> None:
    assert validate_decision_completeness(_complete_decisions())["status"] == "draft_ready"


def test_generated_draft_stays_pending() -> None:
    result = build_pending_contract_draft(_complete_decisions())
    assert result["contract_draft"]["mentor_approval_status"] == "pending"


def test_generated_draft_never_auto_approves() -> None:
    result = build_pending_contract_draft({**_complete_decisions(), "mentor_approval_status": "approved"})
    assert result["contract_draft"]["mentor_approval_status"] != "approved"


def test_generated_draft_uses_adjusted_ohlc() -> None:
    assert build_pending_contract_draft(_complete_decisions())["contract_draft"]["price_basis"] == "adjusted_ohlc"


def test_generated_draft_has_advice_caveat() -> None:
    caveats = build_pending_contract_draft(_complete_decisions())["contract_draft"]["caveats"]
    assert any("not investment advice" in caveat.lower() for caveat in caveats)


def test_decision_example_route_returns_json() -> None:
    status, content_type, body = _script_module().build_response("/api/decision-example")
    assert status == 200
    assert content_type.startswith("application/json")
    assert json.loads(body)["contract_draft"]["mentor_approval_status"] == "pending"


def test_ui_contains_decision_capture() -> None:
    assert "Mentor Decision Capture" in _script_module().build_dashboard_html()


def test_decision_functions_have_no_file_writes() -> None:
    text = SOURCE_PATH.read_text(encoding="utf-8").lower()
    assert all(token not in text for token in ("write_text", "write_bytes", "open(", ".write("))


def test_no_backtrader_import() -> None:
    assert "import backtrader" not in _implementation_text().lower()


def test_no_optimizer_code() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("def optimize", "grid_search", "scipy.optimize"))


def test_no_network_client_imports() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("requests", "httpx", "urllib", "import socket"))


def test_no_db_mutation() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("sqlite3", "insert into", "update ", "delete from", ".execute("))


def test_no_recommendation_wording() -> None:
    output = json.dumps(build_pending_contract_draft(_complete_decisions())).lower()
    assert not re.search(r"\b(buy|sell|hold)\b", output)


def test_progress_report_has_one_decision_capture_row() -> None:
    rows = [
        line
        for line in PROGRESS_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("| Mentor decision capture |")
    ]
    assert len(rows) == 1


def _implementation_text() -> str:
    return "".join(
        path.read_text(encoding="utf-8") for path in (SOURCE_PATH, SERVICE_PATH, SCRIPT_PATH)
    )


def _script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_mentor_demo_ui", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
