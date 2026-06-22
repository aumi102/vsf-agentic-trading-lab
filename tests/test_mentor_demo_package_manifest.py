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


def test_all_mentor_docs_have_valid_frontmatter() -> None:
    expected_prefix = ["---", None, "toc_min_heading_level: 2", "toc_max_heading_level: 3", "---"]
    for relative_path in EXPECTED_MENTOR_DOCS:
        lines = (ROOT / relative_path).read_text(encoding="utf-8").splitlines()[:5]
        assert len(lines) == 5
        assert lines[0] == expected_prefix[0]
        assert lines[1].startswith("title: ")
        assert lines[2:] == expected_prefix[2:]


def test_reviewed_evidence_reports_are_external_only() -> None:
    item = next(item for item in build_manifest()["items"] if item["path"] == "reports/reviewed_evidence/*.md")
    assert item["exists"] is False
    assert item["status"] == "external_only"


def test_raw_market_data_is_blocked() -> None:
    item = next(item for item in build_manifest()["items"] if item["path"] == "data/raw/**")
    assert item["exists"] is False
    assert item["status"] == "blocked"


def test_runbook_has_template_only_warning() -> None:
    text = (ROOT / "docs/mentor/live_system_demo_runbook.md").read_text(encoding="utf-8").lower()
    normalized = " ".join(text.split())
    assert "prefer showing blocked states honestly over fabricating demo inputs" in normalized
    assert "template-only" in text


def test_strategy_template_requires_mentor_approval() -> None:
    text = (ROOT / "docs/mentor/strategy_decision_template.md").read_text(encoding="utf-8")
    assert "A strategy is not approved until this template has mentor-approved values." in text
