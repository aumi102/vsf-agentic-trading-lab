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
    assert result["evidence_strength"] == "adjusted_close_candidate"
    assert result["adjusted_close_fields"] == ["adjustedClose"]
    assert result["can_derive_factor"] is True


def test_payload_inspection_detects_adjusted_close_case_insensitively() -> None:
    result = inspect_payload_for_adjustment_evidence({"ADJ_CLOSE": 80.0, "AdjustedClose": 80.0})

    assert result["evidence_strength"] == "adjusted_close_candidate"
    assert result["adjusted_close_fields"] == ["ADJ_CLOSE", "AdjustedClose"]


def test_payload_inspection_finds_corporate_action_terms() -> None:
    result = inspect_payload_for_adjustment_evidence(
        {
            "events": [
                {
                    "cashDividend": 2000,
                    "stockDividend": 0.1,
                    "splitRatio": "2:1",
                    "exDate": "2026-01-02",
                    "recordDate": "2026-01-03",
                    "paymentDate": "2026-01-20",
                }
            ]
        }
    )

    assert result["status"] == "evidence_found"
    assert result["evidence_strength"] == "corporate_action_candidate"
    assert result["can_derive_factor"] is False
    assert result["corporate_action_terms"] == [
        "cashDividend",
        "exDate",
        "paymentDate",
        "recordDate",
        "splitRatio",
        "stockDividend",
    ]


def test_generic_factor_is_candidate_only_and_risk_factor_is_ignored() -> None:
    result = inspect_payload_for_adjustment_evidence({"factor": 0.8, "risk_factor": "size"})

    assert result["status"] == "evidence_found"
    assert result["evidence_strength"] == "candidate_field_only"
    assert result["generic_factor_fields"] == ["factor"]
    assert result["adjustment_factor_fields"] == []
    assert result["can_derive_factor"] is False


def test_adjustment_factor_field_is_stronger_than_generic_factor() -> None:
    result = inspect_payload_for_adjustment_evidence({"adjust_factor": 0.8, "factor": "ignored generic"})

    assert result["evidence_strength"] == "adjustment_factor_candidate"
    assert result["adjustment_factor_fields"] == ["adjust_factor"]
    assert result["generic_factor_fields"] == ["factor"]
    assert result["can_derive_factor"] is True


def test_payload_inspection_returns_no_evidence_for_gap_chart_shape() -> None:
    payload = [{"symbol": "FPT", "t": [1], "o": [10], "h": [11], "l": [9], "c": [10.5], "v": [1000]}]

    result = inspect_payload_for_adjustment_evidence(payload)

    assert result["status"] == "no_evidence"
    assert result["evidence_strength"] == "none"
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


def test_cli_allow_network_blocked_without_traceback() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/probe_adjusted_factor_sources.py", "--allow-network", "--symbols", "FPT"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "blocked"' in completed.stdout
    assert "Live adjusted-factor source probing is not implemented" in completed.stdout
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


def test_cli_inspect_payload_invalid_json_exits_cleanly(tmp_path: Path) -> None:
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("{not-json", encoding="utf-8")

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

    assert completed.returncode == 1
    assert '"status": "invalid_json"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_source_config_documents_candidate_placeholders() -> None:
    text = Path("configs/ingestion/adjusted_factor_probe_mvp.json").read_text(encoding="utf-8")

    assert "vietcap_iq_company_events" in text
    assert "No adjusted OHLC population" in text


def test_probe_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_factor_probe.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_probe_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_factor_probe.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)
