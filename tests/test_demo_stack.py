"""Lightweight tests for the FastAPI demo stack additions.

Deterministic and offline: these do not require a running QuestDB. The live PGWire
check is skipped when QuestDB is not reachable.
"""
from __future__ import annotations

import math

import pytest

from trading_agent.backtest import simple_engine as se
from trading_agent.observability import next_actions as na  # noqa: F401  (import smoke)
from trading_agent.observability import pipeline_trace as pt
from trading_agent.storage import questdb_client as qdb
from trading_agent.storage import questdb_pgwire_client as pg
from trading_agent.storage import questdb_read as qr


# --- imports / wiring -------------------------------------------------------
def test_fastapi_app_imports_and_registers_routes():
    from trading_agent.api.fastapi_app import create_app

    app = create_app(questdb_url="http://127.0.0.1:9000")
    paths = {getattr(r, "path", "") for r in app.routes}
    for expected in (
        "/health",
        "/demo",
        "/api/demo/menu",
        "/api/demo/status",
        "/api/demo/market/{symbol}",
        "/api/demo/backtest/{symbol}",
        "/api/demo/events/{symbol}",
        "/api/demo/ask",
        "/v1/chat/completions",
        "/market/summary/{symbol}",
    ):
        assert expected in paths, f"missing route {expected}"


def test_pgwire_client_imports_and_builds_dsn():
    assert pg.pgwire_available() in (True, False)
    dsn = pg.build_dsn()
    assert "port=8812" in dsn and "127.0.0.1" in dsn


# --- IPv4 normalization (the perf fix) --------------------------------------
def test_to_ipv4_localhost_rewrites_only_localhost():
    assert qdb.to_ipv4_localhost("http://localhost:9000") == "http://127.0.0.1:9000"
    assert qdb.to_ipv4_localhost("http://localhost/exec") == "http://127.0.0.1/exec"
    # real/remote hosts must be untouched
    assert qdb.to_ipv4_localhost("http://questdb:9000") == "http://questdb:9000"
    assert qdb.to_ipv4_localhost("http://host.docker.internal:9000") == "http://host.docker.internal:9000"


def test_resolve_mode_defaults_to_rest(monkeypatch):
    monkeypatch.delenv("QUESTDB_QUERY_MODE", raising=False)
    assert qr.resolve_mode() == "rest"
    assert qr.resolve_mode("pgwire") == "pgwire"
    assert qr.resolve_mode("garbage") == "rest"


# --- trace schema -----------------------------------------------------------
def test_classify_domain_routes_known_queries():
    assert pt.classify_domain("compare backtest strategies FPT")[0] == "backtest"
    assert pt.classify_domain("latest news FPT")[0] == "event_news"
    assert pt.classify_domain("financial report FPT")[0] == "financial_report"
    assert pt.classify_domain("summary FPT")[0] == "market_summary"


def test_trace_from_rule_result_has_full_schema():
    fake = {
        "status": "ok",
        "intent": "backtest_results",
        "tool_calls": [{"tool": "get_backtest_strategy_comparison", "status": "ok", "row_count": 3}],
        "caveats": ["slippage_bps is 0; slippage is not modeled"],
        "data": {},
    }
    trace = pt.trace_from_rule_result("compare backtest strategies FPT", fake, query_mode="REST")
    assert set(trace) >= {
        "request_id", "user_query", "domain", "pipeline_position", "agents",
        "final_answer_basis", "next_actions",
    }
    assert trace["domain"] == "backtest"
    names = [a["agent_name"] for a in trace["agents"]]
    assert names == ["RouterAgent", "BacktestAgent"]
    router, specialist = trace["agents"]
    # backtest must reject live Backtrader tools and use persisted rows
    assert "run_backtrader" in router["rejected_tools"]
    assert "get_backtest_strategy_comparison" in router["allowed_tools"]
    assert "live Backtrader" in specialist["reason"]
    assert trace["final_answer_basis"]["query_mode"] == "REST"
    assert "backtest_runs" in trace["pipeline_position"]["upstream_tables"]


def test_event_news_trace_forbids_ohlcv_proxy():
    fake = {"status": "unsupported", "intent": "event_unavailable", "tool_calls": [], "caveats": [], "data": {}}
    trace = pt.trace_from_rule_result("latest news VNM", fake, query_mode="REST")
    assert trace["domain"] == "event_news"
    router = trace["agents"][0]
    assert "get_latest_ohlcv" in router["rejected_tools"]


# --- simple engine determinism + economics ----------------------------------
def _ramp_bars(n: int, start: float = 100.0, step: float = 1.0) -> list[se.Bar]:
    bars = []
    for i in range(n):
        price = start + step * i
        bars.append(se.Bar(date=f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}", open=price, high=price * 1.01, low=price * 0.99, close=price, volume=1000.0))
    return bars


def test_simple_engine_is_deterministic():
    bars = _ramp_bars(120)
    out1 = se.run_simple_backtest(bars, symbol="TST", strategy="ma20_ma50", slippage_bps=0.0)
    out2 = se.run_simple_backtest(bars, symbol="TST", strategy="ma20_ma50", slippage_bps=0.0)
    assert out1.metrics == out2.metrics
    assert out1.final_value == out2.final_value


def test_simple_engine_buy_hold_tracks_rising_market():
    bars = _ramp_bars(120)  # monotic rising -> buy & hold should profit
    out = se.run_simple_backtest(bars, symbol="TST", strategy="buy_hold", slippage_bps=0.0, target_percent=0.95)
    assert out.metrics["final_value"] > out.start_value
    # buy & hold benchmark return is positive on a rising series
    assert out.metrics["buy_hold_return_pct"] > 0
    # equity curve has one point per bar
    assert out.metrics["closed_trades"] >= 0
    assert len(out.equity_curve) == len(bars)


def test_simple_engine_rejects_too_few_bars():
    with pytest.raises(ValueError):
        se.run_simple_backtest(_ramp_bars(10), symbol="TST", strategy="ma20_ma50")


# --- next-action engine state shape (offline-safe parsing) ------------------
def test_next_actions_action_shape_keys():
    # Build an action manually to assert the contract the UI relies on.
    sample = {
        "priority": 1, "area": "adjusted_ohlc", "status": "WARN", "title": "t",
        "why": "w", "command": "c", "ui_path": "/x",
    }
    assert set(sample) >= {"priority", "area", "status", "title", "why", "command", "ui_path"}


# --- trace domain derivation: tool calls take priority ----------------------
def _deep_result(tool_names, *, status="ok", nested_intent=None):
    """Mimic the deep/guarded agent envelope: intent nested under data, not top level."""
    return {
        "status": status,
        "data": {"domain": "x", "intent": nested_intent} if nested_intent else {},
        "tool_calls": [{"tool": t, "status": "ok", "row_count": 1} for t in tool_names],
        "caveats": [],
    }


def _agents(trace):
    return [a["agent_name"] for a in trace["agents"]]


def test_summary_ctg_deep_is_market_not_system():
    # The regression: deep-mode 'summary CTG' had nested intent -> wrongly SYSTEM.
    res = _deep_result(["get_latest_ohlcv", "get_latest_features", "get_latest_signal"], nested_intent="symbol_summary")
    domain, _ = pt.derive_domain("summary CTG", res)
    trace = pt.trace_from_rule_result("summary CTG", res, query_mode="REST")
    assert domain == "market_summary"
    assert _agents(trace) == ["RouterAgent", "MarketDataAgent"]
    assert "SystemAgent" not in _agents(trace)
    assert trace["pipeline_position"]["current_step"] != "validation"
    assert {"daily_prices", "feature_snapshots", "signals"} <= set(trace["pipeline_position"]["upstream_tables"])


@pytest.mark.parametrize(
    "tools,expected_domain,expected_agent",
    [
        (["get_latest_ohlcv", "get_latest_features", "get_latest_signal"], "market_summary", "MarketDataAgent"),
        (["get_symbol_summary"], "market_summary", "MarketDataAgent"),
        (["get_latest_financial_report"], "financial_report", "FinancialReportAgent"),
        (["get_backtest_strategy_comparison"], "backtest", "BacktestAgent"),
        (["get_symbol_event_news"], "event_news", "EventNewsAgent"),
    ],
)
def test_trace_domain_from_tool_calls(tools, expected_domain, expected_agent):
    res = _deep_result(tools)
    trace = pt.trace_from_rule_result("q", res, query_mode="REST")
    assert pt.domain_from_tool_calls(res["tool_calls"]) == expected_domain
    assert _agents(trace) == ["RouterAgent", expected_agent]


def test_event_news_vnm_rejects_ohlcv_proxy():
    res = _deep_result(["get_symbol_event_news"], status="unsupported")
    trace = pt.trace_from_rule_result("latest news VNM", res, query_mode="REST")
    assert trace["domain"] == "event_news"
    assert _agents(trace)[1] == "EventNewsAgent"
    assert "get_latest_ohlcv" in trace["agents"][0]["rejected_tools"]


# --- live semantic routing (skipped if QuestDB is unreachable) --------------
def _questdb_up() -> bool:
    res = qr.query_rest_timed("SELECT 1")
    return res.get("status") == "ok"


@pytest.mark.parametrize(
    "query,expected_domain,expected_agent",
    [
        ("summary FPT", "market_summary", "MarketDataAgent"),
        ("summary CTG", "market_summary", "MarketDataAgent"),
        ("summary VCB", "market_summary", "MarketDataAgent"),
        ("summary HPG", "market_summary", "MarketDataAgent"),
        ("financial report FPT", "financial_report", "FinancialReportAgent"),
        ("compare backtest strategies FPT", "backtest", "BacktestAgent"),
        ("latest news FPT", "event_news", "EventNewsAgent"),
        ("latest news VNM", "event_news", "EventNewsAgent"),
    ],
)
def test_live_semantic_routing(query, expected_domain, expected_agent):
    if not _questdb_up():
        pytest.skip("QuestDB REST not reachable in this environment")
    from trading_agent.agent.questdb_agent_service import answer_query

    result = answer_query(query)
    trace = pt.trace_from_rule_result(query, result, query_mode="REST")
    assert trace["domain"] == expected_domain, f"{query} -> {trace['domain']}"
    assert _agents(trace) == ["RouterAgent", expected_agent]
    assert "SystemAgent" not in _agents(trace)
    if expected_domain == "event_news":
        assert "get_latest_ohlcv" in trace["agents"][0]["rejected_tools"]


# --- JSON error handler (no raw 500 text reaches the UI) --------------------
def test_demo_endpoint_returns_json_error_not_raw_500(monkeypatch):
    from fastapi.testclient import TestClient

    from trading_agent.api import fastapi_app

    def _boom(_url):
        raise ModuleNotFoundError("No module named 'pandas'")

    monkeypatch.setattr(fastapi_app, "_build_status", _boom)
    app = fastapi_app.create_app(questdb_url="http://127.0.0.1:9000")
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/demo/status")
    assert resp.status_code == 500
    body = resp.json()  # must be valid JSON, not "Internal Server Error" text
    assert body["status"] == "error"
    assert body["error_type"] == "ModuleNotFoundError"
    assert "pandas" in body["message"]
    assert body["caveats"]


# --- live PGWire (skipped if QuestDB is down) --------------------------------
def test_pgwire_ping_live_or_skip():
    res = pg.ping()
    if res.get("status") != "ok":
        pytest.skip("QuestDB PGWire not reachable in this environment")
    assert res["query_mode"] == "pgwire"
    assert math.isfinite(res["timing"]["total_ms"])
