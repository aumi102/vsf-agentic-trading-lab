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
from trading_agent.tools import questdb_feature_signal_tool as fst
from trading_agent.validation import gates as G

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
    {"id": "product_overview", "label": "Product overview", "group": "Product Status", "method": "GET", "path": "/product/overview",
     "description": "What is currently usable."},
    {"id": "data_status", "label": "QuestDB data status", "group": "Product Status", "method": "GET", "path": "/product/data-status",
     "description": "FA + market data loaded in QuestDB."},
    {"id": "adjusted_gate", "label": "Adjusted OHLC gate", "group": "Product Status", "method": "GET", "path": "/product/adjusted-gate",
     "description": "approved_only vs prototype_allowed."},
    {"id": "signals", "label": "Strategy signals", "group": "Trading Core", "method": "GET", "path": "/product/signals",
     "description": "BUY / SELL / HOLD signal."},
    {"id": "backtest", "label": "Backtest engine v1", "group": "Trading Core", "method": "GET", "path": "/product/backtest",
     "description": "Custom backtest with baseline + strategy."},
    {"id": "cost_slippage", "label": "Cost & slippage guard", "group": "Trading Core", "method": "GET", "path": "/product/cost-slippage",
     "description": "commission, slippage, price-band guard."},
    {"id": "source_verification", "label": "Corporate events source check", "group": "Source Verification", "method": "GET", "path": "/product/source-verification",
     "description": "adjusted OHLC source/corporate action status."},
    {"id": "decision", "label": "Symbol decision", "group": "Trading Core", "method": "GET", "path": "/product/decision?symbol=VNM&strategy=ma_cross_v1&source_policy=prototype_allowed",
     "description": "final research decision for one ticker"},
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

    @app.get("/api/demo/fa/coverage")
    async def demo_fa_coverage() -> dict:
        return await asyncio.to_thread(_build_fa_coverage, url)

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

    class _FakeRequest:
        """Minimal stand-in for Request when calling async endpoints directly."""
        def __init__(self, query_string: str = ""):
            self._query_string = query_string
        @property
        def query_params(self):
            from starlette.datastructures import QueryParams
            return QueryParams(self._query_string)

    def _fake_request(query_string: str) -> Request:
        return _FakeRequest(query_string)

    @app.post("/api/demo/ask")
    async def demo_ask(request: Request) -> JSONResponse:
        body = await _read_json(request)
        message = str(body.get("message") or body.get("query") or "").strip().lower()
        if not message:
            return _json(400, {"status": "error", "caveats": ["message (or query) is required"]})
        # Check for simple query shortcuts (rule mode, no LLM needed)
        symbols_from_msg = [s.strip().upper() for s in ("FPT", "VNM") if s.lower() in message]
        # Decision shortcuts: "nên làm gì", "decision", "analyze", "phân tích",
        # "đánh giá", "recommend", "khuyến nghị" + supported symbol.
        decision_triggers = (
            "nên làm gì", "decision", "analyze", "phân tích",
            "đánh giá", "recommend", "khuyến nghị",
        )
        decision_symbols = ("FPT", "VNM", "CTG", "HPG", "VCB", "VHM")
        decision_sym = None
        for ds in decision_symbols:
            if ds.lower() in message:
                decision_sym = ds
                break
        if decision_sym and any(trig in message for trig in decision_triggers):
            return _json(200, await product_decision(
                symbol=decision_sym,
                strategy="ma_cross_v1",
                source_policy="prototype_allowed",
                include_backtest=True,
            ))
        if "signal" in message and symbols_from_msg:
            return _json(200, await product_signals(
                _fake_request(f"symbols={','.join(symbols_from_msg)}&strategy=ma_cross_v1&source_policy=prototype_allowed")))
        if "backtest" in message and symbols_from_msg:
            return _json(200, await product_backtest(
                _fake_request(f"symbols={','.join(symbols_from_msg)}&strategy=ma_cross_v1&source_policy=prototype_allowed")))
        if "data status" in message or "data-status" in message:
            return _json(200, await product_data_status())
        if "adjusted gate" in message or "adjusted-gate" in message:
            return _json(200, await product_adjusted_gate())
        if "cost" in message and "slippage" in message:
            return _json(200, await product_cost_slippage())
        if "source" in message and ("verification" in message or "check" in message):
            return _json(200, await product_source_verification())
        if "overview" in message:
            return _json(200, await product_overview())
        # Default to rule mode, fall back gracefully on deep
        deep = str(body.get("mode", "rule")).lower() == "deep"
        mode = qr.resolve_mode(body.get("query_mode"))
        # Check API key presence for deep mode (don't expose value)
        api_key_set = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("VSF_DEEPAGENTS_API_KEY"))
        if deep and not api_key_set:
            return _json(200, {
                "status": "unavailable",
                "domain": "deep_agents",
                "answer_markdown": (
                    "## Deep mode requires LLM credentials\n\n"
                    "Deep mode dependencies are installed, but LLM credentials/model config are missing.\n\n"
                    "Set `OPENAI_API_KEY` (and optionally `VSF_DEEPAGENTS_MODEL`) and restart the backend."
                ),
                "caveats": [
                    "Deep mode requires OPENAI_API_KEY or VSF_DEEPAGENTS_API_KEY",
                    "Rule mode works without LLM credentials",
                ],
                "next_action": {
                    "priority": 0,
                    "title": "Configure LLM credentials",
                    "status": "INFO",
                    "why": "Deep mode uses LLM orchestration; rule mode uses deterministic product tools.",
                    "ui_path": "/product/overview",
                },
            })
        try:
            payload = await asyncio.to_thread(_envelope_from_query, message, mode=mode, url=url, deep=deep)
            return _json(200, payload)
        except (ImportError, ModuleNotFoundError) as exc:
            # Deep mode dependencies missing — clean message, no traceback
            if deep:
                return _json(200, {
                    "status": "unavailable",
                    "domain": "deep_agents",
                    "answer_markdown": (
                        "## Deep mode dependencies missing\n\n"
                        "The DeepAgents extra (deepagents, langchain, langchain-openai) is not installed.\n\n"
                        "Rebuild with `INSTALL_DEEPAGENTS=true` to enable deep mode."
                    ),
                    "caveats": ["Deep mode requires the deepagents extra build flag"],
                    "next_action": {
                        "priority": 0,
                        "title": "Install deepagents extra",
                        "status": "INFO",
                        "why": "Deep mode uses deepagents + langchain.",
                        "ui_path": "/product/overview",
                    },
                })
            raise
        except Exception as exc:
            # Graceful fallback for other deep mode failures
            if deep:
                return _json(200, {
                    "status": "unavailable",
                    "domain": "deep_agents",
                    "answer_markdown": (
                        "## Deep mode unavailable\n\n"
                        f"Deep mode is installed but failed to run: {str(exc)[:200]}\n\n"
                        "Use rule mode or the sidebar buttons for product console actions."
                    ),
                    "caveats": ["Deep mode failed; rule mode is fully functional"],
                    "next_action": {
                        "priority": 0,
                        "title": "Use rule-mode sidebar buttons",
                        "status": "INFO",
                        "why": "Rule mode is fully functional without LLM backend.",
                        "ui_path": "/product/overview",
                    },
                })
            raise

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

    # ---- product console endpoints -------------------------------------------
    @app.get("/product/overview")
    async def product_overview() -> dict:
        return {
            "status": "prototype_ready",
            "usable_now": [
                "QuestDB-backed FA/market data lookup",
                "adjusted OHLC readiness gate",
                "BUY/SELL/HOLD strategy signals",
                "custom backtest engine v1",
                "cost/slippage/price-band guard",
                "trade-level metrics",
            ],
            "not_yet_production": [
                "approved adjusted OHLC source missing",
                "FPT/VNM use prototype vnstock-derived adjusted rows only",
                "no real trading/broker execution",
            ],
            "main_run_mode": "backend demo console at /demo",
        }

    @app.get("/product/data-status")
    async def product_data_status() -> dict:
        def _cnt(rows):
            """Extract count from [{'cnt': N}] rows format."""
            if not rows:
                return 0
            row = rows[0]
            if isinstance(row, dict):
                return row.get("cnt", 0)
            return row[0] if row else 0

        try:
            daily = market.query_questdb("SELECT count() cnt FROM daily_prices", url=url)
            adj = market.query_questdb("SELECT count() cnt FROM adjusted_daily_prices", url=url)
            fa_runs = market.query_questdb(
                "SELECT status, count() cnt FROM fa_ingest_runs GROUP BY status", url=url)
            event_news = market.query_questdb("SELECT count() cnt FROM event_news_items", url=url)
            if any(r.get("status") == "error" for r in [daily, adj, fa_runs, event_news]):
                return {"status": "error", "questdb_reachable": True, "message": "query failed"}
            return {
                "status": "ok",
                "questdb_reachable": True,
                "daily_prices_rows": _cnt(daily.get("rows")),
                "adjusted_daily_prices_rows": _cnt(adj.get("rows")),
                "fa_ingest_runs": [{"status": r.get("status", r[0] if not isinstance(r, dict) else "?"),
                                    "count": r.get("cnt", r[1] if not isinstance(r, dict) else 0)}
                                   for r in fa_runs.get("rows", [])],
                "event_news_items_rows": _cnt(event_news.get("rows")),
            }
        except Exception as exc:
            return {"status": "error", "questdb_reachable": False, "message": str(exc)[:200]}

    @app.get("/product/adjusted-gate")
    async def product_adjusted_gate() -> dict:
        try:
            gate = G.adjusted_ohlc_gate(url)
            # Query adjusted_daily_prices for FPT/VNM prototype evidence - avoid || concat
            proto_data = market.query_questdb(
                "SELECT symbol, count() as cnt, min(trade_date) as date_min, max(trade_date) as date_max "
                "FROM adjusted_daily_prices WHERE symbol IN ('FPT','VNM') GROUP BY symbol", url=url)
            # Build prototype symbol list
            proto_symbols = []
            for r in proto_data.get("rows", []):
                if isinstance(r, dict):
                    sym = r.get("symbol", "")
                    proto_symbols.append({
                        "symbol": sym,
                        "status": "PASS_PROTOTYPE",
                        "rows": r.get("cnt", 0),
                        "adjustment_source": f"vnstock:company_events:{sym}",
                        "date_min": str(r.get("date_min", "")),
                        "date_max": str(r.get("date_max", "")),
                        "used_for_demo_backtest": True,
                    })
                elif isinstance(r, (list, tuple)) and len(r) >= 4:
                    sym = r[0]
                    proto_symbols.append({
                        "symbol": sym,
                        "status": "PASS_PROTOTYPE",
                        "rows": r[1],
                        "adjustment_source": f"vnstock:company_events:{sym}",
                        "date_min": str(r[2]) if len(r) > 2 else "",
                        "date_max": str(r[3]) if len(r) > 3 else "",
                        "used_for_demo_backtest": True,
                    })
            return {
                "status": gate.status.lower() if gate.status else "unknown",
                "daily_prices_raw_equivalent": gate.evidence.get("raw_equivalent_ratio") == 1.0,
                "daily_prices_adjusted_columns_present": gate.evidence.get("adjusted_columns_present", []),
                "approved_only": {
                    "approved_count": 0,
                    "official_backtest_allowed": False,
                    "reason": "approved adjusted OHLC source missing",
                    "FPT": "BLOCKED_UNAPPROVED_SOURCE",
                    "VNM": "BLOCKED_UNAPPROVED_SOURCE",
                    "HPG_VCB_CTG_VHM": "BLOCKED_ADJUSTED_SOURCE_MISSING",
                },
                "prototype_allowed": {
                    "prototype_count": len(proto_symbols),
                    "symbols": proto_symbols,
                },
                "warnings": [
                    "daily_prices adjusted columns are raw-equivalent; prototype uses adjusted_daily_prices for FPT/VNM only",
                    "vnstock-derived adjusted rows are prototype only, not approved",
                    "approved_only remains blocked until approved corporate action/vendor adjusted source exists",
                ],
            }
        except Exception as exc:
            # Graceful degradation
            return {
                "status": "error",
                "message": str(exc)[:200],
                "approved_only": {"approved_count": 0, "official_backtest_allowed": False},
                "prototype_allowed": {"prototype_count": 0, "symbols": []},
                "warnings": [f"Error checking gate: {str(exc)[:100]}"],
            }

    @app.get("/product/signals")
    async def product_signals(request: Request) -> dict:
        symbols = request.query_params.get("symbols", "FPT,VNM").split(",")
        strategy = request.query_params.get("strategy", "ma_cross_v1")
        source_policy = request.query_params.get("source_policy", "prototype_allowed")
        strategy_id_map = {"ma_cross_v1": "ma20_ma50_v1"}
        sid = strategy_id_map.get(strategy, "ma20_ma50_v1")
        signals = []
        warnings = []
        if source_policy == "approved_only":
            warnings.append("BLOCKED: no approved adjusted OHLC source")
            return {"status": "blocked", "strategy": strategy, "source_policy": source_policy,
                    "signals": [], "warnings": warnings}
        for sym in symbols[:5]:
            try:
                res = fst.get_latest_signal(sym.strip(), strategy_id=sid, url=url)
                if res.get("status") != "ok" or not res.get("rows"):
                    signals.append({
                        "symbol": sym.strip(), "signal": "HOLD", "raw_signal": None,
                        "score": None, "reason": res.get("caveats", ["no signal rows"])[0] if res.get("caveats") else "no data",
                        "position_state": "NO_DATA",
                    })
                    continue
                row = res["rows"][0]
                if isinstance(row, dict):
                    raw_signal = row.get("signal", "HOLD")
                    score = row.get("score")
                    reason = row.get("reason_code", "")
                else:
                    raw_signal = row[4] if len(row) > 4 else "HOLD"
                    score = row[5] if len(row) > 5 else None
                    reason = row[6] if len(row) > 6 else ""
                # Map CASH to HOLD for display, preserve raw for transparency
                display_signal = raw_signal if raw_signal in ("BUY", "SELL", "HOLD") else "HOLD"
                position_state = "NO_POSITION" if raw_signal == "CASH" else "HOLDING" if raw_signal == "BUY" else "FLAT"
                signals.append({
                    "symbol": sym.strip(),
                    "signal": display_signal,
                    "raw_signal": raw_signal,
                    "score": score,
                    "reason": reason or "",
                    "position_state": position_state,
                })
            except Exception as exc:
                signals.append({"symbol": sym.strip(), "signal": "ERROR", "raw_signal": None,
                               "score": None, "reason": str(exc)[:100], "position_state": "ERROR"})
        if source_policy == "prototype_allowed":
            warnings.append("prototype only: signal is for research/demo, not trading advice")
        return {
            "status": "ok",
            "strategy": strategy,
            "source_policy": source_policy,
            "data_basis": "signals table / latest deterministic signal",
            "signals": signals,
            "warnings": warnings,
        }

    @app.get("/product/backtest")
    async def product_backtest(request: Request) -> dict:
        symbols = request.query_params.get("symbols", "FPT,VNM").split(",")
        strategy = request.query_params.get("strategy", "ma_cross_v1")
        source_policy = request.query_params.get("source_policy", "prototype_allowed")
        strategy_id_map = {"ma_cross_v1": "ma20_ma50"}
        sid = strategy_id_map.get(strategy, "ma20_ma50")
        start_date = "2021-01-01"
        end_date = "2025-12-31"
        commission_bps = 15
        slippage_bps = 10

        warnings = []
        if source_policy == "approved_only":
            warnings.append("BLOCKED: no approved adjusted OHLC source")
            return {
                "status": "blocked", "engine": "custom_backtest_v1", "strategy": strategy,
                "source_policy": source_policy, "results": [], "warnings": warnings,
            }

        # Strategy logic definitions
        strategy_logic = {
            "ma_cross_v1": {
                "rule": "MA20 / MA50 crossover",
                "buy_condition": "MA20 crosses above MA50",
                "sell_condition": "MA20 crosses below or equals MA50",
                "signal_timing": "Signal is computed from historical bars only, no future rows",
            },
            "baseline_buy_hold_v1": {
                "rule": "Buy at first available bar",
                "sell_condition": "Mark-to-market at final bar",
                "purpose": "Engine validation baseline, not alpha strategy",
            },
        }

        # Execution logic
        execution_logic = {
            "signal_generation": "Signal generated on bar t",
            "execution_rule": "Execute on next tradable bar (open price)",
            "position_sizing": "95% of available cash per signal",
            "cash_update": "Cash updated after each fill",
            "no_raw_fallback": "Uses adjusted_daily_prices only, no raw daily_prices fallback",
        }

        results = []
        # Pre-fetch prototype data evidence for FPT/VNM
        proto_evidence = {}
        for sym in [s.strip() for s in symbols[:5] if s.strip() in ("FPT", "VNM")]:
            proto_res = market.query_questdb(
                f"SELECT count() as cnt, min(trade_date) as dmin, max(trade_date) as dmax "
                f"FROM adjusted_daily_prices WHERE symbol = '{sym}'", url=url)
            if proto_res.get("status") == "ok" and proto_res.get("rows"):
                row = proto_res["rows"][0]
                proto_evidence[sym] = {
                    "rows": row.get("cnt", 0) if isinstance(row, dict) else (row[0] if row else 0),
                    "date_min": str(row.get("dmin", "") if isinstance(row, dict) else (row[1] if len(row) > 1 else "")),
                    "date_max": str(row.get("dmax", "") if isinstance(row, dict) else (row[2] if len(row) > 2 else "")),
                }

        for sym in symbols[:5]:
            sym_stripped = sym.strip()
            try:
                bars, data_caveats = se.load_bars_from_questdb(
                    sym_stripped, start_date, end_date, adjusted=True, url=url)
                if not bars:
                    results.append({
                        "symbol": sym_stripped,
                        "status": "error",
                        "error": "no adjusted_daily_prices data available for this symbol",
                    })
                    warnings.extend(data_caveats)
                    continue

                exchange = se.fetch_exchange(sym_stripped, url=url)
                out = se.run_simple_backtest(bars, symbol=sym_stripped, strategy=sid,
                                           slippage_bps=slippage_bps, exchange=exchange)
                sm = out.metrics
                closed_trades = sm.get("closed_trades", 0)

                # Build explanation
                adj_source = f"vnstock:company_events:{sym_stripped}"
                drange = f"{bars[0].date if bars else start_date} to {bars[-1].date if bars else end_date}"
                explanation = (
                    f"Backtest is simulating strategy `{strategy}` on {sym_stripped} from {start_date} to {end_date} "
                    f"using `adjusted_daily_prices` prototype rows from `{adj_source}`. "
                    f"The strategy computes MA20 and MA50 from past bars. "
                    f"When MA20 crosses above MA50, it buys; when MA20 crosses below/equal MA50, it exits to CASH. "
                    f"Each signal is executed according to the engine's execution rule "
                    f"with {commission_bps}bps commission and {slippage_bps}bps slippage applied. "
                    f"The table below shows trades and resulting metrics."
                )

                # Trade summary
                trade_summary = {
                    "total_trades": sm.get("trade_count") or closed_trades,
                    "closed_trades": closed_trades,
                    "first_trade": None,
                    "last_trade": None,
                    "why_no_trades": None,
                }

                if closed_trades == 0:
                    trade_summary["why_no_trades"] = (
                        "No trade was generated because MA20/MA50 did not cross during the selected period. "
                        "Try a longer date range or different symbol."
                    )

                # Sample trades from equity curve
                sample_trades = []
                try:
                    if hasattr(out, 'trades') and out.trades:
                        all_trades = list(out.trades) if hasattr(out.trades, '__iter__') else []
                        # Take first 3 and last 3
                        if len(all_trades) > 6:
                            trades_sample = all_trades[:3] + all_trades[-3:]
                        else:
                            trades_sample = all_trades
                        for t in trades_sample:
                            # Handle RoundTripTrade objects with attributes, not dict
                            if hasattr(t, '__dict__'):
                                sample_trades.append({
                                    "date": str(getattr(t, 'dt', getattr(t, 'date', ''))),
                                    "side": str(getattr(t, 'side', '')),
                                    "price": getattr(t, 'price', None),
                                    "quantity": getattr(t, 'quantity', None),
                                    "value": getattr(t, 'value', None),
                                })
                            elif isinstance(t, dict):
                                sample_trades.append({
                                    "date": str(t.get("date", "")),
                                    "side": t.get("side", ""),
                                    "price": t.get("price"),
                                    "quantity": t.get("quantity"),
                                    "value": t.get("value"),
                                })
                        if all_trades:
                            trade_summary["first_trade"] = sample_trades[0] if sample_trades else None
                            trade_summary["last_trade"] = sample_trades[-1] if len(sample_trades) > 1 else None
                except Exception:
                    pass  # Trade extraction is best-effort

                bar_result = {
                    "symbol": sym_stripped,
                    "backtest_explanation": explanation,
                    "strategy_logic": strategy_logic.get(strategy, strategy_logic["ma_cross_v1"]),
                    "execution_logic": execution_logic,
                    "data_lineage": {
                        "data_basis": "adjusted_daily_prices",
                        "source_policy": source_policy,
                        "adjustment_source": adj_source,
                        "price_basis": "adjusted OHLC",
                        "commission_bps": commission_bps,
                        "slippage_bps": slippage_bps,
                        "date_range": drange,
                    },
                    "trade_summary": trade_summary,
                    "sample_trades": sample_trades[:6] if sample_trades else [],
                    "metrics": {
                        "total_return_pct": sm.get("total_return_pct"),
                        "sharpe_ratio": sm.get("sharpe_ratio"),
                        "sortino_ratio": sm.get("sortino_ratio"),
                        "profit_factor": sm.get("profit_factor"),
                        "max_drawdown_pct": sm.get("max_drawdown_pct"),
                        "win_rate": sm.get("win_rate_pct"),
                        "total_commission": sm.get("total_commission"),
                        "total_slippage_estimate": sm.get("total_slippage_estimate"),
                    },
                    "caveats": [],
                }
                if sym_stripped in proto_evidence:
                    bar_result["data_lineage"]["prototype_rows"] = proto_evidence[sym_stripped].get("rows", 0)
                    bar_result["data_lineage"]["data_date_range"] = (
                        f"{proto_evidence[sym_stripped].get('date_min', '')} "
                        f"to {proto_evidence[sym_stripped].get('date_max', '')}"
                    )
                results.append(bar_result)
                warnings.extend(data_caveats)
            except Exception as exc:
                results.append({"symbol": sym_stripped, "status": "error", "error": str(exc)[:100]})

        if source_policy == "prototype_allowed":
            warnings.append("prototype only: vnstock-derived adjusted rows, not approved")

        return {
            "status": "ok",
            "engine": "custom_backtest_v1",
            "strategy": strategy,
            "source_policy": source_policy,
            "date_range": f"{start_date} to {end_date}",
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "results": results,
            "warnings": warnings,
        }

    @app.get("/product/cost-slippage")
    async def product_cost_slippage() -> dict:
        return {
            "status": "ok",
            "commission_bps": 15,
            "slippage_bps": 10,
            "price_band_guard": {
                "HOSE_HSX": 700,
                "HNX": 1000,
                "UPCOM": 1500,
            },
            "trade_level_fields": [
                "execution_price", "raw_base_price", "gross_value", "net_value",
                "commission", "slippage_value_estimate",
            ],
        }

    @app.get("/product/decision")
    async def product_decision(
        symbol: str = "FPT",
        strategy: str = "ma_cross_v1",
        source_policy: str = "prototype_allowed",
        include_backtest: bool = True,
    ) -> dict:
        """Concise multi-tool product decision for one ticker.

        Orchestrates signals + adjusted-gate + (optional) backtest and returns a
        final research decision that is clearly distinct from a raw signal.
        """
        sym = (symbol or "FPT").strip().upper()
        strategy = (strategy or "ma_cross_v1").strip()
        source_policy = (source_policy or "prototype_allowed").strip()
        caveats: list[str] = []

        # -----------------------------------------------------------------
        # 1. Adjusted gate / source policy check
        # -----------------------------------------------------------------
        approved = False
        prototype = False
        gate_status = "unknown"
        try:
            gate = G.adjusted_ohlc_gate(url)
            gate_status = (gate.status or "unknown").lower()
        except Exception:
            gate_status = "error"

        # Pre-fetch prototype row evidence for the requested symbol
        proto_evidence: dict[str, Any] = {}
        try:
            proto_res = market.query_questdb(
                "SELECT count() as cnt, min(trade_date) as dmin, max(trade_date) as dmax "
                f"FROM adjusted_daily_prices WHERE symbol = '{sym}'",
                url=url,
            )
            if proto_res.get("status") == "ok" and proto_res.get("rows"):
                row = proto_res["rows"][0]
                if isinstance(row, dict):
                    proto_evidence = {
                        "rows": row.get("cnt", 0),
                        "date_min": str(row.get("dmin", "")),
                        "date_max": str(row.get("dmax", "")),
                    }
                else:
                    proto_evidence = {
                        "rows": row[0] if len(row) > 0 else 0,
                        "date_min": str(row[1]) if len(row) > 1 else "",
                        "date_max": str(row[2]) if len(row) > 2 else "",
                    }
        except Exception:
            pass

        prototype = bool(proto_evidence and proto_evidence.get("rows", 0) > 0)
        # Approved source: none in this environment (daily_prices adjusted cols are raw-equivalent)
        approved_count = 0
        source_status_label = "vnstock:company_events:FPT" if prototype else ""

        if source_policy == "prototype_allowed":
            if source_status_label:
                pass  # filled below per symbol
            source_status_label = f"vnstock:company_events:{sym}" if prototype else ""

        # Default response status: blocked if approved_only and no approved source
        status = "ok"
        decision_blocked = False

        adjusted_gate_block = {
            "status": gate_status,
            "source_status": "approved adjusted OHLC source missing",
            "approved": approved,
            "prototype": prototype,
            "approved_count": approved_count,
            "prototype_rows": proto_evidence.get("rows", 0),
            "data_basis": "adjusted_daily_prices" if prototype else "none",
            "source_policy": source_policy,
        }

        if source_policy == "approved_only" and approved_count == 0:
            status = "blocked"
            decision_blocked = True
            caveats.append("approved adjusted OHLC source missing")
            caveats.append("approved_only remains blocked until approved corporate action/vendor adjusted source exists")

        if not prototype and sym not in ("FPT", "VNM"):
            # Symbol has no prototype adjusted rows -> cannot compute decision
            status = "blocked"
            decision_blocked = True
            caveats.append("symbol has no approved/prototype adjusted OHLC source")
            caveats.append("adjusted/corporate action source missing for this symbol")

        # -----------------------------------------------------------------
        # 2. Latest signal (always attempt)
        # -----------------------------------------------------------------
        signal_input: dict[str, Any] = {
            "raw_signal": None,
            "display_signal": None,
            "score": None,
            "reason_code": None,
            "strategy": strategy,
            "position_state": None,
        }
        signal_status = "unavailable"
        try:
            sid = "ma20_ma50_v1" if strategy == "ma_cross_v1" else "ma20_ma50_v1"
            res = fst.get_latest_signal(sym, strategy_id=sid, url=url)
            if res.get("status") == "ok" and res.get("rows"):
                row = res["rows"][0]
                if isinstance(row, dict):
                    raw = row.get("signal", "HOLD")
                    score = row.get("score")
                    reason = row.get("reason_code", "")
                else:
                    raw = row[4] if len(row) > 4 else "HOLD"
                    score = row[5] if len(row) > 5 else None
                raw_signal = raw if raw in ("BUY", "SELL", "HOLD", "CASH") else "HOLD"
                display_signal = raw_signal if raw_signal in ("BUY", "SELL", "HOLD") else "HOLD"
                position_state = (
                    "NO_POSITION" if raw_signal == "CASH"
                    else "HOLDING" if raw_signal == "BUY"
                    else "FLAT" if raw_signal == "SELL"
                    else "FLAT"
                )
                signal_input = {
                    "raw_signal": raw_signal,
                    "display_signal": display_signal,
                    "score": score,
                    "reason_code": reason if isinstance(reason, str) else (reason or ""),
                    "strategy": strategy,
                    "position_state": position_state,
                }
                signal_status = "ok"
            else:
                signal_status = "unavailable"
                caveats.append("signal unavailable or insufficient data")
        except Exception as exc:
            signal_status = "error"
            caveats.append(f"signal lookup failed: {str(exc)[:100]}")

        # -----------------------------------------------------------------
        # 3. Backtest summary (only when allowed + data present)
        # -----------------------------------------------------------------
        backtest_summary: dict[str, Any] = {
            "available": False,
            "total_return_pct": None,
            "sharpe_ratio": None,
            "max_drawdown_pct": None,
            "trade_count": None,
            "data_basis": "adjusted_daily_prices",
            "adjustment_source": f"vnstock:company_events:{sym}" if prototype else "",
        }
        run_backtest = (
            include_backtest
            and source_policy == "prototype_allowed"
            and prototype
        )
        if run_backtest:
            try:
                bars, data_caveats = se.load_bars_from_questdb(
                    sym, "2021-01-01", "2025-12-31", adjusted=True, url=url
                )
                if bars:
                    sid_bt = "ma20_ma50" if strategy == "ma_cross_v1" else "ma20_ma50"
                    exchange = se.fetch_exchange(sym, url=url)
                    out = se.run_simple_backtest(
                        bars, symbol=sym, strategy=sid_bt,
                        slippage_bps=10, exchange=exchange,
                    )
                    sm = out.metrics or {}
                    backtest_summary = {
                        "available": True,
                        "total_return_pct": sm.get("total_return_pct"),
                        "sharpe_ratio": sm.get("sharpe_ratio"),
                        "max_drawdown_pct": sm.get("max_drawdown_pct"),
                        "trade_count": sm.get("trade_count") or sm.get("closed_trades"),
                        "data_basis": "adjusted_daily_prices",
                        "adjustment_source": f"vnstock:company_events:{sym}",
                        "date_range": (
                            f"{bars[0].date if bars else ''} to {bars[-1].date if bars else ''}"
                        ),
                    }
                    caveats.extend(data_caveats)
                else:
                    caveats.append("backtest skipped: no adjusted_daily_prices bars")
            except Exception as exc:
                caveats.append(f"backtest failed: {str(exc)[:100]}")
        else:
            if include_backtest and source_policy == "prototype_allowed":
                caveats.append("backtest skipped: symbol has no prototype adjusted rows")

        # -----------------------------------------------------------------
        # 4. Decision rules
        # -----------------------------------------------------------------
        raw_signal = signal_input.get("raw_signal")
        display_signal = signal_input.get("display_signal")

        action = "UNANSWERED"
        confidence = "low"
        decision_reason = ""
        why_different = ""

        if decision_blocked:
            if sym not in ("FPT", "VNM"):
                action = "NO_OFFICIAL_ACTION"
                decision_reason = "adjusted/corporate action source missing"
                why_different = (
                    "decision blocked: this symbol has no prototype adjusted OHLC source "
                    "(only FPT/VNM currently have prototype rows). Raw signal would be misleading without adjusted data."
                )
            else:
                action = "NO_OFFICIAL_ACTION"
                decision_reason = "approved adjusted OHLC source missing"
                why_different = (
                    "approved_only policy blocks official action. prototype rows exist "
                    "but were explicitly excluded by source_policy."
                )
        elif signal_status != "ok":
            action = "UNANSWERED"
            decision_reason = "signal unavailable or insufficient data"
            why_different = "decision cannot be made: signal layer did not produce a current value."
        elif raw_signal == "CASH":
            # Strategy is out of the market
            action = "NO_POSITION"
            confidence = "medium" if prototype else "low"
            decision_reason = "strategy is in CASH/no-position state (no current buy/sell signal)"
            why_different = (
                "raw_signal=CASH is mapped to display_signal=HOLD by signal layer; "
                "decision layer recognises this as NO_POSITION, not as an active HOLD call."
            )
        elif raw_signal == "BUY":
            action = "BUY_CANDIDATE"
            # Confidence: medium only if no blocking data caveat AND prototype data present
            if prototype and not decision_blocked:
                confidence = "medium"
            else:
                confidence = "low"
            decision_reason = (
                f"ma_cross_v1 issued BUY on {sym}; no blocking data caveats; "
                f"prototype adjusted data available"
                if prototype
                else f"ma_cross_v1 issued BUY on {sym}; data caveat present"
            )
            why_different = (
                "signal=raw BUY is one input; decision=BUY_CANDIDATE adds adjusted-source, "
                "backtest, and not-investment-advice guardrails before any action is taken."
            )
            caveats.append("this is a candidate view, not investment advice")
        elif raw_signal == "SELL":
            action = "SELL_OR_EXIT"
            confidence = "medium" if prototype else "low"
            decision_reason = "ma_cross_v1 issued SELL; treat as exit candidate"
            why_different = (
                "signal=raw SELL is one input; decision=SELL_OR_EXIT emphasises exit/risk action "
                "and adds the same source/backtest/advice guardrails."
            )
            caveats.append("this is a candidate view, not investment advice")
        elif display_signal == "HOLD":
            action = "HOLD"
            confidence = "medium" if prototype else "low"
            decision_reason = "no active buy/sell/cash signal from ma_cross_v1"
            why_different = (
                "display_signal=HOLD can come from CASH or from flat position; "
                "decision=HOLD is the explicit research view when no active crossover."
            )
        else:
            action = "UNANSWERED"
            decision_reason = "signal unavailable or insufficient data"
            why_different = "decision cannot be made: signal layer produced no actionable raw value."

        # Standard caveats always present for the demo
        if prototype:
            caveats.append("vnstock-derived adjusted rows are prototype only, not approved")
        if source_policy == "prototype_allowed":
            caveats.append("source_policy=prototype_allowed; not investment advice")
        if status == "ok" and not decision_blocked:
            caveats.append("uses adjusted_daily_prices only, no raw daily_prices fallback")

        # Market summary: lightweight latest OHLCV if available
        market_summary: dict[str, Any] = {}
        try:
            summary = legacy._handle_derived_latest(url, sym, "summary")
            payload = summary[1] if isinstance(summary, tuple) else summary
            if isinstance(payload, dict):
                rows = payload.get("rows") or payload.get("data", {}).get("rows")
                if isinstance(rows, list) and rows:
                    market_summary = {"latest_bar": rows[0]}
        except Exception:
            pass

        return {
            "status": status,
            "symbol": sym,
            "strategy": strategy,
            "source_policy": source_policy,
            "decision": {
                "action": action,
                "confidence": confidence,
                "reason": decision_reason,
                "why_different_from_signal": why_different,
                "is_investment_advice": False,
            },
            "inputs": {
                "signal": signal_input,
                "adjusted_gate": adjusted_gate_block,
                "backtest_summary": backtest_summary,
                "market_summary": market_summary,
            },
            "caveats": caveats,
        }

    @app.get("/product/source-verification")
    async def product_source_verification() -> dict:
        try:
            items = market.query_questdb(
                "SELECT count() cnt FROM event_news_items WHERE symbol = 'FPT'", url=url)
            payloads = market.query_questdb(
                "SELECT count() cnt FROM event_news_raw_payloads WHERE symbol = 'FPT'", url=url)
            fa_rows = market.query_questdb(
                "SELECT count() cnt FROM fa_balance_sheet WHERE symbol = 'FPT'", url=url)

            def _cnt(res):
                if res.get("status") != "ok" or not res.get("rows"):
                    return 0
                row = res["rows"][0]
                if isinstance(row, dict):
                    return row.get("cnt", 0)
                return row[0] if row else 0

            return {
                "status": "ok",
                "event_news_items_FPT": _cnt(items),
                "event_news_raw_payloads_FPT": _cnt(payloads),
                "fa_balance_sheet_FPT": _cnt(fa_rows),
                "FPT_PDF_scanned": True,
                "required_fields_missing": ["corporate_action_source", "vendor_adjusted_prices"],
                "approved_adjusted_OHLC_blocked": True,
                "next_blocker": "approved corporate action source or vendor adjusted prices",
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)[:200]}

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


def _build_fa_coverage(url: str) -> dict[str, Any]:
    """Return the same summary structure as scripts/questdb_fa_coverage.py.

    Calls the coverage script in-process via its CLI entry point to keep a
    single source of truth. We re-invoke the script body but capture the JSON
    output rather than printing it. Errors degrade to a structured error dict.
    """
    import contextlib as _cl
    import importlib.util as _ilu
    import io as _io
    import json as _json
    import sys as _sys
    from datetime import datetime as _dt, timezone as _tz
    from pathlib import Path as _P

    spec = _ilu.spec_from_file_location(
        "_questdb_fa_coverage_runtime",
        str(_P(__file__).resolve().parents[3] / "scripts" / "questdb_fa_coverage.py"),
    )
    if spec is None or spec.loader is None:
        return {
            "status": "error",
            "action": "fa coverage",
            "domain": "fa",
            "error_type": "ImportError",
            "message": "could not load scripts/questdb_fa_coverage.py",
            "caveats": ["fa coverage script not available in the demo runtime"],
            "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # The coverage script reads CLI args via argparse from sys.argv; force --json
    # so the captured stdout is a parseable JSON object.
    saved_argv = _sys.argv
    _sys.argv = ["questdb_fa_coverage.py", "--json"]
    buf = _io.StringIO()
    with _cl.redirect_stdout(buf):
        try:
            summary = mod.main()
        except SystemExit:
            summary = None
    _sys.argv = saved_argv
    raw = buf.getvalue().strip()
    if not isinstance(summary, dict):
        try:
            summary = _json.loads(raw) if raw.startswith("{") else {}
        except Exception as exc:
            summary = {
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc)[:300],
                "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

    if not summary:
        summary = {
            "status": "error",
            "message": "coverage script returned no summary",
            "generated_at": _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    return {
        "action": "fa coverage",
        "domain": "fa",
        "status": summary.get("status", "unknown"),
        "summary": summary,
        "caveats": [
            "Read-only; the coverage script never writes to QuestDB.",
            "FA ingest remains run-scoped; FA tools use the latest complete run until coverage is full.",
        ],
        "next_action": summary.get("next_action", ""),
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
