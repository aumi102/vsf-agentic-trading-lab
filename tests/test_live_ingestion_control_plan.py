from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.plan_live_ingestion_run import plan_live_ingestion_run


def test_valid_symbols_plan_ok() -> None:
    result = plan_live_ingestion_run(symbols=["FPT", "VNM", "VCB"])

    assert result["status"] == "ok"
    assert result["network_request_made"] is False
    assert result["db_mutation_made"] is False
    assert result["planned_batches"][0]["symbols"] == ["FPT", "VNM", "VCB"]


def test_more_than_three_symbols_blocked() -> None:
    result = plan_live_ingestion_run(symbols=["FPT", "VNM", "VCB", "MSN"])

    assert result["status"] == "blocked"
    assert any("max per batch is 3" in reason for reason in result["blocked_reasons"])
    assert result["planned_batches"] == []


def test_unknown_symbol_blocked() -> None:
    result = plan_live_ingestion_run(symbols=["FPT", "HPG"])

    assert result["status"] == "blocked"
    assert any("Symbols not in allowlist: HPG." == reason for reason in result["blocked_reasons"])


def test_config_default_symbols_plan_ok() -> None:
    result = plan_live_ingestion_run(symbols=None)

    assert result["status"] == "ok"
    assert result["symbols_requested"] == ["FPT", "VNM", "VCB"]
    assert result["count_back"] == 100


def test_invalid_count_back_blocked() -> None:
    result = plan_live_ingestion_run(symbols=["FPT"], count_back=0)

    assert result["status"] == "blocked"
    assert "count_back must be positive." in result["blocked_reasons"]


def test_invalid_rate_limit_config_blocked(tmp_path: Path) -> None:
    rate_config = tmp_path / "rate.json"
    rate_config.write_text(
        json.dumps(
            {
                "policy_name": "bad",
                "max_symbols_per_batch": 3,
                "min_seconds_between_requests": 0,
                "max_batches_per_manual_run": 1,
                "scheduler_enabled": False,
                "raw_retention_days": 30,
                "requires_manual_allow_network": True,
            }
        ),
        encoding="utf-8",
    )

    result = plan_live_ingestion_run(symbols=["FPT"], rate_limit_path=rate_config)

    assert result["status"] == "blocked"
    assert "min_seconds_between_requests must be at least 1." in result["blocked_reasons"]


def test_scheduler_enabled_config_blocked(tmp_path: Path) -> None:
    rate_config = tmp_path / "rate.json"
    rate_config.write_text(
        json.dumps(
            {
                "policy_name": "bad",
                "max_symbols_per_batch": 3,
                "min_seconds_between_requests": 2,
                "max_batches_per_manual_run": 1,
                "scheduler_enabled": True,
                "raw_retention_days": 30,
                "requires_manual_allow_network": True,
            }
        ),
        encoding="utf-8",
    )

    result = plan_live_ingestion_run(symbols=["FPT"], rate_limit_path=rate_config)

    assert result["status"] == "blocked"
    assert "scheduler_enabled must remain false for this dry-run planner." in result["blocked_reasons"]


def test_count_back_over_max_blocked() -> None:
    result = plan_live_ingestion_run(symbols=["FPT"], count_back=10_000)

    assert result["status"] == "blocked"
    assert any("exceeds max_count_back" in reason for reason in result["blocked_reasons"])
    assert result["planned_batches"] == []


def _write_symbol_config(tmp_path: Path, payload: dict) -> Path:
    config = tmp_path / "symbols.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def test_empty_allowed_symbols_config_blocked(tmp_path: Path) -> None:
    config = _write_symbol_config(
        tmp_path,
        {
            "source": "vietcap_iq_gap_chart",
            "allowed_symbols": [],
            "default_symbols": [],
            "default_count_back": 100,
            "max_count_back": 5000,
            "max_symbols_per_batch": 3,
        },
    )

    result = plan_live_ingestion_run(symbols=["FPT"], config_path=config)

    assert result["status"] == "blocked"
    assert "allowed_symbols must be non-empty." in result["blocked_reasons"]


def test_default_symbols_outside_allowlist_blocked(tmp_path: Path) -> None:
    config = _write_symbol_config(
        tmp_path,
        {
            "source": "vietcap_iq_gap_chart",
            "allowed_symbols": ["FPT", "VNM"],
            "default_symbols": ["FPT", "HPG"],
            "default_count_back": 100,
            "max_count_back": 5000,
            "max_symbols_per_batch": 3,
        },
    )

    result = plan_live_ingestion_run(symbols=["FPT"], config_path=config)

    assert result["status"] == "blocked"
    assert any("default_symbols not in allowlist" in reason for reason in result["blocked_reasons"])


def test_raw_retention_days_non_positive_blocked(tmp_path: Path) -> None:
    rate_config = tmp_path / "rate.json"
    rate_config.write_text(
        json.dumps(
            {
                "policy_name": "bad",
                "max_symbols_per_batch": 3,
                "min_seconds_between_requests": 2,
                "max_batches_per_manual_run": 1,
                "scheduler_enabled": False,
                "raw_retention_days": 0,
                "requires_manual_allow_network": True,
            }
        ),
        encoding="utf-8",
    )

    result = plan_live_ingestion_run(symbols=["FPT"], rate_limit_path=rate_config)

    assert result["status"] == "blocked"
    assert "raw_retention_days must be positive." in result["blocked_reasons"]


def test_requires_manual_allow_network_false_blocked(tmp_path: Path) -> None:
    rate_config = tmp_path / "rate.json"
    rate_config.write_text(
        json.dumps(
            {
                "policy_name": "bad",
                "max_symbols_per_batch": 3,
                "min_seconds_between_requests": 2,
                "max_batches_per_manual_run": 1,
                "scheduler_enabled": False,
                "raw_retention_days": 30,
                "requires_manual_allow_network": False,
            }
        ),
        encoding="utf-8",
    )

    result = plan_live_ingestion_run(symbols=["FPT"], rate_limit_path=rate_config)

    assert result["status"] == "blocked"
    assert "requires_manual_allow_network must remain true." in result["blocked_reasons"]


def test_blocked_result_still_reports_no_network_or_db_mutation() -> None:
    result = plan_live_ingestion_run(symbols=["FPT", "VNM", "VCB", "MSN"])

    assert result["status"] == "blocked"
    assert result["network_request_made"] is False
    assert result["db_mutation_made"] is False
    assert result["planned_batches"] == []


def test_cli_valid_plan_outputs_json_and_table() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/plan_live_ingestion_run.py", "--symbols", "FPT,VNM,VCB"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout
    assert "planned_batches" in completed.stdout
    assert "no network request made" in completed.stdout


def test_cli_blocked_too_many_symbols_exits_one() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/plan_live_ingestion_run.py", "--symbols", "FPT,VNM,VCB,MSN"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "blocked"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_config_mode_ok() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/plan_live_ingestion_run.py", "--config", "configs/ingestion/live_symbols_mvp.json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    assert '"symbols_requested": [' in completed.stdout
    assert '"FPT"' in completed.stdout
    assert '"network_request_made": false' in completed.stdout


def test_planner_source_has_no_network_or_db_mutation_code() -> None:
    text = Path("scripts/plan_live_ingestion_run.py").read_text(encoding="utf-8")

    assert "urlopen" not in text
    assert "urllib" not in text
    assert "import requests" not in text
    assert "requests." not in text
    assert "httpx" not in text
    assert "sqlite3" not in text
    assert "INSERT" not in text
    assert "UPDATE" not in text
    assert "DELETE" not in text
