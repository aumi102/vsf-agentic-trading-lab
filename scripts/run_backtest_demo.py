from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.backtest.mvp_engine import (  # noqa: E402
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_SLIPPAGE,
    DEFAULT_TRANSACTION_COST,
    run_backtest,
)
from trading_agent.signals.mvp_momentum import STRATEGY_ID  # noqa: E402
from trading_agent.tools._store import DEFAULT_DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the exploratory Backtest MVP over the local SQLite demo store.")
    parser.add_argument("--symbols", default="FPT,VNM,VCB", help="Comma-separated symbols.")
    parser.add_argument("--strategy-id", default=STRATEGY_ID)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL)
    parser.add_argument("--transaction-cost", type=float, default=DEFAULT_TRANSACTION_COST)
    parser.add_argument("--slippage", type=float, default=DEFAULT_SLIPPAGE)
    args = parser.parse_args()

    result = run_backtest(
        symbols=[item.strip().upper() for item in args.symbols.split(",") if item.strip()],
        strategy_id=args.strategy_id,
        start_date=args.start_date,
        end_date=args.end_date,
        db_path=args.db_path,
        initial_capital=args.initial_capital,
        transaction_cost=args.transaction_cost,
        slippage=args.slippage,
    )
    print(json.dumps(_summary(result), indent=2, sort_keys=True))
    print()
    _print_metrics_table(result.get("metrics", {}))
    print()
    _print_caveats(result)

    status = result.get("status")
    if status == "ok":
        return 0
    if status == "invalid_assumptions":
        return 2
    return 1


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    return {
        "status": result.get("status"),
        "strategy_id": result.get("strategy_id"),
        "symbols": result.get("symbols"),
        "symbols_found": result.get("symbols_found", []),
        "symbols_missing": result.get("symbols_missing", []),
        "start_date": result.get("start_date"),
        "end_date": result.get("end_date"),
        "assumptions": result.get("assumptions"),
        "metrics": {key: metrics.get(key) for key in _METRIC_KEYS},
        "validation_gates": result.get("validation_gates"),
        "not_financial_advice": result.get("not_financial_advice"),
    }


def _print_metrics_table(metrics: dict[str, Any]) -> None:
    print("metric | value")
    print("--- | ---")
    for key in _METRIC_KEYS:
        print(f"{key} | {_format_metric(metrics.get(key))}")


def _print_caveats(result: dict[str, Any]) -> None:
    print("caveats")
    for caveat in result.get("caveats", []):
        print(f"- {caveat}")
    print("- Exploratory output only; not financial advice.")


def _format_metric(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


_METRIC_KEYS = [
    "total_return",
    "annualized_return",
    "sharpe",
    "sortino",
    "profit_factor",
    "max_drawdown",
    "win_rate",
    "number_of_trades",
    "exposure",
]


if __name__ == "__main__":
    raise SystemExit(main())
