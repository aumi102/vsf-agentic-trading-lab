from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/smoke_reviewed_adjusted_price_evidence_package.py")
PACKAGE = Path("tests/fixtures/adjustment_factors/reviewed_evidence_package")


def test_default_package_smoke_exits_zero() -> None:
    completed = _run_package_smoke()

    assert completed.returncode == 0
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["package_dir"] == str((ROOT / PACKAGE).resolve())


def test_json_and_csv_dry_runs_both_ok() -> None:
    payload = json.loads(_run_package_smoke().stdout)

    assert payload["json_dry_run"]["status"] == "ok"
    assert payload["csv_dry_run"]["status"] == "ok"
    assert payload["json_dry_run"]["manifest_integrity"]["payload_sha256_match"] is True
    assert payload["csv_dry_run"]["manifest_integrity"]["payload_sha256_match"] is True


def test_execute_on_temp_db_readiness_passes() -> None:
    payload = json.loads(_run_package_smoke().stdout)

    assert payload["execute"]["status"] == "ok"
    assert payload["execute"]["db_mutation_made"] is True
    assert payload["readiness"]["status"] == "ok"
    assert payload["readiness"]["backtest_gate"] == "pass"


def test_bad_package_dir_exits_one_cleanly(tmp_path: Path) -> None:
    completed = _run_package_smoke("--package-dir", str(tmp_path / "missing"))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "invalid_request"
    assert "missing_package_files:manifest.json,payload.json,payload.csv" in payload["reasons"]


def test_hash_mismatch_package_exits_one_cleanly(tmp_path: Path) -> None:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    (package / "payload.json").write_text(
        (package / "payload.json").read_text(encoding="utf-8").replace("80.0", "81.0", 1),
        encoding="utf-8",
    )

    completed = _run_package_smoke("--package-dir", str(package))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "not_ready"
    assert payload["json_dry_run"]["status"] == "invalid_payload_hash"
    assert "payload_sha256_mismatch" in payload["json_dry_run"]["reasons"]


def test_copied_package_with_relative_raw_path_still_passes(tmp_path: Path) -> None:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)

    completed = _run_package_smoke("--package-dir", str(package))

    assert completed.returncode == 0
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["json_dry_run"]["manifest_integrity"]["raw_path"] == "payload.json"
    assert payload["csv_dry_run"]["manifest_integrity"]["raw_path"] == "payload.csv"


def test_manifest_raw_path_outside_package_exits_one_cleanly(tmp_path: Path) -> None:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw_path"] = "../payload.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    completed = _run_package_smoke("--package-dir", str(package))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "invalid_request"
    assert payload["reasons"] == ["manifest_raw_path_outside_package"]


def test_missing_payload_csv_exits_one_cleanly(tmp_path: Path) -> None:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    (package / "payload.csv").unlink()

    completed = _run_package_smoke("--package-dir", str(package))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "invalid_request"
    assert "missing_package_files:payload.csv" in payload["reasons"]


def test_manifest_hash_matches_payload_json() -> None:
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    payload_hash = _sha256(PACKAGE / "payload.json")

    assert manifest["payload_sha256"] == payload_hash


def test_package_script_has_no_network_imports() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])


def test_package_script_has_no_backtrader_docker_questdb_behavior() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    assert "import backtrader" not in text
    assert "import docker" not in text
    assert "questdb" not in text


def test_package_script_never_references_demo_db() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "data/demo" not in text
    assert "mvp_trading_agent.sqlite" not in text


def test_generated_artifacts_are_temp_only() -> None:
    payload = json.loads(_run_package_smoke().stdout)

    assert ".pytest_tmp" not in json.dumps(payload)
    assert payload["json_dry_run"]["validation_report_path"] is not None
    assert payload["execute"]["factor_output_path"] is not None


def _run_package_smoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()
