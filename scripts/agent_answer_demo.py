from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.agent.orchestrator import answer_market_query
from trading_agent.tools._store import DEFAULT_DB_PATH


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the deterministic agent-facing market answer demo.")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    result = answer_market_query(
        query=args.query or None,
        symbol=args.symbol or None,
        db_path=args.db_path,
        language="vi",
    )
    print(json.dumps(_summary(result), ensure_ascii=False, indent=2, sort_keys=True))
    print("## final_answer")
    print(result["answer_markdown"])
    return 0 if result["status"] == "ok" else 1


def _summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": result.get("status"),
        "symbol": result.get("symbol"),
        "query": result.get("query"),
        "tool_call_sequence": result.get("tool_call_sequence"),
        "caveats": result.get("caveats"),
        "not_financial_advice": result.get("not_financial_advice"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
