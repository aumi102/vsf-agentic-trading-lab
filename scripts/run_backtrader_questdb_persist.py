"""Run Backtrader research strategies and persist results to QuestDB.

This script is still research/demo infrastructure. It creates and writes only
``backtest_*`` result tables and never mutates market-data or financial-report
tables.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from export_questdb_ohlcv_for_backtrader import export_symbol_to_csv, parse_symbols, validate_date  # noqa: E402
from run_backtrader_questdb_demo import STRATEGIES, BacktestResult, print_results, run_one  # noqa: E402
from trading_agent.storage import questdb_client as qdb  # noqa: E402

BACKTEST_TABLES = ["backtest_runs", "backtest_metrics", "backtest_equity_curve", "backtest_trades"]
DEFAULT_OUT_DIR = Path("data/cache/backtrader")
RUN_COLUMNS = [
    "created_at", "run_id", "symbol", "strategy_id", "strategy_name", "start_date", "end_date",
    "data_source", "source_table", "code_commit", "start_cash", "commission", "slippage_bps",
    "adjusted_price_status", "status", "caveats",
]
METRIC_COLUMNS = [
    "created_at", "run_id", "symbol", "strategy_id", "strategy_name", "start_value", "final_value",
    "total_return_pct", "annualized_return_pct", "max_drawdown_pct", "sharpe_ratio", "closed_trades",
    "win_rate_pct", "quality_status",
]
EQUITY_COLUMNS = ["trade_date", "run_id", "symbol", "strategy_id", "strategy_name", "portfolio_value", "cash"]
TRADE_COLUMNS = ["trade_date", "run_id", "symbol", "strategy_id", "event_type", "size", "price", "value", "pnl", "pnl_pct"]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _date_ts(value: str) -> str:
    return f"{value[:10]}T00:00:00.000000Z"


def _code_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"


def _safe_run_id_part(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.upper()).strip("_")


def _make_run_id(batch_id: str, symbol: str, strategy_id: str, start_date: str, end_date: str, commit: str) -> str:
    parts = [
        batch_id,
        _safe_run_id_part(symbol),
        _safe_run_id_part(strategy_id),
        start_date.replace("-", ""),
        end_date.replace("-", ""),
        _safe_run_id_part(commit),
    ]
    return "_".join(part for part in parts if part)


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return out.getvalue().encode("utf-8")


def _ddl(table: str) -> str:
    if table == "backtest_runs":
        return """CREATE TABLE IF NOT EXISTS backtest_runs (
            created_at TIMESTAMP,
            run_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            strategy_id SYMBOL CAPACITY 1024 CACHE,
            strategy_name SYMBOL CAPACITY 1024 CACHE,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            data_source SYMBOL CAPACITY 256 CACHE,
            source_table SYMBOL CAPACITY 256 CACHE,
            code_commit SYMBOL CAPACITY 4096 CACHE,
            start_cash DOUBLE,
            commission DOUBLE,
            slippage_bps DOUBLE,
            adjusted_price_status SYMBOL CAPACITY 256 CACHE,
            status SYMBOL CAPACITY 256 CACHE,
            caveats STRING
        ) TIMESTAMP(created_at) PARTITION BY YEAR WAL"""
    if table == "backtest_metrics":
        return """CREATE TABLE IF NOT EXISTS backtest_metrics (
            created_at TIMESTAMP,
            run_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            strategy_id SYMBOL CAPACITY 1024 CACHE,
            strategy_name SYMBOL CAPACITY 1024 CACHE,
            start_value DOUBLE,
            final_value DOUBLE,
            total_return_pct DOUBLE,
            annualized_return_pct DOUBLE,
            max_drawdown_pct DOUBLE,
            sharpe_ratio DOUBLE,
            closed_trades LONG,
            win_rate_pct DOUBLE,
            quality_status SYMBOL CAPACITY 256 CACHE
        ) TIMESTAMP(created_at) PARTITION BY YEAR WAL"""
    if table == "backtest_equity_curve":
        return """CREATE TABLE IF NOT EXISTS backtest_equity_curve (
            trade_date TIMESTAMP,
            run_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            strategy_id SYMBOL CAPACITY 1024 CACHE,
            strategy_name SYMBOL CAPACITY 1024 CACHE,
            portfolio_value DOUBLE,
            cash DOUBLE
        ) TIMESTAMP(trade_date) PARTITION BY YEAR WAL"""
    if table == "backtest_trades":
        return """CREATE TABLE IF NOT EXISTS backtest_trades (
            trade_date TIMESTAMP,
            run_id SYMBOL CAPACITY 4096 CACHE,
            symbol SYMBOL CAPACITY 4096 CACHE,
            strategy_id SYMBOL CAPACITY 1024 CACHE,
            event_type SYMBOL CAPACITY 256 CACHE,
            size DOUBLE,
            price DOUBLE,
            value DOUBLE,
            pnl DOUBLE,
            pnl_pct DOUBLE
        ) TIMESTAMP(trade_date) PARTITION BY YEAR WAL"""
    raise ValueError(f"unknown backtest table: {table}")


def _ensure_tables(client, base_url: str) -> None:
    for table in BACKTEST_TABLES:
        qdb.exec_query(client, base_url, _ddl(table))


def _replace_tables(client, base_url: str) -> None:
    print("REPLACING ONLY BACKTEST RESULT TABLES; market and FA tables untouched")
    for table in BACKTEST_TABLES:
        qdb.exec_query(client, base_url, f"DROP TABLE IF EXISTS {table}")
    _ensure_tables(client, base_url)


def _adjusted_status(caveats: tuple[str, ...]) -> str:
    joined = " | ".join(caveats).lower()
    if "adjusted_price_missing_warn" in joined or "adjusted ohlc equals raw" in joined:
        return "source_adjustment_unverified"
    return "adjusted_ohlc_used"


def _quality_status(result: BacktestResult, adjusted_price_status: str) -> str:
    if adjusted_price_status == "source_adjustment_unverified":
        return "research_adjustment_unverified"
    if result.max_drawdown_pct is None or result.sharpe_ratio is None:
        return "research_metrics_partial"
    return "research_pass"


def _metric_value(value: float | None) -> float | str:
    return "" if value is None else value


def _result_rows(
    *,
    result: BacktestResult,
    run_id: str,
    strategy_id: str,
    created_at: str,
    code_commit: str,
    start_cash: float,
    commission: float,
    slippage_bps: float,
    adjusted_price_status: str,
    caveats: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    run_row = {
        "created_at": created_at,
        "run_id": run_id,
        "symbol": result.symbol,
        "strategy_id": strategy_id,
        "strategy_name": strategy_id,
        "start_date": _date_ts(result.start_date),
        "end_date": _date_ts(result.end_date),
        "data_source": "questdb",
        "source_table": "daily_prices",
        "code_commit": code_commit,
        "start_cash": start_cash,
        "commission": commission,
        "slippage_bps": slippage_bps,
        "adjusted_price_status": adjusted_price_status,
        "status": "complete",
        "caveats": json.dumps(list(caveats), ensure_ascii=False),
    }
    metric_row = {
        "created_at": created_at,
        "run_id": run_id,
        "symbol": result.symbol,
        "strategy_id": strategy_id,
        "strategy_name": strategy_id,
        "start_value": result.start_value,
        "final_value": result.final_value,
        "total_return_pct": result.total_return_pct,
        "annualized_return_pct": result.annualized_return_pct,
        "max_drawdown_pct": _metric_value(result.max_drawdown_pct),
        "sharpe_ratio": _metric_value(result.sharpe_ratio),
        "closed_trades": result.closed_trades,
        "win_rate_pct": _metric_value(result.win_rate_pct),
        "quality_status": _quality_status(result, adjusted_price_status),
    }
    equity_rows = [
        {
            "trade_date": _date_ts(str(row.get("date"))),
            "run_id": run_id,
            "symbol": result.symbol,
            "strategy_id": strategy_id,
            "strategy_name": strategy_id,
            "portfolio_value": row.get("value"),
            "cash": row.get("cash"),
        }
        for row in result.equity_curve
    ]
    return run_row, metric_row, equity_rows


def _import_rows(client, base_url: str, table: str, rows: list[dict[str, Any]], columns: list[str]) -> int:
    if not rows:
        return 0
    qdb.imp_csv(client, base_url, table, _csv_bytes(rows, columns), timeout_seconds=240.0)
    qdb.wait_wal_applied(client, base_url, table, attempts=240)
    return len(rows)


def persist_results(
    *,
    questdb_url: str,
    symbols: list[str],
    start_date: str,
    end_date: str,
    out_dir: Path,
    start_cash: float,
    commission: float,
    slippage_bps: float,
    replace_run_table: bool,
) -> tuple[list[BacktestResult], dict[str, int]]:
    base = questdb_url.rstrip("/")
    code_commit = _code_commit()
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    all_results: list[BacktestResult] = []
    run_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        csv_path = out_dir / f"backtrader_{symbol}_{start_date}_{end_date}.csv"
        export_result = export_symbol_to_csv(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            out_path=csv_path,
            questdb_url=questdb_url,
        )
        adjusted_price_status = _adjusted_status(export_result.caveats)
        print(
            f"exported symbol={symbol} rows={export_result.rows} "
            f"date_range={export_result.first_date}..{export_result.last_date} path={csv_path}"
        )
        print(f"adjusted_price_status={symbol}:{adjusted_price_status}")
        for caveat in export_result.caveats:
            print(f"caveat={symbol}: {caveat}")
        for strategy_id, strategy_cls in STRATEGIES.items():
            result = run_one(
                symbol=symbol,
                strategy_name=strategy_id,
                strategy_cls=strategy_cls,
                csv_path=csv_path,
                start_value=start_cash,
                commission=commission,
            )
            run_id = _make_run_id(batch_id, symbol, strategy_id, start_date, end_date, code_commit)
            created_at = _utc_timestamp()
            run_row, metric_row, result_equity_rows = _result_rows(
                result=result,
                run_id=run_id,
                strategy_id=strategy_id,
                created_at=created_at,
                code_commit=code_commit,
                start_cash=start_cash,
                commission=commission,
                slippage_bps=slippage_bps,
                adjusted_price_status=adjusted_price_status,
                caveats=export_result.caveats,
            )
            all_results.append(result)
            run_rows.append(run_row)
            metric_rows.append(metric_row)
            equity_rows.extend(result_equity_rows)

    with qdb.open_client(timeout_seconds=300.0) as client:
        if replace_run_table:
            _replace_tables(client, base)
        else:
            _ensure_tables(client, base)
        inserted = {
            "backtest_runs": _import_rows(client, base, "backtest_runs", run_rows, RUN_COLUMNS),
            "backtest_metrics": _import_rows(client, base, "backtest_metrics", metric_rows, METRIC_COLUMNS),
            "backtest_equity_curve": _import_rows(client, base, "backtest_equity_curve", equity_rows, EQUITY_COLUMNS),
            "backtest_trades": 0,
        }
        qdb.wait_wal_applied(client, base, "backtest_trades", attempts=60)
    return all_results, inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist Backtrader research results into QuestDB backtest tables.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol")
    group.add_argument("--symbols")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--start-cash", type=float, default=100_000_000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--replace-run-table", action="store_true")
    args = parser.parse_args()
    try:
        validate_date(args.start_date, "start_date")
        validate_date(args.end_date, "end_date")
        symbols = parse_symbols(args.symbol or args.symbols)
        results, inserted = persist_results(
            questdb_url=args.questdb_url,
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            out_dir=Path(args.out_dir),
            start_cash=args.start_cash,
            commission=args.commission,
            slippage_bps=args.slippage_bps,
            replace_run_table=args.replace_run_table,
        )
        print_results(results)
        for table in BACKTEST_TABLES:
            print(f"{table}_rows_inserted={inserted.get(table, 0)}")
        print("caveat=backtest_trades table is created but trade-level extraction is TODO")
    except Exception as exc:
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
