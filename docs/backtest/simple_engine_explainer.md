# Transparent self-implemented backtest engine (SimpleEngine)

Mentor feedback #3: the demo backtests run on Backtrader, whose fill/sizing
internals are hard to explain. `src/trading_agent/backtest/simple_engine.py`
re-implements the **same MA20/MA50 logic** in fully explicit Python so the trading
logic can be explained line by line — and so we can show it reproduces Backtrader's
economics.

Run it:

```bat
python scripts\run_simple_backtest_demo.py --symbol FPT --strategy ma20_ma50 ^
    --start-date 2020-01-01 --end-date 2025-12-31 --slippage-bps 0
```

Read-only: it loads persisted adjusted OHLCV from QuestDB, runs in-process, and
looks up the persisted Backtrader metrics for the same symbol/strategy/slippage to
print a side-by-side comparison. It **never** runs live Backtrader and never mutates
QuestDB.

## The whole model, on each bar `t`

For each daily bar in ascending date order:

1. **FILL (from the previous bar's decision).** If an order was queued on bar `t-1`,
   it executes at **this bar's open** (`open[t]`). This is the explicit execution
   convention — next-bar-open, so no decision ever depends on same-day or future
   prices (no look-ahead).
   - target value `= pending_target * (cash + shares*open[t])`
   - desired shares `= target_value / open[t]`; `delta = desired - shares`
   - buy fill price `= open[t] * (1 + slippage_bps/10000)`; sell `= open[t] * (1 - …)`
   - commission `= |delta| * fill_price * commission_rate`
   - `cash -= delta*fill_price + commission`; `shares += delta`
2. **ACCOUNT (mark to market).** `equity[t] = cash + shares * close[t]`. This value is
   appended to the equity curve for bar `t`.
3. **SIGNAL + ORDER.** Using closes up to and including `close[t]`, compute the target
   weight `w_t ∈ {0, target_percent}`. If `w_t` crosses the flat↔invested boundary
   versus what we currently hold, **queue an order** to be filled at the next bar's
   open (`open[t+1]`).

At the end, any still-open long position is closed at the final close for round-trip
/ win-rate reporting only (it does not change equity).

### Signal generation (MA20/MA50)

Identical *event* logic to the Backtrader `CrossOver` strategy:

- `MA_fast = SMA(close, 20)`, `MA_slow = SMA(close, 50)` (simple moving averages).
- Track `diff = MA_fast - MA_slow` once both are defined (after 50 bars).
- **cross up** (`prev_diff <= 0 < diff`) → set target `= target_percent` (go long).
- **cross down** (`prev_diff >= 0 > diff`) → set target `= 0` (go to cash).
- Between crosses the position **persists** (we only act on a crossing bar), exactly
  like Backtrader entering on `cross > 0` and exiting on `cross < 0`.

`buy_hold` is also provided: target `= target_percent` from the first bar, held to the
end.

### Explicit assumptions (no hidden defaults)

| Assumption | Value | Notes |
|---|---|---|
| Execution | fill at **next bar open** | documented convention; leak-free |
| Position cap | `target_percent = 0.95` | mirrors the demo's Backtrader `order_target_percent(0.95)` |
| Sizing | from `close[t]` (order) → fill `open[t+1]` | matches Backtrader's sizing-vs-fill split |
| Shares | **fractional allowed** | matches Backtrader's default |
| Commission | `0.001` (0.1%) of traded value | explicit |
| Slippage | `slippage_bps` haircut on fill price | explicit |
| Direction | **long-only, no shorting, no leverage** | |
| Price-band guard | `evaluate_price_band_guard(exchange, slippage_bps)` | reused from the slippage guard |

### Metric formulas (`trading_agent.backtest.metrics`)

- **total_return** `= equity[-1]/equity[0] - 1`.
- **annualized_return** `= (1 + total_return)^(365.25 / calendar_days) - 1`.
- **max_drawdown** = most negative `equity/running_peak - 1` (reported as a negative %).
- **sharpe (annualized)** `= sqrt(252) * mean(daily_returns) / sample_std(daily_returns)`,
  risk-free = 0, daily returns from the equity curve.
- **win_rate** = winning round trips / total round trips.
- **exposure** = fraction of bars holding a position.

## Comparison vs persisted Backtrader (FPT, MA20/MA50, 0 bps)

| metric | SimpleEngine | Backtrader (persisted) |
|---|---:|---:|
| final value | 392,304,486 | 392,519,583 |
| total return | 292.30% | 292.52% |
| annualized return | 25.60% | 25.62% |
| max drawdown | -22.18% | 22.14% |
| sharpe | 1.23 | 0.90 |
| closed trades | 12 | 12 |
| win rate | 58.33% | 58.33% |

**Reading the comparison:**

- **Return, drawdown, trade count, win rate match** to a fraction of a percent. The
  ~0.05% final-value gap comes from tiny sizing/fill differences (Backtrader's broker
  marks and rounds slightly differently; SimpleEngine sizes from `close[t]` and fills
  at `open[t+1]`).
- **Max drawdown** is the same magnitude; SimpleEngine reports it signed (negative),
  Backtrader reports the positive magnitude.
- **Sharpe differs (1.23 vs 0.90)** because the two use **different Sharpe
  definitions**: SimpleEngine uses `sqrt(252)·mean/std` of equity-curve daily returns;
  Backtrader's `SharpeRatio_A` annualizes differently. The return/risk *economics*
  agree; only the ratio convention differs. This is exactly the kind of black-box
  detail the SimpleEngine makes explicit.
- **Trade counting**: Backtrader counts closed `Trade` objects; SimpleEngine counts
  long round trips. Here both are 12.

## Why this reduces black-box risk

- Every number can be traced to a few lines of Python: the bar loop, the SMA, the
  fill rule, the cash/shares update, and the metric formulas — no framework internals.
- The execution convention (next-bar-open), the 95% target, commission and slippage
  are **stated, not inherited** from a library default.
- It runs on the **same adjusted `daily_prices` rows** as the persisted Backtrader
  run, so the comparison isolates *engine behavior* from *data*.
- It reproduces Backtrader's economics, which builds trust that the persisted demo
  results are sound — while making the one real divergence (Sharpe definition)
  explicit and explainable.

## Scope / caveats

- This is an **explainability baseline**, not yet a production engine: long-only, one
  instrument, no leverage/short, simple bps slippage (not a market-impact model).
- Adjusted OHLC source remains unverified/raw-equivalent → results are research-only
  (the same caveat the persisted runs carry).
- The persisted Backtrader results are **not** replaced; SimpleEngine is additive and
  for education / future custom-engine work.
