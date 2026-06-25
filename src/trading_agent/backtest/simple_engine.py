"""Transparent, self-implemented daily-bar backtest engine.

Purpose (mentor feedback): the persisted demo backtests run on Backtrader, whose
fill/sizing internals are a black box for explanation. This engine re-implements
the *same* MA20/MA50 logic with fully explicit, line-by-line Python so the trading
logic can be explained without relying on Backtrader internals.

What happens on each bar (the whole model in one place):

  1. SIGNAL  - using closes up to and including bar t, decide the target weight
               w_t in {0, target_percent}. For MA20/MA50 we go long on the bar
               where MA20 crosses above MA50 and go to cash when it crosses below
               (identical event logic to the Backtrader CrossOver strategy).
  2. ORDER   - if w_t differs from the position we currently hold, queue a market
               order. Order size is computed from the *close of bar t* (the sizing
               price), exactly like Backtrader's order_target_percent.
  3. FILL    - the queued order fills at the NEXT bar's OPEN (open[t+1]). This is
               the explicit execution convention (no same-day look-ahead). Slippage
               moves the fill against us; commission is charged on the traded value.
  4. ACCOUNT - cash and shares update from the fill; equity[t] = cash + shares*close[t].

Constraints (kept deliberately simple and explicit):
  * long-only, no shorting;
  * no leverage (target_percent <= 1.0, default 0.95 to mirror the demo runs);
  * fractional shares allowed (Backtrader's default), so sizing is exact;
  * commission is an explicit per-trade rate; slippage is an explicit bps haircut.

Everything is deterministic: same input bars + params -> identical output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_agent.backtest import metrics as M
from trading_agent.backtest.slippage_guard import evaluate_price_band_guard
from trading_agent.tools import questdb_market_data_tool as market

DEFAULT_URL = market.DEFAULT_URL
DEFAULT_START_CASH = 100_000_000.0
DEFAULT_COMMISSION = 0.001
DEFAULT_TARGET_PERCENT = 0.95


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Fill:
    date: str
    side: str          # "buy" | "sell"
    shares: float
    fill_price: float
    commission: float
    cash_after: float
    shares_after: float


@dataclass
class RoundTripTrade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    return_pct: float
    bars_held: int


@dataclass
class BacktestOutput:
    symbol: str
    strategy: str
    params: dict[str, Any]
    start_date: str
    end_date: str
    start_value: float
    final_value: float
    equity_curve: list[dict[str, Any]]
    fills: list[Fill]
    trades: list[RoundTripTrade]
    metrics: dict[str, Any]
    price_band_status: str
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "params": self.params,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "start_value": self.start_value,
            "final_value": self.final_value,
            "metrics": self.metrics,
            "price_band_status": self.price_band_status,
            "trades": [t.__dict__ for t in self.trades],
            "fills": [f.__dict__ for f in self.fills],
            "equity_curve_head": self.equity_curve[:3],
            "equity_curve_tail": self.equity_curve[-3:],
            "equity_curve_points": len(self.equity_curve),
            "caveats": self.caveats,
        }


# --- signals ----------------------------------------------------------------
def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ma_cross_target_weights(closes: list[float], fast: int, slow: int, target_percent: float) -> list[float]:
    """Target weight per bar using MA-cross *event* logic (matches Backtrader).

    Long (target_percent) from the bar MA_fast crosses above MA_slow until the bar
    it crosses below; flat (0.0) otherwise. Position persists between crosses.
    """
    ma_fast = _sma(closes, fast)
    ma_slow = _sma(closes, slow)
    weights = [0.0] * len(closes)
    target = 0.0
    prev_diff: float | None = None
    for i in range(len(closes)):
        f, s = ma_fast[i], ma_slow[i]
        if f is not None and s is not None:
            diff = f - s
            if prev_diff is not None:
                crossed_up = prev_diff <= 0 < diff
                crossed_down = prev_diff >= 0 > diff
                if crossed_up:
                    target = target_percent
                elif crossed_down:
                    target = 0.0
            prev_diff = diff
        weights[i] = target
    return weights


def buy_hold_target_weights(closes: list[float], target_percent: float) -> list[float]:
    """Enter target_percent on the first bar and hold to the end."""
    return [target_percent] * len(closes)


STRATEGIES = {"ma20_ma50", "buy_hold"}


def _target_weights(strategy: str, closes: list[float], fast: int, slow: int, target_percent: float) -> list[float]:
    if strategy == "ma20_ma50":
        return ma_cross_target_weights(closes, fast, slow, target_percent)
    if strategy == "buy_hold":
        return buy_hold_target_weights(closes, target_percent)
    raise ValueError(f"unknown strategy: {strategy!r} (supported: {sorted(STRATEGIES)})")


# --- engine -----------------------------------------------------------------
def run_simple_backtest(
    bars: list[Bar],
    *,
    symbol: str,
    strategy: str = "ma20_ma50",
    fast: int = 20,
    slow: int = 50,
    start_cash: float = DEFAULT_START_CASH,
    commission: float = DEFAULT_COMMISSION,
    slippage_bps: float = 0.0,
    target_percent: float = DEFAULT_TARGET_PERCENT,
    exchange: str | None = None,
) -> BacktestOutput:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy!r} (supported: {sorted(STRATEGIES)})")
    if not 0.0 < target_percent <= 1.0:
        raise ValueError("target_percent must be in (0, 1]")
    if len(bars) < slow + 2:
        raise ValueError(f"need > {slow + 2} bars, got {len(bars)}")

    closes = [b.close for b in bars]
    weights = _target_weights(strategy, closes, fast, slow, target_percent)

    guard = evaluate_price_band_guard(exchange, slippage_bps)
    slip = slippage_bps / 10_000.0
    cash = float(start_cash)
    shares = 0.0
    pending_target: float | None = None  # weight to execute at next bar's open

    equity_curve: list[dict[str, Any]] = []
    fills: list[Fill] = []
    # Track open position for round-trip trade reconstruction.
    open_entry: dict[str, Any] | None = None
    trades: list[RoundTripTrade] = []
    equity_values: list[float] = []

    for i, bar in enumerate(bars):
        # STEP 3 (FILL): execute the order queued on the previous bar at THIS open.
        if pending_target is not None:
            target_value = pending_target * (cash + shares * bar.open)
            desired_shares = target_value / bar.open if bar.open > 0 else shares
            delta = desired_shares - shares
            if abs(delta) > 1e-12 and bar.open > 0:
                if delta > 0:
                    fill_price = bar.open * (1.0 + slip)
                    side = "buy"
                else:
                    fill_price = bar.open * (1.0 - slip)
                    side = "sell"
                trade_value = abs(delta) * fill_price
                comm = trade_value * commission
                cash -= delta * fill_price + comm
                shares += delta
                fills.append(Fill(bar.date, side, abs(delta), fill_price, comm, cash, shares))
                open_entry, closed = _update_trades(open_entry, side, bar, fill_price, abs(delta), i)
                if closed is not None:
                    trades.append(closed)
            pending_target = None

        # STEP 4 (ACCOUNT): mark equity using this bar's close.
        equity = cash + shares * bar.close
        equity_values.append(equity)
        equity_curve.append({"date": bar.date, "value": equity, "cash": cash, "shares": shares, "close": bar.close})

        # STEP 1+2 (SIGNAL + ORDER): decide the target from closes up to and incl. t;
        # if it differs from what we hold, queue an order for the NEXT open.
        target = weights[i]
        current_weight = (shares * bar.close) / equity if equity > 0 else 0.0
        if _weight_changed(current_weight, target, target_percent):
            pending_target = target

    # Close any still-open round trip at the final close for win-rate reporting.
    if open_entry is not None:
        last = bars[-1]
        gross = last.close / open_entry["price"] - 1.0
        trades.append(
            RoundTripTrade(
                entry_date=open_entry["date"],
                exit_date=last.date,
                entry_price=round(open_entry["price"], 6),
                exit_price=round(last.close, 6),
                shares=round(open_entry["shares"], 6),
                pnl=round((last.close - open_entry["price"]) * open_entry["shares"], 2),
                return_pct=round(gross * 100.0, 4),
                bars_held=len(bars) - 1 - open_entry["index"],
            )
        )

    final_value = equity_values[-1] if equity_values else float(start_cash)
    dates = [b.date for b in bars]
    trade_pnls = [t.pnl for t in trades]
    position_flags = [row["shares"] > 0 for row in equity_curve]
    summary = M.summarize_metrics(
        equity=equity_values,
        dates=dates,
        trade_pnls=trade_pnls,
        position_flags=position_flags,
        number_of_trades=len(trades),
    )
    metrics = {
        "start_value": round(start_cash, 2),
        "final_value": round(final_value, 2),
        "total_return_pct": _pct(summary["total_return"]),
        "annualized_return_pct": _pct(summary["annualized_return"]),
        "max_drawdown_pct": _pct(summary["max_drawdown"]),
        "sharpe_ratio": _round(summary["sharpe"]),
        "sortino_ratio": _round(summary["sortino"]),
        "closed_trades": len(trades),
        "win_rate_pct": _pct(summary["win_rate"]),
        "exposure_pct": _pct(summary["exposure"]),
        "buy_hold_return_pct": round((closes[-1] / closes[0] - 1.0) * 100.0, 4) if closes[0] else None,
    }
    caveats = [
        "self-implemented engine; execution convention = fill at NEXT bar open (no look-ahead).",
        f"long-only, no leverage, target_percent={target_percent}, fractional shares allowed.",
        f"commission={commission} per trade value; slippage_bps={slippage_bps} applied to fill price.",
        "adjusted OHLC source remains unverified/raw-equivalent; results are research-only.",
        *list(guard.caveats),
    ]
    return BacktestOutput(
        symbol=symbol,
        strategy=strategy,
        params={
            "strategy": strategy,
            "fast": fast,
            "slow": slow,
            "start_cash": start_cash,
            "commission": commission,
            "slippage_bps": slippage_bps,
            "target_percent": target_percent,
            "execution": "next_bar_open",
            "exchange": guard.exchange,
        },
        start_date=dates[0],
        end_date=dates[-1],
        start_value=start_cash,
        final_value=final_value,
        equity_curve=equity_curve,
        fills=fills,
        trades=trades,
        metrics=metrics,
        price_band_status=guard.status,
        caveats=caveats,
    )


def _weight_changed(current: float, target: float, target_percent: float) -> bool:
    """Treat as a position change when crossing the flat<->invested boundary."""
    currently_invested = current > target_percent * 0.5
    wants_invested = target > target_percent * 0.5
    return currently_invested != wants_invested


def _update_trades(open_entry, side, bar, fill_price, qty, index):
    """Maintain a single open round-trip; return (open_entry, closed_trade_or_None)."""
    if side == "buy" and open_entry is None:
        return {"date": bar.date, "price": fill_price, "shares": qty, "index": index}, None
    if side == "sell" and open_entry is not None:
        gross = fill_price / open_entry["price"] - 1.0
        closed = RoundTripTrade(
            entry_date=open_entry["date"],
            exit_date=bar.date,
            entry_price=round(open_entry["price"], 6),
            exit_price=round(fill_price, 6),
            shares=round(open_entry["shares"], 6),
            pnl=round((fill_price - open_entry["price"]) * open_entry["shares"], 2),
            return_pct=round(gross * 100.0, 4),
            bars_held=index - open_entry["index"],
        )
        return None, closed
    return open_entry, None


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100.0, 4)


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


# --- data loading -----------------------------------------------------------
def load_bars_from_questdb(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    adjusted: bool = True,
    url: str = DEFAULT_URL,
) -> tuple[list[Bar], list[str]]:
    """Load pass-quality OHLCV bars (adjusted by default) for a symbol from QuestDB."""
    res = market.get_ohlcv_window(symbol, start_date, end_date, adjusted=adjusted, url=url)
    if res.get("status") != "ok":
        raise RuntimeError(f"QuestDB window query failed: {res.get('caveats')}")
    bars: list[Bar] = []
    for row in res.get("rows", []):
        try:
            bars.append(
                Bar(
                    date=str(row.get("trade_date"))[:10],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
        except (TypeError, ValueError, KeyError):
            continue
    return bars, list(res.get("caveats", []))


def fetch_exchange(symbol: str, *, url: str = DEFAULT_URL) -> str | None:
    """Best-effort exchange lookup for the price-band guard."""
    sym = (symbol or "").strip().upper()
    res = market.query_questdb(f"SELECT exchange FROM securities WHERE symbol = '{sym}' LIMIT 1", url=url)
    if res.get("status") == "ok" and res.get("rows"):
        return res["rows"][0].get("exchange")
    return None


def format_report(out: BacktestOutput) -> str:
    m = out.metrics

    def num(value: Any, suffix: str = "") -> str:
        return "n/a" if value is None else f"{value:,}{suffix}"

    lines = [
        f"Self-implemented engine  symbol={out.symbol}  strategy={out.strategy}",
        f"  period            : {out.start_date} .. {out.end_date}",
        f"  execution         : {out.params['execution']} (fill at next bar open)",
        f"  target_percent    : {out.params['target_percent']}  commission: {out.params['commission']}  slippage_bps: {out.params['slippage_bps']}",
        f"  price_band_status : {out.price_band_status}",
        "  " + "-" * 56,
        f"  start value       : {num(m['start_value'])}",
        f"  final value       : {num(m['final_value'])}",
        f"  total return      : {num(m['total_return_pct'], '%')}",
        f"  annualized return : {num(m['annualized_return_pct'], '%')}",
        f"  max drawdown      : {num(m['max_drawdown_pct'], '%')}",
        f"  sharpe (ann.)     : {num(m['sharpe_ratio'])}",
        f"  closed trades     : {num(m['closed_trades'])}",
        f"  win rate          : {num(m['win_rate_pct'], '%')}",
        f"  exposure          : {num(m['exposure_pct'], '%')}",
        f"  buy & hold return : {num(m['buy_hold_return_pct'], '%')}  (benchmark)",
    ]
    return "\n".join(lines)
