from __future__ import annotations

import math


TRADING_DAYS_PER_YEAR = 252


def total_return(equity: list[float]) -> float | None:
    if len(equity) < 2 or equity[0] == 0:
        return None
    return equity[-1] / equity[0] - 1.0


def annualized_return(equity: list[float], dates: list[str]) -> float | None:
    result = total_return(equity)
    if result is None or len(dates) < 2:
        return None
    days = _calendar_days(dates[0], dates[-1])
    if days <= 0 or result <= -1:
        return None
    return (1.0 + result) ** (365.25 / days) - 1.0


def sharpe_ratio(returns: list[float]) -> float | None:
    clean = [value for value in returns if value is not None]
    if len(clean) < 2:
        return None
    std = _sample_std(clean)
    if std is None or std == 0:
        return None
    return math.sqrt(TRADING_DAYS_PER_YEAR) * (_mean(clean) / std)


def sortino_ratio(returns: list[float]) -> float | None:
    clean = [value for value in returns if value is not None]
    downside = [min(0.0, value) for value in clean if value < 0]
    if len(clean) < 2 or len(downside) < 2:
        return None
    downside_std = _sample_std(downside)
    if downside_std is None or downside_std == 0:
        return None
    return math.sqrt(TRADING_DAYS_PER_YEAR) * (_mean(clean) / downside_std)


def profit_factor(trade_pnls: list[float]) -> float | None:
    gross_profit = sum(value for value in trade_pnls if value > 0)
    gross_loss = abs(sum(value for value in trade_pnls if value < 0))
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def max_drawdown(equity: list[float]) -> float | None:
    if not equity:
        return None
    peak = equity[0]
    worst = 0.0
    for value in equity:
        if value > peak:
            peak = value
        if peak == 0:
            continue
        drawdown = value / peak - 1.0
        worst = min(worst, drawdown)
    return worst


def win_rate(trade_pnls: list[float]) -> float | None:
    if not trade_pnls:
        return None
    wins = sum(1 for value in trade_pnls if value > 0)
    return wins / len(trade_pnls)


def exposure(position_flags: list[bool]) -> float | None:
    if not position_flags:
        return None
    return sum(1 for value in position_flags if value) / len(position_flags)


def daily_returns(equity: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(equity, equity[1:]):
        if previous == 0:
            continue
        returns.append(current / previous - 1.0)
    return returns


def summarize_metrics(
    *,
    equity: list[float],
    dates: list[str],
    trade_pnls: list[float],
    position_flags: list[bool],
    number_of_trades: int,
) -> dict[str, float | int | None]:
    returns = daily_returns(equity)
    return {
        "total_return": total_return(equity),
        "annualized_return": annualized_return(equity, dates),
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "profit_factor": profit_factor(trade_pnls),
        "max_drawdown": max_drawdown(equity),
        "win_rate": win_rate(trade_pnls),
        "number_of_trades": number_of_trades,
        "exposure": exposure(position_flags),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _calendar_days(start: str, end: str) -> int:
    from datetime import date

    return (date.fromisoformat(end) - date.fromisoformat(start)).days
