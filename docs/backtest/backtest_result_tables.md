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
- `scenario_label SYMBOL`
- `price_band_status SYMBOL`
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
- `slippage_bps DOUBLE`
- `scenario_label SYMBOL`
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
- `scenario_label SYMBOL`
- `portfolio_value DOUBLE`
- `cash DOUBLE`

### `backtest_trades`

One row per closed Backtrader trade event where the strategy closes a position.
This is an aggregate closed-trade event ledger, not a full entry/exit fill ledger.

Columns:

- `trade_date TIMESTAMP`
- `run_id SYMBOL`
- `symbol SYMBOL`
- `strategy_id SYMBOL`
- `scenario_label SYMBOL`
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

Run the current demo slippage scenarios:

```bat
python scripts\run_backtrader_questdb_persist.py --symbols FPT,VNM,HPG --start-date 2020-01-01 --end-date 2025-12-31 --replace-run-table --slippage-scenarios-bps 0,5,10,15
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
- closed-trade event rows in `backtest_trades`.
- scenario metadata in `slippage_bps` and `scenario_label`.

## Current strategy coverage

- `buy_hold`
- `ma20_ma50`
- `rsi_mean_reversion`

## Current slippage scenario coverage

The latest demo run persists 3 symbols x 3 strategies x 4 slippage scenarios:

- symbols: FPT, VNM, HPG;
- slippage scenarios: 0, 5, 10, 15 bps;
- `backtest_runs`: 36;
- `backtest_metrics`: 36;
- `backtest_equity_curve`: 53,964;
- `backtest_trades`: 400.

All current demo scenario rows have `price_band_status=price_band_guard_pass`.
Agent/backtest comparison defaults remain stable because lookup tools prefer
`slippage_bps=0.0` unless a slippage scenario is explicitly requested.

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
- Slippage is explicit in `slippage_bps`; default demo runs use `0` bps.
- `price_band_status` records whether slippage is within known exchange bands:
  - HOSE/HSX: 700 bps;
  - HNX: 1000 bps;
  - UPCOM: 1500 bps.
- Exchange metadata has been expanded from captured Vietcap IQ universe and HOSE listed-universe dry-run evidence. Current `securities` coverage is 1,556/1,556 symbols, with no source conflicts detected in the generated override file.
- Current demo persisted runs show `price_band_guard_pass` for FPT/VNM/HPG.
- Broader universe exchange metadata should not be assumed complete unless source-backed.
- No tax, liquidity, corporate-action, or full execution-quality model is included.
- `backtest_trades` captures closed trade events; Backtrader does not expose every normalized entry/exit field in this first version.
- These results are not production strategy validation and are not investment advice.

Optional slippage guard checks:

```bat
python scripts\check_price_band_guard.py --symbols FPT,VNM,HPG --slippage-bps 5
python scripts\check_price_band_guard.py --symbols FPT,VNM,HPG --slippage-bps 10
python scripts\check_price_band_guard.py --symbols FPT,VNM,HPG --slippage-bps 15
```
