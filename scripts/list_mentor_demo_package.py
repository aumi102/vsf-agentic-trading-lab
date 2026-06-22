from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

PACKAGE_ENTRIES = (
    ("docs/mentor/live_demo_index.md", "ready_to_upload", "Mentor-call entry point."),
    ("docs/mentor/vin_folder_upload_manifest.md", "ready_to_upload", "Vin folder checklist."),
    ("docs/mentor/live_system_demo_runbook.md", "ready_to_upload", "Live demo commands and gates."),
    ("docs/mentor/backtest_strategy_review_agenda.md", "ready_to_upload", "Backtest and strategy call agenda."),
    ("docs/mentor/strategy_decision_template.md", "ready_to_upload", "Mentor approval template."),
    ("docs/mentor/backtest_readiness_checklist.md", "ready_to_upload", "Pre-backtest gate checklist."),
    ("docs/mentor/current_system_status_for_call.md", "ready_to_upload", "Current implementation status."),
    ("docs/mentor/mentor_questions.md", "ready_to_upload", "Open decisions for mentor."),
    ("docs/architecture/02_trading_agent_architecture_overview.md", "ready_to_upload", "Product architecture."),
    ("docs/demo/vsf_mentor_db_ingestion_backtest_handoff.md", "ready_to_upload", "Current handoff."),
    ("docs/backtest/adjusted_ohlc_backtest_requirement.md", "ready_to_upload", "Adjusted-price policy."),
    ("docs/backtest/adjusted_ohlc_backtest_feed_contract.md", "ready_to_upload", "Adjusted feed contract."),
    ("docs/backtest/adjusted_ohlc_feed_to_backtest_dry_run.md", "ready_to_upload", "Dry-run preparation."),
    ("docs/backtest/adjusted_ohlc_fixture_signal_dry_run.md", "ready_to_upload", "Fixture signal."),
    ("docs/backtest/adjusted_ohlc_fixture_metrics_report.md", "ready_to_upload", "Fixture metrics."),
    ("docs/backtest/adjusted_ohlc_fixture_roundtrip_engine.md", "ready_to_upload", "Fixture round-trip."),
    ("docs/backtest/adjusted_ohlc_fixture_cost_diagnostics.md", "ready_to_upload", "Fixture cost diagnostics."),
    ("docs/reports/progress_report.md", "ready_to_upload", "Repository progress report."),
    ("docs/reports/mentor_demo_report.md", "ready_to_upload", "Mentor demo report."),
    ("docs/reports/backtest_mvp_demo_report.md", "ready_to_upload", "Exploratory backtest report with caveats."),
    ("reports/reviewed_evidence/*.md", "external_only", "Ignored/generated reviewed-evidence reports; share externally only."),
    ("data/raw/**", "blocked", "Real raw market data is blocked from this upload package."),
)


def build_manifest(root: str | Path = ROOT) -> dict[str, Any]:
    base = Path(root)
    items = []
    for relative_path, intended_status, note in PACKAGE_ENTRIES:
        virtual = intended_status in {"external_only", "blocked"}
        exists = False if virtual else (base / relative_path).is_file()
        status = intended_status if virtual else ("ready_to_upload" if exists else "missing")
        items.append({"path": relative_path, "exists": exists, "status": status, "note": note})
    return {
        "status": "ok" if all(item["status"] != "missing" for item in items) else "incomplete",
        "items": items,
        "caveats": [
            "Do not upload secrets or unapproved real raw data.",
            "Generated reports remain external and are not committed.",
            "This package does not claim production readiness or provide investment advice.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List the mentor live-demo and Vin-folder package.")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    manifest = build_manifest()
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
