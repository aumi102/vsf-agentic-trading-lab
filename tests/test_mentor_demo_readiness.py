from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from trading_agent.mentor_demo.demo_readiness import (
    build_demo_readiness_report,
    get_demo_readiness_checks,
    get_five_minute_demo_script,
)


SOURCE_PATH = Path("src/trading_agent/mentor_demo/demo_readiness.py")
SERVICE_PATH = Path("src/trading_agent/mentor_demo/demo_service.py")
SCRIPT_PATH = Path("scripts/run_mentor_demo_ui.py")
PROGRESS_PATH = Path("docs/reports/progress_report.md")


def test_readiness_report_returns_ok() -> None:
    assert build_demo_readiness_report()["status"] == "ok"


def test_checks_include_brief_exists() -> None:
    assert _checks()["brief_exists"]["status"] == "ok"


def test_checks_include_registry_only_noop_enabled() -> None:
    assert _checks()["registry_only_noop_enabled"]["status"] == "ok"


def test_checks_include_no_real_family_enabled() -> None:
    assert _checks()["no_real_family_enabled"]["status"] == "ok"


def test_report_includes_demo_command() -> None:
    assert build_demo_readiness_report()["demo_command"] == "python scripts/run_mentor_demo_ui.py"


def test_report_includes_browser_url() -> None:
    assert build_demo_readiness_report()["browser_url"] == "http://127.0.0.1:8765"


def test_report_includes_upload_files() -> None:
    assert build_demo_readiness_report()["upload_files"] == [
        "docs/mentor/mentor_call_brief_2026_06_22.md",
        "docs/reports/progress_report.md",
    ]


def test_report_marks_not_financial_advice() -> None:
    assert build_demo_readiness_report()["not_financial_advice"] is True


def test_demo_script_contains_pending_contract() -> None:
    assert "pending contract" in _script_text().lower()


def test_demo_script_contains_registry_and_noop() -> None:
    text = _script_text().lower()
    assert "registry" in text and "noop" in text


def test_demo_script_contains_decision_capture() -> None:
    assert "decision capture" in _script_text().lower()


def test_demo_readiness_route_returns_ok() -> None:
    _, _, body = _script_module().build_response("/api/demo-readiness")
    assert json.loads(body)["status"] == "ok"


def test_demo_script_route_returns_ok() -> None:
    _, _, body = _script_module().build_response("/api/demo-script")
    assert json.loads(body)["status"] == "ok"


def test_dashboard_contains_final_readiness() -> None:
    assert "Final Demo Readiness" in _script_module().build_dashboard_html()


def test_dashboard_contains_copy_demo_script() -> None:
    assert "Copy Demo Script" in _script_module().build_dashboard_html()


def test_no_post_route() -> None:
    assert "do_POST" not in SCRIPT_PATH.read_text(encoding="utf-8")


def test_no_backtrader_import() -> None:
    assert "import backtrader" not in _implementation_text().lower()


def test_no_optimizer_code() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("def optimize", "grid_search", "scipy.optimize"))


def test_no_db_mutation() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("sqlite3", "insert into", "update ", "delete from", ".execute("))


def test_no_network_client_imports() -> None:
    text = _implementation_text().lower()
    assert all(token not in text for token in ("requests", "httpx", "urllib", "import socket"))


def test_progress_report_has_one_readiness_polish_row() -> None:
    rows = [
        line
        for line in PROGRESS_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("| Mentor demo readiness polish |")
    ]
    assert len(rows) == 1


def _checks() -> dict[str, dict[str, object]]:
    return {str(check["name"]): check for check in get_demo_readiness_checks()}


def _script_text() -> str:
    return json.dumps(get_five_minute_demo_script())


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
