"""Smoke test for a RUNNING QuestDB agent backend.

Start the backend first, then:
  python scripts\smoke_questdb_agent_backend.py --api-url http://127.0.0.1:8010

Hits health, market, derived feature/signal, agent, and OpenAI-compatible routes.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # HTTPError etc.
        code = getattr(exc, "code", 0)
        payload: dict = {}
        try:
            payload = json.loads(exc.read().decode("utf-8"))  # type: ignore[attr-defined]
        except Exception:
            payload = {"error": str(exc)}
        return code, payload


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke test the QuestDB agent backend.")
    p.add_argument("--api-url", default="http://127.0.0.1:8010")
    p.add_argument("--symbol", default="FPT")
    args = p.parse_args()
    base = args.api_url.rstrip("/")

    checks = [
        ("GET  /health", "GET", f"{base}/health", None, lambda c, d: c == 200 and d.get("status") == "ok"),
        ("GET  /questdb/health", "GET", f"{base}/questdb/health", None,
         lambda c, d: c == 200 and d.get("status") == "ok" and "row_count" in d),
        (f"GET  /market/latest/{args.symbol}", "GET", f"{base}/market/latest/{args.symbol}", None,
         lambda c, d: c in (200, 404)),
        (f"GET  /features/latest/{args.symbol}", "GET", f"{base}/features/latest/{args.symbol}", None,
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("data")),
        (f"GET  /signals/latest/{args.symbol}", "GET", f"{base}/signals/latest/{args.symbol}", None,
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("data")),
        (f"GET  /market/summary/{args.symbol}", "GET", f"{base}/market/summary/{args.symbol}", None,
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("data")),
        (f"GET  /backtest/comparison/{args.symbol}", "GET", f"{base}/backtest/comparison/{args.symbol}", None,
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("row_count", 0) >= 1),
        (f"GET  /backtest/latest/{args.symbol}", "GET", f"{base}/backtest/latest/{args.symbol}", None,
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("row_count", 0) >= 1),
        ("POST /agent/chat persisted backtest", "POST", f"{base}/agent/chat", {"message": f"backtest {args.symbol}"},
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("intent") == "backtest_results"
         and any(call.get("tool") == "get_backtest_strategy_comparison" for call in d.get("tool_calls", []))),
        ("POST /agent/chat", "POST", f"{base}/agent/chat", {"message": "how many rows are in QuestDB"},
         lambda c, d: c == 200 and d.get("status") == "ok" and d.get("intent") == "db_health"),
        ("GET  /v1/models", "GET", f"{base}/v1/models", None,
         lambda c, d: c == 200 and d.get("data", [{}])[0].get("id") == "vsf-questdb-agent"),
        ("POST /v1/chat/completions", "POST", f"{base}/v1/chat/completions",
         {"model": "vsf-questdb-agent", "stream": False,
          "messages": [{"role": "user", "content": "show latest " + args.symbol + " data"}]},
         lambda c, d: c == 200 and d.get("choices", [{}])[0].get("message", {}).get("content")),
        ("POST /v1/chat/completions (stream rejected)", "POST", f"{base}/v1/chat/completions",
         {"stream": True, "messages": [{"role": "user", "content": "hi"}]},
         lambda c, d: c == 400 and "error" in d),
    ]

    passed = 0
    print(f"smoke test backend at {base}")
    print("-" * 60)
    for name, method, url, body, check in checks:
        code, payload = _request(method, url, body)
        ok = False
        try:
            ok = bool(check(code, payload))
        except Exception:
            ok = False
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        detail = json.dumps(payload, ensure_ascii=False)
        print(f"[{status}] {name:<42} http={code} {detail[:90]}")
    print("-" * 60)
    print(f"{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
