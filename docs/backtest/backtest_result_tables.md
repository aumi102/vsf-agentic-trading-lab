# QuestDB backtest result tables

## Scope

Backtrader research results can now be persisted into QuestDB result tables for reproducibility and inspection. This is still research/demo infrastructure and is not wired into DeepAgents.

The persistence runner reads QuestDB `daily_prices`, exports Backtrader-compatible CSV files under ignored `data/cache`, runs the research strategies, and writes only `backtest_*` tables.

It does not mutate:

- `daily_prices`
- `securities`
- `feature_snapshots`
- `signals`
- any `fa_*` table

## Tables

### `backtest_runs`

One row per symbol/strategy result.

Columns:

- `created_at TIMESTAMP`
- `run_id SYMBOL`
- `symbol SYMBOL`
- `strategy_id SYMBOL`
- `strategy_name SYMBOL`
- `start_date TIMESTAMP`
- `end_date TIMESTAMP`
- `data_source SYMBOL`
- `source_table SYMBOL`
- `code_commit SYMBOL`
- `start_cash DOUBLE`
- `commission DOUBLE`
- `slippage_bps DOUBLE`
- `adjusted_price_status SYMBOL`
- `status SYMBOL`
- `caveats STRING`

### `backtest_metrics`

One metric row per symbol/strategy result.

Columns:

- `created_at TIMESTAMP`
- `run_id SYMBOL`
- `symbol SYMBOL`
- `strategy_id SYMBOL`
- `strategy_name SYMBOL`
- `start_value DOUBLE`
- `final_value DOUBLE`
- `total_return_pct DOUBLE`
- `annualized_return_pct DOUBLE`
- `max_drawdown_pct DOUBLE`
- `sharpe_ratio DOUBLE`
- `closed_trades LONG`
- `win_rate_pct DOUBLE`
- `quality_status SYMBOL`

### `backtest_equity_curve`

One row per strategy/day equity snapshot.

Columns:

- `trade_date TIMESTAMP`
- `run_id SYMBOL`
- `symbol SYMBOL`
- `strategy_id SYMBOL`
- `strategy_name SYMBOL`
- `portfolio_value DOUBLE`
- `cash DOUBLE`

### `backtest_trades`

Created for the future trade ledger. Trade-level extraction is still TODO.

Columns:

- `trade_date TIMESTAMP`
- `run_id SYMBOL`
- `symbol SYMBOL`
- `strategy_id SYMBOL`
- `event_type SYMBOL`
- `size DOUBLE`
- `price DOUBLE`
- `value DOUBLE`
- `pnl DOUBLE`
- `pnl_pct DOUBLE`

## How to run persistence

One symbol:

```bat
python scripts\run_backtrader_questdb_persist.py --symbol FPT --start-date 2020-01-01 --end-date 2025-12-31
```

Demo basket:

```bat
python scripts\run_backtrader_questdb_persist.py --symbols FPT,VNM,HPG --start-date 2020-01-01 --end-date 2025-12-31
```

Replace only backtest result tables:

```bat
python scripts\run_backtrader_questdb_persist.py --symbols FPT,VNM,HPG --start-date 2020-01-01 --end-date 2025-12-31 --replace-run-table
```

Inspect persisted results:

```bat
python scripts\questdb_backtest_status.py
```

## Difference from the notebook

The notebook is an interactive research demo. It calls the helper scripts and reads ignored CSV outputs.

The persistence runner writes a reproducible QuestDB record:

- run metadata in `backtest_runs`;
- metrics in `backtest_metrics`;
- daily equity snapshots in `backtest_equity_curve`;
- reserved trade table in `backtest_trades`.

## Current strategy coverage

- `buy_hold`
- `ma20_ma50`
- `rsi_mean_reversion`

## Why this is not wired into DeepAgents yet

Backtests should only run when a user explicitly requests backtesting, simulation, or strategy-performance analysis. Before agent exposure, the system needs routing and answer guardrails so market/financial-report prompts do not accidentally trigger backtests.

Required before DeepAgents integration:

- strategy registry and versioned parameters;
- explicit backtest intent routing;
- bounded symbol/date scope;
- result caching or persisted-result lookup behavior;
- mandatory caveat disclosure;
- no real-money advice language.

## Caveats

- Adjusted OHLC source remains unverified in current data quality checks.
- Persisted rows include `adjusted_price_status`; current demo data is expected to show `source_adjustment_unverified`.
- Commission is a simple flat broker commission parameter.
- Slippage is currently recorded as `0` bps and not modeled.
- No tax, liquidity, price-limit, corporate-action, or execution-quality model is included.
- `backtest_trades` exists but trade-level extraction is TODO.
- These results are not production strategy validation and are not investment advice.
