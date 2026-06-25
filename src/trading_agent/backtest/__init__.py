"""Backtest package.

``run_backtest`` (the pandas/Backtrader research engine) is exposed lazily so that
importing lightweight, pandas-free submodules — ``slippage_guard``, ``metrics`` and
``simple_engine`` — does not pull in pandas. This keeps the read-only FastAPI demo and
the validation gates importable under the core (no-pandas) environment.

Both access styles keep working:
  * ``from trading_agent.backtest import run_backtest``        (lazy, on access)
  * ``from trading_agent.backtest.mvp_engine import run_backtest``  (direct)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["run_backtest"]

if TYPE_CHECKING:  # type-checkers / IDEs only; no runtime import
    from trading_agent.backtest.mvp_engine import run_backtest


def __getattr__(name: str):
    if name == "run_backtest":
        from trading_agent.backtest.mvp_engine import run_backtest

        return run_backtest
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
