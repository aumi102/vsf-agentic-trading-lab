# Backtrader QuestDB strategy notebook plan

## What was added

- `scripts/export_questdb_ohlcv_for_backtrader.py`
  - Read-only export from QuestDB `daily_prices`.
  - Writes Backtrader-compatible CSV files under `data/cache`.
  - Uses adjusted OHLC columns when available.
  - Prints caveats when adjusted values appear equal to raw values or `adjustment_status` includes `adjusted_price_missing_warn`.

- `scripts/run_backtrader_questdb_demo.py`
  - Exports QuestDB OHLCV first, then runs Backtrader strategies.
  - Prints a comparison table.
  - Writes ignored research outputs:
    - `data/cache/backtrader/backtrader_summary.csv`
    - `data/cache/backtrader/backtrader_equity_curves.csv`

- `notebooks/backtrader_questdb_strategy_demo.ipynb`
  - Research/demo notebook for FPT, VNM, and HPG.
  - Calls the helper scripts so notebook logic stays reproducible on Windows.

- `requirements-research.txt`
  - Minimal research-only dependency list containing `backtrader`.

## How to run

Install the research dependency in the active environment:

```bat
pip install -r requirements-research.txt
```

Export one symbol:

```bat
python scripts\export_questdb_ohlcv_for_backtrader.py --symbol FPT --start-date 2020-01-01 --end-date 2025-12-31 --out data/cache/backtrader_FPT.csv
```

Run one-symbol strategy comparison:

```bat
python scripts\run_backtrader_questdb_demo.py --symbol FPT --start-date 2020-01-01 --end-date 2025-12-31
```

Run the demo basket:

```bat
python scripts\run_backtrader_questdb_demo.py --symbols FPT,VNM,HPG --start-date 2020-01-01 --end-date 2025-12-31
```

Open the notebook:

```bat
jupyter notebook notebooks\backtrader_questdb_strategy_demo.ipynb
```

## Data source

The only database source is QuestDB `daily_prices`. The export helper performs read-only `SELECT` queries and does not mutate QuestDB.

Exported CSV schema:

- `datetime`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `openinterest`

The helper validates:

- `high >= max(open, close)`
- `low <= min(open, close)`
- `volume >= 0`

## Strategies

1. Buy and Hold baseline.
2. MA20/MA50 crossover.
3. RSI mean reversion.

## Metrics

The runner reports:

- start value
- final value
- total return
- annualized return
- max drawdown
- Sharpe ratio when Backtrader can compute it
- closed trades
- win rate when closed trades exist

## Persisted result tables

The research runner now has a companion persistence script that stores reproducible outputs in QuestDB `backtest_*` tables:

```bat
python scripts\run_backtrader_questdb_persist.py --symbols FPT,VNM,HPG --start-date 2020-01-01 --end-date 2025-12-31 --replace-run-table
python scripts\questdb_backtest_status.py
```

See `docs/backtest/backtest_result_tables.md` for schemas, caveats, and the DeepAgents integration gate.

## Caveats

- Adjusted OHLC fields are still source-unverified in the current data quality audit.
- Many exported rows currently show adjusted values equal to raw values and/or `adjusted_price_missing_warn`.
- This notebook is research/demo only.
- Backtrader is not wired into DeepAgents in this task.
- Generated CSVs and summaries are under ignored `data/cache` paths and should not be committed.
- Results are not investment advice and do not include realistic slippage, liquidity, corporate action validation, or tax modeling.

## Next production steps

- Persist research outputs to dedicated tables:
  - `backtest_runs`
  - `backtest_metrics`
  - `backtest_trades`
- Add a strategy registry with versioned parameters.
- Add reproducibility metadata: data run, code commit, start/end dates, adjusted-price caveat state.
- Add slippage/commission/liquidity assumptions per market.
- Add guardrails before exposing backtests to DeepAgents:
  - require explicit backtest intent
  - require symbol/date/strategy scope
  - prohibit real-money advice language
  - state data caveats and assumptions in every answer
