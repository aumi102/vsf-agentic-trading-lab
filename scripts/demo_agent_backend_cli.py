"""CLI client for the QuestDB agent — direct service mode or HTTP API mode.

Direct (in-process, no server):
  python scripts\demo_agent_backend_cli.py "show latest FPT data"

API mode (talks to a running backend):
  python scripts\demo_agent_backend_cli.py --api-url http://127.0.0.1:8010 "show latest FPT data"
  python scripts\demo_agent_backend_cli.py --api-url http://127.0.0.1:8010 "backtest MA strategy for FPT from 2020 to 2025"

Prints: intent, tool calls, answer markdown, caveats.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


def via_api(api_url: str, message: str) -> dict:
    body = json.dumps({"message": message}).encode("utf-8")
    req = Request(f"{api_url.rstrip('/')}/agent/chat", data=body,
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def via_direct(message: str, questdb_url: str) -> dict:
    from trading_agent.agent.questdb_agent_service import answer_query
    return answer_query(message, questdb_url=questdb_url)


def render(result: dict) -> None:
    print(f"intent      : {result.get('intent')}   status: {result.get('status')}")
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
    if not result.get("caveats"):
        print("  (none)")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="QuestDB agent CLI client (direct or API).")
    p.add_argument("query", nargs="+", help="Natural-language query.")
    p.add_argument("--api-url", default="", help="Backend URL; if omitted, runs the service in-process.")
    p.add_argument("--questdb-url", default="http://localhost:9000", help="Used only in direct mode.")
    args = p.parse_args(argv)
    message = " ".join(args.query)

    print(f'> "{message}"')
    mode = "api" if args.api_url else "direct"
    print(f"mode        : {mode}{(' ' + args.api_url) if args.api_url else ''}")
    try:
        result = via_api(args.api_url, message) if args.api_url else via_direct(message, args.questdb_url)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    render(result)
    return 0 if result.get("status") in {"ok", "unsupported"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
