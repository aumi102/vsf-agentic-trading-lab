from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.db.schema import create_schema
from trading_agent.ingestion.reviewed_adjusted_price_evidence import (
    compute_file_sha256,
    run_reviewed_adjusted_price_evidence_intake,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("tests/fixtures/adjustment_factors/reviewed_adjusted_price_manifest.json")


def test_valid_json_payload_and_manifest_dry_run_returns_ok(tmp_path: Path) -> None:
    payload = _payload(tmp_path)

    result = _run_intake(payload_path=payload, symbols=["FPT"])

    assert result["status"] == "ok"
    assert result["manifest_status"] == "ok"
    assert result["usable_records"] == 1
    assert result["db_mutation_made"] is False


def test_valid_csv_payload_and_manifest_dry_run_returns_ok(tmp_path: Path) -> None:
    payload = tmp_path / "payload.csv"
    payload.write_text("symbol,trade_date,close,adjusted_close\nFPT,2026-01-02,100,80\n", encoding="utf-8")

    result = _run_intake(payload_path=payload, symbols=["FPT"])

    assert result["status"] == "ok"
    assert result["usable_records"] == 1


def test_missing_manifest_clean_error(tmp_path: Path) -> None:
    result = run_reviewed_adjusted_price_evidence_intake(
        manifest_path=tmp_path / "missing.json",
        payload_path=_payload(tmp_path),
        symbols=["FPT"],
    )

    assert result["status"] == "missing_manifest"
    assert result["db_mutation_made"] is False


def test_invalid_manifest_json_clean_error(tmp_path: Path) -> None:
    manifest = tmp_path / "bad_manifest.json"
    manifest.write_text("{bad", encoding="utf-8")

    result = run_reviewed_adjusted_price_evidence_intake(
        manifest_path=manifest,
        payload_path=_payload(tmp_path),
        symbols=["FPT"],
    )

    assert result["status"] == "invalid_manifest_json"


def test_missing_payload_clean_error(tmp_path: Path) -> None:
    result = run_reviewed_adjusted_price_evidence_intake(
        manifest_path=MANIFEST,
        payload_path=tmp_path / "missing.json",
        symbols=["FPT"],
    )

    assert result["status"] == "missing_payload"


def test_missing_reviewer_rejected(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, reviewer="")

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "reviewer_required" in result["reasons"]


def test_missing_reviewed_at_rejected(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, reviewed_at="")

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "reviewed_at_required" in result["reasons"]


def test_invalid_evidence_basis_rejected(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, evidence_basis="raw_close_as_adjusted_close")

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "unsupported_evidence_basis:raw_close_as_adjusted_close" in result["reasons"]


def test_missing_payload_sha256_rejected(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, payload_sha256="")

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "payload_sha256_required" in result["reasons"]


def test_invalid_payload_sha256_format_rejected(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, payload_sha256="not-a-sha")

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "payload_sha256_invalid" in result["reasons"]


def test_payload_sha256_mismatch_rejected_without_factor_output(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, payload_sha256="0" * 64)
    factor_output = tmp_path / "factors.json"

    result = _run_intake(
        manifest_path=manifest,
        payload_path=payload,
        symbols=["FPT"],
        factor_output_path=factor_output,
    )

    assert result["status"] == "invalid_payload_hash"
    assert "payload_sha256_mismatch" in result["reasons"]
    assert result["manifest_integrity"]["payload_sha256_match"] is False
    assert not factor_output.exists()


def test_invalid_reviewed_at_rejected(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, reviewed_at="2026-6-19")

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "reviewed_at_must_be_iso_date" in result["reasons"]


def test_manual_curated_requires_not_real_market_data(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload, not_real_market_data=False)

    result = _run_intake(manifest_path=manifest, payload_path=payload, symbols=["FPT"])

    assert result["status"] == "invalid_manifest"
    assert "not_real_market_data_required_for_dev_only" in result["reasons"]


def test_more_than_three_symbols_blocked(tmp_path: Path) -> None:
    result = _run_intake(payload_path=_payload(tmp_path), symbols=["FPT", "VNM", "VCB", "HPG"])

    assert result["status"] == "invalid_request"
    assert "too_many_symbols:max=3" in result["reasons"]


def test_requested_symbol_not_present_returns_not_ready(tmp_path: Path) -> None:
    result = _run_intake(payload_path=_payload(tmp_path), symbols=["MSN"])

    assert result["status"] == "not_ready"
    assert result["missing_records"] == 1
    assert "requested_symbols_missing:MSN" in result["reasons"]


def test_close_less_than_or_equal_zero_rejected(tmp_path: Path) -> None:
    result = _run_intake(payload_path=_payload(tmp_path, close=0), symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert "close_must_be_positive" in result["reasons"]


def test_adjusted_close_less_than_or_equal_zero_rejected(tmp_path: Path) -> None:
    result = _run_intake(payload_path=_payload(tmp_path, adjusted_close=0), symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert "adjusted_close_must_be_positive" in result["reasons"]


def test_raw_close_as_adjusted_close_blocked(tmp_path: Path) -> None:
    result = _run_intake(payload_path=_payload(tmp_path, close=100, adjusted_close=100), symbols=["FPT"])

    assert result["status"] == "not_ready"
    assert "raw_close_as_adjusted_close_blocked" in result["reasons"]


def test_no_factor_one_fallback_created(tmp_path: Path) -> None:
    factor_output = tmp_path / "factors.json"

    result = _run_intake(
        payload_path=_payload(tmp_path, close=100, adjusted_close=100),
        symbols=["FPT"],
        factor_output_path=factor_output,
    )

    assert result["status"] == "not_ready"
    assert not factor_output.exists()


def test_validation_report_written_when_requested(tmp_path: Path) -> None:
    report = tmp_path / "validation.json"

    result = _run_intake(payload_path=_payload(tmp_path), symbols=["FPT"], validation_output_path=report)

    assert result["status"] == "ok"
    assert report.exists()
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "ok"


def test_validation_report_includes_manifest_integrity(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    report = tmp_path / "validation.json"

    result = _run_intake(payload_path=payload, symbols=["FPT"], validation_output_path=report)
    saved = json.loads(report.read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert saved["manifest_integrity"]["source_id"] == "fixture:reviewed_adjusted_price"
    assert saved["manifest_integrity"]["raw_path"] == str(payload)
    assert saved["manifest_integrity"]["reviewer"] == "fixture-reviewer"
    assert saved["manifest_integrity"]["reviewed_at"] == "2026-06-19"
    assert saved["manifest_integrity"]["evidence_basis"] == "manual_curated_for_dev_only"
    assert saved["manifest_integrity"]["payload_sha256"] == compute_file_sha256(payload)
    assert saved["manifest_integrity"]["computed_payload_sha256"] == compute_file_sha256(payload)
    assert saved["manifest_integrity"]["payload_sha256_match"] is True
    assert saved["manifest_integrity"]["not_real_market_data"] is True


def test_factor_output_written_when_requested(tmp_path: Path) -> None:
    factor_output = tmp_path / "factors.json"

    result = _run_intake(payload_path=_payload(tmp_path), symbols=["FPT"], factor_output_path=factor_output)

    assert result["status"] == "ok"
    assert factor_output.exists()
    assert json.loads(factor_output.read_text(encoding="utf-8"))[0]["factor"] == 0.8


def test_execute_full_coverage_temp_db_returns_ok_readiness_pass(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, [{"symbol": "FPT", "trade_date": "2026-01-02"}])
    factor_output = tmp_path / "factors.json"

    result = _run_intake(
        payload_path=_payload(tmp_path),
        symbols=["FPT"],
        factor_output_path=factor_output,
        db_path=db_path,
        dry_run=False,
        execute=True,
    )

    assert result["status"] == "ok"
    assert result["readiness_status"] == "ok"
    assert result["backtest_gate"] == "pass"
    assert result["db_mutation_made"] is True


def test_execute_partial_coverage_returns_not_ready_readiness_blocked(tmp_path: Path) -> None:
    db_path = _make_db(
        tmp_path,
        [
            {"symbol": "FPT", "trade_date": "2026-01-02"},
            {"symbol": "FPT", "trade_date": "2026-01-03"},
        ],
    )
    factor_output = tmp_path / "factors.json"

    result = _run_intake(
        payload_path=_payload(tmp_path),
        symbols=["FPT"],
        factor_output_path=factor_output,
        db_path=db_path,
        dry_run=False,
        execute=True,
    )

    assert result["status"] == "not_ready"
    assert result["readiness_status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"


def test_cli_success_exits_zero(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload)
    completed = _run_cli(
        "--manifest",
        str(manifest),
        "--payload",
        str(payload),
        "--symbols",
        "FPT",
        "--factor-output",
        str(tmp_path / "factors.json"),
    )

    assert completed.returncode == 0
    assert '"status": "ok"' in completed.stdout


def test_cli_expected_errors_exit_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_cli(
        "--manifest",
        str(MANIFEST),
        "--payload",
        str(tmp_path / "missing.json"),
        "--symbols",
        "FPT",
    )

    assert completed.returncode == 1
    assert '"status": "missing_payload"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_cli_allow_network_exits_one_without_traceback(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    manifest = _manifest(tmp_path, payload)
    completed = _run_cli(
        "--manifest",
        str(manifest),
        "--payload",
        str(payload),
        "--symbols",
        "FPT",
        "--allow-network",
    )

    assert completed.returncode == 1
    assert '"network_not_implemented"' in completed.stdout
    assert "Traceback" not in completed.stderr


def test_no_network_imports() -> None:
    text = Path("src/trading_agent/ingestion/reviewed_adjusted_price_evidence.py").read_text(encoding="utf-8")
    cli = Path("scripts/run_reviewed_adjusted_price_evidence_intake.py").read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])
    assert all(name not in cli for name in ["requests", "httpx", "urllib"])


def test_no_backtrader_docker_questdb_behavior() -> None:
    text = Path("src/trading_agent/ingestion/reviewed_adjusted_price_evidence.py").read_text(encoding="utf-8").lower()
    cli = Path("scripts/run_reviewed_adjusted_price_evidence_intake.py").read_text(encoding="utf-8").lower()

    blocked = ["import backtrader", "import docker", "questdb"]
    assert all(name not in text for name in blocked)
    assert all(name not in cli for name in blocked)


def _run_intake(
    *,
    payload_path: Path,
    symbols: list[str],
    manifest_path: Path | None = None,
    validation_output_path: Path | None = None,
    factor_output_path: Path | None = None,
    db_path: Path | None = None,
    dry_run: bool = True,
    execute: bool = False,
) -> dict[str, object]:
    if manifest_path is None:
        manifest_path = _manifest(payload_path.parent, payload_path)
    return run_reviewed_adjusted_price_evidence_intake(
        manifest_path=manifest_path,
        payload_path=payload_path,
        symbols=symbols,
        validation_output_path=validation_output_path,
        factor_output_path=factor_output_path,
        db_path=db_path,
        dry_run=dry_run,
        execute=execute,
    )


def _payload(
    tmp_path: Path,
    *,
    symbol: str = "FPT",
    trade_date: str = "2026-01-02",
    close: float = 100.0,
    adjusted_close: float = 80.0,
) -> Path:
    path = tmp_path / "payload.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "close": close,
                    "adjusted_close": adjusted_close,
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


def _manifest(tmp_path: Path, payload_path: Path, **overrides: object) -> Path:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["raw_path"] = str(payload_path)
    payload["payload_sha256"] = compute_file_sha256(payload_path)
    payload.update(overrides)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_reviewed_adjusted_price_evidence_intake.py", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _make_db(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        for row in rows:
            symbol = str(row.get("symbol", "FPT"))
            trade_date = str(row.get("trade_date", "2026-01-02"))
            con.execute(
                """
                INSERT INTO daily_prices (
                    security_id, symbol, trade_date, open, high, low, close,
                    volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"fixture:reviewed:{symbol}:{trade_date}",
                    symbol,
                    trade_date,
                    90.0,
                    110.0,
                    80.0,
                    100.0,
                    1000.0,
                    100000.0,
                    "source_reported",
                    "unknown",
                    "fixture:daily_prices",
                    f"fixtures/{symbol.lower()}_{trade_date}.json",
                    "ok",
                ),
            )
        con.commit()
    return db_path
