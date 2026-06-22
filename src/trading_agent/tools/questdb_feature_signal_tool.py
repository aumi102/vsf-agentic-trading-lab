"""Read-only QuestDB tools for deterministic feature and signal side tables."""
from __future__ import annotations

import re
from typing import Any

from trading_agent.tools import questdb_market_data_tool as market

DEFAULT_URL = market.DEFAULT_URL
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
_STRATEGY_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _error(caveat: str) -> dict[str, Any]:
    return {
        "status": "error", "rows": [], "data": {}, "row_count": 0,
        "source": "questdb", "sql": "", "tool_calls": [], "caveats": [caveat],
    }


def _normalized(result: dict[str, Any], tool_name: str) -> dict[str, Any]:
    rows = result.get("rows", [])
    result["data"] = rows[0] if rows else {}
    result["tool_calls"] = [{
        "tool": tool_name,
        "status": result.get("status"),
        "row_count": result.get("row_count", 0),
    }]
    return result


def get_latest_features(symbol: str, url: str = DEFAULT_URL) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not _SYMBOL_RE.fullmatch(sym):
        return _error(f"invalid_symbol: {symbol!r}")
    sql = (
        "SELECT trade_date, security_id, symbol, adjusted_close, volume, return_1d, "
        "ma20, ma50, volatility20, volume_ma20, close_to_ma20, close_to_ma50, "
        "feature_version, quality_status, source_table FROM feature_snapshots "
        f"WHERE symbol = '{sym}' ORDER BY trade_date DESC LIMIT 1"
    )
    result = _normalized(market.query_questdb(sql, url=url), "get_latest_features")
    if result["status"] == "ok" and not result["rows"]:
        result["caveats"].append(f"No feature rows for symbol '{sym}'.")
    return result


def get_latest_signal(
    symbol: str,
    strategy_id: str = "ma20_ma50_v1",
    url: str = DEFAULT_URL,
) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    strategy = (strategy_id or "").strip()
    if not _SYMBOL_RE.fullmatch(sym):
        return _error(f"invalid_symbol: {symbol!r}")
    if not _STRATEGY_RE.fullmatch(strategy):
        return _error(f"invalid_strategy_id: {strategy_id!r}")
    sql = (
        "SELECT trade_date, security_id, symbol, strategy_id, signal, score, reason_code, "
        "intended_execution, feature_version, signal_version, quality_status FROM signals "
        f"WHERE symbol = '{sym}' AND strategy_id = '{strategy}' "
        "ORDER BY trade_date DESC LIMIT 1"
    )
    result = _normalized(market.query_questdb(sql, url=url), "get_latest_signal")
    if result["status"] == "ok" and not result["rows"]:
        result["caveats"].append(f"No signal rows for symbol '{sym}' and strategy '{strategy}'.")
    return result


def get_symbol_summary(symbol: str, url: str = DEFAULT_URL) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not _SYMBOL_RE.fullmatch(sym):
        return _error(f"invalid_symbol: {symbol!r}")
    latest = market.get_latest_ohlcv(sym, url=url)
    features = get_latest_features(sym, url=url)
    signal = get_latest_signal(sym, url=url)
    tool_calls = [
        {"tool": "get_latest_ohlcv", "args": {"symbol": sym},
         "status": latest.get("status"), "row_count": latest.get("row_count", 0)},
        {"tool": "get_latest_features", "args": {"symbol": sym},
         "status": features.get("status"), "row_count": features.get("row_count", 0)},
        {"tool": "get_latest_signal", "args": {"symbol": sym, "strategy_id": "ma20_ma50_v1"},
         "status": signal.get("status"), "row_count": signal.get("row_count", 0)},
    ]
    data = {
        "symbol": sym,
        "latest": latest.get("rows", [None])[0] if latest.get("rows") else None,
        "features": features.get("data") or None,
        "signal": signal.get("data") or None,
    }
    caveats = list(latest.get("caveats", [])) + list(features.get("caveats", [])) + list(signal.get("caveats", []))
    successful = sum(
        result.get("status") == "ok" and bool(result.get("rows"))
        for result in (latest, features, signal)
    )
    status = "ok" if successful == 3 else ("partial" if successful else "error")
    return {
        "status": status,
        "rows": [data] if successful else [],
        "data": data,
        "row_count": 1 if successful else 0,
        "source": "questdb",
        "sql": [latest.get("sql", ""), features.get("sql", ""), signal.get("sql", "")],
        "tool_calls": tool_calls,
        "caveats": caveats,
    }
