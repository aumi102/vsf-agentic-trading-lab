from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/summarize_reviewed_adjusted_price_validation_report.py")


def test_summarizer_writes_markdown_for_ok_dry_run_report(tmp_path: Path) -> None:
    report = _write_report(tmp_path, status="ok")
    output = tmp_path / "summary.md"

    completed = _run_summary(report, output)

    assert completed.returncode == 0
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "Reviewed Adjusted Price Evidence Dry-Run Report" in text
    assert "Dry-run validation passed" in text


def test_summarizer_exits_zero_for_ok_status(tmp_path: Path) -> None:
    completed = _run_summary(_write_report(tmp_path, status="ok"), tmp_path / "summary.md")

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


def test_summarizer_exits_one_for_not_ready_status(tmp_path: Path) -> None:
    completed = _run_summary(_write_report(tmp_path, status="not_ready"), tmp_path / "summary.md")

    assert completed.returncode == 1
    assert '"status": "not_ready"' in completed.stdout
    assert "validation_status:not_ready" in completed.stdout


def test_summarizer_rejects_missing_file(tmp_path: Path) -> None:
    completed = _run_summary(tmp_path / "missing.json", tmp_path / "summary.md")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "missing_report"' in completed.stdout


def test_summarizer_rejects_invalid_json(tmp_path: Path) -> None:
    report = tmp_path / "bad.json"
    report.write_text("{bad", encoding="utf-8")

    completed = _run_summary(report, tmp_path / "summary.md")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "invalid_report_json"' in completed.stdout


def test_summarizer_rejects_non_object_json(tmp_path: Path) -> None:
    report = tmp_path / "bad.json"
    report.write_text("[]", encoding="utf-8")

    completed = _run_summary(report, tmp_path / "summary.md")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "invalid_report_json"' in completed.stdout


def test_missing_manifest_integrity_exits_one(tmp_path: Path) -> None:
    completed = _run_summary(
        _write_report(tmp_path, status="ok", manifest_integrity=None),
        tmp_path / "summary.md",
    )

    assert completed.returncode == 1
    assert "manifest_integrity_missing" in completed.stdout


def test_payload_sha256_match_false_exits_one(tmp_path: Path) -> None:
    completed = _run_summary(
        _write_report(tmp_path, status="ok", manifest_integrity={"payload_sha256_match": False}),
        tmp_path / "summary.md",
    )

    assert completed.returncode == 1
    assert "payload_sha256_not_matched" in completed.stdout


def test_invalid_records_present_exits_one(tmp_path: Path) -> None:
    completed = _run_summary(
        _write_report(tmp_path, status="ok", invalid_records=2),
        tmp_path / "summary.md",
    )

    assert completed.returncode == 1
    assert "invalid_records_present:2" in completed.stdout


def test_missing_records_present_exits_one(tmp_path: Path) -> None:
    completed = _run_summary(
        _write_report(tmp_path, status="ok", missing_records=1),
        tmp_path / "summary.md",
    )

    assert completed.returncode == 1
    assert "missing_records_present:1" in completed.stdout


def test_summarizer_includes_manifest_integrity(tmp_path: Path) -> None:
    output = tmp_path / "summary.md"

    completed = _run_summary(_write_report(tmp_path, status="ok"), output)

    assert completed.returncode == 0
    text = output.read_text(encoding="utf-8")
    assert "source_id" in text
    assert "payload_sha256_match" in text
    assert "fixture:reviewed_evidence_package" in text


def test_summarizer_includes_backtrader_blocked_warning(tmp_path: Path) -> None:
    output = tmp_path / "summary.md"

    completed = _run_summary(_write_report(tmp_path, status="ok"), output)

    assert completed.returncode == 0
    assert "Backtrader/VN100 must remain blocked" in output.read_text(encoding="utf-8")


def test_summarizer_validates_expected_symbols(tmp_path: Path) -> None:
    completed = _run_summary(
        _write_report(tmp_path, status="ok", symbols=["FPT", "VNM"]),
        tmp_path / "summary.md",
        "--expected-symbols",
        "FPT,VNM,VCB",
    )

    assert completed.returncode == 1
    assert "expected_symbols_missing:VCB" in completed.stdout


def test_successful_report_includes_conservative_recommendation(tmp_path: Path) -> None:
    output = tmp_path / "summary.md"

    completed = _run_summary(_write_report(tmp_path, status="ok"), output)

    assert completed.returncode == 0
    text = output.read_text(encoding="utf-8")
    assert "Ready for reviewed execute dry-run on an explicit local DB" in text
    assert "Backtrader/VN100 must remain blocked" in text


def test_readiness_pass_report_says_execute_validation_passed(tmp_path: Path) -> None:
    output = tmp_path / "summary.md"

    completed = _run_summary(
        _write_report(tmp_path, status="ok", readiness_status="ok", backtest_gate="pass"),
        output,
    )

    assert completed.returncode == 0
    text = output.read_text(encoding="utf-8")
    assert "Execute validation passed on the local DB" in text
    assert "Backtrader/VN100 must remain blocked" in text


def test_no_network_imports() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])


def test_no_backtrader_docker_questdb_behavior() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    assert "import backtrader" not in text
    assert "import docker" not in text
    assert "questdb" not in text


def _write_report(
    tmp_path: Path,
    *,
    status: str,
    symbols: list[str] | None = None,
    manifest_integrity: dict[str, object] | None | bool = True,
    invalid_records: int = 0,
    missing_records: int | None = None,
    readiness_status: str | None = None,
    backtest_gate: str | None = None,
) -> Path:
    default_integrity = {
        "source_id": "fixture:reviewed_evidence_package",
        "raw_path": "payload.json",
        "reviewer": "fixture-reviewer",
        "reviewed_at": "2026-06-19",
        "evidence_basis": "manual_curated_for_dev_only",
        "payload_sha256": "0" * 64,
        "computed_payload_sha256": "0" * 64,
        "payload_sha256_match": True,
        "not_real_market_data": True,
    }
    if manifest_integrity is True:
        integrity: dict[str, object] | None = default_integrity
    elif manifest_integrity is None:
        integrity = None
    else:
        integrity = {**default_integrity, **manifest_integrity}
    missing = (0 if status == "ok" else 1) if missing_records is None else missing_records
    report = {
        "status": status,
        "symbols": symbols or ["FPT", "VNM", "VCB"],
        "manifest_status": "ok",
        "rows_total": 3,
        "usable_records": 3 if status == "ok" else 0,
        "invalid_records": invalid_records,
        "missing_records": missing,
        "readiness_status": readiness_status,
        "backtest_gate": backtest_gate,
        "reasons": [] if status == "ok" else ["reviewed_evidence_not_ready"],
        "caveats": [
            "Reviewed local adjusted-price evidence only; no network request made.",
            "Backtrader/VN100 remains blocked until reviewed evidence and adjusted readiness pass.",
        ],
    }
    if integrity is not None:
        report["manifest_integrity"] = integrity
    path = tmp_path / "validation.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def _run_summary(report: Path, output: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--validation-report",
            str(report),
            "--output-md",
            str(output),
            *extra_args,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
