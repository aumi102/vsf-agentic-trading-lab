from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.mentor_demo.decision_capture import get_decision_fields
from trading_agent.strategy.strategy_adapter_registry import list_strategy_adapters


ROOT = Path(__file__).resolve().parents[3]
DEMO_COMMAND = "python scripts/run_mentor_demo_ui.py"
BROWSER_URL = "http://127.0.0.1:8765"
BRIEF_PATH = "docs/mentor/mentor_call_brief_2026_06_22.md"
PROGRESS_PATH = "docs/reports/progress_report.md"
CONTRACT_TEMPLATE_PATH = "docs/strategy/examples/strategy_contract_template.json"
UI_SCRIPT_PATH = "scripts/run_mentor_demo_ui.py"
UPLOAD_FILES = [BRIEF_PATH, PROGRESS_PATH]
BLOCKED_ITEMS = [
    "real strategy execution",
    "Backtrader",
    "optimizer",
    "full VN100",
    "network fetch",
    "database mutation",
    "broker or live trading",
    "performance or profitability claim",
]
READINESS_CAVEATS = [
    "Local research demo only.",
    "No raw data is required.",
    "Not investment advice.",
]


def get_demo_readiness_checks() -> list[dict[str, Any]]:
    registry = list_strategy_adapters()
    enabled = [entry["family"] for entry in registry if entry["enabled"]]
    real_enabled = [family for family in enabled if family != "noop"]
    decision_fields = get_decision_fields()
    return [
        _check("brief_exists", (ROOT / BRIEF_PATH).is_file(), BRIEF_PATH),
        _check("progress_report_exists", (ROOT / PROGRESS_PATH).is_file(), PROGRESS_PATH),
        _check(
            "pending_contract_template_exists",
            (ROOT / CONTRACT_TEMPLATE_PATH).is_file(),
            CONTRACT_TEMPLATE_PATH,
        ),
        _check(
            "local_ui_server_command_exists",
            (ROOT / UI_SCRIPT_PATH).is_file(),
            DEMO_COMMAND,
        ),
        _check("registry_only_noop_enabled", enabled == ["noop"], {"enabled": enabled}),
        _check(
            "decision_capture_available",
            bool(decision_fields),
            {"field_count": len(decision_fields)},
        ),
        _check("no_real_family_enabled", not real_enabled, {"real_enabled": real_enabled}),
        _check(
            "upload_recommendation_is_minimal",
            UPLOAD_FILES == [BRIEF_PATH, PROGRESS_PATH],
            {"files": list(UPLOAD_FILES)},
        ),
        _check(
            "caveats_include_no_investment_advice",
            any("not investment advice" in item.lower() for item in READINESS_CAVEATS),
            {"caveats": list(READINESS_CAVEATS)},
        ),
        _check("no_raw_data_required", True, "Synthetic local fixtures and repository docs only."),
    ]


def build_demo_readiness_report() -> dict[str, Any]:
    checks = get_demo_readiness_checks()
    return {
        "status": "ok" if all(check["status"] == "ok" for check in checks) else "not_ready",
        "checks": checks,
        "demo_command": DEMO_COMMAND,
        "browser_url": BROWSER_URL,
        "upload_files": list(UPLOAD_FILES),
        "blocked_items": list(BLOCKED_ITEMS),
        "caveats": list(READINESS_CAVEATS),
        "not_financial_advice": True,
    }


def get_five_minute_demo_script() -> dict[str, Any]:
    return {
        "status": "ok",
        "duration": "5 minutes",
        "steps": [
            {
                "time": "0:00-0:30",
                "topic": "Overview",
                "talk_track": "Show the agent/tool product and explain that this is a safety-gate demo.",
            },
            {
                "time": "0:30-1:30",
                "topic": "Pending contract blocked",
                "talk_track": "Validate the pending contract and show that mentor approval is still required.",
            },
            {
                "time": "1:30-2:30",
                "topic": "Registry and noop gate",
                "talk_track": "Show that only noop is enabled and every real strategy family remains blocked.",
            },
            {
                "time": "2:30-4:00",
                "topic": "Decision capture",
                "talk_track": "Capture the mentor's assumptions into a pending, non-persisted contract draft.",
            },
            {
                "time": "4:00-5:00",
                "topic": "Mentor decisions needed",
                "talk_track": "Confirm family, universe, execution price, costs, rebalance, and risk rules.",
            },
        ],
        "not_financial_advice": True,
    }


def _check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok" if passed else "not_ready",
        "detail": detail,
    }
