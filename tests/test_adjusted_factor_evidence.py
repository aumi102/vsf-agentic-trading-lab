from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from trading_agent.ingestion.adjusted_factor_evidence import (
    build_adjusted_factor_evidence_record,
    capture_payload_adjustment_evidence,
    summarize_adjusted_factor_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def test_capture_adjusted_close_evidence(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"symbol": "FPT", "adjusted_close": 80.0}), encoding="utf-8")

    result = capture_payload_adjustment_evidence(
        symbol="fpt",
        source="tracked_fixtures",
        payload_path=payload_path,
    )

    assert result["status"] == "candidate_evidence"
    assert result["symbol"] == "FPT"
    assert result["evidence_strength"] == "adjusted_close_candidate"
    assert result["adjusted_close_fields"] == ["adjusted_close"]
    assert result["can_derive_factor"] is True
    assert result["network_request_made"] is False
    assert result["db_mutation_made"] is False
    assert result["adjusted_ohlc_populated"] is False


def test_capture_corporate_action_terms_without_factor_derivation(tmp_path: Path) -> None:
    payload_path = tmp_path / "events.json"
    payload_path.write_text(json.dumps({"events": [{"cashDividend": 1000, "exDate": "2026-01-02"}]}), encoding="utf-8")

    result = capture_payload_adjustment_evidence(
        symbol="FPT",
        source="tracked_fixtures",
        payload_path=payload_path,
    )

    assert result["status"] == "candidate_evidence"
    assert result["evidence_strength"] == "corporate_action_candidate"
    assert result["corporate_action_terms"] == ["cashDividend", "exDate"]
    assert result["can_derive_factor"] is False


def test_gap_chart_payload_returns_no_evidence(tmp_path: Path) -> None:
    payload_path = tmp_path / "gap.json"
    payload_path.write_text(
        json.dumps([{"symbol": "FPT", "t": [1], "o": [10], "h": [11], "l": [9], "c": [10.5], "v": [1000]}]),
        encoding="utf-8",
    )

    result = capture_payload_adjustment_evidence(
        symbol="FPT",
        source="vietcap_iq_gap_chart",
        payload_path=payload_path,
    )

    assert result["status"] == "no_evidence"
    assert result["evidence_strength"] == "none"
    assert result["can_derive_factor"] is False


def test_content_hash_is_stable(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"adjClose": 90.0}, sort_keys=True), encoding="utf-8")

    first = capture_payload_adjustment_evidence(symbol="FPT", source="tracked_fixtures", payload_path=payload_path)
    second = capture_payload_adjustment_evidence(symbol="FPT", source="tracked_fixtures", payload_path=payload_path)

    assert first["content_hash"] == second["content_hash"]
    assert len(first["content_hash"]) == 64


def test_file_capture_hash_uses_exact_payload_bytes(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_bytes(b'{"adjClose":90.0}\r\n')

    result = capture_payload_adjustment_evidence(symbol="FPT", source="tracked_fixtures", payload_path=payload_path)

    assert result["content_hash"] == hashlib.sha256(payload_path.read_bytes()).hexdigest()


def test_empty_metadata_returns_invalid_record() -> None:
    result = build_adjusted_factor_evidence_record(
        symbol="",
        source="",
        payload_path="",
        payload={"adjusted_close": 80.0},
    )

    assert result["status"] == "invalid"
    assert result["can_derive_factor"] is False
    assert result["reasons"] == ["symbol_required", "source_required", "payload_path_required"]


def test_generic_factor_only_does_not_imply_derivability(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"factor": 0.8}), encoding="utf-8")

    result = capture_payload_adjustment_evidence(symbol="FPT", source="tracked_fixtures", payload_path=payload_path)

    assert result["status"] == "candidate_evidence"
    assert result["evidence_strength"] == "candidate_field_only"
    assert result["can_derive_factor"] is False


def test_summary_counts_records(tmp_path: Path) -> None:
    close_path = tmp_path / "close.json"
    gap_path = tmp_path / "gap.json"
    close_path.write_text(json.dumps({"adjustedClose": 90.0}), encoding="utf-8")
    gap_path.write_text(json.dumps({"c": [10.0]}), encoding="utf-8")
    records = [
        capture_payload_adjustment_evidence(symbol="FPT", source="tracked_fixtures", payload_path=close_path),
        capture_payload_adjustment_evidence(symbol="FPT", source="vietcap_iq_gap_chart", payload_path=gap_path),
    ]

    summary = summarize_adjusted_factor_evidence(records)

    assert summary["status"] == "ok"
    assert summary["total_records"] == 2
    assert summary["records_with_derivable_factor_candidate"] == 1
    assert summary["by_status"] == {"candidate_evidence": 1, "no_evidence": 1}
    assert summary["db_mutation_made"] is False


def test_summary_handles_empty_records() -> None:
    summary = summarize_adjusted_factor_evidence([])

    assert summary["status"] == "empty"
    assert summary["total_records"] == 0
    assert summary["records_with_derivable_factor_candidate"] == 0


def test_summary_handles_invalid_and_missing_records(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"
    records = [
        capture_payload_adjustment_evidence(symbol="FPT", source="tracked_fixtures", payload_path=missing_path),
        build_adjusted_factor_evidence_record(symbol="", source="", payload_path="", payload={"adjusted_close": 80.0}),
    ]

    summary = summarize_adjusted_factor_evidence(records)

    assert summary["status"] == "ok"
    assert summary["records_with_derivable_factor_candidate"] == 0
    assert summary["by_status"] == {"invalid": 1, "missing_payload": 1}


def test_missing_payload_path_returns_clean_cli_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "tracked_fixtures",
            "--symbol",
            "FPT",
            "--payload",
            str(missing_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "missing_payload"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_missing_payload_does_not_write_output(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"
    output_path = tmp_path / "reports" / "evidence.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "tracked_fixtures",
            "--symbol",
            "FPT",
            "--payload",
            str(missing_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert not output_path.exists()


def test_invalid_json_returns_clean_cli_error(tmp_path: Path) -> None:
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("{bad-json", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "tracked_fixtures",
            "--symbol",
            "FPT",
            "--payload",
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


def test_invalid_json_does_not_write_output(tmp_path: Path) -> None:
    payload_path = tmp_path / "bad.json"
    output_path = tmp_path / "reports" / "evidence.json"
    payload_path.write_text("{bad-json", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "tracked_fixtures",
            "--symbol",
            "FPT",
            "--payload",
            str(payload_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert not output_path.exists()


def test_output_json_file_is_written_only_when_requested(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    output_path = tmp_path / "reports" / "adjusted_factor_evidence.json"
    payload_path.write_text(json.dumps({"adj_close": 90.0}), encoding="utf-8")

    no_output = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "tracked_fixtures",
            "--symbol",
            "FPT",
            "--payload",
            str(payload_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert no_output.returncode == 0
    assert not output_path.exists()

    with_output = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "tracked_fixtures",
            "--symbol",
            "FPT",
            "--payload",
            str(payload_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert with_output.returncode == 0
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["status"] == "candidate_evidence"


def test_invalid_metadata_cli_does_not_write_output(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    output_path = tmp_path / "reports" / "evidence.json"
    payload_path.write_text(json.dumps({"adjusted_close": 80.0}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/capture_adjusted_factor_evidence.py",
            "--source",
            "",
            "--symbol",
            "",
            "--payload",
            str(payload_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"status": "invalid"' in completed.stdout
    assert not output_path.exists()


def test_evidence_module_has_no_network_imports() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_factor_evidence.py").read_text(encoding="utf-8")

    assert all(name not in source for name in ["requests", "httpx", "urllib"])


def test_evidence_module_has_no_db_imports_or_mutation() -> None:
    source = Path("src/trading_agent/ingestion/adjusted_factor_evidence.py").read_text(encoding="utf-8")

    blocked = ["sqlite3", "sqlalchemy", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "]
    assert all(name not in source for name in blocked)
