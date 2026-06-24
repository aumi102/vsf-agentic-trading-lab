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
  * backtest_results - "backtest FPT", "compare backtest strategies FPT"
"""
from __future__ import annotations

import re
from typing import Any

from trading_agent.tools import questdb_backtest_result_tool as backtest_tool
from trading_agent.tools import questdb_event_news_tool as event_news_tool
from trading_agent.tools import questdb_financial_report_tool as fa_tool
from trading_agent.tools import questdb_feature_signal_tool as feature_signal_tool
from trading_agent.tools import questdb_market_data_tool as tool

SUPPORTED_EXAMPLES = [
    "how many rows are in QuestDB",
    "show latest FPT data",
    "show FPT from 2020-01-01 to 2025-12-31",
    "compare backtest strategies FPT",
    "MA20/MA50 backtest FPT",
    "summary FPT",
    "latest signal FPT",
    "latest news FPT",
]

# Tokens that are never ticker symbols.
_STOPWORDS = {
    "MA", "FROM", "TO", "IN", "HOW", "MANY", "ROWS", "ROW", "ARE", "THE", "DATA",
    "SHOW", "LATEST", "LAST", "PRICE", "FOR", "OF", "QUESTDB", "DB", "STRATEGY",
    "BACKTEST", "RUN", "GET", "LIST", "UNIVERSE", "SYMBOLS", "AND", "WITH", "A",
    "RESULT", "RESULTS", "COMPARE", "SIMULATE", "PERFORMANCE", "STRATEGY", "STRATEGIES",
    "COUNT", "TOTAL", "HEALTH", "TABLE", "IS", "WHAT", "OHLCV", "WINDOW", "HISTORY",
    "CURRENT", "TODAY", "NOW", "QUOTE", "STATUS", "CROSS", "MOVING", "AVERAGE",
    "SIGNAL", "SIGNALS", "FEATURE", "FEATURES", "SUMMARY", "SUMMARIZE", "USING",
    "FINANCIAL", "REPORT", "REPORTS", "BALANCE", "SHEET", "INCOME", "STATEMENT",
    "CASH", "FLOW", "EVENT", "EVENTS", "NEWS", "MONTH", "PAST",
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


def _has_latest_keyword(query: str) -> bool:
    return any(k in query.lower() for k in _LATEST_KEYWORDS)


def _has_any(query: str, keywords: tuple[str, ...]) -> bool:
    q = query.lower()
    return any(k in q for k in keywords)


def _statement_type_from_query(query: str) -> str | None:
    q = query.lower()
    if "balance sheet" in q or any(k in q for k in ("tài sản", "tai san", "liability", "liabilities", "vốn chủ", "von chu")):
        return "BALANCE_SHEET"
    if "income statement" in q or any(k in q for k in ("doanh thu", "revenue", "lợi nhuận", "loi nhuan", "profit")):
        return "INCOME_STATEMENT"
    if "cash flow" in q:
        return "CASH_FLOW"
    if any(k in q for k in ("thuyết minh", "thuyet minh", "notes", "note")):
        return "NOTE"
    return None


def classify(query: str) -> str:
    q = query.lower()
    if _has_any(query, _EVENT_KEYWORDS):
        return "event_unavailable"
    if _has_any(query, _FINANCIAL_REPORT_KEYWORDS):
        return "financial_report"
    if any(k in q for k in ("how many", "row count", "db status", "questdb health", "db health", "table health")) \
            or q.strip() in {"health", "status", "db", "questdb"}:
        return "db_health"
    if _has_any(query, _BACKTEST_KEYWORDS):
        return "backtest_results"
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


def _strategy_id_from_query(query: str) -> str | None:
    q = query.lower()
    if any(k in q for k in ("ma20", "ma50", "ma20/ma50", "ma 20", "ma 50", "moving average")):
        return "ma20_ma50"
    if any(k in q for k in ("buy hold", "buy-and-hold", "buy_hold", "hold baseline")):
        return "buy_hold"
    if "rsi" in q:
        return "rsi_mean_reversion"
    return None


def _fmt(value: Any, decimals: int = 2) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value: Any, decimals: int = 2) -> str:
    text = _fmt(value, decimals)
    return text if text == "n/a" else f"{text}%"


def _format_backtest_answer(symbol: str, rows: list[dict[str, Any]], *, comparison: bool) -> str:
    if not rows:
        return f"No persisted backtest results found for {symbol}."
    first = rows[0]
    start = str(first.get("start_date") or "")[:10]
    end = str(first.get("end_date") or "")[:10]
    lines = [
        f"**{symbol} persisted backtest results** ({start} .. {end})",
        "- source: QuestDB persisted `backtest_runs` / `backtest_metrics`",
        f"- source table: `{first.get('source_table')}` · code commit: `{first.get('code_commit')}`",
        f"- commission: {_fmt(first.get('commission'), 4)} · slippage_bps: {_fmt(first.get('slippage_bps'), 2)}",
        f"- price_band_status: `{first.get('price_band_status') or 'not_recorded'}`",
        f"- adjusted_price_status: `{first.get('adjusted_price_status')}`",
        "",
        "| Strategy | Final value | Total return | Annualized | Max DD | Sharpe | Trades | Win rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.get('strategy_id')}` | {_fmt(row.get('final_value'), 0)} | "
            f"{_fmt_pct(row.get('total_return_pct'))} | {_fmt_pct(row.get('annualized_return_pct'))} | "
            f"{_fmt_pct(row.get('max_drawdown_pct'))} | {_fmt(row.get('sharpe_ratio'))} | "
            f"{int(row.get('closed_trades') or 0)} | {_fmt_pct(row.get('win_rate_pct'))} |"
        )
    lines.append("")
    lines.append("Research-only persisted lookup; no live Backtrader execution was run by the agent.")
    if not comparison:
        lines.append("Use `compare backtest strategies <SYMBOL>` to see all persisted strategies for the symbol.")
    return "\n".join(lines)


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

    if intent == "event_unavailable":
        if not symbol:
            return _result(
                "unsupported",
                intent,
                query,
                "Event/news data requires a ticker symbol. I will not use OHLCV as a proxy for events/news.",
                [],
                {},
                ["event/news symbol missing", "market price tools are disallowed for event/news questions"],
            )
        res = _call(
            tool_calls,
            "get_symbol_event_news",
            {"symbol": symbol, "limit": 5},
            event_news_tool.get_symbol_event_news(symbol, limit=5, url=questdb_url),
        )
        if res.get("status") != "ok" or not res.get("rows"):
            return _result(
                "unsupported",
                intent,
                query,
                f"Event/news data is unavailable for {symbol}. I will not use OHLCV as a proxy for events/news.",
                tool_calls,
                {},
                res.get("caveats", []) + ["market price tools are disallowed for event/news questions"],
            )
        rows = res["rows"]
        lines = [
            f"**{symbol} latest official disclosure/event records**",
            "- source: QuestDB `event_news_items`",
            "- scope: official disclosure records only, not general news",
            "",
            "| Date | Category | Title | Source |",
            "|---|---|---|---|",
        ]
        for row in rows:
            title = str(row.get("title") or "").replace("|", "\\|")
            lines.append(
                f"| {str(row.get('published_at') or '')[:10]} | `{row.get('category')}` | {title} | `{row.get('source')}` |"
            )
        return _result("ok", intent, query, "\n".join(lines), tool_calls, {"rows": rows}, res.get("caveats", []))

    if intent == "financial_report":
        if not symbol:
            return _unsupported(query, ["No ticker symbol found in the financial-report request."])
        statement_type = _statement_type_from_query(query)
        if statement_type:
            res = _call(
                tool_calls,
                "get_latest_financial_report",
                {"symbol": symbol, "statement_type": statement_type},
                fa_tool.get_latest_financial_report(symbol, statement_type, url=questdb_url),
            )
        else:
            res = _call(
                tool_calls,
                "get_financial_report_summary",
                {"symbol": symbol},
                fa_tool.get_financial_report_summary(symbol, url=questdb_url),
            )
        if res.get("status") != "ok" or not res.get("rows"):
            return _result(
                "unavailable",
                intent,
                query,
                f"Financial report data is unavailable for {symbol}. FA tables must be ingested before this question can be answered.",
                tool_calls,
                {},
                res.get("caveats", []) + ["OHLCV/features/signals were not used as a substitute for financial reports"],
            )
        rows = res["rows"]
        latest_date = str(rows[0].get("public_date") or rows[0].get("period_end_date") or "")[:10]
        sections = sorted({str(row.get("statement_type")) for row in rows})
        md = (
            f"**{symbol} financial report data** ({latest_date})\n"
            f"- statements: {', '.join(sections)}\n"
            f"- metric rows returned: {len(rows):,}\n"
            "- metric names may be blank where Vietcap IQ metric mapping is unverified"
        )
        return _result("ok", intent, query, md, tool_calls, {"rows": rows[:20], "returned": len(rows)}, res.get("caveats", []))

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

    if intent == "backtest_results":
        if not symbol:
            return _unsupported(query, ["No ticker symbol found in the request."])
        strategy_id = _strategy_id_from_query(query)
        wants_compare = strategy_id is None or "compare" in query.lower() or "strategies" in query.lower()
        if wants_compare:
            res = _call(
                tool_calls,
                "get_backtest_strategy_comparison",
                {"symbol": symbol},
                backtest_tool.get_backtest_strategy_comparison(symbol, url=questdb_url),
            )
        else:
            res = _call(
                tool_calls,
                "get_latest_backtest_metrics",
                {"symbol": symbol, "strategy_id": strategy_id},
                backtest_tool.get_latest_backtest_metrics(symbol, strategy_id=strategy_id, url=questdb_url),
            )
        if res.get("status") != "ok" or not res.get("rows"):
            return _result(
                "unavailable",
                intent,
                query,
                f"Persisted backtest result is unavailable for {symbol}. Run `scripts/run_backtrader_questdb_persist.py` first for this symbol/strategy.",
                tool_calls,
                {},
                res.get("caveats", []),
            )
        rows = res["rows"]
        md = _format_backtest_answer(symbol, rows, comparison=wants_compare)
        return _result("ok", intent, query, md, tool_calls, {"rows": rows}, res.get("caveats", []))

    return _unsupported(query, ["Query intent not recognized."])


def _unsupported(query: str, reasons: list[str]) -> dict[str, Any]:
    md = "I can't handle that yet. Try:\n" + "\n".join(f"- {e}" for e in SUPPORTED_EXAMPLES)
    return _result("unsupported", "unsupported", query, md, [], {"supported_examples": SUPPORTED_EXAMPLES}, reasons)
