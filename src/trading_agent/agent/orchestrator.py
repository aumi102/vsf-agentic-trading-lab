from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from trading_agent.tools._store import DEFAULT_DB_PATH
from trading_agent.tools.feature_tool import compute_latest_features
from trading_agent.tools.market_data_tool import get_latest_market_data
from trading_agent.tools.report_tool import compose_market_answer
from trading_agent.tools.risk_tool import assess_symbol_risk
from trading_agent.tools.signal_tool import evaluate_active_signals


BUILD_INSTRUCTION = "python scripts/build_mvp_db.py --symbols FPT,VNM,VCB"
DEMO_SYMBOLS = ("FPT", "VNM", "VCB", "REE", "SAM")
TOOL_CALL_SEQUENCE = ["market_data", "features", "signal", "risk", "report"]
_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}\b")


def answer_market_query(
    query: str | None = None,
    symbol: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    language: str = "vi",
) -> dict[str, object]:
    normalized_query = (query or "").strip()
    path = Path(db_path)
    available_symbols = _available_symbols(path)
    resolved_symbol = _resolve_symbol(symbol=symbol, query=normalized_query, available_symbols=available_symbols)

    if resolved_symbol is None:
        return _needs_symbol_response(normalized_query)
    if not path.exists():
        return _missing_store_response(normalized_query, resolved_symbol, path)

    market = get_latest_market_data(resolved_symbol, path)
    features = compute_latest_features(resolved_symbol, path)
    signal = evaluate_active_signals(resolved_symbol, path)
    risk = assess_symbol_risk(resolved_symbol, path)
    report = compose_market_answer(resolved_symbol, language=language, db_path=path)
    status = "ok"
    if market.get("status") == "not_found":
        status = "not_found"
    elif report.get("status") != "ok":
        status = str(report.get("status") or "not_available")

    caveats = []
    for output in [market, features, signal, risk, report]:
        caveats.extend(output.get("caveats") or [])

    return {
        "status": status,
        "query": normalized_query,
        "symbol": resolved_symbol,
        "tool_call_sequence": TOOL_CALL_SEQUENCE.copy(),
        "tool_outputs": {
            "market_data": market,
            "features": features,
            "signal": signal,
            "risk": risk,
            "report": report,
        },
        "answer_markdown": report.get("answer_markdown", ""),
        "caveats": sorted(set(str(item) for item in caveats)),
        "not_financial_advice": True,
    }


def _available_symbols(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set(DEMO_SYMBOLS)
    try:
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT DISTINCT symbol FROM securities").fetchall()
    except sqlite3.Error:
        return set(DEMO_SYMBOLS)
    symbols = {str(row[0]).strip().upper() for row in rows if row and str(row[0]).strip()}
    return symbols or set(DEMO_SYMBOLS)


def _resolve_symbol(symbol: str | None, query: str, available_symbols: set[str]) -> str | None:
    if symbol and symbol.strip():
        return symbol.strip().upper()
    upper_query = query.upper()
    for candidate in sorted(available_symbols, key=len, reverse=True):
        if re.search(rf"\b{re.escape(candidate)}\b", upper_query):
            return candidate
    candidates = _SYMBOL_RE.findall(query)
    return candidates[0].upper() if candidates else None


def _needs_symbol_response(query: str) -> dict[str, object]:
    answer = (
        "Mình chưa xác định được mã chứng khoán cần hỏi. "
        "Vui lòng truyền `--symbol FPT` hoặc hỏi rõ mã như `FPT hôm nay thế nào?`."
    )
    return {
        "status": "needs_symbol",
        "query": query,
        "symbol": None,
        "tool_call_sequence": [],
        "tool_outputs": {},
        "answer_markdown": answer,
        "caveats": ["No symbol was resolved from the input."],
        "not_financial_advice": True,
    }


def _missing_store_response(query: str, symbol: str, db_path: Path) -> dict[str, object]:
    answer = (
        f"Chưa có MVP SQLite store tại `{db_path}`. "
        f"Hãy chạy `{BUILD_INSTRUCTION}` trước khi hỏi về `{symbol}`."
    )
    return {
        "status": "missing_store",
        "query": query,
        "symbol": symbol,
        "tool_call_sequence": [],
        "tool_outputs": {},
        "answer_markdown": answer,
        "caveats": [f"MVP store missing: {db_path}", f"Build command: {BUILD_INSTRUCTION}"],
        "not_financial_advice": True,
    }
