from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from trading_agent.mentor_demo.demo_service import (
    build_demo_summary,
    get_demo_status,
    get_upload_recommendation,
    list_registry_status,
    run_disabled_family_preview,
    run_noop_adapter_preview,
    run_pending_contract_validation,
)


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = Path("src/trading_agent/mentor_demo/demo_service.py")
SCRIPT_PATH = Path("scripts/run_mentor_demo_ui.py")
RUNBOOK_PATH = Path("docs/mentor/mentor_demo_ui_runbook.md")
CONTRACT_SYMBOLS = {"FPT", "VNM", "VCB"}


def test_demo_service_status_returns_ok() -> None:
    assert get_demo_status()["status"] == "ok"


def test_upload_recommendation_is_minimal() -> None:
    result = get_upload_recommendation()
    assert result["primary_file"] == "docs/mentor/mentor_call_brief_2026_06_22.md"
    assert result["optional_file"] == "docs/reports/progress_report.md"


def test_pending_contract_validation_is_not_ready() -> None:
    result = run_pending_contract_validation()
    assert result["status"] == "not_ready"
    assert "mentor_approval_not_approved:pending" in result["reasons"]


def test_registry_enables_only_noop() -> None:
    result = list_registry_status()
    assert result["enabled_families"] == ["noop"]
    assert set(result["disabled_families"]) == {
        "moving_average", "momentum", "breakout", "mean_reversion"
    }


def test_noop_preview_returns_ok() -> None:
    assert run_noop_adapter_preview()["status"] == "ok"


def test_noop_preview_excludes_extra_prepared_symbol() -> None:
    rows = run_noop_adapter_preview()["signal_intent_rows"]
    assert {row["symbol"] for row in rows} == CONTRACT_SYMBOLS
    assert "HPG" not in {row["symbol"] for row in rows}


def test_noop_preview_only_uses_no_signal() -> None:
    rows = run_noop_adapter_preview()["signal_intent_rows"]
    assert {row["signal_intent_action"] for row in rows} == {"NO_SIGNAL"}


def test_disabled_moving_average_is_blocked() -> None:
    assert run_disabled_family_preview()["status"] == "blocked"


def test_disabled_moving_average_has_named_reason() -> None:
    assert run_disabled_family_preview()["reason"] == "strategy_family_not_enabled:moving_average"


def test_summary_returns_ok() -> None:
    assert build_demo_summary()["status"] == "ok"


def test_html_route_contains_dashboard_title() -> None:
    status, content_type, body = _script_module().build_response("/")
    assert status == 200
    assert content_type.startswith("text/html")
    assert "VSF Local Mentor Demo UI" in body.decode("utf-8")


def test_api_summary_returns_json() -> None:
    status, content_type, body = _script_module().build_response("/api/summary")
    assert status == 200
    assert content_type.startswith("application/json")
    assert json.loads(body)["status"] == "ok"


def test_once_json_exits_zero_and_prints_ok() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--once-json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["status"] == "ok"


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


def test_output_has_no_recommendation_wording() -> None:
    text = json.dumps(
        [build_demo_summary(), run_noop_adapter_preview(), run_disabled_family_preview()]
    ).lower()
    assert all(word not in text for word in ("buy", "sell", "hold"))


def test_output_has_no_performance_fields() -> None:
    keys = _all_keys([build_demo_summary(), run_noop_adapter_preview()])
    assert not {"pnl", "equity", "return", "returns"} & keys


def test_runbook_references_one_command() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "python scripts/run_mentor_demo_ui.py" in text


def _implementation_text() -> str:
    return SERVICE_PATH.read_text(encoding="utf-8") + SCRIPT_PATH.read_text(encoding="utf-8")


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | set().union(
            *(_all_keys(item) for item in value.values()), set()
        )
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_mentor_demo_ui", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
