from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from trading_agent.ingestion.adjusted_factor_probe import (
    inspect_payload_for_adjustment_evidence,
    plan_adjusted_factor_probe,
)


ROOT = Path(__file__).resolve().parents[1]


def test_valid_dry_run_probe_plan() -> None:
    result = plan_adjusted_factor_probe(
        symbols=["FPT", "VNM", "VCB"],
        candidate_sources=["vietcap_iq_gap_chart", "tracked_fixtures"],
    )

    assert result["status"] == "ok"
    assert result["network_request_made"] is False
    assert result["db_mutation_made"] is False
    assert result["adjusted_ohlc_populated"] is False
    assert result["planned_steps"]


def test_too_many_symbols_blocked() -> None:
    result = plan_adjusted_factor_probe(
        symbols=["FPT", "VNM", "VCB", "MSN"],
        candidate_sources=["vietcap_iq_gap_chart"],
    )

    assert result["status"] == "blocked"
    assert any("max per probe is 3" in reason for reason in result["blocked_reasons"])


def test_unknown_candidate_source_blocked() -> None:
    result = plan_adjusted_factor_probe(symbols=["FPT"], candidate_sources=["unknown_source"])

    assert result["status"] == "blocked"
    assert "Unknown candidate source: unknown_source." in result["blocked_reasons"]


def test_no_network_and_no_db_mutation_flags_on_blocked_plan() -> None:
    result = plan_adjusted_factor_probe(
        symbols=["FPT"],
        candidate_sources=["vietcap_iq_gap_chart"],
        allow_network=True,
    )

    assert result["status"] == "blocked"
    assert result["network_request_made"] is False
    assert result["db_mutation_made"] is False
    assert "Live adjusted-factor source probing is not implemented in this PR." in result["blocked_reasons"]


def test_payload_inspection_finds_adjusted_close() -> None:
    result = inspect_payload_for_adjustment_evidence({"symbol": "FPT", "adjustedClose": 80.0})

    assert result["status"] == "evidence_found"
    assert result["adjusted_close_fields"] == ["adjustedClose"]
    assert result["can_derive_factor"] is True


def test_payload_inspection_finds_corporate_action_terms() -> None:
    result = inspect_payload_for_adjustment_evidence(
        {"events": [{"dividend": 2000, "split": "2:1", "ex_date": "2026-01-02"}]}
    )

    assert result["status"] == "evidence_found"
    assert result["corporate_action_terms"] == ["dividend", "ex_date", "split"]


def test_payload_inspection_returns_no_evidence_for_gap_chart_shape() -> None:
    payload = [{"symbol": "FPT", "t": [1], "o": [10], "h": [11], "l": [9], "c": [10.5], "v": [1000]}]

    result = inspect_payload_for_adjustment_evidence(payload)

    assert result["status"] == "no_evidence"
    assert result["adjusted_close_fields"] == []
    assert result["adjustment_factor_fields"] == []
    assert result["corporate_action_terms"] == []


def test_cli_valid_dry_run_exits_zero() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/probe_adjusted_factor_sources.py", "--symbols", "FPT,VNM,VCB"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout
    assert '"network_request_made": false' in completed.stdout


def test_cli_blocked_exits_one_without_traceback() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/probe_adjusted_factor_sources.py", "--symbols", "FPT,VNM,VCB,MSN"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "blocked"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_inspect_payload_exits_zero(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"adj_close": 90.0}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/probe_adjusted_factor_sources.py",
            "--inspect-payload",
            str(payload_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert '"status": "evidence_found"' in completed.stdout


def test_probe_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_factor_probe.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_probe_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_factor_probe.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)
