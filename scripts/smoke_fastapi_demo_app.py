"""Smoke-test a running FastAPI demo console.

  python scripts\smoke_fastapi_demo_app.py --base-url http://127.0.0.1:8010

Assumes the server is already running (start it with run_fastapi_demo_app.py).
Read-only: it only issues GET/POST against the demo endpoints. Prints a PASS/FAIL
summary and exits non-zero if any check fails. Uses only the stdlib so it runs in
the core (no-pandas) environment too.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


def _get(base: str, path: str, timeout: float = 60.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # connection refused etc.
        return 0, f"{type(exc).__name__}: {exc}"


def _post(base: str, path: str, body: dict, timeout: float = 120.0) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def _json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the FastAPI demo console.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    # 1) /demo is HTML
    code, body = _get(base, "/demo")
    record("/demo returns HTML", code == 200 and "<!DOCTYPE html>" in body, f"status={code}")

    # 2) key GET endpoints return valid JSON and are not 500
    get_endpoints = [
        "/health", "/api/demo/menu", "/api/demo/status", "/api/demo/validation",
        "/api/demo/readiness", "/api/demo/market/FPT", "/api/demo/fa/FPT",
        "/api/demo/backtest/FPT", "/api/demo/backtest/FPT/slippage",
        "/api/demo/backtest/FPT/simple-engine",
        "/api/demo/backtest/FPT/simple-engine/logic",
        "/api/demo/backtest/FPT/simple-engine/variants",
        "/api/demo/events/FPT", "/api/demo/events/VNM",
        "/api/demo/trace/examples", "/api/demo/next-actions",
        "/api/demo/benchmark/questdb",
    ]
    for path in get_endpoints:
        code, body = _get(base, path)
        data = _json(body)
        record(f"GET {path} non-500 JSON", code not in (0, 500) and data is not None, f"status={code}")

    # 2a) SimpleEngine logic endpoint exposes the explicit assumptions block.
    code, body = _get(base, "/api/demo/backtest/FPT/simple-engine/logic")
    logic = (_json(body) or {}).get("logic") or {}
    required_logic_keys = [
        "data_source", "price_input", "signal_formula", "execution_timing",
        "position_sizing", "commission", "slippage", "metrics",
        "why_differs_from_backtrader",
    ]
    missing = [k for k in required_logic_keys if k not in logic]
    record("/logic has required assumption keys", not missing and code == 200,
           f"status={code} missing={missing} signal='{(logic.get('signal_formula') or '')[:40]}'")

    # 2b) SimpleEngine variant lab returns multiple variants + a baseline row.
    code, body = _get(base, "/api/demo/backtest/FPT/simple-engine/variants")
    data = _json(body) or {}
    rows = data.get("rows") or []
    baseline_id = data.get("baseline_id")
    baseline_row = next((r for r in rows if r.get("variant") == baseline_id), None) if baseline_id else None
    record("/variants returns >=7 rows", code == 200 and len(rows) >= 7, f"status={code} rows={len(rows)}")
    record("/variants has baseline row", baseline_row is not None,
           f"baseline_id={baseline_id} found={baseline_row is not None}")
    non_baseline_narratives = [r.get("narrative") for r in rows if r.get("variant") != baseline_id]
    record("/variants non-baseline rows carry narratives",
           all(n for n in non_baseline_narratives) and len(non_baseline_narratives) >= 6,
           f"narratives={sum(1 for n in non_baseline_narratives if n)}/{len(non_baseline_narratives)}")

    # 2c) SimpleEngine main endpoint now embeds the same logic block.
    code, body = _get(base, "/api/demo/backtest/FPT/simple-engine")
    se = _json(body) or {}
    record("/simple-engine embeds logic block", code == 200 and "logic" in se and isinstance(se["logic"], dict),
           f"status={code} has_logic={('logic' in se)}")

    # 3) /api/demo/validation no longer crashes (must be 200 + has gates)
    code, body = _get(base, "/api/demo/validation")
    data = _json(body) or {}
    record("/api/demo/validation 200 with gates", code == 200 and isinstance(data.get("gates"), list),
           f"status={code} overall={data.get('overall_status')}")

    # 4) summary CTG -> market_summary / MarketDataAgent (not SYSTEM)
    code, body = _post(base, "/api/demo/ask", {"query": "summary CTG", "mode": "deep"})
    data = _json(body) or {}
    agents = [a.get("agent_name") for a in (data.get("trace", {}).get("agents") or [])]
    record("ask summary CTG -> market_summary", data.get("domain") == "market_summary" and "MarketDataAgent" in agents,
           f"domain={data.get('domain')} agents={agents}")
    record("ask summary CTG -> no SystemAgent", "SystemAgent" not in agents, f"agents={agents}")

    # 5) latest news VNM -> event_news and rejects OHLCV proxy
    code, body = _post(base, "/api/demo/ask", {"query": "latest news VNM", "mode": "deep"})
    data = _json(body) or {}
    router = (data.get("trace", {}).get("agents") or [{}])[0]
    rejected = router.get("rejected_tools", [])
    record("ask latest news VNM -> event_news", data.get("domain") == "event_news", f"domain={data.get('domain')}")
    record("ask latest news VNM rejects OHLCV proxy", "get_latest_ohlcv" in rejected, f"rejected={rejected}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"FastAPI demo smoke  base={base}")
    print("-" * 64)
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{('  (' + detail + ')') if detail and not ok else ''}")
    print("-" * 64)
    print(f"SMOKE_RESULT={'PASS' if passed == len(checks) else 'FAIL'}  ({passed}/{len(checks)})")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
