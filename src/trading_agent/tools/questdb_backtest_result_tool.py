"""Read-only QuestDB tools for persisted Backtrader result tables.

These functions only look up already persisted results. They never run
Backtrader and never mutate QuestDB.
"""
from __future__ import annotations

import json
import re
from typing import Any

from trading_agent.tools import questdb_market_data_tool as market

DEFAULT_URL = market.DEFAULT_URL
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
STRATEGY_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
SCENARIO_RE = re.compile(r"^[A-Za-z0-9_]{1,128}$")
MISSING_INSTRUCTION = "Run scripts/run_backtrader_questdb_persist.py first for this symbol/strategy."


def _envelope(status: str, rows: list[dict[str, Any]], sql: Any, caveats: list[str], tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "rows": rows,
        "data": rows,
        "row_count": len(rows),
        "source": "questdb",
        "sql": sql,
        "tool_calls": [{"tool": tool_name, "args": args, "status": status, "row_count": len(rows)}],
        "caveats": list(dict.fromkeys(caveats)),
    }


def _validate_symbol(symbol: str) -> str | None:
    sym = (symbol or "").strip().upper()
    return sym if SYMBOL_RE.fullmatch(sym) else None


def _validate_strategy_id(strategy_id: str | None) -> str | None:
    if strategy_id is None or not str(strategy_id).strip():
        return None
    sid = str(strategy_id).strip()
    return sid if STRATEGY_RE.fullmatch(sid) else ""


def _validate_scenario_label(scenario_label: str | None) -> str | None:
    if scenario_label is None or not str(scenario_label).strip():
        return None
    label = str(scenario_label).strip()
    return label if SCENARIO_RE.fullmatch(label) else ""


def _table_exists(table: str, url: str) -> bool:
    res = market.query_questdb("SHOW TABLES", url=url)
    return res.get("status") == "ok" and table in {str(row.get("table_name")) for row in res.get("rows", [])}


def _decode_caveats(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [text]


def _row_caveats(rows: list[dict[str, Any]]) -> list[str]:
    caveats: list[str] = []
    for row in rows:
        caveats.extend(_decode_caveats(row.get("caveats")))
        if row.get("adjusted_price_status") == "source_adjustment_unverified":
            caveats.append("adjusted OHLC source remains unverified; backtest is research-only")
        if row.get("price_band_status") == "exchange_unknown_price_band_guard_not_fully_verified":
            caveats.append("exchange unknown; price-band guard is not fully verified")
        elif row.get("price_band_status") == "slippage_bps_exceeds_exchange_price_band":
            caveats.append("slippage_bps exceeds configured exchange price band")
        if row.get("slippage_bps") in (0, 0.0, "0", "0.0"):
            caveats.append("slippage_bps is 0; slippage is not modeled")
    return list(dict.fromkeys(caveats))


def _missing(tool_name: str, args: dict[str, Any], sql: Any, caveats: list[str] | None = None) -> dict[str, Any]:
    return _envelope("unavailable", [], sql, (caveats or []) + [MISSING_INSTRUCTION], tool_name, args)


def _metric_join_sql(
    symbol: str,
    strategy_id: str | None = None,
    *,
    slippage_bps: float | None = 0.0,
    scenario_label: str | None = None,
) -> str:
    strategy_filter = f" AND r.strategy_id = '{strategy_id}'" if strategy_id else ""
    slippage_filter = "" if slippage_bps is None else f" AND r.slippage_bps = {float(slippage_bps)}"
    scenario_filter = f" AND r.scenario_label = '{scenario_label}'" if scenario_label else ""
    return (
        "SELECT r.created_at, r.run_id, r.symbol, r.strategy_id, r.strategy_name, "
        "r.start_date, r.end_date, r.data_source, r.source_table, r.code_commit, "
        "r.start_cash, r.commission, r.slippage_bps, r.scenario_label, r.price_band_status, r.adjusted_price_status, r.status AS run_status, "
        "r.caveats, m.start_value, m.final_value, m.total_return_pct, m.annualized_return_pct, "
        "m.max_drawdown_pct, m.sharpe_ratio, m.closed_trades, m.win_rate_pct, m.slippage_bps AS metric_slippage_bps, "
        "m.scenario_label AS metric_scenario_label, m.quality_status "
        "FROM backtest_runs r JOIN backtest_metrics m ON r.run_id = m.run_id "
        f"WHERE r.symbol = '{symbol}'{strategy_filter}{slippage_filter}{scenario_filter} "
        "ORDER BY r.created_at DESC"
    )


def _latest_per_strategy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        strategy = str(row.get("strategy_id") or "")
        if strategy in seen:
            continue
        seen.add(strategy)
        out.append(row)
    return out


def get_latest_backtest_metrics(
    symbol: str,
    strategy_id: str | None = None,
    slippage_bps: float | None = 0.0,
    scenario_label: str | None = None,
    url: str = DEFAULT_URL,
) -> dict[str, Any]:
    """Return latest persisted backtest metrics for a symbol and optional strategy."""
    sym = _validate_symbol(symbol)
    sid = _validate_strategy_id(strategy_id)
    label = _validate_scenario_label(scenario_label)
    args = {"symbol": symbol, "strategy_id": strategy_id, "slippage_bps": slippage_bps, "scenario_label": scenario_label}
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"], "get_latest_backtest_metrics", args)
    if sid == "":
        return _envelope("error", [], "", [f"invalid_strategy_id: {strategy_id!r}"], "get_latest_backtest_metrics", args)
    if label == "":
        return _envelope("error", [], "", [f"invalid_scenario_label: {scenario_label!r}"], "get_latest_backtest_metrics", args)
    for table in ("backtest_runs", "backtest_metrics"):
        if not _table_exists(table, url):
            return _missing("get_latest_backtest_metrics", args, "", [f"{table} is missing"])
    sql = _metric_join_sql(sym, sid, slippage_bps=slippage_bps, scenario_label=label)
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok":
        return _envelope("error", [], sql, res.get("caveats", []), "get_latest_backtest_metrics", args)
    rows = res.get("rows", [])
    latest = _latest_per_strategy(rows) if sid is None else rows[:1]
    if not latest:
        return _missing("get_latest_backtest_metrics", args, sql)
    caveats = _row_caveats(latest)
    return _envelope("ok", latest, sql, caveats, "get_latest_backtest_metrics", {"symbol": sym, "strategy_id": sid, "slippage_bps": slippage_bps, "scenario_label": label})


def get_backtest_strategy_comparison(symbol: str, slippage_bps: float | None = 0.0, scenario_label: str | None = None, url: str = DEFAULT_URL) -> dict[str, Any]:
    """Return latest persisted metric row for each strategy for a symbol."""
    sym = _validate_symbol(symbol)
    label = _validate_scenario_label(scenario_label)
    args = {"symbol": symbol, "slippage_bps": slippage_bps, "scenario_label": scenario_label}
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"], "get_backtest_strategy_comparison", args)
    if label == "":
        return _envelope("error", [], "", [f"invalid_scenario_label: {scenario_label!r}"], "get_backtest_strategy_comparison", args)
    for table in ("backtest_runs", "backtest_metrics"):
        if not _table_exists(table, url):
            return _missing("get_backtest_strategy_comparison", args, "", [f"{table} is missing"])
    sql = _metric_join_sql(sym, slippage_bps=slippage_bps, scenario_label=label)
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok":
        return _envelope("error", [], sql, res.get("caveats", []), "get_backtest_strategy_comparison", args)
    rows = _latest_per_strategy(res.get("rows", []))
    rows = sorted(rows, key=lambda row: str(row.get("strategy_id") or ""))
    if not rows:
        return _missing("get_backtest_strategy_comparison", args, sql)
    caveats = _row_caveats(rows)
    return _envelope("ok", rows, sql, caveats, "get_backtest_strategy_comparison", {"symbol": sym, "slippage_bps": slippage_bps, "scenario_label": label})


def get_backtest_slippage_scenarios(symbol: str, strategy_id: str | None = None, url: str = DEFAULT_URL) -> dict[str, Any]:
    """Return latest persisted metrics across slippage scenarios for a symbol."""
    sym = _validate_symbol(symbol)
    sid = _validate_strategy_id(strategy_id)
    args = {"symbol": symbol, "strategy_id": strategy_id}
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"], "get_backtest_slippage_scenarios", args)
    if sid == "":
        return _envelope("error", [], "", [f"invalid_strategy_id: {strategy_id!r}"], "get_backtest_slippage_scenarios", args)
    for table in ("backtest_runs", "backtest_metrics"):
        if not _table_exists(table, url):
            return _missing("get_backtest_slippage_scenarios", args, "", [f"{table} is missing"])
    sql = _metric_join_sql(sym, sid, slippage_bps=None)
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok":
        return _envelope("error", [], sql, res.get("caveats", []), "get_backtest_slippage_scenarios", args)
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for row in res.get("rows", []):
        key = (str(row.get("strategy_id") or ""), str(row.get("scenario_label") or row.get("slippage_bps") or ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows = sorted(rows, key=lambda row: (str(row.get("strategy_id") or ""), float(row.get("slippage_bps") or 0)))
    if not rows:
        return _missing("get_backtest_slippage_scenarios", args, sql)
    caveats = _row_caveats(rows)
    return _envelope("ok", rows, sql, caveats, "get_backtest_slippage_scenarios", {"symbol": sym, "strategy_id": sid})


def get_backtest_equity_curve(symbol: str, strategy_id: str, limit: int = 5000, slippage_bps: float | None = 0.0, scenario_label: str | None = None, url: str = DEFAULT_URL) -> dict[str, Any]:
    """Return persisted equity curve rows for the latest symbol/strategy run."""
    sym = _validate_symbol(symbol)
    sid = _validate_strategy_id(strategy_id)
    label = _validate_scenario_label(scenario_label)
    args = {"symbol": symbol, "strategy_id": strategy_id, "limit": limit, "slippage_bps": slippage_bps, "scenario_label": scenario_label}
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"], "get_backtest_equity_curve", args)
    if sid in (None, ""):
        return _envelope("error", [], "", [f"invalid_strategy_id: {strategy_id!r}"], "get_backtest_equity_curve", args)
    if label == "":
        return _envelope("error", [], "", [f"invalid_scenario_label: {scenario_label!r}"], "get_backtest_equity_curve", args)
    for table in ("backtest_runs", "backtest_equity_curve"):
        if not _table_exists(table, url):
            return _missing("get_backtest_equity_curve", args, "", [f"{table} is missing"])
    safe_limit = max(1, min(int(limit), 5000))
    slippage_filter = "" if slippage_bps is None else f" AND slippage_bps = {float(slippage_bps)}"
    scenario_filter = f" AND scenario_label = '{label}'" if label else ""
    run_sql = (
        "SELECT created_at, run_id, symbol, strategy_id, strategy_name, start_date, end_date, data_source, "
        "source_table, code_commit, start_cash, commission, slippage_bps, scenario_label, price_band_status, adjusted_price_status, status AS run_status, caveats "
        "FROM backtest_runs "
        f"WHERE symbol = '{sym}' AND strategy_id = '{sid}'{slippage_filter}{scenario_filter} "
        "ORDER BY created_at DESC LIMIT 1"
    )
    run_res = market.query_questdb(run_sql, url=url)
    if run_res.get("status") != "ok":
        return _envelope("error", [], run_sql, run_res.get("caveats", []), "get_backtest_equity_curve", args)
    run_rows = run_res.get("rows", [])
    if not run_rows:
        return _missing("get_backtest_equity_curve", args, run_sql)
    run = run_rows[0]
    run_id = str(run.get("run_id") or "")
    equity_sql = (
        "SELECT trade_date, run_id, symbol, strategy_id, strategy_name, portfolio_value, cash "
        "FROM backtest_equity_curve "
        f"WHERE run_id = '{run_id}' ORDER BY trade_date ASC LIMIT {safe_limit}"
    )
    equity_res = market.query_questdb(equity_sql, url=url)
    if equity_res.get("status") != "ok":
        return _envelope("error", [], [run_sql, equity_sql], equity_res.get("caveats", []), "get_backtest_equity_curve", args)
    rows = equity_res.get("rows", [])
    if not rows:
        return _missing("get_backtest_equity_curve", args, [run_sql, equity_sql])
    enriched = [{**row, **{f"run_{key}": value for key, value in run.items() if key not in row}} for row in rows]
    caveats = _row_caveats([run])
    if len(rows) == safe_limit:
        caveats.append(f"equity curve limited to {safe_limit} rows")
    return _envelope("ok", enriched, [run_sql, equity_sql], caveats, "get_backtest_equity_curve", {"symbol": sym, "strategy_id": sid, "limit": safe_limit})
