---
title: backtest_mvp_demo
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest MVP Demo

## Scope

This page documents the exploratory Backtest MVP scaffold for the local agent demo. It is deterministic, reads only the cached SQLite MVP store, and does not use LLM decisions, broker execution, live trading, QuestDB, or network fetches.

This is not a production backtest and not financial advice.

---

## Strategy

Strategy id: `mvp_ma20_ma50_momentum`.

The scaffold reuses the existing `signals` table generated from the MA20/MA50 momentum rule:

- `BUY` opens or keeps a long position.
- `SELL` exits to cash.
- `HOLD` keeps the current state.
- `HOLD_WITH_LOW_CONFIDENCE` does not open a new position.

The MVP is long/cash only. It never shorts and never routes orders.

---

## Data And Assumptions

Default data source:

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

The backtest reads `daily_prices`, `feature_snapshots`, and `signals` from `data/demo/mvp_trading_agent.sqlite`.

Default assumptions:

| Setting | Default |
|---|---:|
| Initial capital | `100000000` |
| Transaction cost | `0.001` |
| Slippage | `0.0005` |
| Price basis | Reported from the store |
| Execution convention | Same-day close for MVP only |

The same-day close convention is an explicit caveat. A production backtest must use a stricter next-bar executable price convention.

Rows with `quality_status=fail` are excluded. The output reports whether source lineage (`source_id`, `raw_path`) is present. `adjustment_status=unknown` remains a corporate-action caveat.

---

## CLI

```bash
python scripts/run_backtest_demo.py --symbols FPT,VNM,VCB --strategy-id mvp_ma20_ma50_momentum
python scripts/run_backtest_demo.py --symbols FPT --start-date 2020-01-01 --end-date 2026-06-05
python scripts/run_backtest_demo.py --symbols HPG --strategy-id mvp_ma20_ma50_momentum
```

The CLI prints a JSON summary, a compact metrics table, and caveats. Missing DB and all-missing-symbol paths return nonzero status without a traceback.

---

## Outputs

The engine returns:

- `status`
- `strategy_id`
- `symbols`, `symbols_found`, `symbols_missing`
- `start_date`, `end_date`
- `assumptions`
- `metrics`
- `trades`
- `equity_curve`
- `validation_gates`
- `caveats`
- `not_financial_advice=True`

Metrics include total return, annualized return when feasible, Sharpe, Sortino, profit factor, max drawdown, win rate, trade count, and exposure. Metrics that cannot be computed reliably return `None` with a caveat.

---

## Remaining Hardening

Production DB/backtest work is still pending. Before expanding the universe or adding QuestDB/LLM layers, mentor review must confirm the store decision, symbol universe, cost/slippage assumptions, and execution convention.
