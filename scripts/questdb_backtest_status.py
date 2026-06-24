"""Read-only status report for QuestDB backtest result tables."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.storage import questdb_client as qdb  # noqa: E402

BACKTEST_TABLES = ["backtest_runs", "backtest_metrics", "backtest_equity_curve", "backtest_trades"]


def _existing_tables(client, base: str) -> set[str]:
    _, table_rows = qdb.exec_rows(client, base, "SHOW TABLES")
    return {str(row[0]) for row in table_rows if row}


def _columns(client, base: str, table: str) -> set[str]:
    return set(qdb.column_names(client, base, table))


def _count(client, base: str, table: str) -> int:
    return int(qdb.exec_scalar(client, base, f"SELECT count() FROM {table}", 0))


def _print_symbol_strategy_summary(client, base: str, table: str, columns: set[str]) -> None:
    if "symbol" in columns:
        symbols = int(qdb.exec_scalar(client, base, f"SELECT count_distinct(symbol) FROM {table}", 0))
        print(f"  symbols={symbols:,}")
    if "strategy_id" in columns:
        _, strategies = qdb.exec_rows(client, base, f"SELECT strategy_id, count() c FROM {table} ORDER BY strategy_id")
        print("  strategies=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in strategies))
    if "slippage_bps" in columns:
        _, rows = qdb.exec_rows(client, base, f"SELECT slippage_bps, count() c FROM {table} GROUP BY slippage_bps ORDER BY slippage_bps")
        print("  slippage_bps=" + ", ".join(f"{float(row[0] or 0):g}:{int(row[1]):,}" for row in rows))
    if "scenario_label" in columns:
        _, rows = qdb.exec_rows(client, base, f"SELECT scenario_label, count() c FROM {table} GROUP BY scenario_label ORDER BY scenario_label")
        print("  scenarios=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in rows))


def _print_run_breakdowns(client, base: str, table: str, columns: set[str]) -> None:
    if "run_id" in columns:
        if "created_at" in columns:
            latest_sql = f"SELECT run_id FROM {table} ORDER BY created_at DESC LIMIT 1"
        elif "trade_date" in columns:
            latest_sql = f"SELECT run_id FROM {table} ORDER BY trade_date DESC, run_id DESC LIMIT 1"
        else:
            latest_sql = f"SELECT run_id FROM {table} ORDER BY run_id DESC LIMIT 1"
        _, latest = qdb.exec_rows(client, base, latest_sql)
        if latest:
            print(f"  latest_run_id={latest[0][0]}")
    if "adjusted_price_status" in columns:
        _, rows = qdb.exec_rows(client, base, f"SELECT adjusted_price_status, count() c FROM {table} ORDER BY c DESC")
        print("  adjusted_price_status=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in rows))
    if "quality_status" in columns:
        _, rows = qdb.exec_rows(client, base, f"SELECT quality_status, count() c FROM {table} ORDER BY c DESC")
        print("  quality_status=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in rows))
    if "price_band_status" in columns:
        _, rows = qdb.exec_rows(client, base, f"SELECT price_band_status, count() c FROM {table} ORDER BY c DESC")
        print("  price_band_status=" + ", ".join(f"{row[0]}:{int(row[1]):,}" for row in rows))


def _print_latest_metrics(client, base: str, existing: set[str]) -> None:
    if "backtest_metrics" not in existing:
        return
    metric_columns = _columns(client, base, "backtest_metrics")
    has_scenarios = {"slippage_bps", "scenario_label"}.issubset(metric_columns)
    scenario_select = ", m.slippage_bps, m.scenario_label " if has_scenarios else " "
    scenario_header = " | slippage_bps | scenario" if has_scenarios else ""
    scenario_filter = "WHERE slippage_bps = 0.0 " if has_scenarios else ""
    latest_run_limit = 9
    _, rows = qdb.exec_rows(
        client,
        base,
        "SELECT m.symbol, m.strategy_id, m.final_value, m.total_return_pct, m.annualized_return_pct, "
        "m.max_drawdown_pct, m.sharpe_ratio, m.closed_trades, m.win_rate_pct, m.run_id"
        f"{scenario_select}"
        "FROM backtest_metrics m "
        f"JOIN (SELECT run_id FROM backtest_runs {scenario_filter}ORDER BY created_at DESC LIMIT {latest_run_limit}) r ON m.run_id = r.run_id "
        "ORDER BY m.symbol, m.strategy_id",
    )
    if not rows:
        return
    label = "latest_default_metrics" if has_scenarios else "latest_metrics"
    print(f"{label}:")
    print("  symbol | strategy | final_value | total_return_pct | annualized_return_pct | max_drawdown_pct | sharpe | trades | win_rate_pct" + scenario_header)
    for row in rows:
        extra = ""
        if has_scenarios:
            extra = f" | {float(row[10] or 0):g} | {row[11]}"
        print(
            "  "
            f"{row[0]} | {row[1]} | {float(row[2]):,.0f} | {float(row[3]):.2f} | "
            f"{float(row[4]):.2f} | {float(row[5]):.2f} | "
            f"{'' if row[6] is None else f'{float(row[6]):.2f}'} | "
            f"{int(row[7]) if row[7] is not None else 0} | "
            f"{'' if row[8] is None else f'{float(row[8]):.2f}'}"
            f"{extra}"
        )


def _print_latest_trades(client, base: str, existing: set[str]) -> None:
    if "backtest_trades" not in existing:
        return
    _, rows = qdb.exec_rows(
        client,
        base,
        "SELECT trade_date, symbol, strategy_id, event_type, size, price, value, pnl, pnl_pct "
        "FROM backtest_trades ORDER BY trade_date DESC, run_id DESC LIMIT 5",
    )
    if not rows:
        return
    print("latest_trades:")
    print("  trade_date | symbol | strategy | event | size | price | value | pnl | pnl_pct")
    for row in rows:
        print(
            "  "
            f"{str(row[0])[:10]} | {row[1]} | {row[2]} | {row[3]} | "
            f"{'' if row[4] is None else f'{float(row[4]):,.0f}'} | "
            f"{'' if row[5] is None else f'{float(row[5]):,.2f}'} | "
            f"{'' if row[6] is None else f'{float(row[6]):,.2f}'} | "
            f"{'' if row[7] is None else f'{float(row[7]):,.2f}'} | "
            f"{'' if row[8] is None else f'{float(row[8]):.2f}'}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Show QuestDB backtest result table status.")
    parser.add_argument("--questdb-url", default=qdb.DEFAULT_QUESTDB_URL)
    args = parser.parse_args()
    base = args.questdb_url.rstrip("/")
    with qdb.open_client() as client:
        existing = _existing_tables(client, base)
        print("tables_present=" + ",".join(table for table in BACKTEST_TABLES if table in existing))
        for table in BACKTEST_TABLES:
            if table not in existing:
                print(f"{table}: missing")
                continue
            columns = _columns(client, base, table)
            total = _count(client, base, table)
            print(f"{table}: rows={total:,}")
            _print_symbol_strategy_summary(client, base, table, columns)
            _print_run_breakdowns(client, base, table, columns)
        _print_latest_metrics(client, base, existing)
        _print_latest_trades(client, base, existing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
