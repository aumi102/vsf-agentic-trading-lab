"""Next-action recommender for the mentor demo.

Given the current persisted QuestDB state (plus optional benchmark/readiness
hints), return a prioritized list of "what to do next" items. Each item states:

  * the current status of an area;
  * the next recommended action;
  * why it matters;
  * the exact command or UI path to run it.

This is intentionally *fast and read-only*: it runs a handful of focused SELECTs
against QuestDB rather than the full validation-gate suite (which shells out to
docker build + readiness). The heavier gates remain available via
``/api/demo/validation``.
"""
from __future__ import annotations

from typing import Any

from trading_agent.tools import questdb_market_data_tool as market

DEFAULT_URL = market.DEFAULT_URL
DEMO_SYMBOLS = ("FPT", "VNM", "HPG")
FA_FACT_TABLES = ("fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes")
FA_MAPPING_COVERAGE_TARGET = 95.0


def _scalar(sql: str, url: str, default: Any = 0) -> Any:
    res = market.query_questdb(sql, url=url)
    if res.get("status") != "ok" or not res.get("rows"):
        return default
    row = res["rows"][0]
    return next(iter(row.values()), default)


def _existing_tables(url: str) -> set[str]:
    res = market.query_questdb("SHOW TABLES", url=url)
    if res.get("status") != "ok":
        return set()
    return {str(row.get("table_name")) for row in res.get("rows", [])}


def adjusted_ohlc_state(url: str = DEFAULT_URL) -> dict[str, Any]:
    total = int(_scalar("SELECT count() FROM daily_prices", url, 0))
    warn = int(_scalar("SELECT count() FROM daily_prices WHERE adjustment_status = 'adjusted_price_missing_warn'", url, 0))
    equal = int(_scalar("SELECT count() FROM daily_prices WHERE adjusted_close = close", url, 0))
    ratio = (equal / total) if total else None
    unverified = bool(warn) or ratio == 1.0
    return {
        "total_rows": total,
        "adjusted_price_missing_warn_rows": warn,
        "raw_equivalent_ratio": ratio,
        "status": "WARN" if unverified else "PASS",
    }


def fa_mapping_state(url: str = DEFAULT_URL) -> dict[str, Any]:
    tables = _existing_tables(url)
    if "fa_metric_mapping" not in tables:
        return {"status": "WARN", "min_consensus_coverage_pct": 0.0, "mapping_table_exists": False}
    coverages: list[float] = []
    per_table: dict[str, float] = {}
    for table in FA_FACT_TABLES:
        if table not in tables:
            continue
        total_codes = int(_scalar(f"SELECT count_distinct(metric_code) FROM {table}", url, 0))
        mapped = int(
            _scalar(
                "SELECT count_distinct(f.metric_code) "
                f"FROM {table} f JOIN fa_metric_mapping m "
                "ON f.metric_code = m.metric_code AND f.statement_type = m.statement_type "
                "WHERE m.quality_status = 'source_backed_consensus'",
                url,
                0,
            )
        )
        pct = (mapped / total_codes * 100.0) if total_codes else 0.0
        per_table[table] = round(pct, 2)
        coverages.append(pct)
    min_cov = min(coverages) if coverages else 0.0
    return {
        "status": "PASS" if min_cov >= FA_MAPPING_COVERAGE_TARGET else "WARN",
        "min_consensus_coverage_pct": round(min_cov, 2),
        "per_table_coverage_pct": per_table,
        "mapping_table_exists": True,
    }


def event_news_state(url: str = DEFAULT_URL) -> dict[str, Any]:
    tables = _existing_tables(url)
    if "event_news_items" not in tables:
        return {"status": "WARN", "covered_demo_symbols": [], "missing_demo_symbols": list(DEMO_SYMBOLS)}
    quoted = ",".join(f"'{s}'" for s in DEMO_SYMBOLS)
    res = market.query_questdb(
        f"SELECT symbol, count() c FROM event_news_items WHERE symbol IN ({quoted}) GROUP BY symbol",
        url=url,
    )
    covered = sorted({str(row.get("symbol")) for row in res.get("rows", [])}) if res.get("status") == "ok" else []
    missing = [s for s in DEMO_SYMBOLS if s not in covered]
    return {
        "status": "PASS" if not missing else "WARN",
        "covered_demo_symbols": covered,
        "missing_demo_symbols": missing,
    }


def backtest_slippage_state(url: str = DEFAULT_URL) -> dict[str, Any]:
    tables = _existing_tables(url)
    if "backtest_runs" not in tables:
        return {"status": "WARN", "has_zero_slippage": False, "distinct_slippage_bps": []}
    res = market.query_questdb(
        "SELECT DISTINCT slippage_bps FROM backtest_runs ORDER BY slippage_bps", url=url
    )
    values = [float(row.get("slippage_bps") or 0) for row in res.get("rows", [])] if res.get("status") == "ok" else []
    return {
        "status": "WARN" if (0.0 in values) else "PASS",
        "has_zero_slippage": 0.0 in values,
        "distinct_slippage_bps": values,
    }


def compute_next_actions(
    url: str = DEFAULT_URL,
    *,
    query_mode_recommendation: str | None = None,
) -> dict[str, Any]:
    """Return {current_status, states, next_actions} for the demo."""
    adjusted = adjusted_ohlc_state(url)
    fa = fa_mapping_state(url)
    events = event_news_state(url)
    slippage = backtest_slippage_state(url)

    actions: list[dict[str, Any]] = []

    if adjusted["status"] == "WARN":
        actions.append({
            "priority": 1,
            "area": "adjusted_ohlc",
            "status": adjusted["status"],
            "title": "Establish corporate-action / adjusted-price evidence",
            "why": "Adjusted OHLC currently looks raw-equivalent/unverified, so all backtests carry a research-only caveat.",
            "command": "python scripts\\run_adjusted_price_evidence_pipeline.py",
            "ui_path": "/api/demo/validation -> adjusted_ohlc_gate",
        })

    if fa["status"] == "WARN":
        actions.append({
            "priority": 2,
            "area": "fa_mapping",
            "status": fa["status"],
            "title": "Raise FA metric-mapping consensus coverage to >= 95%",
            "why": f"Minimum source-backed consensus coverage is {fa.get('min_consensus_coverage_pct')}%; metric names are enriched only at read time.",
            "command": "python scripts\\resolve_vietcap_iq_fa_metric_mapping.py && python scripts\\load_vietcap_fa_metric_mapping_to_questdb.py",
            "ui_path": "/api/demo/fa/FPT -> caveats",
        })

    if events["status"] == "WARN":
        missing = ", ".join(events.get("missing_demo_symbols") or []) or "demo symbols"
        actions.append({
            "priority": 3,
            "area": "event_news",
            "status": events["status"],
            "title": "Expand official-disclosure event/news coverage",
            "why": f"Event/news coverage is narrow (missing: {missing}); VNM/HPG must return unavailable, never an OHLCV proxy.",
            "command": "python scripts\\probe_event_news_sources.py && python scripts\\ingest_event_news_to_questdb.py",
            "ui_path": "/api/demo/events/VNM (guardrail demo)",
        })

    if slippage["status"] == "WARN":
        actions.append({
            "priority": 4,
            "area": "slippage_model",
            "status": slippage["status"],
            "title": "Document / extend the slippage model beyond simple bps",
            "why": "Some persisted runs use slippage_bps=0 and the model is a simple bps haircut, not a market-impact model.",
            "command": "python scripts\\run_backtrader_questdb_persist.py --symbol FPT --start-date 2020-01-01 --end-date 2025-12-31 --slippage-scenarios-bps 0,5,10,15",
            "ui_path": "/api/demo/backtest/FPT/slippage",
        })

    if query_mode_recommendation == "pgwire":
        actions.append({
            "priority": 5,
            "area": "query_path",
            "status": "OPTIMIZE",
            "title": "Switch selected read-only APIs to the PGWire query path",
            "why": "The benchmark found PGWire faster/stabler than REST for repeated read queries.",
            "command": "set QUESTDB_QUERY_MODE=pgwire",
            "ui_path": "/api/demo/benchmark/questdb",
        })

    if not actions:
        actions.append({
            "priority": 0,
            "area": "demo",
            "status": "PASS",
            "title": "Demo state is healthy; proceed with the FastAPI console walkthrough",
            "why": "No WARN states detected in the fast read-only probes.",
            "command": "uv run python scripts\\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010",
            "ui_path": "/demo",
        })

    actions.sort(key=lambda item: item["priority"])
    warn_count = sum(1 for state in (adjusted, fa, events, slippage) if state["status"] == "WARN")
    current_status = "PASS" if warn_count == 0 else "WARN"
    return {
        "current_status": current_status,
        "warn_areas": warn_count,
        "states": {
            "adjusted_ohlc": adjusted,
            "fa_mapping": fa,
            "event_news": events,
            "backtest_slippage": slippage,
        },
        "next_actions": actions,
    }
