"""Smoke test the DeepAgents mode of a RUNNING backend.

  python scripts\smoke_deepagents_backend.py --api-url http://127.0.0.1:8010

Checks:
  1. /v1/models lists `vsf-questdb-deepagent`        (no API key needed)
  2. /agent/chat with mode=deep                       (live; skipped if no OPENAI_API_KEY)
  3. /v1/chat/completions model=vsf-questdb-deepagent (live; skipped if no OPENAI_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

DEEP_MODEL = "vsf-questdb-deepagent"


def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        code = getattr(exc, "code", 0)
        try:
            return code, json.loads(exc.read().decode("utf-8"))  # type: ignore[attr-defined]
        except Exception:
            return code, {"error": str(exc)}


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke test DeepAgents backend mode.")
    p.add_argument("--api-url", default="http://127.0.0.1:8010")
    p.add_argument("--symbol", default="FPT")
    args = p.parse_args()
    base = args.api_url.rstrip("/")
    have_key = bool(os.environ.get("OPENAI_API_KEY"))

    print(f"smoke (deepagents) backend at {base}  OPENAI_API_KEY_set={have_key}")
    print("-" * 64)
    passed = total = 0

    # 1) models list always testable
    total += 1
    code, payload = _request("GET", f"{base}/v1/models")
    ids = [m.get("id") for m in payload.get("data", [])]
    ok = code == 200 and DEEP_MODEL in ids
    passed += int(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] GET  /v1/models has {DEEP_MODEL:<22} http={code} ids={ids}")

    if not have_key:
        print("-" * 64)
        print("SKIP live DeepAgents checks: OPENAI_API_KEY not set.")
        print("Set OPENAI_API_KEY in the backend's environment, then re-run for the live checks:")
        print("  - POST /agent/chat {mode:deep}")
        print(f"  - POST /v1/chat/completions {{model:{DEEP_MODEL}}}")
        print("-" * 64)
        print(f"{passed}/{total} non-live checks passed")
        return 0 if passed == total else 1

    # 2) /agent/chat mode=deep
    total += 1
    code, payload = _request("POST", f"{base}/agent/chat",
                             {"message": f"show latest {args.symbol} data", "mode": "deep"})
    ok = code == 200 and payload.get("mode") == "deepagents" and payload.get("status") == "ok"
    passed += int(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] POST /agent/chat mode=deep            http={code} status={payload.get('status')}")

    # 3) /v1/chat/completions model=deepagent
    total += 1
    code, payload = _request("POST", f"{base}/v1/chat/completions",
                             {"model": DEEP_MODEL, "stream": False,
                              "messages": [{"role": "user", "content": "how many rows are in QuestDB"}]})
    content = payload.get("choices", [{}])[0].get("message", {}).get("content")
    ok = code == 200 and bool(content)
    passed += int(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] POST /v1/chat/completions deepagent   http={code} has_content={bool(content)}")

    print("-" * 64)
    print(f"{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
