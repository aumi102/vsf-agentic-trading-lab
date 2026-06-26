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


def rsi_sma(closes: list[float], period: int) -> list[float | None]:
    """Wilder-style RSI using simple moving averages of up/down moves (Backtrader RSI_SMA)."""
    ups = [0.0] * len(closes)
    downs = [0.0] * len(closes)
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        ups[i] = max(change, 0.0)
        downs[i] = max(-change, 0.0)
    avg_up = _sma(ups, period)
    avg_down = _sma(downs, period)
    out: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        au, ad = avg_up[i], avg_down[i]
        if au is None or ad is None:
            continue
        if ad == 0:
            out[i] = 100.0
        else:
            rs = au / ad
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def rsi_mean_reversion_target_weights(
    closes: list[float], period: int, buy_below: float, exit_above: float, target_percent: float
) -> list[float]:
    """Long when RSI drops below buy_below; exit when RSI rises above exit_above."""
    rsi = rsi_sma(closes, period)
    weights = [0.0] * len(closes)
    target = 0.0
    for i in range(len(closes)):
        value = rsi[i]
        if value is not None:
            if target == 0.0 and value < buy_below:
                target = target_percent
            elif target > 0.0 and value > exit_above:
                target = 0.0
        weights[i] = target
    return weights


STRATEGIES = {"ma20_ma50", "buy_hold", "rsi_mean_reversion"}


def _target_weights(strategy: str, closes: list[float], fast: int, slow: int, target_percent: float) -> list[float]:
    if strategy == "ma20_ma50":
        return ma_cross_target_weights(closes, fast, slow, target_percent)
    if strategy == "buy_hold":
        return buy_hold_target_weights(closes, target_percent)
    if strategy == "rsi_mean_reversion":
        return rsi_mean_reversion_target_weights(closes, period=14, buy_below=30.0, exit_above=55.0, target_percent=target_percent)
    raise ValueError(f"unknown strategy: {strategy!r} (supported: {sorted(STRATEGIES)})")


def _apply_volume_filter(weights: list[float], volumes: list[float], window: int = 20) -> list[float]:
    """Zero out long bars whose volume is not above its rolling average (confirmation)."""
    vol_ma = _sma(volumes, window)
    out = list(weights)
    for i in range(len(out)):
        if out[i] > 0.0 and (vol_ma[i] is None or volumes[i] <= vol_ma[i]):
            out[i] = 0.0
    return out


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
    execution: str = "next_open",
    volume_filter: bool = False,
    price_input: str = "adjusted",
    exchange: str | None = None,
) -> BacktestOutput:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy!r} (supported: {sorted(STRATEGIES)})")
    if execution not in {"next_open", "same_close"}:
        raise ValueError("execution must be 'next_open' or 'same_close'")
    if not 0.0 < target_percent <= 1.0:
        raise ValueError("target_percent must be in (0, 1]")
    if len(bars) < slow + 2:
        raise ValueError(f"need > {slow + 2} bars, got {len(bars)}")

    closes = [b.close for b in bars]
    weights = _target_weights(strategy, closes, fast, slow, target_percent)
    if volume_filter:
        weights = _apply_volume_filter(weights, [b.volume for b in bars])

    guard = evaluate_price_band_guard(exchange, slippage_bps)
    slip = slippage_bps / 10_000.0
    cash = float(start_cash)
    shares = 0.0
    pending_target: float | None = None  # weight to execute at next bar's open

    equity_curve: list[dict[str, Any]] = []
    fills: list[Fill] = []
    open_entry: dict[str, Any] | None = None  # track open position for round-trip trades
    trades: list[RoundTripTrade] = []
    equity_values: list[float] = []

    def _do_fill(bar: Bar, price: float, target: float, index: int) -> None:
        """Move toward `target` weight at `price`; update cash/shares, fills, trades."""
        nonlocal cash, shares, open_entry
        if price <= 0:
            return
        target_value = target * (cash + shares * price)
        delta = target_value / price - shares
        if abs(delta) <= 1e-12:
            return
        fill_price = price * (1.0 + slip) if delta > 0 else price * (1.0 - slip)
        side = "buy" if delta > 0 else "sell"
        comm = abs(delta) * fill_price * commission
        cash -= delta * fill_price + comm
        shares += delta
        fills.append(Fill(bar.date, side, abs(delta), fill_price, comm, cash, shares))
        open_entry, closed = _update_trades(open_entry, side, bar, fill_price, abs(delta), index)
        if closed is not None:
            trades.append(closed)

    for i, bar in enumerate(bars):
        # FILL (next_open): execute the order queued on the previous bar at THIS open.
        if execution == "next_open" and pending_target is not None:
            _do_fill(bar, bar.open, pending_target, i)
            pending_target = None

        target = weights[i]
        current_weight = (shares * bar.close) / (cash + shares * bar.close) if (cash + shares * bar.close) > 0 else 0.0
        changed = _weight_changed(current_weight, target, target_percent)

        if execution == "same_close":
            # SIGNAL computed at close[t] is FILLED at the SAME close[t] (illustrative
            # variant; introduces a same-bar execution assumption, not look-ahead-free).
            if changed:
                _do_fill(bar, bar.close, target, i)
        elif changed:
            pending_target = target  # queue for the NEXT bar's open

        # ACCOUNT: mark equity using this bar's close.
        equity = cash + shares * bar.close
        equity_values.append(equity)
        equity_curve.append({"date": bar.date, "value": equity, "cash": cash, "shares": shares, "close": bar.close})

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
    exec_note = "fill at NEXT bar open (no look-ahead)" if execution == "next_open" else "fill at SAME-day close (same-bar execution assumption)"
    caveats = [
        f"self-implemented engine; execution convention = {exec_note}.",
        f"long-only, no leverage, target_percent={target_percent}, fractional shares allowed.",
        f"commission={commission} per trade value; slippage_bps={slippage_bps} applied to fill price.",
        f"price input = {price_input} OHLC; volume_filter={volume_filter}.",
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
            "execution": execution,
            "volume_filter": volume_filter,
            "price_input": price_input,
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
        f"  execution         : {out.params['execution']}",
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


# --- explicit logic block (Task A) ------------------------------------------
def engine_logic(out: BacktestOutput) -> dict[str, Any]:
    """Return a concrete, mentor-readable description of the engine's exact logic."""
    p = out.params
    fast, slow = p["fast"], p["slow"]
    strat = p["strategy"]
    if strat == "ma20_ma50":
        signal = f"long when MA{fast} > MA{slow} (enter on the upward cross), else cash (exit on the downward cross)"
    elif strat == "rsi_mean_reversion":
        signal = "long when RSI(14) < 30 (oversold), exit to cash when RSI(14) > 55"
    else:
        signal = "buy on the first bar and hold to the end"
    if p.get("volume_filter"):
        signal += "; additionally require volume > its 20-bar average to hold long"
    exec_desc = "the NEXT bar's OPEN (open[t+1]) - leak-free" if p["execution"] == "next_open" else "the SAME bar's CLOSE (close[t]) - optimistic same-bar assumption"
    return {
        "data_source": "QuestDB daily_prices (read-only)",
        "date_range": f"{out.start_date} .. {out.end_date}",
        "price_input": f"{p['price_input']} OHLC; quality_status='pass' rows only",
        "signal_formula": signal,
        "execution_timing": f"the order implied by close[t] is filled at {exec_desc}",
        "position_sizing": f"order_target_percent({p['target_percent']}): target value = {p['target_percent']} x equity, sized from close[t]",
        "commission": f"{p['commission']} ({p['commission'] * 100:g}%) of traded value, charged per fill",
        "slippage": f"{p['slippage_bps']} bps moved against the fill (buy higher, sell lower)",
        "fractional_shares": "yes (matches Backtrader's default)",
        "direction": "long-only; no shorting; no leverage",
        "cash_hold_behavior": "uninvested cash earns 0; when flat the portfolio is entirely cash",
        "equity_update": "equity[t] = cash + shares x close[t], recorded once per bar",
        "metrics": "total return; annualized = (1+total)^(365.25/calendar_days)-1; max drawdown; Sharpe = sqrt(252) x mean/std of daily equity returns (rf=0); trades = long round trips; win rate = winning round trips / trades",
        "why_differs_from_backtrader": [
            "sizes from close[t] but fills at open[t+1] (small sizing-vs-fill gap)",
            "Sharpe uses sqrt(252) x mean/std; Backtrader's SharpeRatio_A annualizes differently",
            "trade count = long round trips here vs Backtrader closed Trade objects",
            "same adjusted daily_prices rows, 0.95 target, 0.1% commission and bps slippage are used in both",
        ],
    }


# --- deterministic variant / sensitivity lab (Task B) -----------------------
def _variant(variant_id: str, changed: str, why: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "strategy": "ma20_ma50", "price_input": "adjusted", "execution": "next_open",
        "slippage_bps": 0.0, "target_percent": 0.95, "volume_filter": False,
    }
    base.update(overrides)
    return {"id": variant_id, "changed": changed, "why": why, **base}


VARIANT_SPECS: list[dict[str, Any]] = [
    _variant("baseline_ma20_ma50_adjusted_next_open", "baseline", "reference: adjusted close, next-open fill, 95% target, 0 bps"),
    _variant("ma20_ma50_raw_close_next_open", "price input adjusted -> raw", "raw close ignores corporate-action adjustment; splits/dividends distort the MAs and returns", price_input="raw"),
    _variant("ma20_ma50_adjusted_same_close", "execution next-open -> same-day close", "acting on the same close that produced the signal is an optimistic same-bar assumption", execution="same_close"),
    _variant("ma20_ma50_adjusted_next_open_full_capital", "target 95% -> 100% capital", "removing the 5% cash buffer raises exposure, returns and drawdown", target_percent=1.0),
    _variant("ma20_ma50_adjusted_next_open_5bps", "slippage 0 -> 5 bps", "each trade pays more friction; net return drops with turnover", slippage_bps=5.0),
    _variant("ma20_ma50_adjusted_next_open_10bps", "slippage 0 -> 10 bps", "double the 5 bps friction", slippage_bps=10.0),
    _variant("ma20_ma50_adjusted_next_open_15bps", "slippage 0 -> 15 bps", "highest friction; shows slippage sensitivity", slippage_bps=15.0),
    _variant("ma20_ma50_with_volume_filter", "feature: require volume > 20-bar average to be long", "volume confirmation changes days-in-market and trade timing", volume_filter=True),
    _variant("rsi_mean_reversion_baseline", "strategy MA-cross -> RSI(14) mean reversion", "different signal family: buy oversold (<30), exit on recovery (>55)", strategy="rsi_mean_reversion"),
]

_VARIANT_METRIC_KEYS = ("final_value", "total_return_pct", "annualized_return_pct", "max_drawdown_pct", "sharpe_ratio", "closed_trades", "win_rate_pct")


def run_variants(
    symbol: str,
    *,
    url: str = DEFAULT_URL,
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
) -> dict[str, Any]:
    """Run the deterministic variant lab for a symbol and return a comparison + narrative."""
    adj_bars, adj_caveats = load_bars_from_questdb(symbol, start_date, end_date, adjusted=True, url=url)
    raw_bars, raw_caveats = load_bars_from_questdb(symbol, start_date, end_date, adjusted=False, url=url)
    exchange = fetch_exchange(symbol, url=url)
    results: list[dict[str, Any]] = []
    baseline: dict[str, Any] | None = None
    for spec in VARIANT_SPECS:
        bars = raw_bars if spec["price_input"] == "raw" else adj_bars
        row: dict[str, Any] = {"id": spec["id"], "changed": spec["changed"], "why": spec["why"]}
        try:
            out = run_simple_backtest(
                bars, symbol=symbol, strategy=spec["strategy"], slippage_bps=spec["slippage_bps"],
                target_percent=spec["target_percent"], execution=spec["execution"],
                volume_filter=spec["volume_filter"], price_input=spec["price_input"], exchange=exchange,
            )
            row["metrics"] = {key: out.metrics.get(key) for key in _VARIANT_METRIC_KEYS}
        except Exception as exc:  # keep one bad variant from breaking the table
            row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
            continue
        if spec["id"].startswith("baseline"):
            baseline = row["metrics"]
        results.append(row)

    for row in results:
        if "metrics" in row and baseline is not None and not row["id"].startswith("baseline"):
            base_ret = baseline.get("total_return_pct") or 0.0
            var_ret = row["metrics"].get("total_return_pct") or 0.0
            delta = var_ret - base_ret
            direction = "outperforms" if delta > 0.05 else "underperforms" if delta < -0.05 else "matches"
            if row["id"] == "ma20_ma50_raw_close_next_open" and abs(delta) <= 0.05:
                row["narrative"] = (
                    "identical to baseline here because this symbol's adjusted OHLC currently equals raw "
                    "(adjustment factor ~ 1.0; source unverified). On a split/dividend name they would diverge."
                )
            else:
                row["narrative"] = f"{direction} baseline by {delta:+.2f} pp total return - {row['why']}"
    return {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "baseline_id": "baseline_ma20_ma50_adjusted_next_open",
        "variants": results,
        "caveats": list(dict.fromkeys(list(adj_caveats) + list(raw_caveats)))
        + ["deterministic + transparent; no live Backtrader; for explainability/sensitivity only"],
    }
