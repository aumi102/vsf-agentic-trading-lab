import re
from pathlib import Path


BRIEF_PATH = Path("docs/mentor/mentor_call_brief_2026_06_22.md")
PROGRESS_PATH = Path("docs/reports/progress_report.md")
EXPECTED_FRONTMATTER = """---
title: mentor_call_brief_2026_06_22
toc_min_heading_level: 2
toc_max_heading_level: 3
---
"""


def _brief() -> str:
    return BRIEF_PATH.read_text(encoding="utf-8")


def test_brief_exists_with_valid_frontmatter() -> None:
    assert BRIEF_PATH.is_file()
    assert _brief().startswith(EXPECTED_FRONTMATTER)


def test_brief_recommends_only_the_minimal_upload_set() -> None:
    text = _brief()
    upload_section = text.split("## Files to Upload to the Vin Folder", 1)[1]
    upload_paths = set(re.findall(r"`(docs/[^`]+\.md)`", upload_section))

    assert "docs/mentor/mentor_call_brief_2026_06_22.md" in upload_paths
    assert upload_paths == {
        "docs/mentor/mentor_call_brief_2026_06_22.md",
        "docs/reports/progress_report.md",
    }


def test_brief_excludes_sensitive_and_generated_uploads() -> None:
    text = " ".join(_brief().lower().split())
    for phrase in ("raw data", "secrets", "database files", "build/temp artifacts"):
        assert phrase in text


def test_brief_states_project_boundaries() -> None:
    text = _brief().lower()
    for phrase in (
        "real backtrader",
        "full vn100",
        "optimizer",
        "live trading",
        "performance / profitability claim",
        "investment advice",
    ):
        assert phrase in text


def test_brief_lists_mentor_decisions() -> None:
    text = _brief().lower()
    for phrase in (
        "family",
        "universe",
        "execution price",
        "transaction cost",
        "slippage",
        "rebalance",
        "risk",
    ):
        assert phrase in text


def test_progress_report_has_one_mentor_call_brief_row() -> None:
    text = PROGRESS_PATH.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| Mentor call brief |")]
    assert len(rows) == 1
