"""DeepAgents-powered (LLM + tool-calling) agent over the read-only QuestDB tools.

This is the "real agent" mode: an LLM reasons and decides which of our SAFE,
read-only tools to call. It is optional — if `deepagents`/`langchain-openai`
are not installed, or `OPENAI_API_KEY` is unset, ``answer_query_deepagents``
returns a clean error envelope and the rule-based agent remains the fallback.

Safety (strict):
  * Only read-only QuestDB tools are exposed.
  * No write/ingest/DDL; QuestDB localhost reads only.
  * DeepAgents' built-in shell (`execute`) is inert on the default StateBackend,
    and its file tools operate on an in-memory virtual filesystem (sandboxed),
    not the real disk. The system prompt forbids using anything but our tools.
  * No API key is hard-coded; the model reads OPENAI_API_KEY from the env.
"""
from __future__ import annotations

import os
import re
from typing import Any

from trading_agent.tools import questdb_backtest_result_tool as bt_tool
from trading_agent.tools import questdb_financial_report_tool as fa_tool
from trading_agent.tools import questdb_feature_signal_tool as fst
from trading_agent.tools import questdb_market_data_tool as mdt

DEFAULT_MODEL = "gpt-4.1-mini"
MODE = "deepagents"
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,10}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SYSTEM_PROMPT = """You are the VSF trading data agent.
RULES:
- You can ONLY use the provided read-only tools: get_questdb_health, get_latest_ohlcv,
  get_latest_features, get_latest_signal, get_symbol_summary, get_latest_financial_report,
  get_financial_metrics, get_financial_report_summary, get_ohlcv_window, and only when
  explicitly requested, persisted backtest result lookup tools. Never use file, shell, or any other tools.
- Answer strictly from tool outputs. NEVER invent or estimate data that a tool did not return.
- Always state the data source (QuestDB `daily_prices`) and include caveats.
- Do NOT give real-money investment advice. This is research/analytics only.
- Do NOT use market price/OHLCV/features/signals as substitutes for financial reports.
- Do NOT use latest features/signals to summarize an older historical window unless the user explicitly asks to compare current state.
- If the user asks for event/news data, say unavailable because no event/news tool exists yet.
- Resolve relative date ranges against available tool data and state exact dates; do not choose arbitrary months.
- If requested data domain is unavailable, say unavailable.
- Do not suggest or mention backtests unless the user explicitly asks for backtest/simulate/strategy performance.
- Use persisted backtest results only. Do NOT run live Backtrader or any live strategy simulation.
- If a persisted backtest result is missing, say unavailable and tell the operator to run
  `scripts/run_backtrader_questdb_persist.py` first for that symbol/strategy.
- For backtest result lookups, state the persisted assumptions/caveats returned by the tool:
  source table, start/end dates, commission, slippage_bps, adjusted_price_status, code_commit.
- If the user's request is not supported by these tools, say it is unsupported and suggest
  supported examples (DB health, latest <SYMBOL>, OHLCV window, persisted backtest comparison).
- Keep answers concise and in markdown."""

_MODEL_CACHE: dict[str, Any] = {}

_FINANCIAL_REPORT_KEYWORDS = (
    "financial report", "financial reports", "báo cáo tài chính", "bao cao tai chinh",
    "balance sheet", "income statement", "cash flow", "thuyết minh", "thuyet minh",
    "doanh thu", "revenue", "lợi nhuận", "loi nhuan", "profit", "tài sản", "tai san",
    "asset", "assets", "nợ", "no", "liability", "liabilities", "vốn chủ", "von chu", "equity",
)
_EVENT_KEYWORDS = ("event", "events", "news", "tin tức", "tin tuc", "sự kiện", "su kien")
_BACKTEST_KEYWORDS = (
    "backtest", "simulate", "strategy performance", "run strategy",
    "kiểm thử chiến lược", "kiem thu chien luoc", "kết quả backtest", "ket qua backtest",
)


def _validate_symbol(symbol: str) -> str | None:
    sym = (symbol or "").strip().upper()
    return sym if _SYMBOL_RE.match(sym) else None


def _has_any(query: str, keywords: tuple[str, ...]) -> bool:
    q = query.lower()
    return any(k in q for k in keywords)


def _build_tools(questdb_url: str, tool_log: list[dict], allow_backtest: bool = True):
    """Create the safe read-only LangChain tools, logging each invocation."""
    from langchain_core.tools import tool

    def _log(name: str, args: dict, result: dict) -> None:
        tool_log.append({"tool": name, "args": args,
                         "status": result.get("status"), "row_count": result.get("row_count")})

    @tool
    def get_questdb_health() -> dict:
        """Return QuestDB daily_prices health: total rows, distinct symbols, date range."""
        res = mdt.get_table_health(url=questdb_url)
        _log("get_questdb_health", {}, res)
        if res["status"] != "ok" or not res["rows"]:
            return {"status": res["status"], "caveats": res["caveats"]}
        return {"status": "ok", **res["rows"][0], "caveats": res["caveats"]}

    @tool
    def get_latest_ohlcv(symbol: str) -> dict:
        """Return the most recent OHLCV bar for a ticker symbol from QuestDB."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = mdt.get_latest_ohlcv(sym, url=questdb_url)
        _log("get_latest_ohlcv", {"symbol": sym}, res)
        if res["status"] != "ok" or res["row_count"] == 0:
            return {"status": "no_data", "symbol": sym, "caveats": res["caveats"]}
        return {"status": "ok", "symbol": sym, "latest": res["rows"][0], "caveats": res["caveats"]}

    @tool
    def get_latest_features(symbol: str) -> dict:
        """Return the latest deterministic feature snapshot for a ticker symbol."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = fst.get_latest_features(sym, url=questdb_url)
        _log("get_latest_features", {"symbol": sym}, res)
        return {"status": res["status"], "symbol": sym, "features": res.get("data"),
                "caveats": res["caveats"]}

    @tool
    def get_latest_signal(symbol: str, strategy_id: str = "ma20_ma50_v1") -> dict:
        """Return the latest deterministic strategy signal for a ticker symbol."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = fst.get_latest_signal(sym, strategy_id=strategy_id, url=questdb_url)
        _log("get_latest_signal", {"symbol": sym, "strategy_id": strategy_id}, res)
        return {"status": res["status"], "symbol": sym, "signal": res.get("data"),
                "caveats": res["caveats"]}

    @tool
    def get_symbol_summary(symbol: str) -> dict:
        """Combine latest OHLCV, derived features, and deterministic signal for a ticker."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = fst.get_symbol_summary(sym, url=questdb_url)
        _log("get_symbol_summary", {"symbol": sym}, res)
        return {"status": res["status"], **res.get("data", {}), "caveats": res["caveats"]}

    @tool
    def get_latest_financial_report(symbol: str, statement_type: str = "") -> dict:
        """Return latest financial-report metrics for a ticker and optional statement type."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        st = statement_type or None
        res = fa_tool.get_latest_financial_report(sym, st, url=questdb_url)
        _log("get_latest_financial_report", {"symbol": sym, "statement_type": st}, res)
        return {"status": res["status"], "symbol": sym, "rows": res.get("rows", [])[:50], "caveats": res["caveats"]}

    @tool
    def get_financial_metrics(symbol: str, statement_type: str, metric_codes: list[str] | None = None, limit: int = 50) -> dict:
        """Return selected financial metrics for a ticker from QuestDB FA tables."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = fa_tool.get_financial_metrics(sym, statement_type, metric_codes=metric_codes, limit=limit, url=questdb_url)
        _log("get_financial_metrics", {"symbol": sym, "statement_type": statement_type, "metric_codes": metric_codes}, res)
        return {"status": res["status"], "symbol": sym, "rows": res.get("rows", []), "caveats": res["caveats"]}

    @tool
    def get_financial_report_summary(symbol: str) -> dict:
        """Return a compact latest financial-report summary across FA tables for a ticker."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = fa_tool.get_financial_report_summary(sym, url=questdb_url)
        _log("get_financial_report_summary", {"symbol": sym}, res)
        return {"status": res["status"], "symbol": sym, "rows": res.get("rows", [])[:50], "caveats": res["caveats"]}

    @tool
    def get_ohlcv_window(symbol: str, start_date: str, end_date: str,
                         adjusted: bool = True, limit: int = 2000) -> dict:
        """Return OHLCV bars for a symbol between start_date and end_date (YYYY-MM-DD).

        Returns a compact summary (counts + first/last + small head/tail sample), not all rows.
        """
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        if not _DATE_RE.match(start_date or "") or not _DATE_RE.match(end_date or ""):
            return {"status": "error", "caveats": ["dates must be YYYY-MM-DD"]}
        res = mdt.get_ohlcv_window(sym, start_date, end_date, adjusted=adjusted, url=questdb_url)
        _log("get_ohlcv_window", {"symbol": sym, "start_date": start_date, "end_date": end_date,
                                  "adjusted": adjusted}, res)
        if res["status"] != "ok":
            return {"status": "error", "caveats": res["caveats"]}
        rows = res["rows"]
        cap = max(1, int(limit))
        return {
            "status": "ok", "symbol": sym, "start_date": start_date, "end_date": end_date,
            "adjusted": adjusted, "row_count": res["row_count"],
            "first": rows[0] if rows else None, "last": rows[-1] if rows else None,
            "head": rows[:3], "tail": rows[-3:], "note": f"showing summary; full row_count={res['row_count']} (cap {cap})",
            "caveats": res["caveats"],
        }

    @tool
    def get_latest_backtest_metrics(symbol: str, strategy_id: str = "") -> dict:
        """Return latest persisted backtest metrics for a ticker and optional strategy_id."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        sid = strategy_id or None
        res = bt_tool.get_latest_backtest_metrics(sym, strategy_id=sid, url=questdb_url)
        _log("get_latest_backtest_metrics", {"symbol": sym, "strategy_id": sid}, res)
        return {"status": res["status"], "symbol": sym, "rows": res.get("rows", []), "caveats": res["caveats"]}

    @tool
    def get_backtest_strategy_comparison(symbol: str) -> dict:
        """Return latest persisted backtest metric row per strategy for a ticker."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        res = bt_tool.get_backtest_strategy_comparison(sym, url=questdb_url)
        _log("get_backtest_strategy_comparison", {"symbol": sym}, res)
        return {"status": res["status"], "symbol": sym, "rows": res.get("rows", []), "caveats": res["caveats"]}

    @tool
    def get_backtest_equity_curve(symbol: str, strategy_id: str, limit: int = 5000) -> dict:
        """Return bounded persisted equity curve rows for a ticker and strategy_id."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        safe_limit = max(1, min(int(limit), 5000))
        res = bt_tool.get_backtest_equity_curve(sym, strategy_id=strategy_id, limit=safe_limit, url=questdb_url)
        _log("get_backtest_equity_curve", {"symbol": sym, "strategy_id": strategy_id, "limit": safe_limit}, res)
        return {"status": res["status"], "symbol": sym, "rows": res.get("rows", []), "caveats": res["caveats"]}

    tools = [get_questdb_health, get_latest_ohlcv, get_latest_features, get_latest_signal,
             get_symbol_summary, get_latest_financial_report, get_financial_metrics,
             get_financial_report_summary, get_ohlcv_window]
    if allow_backtest:
        tools.extend([get_latest_backtest_metrics, get_backtest_strategy_comparison, get_backtest_equity_curve])
    return tools


def _resolve_model_name(model: str | None) -> str:
    return model or os.environ.get("VSF_DEEPAGENTS_MODEL") or DEFAULT_MODEL


def _get_chat_model(model_name: str, timeout_seconds: int):
    cache_key = f"{model_name}|{timeout_seconds}"
    if cache_key not in _MODEL_CACHE:
        from langchain_openai import ChatOpenAI
        _MODEL_CACHE[cache_key] = ChatOpenAI(model=model_name, temperature=0, timeout=timeout_seconds)
    return _MODEL_CACHE[cache_key]


def _coerce_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return str(content)


def _safe_error(exc: Exception) -> str:
    """Remove API credential fragments from provider exception messages."""
    return re.sub(r"sk-[A-Za-z0-9_*\-]+", "sk-<redacted>", str(exc))


def _remove_backtest_suggestions(answer: str) -> str:
    lines = [line for line in answer.splitlines() if "backtest" not in line.lower()]
    return "\n".join(lines).strip() or answer


def _result(status: str, query: str, answer_markdown: str,
            tool_calls: list[dict], data: dict, caveats: list[str]) -> dict[str, Any]:
    return {
        "status": status, "mode": MODE, "query": query, "answer_markdown": answer_markdown,
        "tool_calls": tool_calls, "data": data, "caveats": caveats,
    }


def deepagents_available() -> tuple[bool, str]:
    try:
        import deepagents  # noqa: F401
        import langchain_openai  # noqa: F401
        return True, ""
    except Exception as exc:  # ImportError or partial install
        return False, str(exc)


def answer_query_deepagents(
    query: str,
    *,
    questdb_url: str = "http://localhost:9000",
    model: str | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return _result("error", query, "Empty query.", [], {}, ["Provide a question."])

    if _has_any(query, _EVENT_KEYWORDS):
        return _result(
            "unsupported",
            query,
            "Event/news data is unavailable: no event/news QuestDB table or tool is implemented yet. I will not use OHLCV as a proxy for events/news.",
            [],
            {},
            ["event/news tool unavailable", "market price tools are disallowed for event/news questions"],
        )

    ok, err = deepagents_available()
    if not ok:
        return _result("error", query,
                       "DeepAgents mode unavailable.", [], {},
                       [f"deepagents/langchain-openai not importable: {err}",
                        "Install: pip install deepagents langchain langchain-openai"])
    if not os.environ.get("OPENAI_API_KEY"):
        return _result("error", query, "DeepAgents mode requires an LLM API key.", [], {},
                       ["OPENAI_API_KEY is not set in the environment.",
                        "Set it (do not hard-code) and retry, or use rule-based mode."])

    from deepagents import create_deep_agent

    model_name = _resolve_model_name(model)
    allow_backtest = _has_any(query, _BACKTEST_KEYWORDS)
    wants_financial = _has_any(query, _FINANCIAL_REPORT_KEYWORDS)
    tool_log: list[dict] = []
    try:
        tools = _build_tools(questdb_url, tool_log, allow_backtest=allow_backtest)
        llm = _get_chat_model(model_name, timeout_seconds)
        agent = create_deep_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)
        out = agent.invoke({"messages": [{"role": "user", "content": query}]},
                           {"recursion_limit": 25})
    except Exception as exc:
        safe_error = _safe_error(exc)
        return _result("error", query, f"DeepAgents run failed: {safe_error}", tool_log,
                       {"model": model_name}, [f"agent_error: {safe_error}"])

    messages = out.get("messages", []) if isinstance(out, dict) else []
    answer = ""
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        role = getattr(msg, "type", "") or getattr(msg, "role", "")
        if content and role in {"ai", "assistant"}:
            answer = _coerce_text(content)
            break
    if not answer and messages:
        answer = _coerce_text(getattr(messages[-1], "content", ""))

    if wants_financial and not any(call.get("tool", "").startswith("get_financial") for call in tool_log):
        return _result(
            "unavailable",
            query,
            "Financial report data is unavailable or no financial-report tool was used. I will not use OHLCV/features/signals as a substitute.",
            tool_log,
            {"model": model_name, "tool_log": tool_log},
            ["financial-report guardrail triggered"],
        )
    if not allow_backtest and answer:
        answer = _remove_backtest_suggestions(answer)

    caveats = ["mode=deepagents (LLM tool-calling)", f"model={model_name}",
               "answers are grounded in read-only QuestDB tool outputs; not investment advice"]
    if not tool_log:
        caveats.append("no data tool was called for this query")
    status = "ok" if answer else "error"
    return _result(status, query, answer or "No answer produced.", tool_log,
                   {"model": model_name, "tool_log": tool_log}, caveats)
