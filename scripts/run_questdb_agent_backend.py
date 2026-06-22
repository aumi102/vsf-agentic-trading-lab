"""Start the read-only QuestDB agent backend.

  python scripts\run_questdb_agent_backend.py --host 127.0.0.1 --port 8010

Zero external dependencies (Python stdlib http.server). This does NOT touch
ingestion; it only serves read-only queries against QuestDB.
"""
from __future__ import annotations

import argparse
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

from trading_agent.backend.app import serve  # noqa: E402
from trading_agent.tools import questdb_market_data_tool as tool  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Run the QuestDB agent backend (stdlib HTTP).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8010)
    p.add_argument("--questdb-url", default=tool.DEFAULT_URL)
    args = p.parse_args()
    serve(host=args.host, port=args.port, questdb_url=args.questdb_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
