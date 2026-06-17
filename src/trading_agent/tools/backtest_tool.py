from __future__ import annotations

from pathlib import Path
from typing import Any

from trading_agent.backtest.mvp_engine import run_backtest
from trading_agent.signals.mvp_momentum import STRATEGY_ID
from trading_agent.tools._store import DEFAULT_DB_PATH


def run_backtest_tool(
    symbols: list[str],
    db_path: str | Path = DEFAULT_DB_PATH,
    strategy_id: str = STRATEGY_ID,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100_000_000.0,
    transaction_cost: float = 0.001,
    slippage: float = 0.0005,
) -> dict[str, Any]:
    return run_backtest(
        symbols=symbols,
        db_path=db_path,
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        transaction_cost=transaction_cost,
        slippage=slippage,
    )
