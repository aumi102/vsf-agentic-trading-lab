"""DeepAgents-powered (LLM + tool-calling) agent over the read-only QuestDB tools.

This is the "real agent" mode: an LLM reasons and decides which of our SAFE,
read-only tools to call. It is optional — if `deepagents`/`langchain-openai`
are not installed, or `OPENAI_API_KEY` is unset, ``answer_query_deepagents``
returns a clean error envelope and the rule-based agent remains the fallback.

Safety (strict):
  * Only 4 read-only tools are exposed: health, latest, window, MA backtest.
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

from trading_agent.strategies.simple_ma_cross import run_ma_cross_backtest
from trading_agent.tools import questdb_market_data_tool as mdt

DEFAULT_MODEL = "gpt-4.1-mini"
MODE = "deepagents"
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,10}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SYSTEM_PROMPT = """You are the VSF trading data agent.
RULES:
- You can ONLY use the provided read-only tools: get_questdb_health, get_latest_ohlcv,
  get_ohlcv_window, run_ma_backtest. Never use file, shell, or any other tools.
- Answer strictly from tool outputs. NEVER invent or estimate data that a tool did not return.
- Always state the data source (QuestDB `daily_prices`) and include caveats.
- Do NOT give real-money investment advice. This is research/analytics only.
- For a backtest, state the assumptions explicitly: MA20/MA50 crossover (unless the user
  asked otherwise), prices are the source-reported/adjusted close (adjustment_status may be
  `adjusted_price_missing_warn`), the transaction cost in bps, long-only, and next-day-close
  execution (leak-free).
- If the user's request is not supported by these tools, say it is unsupported and suggest
  supported examples (DB health, latest <SYMBOL>, OHLCV window, MA backtest).
- Keep answers concise and in markdown."""

_MODEL_CACHE: dict[str, Any] = {}


def _validate_symbol(symbol: str) -> str | None:
    sym = (symbol or "").strip().upper()
    return sym if _SYMBOL_RE.match(sym) else None


def _build_tools(questdb_url: str, tool_log: list[dict]):
    """Create the 4 safe read-only LangChain tools, logging each invocation."""
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
    def run_ma_backtest(symbol: str, start_date: str, end_date: str,
                        fast_window: int = 20, slow_window: int = 50,
                        transaction_cost_bps: float = 15.0) -> dict:
        """Run a long-only MA crossover backtest (adjusted close) on QuestDB data and return metrics."""
        sym = _validate_symbol(symbol)
        if not sym:
            return {"status": "error", "caveats": [f"invalid symbol: {symbol!r}"]}
        if not _DATE_RE.match(start_date or "") or not _DATE_RE.match(end_date or ""):
            return {"status": "error", "caveats": ["dates must be YYYY-MM-DD"]}
        res = mdt.get_ohlcv_window(sym, start_date, end_date, adjusted=True, url=questdb_url)
        _log("run_ma_backtest", {"symbol": sym, "start_date": start_date, "end_date": end_date,
                                 "fast_window": fast_window, "slow_window": slow_window,
                                 "transaction_cost_bps": transaction_cost_bps}, res)
        if res["status"] != "ok" or res["row_count"] == 0:
            return {"status": "error", "symbol": sym,
                    "caveats": res["caveats"] + [f"no data for {sym} in {start_date}..{end_date}"]}
        import pandas as pd
        bt = run_ma_cross_backtest(pd.DataFrame(res["rows"]), fast=int(fast_window),
                                   slow=int(slow_window), cost_bps=float(transaction_cost_bps))
        if bt.get("status") != "ok":
            return {"status": "error", "symbol": sym, "caveats": res["caveats"] + bt.get("caveats", [])}
        return {"status": "ok", "symbol": sym, "params": bt["params"], "metrics": bt["metrics"],
                "caveats": res["caveats"] + bt["caveats"]}

    return [get_questdb_health, get_latest_ohlcv, get_ohlcv_window, run_ma_backtest]


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
    tool_log: list[dict] = []
    try:
        tools = _build_tools(questdb_url, tool_log)
        llm = _get_chat_model(model_name, timeout_seconds)
        agent = create_deep_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)
        out = agent.invoke({"messages": [{"role": "user", "content": query}]},
                           {"recursion_limit": 25})
    except Exception as exc:
        return _result("error", query, f"DeepAgents run failed: {exc}", tool_log,
                       {"model": model_name}, [f"agent_error: {exc}"])

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

    caveats = ["mode=deepagents (LLM tool-calling)", f"model={model_name}",
               "answers are grounded in read-only QuestDB tool outputs; not investment advice"]
    if not tool_log:
        caveats.append("no data tool was called for this query")
    status = "ok" if answer else "error"
    return _result(status, query, answer or "No answer produced.", tool_log,
                   {"model": model_name, "tool_log": tool_log}, caveats)
