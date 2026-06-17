---
title: backtest_mvp_spec
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest MVP Specification

## Scope

This spec covers the minimum viable backtest for the current demo phase. It is rule-based only. No LLM decisions, no broker execution, no realtime data, no portfolio optimizer.

The backtest reads canonical daily prices from the existing SQLite MVP store (or a compatible replacement) and applies the current deterministic signal logic.

---

## Strategy: `mvp_ma20_ma50_momentum`

**Logic (deterministic, already implemented in `evaluate_active_signals`):**

- BUY when `close > MA20 > MA50` and `return_20d > 0`
- SELL when `close < MA20 < MA50` and `return_20d < 0`
- HOLD otherwise (including low-confidence cases with insufficient lookback)

Position sizing: long-only, flat position (fully in or fully out). No short-selling in MVP.

---

## Required Inputs

| Input | Default | Notes |
|---|---|---|
| `symbols` | `["FPT", "VNM", "VCB"]` | Must exist in the store |
| `start_date` | Earliest available | Inclusive |
| `end_date` | Latest available | Inclusive |
| `strategy_id` | `mvp_ma20_ma50_momentum` | Used as key in results |
| `cost_bps` | 20 | Round-trip brokerage cost in basis points |
| `slippage_bps` | 5 | Execution slippage per trade |
| `price_basis` | `close` | Must match `price_basis` in DB |
| `initial_capital` | 1_000_000 | VND (or any unit — ratio metrics are unit-invariant) |
| `position_sizing` | `full_equity` | All-in when signal=BUY; flat when SELL/HOLD |

---

## Required Outputs

| Output | Description |
|---|---|
| `trades` | List of `{date, symbol, action, price, cost_bps, slippage_bps}` |
| `equity_curve` | `{date, portfolio_value}` per day |
| `sharpe_ratio` | Annualised, using daily returns, risk-free=0 |
| `sortino_ratio` | Downside deviation variant |
| `profit_factor` | Gross profit / gross loss |
| `max_drawdown` | Peak-to-trough percentage |
| `win_rate` | Fraction of closed trades with positive P&L |
| `exposure_pct` | Fraction of days with non-zero position |
| `total_return_pct` | Final equity / initial capital − 1 |
| `caveats` | Data quality warnings carried through from tools |
| `not_for_live_trading` | Always `true` |

---

## Validation Gates

The backtest must refuse to run or emit an explicit `quality=fail` if any of the following are true:

1. Any row used has `quality_status=fail` (OHLC inconsistency).
2. `adjustment_status` is not `unknown` but the backtest config says `adjusted=True` — mismatch.
3. Lookback is below MA50 minimum (50 days) at the start date.
4. `source_id` or `raw_path` is missing from any row used.
5. Cost and slippage assumptions are not explicitly stated in output.
6. `price_basis` in config does not match `price_basis` in DB row.

Gate failure emits a structured dict with `status=quality_fail` and `blocking_caveats`, not a Python exception.

---

## Demo Scenario

```
backtest(
    symbols=["FPT", "VNM", "VCB"],
    strategy_id="mvp_ma20_ma50_momentum",
    cost_bps=20,
    slippage_bps=5,
    initial_capital=1_000_000,
)
```

Output must be clearly labeled:

```
## backtest_mvp_ma20_ma50_momentum — EXPLORATORY ONLY

Not for live trading. Data: saved local payloads, adjustment_status=unknown.
Results reflect rule-based logic on unvalidated historical data.
```

---

## Not in Scope

- Portfolio optimization or capital allocation across symbols.
- Live trading or order routing.
- Reinforcement learning or LLM-generated trade decisions.
- Walk-forward optimization or parameter search.
- Transaction cost modeling beyond flat bps.
- Corporate-action adjustment (blocked until adjustment engine exists).

---

## Prerequisite

The backtest reads from the existing `daily_prices` table. No new store migration is required for the MVP backtest. If the store is replaced (e.g., DuckDB), the backtest module must be adapted, but the spec and validation gates remain identical.
