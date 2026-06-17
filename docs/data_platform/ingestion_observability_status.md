---
title: ingestion_observability_status
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Ingestion Observability Status

## Purpose

This adds a read-only status layer for the local SQLite DB and OHLCV ingestion
foundation. It answers whether the store exists, has auditable source runs,
retains raw lineage, has watermarks, and is ready for deterministic tools.

This is not production monitoring, not live trading, and not financial advice.

## Commands

Inspect the default demo DB:

```bash
python scripts/run_ingestion_status.py
```

Inspect a symbol subset:

```bash
python scripts/run_ingestion_status.py --symbols FPT,VNM,VCB
```

Inspect an explicit DB path:

```bash
python scripts/run_ingestion_status.py --db-path data/demo/mvp_trading_agent.sqlite
```

## What It Reads

- `source_runs`
- `raw_source_payloads`
- `ingestion_watermarks`
- `securities`
- `daily_prices`
- `feature_snapshots`
- `signals`

The command does not fetch data and does not write to the store.

## Output

The API returns a stable dictionary with:

- `status`: `ok`, `missing_store`, `empty_store`, or `quality_warn`
- latest source runs, sorted newest first
- watermarks by source and symbol
- table counts
- symbol date ranges and failed OHLC row counts
- lineage count for `daily_prices` rows missing `source_id` or `raw_path`
- freshness summary and stale symbols
- readiness for market data, features, signals, and backtest tools

The CLI prints the JSON summary plus compact tables for counts, runs,
watermarks, and freshness.

## Mentor Use

Run this before trusting demo or backtest output. A DB built by
`build_mvp_db.py` can have `tool_readiness=ok` but `status=quality_warn` because
it may have no `source_runs` or `ingestion_watermarks`. A DB updated by
`run_ohlcv_ingestion.py` should show source runs, raw payload rows, watermarks,
and `status=ok` when lineage is complete.

`tool_readiness=ok` only means the local deterministic tools have enough rows to
answer. It does not mean production-grade ingestion, source approval, or
freshness guarantees.

## Boundaries

- Read-only status reporting only.
- No scheduler, daemon, or network fetch.
- No QuestDB implementation.
- No broker execution, live trading, shorting, or portfolio optimization.
- Production monitoring remains blocked pending mentor decisions on DB path,
  ingestion cadence, rate limits, and raw retention.
