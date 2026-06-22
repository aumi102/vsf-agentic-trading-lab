"""Simple long-only MA(20)/MA(50) crossover strategy + backtest.

Rules (per spec):
  * Uses adjusted close.
  * BUY (full position) when MA_fast > MA_slow, else CASH (flat).
  * Long-only, 1x notional, no leverage.
  * Transaction cost default 15 bps (0.15%) charged on each position change.

No future leakage / execution convention:
  The signal is computed from the close of day t (MA values use closes up to
  and including t). The signal is then shifted forward one trading day
  (position[t+1] = signal[t]), i.e. it is EXECUTED AT THE NEXT DAY'S CLOSE and
  captures that day's close-to-close return. No position ever depends on the
  same-day or any future price, so there is no look-ahead.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def run_ma_cross_backtest(
    df: pd.DataFrame,
    *,
    fast: int = 20,
    slow: int = 50,
    cost_bps: float = 15.0,
    price_col: str = "close",
    date_col: str = "trade_date",
) -> dict[str, Any]:
    """Run the MA-cross backtest on a frame with date_col + price_col (adjusted close)."""
    if fast >= slow:
        return {"status": "error", "caveats": [f"fast ({fast}) must be < slow ({slow})"]}
    data = df[[date_col, price_col]].copy()
    data[price_col] = pd.to_numeric(data[price_col], errors="coerce")
    data = data.dropna(subset=[price_col]).reset_index(drop=True)
    if len(data) <= slow + 2:
        return {"status": "error", "caveats": [f"need > {slow + 2} bars, got {len(data)}"]}

    close = data[price_col]
    ma_fast = close.rolling(fast).mean()
    ma_slow = close.rolling(slow).mean()

    signal = (ma_fast > ma_slow).astype(float)
    signal[ma_fast.isna() | ma_slow.isna()] = 0.0
    position = signal.shift(1).fillna(0.0)  # next-day execution -> no look-ahead

    ret = close.pct_change().fillna(0.0)
    cost_rate = cost_bps / 10_000.0
    turnover = position.diff().abs().fillna(position.abs())
    costs = turnover * cost_rate
    strat_ret = position * ret - costs

    equity = (1.0 + strat_ret).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    n_days = len(data)
    years = n_days / TRADING_DAYS_PER_YEAR
    annualized_return = float((equity.iloc[-1]) ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else float("nan")
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())
    vol = float(strat_ret.std())
    sharpe = float(strat_ret.mean() / vol * np.sqrt(TRADING_DAYS_PER_YEAR)) if vol > 0 else float("nan")

    trades = _extract_trades(data, position, close, date_col, cost_rate)
    wins = [t for t in trades if t["return_pct"] > 0]
    win_rate = (len(wins) / len(trades)) if trades else float("nan")

    buy_hold_return = float(close.iloc[-1] / close.iloc[0] - 1.0)

    return {
        "status": "ok",
        "params": {"fast": fast, "slow": slow, "cost_bps": cost_bps, "execution": "next_day_close"},
        "metrics": {
            "bars": n_days,
            "start_date": str(data[date_col].iloc[0])[:10],
            "end_date": str(data[date_col].iloc[-1])[:10],
            "total_return": total_return,
            "annualized_return": annualized_return,
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "number_of_trades": len(trades),
            "win_rate": win_rate,
            "buy_hold_return": buy_hold_return,
        },
        "trades": trades,
        "caveats": [
            "adjusted close used; signal shifted 1 day (next-day-close execution, leak-free).",
            f"transaction cost {cost_bps} bps per position change; long-only, 1x, no leverage.",
        ],
    }


def _extract_trades(
    data: pd.DataFrame, position: pd.Series, close: pd.Series, date_col: str, cost_rate: float
) -> list[dict[str, Any]]:
    """Reconstruct round-trip trades (entry->exit) for win-rate reporting."""
    trades: list[dict[str, Any]] = []
    in_pos = False
    entry_idx = 0
    pos = position.to_numpy()
    for i in range(len(pos)):
        if not in_pos and pos[i] > 0:
            in_pos = True
            entry_idx = i
        elif in_pos and pos[i] == 0:
            trades.append(_make_trade(data, close, date_col, entry_idx, i, cost_rate))
            in_pos = False
    if in_pos:  # still holding at the end -> close at last bar
        trades.append(_make_trade(data, close, date_col, entry_idx, len(pos) - 1, cost_rate))
    return trades


def _make_trade(data, close, date_col, entry_idx, exit_idx, cost_rate) -> dict[str, Any]:
    entry_px = float(close.iloc[entry_idx])
    exit_px = float(close.iloc[exit_idx])
    gross = exit_px / entry_px - 1.0
    net = gross - 2.0 * cost_rate  # entry + exit cost
    return {
        "entry_date": str(data[date_col].iloc[entry_idx])[:10],
        "exit_date": str(data[date_col].iloc[exit_idx])[:10],
        "entry_price": round(entry_px, 4),
        "exit_price": round(exit_px, 4),
        "return_pct": round(net * 100.0, 4),
        "bars_held": int(exit_idx - entry_idx),
    }


def format_report(symbol: str, result: dict[str, Any]) -> str:
    """Human-readable result table."""
    if result.get("status") != "ok":
        return f"Backtest error for {symbol}: {', '.join(result.get('caveats', []))}"
    m = result["metrics"]
    p = result["params"]

    def pct(x: float) -> str:
        return "n/a" if x != x else f"{x * 100:,.2f}%"

    def num(x: float) -> str:
        return "n/a" if x != x else f"{x:,.2f}"

    lines = [
        f"Strategy : MA{p['fast']}/MA{p['slow']} crossover, long-only, {p['cost_bps']} bps cost, {p['execution']} exec",
        f"Symbol   : {symbol}   Period: {m['start_date']} .. {m['end_date']}  ({m['bars']} bars)",
        "-" * 60,
        f"  {'Total return':<22}: {pct(m['total_return'])}",
        f"  {'Annualized return':<22}: {pct(m['annualized_return'])}",
        f"  {'Max drawdown':<22}: {pct(m['max_drawdown'])}",
        f"  {'Sharpe (ann.)':<22}: {num(m['sharpe'])}",
        f"  {'Number of trades':<22}: {m['number_of_trades']}",
        f"  {'Win rate':<22}: {pct(m['win_rate'])}",
        f"  {'Buy & hold return':<22}: {pct(m['buy_hold_return'])}  (benchmark)",
        "-" * 60,
    ]
    return "\n".join(lines)
