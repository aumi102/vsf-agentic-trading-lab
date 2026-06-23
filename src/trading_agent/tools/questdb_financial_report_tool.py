"""Read-only QuestDB tools for financial report tables."""
from __future__ import annotations

import re
from typing import Any

from trading_agent.tools import questdb_market_data_tool as market

DEFAULT_URL = market.DEFAULT_URL
SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,12}$")
STATEMENT_TABLES = {
    "balance_sheet": "fa_balance_sheet",
    "BALANCE_SHEET": "fa_balance_sheet",
    "income_statement": "fa_income_statement",
    "INCOME_STATEMENT": "fa_income_statement",
    "cash_flow": "fa_cash_flow",
    "CASH_FLOW": "fa_cash_flow",
    "notes": "fa_notes",
    "NOTE": "fa_notes",
}


def _envelope(status: str, rows: list[dict[str, Any]], sql: Any, caveats: list[str]) -> dict[str, Any]:
    return {"status": status, "rows": rows, "data": rows, "row_count": len(rows), "source": "questdb", "sql": sql, "tool_calls": [], "caveats": caveats}


def _validate_symbol(symbol: str) -> str | None:
    sym = (symbol or "").strip().upper()
    return sym if SYMBOL_RE.fullmatch(sym) else None


def _table_exists(table: str, url: str) -> bool:
    res = market.query_questdb("SHOW TABLES", url=url)
    return res.get("status") == "ok" and table in {str(row.get("table_name")) for row in res.get("rows", [])}


def _normalize_statement(statement_type: str | None) -> tuple[str | None, str | None]:
    if not statement_type:
        return None, None
    key = statement_type.strip()
    table = STATEMENT_TABLES.get(key) or STATEMENT_TABLES.get(key.lower()) or STATEMENT_TABLES.get(key.upper())
    return (key.upper(), table) if table else (None, None)


def get_latest_complete_fa_run_id(url: str = DEFAULT_URL) -> str | None:
    """Return the newest complete FA ingest run_id, if run tracking is available."""
    if not _table_exists("fa_ingest_runs", url):
        return None
    sql = "SELECT run_id FROM fa_ingest_runs WHERE status = 'complete' ORDER BY created_at DESC LIMIT 1"
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok" or not res.get("rows"):
        return None
    run_id = str(res["rows"][0].get("run_id") or "").strip()
    return run_id or None


def _run_scope(url: str) -> tuple[str, list[str], str | None]:
    run_id = get_latest_complete_fa_run_id(url)
    if run_id:
        return f" AND run_id = '{run_id}'", [f"using_latest_complete_fa_run_id={run_id}"], run_id
    return "", ["fa_ingest_runs unavailable or has no complete run; query may include duplicate append rows"], None


def get_latest_financial_report(symbol: str, statement_type: str | None = None, url: str = DEFAULT_URL) -> dict[str, Any]:
    sym = _validate_symbol(symbol)
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"])
    targets: list[tuple[str, str]] = []
    if statement_type:
        section, table = _normalize_statement(statement_type)
        if not section or not table:
            return _envelope("error", [], "", [f"invalid_statement_type: {statement_type!r}"])
        targets.append((section, table))
    else:
        targets = [("BALANCE_SHEET", "fa_balance_sheet"), ("INCOME_STATEMENT", "fa_income_statement"), ("CASH_FLOW", "fa_cash_flow"), ("NOTE", "fa_notes")]
    rows: list[dict[str, Any]] = []
    sqls: list[str] = []
    run_filter, caveats, run_id = _run_scope(url)
    for section, table in targets:
        if not _table_exists(table, url):
            caveats.append(f"{table} is not present; financial report data not ingested for this symbol")
            continue
        sql = (
            f"SELECT public_date, security_id, symbol, statement_type, period_type, fiscal_year, fiscal_quarter, "
            f"period_end_date, metric_code, metric_name, metric_value, metric_value_raw, currency, unit, source, "
            f"run_id, raw_payload_ref, quality_status FROM {table} WHERE symbol = '{sym}' "
            f"{run_filter} AND public_date = (SELECT max(public_date) FROM {table} WHERE symbol = '{sym}' {run_filter}) "
            f"ORDER BY metric_code LIMIT 100"
        )
        sqls.append(sql)
        res = market.query_questdb(sql, url=url)
        if res.get("status") == "ok":
            rows.extend(res.get("rows", []))
        else:
            caveats.extend(res.get("caveats", []))
    if not rows:
        caveats.append("financial report data not ingested for this symbol")
        return _envelope("unavailable", [], sqls, caveats)
    out = _envelope("ok", rows, sqls, caveats)
    out["run_id"] = run_id
    out["tool_calls"] = [{"tool": "get_latest_financial_report", "args": {"symbol": sym, "statement_type": statement_type, "run_id": run_id}, "status": "ok", "row_count": len(rows)}]
    return out


def get_financial_metrics(symbol: str, statement_type: str, metric_codes: list[str] | None = None, limit: int = 50, url: str = DEFAULT_URL) -> dict[str, Any]:
    sym = _validate_symbol(symbol)
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"])
    section, table = _normalize_statement(statement_type)
    if not section or not table:
        return _envelope("error", [], "", [f"invalid_statement_type: {statement_type!r}"])
    if not _table_exists(table, url):
        return _envelope("unavailable", [], "", ["financial report data not ingested for this symbol"])
    limit = max(1, min(int(limit), 500))
    run_filter, caveats, run_id = _run_scope(url)
    code_filter = ""
    if metric_codes:
        safe_codes = [c.strip() for c in metric_codes if re.fullmatch(r"[A-Za-z0-9_]{1,64}", c.strip())]
        if safe_codes:
            code_filter = " AND metric_code IN (" + ", ".join(f"'{c}'" for c in safe_codes) + ")"
    sql = f"SELECT * FROM {table} WHERE symbol = '{sym}'{run_filter}{code_filter} ORDER BY public_date DESC, metric_code LIMIT {limit}"
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok" or not res.get("rows"):
        return _envelope("unavailable", [], sql, ["financial report data not ingested for this symbol"] + res.get("caveats", []))
    out = _envelope("ok", res["rows"], sql, caveats + res.get("caveats", []))
    out["run_id"] = run_id
    out["tool_calls"] = [{"tool": "get_financial_metrics", "args": {"symbol": sym, "statement_type": statement_type, "run_id": run_id}, "status": "ok", "row_count": len(res["rows"])}]
    return out


def get_financial_report_summary(symbol: str, url: str = DEFAULT_URL) -> dict[str, Any]:
    sym = _validate_symbol(symbol)
    if not sym:
        return _envelope("error", [], "", [f"invalid_symbol: {symbol!r}"])
    statements = ["BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW", "NOTE"]
    rows: list[dict[str, Any]] = []
    caveats: list[str] = []
    calls: list[dict[str, Any]] = []
    sqls: list[Any] = []
    for st in statements:
        res = get_latest_financial_report(sym, st, url=url)
        sqls.append(res.get("sql"))
        caveats.extend(res.get("caveats", []))
        calls.append({"tool": "get_latest_financial_report", "args": {"symbol": sym, "statement_type": st}, "status": res.get("status"), "row_count": res.get("row_count", 0)})
        rows.extend(res.get("rows", [])[:10])
    caveats = list(dict.fromkeys(caveats))
    if not rows:
        return {"status": "unavailable", "rows": [], "data": [], "row_count": 0, "source": "questdb", "sql": sqls, "tool_calls": calls, "caveats": ["financial report data not ingested for this symbol"] + caveats}
    return {"status": "ok", "rows": rows, "data": rows, "row_count": len(rows), "source": "questdb", "sql": sqls, "tool_calls": calls, "caveats": caveats}
