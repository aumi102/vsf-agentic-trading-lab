---
title: backtest_mvp_spec
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest MVP Specification

## Scope

This spec covers the minimum viable backtest scaffold for the current demo phase. It is rule-based only. No LLM decisions, no broker execution, no realtime data, no portfolio optimizer.

The scaffold reads cached `daily_prices`, `feature_snapshots`, and `signals` from the existing SQLite MVP store and applies the current deterministic signal logic. It is exploratory only and not financial advice.

---

## Strategy: `mvp_ma20_ma50_momentum`

**Logic (deterministic, already implemented in `evaluate_active_signals`):**

- BUY when `close > MA20 > MA50` and `return_20d > 0`
- SELL when `close < MA20 < MA50` and `return_20d < 0`
- HOLD otherwise
- HOLD_WITH_LOW_CONFIDENCE does not open a new position

Position sizing: long-only, cash or fully long per symbol allocation. No short-selling in MVP.

---

## Required Inputs

| Input | Default | Notes |
|---|---|---|
| `symbols` | `["FPT", "VNM", "VCB"]` | Must exist in the store |
| `start_date` | Earliest available | Inclusive |
| `end_date` | Latest available | Inclusive |
| `strategy_id` | `mvp_ma20_ma50_momentum` | Used as key in results |
| `transaction_cost` | 0.001 | Fractional cost per trade |
| `slippage` | 0.0005 | Fractional slippage per trade |
| `price_basis` | Store-reported | Reported in output |
| `initial_capital` | 100_000_000 | VND or any unit; ratio metrics are unit-invariant |
| `position_sizing` | per-symbol allocation | All-in per symbol when signal=BUY; flat when SELL |

---

## Required Outputs

| Output | Description |
|---|---|
| `trades` | List of `{date, symbol, action, price, fill_price, transaction_cost, slippage}` |
| `equity_curve` | `{date, portfolio_value}` per day |
| `sharpe` | Annualized, using daily returns, risk-free=0 |
| `sortino` | Downside deviation variant |
| `profit_factor` | Gross profit / gross loss |
| `max_drawdown` | Peak-to-trough percentage |
| `win_rate` | Fraction of closed trades with positive P&L |
| `exposure` | Fraction of days with non-zero position |
| `total_return` | Final equity / initial capital minus 1 |
| `caveats` | Data quality warnings carried through from tools |
| `not_financial_advice` | Always `true` |

Metrics that cannot be computed reliably return `None` with a caveat.

---

## Validation Gates

The backtest emits validation gates and returns a structured non-OK status if a blocking gate fails:

1. The SQLite store exists.
2. Requested symbols exist in the store.
3. Usable rows exist in the requested date range.
4. Rows with `quality_status=fail` are excluded.
5. `source_id` and `raw_path` are present on rows used.
6. At least 50-day lookback is available for the requested window.
7. Cost and slippage assumptions are explicitly stated in output.
8. Price basis is reported in the assumptions.
9. `adjustment_status` is carried through with an explicit corporate-action caveat.
10. Same-day close execution is labeled as an MVP leakage caveat; production must use a stricter next-bar convention.

If only some requested symbols are missing, the run returns `status=ok` for the found symbols, reports `symbols_missing`, and marks `symbols_exist` as `warn`. If a requested date range has no usable rows, the run returns `status=not_found`, not a Python exception.

---

## Demo Scenario

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
python scripts/run_backtest_demo.py --symbols FPT,VNM,VCB --strategy-id mvp_ma20_ma50_momentum
```

Output must be clearly labeled:

```text
backtest_mvp_ma20_ma50_momentum - EXPLORATORY ONLY
Not for live trading. Data: saved local payloads, adjustment_status may be unknown.
Results reflect rule-based logic on unvalidated historical data.
```

---

## Not in Scope

- Portfolio optimization.
- Live trading or order routing.
- Reinforcement learning or LLM-generated trade decisions.
- Walk-forward optimization or parameter search.
- Transaction cost modeling beyond flat fractional assumptions.
- Corporate-action adjustment, blocked until an adjustment engine exists.

---

## Prerequisite

The backtest reads from the existing SQLite MVP store. No new store migration is required for the MVP scaffold. If the store is replaced, for example with DuckDB, the module must be adapted, but the validation gates remain the same.
