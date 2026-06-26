"""FastAPI demo console for the QuestDB-backed trading agent.

Mentor feedback #1: the demo must be menu-driven, not a wall of terminal commands.
This app exposes:

  * a browser console at ``/demo`` (buttons -> result + anti-blackbox trace);
  * JSON APIs under ``/api/demo/*`` that every button calls;
  * the legacy backend endpoints (``/health``, ``/v1/*``, ``/market/summary/*`` ...)
    so existing clients keep working.

It is strictly read-only: it reads persisted QuestDB data and runs safe in-process
diagnostics. It never runs live Backtrader and never mutates any table.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from trading_agent.agent.deepagents_questdb_service import answer_query_deepagents
from trading_agent.agent.questdb_agent_service import answer_query
from trading_agent.backend import app as legacy
from trading_agent.backtest import simple_engine as se
from trading_agent.observability import next_actions as na
from trading_agent.observability import pipeline_trace as pt
from trading_agent.storage import questdb_pgwire_client as pg
from trading_agent.storage import questdb_read as qr
from trading_agent.tools import questdb_backtest_result_tool as backtest_tool
from trading_agent.tools import questdb_market_data_tool as market

HERE = Path(__file__).resolve().parent
CONSOLE_HTML = HERE / "demo_console.html"
DEMO_SYMBOL = "FPT"

# Representative probe SQL per domain so every demo envelope can report real
# query_mode / execute_ms / total_ms timing (mentor feedback #6).
PROBE_SQL: dict[str, Callable[[str], str]] = {
    "market_summary": lambda s: f"SELECT trade_date, close, adjusted_close, volume FROM daily_prices WHERE symbol = '{s}' ORDER BY trade_date DESC LIMIT 1",
    "financial_report": lambda s: f"SELECT public_date, statement_type, metric_code FROM fa_balance_sheet WHERE symbol = '{s}' ORDER BY public_date DESC LIMIT 1",
    "backtest": lambda s: f"SELECT r.strategy_id, m.final_value FROM backtest_runs r JOIN backtest_metrics m ON r.run_id = m.run_id WHERE r.symbol = '{s}' AND r.slippage_bps = 0.0",
    "event_news": lambda s: f"SELECT published_at, title FROM event_news_items WHERE symbol = '{s}' ORDER BY published_at DESC LIMIT 5",
    "system": lambda s: "SELECT count() FROM daily_prices",
}

MENU = [
    {"id": "status", "label": "System status", "group": "Diagnostics", "method": "GET", "path": "/api/demo/status",
     "description": "QuestDB table health, FA latest run, backtest coverage."},
    {"id": "validation", "label": "Validation gates", "group": "Diagnostics", "method": "GET", "path": "/api/demo/validation",
     "description": "Fast read-only data gates (no docker/subprocess)."},
    {"id": "readiness", "label": "Mentor readiness", "group": "Diagnostics", "method": "GET", "path": "/api/demo/readiness",
     "description": "In-process routing readiness for the demo queries."},
    {"id": "market", "label": "Market summary FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/market/FPT",
     "description": "Latest OHLCV + features + deterministic signal."},
    {"id": "fa", "label": "Financial report FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/fa/FPT",
     "description": "Persisted Vietcap FA facts (read-time metric names)."},
    {"id": "backtest", "label": "Backtest comparison FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/backtest/FPT",
     "description": "Persisted Backtrader strategy comparison (no live run)."},
    {"id": "slippage", "label": "Slippage scenarios FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/backtest/FPT/slippage",
     "description": "Persisted 0/5/10/15 bps slippage scenarios."},
    {"id": "simple_engine", "label": "SimpleEngine vs Backtrader FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/backtest/FPT/simple-engine",
     "description": "Transparent self-implemented engine vs persisted Backtrader."},
    {"id": "simple_engine_logic", "label": "SimpleEngine logic FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/backtest/FPT/simple-engine/logic",
     "description": "Exact signal/execution/sizing/cost logic, made explicit."},
    {"id": "simple_engine_variants", "label": "Strategy logic lab FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/backtest/FPT/simple-engine/variants",
     "description": "Deterministic ablations: price input, execution, capital, slippage, volume, RSI."},
    {"id": "events_fpt", "label": "Latest disclosure FPT", "group": "Agent answers", "method": "GET", "path": "/api/demo/events/FPT",
     "description": "Official disclosure records for FPT."},
    {"id": "events_vnm", "label": "Event guardrail VNM", "group": "Guardrails", "method": "GET", "path": "/api/demo/events/VNM",
     "description": "Shows 'unavailable' (no OHLCV proxy) for VNM."},
    {"id": "trace", "label": "Pipeline trace examples", "group": "Anti-blackbox", "method": "GET", "path": "/api/demo/trace/examples",
     "description": "Full anti-blackbox traces for each domain."},
    {"id": "benchmark", "label": "Query benchmark", "group": "Performance", "method": "GET", "path": "/api/demo/benchmark/questdb",
     "description": "REST vs PGWire timing on representative reads."},
    {"id": "next", "label": "Next recommended actions", "group": "Diagnostics", "method": "GET", "path": "/api/demo/next-actions",
     "description": "Prioritized next steps from current state."},
]


class TTLCache:
    """Tiny in-process TTL cache for non-mutating read results."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, ttl: float) -> Any | None:
        item = self._store.get(key)
        if item and (time.monotonic() - item[0]) <= ttl:
            return item[1]
        return None

    def put(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)


def _resolve_mode(request: Request) -> str:
    return qr.resolve_mode(request.query_params.get("mode"))


def _timed_probe(domain: str, symbol: str, mode: str, url: str) -> dict[str, Any]:
    """Run the domain's representative read and return its timing block."""
    sql_builder = PROBE_SQL.get(domain, PROBE_SQL["system"])
    res = qr.run_read_query(sql_builder(symbol), mode=mode, url=url)
    timing = dict(res.get("timing", {}))
    timing["query_mode"] = res.get("query_mode", mode)
    return timing


def _domain_next_action(domain: str, states: dict[str, Any]) -> dict[str, Any] | None:
    mapping = {
        "market_summary": None,
        "financial_report": "fa_mapping",
        "backtest": "backtest_slippage",
        "event_news": "event_news",
    }
    area = mapping.get(domain)
    if not area:
        return None
    full = na.compute_next_actions(url=market.DEFAULT_URL)
    for action in full["next_actions"]:
        if action["area"] in {area, "slippage_model" if area == "backtest_slippage" else area}:
            return action
    return None


def _envelope_from_query(query: str, *, mode: str, url: str, deep: bool = False) -> dict[str, Any]:
    """Run a canonical agent query and wrap it with trace + timing + next action."""
    start = time.perf_counter()
    result = answer_query_deepagents(query, questdb_url=url) if deep else answer_query(query, questdb_url=url)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    domain, intent = pt.derive_domain(query, result)
    trace = pt.trace_from_rule_result(query, result, query_mode=mode.upper())
    timing = _timed_probe(domain, _symbol_of(query) or DEMO_SYMBOL, mode, url)
    states = na.compute_next_actions(url=url)["states"]
    return {
        "action": query,
        "domain": domain,
        "status": result.get("status"),
        "answer_markdown": result.get("answer_markdown"),
        "result": result.get("data"),
        "rows": result.get("data", {}).get("rows") if isinstance(result.get("data"), dict) else None,
        "tool_calls": result.get("tool_calls", []),
        "trace": trace,
        "caveats": result.get("caveats", []),
        "next_action": _domain_next_action(domain, states),
        "timing": timing,
        "elapsed_ms": round(elapsed_ms, 3),
        "mode": result.get("mode", "deep" if deep else "rule"),
    }


def _symbol_of(query: str) -> str | None:
    from trading_agent.agent.questdb_agent_service import extract_symbol

    return extract_symbol(query)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    qr.close_all()  # close pooled REST/PGWire connections on shutdown


def create_app(questdb_url: str | None = None) -> FastAPI:
    url = questdb_url or market.DEFAULT_URL
    app = FastAPI(title="VSF QuestDB Agent — Demo Console", version="1.0.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    cache = TTLCache()

    def _json(code: int, payload: dict) -> JSONResponse:
        return JSONResponse(status_code=code, content=payload)

    @app.exception_handler(Exception)
    async def _demo_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a structured JSON error so the browser never sees raw 500 text."""
        import sys
        import traceback

        path = request.url.path
        print(f"[demo-error] {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error_type": type(exc).__name__,
                "message": _redact(str(exc))[:600],
                "path": path,
                "caveats": ["demo endpoint failed; see server logs"],
                "next_action": "fix missing optional dependency or import side-effect",
            },
        )

    # ---- browser UI --------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    @app.get("/demo", response_class=HTMLResponse)
    async def demo_console() -> HTMLResponse:
        if CONSOLE_HTML.exists():
            return HTMLResponse(CONSOLE_HTML.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>demo_console.html missing</h1>", status_code=500)

    # ---- demo JSON APIs ----------------------------------------------------
    @app.get("/api/demo/menu")
    async def demo_menu() -> dict:
        return {"service": legacy.SERVICE_NAME, "default_symbol": DEMO_SYMBOL, "menu": MENU,
                "query_mode_default": qr.resolve_mode(None), "pgwire_available": pg.pgwire_available()}

    @app.get("/api/demo/status")
    async def demo_status(request: Request) -> dict:
        cached = cache.get("status", ttl=10.0)
        if cached:
            return cached
        payload = await asyncio.to_thread(_build_status, url)
        cache.put("status", payload)
        return payload

    @app.get("/api/demo/validation")
    async def demo_validation() -> dict:
        cached = cache.get("validation", ttl=15.0)
        if cached:
            return cached
        payload = await asyncio.to_thread(_build_validation, url)
        cache.put("validation", payload)
        return payload

    @app.get("/api/demo/readiness")
    async def demo_readiness() -> dict:
        cached = cache.get("readiness", ttl=20.0)
        if cached:
            return cached
        payload = await asyncio.to_thread(_build_readiness, url)
        cache.put("readiness", payload)
        return payload

    @app.get("/api/demo/market/{symbol}")
    async def demo_market(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_envelope_from_query, f"summary {symbol.upper()}", mode=mode, url=url)

    @app.get("/api/demo/fa/{symbol}")
    async def demo_fa(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_envelope_from_query, f"financial report {symbol.upper()}", mode=mode, url=url)

    @app.get("/api/demo/backtest/{symbol}/slippage")
    async def demo_slippage(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_build_slippage, symbol.upper(), mode, url)

    @app.get("/api/demo/backtest/{symbol}/simple-engine/logic")
    async def demo_simple_engine_logic(symbol: str) -> dict:
        return await asyncio.to_thread(_build_simple_engine_logic, symbol.upper(), url)

    @app.get("/api/demo/backtest/{symbol}/simple-engine/variants")
    async def demo_simple_engine_variants(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_build_variants, symbol.upper(), mode, url)

    @app.get("/api/demo/backtest/{symbol}/simple-engine")
    async def demo_simple_engine(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_build_simple_engine, symbol.upper(), mode, url)

    @app.get("/api/demo/backtest/{symbol}")
    async def demo_backtest(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_envelope_from_query, f"compare backtest strategies {symbol.upper()}", mode=mode, url=url)

    @app.get("/api/demo/events/{symbol}")
    async def demo_events(symbol: str, request: Request) -> dict:
        mode = _resolve_mode(request)
        return await asyncio.to_thread(_envelope_from_query, f"latest news {symbol.upper()}", mode=mode, url=url)

    @app.post("/api/demo/ask")
    async def demo_ask(request: Request) -> JSONResponse:
        body = await _read_json(request)
        message = str(body.get("message") or body.get("query") or "").strip()
        if not message:
            return _json(400, {"status": "error", "caveats": ["message (or query) is required"]})
        deep = str(body.get("mode", "rule")).lower() == "deep"
        mode = qr.resolve_mode(body.get("query_mode"))
        payload = await asyncio.to_thread(_envelope_from_query, message, mode=mode, url=url, deep=deep)
        return _json(200, payload)

    @app.get("/api/demo/trace/examples")
    async def demo_trace_examples() -> dict:
        cached = cache.get("trace_examples", ttl=20.0)
        if cached:
            return cached
        payload = await asyncio.to_thread(_build_trace_examples, url)
        cache.put("trace_examples", payload)
        return payload

    @app.get("/api/demo/benchmark/questdb")
    async def demo_benchmark() -> dict:
        cached = cache.get("benchmark", ttl=30.0)
        if cached:
            return cached
        payload = await asyncio.to_thread(_build_benchmark, url)
        cache.put("benchmark", payload)
        return payload

    @app.get("/api/demo/next-actions")
    async def demo_next_actions() -> dict:
        cached = cache.get("next_actions", ttl=15.0)
        if cached:
            return cached
        bench = cache.get("benchmark", ttl=30.0)
        hint = "pgwire" if bench and bench.get("recommendation_mode") == "pgwire" else None
        payload = await asyncio.to_thread(na.compute_next_actions, url, query_mode_recommendation=hint)
        cache.put("next_actions", payload)
        return payload

    # ---- legacy endpoints (preserved) --------------------------------------
    @app.get("/health")
    async def health() -> dict:
        return legacy.handle_health(url)[1]

    @app.get("/questdb/health")
    async def questdb_health() -> JSONResponse:
        code, payload = await asyncio.to_thread(legacy.handle_questdb_health, url)
        return _json(code, payload)

    @app.get("/v1/models")
    async def v1_models() -> dict:
        return legacy.handle_models(url)[1]

    @app.post("/v1/chat/completions")
    async def v1_chat(request: Request) -> JSONResponse:
        body = await _read_json(request)
        code, payload = await asyncio.to_thread(legacy.handle_chat_completions, url, body)
        return _json(code, payload)

    @app.get("/market/summary/{symbol}")
    async def market_summary(symbol: str) -> JSONResponse:
        code, payload = await asyncio.to_thread(legacy._handle_derived_latest, url, symbol, "summary")
        return _json(code, payload)

    @app.get("/backtest/comparison/{symbol}")
    async def backtest_comparison(symbol: str, request: Request) -> JSONResponse:
        code, payload = await asyncio.to_thread(
            legacy.handle_backtest_comparison, url, symbol, dict(request.query_params and _multi(request))
        )
        return _json(code, payload)

    @app.get("/backtest/slippage-scenarios/{symbol}")
    async def backtest_slippage(symbol: str, request: Request) -> JSONResponse:
        code, payload = await asyncio.to_thread(
            legacy.handle_backtest_slippage_scenarios, url, symbol, _multi(request)
        )
        return _json(code, payload)

    @app.get("/events/latest/{symbol}")
    async def events_latest(symbol: str, request: Request) -> JSONResponse:
        code, payload = await asyncio.to_thread(legacy.handle_event_news_latest, url, symbol, _multi(request))
        return _json(code, payload)

    return app


# --- blocking builders (run in a worker thread) -----------------------------
def _build_status(url: str) -> dict[str, Any]:
    health_code, health = legacy.handle_questdb_health(url)
    fa_run = market.query_questdb(
        "SELECT run_id, status, symbols_processed, failure_count, created_at FROM fa_ingest_runs "
        "WHERE status = 'complete' ORDER BY created_at DESC LIMIT 1",
        url=url,
    )
    bt = market.query_questdb(
        "SELECT count_distinct(symbol) symbols, count_distinct(strategy_id) strategies, count() runs FROM backtest_runs",
        url=url,
    )
    counts = market.query_questdb(
        "SELECT "
        "(SELECT count() FROM daily_prices) daily_prices, "
        "(SELECT count() FROM feature_snapshots) feature_snapshots, "
        "(SELECT count() FROM signals) signals, "
        "(SELECT count() FROM backtest_trades) backtest_trades",
        url=url,
    )
    return {
        "status": "ok" if health_code == 200 else "error",
        "questdb_health": health,
        "fa_latest_complete_run": (fa_run["rows"][0] if fa_run.get("rows") else None),
        "backtest_summary": (bt["rows"][0] if bt.get("rows") else None),
        "pipeline_counts": (counts["rows"][0] if counts.get("rows") else None),
        "caveats": health.get("caveats", []),
    }


def _build_validation(url: str) -> dict[str, Any]:
    """Fast read-only data gates only (skip docker/subprocess gates)."""
    from trading_agent.validation import gates as G

    fast_gates = [
        ("market_table_coverage", G.market_table_coverage),
        ("feature_signal_parity", G.feature_signal_parity),
        ("adjusted_ohlc_gate", G.adjusted_ohlc_gate),
        ("exchange_metadata_gate", G.exchange_metadata_gate),
        ("fa_tables_gate", G.fa_tables_gate),
        ("fa_mapping_gate", G.fa_mapping_gate),
        ("backtest_tables_gate", G.backtest_tables_gate),
        ("backtest_execution_assumptions_gate", G.backtest_execution_assumptions_gate),
        ("event_news_gate_fast", _fast_event_news_gate),
    ]
    results = [G._safe_gate(name, func, url).to_dict() for name, func in fast_gates]
    overall = "FAIL" if any(g["status"] == "FAIL" and g["blocking"] for g in results) else (
        "WARN" if any(g["status"] in {"WARN", "FAIL"} for g in results) else "PASS"
    )
    return {
        "overall_status": overall,
        "scope": "fast_data_gates (docker + agent-guardrail gates excluded; run scripts/run_validation_gates.py for the full suite)",
        "gates": results,
    }


def _fast_event_news_gate(url: str):
    """Event/news coverage gate WITHOUT the subprocess agent check (demo-fast)."""
    from trading_agent.validation import gates as G

    state = na.event_news_state(url)
    status = "PASS" if state["status"] == "PASS" else "WARN"
    caveats = [] if status == "PASS" else [f"event/news demo coverage partial; missing {', '.join(state['missing_demo_symbols'])}"]
    return G._gate("event_news_gate_fast", status, state, caveats, "Expand official disclosure source coverage for VNM/HPG.")


def _build_readiness(url: str) -> dict[str, Any]:
    """In-process routing readiness for the demo queries (fast, no subprocess)."""
    checks: list[dict[str, Any]] = []

    def add(name: str, query: str, expect: Callable[[dict], tuple[str, str]]) -> None:
        res = answer_query(query, questdb_url=url)
        status, reason = expect(res)
        checks.append({
            "name": name, "query": query, "status": status, "reason": reason,
            "intent": res.get("intent"), "result_status": res.get("status"),
            "tool_calls": [c.get("tool") for c in res.get("tool_calls", [])],
        })

    def market_ok(res: dict) -> tuple[str, str]:
        tools = {c.get("tool") for c in res.get("tool_calls", [])}
        bad = tools & {"get_latest_financial_report", "get_backtest_strategy_comparison"}
        if bad:
            return "FAIL", f"market route leaked into {sorted(bad)}"
        return ("PASS", "used market tools") if tools & {"get_symbol_summary", "get_latest_ohlcv", "get_latest_features", "get_latest_signal"} else ("WARN", "no market tool recorded")

    def fa_ok(res: dict) -> tuple[str, str]:
        tools = {c.get("tool") for c in res.get("tool_calls", [])}
        return ("PASS", "used FA tools") if tools & {"get_latest_financial_report", "get_financial_report_summary"} else ("WARN", "no FA tool recorded")

    def event_ok(res: dict) -> tuple[str, str]:
        tools = {c.get("tool") for c in res.get("tool_calls", [])}
        if tools & {"get_latest_ohlcv", "get_symbol_summary"}:
            return "FAIL", "event route used OHLCV proxy"
        return "PASS", "no OHLCV proxy; event tool or unavailable"

    def backtest_ok(res: dict) -> tuple[str, str]:
        tools = {c.get("tool") for c in res.get("tool_calls", [])}
        if tools & {"run_ma_backtest", "run_backtrader"}:
            return "FAIL", "used live Backtrader tool"
        return ("PASS", "used persisted comparison") if "get_backtest_strategy_comparison" in tools else ("WARN", "no persisted comparison tool recorded")

    add("market_summary_FPT", "summary FPT", market_ok)
    add("financial_report_FPT", "financial report FPT", fa_ok)
    add("event_guardrail_FPT", "latest news FPT", event_ok)
    add("backtest_comparison_FPT", "compare backtest strategies FPT", backtest_ok)

    final = "FAIL" if any(c["status"] == "FAIL" for c in checks) else ("WARN" if any(c["status"] == "WARN" for c in checks) else "PASS")
    return {
        "final_status": final,
        "scope": "in_process routing readiness; run scripts/run_mentor_demo_readiness.py --deepagents for the full live suite",
        "checks": checks,
    }


def _build_slippage(symbol: str, mode: str, url: str) -> dict[str, Any]:
    start = time.perf_counter()
    res = backtest_tool.get_backtest_slippage_scenarios(symbol, url=url)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    trace = pt.PipelineTrace(f"slippage scenarios {symbol}", "backtest")
    trace.add_agent(pt.router_step("backtest", f"slippage scenarios {symbol}", "backtest_results"))
    trace.add_agent(
        pt.specialist_step(
            "backtest",
            decision=f"answered using get_backtest_slippage_scenarios ({res.get('row_count', 0)} rows)",
            reason="Used persisted backtest rows across 0/5/10/15 bps; no live Backtrader execution.",
            input_summary=f"slippage scenarios {symbol}",
            tool_calls=res.get("tool_calls", []),
            caveats=res.get("caveats", []),
        )
    )
    trace.set_final_basis(tables=["backtest_runs", "backtest_metrics"], query_mode=mode.upper(), caveats=res.get("caveats", []))
    return {
        "action": f"slippage scenarios {symbol}",
        "domain": "backtest",
        "status": res.get("status"),
        "rows": res.get("rows", []),
        "tool_calls": res.get("tool_calls", []),
        "trace": trace.to_dict(),
        "caveats": res.get("caveats", []),
        "timing": _timed_probe("backtest", symbol, mode, url),
        "elapsed_ms": round(elapsed_ms, 3),
    }


def _build_simple_engine(symbol: str, mode: str, url: str, *, strategy: str = "ma20_ma50", slippage_bps: float = 0.0) -> dict[str, Any]:
    """Run the transparent SimpleEngine and compare to persisted Backtrader (read-only)."""
    start = time.perf_counter()
    try:
        bars, data_caveats = se.load_bars_from_questdb(symbol, "2020-01-01", "2025-12-31", adjusted=True, url=url)
        exchange = se.fetch_exchange(symbol, url=url)
        out = se.run_simple_backtest(bars, symbol=symbol, strategy=strategy, slippage_bps=slippage_bps, exchange=exchange)
    except Exception as exc:
        return {
            "action": f"simple-engine {symbol}", "domain": "backtest", "status": "error",
            "error_type": type(exc).__name__, "message": str(exc)[:300],
            "caveats": ["SimpleEngine could not load/run for this symbol"],
        }
    persisted_res = backtest_tool.get_latest_backtest_metrics(symbol, strategy_id=strategy, slippage_bps=slippage_bps, url=url)
    persisted = persisted_res["rows"][0] if persisted_res.get("status") == "ok" and persisted_res.get("rows") else None
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    sm = out.metrics
    keys = [
        ("final_value", "final_value"), ("total_return_pct", "total_return_pct"),
        ("annualized_return_pct", "annualized_return_pct"), ("max_drawdown_pct", "max_drawdown_pct"),
        ("sharpe_ratio", "sharpe_ratio"), ("closed_trades", "closed_trades"), ("win_rate_pct", "win_rate_pct"),
    ]
    comparison = [
        {"metric": label, "simple_engine": sm.get(skey), "backtrader": (persisted.get(skey) if persisted else None)}
        for label, skey in keys
    ]
    answer = (
        f"**SimpleEngine vs persisted Backtrader — {symbol} {strategy} @ {slippage_bps:g} bps**\n"
        f"- execution: next-bar-open · target 0.95 · commission 0.001 · fractional shares\n"
        f"- SimpleEngine final value {sm.get('final_value')}, total return {sm.get('total_return_pct')}%\n"
        "- differences are expected/explainable: SimpleEngine sizes from close[t] and fills at open[t+1]; "
        "Sharpe differs by definition; trade counting differs (long round trips vs Backtrader closed trades)."
    )
    trace = pt.PipelineTrace(f"simple-engine {symbol}", "backtest")
    trace.add_agent(pt.router_step("backtest", f"simple-engine {symbol}", "backtest_results"))
    trace.add_agent(
        pt.specialist_step(
            "backtest",
            decision=f"ran self-implemented engine on {symbol} and read persisted Backtrader metrics",
            reason="Transparent in-process engine for explainability; live Backtrader is NOT run by the agent runtime.",
            input_summary=f"simple-engine {symbol} {strategy}",
            tool_calls=[{"tool": "simple_engine.run_simple_backtest", "args": {"symbol": symbol, "strategy": strategy}, "status": "ok", "row_count": len(out.equity_curve)},
                        *persisted_res.get("tool_calls", [])],
            caveats=out.caveats,
        )
    )
    trace.set_final_basis(tables=["daily_prices", "backtest_runs", "backtest_metrics"], query_mode=mode.upper(), caveats=out.caveats)
    return {
        "action": f"simple-engine {symbol}",
        "domain": "backtest",
        "status": "ok",
        "answer_markdown": answer,
        "rows": comparison,
        "logic": se.engine_logic(out),
        "simple_engine_metrics": sm,
        "backtrader_metrics": persisted,
        "trace": trace.to_dict(),
        "caveats": out.caveats + (["no persisted Backtrader row for this exact symbol/strategy/slippage"] if persisted is None else []) + list(data_caveats),
        "next_action": {
            "priority": 0, "area": "backtest_engine", "status": "INFO",
            "title": "SimpleEngine is an explainability baseline, not a production engine",
            "why": "Long-only, simple bps slippage; use it to explain logic, not to replace persisted Backtrader.",
            "command": "python scripts\\run_simple_backtest_demo.py --symbol FPT --strategy ma20_ma50 --start-date 2020-01-01 --end-date 2025-12-31 --slippage-bps 0",
            "ui_path": "/api/demo/backtest/FPT/simple-engine",
        },
        "timing": _timed_probe("backtest", symbol, mode, url),
        "elapsed_ms": round(elapsed_ms, 3),
    }


def _build_simple_engine_logic(symbol: str, url: str, *, strategy: str = "ma20_ma50") -> dict[str, Any]:
    """Return the explicit SimpleEngine logic/assumptions for a symbol (read-only)."""
    try:
        bars, _ = se.load_bars_from_questdb(symbol, "2020-01-01", "2025-12-31", adjusted=True, url=url)
        out = se.run_simple_backtest(bars, symbol=symbol, strategy=strategy, slippage_bps=0.0, exchange=se.fetch_exchange(symbol, url=url))
    except Exception as exc:
        return {"action": f"simple-engine logic {symbol}", "domain": "backtest", "status": "error",
                "error_type": type(exc).__name__, "message": str(exc)[:300],
                "caveats": ["SimpleEngine logic could not be computed for this symbol"]}
    return {
        "action": f"simple-engine logic {symbol}",
        "domain": "backtest",
        "status": "ok",
        "symbol": symbol,
        "strategy": strategy,
        "logic": se.engine_logic(out),
        "params": out.params,
        "caveats": out.caveats,
        "next_action": {
            "priority": 0, "area": "backtest_engine", "status": "INFO",
            "title": "Compare against persisted Backtrader / run the variant lab",
            "why": "The logic above is the exact, transparent model used by the SimpleEngine.",
            "command": "python scripts\\run_simple_backtest_demo.py --symbol FPT --strategy ma20_ma50 --start-date 2020-01-01 --end-date 2025-12-31 --slippage-bps 0",
            "ui_path": "/api/demo/backtest/FPT/simple-engine/variants",
        },
    }


def _build_variants(symbol: str, mode: str, url: str) -> dict[str, Any]:
    """Run the deterministic SimpleEngine variant/sensitivity lab (read-only)."""
    start = time.perf_counter()
    try:
        lab = se.run_variants(symbol, url=url)
    except Exception as exc:
        return {"action": f"simple-engine variants {symbol}", "domain": "backtest", "status": "error",
                "error_type": type(exc).__name__, "message": str(exc)[:300],
                "caveats": ["SimpleEngine variant lab could not run for this symbol"]}
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    # Flatten to UI rows: one row per variant with its key metrics.
    rows = []
    for v in lab["variants"]:
        m = v.get("metrics", {})
        rows.append({
            "variant": v["id"], "changed": v["changed"],
            "total_return_pct": m.get("total_return_pct"), "annualized_return_pct": m.get("annualized_return_pct"),
            "max_drawdown_pct": m.get("max_drawdown_pct"), "sharpe": m.get("sharpe_ratio"),
            "trades": m.get("closed_trades"), "win_rate_pct": m.get("win_rate_pct"),
            "narrative": v.get("narrative") or v.get("why") or v.get("error"),
        })
    trace = pt.PipelineTrace(f"simple-engine variants {symbol}", "backtest")
    trace.add_agent(pt.router_step("backtest", f"simple-engine variants {symbol}", "backtest_results"))
    trace.add_agent(
        pt.specialist_step(
            "backtest",
            decision=f"ran {len(rows)} deterministic SimpleEngine variants on {symbol}",
            reason="Transparent in-process sensitivity lab; no live Backtrader is run by the agent runtime.",
            input_summary=f"variants {symbol}",
            tool_calls=[{"tool": "simple_engine.run_variants", "args": {"symbol": symbol}, "status": "ok", "row_count": len(rows)}],
            caveats=lab["caveats"],
        )
    )
    trace.set_final_basis(tables=["daily_prices"], query_mode=mode.upper(), caveats=lab["caveats"])
    return {
        "action": f"simple-engine variants {symbol}",
        "domain": "backtest",
        "status": "ok",
        "answer_markdown": f"**SimpleEngine variant lab — {symbol}** ({lab['start_date']}..{lab['end_date']}). "
                           f"Baseline = `{lab['baseline_id']}`. Each row changes one assumption/feature and shows the impact.",
        "rows": rows,
        "baseline_id": lab["baseline_id"],
        "variants": lab["variants"],
        "trace": trace.to_dict(),
        "caveats": lab["caveats"],
        "elapsed_ms": round(elapsed_ms, 3),
    }


def _build_trace_examples(url: str) -> dict[str, Any]:
    examples = []
    for query in ("summary FPT", "financial report FPT", "compare backtest strategies FPT", "latest news VNM"):
        res = answer_query(query, questdb_url=url)
        examples.append({
            "query": query,
            "status": res.get("status"),
            "trace": pt.trace_from_rule_result(query, res, query_mode="REST"),
        })
    return {"examples": examples, "note": "concise decision reasons only; no hidden chain-of-thought is exposed."}


BENCHMARK_QUERIES: dict[str, str] = {
    "latest_ohlcv_FPT": "SELECT trade_date, open, high, low, close, adjusted_close, volume FROM daily_prices WHERE symbol = 'FPT' ORDER BY trade_date DESC LIMIT 1",
    "backtest_comparison_FPT": "SELECT r.strategy_id, m.final_value, m.total_return_pct FROM backtest_runs r JOIN backtest_metrics m ON r.run_id = m.run_id WHERE r.symbol = 'FPT' AND r.slippage_bps = 0.0",
    "event_latest_FPT": "SELECT published_at, title, category FROM event_news_items WHERE symbol = 'FPT' ORDER BY published_at DESC LIMIT 5",
    "count_daily_prices": "SELECT count() FROM daily_prices",
}


def _build_benchmark(url: str) -> dict[str, Any]:
    import statistics

    return _run_benchmark(url, BENCHMARK_QUERIES, statistics)


def _run_benchmark(url: str, queries: dict[str, str], statistics) -> dict[str, Any]:
    pgwire_live = pg.pgwire_available() and pg.ping().get("status") == "ok"
    results: dict[str, Any] = {}
    rest_p50: list[float] = []
    pg_p50: list[float] = []
    for name, sql in queries.items():
        rest = _bench_one(lambda q: qr.query_rest_timed(q, url=url), sql, repeats=10)
        pgw = _bench_one(lambda q: pg.query_pgwire(q), sql, repeats=10) if pgwire_live else {"error": "pgwire unavailable"}
        results[name] = {"rest": rest, "pgwire": pgw}
        if "p50" in rest:
            rest_p50.append(rest["p50"])
        if isinstance(pgw, dict) and "p50" in pgw:
            pg_p50.append(pgw["p50"])
    rec_mode = "rest"
    if rest_p50 and pg_p50:
        rest_mean = statistics.fmean(rest_p50)
        pg_mean = statistics.fmean(pg_p50)
        if pg_mean < rest_mean * 0.9:
            rec_mode = "pgwire"
    return {
        "pgwire_live": pgwire_live,
        "results": results,
        "recommendation_mode": rec_mode,
        "note": "warm/reused connections; keep REST /imp for ingestion. Demoed 72ms was REST/network overhead, not execute time.",
    }


def _bench_one(runner, sql: str, repeats: int) -> dict[str, Any]:
    import statistics

    for _ in range(2):
        if runner(sql).get("status") != "ok":
            return {"error": "query failed"}
    totals, executes = [], []
    for _ in range(repeats):
        res = runner(sql)
        if res.get("status") != "ok":
            return {"error": "query failed"}
        totals.append(float(res.get("timing", {}).get("total_ms", 0.0)))
        executes.append(float(res.get("timing", {}).get("execute_ms", 0.0)))
    ordered = sorted(totals)
    return {
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))], 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "execute_mean": round(statistics.fmean(executes), 4),
    }


def _multi(request: Request) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key in request.query_params.keys():
        out[key] = request.query_params.getlist(key)
    return out


async def _read_json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _redact(text: str) -> str:
    """Strip any OpenAI-style key fragments from an error message before returning it."""
    import re

    return re.sub(r"sk-[A-Za-z0-9_*-]{6,}", "sk-<redacted>", text or "")
