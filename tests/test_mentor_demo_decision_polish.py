from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


SOURCE_PATH = Path("src/trading_agent/mentor_demo/decision_capture.py")
SCRIPT_PATH = Path("scripts/run_mentor_demo_ui.py")
PROGRESS_PATH = Path("docs/reports/progress_report.md")


def test_dashboard_has_sample_fill_button() -> None:
    assert "Fill Sample Mentor Decision" in _html()


def test_dashboard_has_copy_talk_track_button() -> None:
    assert "Copy Demo Talk Track" in _html()


def test_talk_track_is_rendered_after_route_call() -> None:
    html = _html()
    assert "fetch('/api/talk-track')" in html
    assert "textContent = payload.talk_track" in html


def test_dashboard_uses_number_or_null() -> None:
    assert "numberOrNull" in _html()


def test_blank_number_warning_is_visible_in_html() -> None:
    assert "Required number fields are blank; values remain null" in _html()


def test_cost_does_not_use_direct_number_conversion() -> None:
    assert "Number(fieldValue('decision-cost'))" not in _html()


def test_slippage_does_not_use_direct_number_conversion() -> None:
    assert "Number(fieldValue('decision-slippage'))" not in _html()


def test_talk_track_route_returns_ok() -> None:
    status, _, body = _script_module().build_response("/api/talk-track")
    assert status == 200
    assert json.loads(body)["status"] == "ok"


def test_talk_track_says_no_approval() -> None:
    assert "does not approve the contract" in _talk_track().lower()


def test_talk_track_says_no_family_enablement() -> None:
    assert "enable a family" in _talk_track().lower()


def test_talk_track_states_strategy_performance_advice_boundaries() -> None:
    text = _talk_track().lower()
    assert all(phrase in text for phrase in ("run a strategy", "compute performance", "investment advice"))


def test_sample_draft_stays_pending() -> None:
    html = _html()
    assert "mentor_approval_status: 'pending'" in html
    assert "fillSampleMentorDecision" in html


def test_server_template_stays_not_ready() -> None:
    _, _, body = _script_module().build_response("/api/decision-template")
    assert json.loads(body)["status"] == "not_ready"


def test_server_example_stays_draft_ready_and_pending() -> None:
    _, _, body = _script_module().build_response("/api/decision-example")
    payload = json.loads(body)
    assert payload["status"] == "draft_ready"
    assert payload["contract_draft"]["mentor_approval_status"] == "pending"


def test_no_post_route_added() -> None:
    assert "do_POST" not in SCRIPT_PATH.read_text(encoding="utf-8")


def test_no_file_write_added() -> None:
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


def test_progress_report_has_one_decision_polish_row() -> None:
    rows = [
        line
        for line in PROGRESS_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("| Mentor decision capture polish |")
    ]
    assert len(rows) == 1


def _html() -> str:
    return _script_module().build_dashboard_html()


def _talk_track() -> str:
    _, _, body = _script_module().build_response("/api/talk-track")
    return str(json.loads(body)["talk_track"])


def _implementation_text() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8") + SCRIPT_PATH.read_text(encoding="utf-8")


def _script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_mentor_demo_ui", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
