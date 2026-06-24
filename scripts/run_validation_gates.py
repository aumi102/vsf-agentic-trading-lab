"""Run read-only validation gates for the QuestDB-backed mentor demo."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

from trading_agent.validation.gates import render_markdown, render_text, run_all_gates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only validation gates.")
    parser.add_argument("--questdb-url", default="http://localhost:9000")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--write-report", help="Write a Markdown report path.")
    args = parser.parse_args()

    report = run_all_gates(args.questdb_url)
    if args.write_report:
        path = Path(args.write_report)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report), encoding="utf-8")
        print(f"report_written={path}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_text(report))
    return 1 if report["overall_status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
