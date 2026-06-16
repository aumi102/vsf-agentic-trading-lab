from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.agent.demo_runner import SUPPORTED_SCENARIOS, run_demo
from trading_agent.tools._store import DEFAULT_DB_PATH


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run mentor-facing agent demo scenarios.")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=list(SUPPORTED_SCENARIOS),
        help="Demo scenario to run.",
    )
    parser.add_argument("--symbol", default="", help="Single symbol (market_brief, risk_check).")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols (compare).")
    parser.add_argument("--query", default="", help="Natural-language query (market_brief).")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    symbols_list = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else None
    )

    result = run_demo(
        scenario=args.scenario,
        symbol=args.symbol or None,
        symbols=symbols_list,
        query=args.query or None,
        db_path=args.db_path,
    )

    print(json.dumps(_summary(result), ensure_ascii=False, indent=2, sort_keys=True))
    print("## final_answer")
    print(result["answer_markdown"])

    return 0 if result.get("status") == "ok" else 1


def _summary(result: dict) -> dict:
    return {
        "status": result.get("status"),
        "scenario": result.get("scenario"),
        "input": result.get("input"),
        "tool_call_trace": result.get("tool_call_trace"),
        "caveats": result.get("caveats"),
        "not_financial_advice": result.get("not_financial_advice"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
