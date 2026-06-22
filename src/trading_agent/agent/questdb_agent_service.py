"""Rule-based agent service over the read-only QuestDB market-data tools.

Single entry point: ``answer_query(query)`` -> structured dict. The "agent" is
rule-based (no LLM, no discretionary signals) but it calls REAL tools and only
reports data that QuestDB actually returns. Every response carries caveats/status.

Supported intents:
  * db_health     - "how many rows are in QuestDB", "db status", "questdb health"
  * latest_ohlcv  - "show latest FPT data", "latest HPG", "HPG hôm nay thế nào"
  * latest_features - "FPT features"
  * latest_signal - "latest signal FPT", "FPT signal"
  * symbol_summary - "summary FPT", "HPG hôm nay thế nào"
  * ohlcv_window  - "show FPT from 2020-01-01 to 2025-12-31", "OHLCV VNM 2021 to 2024"
  * ma_backtest   - "backtest MA strategy for FPT from 2020 to 2025", "ma20 ma50 HPG 2021 2024"
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from trading_agent.strategies.simple_ma_cross import format_report, run_ma_cross_backtest
from trading_agent.tools import questdb_feature_signal_tool as feature_signal_tool
from trading_agent.tools import questdb_market_data_tool as tool

SUPPORTED_EXAMPLES = [
    "how many rows are in QuestDB",
    "show latest FPT data",
    "show FPT from 2020-01-01 to 2025-12-31",
    "backtest MA strategy for FPT from 2020 to 2025",
    "summary FPT",
    "latest signal FPT",
]

# Tokens that are never ticker symbols.
_STOPWORDS = {
    "MA", "FROM", "TO", "IN", "HOW", "MANY", "ROWS", "ROW", "ARE", "THE", "DATA",
    "SHOW", "LATEST", "LAST", "PRICE", "FOR", "OF", "QUESTDB", "DB", "STRATEGY",
    "BACKTEST", "RUN", "GET", "LIST", "UNIVERSE", "SYMBOLS", "AND", "WITH", "A",
    "COUNT", "TOTAL", "HEALTH", "TABLE", "IS", "WHAT", "OHLCV", "WINDOW", "HISTORY",
    "CURRENT", "TODAY", "NOW", "QUOTE", "STATUS", "CROSS", "MOVING", "AVERAGE",
    "SIGNAL", "SIGNALS", "FEATURE", "FEATURES", "SUMMARY", "SUMMARIZE", "USING",
    # common Vietnamese function words (ASCII forms)
    "HOM", "NAY", "NAO", "GIA", "THE", "CUA", "VE",
}


def _tokens(query: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]{1,12}", query.upper())


def extract_symbol(query: str) -> str | None:
    for token in _tokens(query):
        if token in _STOPWORDS:
            continue
        if re.fullmatch(r"MA\d+", token):       # MA window spec, not a symbol
            continue
        if token.isdigit():                      # numbers / years
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", token):
            return token
    return None


def extract_dates(query: str) -> tuple[str | None, str | None]:
    iso = re.findall(r"\d{4}-\d{2}-\d{2}", query)
    if len(iso) >= 2:
        return iso[0], iso[1]
    if len(iso) == 1:
        return iso[0], iso[0]
    years = re.findall(r"\b(20\d{2})\b", query)
    if len(years) >= 2:
        return f"{years[0]}-01-01", f"{years[1]}-12-31"
    if len(years) == 1:
        return f"{years[0]}-01-01", f"{years[0]}-12-31"
    return None, None


def extract_ma_windows(query: str) -> tuple[int, int]:
    windows = sorted(int(m) for m in re.findall(r"MA(\d+)", query.upper()))
    if len(windows) >= 2:
        return windows[0], windows[1]
    return 20, 50


_LATEST_KEYWORDS = ("latest", "last", "current", "today", "hôm nay", "hom nay", "now", "price", "show", "quote")


def _has_latest_keyword(query: str) -> bool:
    return any(k in query.lower() for k in _LATEST_KEYWORDS)


def classify(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ("how many", "row count", "db status", "questdb health", "db health", "table health")) \
            or q.strip() in {"health", "status", "db", "questdb"}:
        return "db_health"
    if any(k in q for k in ("backtest", "ma strategy", "ma cross", "moving average")) or re.search(r"ma\d+", q):
        return "ma_backtest"
    sym = extract_symbol(query)
    if sym and any(k in q for k in ("summary", "summarize", "hôm nay thế nào", "hom nay the nao")):
        return "symbol_summary"
    if sym and "feature" in q:
        return "latest_features"
    if sym and "signal" in q:
        return "latest_signal"
    has_range = bool(re.search(r"\d{4}-\d{2}-\d{2}", query)) or len(re.findall(r"\b20\d{2}\b", query)) >= 2 \
        or any(k in q for k in ("ohlcv", "window", "history", " from ", "between"))
    if has_range and sym:
        return "ohlcv_window"
    if sym and _has_latest_keyword(query):
        return "latest_ohlcv"
    if sym:
        return "latest_ohlcv"
    return "unsupported"


def _result(status: str, intent: str, query: str, answer_markdown: str,
            tool_calls: list[dict], data: dict, caveats: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "intent": intent,
        "query": query,
        "answer_markdown": answer_markdown,
        "tool_calls": tool_calls,
        "data": data,
        "caveats": caveats,
    }


def _call(tool_calls: list[dict], name: str, args: dict, result: dict) -> dict:
    tool_calls.append({
        "tool": name, "args": args,
        "status": result.get("status"), "row_count": result.get("row_count"),
    })
    return result


def answer_query(query: str, *, questdb_url: str = tool.DEFAULT_URL) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return _result("error", "none", query, "Empty query.", [], {}, ["Provide a question."])
    intent = classify(query)
    tool_calls: list[dict] = []

    if intent == "db_health":
        res = _call(tool_calls, "get_table_health", {}, tool.get_table_health(url=questdb_url))
        if res["status"] != "ok" or not res["rows"]:
            return _result("error", intent, query, "QuestDB health query failed.", tool_calls, {}, res["caveats"])
        row = res["rows"][0]
        adj = row.get("adjustment_status_breakdown", [])
        md = [
            "**QuestDB `daily_prices` health**",
            f"- rows: **{int(row.get('total_rows', 0)):,}**",
            f"- distinct symbols: **{int(row.get('symbols', 0)):,}**",
            f"- date range: {str(row.get('first_date'))[:10]} .. {str(row.get('last_date'))[:10]}",
        ]
        for a in adj:
            md.append(f"- adjustment_status `{a.get('adjustment_status')}`: {int(a.get('rows', 0)):,}")
        return _result("ok", intent, query, "\n".join(md), tool_calls, {"health": row}, res["caveats"])

    symbol = extract_symbol(query)

    if intent in {"latest_features", "latest_signal", "symbol_summary"}:
        if not symbol:
            return _unsupported(query, ["No ticker symbol found in the request."])
        if intent == "latest_features":
            res = _call(
                tool_calls,
                "get_latest_features",
                {"symbol": symbol},
                feature_signal_tool.get_latest_features(symbol, url=questdb_url),
            )
            if res["status"] != "ok" or not res["rows"]:
                return _result("error", intent, query, f"No derived features for {symbol}.", tool_calls, {}, res["caveats"])
            row = res["rows"][0]
            md = (
                f"**{symbol} latest features** ({str(row['trade_date'])[:10]})\n"
                f"- adjusted close: {row.get('adjusted_close')} · return_1d: {row.get('return_1d')}\n"
                f"- MA20: {row.get('ma20')} · MA50: {row.get('ma50')} · volatility20: {row.get('volatility20')}\n"
                f"- feature version: `{row.get('feature_version')}` · quality: `{row.get('quality_status')}`"
            )
            return _result("ok", intent, query, md, tool_calls, {"features": row}, res["caveats"])
        if intent == "latest_signal":
            res = _call(
                tool_calls,
                "get_latest_signal",
                {"symbol": symbol, "strategy_id": "ma20_ma50_v1"},
                feature_signal_tool.get_latest_signal(symbol, url=questdb_url),
            )
            if res["status"] != "ok" or not res["rows"]:
                return _result("error", intent, query, f"No derived signal for {symbol}.", tool_calls, {}, res["caveats"])
            row = res["rows"][0]
            md = (
                f"**{symbol} latest deterministic signal** ({str(row['trade_date'])[:10]})\n"
                f"- signal: **{row.get('signal')}** · score: {row.get('score')}\n"
                f"- reason: `{row.get('reason_code')}` · execution: `{row.get('intended_execution')}`\n"
                f"- strategy: `{row.get('strategy_id')}` · quality: `{row.get('quality_status')}`"
            )
            return _result("ok", intent, query, md, tool_calls, {"signal": row}, res["caveats"])

        res = feature_signal_tool.get_symbol_summary(symbol, url=questdb_url)
        tool_calls.extend(res.get("tool_calls", []))
        if res["status"] not in {"ok", "partial"} or not res.get("data"):
            return _result("error", intent, query, f"No summary data for {symbol}.", tool_calls, {}, res["caveats"])
        data = res["data"]
        latest = data.get("latest") or {}
        features = data.get("features") or {}
        signal = data.get("signal") or {}
        md = (
            f"**{symbol} market summary** ({str(latest.get('trade_date') or features.get('trade_date') or signal.get('trade_date'))[:10]})\n"
            f"- close: {latest.get('close')} · adjusted close: {features.get('adjusted_close')} · volume: {latest.get('volume')}\n"
            f"- MA20: {features.get('ma20')} · MA50: {features.get('ma50')} · volatility20: {features.get('volatility20')}\n"
            f"- deterministic signal: **{signal.get('signal')}** · score: {signal.get('score')} · reason: `{signal.get('reason_code')}`"
        )
        return _result(res["status"], intent, query, md, tool_calls, data, res["caveats"])

    if intent == "latest_ohlcv":
        if not symbol:
            return _unsupported(query, ["No ticker symbol found in the request."])
        res = _call(tool_calls, "get_latest_ohlcv", {"symbol": symbol}, tool.get_latest_ohlcv(symbol, url=questdb_url))
        if res["status"] != "ok" or res["row_count"] == 0:
            if not _has_latest_keyword(query):
                # Weak guess (no market keyword) that has no data -> not a market query.
                return _unsupported(query, [f"Query not recognized (guessed symbol '{symbol}' has no data in QuestDB)."])
            return _result("error", intent, query, f"No data for {symbol} in QuestDB.", tool_calls, {}, res["caveats"])
        r = res["rows"][0]
        md = (
            f"**{symbol} latest bar** ({str(r['trade_date'])[:10]}, {r.get('exchange')})\n"
            f"- open {r['open']} / high {r['high']} / low {r['low']} / close {r['close']}\n"
            f"- adjusted_close {r['adjusted_close']} · volume {r['volume']} · value {r['value']}\n"
            f"- adjustment_status `{r['adjustment_status']}` · quality `{r['quality_status']}`"
        )
        return _result("ok", intent, query, md, tool_calls, {"latest": r}, res["caveats"])

    if intent == "ohlcv_window":
        if not symbol:
            return _unsupported(query, ["No ticker symbol found in the request."])
        start, end = extract_dates(query)
        caveats: list[str] = []
        if not start or not end:
            start, end = "2020-01-01", "2025-12-31"
            caveats.append("No date range parsed; defaulted to 2020-01-01..2025-12-31.")
        res = _call(tool_calls, "get_ohlcv_window", {"symbol": symbol, "start_date": start, "end_date": end},
                    tool.get_ohlcv_window(symbol, start, end, adjusted=True, url=questdb_url))
        if res["status"] != "ok":
            return _result("error", intent, query, "QuestDB window query failed.", tool_calls, {}, res["caveats"] + caveats)
        rows = res["rows"]
        if not rows:
            return _result("ok", intent, query, f"No rows for {symbol} in {start}..{end}.", tool_calls,
                           {"row_count": 0}, res["caveats"] + caveats)
        first, last = rows[0], rows[-1]
        md = (
            f"**{symbol} OHLCV {start} .. {end}** (adjusted)\n"
            f"- bars: **{len(rows):,}**\n"
            f"- first {str(first['trade_date'])[:10]} close {first['close']}\n"
            f"- last  {str(last['trade_date'])[:10]} close {last['close']}"
        )
        data = {"row_count": len(rows), "first": first, "last": last,
                "sample_head": rows[:3], "sample_tail": rows[-3:]}
        return _result("ok", intent, query, md, tool_calls, data, res["caveats"] + caveats)

    if intent == "ma_backtest":
        if not symbol:
            return _unsupported(query, ["No ticker symbol found in the request."])
        start, end = extract_dates(query)
        caveats = []
        if not start or not end:
            start, end = "2020-01-01", "2025-12-31"
            caveats.append("No date range parsed; defaulted to 2020-01-01..2025-12-31.")
        fast, slow = extract_ma_windows(query)
        res = _call(tool_calls, "get_ohlcv_window",
                    {"symbol": symbol, "start_date": start, "end_date": end, "adjusted": True},
                    tool.get_ohlcv_window(symbol, start, end, adjusted=True, url=questdb_url))
        if res["status"] != "ok" or res["row_count"] == 0:
            return _result("error", intent, query, f"No data for {symbol} in {start}..{end} to backtest.",
                           tool_calls, {}, res["caveats"] + caveats)
        df = pd.DataFrame(res["rows"])
        bt = run_ma_cross_backtest(df, fast=fast, slow=slow)
        tool_calls.append({"tool": "run_ma_cross_backtest",
                           "args": {"fast": fast, "slow": slow, "bars": res["row_count"]},
                           "status": bt.get("status"), "row_count": res["row_count"]})
        if bt.get("status") != "ok":
            return _result("error", intent, query, f"Backtest error: {bt.get('caveats')}",
                           tool_calls, {}, res["caveats"] + caveats + bt.get("caveats", []))
        md = "```\n" + format_report(symbol, bt) + "\n```"
        return _result("ok", intent, query, md, tool_calls,
                       {"metrics": bt["metrics"], "params": bt["params"]},
                       res["caveats"] + caveats + bt["caveats"])

    return _unsupported(query, ["Query intent not recognized."])


def _unsupported(query: str, reasons: list[str]) -> dict[str, Any]:
    md = "I can't handle that yet. Try:\n" + "\n".join(f"- {e}" for e in SUPPORTED_EXAMPLES)
    return _result("unsupported", "unsupported", query, md, [], {"supported_examples": SUPPORTED_EXAMPLES}, reasons)
