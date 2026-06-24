"""Read-only validation gates for the QuestDB-backed trading-agent stack."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from trading_agent.backtest.slippage_guard import evaluate_price_band_guard, normalize_exchange
from trading_agent.storage import questdb_client as qdb

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL
DEMO_SYMBOLS = ("FPT", "VNM", "HPG")
FA_TABLES = ("fa_balance_sheet", "fa_income_statement", "fa_cash_flow", "fa_notes")
BACKTEST_TABLES = ("backtest_runs", "backtest_metrics", "backtest_equity_curve", "backtest_trades")
EVENT_NEWS_TABLES = ("event_news_raw_payloads", "event_news_items")


@dataclass(frozen=True)
class GateResult:
    gate_name: str
    status: str
    evidence: dict[str, Any]
    caveats: list[str]
    recommended_fix: str
    blocking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gate(
    name: str,
    status: str,
    evidence: dict[str, Any] | None = None,
    caveats: list[str] | None = None,
    recommended_fix: str = "",
    *,
    blocking: bool = False,
) -> GateResult:
    return GateResult(
        gate_name=name,
        status=status,
        evidence=evidence or {},
        caveats=caveats or [],
        recommended_fix=recommended_fix,
        blocking=blocking,
    )


def _safe_gate(name: str, func: Callable[[str], GateResult], url: str) -> GateResult:
    try:
        return func(url)
    except Exception as exc:
        return _gate(
            name,
            "FAIL",
            {"error_type": type(exc).__name__, "error": str(exc)},
            ["gate execution failed"],
            "Inspect QuestDB connectivity and gate implementation.",
            blocking=True,
        )


def _existing_tables(client, base: str) -> set[str]:
    _, rows = qdb.exec_rows(client, base, "SHOW TABLES")
    return {str(row[0]) for row in rows if row}


def _count(client, base: str, table: str) -> int:
    return int(qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0))


def _scalar(client, base: str, sql: str, default: Any = None) -> Any:
    return qdb.exec_scalar(client, base, sql, default)


def _run_command(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def market_table_coverage(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    with qdb.open_client() as client:
        tables = _existing_tables(client, base)
        if "daily_prices" not in tables:
            return _gate("market_table_coverage", "FAIL", {"tables": sorted(tables)}, ["daily_prices missing"], "Restore or load daily_prices.", blocking=True)
        row_count = _count(client, base, "daily_prices")
        symbols = int(_scalar(client, base, "SELECT count_distinct(symbol) FROM daily_prices", 0))
        latest = _scalar(client, base, "SELECT max(trade_date) FROM daily_prices", "")
    status = "PASS" if row_count > 0 and symbols > 0 and latest else "FAIL"
    return _gate(
        "market_table_coverage",
        status,
        {"daily_prices_rows": row_count, "symbols": symbols, "latest_trade_date": str(latest)[:10]},
        [] if status == "PASS" else ["market data coverage is empty or missing latest date"],
        "Run approved OHLCV ingestion only if market data is genuinely missing.",
        blocking=status == "FAIL",
    )


def feature_signal_parity(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    with qdb.open_client() as client:
        tables = _existing_tables(client, base)
        missing = [t for t in ("daily_prices", "feature_snapshots", "signals") if t not in tables]
        if missing:
            return _gate("feature_signal_parity", "FAIL", {"missing": missing}, ["derived market tables missing"], "Run derived table builder.", blocking=True)
        daily_rows = _count(client, base, "daily_prices")
        feature_rows = _count(client, base, "feature_snapshots")
        signal_rows = _count(client, base, "signals")
        daily_latest = _scalar(client, base, "SELECT max(trade_date) FROM daily_prices", "")
        feature_latest = _scalar(client, base, "SELECT max(trade_date) FROM feature_snapshots", "")
        signal_latest = _scalar(client, base, "SELECT max(trade_date) FROM signals", "")
    row_tolerance = max(10, int(daily_rows * 0.001))
    rows_ok = abs(daily_rows - feature_rows) <= row_tolerance and abs(feature_rows - signal_rows) <= row_tolerance
    dates_ok = str(daily_latest)[:10] == str(feature_latest)[:10] == str(signal_latest)[:10]
    status = "PASS" if rows_ok and dates_ok else "WARN"
    return _gate(
        "feature_signal_parity",
        status,
        {
            "daily_prices_rows": daily_rows,
            "feature_snapshots_rows": feature_rows,
            "signals_rows": signal_rows,
            "daily_latest": str(daily_latest)[:10],
            "feature_latest": str(feature_latest)[:10],
            "signal_latest": str(signal_latest)[:10],
            "row_tolerance": row_tolerance,
        },
        [] if status == "PASS" else ["feature/signal row counts or latest dates are not in parity"],
        "Rebuild feature_snapshots and signals from daily_prices.",
    )


def adjusted_ohlc_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    with qdb.open_client() as client:
        columns = set(qdb.column_names(client, base, "daily_prices"))
        adjusted_cols = {"adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close"}
        has_adjusted = sorted(adjusted_cols & columns)
        evidence: dict[str, Any] = {
            "adjusted_columns_present": has_adjusted,
            "source_verification_status": "not_checked",
        }
        caveats: list[str] = []
        if "adjusted_close" in columns:
            equal_rows = int(_scalar(client, base, "SELECT count() FROM daily_prices WHERE adjusted_close = close", 0))
            total_rows = _count(client, base, "daily_prices")
            warn_rows = int(_scalar(client, base, "SELECT count() FROM daily_prices WHERE adjustment_status = 'adjusted_price_missing_warn'", 0))
            non_1_factor_rows = int(_scalar(client, base, "SELECT count() FROM daily_prices WHERE close != 0 AND adjusted_close IS NOT NULL AND abs(adjusted_close / close - 1.0) > 0.000001", 0))
            evidence.update({
                "adjusted_close_equals_close_rows": equal_rows,
                "total_rows": total_rows,
                "raw_equivalent_ratio": (equal_rows / total_rows) if total_rows else None,
                "adjusted_price_missing_warn_rows": warn_rows,
                "non_1_factor_rows": non_1_factor_rows,
            })
            if equal_rows == total_rows or warn_rows > 0:
                caveats.append("adjusted close appears unverified or equal to raw for current rows")
        if adjusted_cols.issubset(columns):
            try:
                _, rows = qdb.exec_rows(
                    client,
                    base,
                    "SELECT corr(high, adjusted_high), corr(close, adjusted_close), "
                    "max(abs(adjusted_open - open * (adjusted_close / close))), "
                    "max(abs(adjusted_high - high * (adjusted_close / close))), "
                    "max(abs(adjusted_low - low * (adjusted_close / close))) "
                    "FROM daily_prices "
                    "WHERE high > 0 AND close > 0 AND open > 0 AND low > 0 "
                    "AND adjusted_high > 0 AND adjusted_close > 0 AND adjusted_open > 0 AND adjusted_low > 0",
                )
                if rows:
                    evidence["corr_high_adjusted_high"] = rows[0][0]
                    evidence["corr_close_adjusted_close"] = rows[0][1]
                    max_errors = [float(value or 0.0) for value in rows[0][2:5]]
                    evidence["max_factor_application_error"] = max(max_errors) if max_errors else None
                    evidence["internal_consistency_status"] = "pass" if not max_errors or max(max_errors) <= 1e-6 else "fail"
                    if evidence["internal_consistency_status"] == "fail":
                        caveats.append("adjusted OHLC columns are inconsistent with adjusted_close / close factor math")
            except Exception as exc:
                evidence["correlation_check_error"] = f"{type(exc).__name__}: {exc}"
                caveats.append("QuestDB correlation check unavailable; inspected adjusted columns and status instead")
        if evidence.get("adjusted_price_missing_warn_rows") or evidence.get("raw_equivalent_ratio") == 1.0:
            evidence["source_verification_status"] = "source_adjustment_unverified_raw_equivalent"
        elif evidence.get("non_1_factor_rows", 0):
            evidence["source_verification_status"] = "internal_consistency_only_source_unverified"
            caveats.append("non-1 adjusted factors exist but external corporate-action source verification is not established")
    if not {"adjusted_close"}.issubset(columns):
        return _gate("adjusted_ohlc_gate", "WARN", evidence, ["adjusted_close column missing"], "Derive adjusted OHLC from verified corporate-action factors.")
    if evidence.get("internal_consistency_status") == "fail":
        return _gate("adjusted_ohlc_gate", "FAIL", evidence, caveats, "Fix adjusted OHLC factor application before using adjusted data.", blocking=True)
    if caveats:
        return _gate("adjusted_ohlc_gate", "WARN", evidence, caveats, "Verify adjusted OHLC against corporate-action/vendor adjustment evidence.")
    return _gate("adjusted_ohlc_gate", "PASS", evidence, [], "Keep monitoring adjusted OHLC quality.")


def exchange_metadata_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    quoted = ",".join(f"'{symbol}'" for symbol in DEMO_SYMBOLS)
    with qdb.open_client() as client:
        if "securities" not in _existing_tables(client, base):
            return _gate("exchange_metadata_gate", "FAIL", {}, ["securities missing"], "Rebuild securities from daily_prices.", blocking=True)
        total = _count(client, base, "securities")
        known = int(_scalar(client, base, "SELECT count() FROM securities WHERE exchange IS NOT NULL AND exchange != 'UNKNOWN' AND exchange != ''", 0))
        _, demo_rows = qdb.exec_rows(client, base, f"SELECT symbol, exchange FROM securities WHERE symbol IN ({quoted}) ORDER BY symbol")
    demo = {str(row[0]): row[1] for row in demo_rows}
    normalized_demo = {symbol: normalize_exchange(demo.get(symbol)) for symbol in DEMO_SYMBOLS}
    price_band_status = {
        symbol: evaluate_price_band_guard(normalized_demo.get(symbol), 0.0).status
        for symbol in DEMO_SYMBOLS
    }
    missing_demo = [symbol for symbol in DEMO_SYMBOLS if normalized_demo.get(symbol) == "UNKNOWN"]
    unsupported_demo = [
        symbol for symbol, guard_status in price_band_status.items()
        if guard_status != "price_band_guard_pass"
    ]
    missing_broader = max(total - known, 0)
    broad_missing_threshold = max(50, int(total * 0.05))
    status = "PASS"
    caveats: list[str] = []
    if missing_demo or unsupported_demo:
        status = "WARN"
        caveats.append(f"demo symbols missing/unsupported exchange: {', '.join(sorted(set(missing_demo + unsupported_demo)))}")
    elif missing_broader > broad_missing_threshold:
        status = "WARN"
        caveats.append(f"broader universe has {missing_broader} missing exchange values")
    return _gate(
        "exchange_metadata_gate",
        status,
        {
            "demo_symbols_checked": list(DEMO_SYMBOLS),
            "demo_symbol_exchanges": normalized_demo,
            "demo_price_band_status": price_band_status,
            "missing_demo_symbols": missing_demo,
            "unsupported_demo_symbols": unsupported_demo,
            "total_securities": total,
            "exchange_non_null_count": known,
            "exchange_coverage_pct": (known / total * 100.0) if total else 0.0,
            "broader_missing_exchange_count": missing_broader,
        },
        caveats,
        "Fill exchange metadata so price-band guard can pass.",
    )


def fa_tables_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    with qdb.open_client() as client:
        tables = _existing_tables(client, base)
        missing = [table for table in FA_TABLES if table not in tables]
        if missing:
            return _gate("fa_tables_gate", "WARN", {"missing": missing}, ["FA tables missing"], "Run FA smoke/run-scoped ingestion.")
        row_counts = {table: _count(client, base, table) for table in FA_TABLES}
        symbols = {table: int(_scalar(client, base, f"SELECT count_distinct(symbol) FROM {table}", 0)) for table in FA_TABLES}
        latest_complete = None
        latest_status = None
        if "fa_ingest_runs" in tables:
            latest_complete = _scalar(client, base, "SELECT run_id FROM fa_ingest_runs WHERE status = 'complete' ORDER BY created_at DESC LIMIT 1", "")
            latest_status = _scalar(client, base, "SELECT status FROM fa_ingest_runs ORDER BY created_at DESC LIMIT 1", "")
    status = "PASS" if all(count > 0 for count in row_counts.values()) and latest_complete else "WARN"
    return _gate(
        "fa_tables_gate",
        status,
        {"row_counts": row_counts, "symbol_counts": symbols, "latest_complete_run_id": latest_complete, "latest_run_status": latest_status},
        [] if status == "PASS" else ["FA table coverage incomplete or no complete FA run found"],
        "Run FA ingestion in run-scoped mode and verify questdb_fa_status.py.",
    )


def fa_mapping_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    breakdown: dict[str, dict[str, int]] = {}
    mapping_coverage: dict[str, dict[str, Any]] = {}
    mapping_table_exists = False
    with qdb.open_client() as client:
        tables = _existing_tables(client, base)
        mapping_table_exists = "fa_metric_mapping" in tables
        mapping_rows = _count(client, base, "fa_metric_mapping") if mapping_table_exists else 0
        mapping_consensus_rows = int(
            _scalar(client, base, "SELECT count() FROM fa_metric_mapping WHERE quality_status = 'source_backed_consensus'", 0)
        ) if mapping_table_exists else 0
        for table in FA_TABLES:
            if table not in tables:
                continue
            _, rows = qdb.exec_rows(client, base, f"SELECT quality_status, count() c FROM {table} GROUP BY quality_status")
            breakdown[table] = {str(row[0]): int(row[1]) for row in rows}
            if mapping_table_exists:
                total_codes = int(_scalar(client, base, f"SELECT count_distinct(metric_code) FROM {table}", 0))
                mapped_codes = int(
                    _scalar(
                        client,
                        base,
                        "SELECT count_distinct(f.metric_code) "
                        f"FROM {table} f JOIN fa_metric_mapping m "
                        "ON f.metric_code = m.metric_code AND f.statement_type = m.statement_type "
                        "WHERE m.quality_status = 'source_backed_consensus'",
                        0,
                    )
                )
                mapping_coverage[table] = {
                    "fact_distinct_metric_codes": total_codes,
                    "mapped_consensus_metric_codes": mapped_codes,
                    "mapped_consensus_code_pct": (mapped_codes / total_codes * 100.0) if total_codes else 0.0,
                }
    unverified = sum(counts.get("metric_mapping_unverified", 0) for counts in breakdown.values())
    coverage_values = [float(row.get("mapped_consensus_code_pct") or 0.0) for row in mapping_coverage.values()]
    min_coverage = min(coverage_values) if coverage_values else 0.0
    status = "PASS" if mapping_table_exists and min_coverage >= 95.0 and not unverified else "WARN"
    caveats: list[str] = []
    if not mapping_table_exists:
        caveats.append("fa_metric_mapping table is unavailable")
    elif min_coverage < 95.0:
        caveats.append("FA metric mapping exists but consensus coverage remains below production threshold")
    if unverified:
        caveats.append("FA fact rows still carry metric_mapping_unverified quality_status; tools enrich names at read time only")
    return _gate(
        "fa_mapping_gate",
        status,
        {
            "quality_status_breakdown": breakdown,
            "metric_mapping_unverified_rows": unverified,
            "fa_metric_mapping_table_exists": mapping_table_exists,
            "fa_metric_mapping_rows": mapping_rows if mapping_table_exists else 0,
            "fa_metric_mapping_consensus_rows": mapping_consensus_rows if mapping_table_exists else 0,
            "mapping_coverage": mapping_coverage,
            "minimum_consensus_code_coverage_pct": min_coverage,
        },
        caveats,
        "Build and verify Vietcap metric-code mapping before claiming semantic FA metric names.",
    )


def backtest_tables_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    with qdb.open_client() as client:
        tables = _existing_tables(client, base)
        missing = [table for table in BACKTEST_TABLES if table not in tables]
        if missing:
            return _gate("backtest_tables_gate", "FAIL", {"missing": missing}, ["backtest result tables missing"], "Run demo-symbol backtest persistence.", blocking=True)
        row_counts = {table: _count(client, base, table) for table in BACKTEST_TABLES}
        symbols = int(_scalar(client, base, "SELECT count_distinct(symbol) FROM backtest_runs", 0))
        strategies = int(_scalar(client, base, "SELECT count_distinct(strategy_id) FROM backtest_runs", 0))
    status = "PASS" if row_counts["backtest_runs"] > 0 and row_counts["backtest_metrics"] > 0 and row_counts["backtest_equity_curve"] > 0 and row_counts["backtest_trades"] > 0 else "WARN"
    return _gate(
        "backtest_tables_gate",
        status,
        {"row_counts": row_counts, "symbols": symbols, "strategies": strategies},
        [] if status == "PASS" else ["backtest result coverage is incomplete"],
        "Run scripts/run_backtrader_questdb_persist.py for the demo symbols.",
    )


def backtest_execution_assumptions_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    with qdb.open_client() as client:
        if "backtest_runs" not in _existing_tables(client, base):
            return _gate("backtest_execution_assumptions_gate", "FAIL", {}, ["backtest_runs missing"], "Run backtest persistence.", blocking=True)
        _, rows = qdb.exec_rows(
            client,
            base,
            "SELECT commission, slippage_bps, price_band_status, count() c FROM backtest_runs "
            "GROUP BY commission, slippage_bps, price_band_status ORDER BY c DESC",
        )
    evidence = {
        "assumption_breakdown": [
            {"commission": row[0], "slippage_bps": row[1], "price_band_status": row[2], "rows": int(row[3])}
            for row in rows
        ]
    }
    statuses = {str(row[2]) for row in rows}
    slippage_values = [float(row[1] or 0) for row in rows]
    caveats: list[str] = []
    status = "PASS"
    if "exchange_unknown_price_band_guard_not_fully_verified" in statuses:
        status = "WARN"
        caveats.append("exchange metadata missing; price-band guard cannot be fully verified")
    if any(value == 0.0 for value in slippage_values):
        status = "WARN" if status == "PASS" else status
        caveats.append("slippage_bps is 0; slippage remains a simple demo assumption")
    if "slippage_bps_exceeds_exchange_price_band" in statuses:
        status = "FAIL"
        caveats.append("slippage exceeds exchange price-band guard")
    return _gate(
        "backtest_execution_assumptions_gate",
        status,
        evidence,
        caveats,
        "Fill exchange metadata and rerun persisted backtests; tune slippage assumptions after mentor approval.",
        blocking=status == "FAIL",
    )


def event_news_gate(url: str = DEFAULT_URL) -> GateResult:
    base = url.rstrip("/")
    evidence: dict[str, Any] = {}
    caveats: list[str] = []
    with qdb.open_client() as client:
        tables = _existing_tables(client, base)
        missing = [table for table in EVENT_NEWS_TABLES if table not in tables]
        evidence["tables_present"] = {table: table in tables for table in EVENT_NEWS_TABLES}
        if missing:
            probe_doc = ROOT / "docs" / "data_sources" / "event_news_source_probe.md"
            evidence["probe_doc_exists"] = probe_doc.exists()
            return _gate(
                "event_news_gate",
                "WARN",
                evidence,
                ["event/news probe exists but QuestDB event_news tables are not ready"] if probe_doc.exists() else ["event/news ingestion remains unsupported"],
                "Run controlled event/news source probe and only ingest if stable records are parsed.",
            )
        row_counts = {table: _count(client, base, table) for table in EVENT_NEWS_TABLES}
        symbol_counts = {table: int(_scalar(client, base, f"SELECT count_distinct(symbol) FROM {table}", 0)) for table in EVENT_NEWS_TABLES}
        quoted = ",".join(f"'{symbol}'" for symbol in DEMO_SYMBOLS)
        _, demo_rows = qdb.exec_rows(
            client,
            base,
            f"SELECT symbol, count() c FROM event_news_items WHERE symbol IN ({quoted}) GROUP BY symbol ORDER BY symbol",
        )
    demo_counts = {str(row[0]): int(row[1]) for row in demo_rows}
    evidence.update({"row_counts": row_counts, "symbol_counts": symbol_counts, "demo_symbol_event_counts": demo_counts})
    if not any(row_counts.values()):
        return _gate("event_news_gate", "WARN", evidence, ["event/news tables exist but contain no rows"], "Ingest a small verified disclosure/event source run.")
    if not any(symbol in demo_counts for symbol in DEMO_SYMBOLS):
        return _gate("event_news_gate", "WARN", evidence, ["event/news rows exist but no demo symbols are covered"], "Ingest demo-symbol event records or keep event/news unsupported.")
    missing_demo = [symbol for symbol in DEMO_SYMBOLS if symbol not in demo_counts]
    if missing_demo:
        caveats.append(f"event/news demo coverage is partial; missing {', '.join(missing_demo)}")

    proc = _run_command([sys.executable, "scripts\\demo_agent_backend_cli.py", "latest news FPT"], timeout=60)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    evidence["agent_latest_news_exit_code"] = proc.returncode
    evidence["agent_latest_news_uses_event_tool"] = "get_symbol_event_news" in output
    evidence["agent_latest_news_uses_ohlcv_proxy"] = "get_latest_ohlcv" in output or "get_symbol_summary" in output
    if evidence["agent_latest_news_uses_ohlcv_proxy"]:
        return _gate(
            "event_news_gate",
            "FAIL",
            evidence,
            ["event/news query used market data proxy"],
            "Fix agent routing so event/news queries use only event/news tools or return unsupported.",
            blocking=True,
        )
    status = "PASS" if evidence["agent_latest_news_uses_event_tool"] else "WARN"
    if status == "WARN":
        caveats.append("event/news data exists but agent route did not use get_symbol_event_news")
    return _gate(
        "event_news_gate",
        status,
        evidence,
        caveats,
        "Expand event/news sources only after source schema and PIT semantics are stable.",
    )


def agent_guardrail_gate(url: str = DEFAULT_URL) -> GateResult:
    proc = _run_command(
        [sys.executable, "scripts\\run_mentor_demo_readiness.py", "--deepagents"],
        timeout=180,
    )
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    final = "UNKNOWN"
    for line in output.splitlines():
        if line.startswith("FINAL_STATUS="):
            final = line.split("=", 1)[1].strip()
    status = "PASS" if proc.returncode == 0 and final == "PASS" else "WARN" if final == "PARTIAL" else "FAIL"
    return _gate(
        "agent_guardrail_gate",
        status,
        {"exit_code": proc.returncode, "final_status": final},
        [] if status == "PASS" else ["agent readiness did not reach PASS"],
        "Inspect run_mentor_demo_readiness.py output and fix routing/credential issues.",
        blocking=status == "FAIL",
    )


def docker_packaging_gate(url: str = DEFAULT_URL) -> GateResult:
    del url
    required = ["Dockerfile", "docker-compose.yml", ".dockerignore"]
    missing = [path for path in required if not (ROOT / path).exists()]
    evidence: dict[str, Any] = {"required_files": {path: (ROOT / path).exists() for path in required}}
    caveats: list[str] = []
    if missing:
        return _gate("docker_packaging_gate", "WARN", evidence, [f"missing docker files: {', '.join(missing)}"], "Add Dockerfile, docker-compose.yml, and .dockerignore.")
    config = _run_command(["docker", "compose", "config"], timeout=120)
    evidence["compose_config_exit_code"] = config.returncode
    if config.returncode != 0:
        return _gate(
            "docker_packaging_gate",
            "WARN",
            {**evidence, "compose_config_error": (config.stderr or config.stdout)[-1000:]},
            ["docker compose config failed"],
            "Start Docker Desktop and inspect docker-compose.yml.",
        )
    if "sk-" in config.stdout:
        return _gate(
            "docker_packaging_gate",
            "FAIL",
            evidence,
            ["docker compose config output contains an OpenAI-style secret"],
            "Remove secret interpolation from compose config; use env_file or runtime secret injection.",
            blocking=True,
        )
    version = _run_command(["docker", "version", "--format", "{{.Server.Version}}"], timeout=60)
    evidence["docker_server_version_exit_code"] = version.returncode
    if version.returncode != 0:
        return _gate(
            "docker_packaging_gate",
            "WARN",
            {**evidence, "docker_version_error": (version.stderr or version.stdout)[-1000:]},
            ["Docker daemon unavailable; packaging files exist but image build was not verified"],
            "Start Docker Desktop and run docker build -t vsf-agent-backend:demo .",
        )
    evidence["docker_server_version"] = version.stdout.strip()
    build = _run_command(["docker", "build", "-t", "vsf-agent-backend:demo", "."], timeout=600)
    evidence["docker_build_exit_code"] = build.returncode
    if build.returncode != 0:
        return _gate(
            "docker_packaging_gate",
            "WARN",
            {**evidence, "docker_build_error": (build.stderr or build.stdout)[-2000:]},
            ["Docker build failed in current environment"],
            "Inspect Docker build output and dependency installation.",
        )
    return _gate("docker_packaging_gate", "PASS", evidence, caveats, "Keep image build in CI or demo preflight.")


GATES: tuple[tuple[str, Callable[[str], GateResult]], ...] = (
    ("market_table_coverage", market_table_coverage),
    ("feature_signal_parity", feature_signal_parity),
    ("adjusted_ohlc_gate", adjusted_ohlc_gate),
    ("exchange_metadata_gate", exchange_metadata_gate),
    ("fa_tables_gate", fa_tables_gate),
    ("fa_mapping_gate", fa_mapping_gate),
    ("backtest_tables_gate", backtest_tables_gate),
    ("backtest_execution_assumptions_gate", backtest_execution_assumptions_gate),
    ("event_news_gate", event_news_gate),
    ("agent_guardrail_gate", agent_guardrail_gate),
    ("docker_packaging_gate", docker_packaging_gate),
)


def overall_status(results: list[GateResult]) -> str:
    if any(result.status == "FAIL" and result.blocking for result in results):
        return "FAIL"
    if any(result.status in {"WARN", "FAIL"} for result in results):
        return "WARN"
    return "PASS"


def run_all_gates(url: str = DEFAULT_URL) -> dict[str, Any]:
    results = [_safe_gate(name, func, url) for name, func in GATES]
    return {
        "overall_status": overall_status(results),
        "gates": [result.to_dict() for result in results],
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [f"OVERALL_STATUS={report['overall_status']}"]
    for gate in report["gates"]:
        lines.append("")
        lines.append(f"[{gate['status']}] {gate['gate_name']} blocking={str(gate['blocking']).lower()}")
        lines.append("  evidence=" + json.dumps(gate["evidence"], ensure_ascii=False, default=str))
        if gate["caveats"]:
            lines.append("  caveats=" + " | ".join(gate["caveats"]))
        if gate["recommended_fix"]:
            lines.append("  recommended_fix=" + gate["recommended_fix"])
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Validation gate latest report", "", f"**OVERALL_STATUS:** `{report['overall_status']}`", ""]
    lines.append("| Gate | Status | Blocking | Caveats | Recommended fix |")
    lines.append("|---|---|---:|---|---|")
    for gate in report["gates"]:
        caveats = "<br>".join(str(c) for c in gate["caveats"]) if gate["caveats"] else ""
        fix = str(gate["recommended_fix"]).replace("|", "\\|")
        lines.append(f"| `{gate['gate_name']}` | `{gate['status']}` | `{gate['blocking']}` | {caveats} | {fix} |")
    lines.append("")
    lines.append("## Evidence")
    for gate in report["gates"]:
        lines.append("")
        lines.append(f"### {gate['gate_name']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(gate["evidence"], ensure_ascii=False, indent=2, default=str))
        lines.append("```")
    return "\n".join(lines) + "\n"
