"""DeepAgents (LLM tool-calling) CLI demo over QuestDB — read-only.

  python scripts\demo_deepagents_questdb_cli.py "how many rows are in QuestDB"
  python scripts\demo_deepagents_questdb_cli.py "show latest FPT data"
  python scripts\demo_deepagents_questdb_cli.py "backtest MA strategy for FPT from 2020 to 2025"
  python scripts\demo_deepagents_questdb_cli.py --model gpt-4.1-mini "show latest FPT data"

Requires `deepagents`/`langchain-openai` installed and OPENAI_API_KEY set.
If unavailable it prints a clean error (use the rule-based demo instead).
"""
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

from trading_agent.agent.deepagents_questdb_service import answer_query_deepagents  # noqa: E402


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="DeepAgents QuestDB CLI demo (read-only).")
    p.add_argument("query", nargs="+", help="Natural-language query.")
    p.add_argument("--model", default=None, help="Override model (else VSF_DEEPAGENTS_MODEL or gpt-4.1-mini).")
    p.add_argument("--questdb-url", default="http://localhost:9000")
    p.add_argument("--timeout-seconds", type=int, default=60)
    args = p.parse_args(argv)
    message = " ".join(args.query)

    print(f'> "{message}"')
    result = answer_query_deepagents(
        message, questdb_url=args.questdb_url, model=args.model, timeout_seconds=args.timeout_seconds
    )
    print(f"mode        : {result.get('mode')}   status: {result.get('status')}")
    print("tool_calls  :")
    for call in result.get("tool_calls", []) or []:
        print(f"  - {call.get('tool')} args={json.dumps(call.get('args', {}), ensure_ascii=False)} "
              f"status={call.get('status')} rows={call.get('row_count')}")
    if not result.get("tool_calls"):
        print("  (none)")
    print("answer      :")
    for line in (result.get("answer_markdown") or "").splitlines():
        print(f"  {line}")
    print("caveats     :")
    for c in result.get("caveats", []) or []:
        print(f"  - {c}")
    return 0 if result.get("status") in {"ok", "unsupported"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
