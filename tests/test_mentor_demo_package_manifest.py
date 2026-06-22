from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.list_mentor_demo_package import PACKAGE_ENTRIES, build_manifest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/list_mentor_demo_package.py")
EXPECTED_MENTOR_DOCS = {
    "docs/mentor/live_demo_index.md",
    "docs/mentor/vin_folder_upload_manifest.md",
    "docs/mentor/live_system_demo_runbook.md",
    "docs/mentor/backtest_strategy_review_agenda.md",
    "docs/mentor/strategy_decision_template.md",
    "docs/mentor/backtest_readiness_checklist.md",
    "docs/mentor/current_system_status_for_call.md",
    "docs/mentor/mentor_questions.md",
}


def test_all_expected_mentor_docs_listed() -> None:
    assert EXPECTED_MENTOR_DOCS <= {entry[0] for entry in PACKAGE_ENTRIES}
    assert build_manifest()["status"] == "ok"


def test_missing_file_marked_missing(tmp_path: Path) -> None:
    manifest = build_manifest(tmp_path)
    first = next(item for item in manifest["items"] if item["path"] == "docs/mentor/live_demo_index.md")
    assert first["exists"] is False
    assert first["status"] == "missing"
    assert manifest["status"] == "incomplete"


def test_output_json_works(tmp_path: Path) -> None:
    output = tmp_path / "package.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-json", str(output)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"


def test_no_generated_package_artifact_committed() -> None:
    assert not (ROOT / "mentor_demo_package.json").exists()
    assert all(entry[0] != "mentor_demo_package.json" for entry in PACKAGE_ENTRIES)


def test_no_network_imports() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert all(token not in text for token in ("requests", "httpx", "urllib", "socket"))


def test_no_db_mutation() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    assert all(token not in text for token in ("sqlite3", "insert into", "update ", "delete from", ".execute("))
