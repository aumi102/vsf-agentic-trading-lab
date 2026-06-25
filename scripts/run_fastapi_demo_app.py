"""Run the FastAPI demo console.

  uv run python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010
  (or)  python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010

Then open http://127.0.0.1:8010/demo in a browser. Read-only: serves persisted
QuestDB data and safe in-process diagnostics. Never runs live Backtrader.
"""
from __future__ import annotations

import argparse
import os
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FastAPI demo console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--questdb-url", default=os.environ.get("QUESTDB_URL", "http://localhost:9000"))
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn autoreload (dev only).")
    args = parser.parse_args()

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "FastAPI/uvicorn are not installed. Install with one of:\n"
            "  uv sync --extra api\n"
            "  python -m pip install fastapi uvicorn psycopg[binary,pool]\n"
            "The stdlib backend remains available via scripts/run_questdb_agent_backend.py.",
            file=sys.stderr,
        )
        return 1

    os.environ.setdefault("QUESTDB_URL", args.questdb_url)
    from trading_agent.api.fastapi_app import create_app

    app = create_app(questdb_url=args.questdb_url)
    print(f"VSF FastAPI demo console -> http://{args.host}:{args.port}/demo  (QuestDB={args.questdb_url})")
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
