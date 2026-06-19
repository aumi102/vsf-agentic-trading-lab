from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.db.schema import create_schema


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PACKAGE = Path("tests/fixtures/adjustment_factors/reviewed_evidence_package")
CREATE_SCRIPT = Path("scripts/create_reviewed_adjusted_price_manifest.py")
VALIDATE_SCRIPT = Path("scripts/validate_reviewed_adjusted_price_package.py")


def test_manifest_generator_computes_correct_sha256(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    output = tmp_path / "manifest.json"

    completed = _run_create(payload, output, evidence_basis="adjusted_price_vendor_export")

    assert completed.returncode == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["payload_sha256"] == _sha256(payload)
    assert json.loads(completed.stdout)["status"] == "ok"


def test_generator_rejects_missing_payload(tmp_path: Path) -> None:
    completed = _run_create(tmp_path / "missing.json", tmp_path / "manifest.json")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "payload_not_found" in completed.stdout


def test_generator_rejects_invalid_reviewed_at(tmp_path: Path) -> None:
    completed = _run_create(_payload(tmp_path), tmp_path / "manifest.json", reviewed_at="2026-6-19")

    assert completed.returncode == 1
    assert "reviewed_at_must_be_iso_date" in completed.stdout


def test_generator_rejects_invalid_evidence_basis(tmp_path: Path) -> None:
    completed = _run_create(_payload(tmp_path), tmp_path / "manifest.json", evidence_basis="raw_close")

    assert completed.returncode == 1
    assert "unsupported_evidence_basis:raw_close" in completed.stdout


def test_dev_only_basis_requires_not_real_market_data_flag(tmp_path: Path) -> None:
    completed = _run_create(_payload(tmp_path), tmp_path / "manifest.json", not_real_market_data=False)

    assert completed.returncode == 1
    assert "not_real_market_data_required_for_dev_only" in completed.stdout


def test_package_validator_validates_synthetic_temp_package_dry_run(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    report = tmp_path / "validation.json"
    factors = tmp_path / "factors.json"

    completed = _run_validate(package, validation_output=report, factor_output=factors)

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert report.exists()
    assert factors.exists()


def test_package_validator_rejects_hash_mismatch(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    payload_path = package / "payload.json"
    payload_path.write_text(payload_path.read_text(encoding="utf-8").replace("80.0", "81.0", 1), encoding="utf-8")

    completed = _run_validate(package)

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "invalid_payload_hash"' in completed.stdout


def test_package_validator_rejects_missing_manifest(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "manifest.json").unlink()

    completed = _run_validate(package)

    assert completed.returncode == 1
    assert '"missing_manifest"' in completed.stdout


def test_package_validator_rejects_missing_payload(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "payload.json").unlink()
    (package / "payload.csv").unlink()

    completed = _run_validate(package)

    assert completed.returncode == 1
    assert '"missing_payload"' in completed.stdout


def test_package_validator_execute_temp_db_readiness_pass(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    db_path = _make_db(tmp_path)
    factors = tmp_path / "factors.json"

    completed = _run_validate(package, factor_output=factors, db_path=db_path, execute=True)

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["readiness_status"] == "ok"
    assert payload["backtest_gate"] == "pass"


def test_cli_expected_errors_exit_one_without_traceback(tmp_path: Path) -> None:
    completed = _run_validate(tmp_path / "missing")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "invalid_request"' in completed.stdout


def test_no_network_imports() -> None:
    texts = [CREATE_SCRIPT.read_text(encoding="utf-8"), VALIDATE_SCRIPT.read_text(encoding="utf-8")]

    assert all(name not in text for text in texts for name in ["requests", "httpx", "urllib"])


def test_no_backtrader_docker_questdb_behavior() -> None:
    texts = [CREATE_SCRIPT.read_text(encoding="utf-8").lower(), VALIDATE_SCRIPT.read_text(encoding="utf-8").lower()]
    blocked = ["import backtrader", "import docker", "questdb"]

    assert all(name not in text for text in texts for name in blocked)


def test_no_references_to_production_demo_db() -> None:
    texts = [CREATE_SCRIPT.read_text(encoding="utf-8"), VALIDATE_SCRIPT.read_text(encoding="utf-8")]

    assert all("data/demo" not in text for text in texts)
    assert all("mvp_trading_agent.sqlite" not in text for text in texts)


def test_gitignore_includes_reviewed_evidence_paths() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "data/reviewed_evidence/" in text
    assert "reports/reviewed_evidence/" in text


def _payload(tmp_path: Path) -> Path:
    path = tmp_path / "payload.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": "FPT",
                    "trade_date": "2026-01-02",
                    "close": 100.0,
                    "adjusted_close": 80.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


def _run_create(
    payload: Path,
    output: Path,
    *,
    reviewed_at: str = "2026-06-19",
    evidence_basis: str = "manual_curated_for_dev_only",
    not_real_market_data: bool = True,
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(CREATE_SCRIPT),
        "--payload",
        str(payload),
        "--source-id",
        "fixture:real_onboarding",
        "--reviewer",
        "fixture-reviewer",
        "--reviewed-at",
        reviewed_at,
        "--evidence-basis",
        evidence_basis,
        "--raw-path",
        "payload.json",
        "--output",
        str(output),
    ]
    if not_real_market_data:
        args.append("--not-real-market-data")
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _run_validate(
    package: Path,
    *,
    validation_output: Path | None = None,
    factor_output: Path | None = None,
    db_path: Path | None = None,
    execute: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(VALIDATE_SCRIPT),
        "--package-dir",
        str(package),
        "--symbols",
        "FPT,VNM,VCB",
    ]
    if validation_output is not None:
        args.extend(["--validation-output", str(validation_output)])
    if factor_output is not None:
        args.extend(["--factor-output", str(factor_output)])
    if db_path is not None:
        args.extend(["--db-path", str(db_path)])
    if execute:
        args.append("--execute")
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _copy_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    shutil.copytree(ROOT / FIXTURE_PACKAGE, package)
    return package


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "reviewed_onboarding.sqlite"
    raw_close = {"FPT": 100.0, "VNM": 200.0, "VCB": 50.0}
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        for symbol, close in raw_close.items():
            con.execute(
                """
                INSERT INTO daily_prices (
                    security_id, symbol, trade_date, open, high, low, close,
                    volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"fixture:real_onboarding:{symbol}:2026-01-02",
                    symbol,
                    "2026-01-02",
                    close * 0.95,
                    close * 1.05,
                    close * 0.9,
                    close,
                    1000.0,
                    close * 1000.0,
                    "source_reported",
                    "unknown",
                    "fixture:daily_prices_real_onboarding",
                    f"synthetic://real-onboarding/{symbol.lower()}",
                    "ok",
                ),
            )
        con.commit()
    return db_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
