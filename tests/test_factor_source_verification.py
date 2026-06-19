from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.ingestion.factor_source_verification import (
    plan_factor_source_verification,
    verify_factor_source_payload,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path("tests/fixtures/adjustment_factors")
ADJUSTED_CLOSE_PAYLOAD = FIXTURE_DIR / "adjusted_close_payload.json"
CORPORATE_ACTION_PAYLOAD = FIXTURE_DIR / "corporate_action_factor_payload.json"


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plan_valid_for_default_symbols() -> None:
    plan = plan_factor_source_verification(["FPT", "VNM", "VCB"])

    assert plan["status"] == "ok"
    assert plan["symbols_requested"] == ["FPT", "VNM", "VCB"]
    assert plan["blocked_reasons"] == []
    assert plan["planned_steps"]
    assert plan["network_request_made"] is False


def test_plan_blocks_too_many_symbols() -> None:
    plan = plan_factor_source_verification(["FPT", "VNM", "VCB", "HPG"], max_symbols=3)

    assert plan["status"] == "blocked"
    assert any("max per check is 3" in reason for reason in plan["blocked_reasons"])
    assert plan["planned_steps"] == []


def test_plan_blocks_allow_network() -> None:
    plan = plan_factor_source_verification(["FPT"], allow_network=True)

    assert plan["status"] == "blocked"
    assert any("Live factor-source verification is not implemented" in reason for reason in plan["blocked_reasons"])


def test_config_defaults_match_small_symbol_guardrail() -> None:
    config = _load(Path("configs/ingestion/verified_factor_source_check_mvp.json"))

    assert config["default_symbols"] == ["FPT", "VNM", "VCB"]
    assert config["max_symbols_per_check"] == 3
    assert config["allow_network_default"] is False


def test_module_starts_with_future_annotations_import() -> None:
    source = Path("src/trading_agent/ingestion/factor_source_verification.py").read_text(encoding="utf-8")

    assert source.startswith("from __future__ import annotations\n")


def test_controlled_verification_doc_frontmatter_is_valid() -> None:
    source = Path("docs/data_platform/controlled_factor_source_verification.md").read_text(encoding="utf-8")
    expected = [
        "---",
        "title: controlled_factor_source_verification",
        "toc_min_heading_level: 2",
        "toc_max_heading_level: 3",
        "---",
    ]

    assert source.splitlines()[:5] == expected


def test_adjusted_close_payload_verifies_usable_record() -> None:
    result = verify_factor_source_payload(
        _load(ADJUSTED_CLOSE_PAYLOAD),
        method="adjusted_close_ratio",
        source_id="fixture:adjusted_close",
        raw_path=str(ADJUSTED_CLOSE_PAYLOAD),
        symbols=["FPT"],
    )

    assert result["status"] == "ok"
    assert result["usable_records"] == 1
    assert result["symbols"] == ["FPT"]
    assert result["adjusted_ohlc_populated"] is False


def test_corporate_action_payload_verifies_usable_record() -> None:
    result = verify_factor_source_payload(
        _load(CORPORATE_ACTION_PAYLOAD),
        method="corporate_action_derived",
        source_id="fixture:corporate_action",
        raw_path=str(CORPORATE_ACTION_PAYLOAD),
        symbols=["FPT"],
    )

    assert result["status"] == "ok"
    assert result["usable_records"] == 1


def test_missing_adjusted_close_returns_no_usable_records() -> None:
    result = verify_factor_source_payload(
        [{"symbol": "FPT", "trade_date": "2026-01-02", "close": 100.0}],
        method="adjusted_close_ratio",
        source_id="fixture:adjusted_close",
        raw_path="fixtures/missing_adjusted_close.json",
        symbols=["FPT"],
    )

    assert result["status"] == "not_ready"
    assert result["usable_records"] == 0
    assert result["missing_records"] == 1
    assert "no_usable_factor_records" in result["reasons"]


def test_unknown_method_returns_clean_error() -> None:
    result = verify_factor_source_payload(
        _load(ADJUSTED_CLOSE_PAYLOAD),
        method="mystery_method",
        source_id="fixture:adjusted_close",
        raw_path=str(ADJUSTED_CLOSE_PAYLOAD),
        symbols=["FPT"],
    )

    assert result["status"] == "invalid"
    assert result["usable_records"] == 0
    assert "unsupported_factor_source_method:mystery_method" in result["reasons"]


def test_symbols_filter_excludes_unrequested_symbols() -> None:
    payload = [
        {"symbol": "FPT", "trade_date": "2026-01-02", "close": 100.0, "adjusted_close": 80.0},
        {"symbol": "VNM", "trade_date": "2026-01-02", "close": 100.0, "adjusted_close": 90.0},
    ]
    result = verify_factor_source_payload(
        payload,
        method="adjusted_close_ratio",
        source_id="fixture:adjusted_close",
        raw_path="fixtures/multi.json",
        symbols=["FPT"],
    )

    assert result["status"] == "ok"
    assert result["records_total"] == 1
    assert result["symbols"] == ["FPT"]


def test_requested_symbol_not_present_returns_no_usable_records() -> None:
    result = verify_factor_source_payload(
        _load(ADJUSTED_CLOSE_PAYLOAD),
        method="adjusted_close_ratio",
        source_id="fixture:adjusted_close",
        raw_path=str(ADJUSTED_CLOSE_PAYLOAD),
        symbols=["MSN"],
    )

    assert result["status"] == "not_ready"
    assert result["usable_records"] == 0
    assert result["records_total"] == 0
    assert "no_usable_factor_records" in result["reasons"]


def test_mixed_usable_and_invalid_requested_records_are_reported() -> None:
    payload = [
        {"symbol": "FPT", "trade_date": "2026-01-02", "close": 100.0, "adjusted_close": 80.0},
        {"symbol": "FPT", "trade_date": "2026-01-03", "close": 100.0, "adjusted_close": -1.0},
        {"symbol": "VNM", "trade_date": "2026-01-02", "close": 100.0, "adjusted_close": 90.0},
    ]
    result = verify_factor_source_payload(
        payload,
        method="adjusted_close_ratio",
        source_id="fixture:adjusted_close",
        raw_path="fixtures/mixed.json",
        symbols=["FPT"],
    )

    assert result["status"] == "ok"
    assert result["records_total"] == 2
    assert result["usable_records"] == 1
    assert result["invalid_records"] == 1
    assert result["missing_records"] == 0


def test_cli_success_exits_zero() -> None:
    proc = _run_cli(
        "--payload",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--method",
        "adjusted_close_ratio",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--symbols",
        "FPT",
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"
    assert payload["usable_records"] == 1


def test_cli_allow_network_exits_one_cleanly() -> None:
    proc = _run_cli(
        "--payload",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--method",
        "adjusted_close_ratio",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--symbols",
        "FPT",
        "--allow-network",
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "network_not_implemented"
    assert payload["network_request_made"] is False


def test_cli_unknown_method_exits_one_cleanly() -> None:
    proc = _run_cli(
        "--payload",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--method",
        "raw_close_is_adjusted",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--symbols",
        "FPT",
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "unknown_method"


def test_cli_missing_payload_exits_one_cleanly() -> None:
    proc = _run_cli(
        "--payload",
        "tests/fixtures/adjustment_factors/does_not_exist.json",
        "--method",
        "adjusted_close_ratio",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        "fixtures/does_not_exist.json",
        "--symbols",
        "FPT",
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "missing_payload"


def test_cli_invalid_json_exits_one_cleanly(tmp_path: Path) -> None:
    payload_path = tmp_path / "invalid.json"
    payload_path.write_text("{not json", encoding="utf-8")
    proc = _run_cli(
        "--payload",
        str(payload_path),
        "--method",
        "adjusted_close_ratio",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(payload_path),
        "--symbols",
        "FPT",
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "invalid_json"


def test_cli_requested_symbol_not_present_exits_one_cleanly() -> None:
    proc = _run_cli(
        "--payload",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--method",
        "adjusted_close_ratio",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(ADJUSTED_CLOSE_PAYLOAD),
        "--symbols",
        "MSN",
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "not_ready"
    assert payload["usable_records"] == 0


def test_cli_no_usable_records_exits_one_cleanly() -> None:
    proc = _run_cli(
        "--payload",
        str(CORPORATE_ACTION_PAYLOAD),
        "--method",
        "adjusted_close_ratio",
        "--source-id",
        "fixture:adjusted_close",
        "--raw-path",
        str(CORPORATE_ACTION_PAYLOAD),
        "--symbols",
        "FPT",
    )

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "not_ready"
    assert payload["usable_records"] == 0


def test_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/factor_source_verification.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/factor_source_verification.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)


def test_verification_never_populates_adjusted_ohlc() -> None:
    plan = plan_factor_source_verification(["FPT"])
    result = verify_factor_source_payload(
        _load(ADJUSTED_CLOSE_PAYLOAD),
        method="adjusted_close_ratio",
        source_id="fixture:adjusted_close",
        raw_path=str(ADJUSTED_CLOSE_PAYLOAD),
        symbols=["FPT"],
    )

    assert plan["adjusted_ohlc_populated"] is False
    assert result["adjusted_ohlc_populated"] is False
    assert result["db_mutation_made"] is False


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/verify_factor_source_payload.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
