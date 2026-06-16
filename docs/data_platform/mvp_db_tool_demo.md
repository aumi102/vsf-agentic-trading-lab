---
title: mvp_db_tool_demo
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# MVP DB Tool Demo

## Purpose

This branch starts the local data/tool layer needed for an agent demo. It does
not implement production trading, broker execution, QuestDB, full-history
ingestion, or backtesting. The goal is a deterministic local flow:

```text
saved raw OHLCV -> SQLite MVP store -> features -> rule signal -> risk -> Vietnamese answer
```

## Storage Choice

The MVP store uses SQLite at `data/demo/mvp_trading_agent.sqlite`. SQLite is in
the Python standard library, avoids new infrastructure, and supports stable tool
queries. Generated DB files stay under ignored `data/`.

## Tables

| Table | Role | Key |
|---|---|---|
| `securities` | symbol identity and lineage | `security_id` |
| `daily_prices` | canonical daily OHLCV rows | `security_id + trade_date + source_id` |
| `feature_snapshots` | return, MA, volatility, volume features | `security_id + as_of_date + feature_version` |
| `signals` | deterministic strategy outputs | `security_id + as_of_date + strategy_id + signal_version` |

All rows retain `source_id`, `raw_path`, and `quality_status`. Failed OHLC rows
remain visible in `daily_prices`, but features and signals are computed only
from non-fail price rows.

## Build And Demo

Available local saved gap-chart payloads: `FPT`, `VNM`, `VCB`, `REE`, `SAM`.
The default demo uses `FPT,VNM,VCB` because existing docs already validated
their countBack=5000 coverage.

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
python scripts/demo_agent_tools.py --symbol FPT
```

The build prints available symbols, loaded symbols, row counts, date ranges,
quality counts, and the SQLite output path.

## Tools

- `get_latest_market_data(symbol)`
- `compute_latest_features(symbol)`
- `evaluate_active_signals(symbol)`
- `assess_symbol_risk(symbol)`
- `compose_market_answer(symbol, language="vi")`

The signal is deterministic: BUY when `close > ma_20 > ma_50` and
`return_20d > 0`; SELL when `close < ma_20 < ma_50` and `return_20d < 0`; HOLD
otherwise. Insufficient lookback returns `HOLD_WITH_LOW_CONFIDENCE`.

## Current Demo Result

Local build on `FPT,VNM,VCB` produced 3 securities, 14,079 daily price rows,
14,071 feature snapshots, and 14,071 signals. Eight historical OHLC rows failed
quality checks and were excluded from features/signals. For FPT, the latest
demo answer status is OK and the signal is HOLD.

## Limitations

- Source is saved local Vietcap IQ gap-chart payloads, not a fresh official
  exchange feed.
- Adjustment/corporate-action basis remains unknown.
- No trading calendar, corporate actions, real-time feed, broker execution, or
  backtest is implemented.
- No production DB, QuestDB schema, full universe ingestion, or live tool
  routing is implemented.
