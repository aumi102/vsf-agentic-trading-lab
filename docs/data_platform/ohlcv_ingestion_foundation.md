---
title: ohlcv_ingestion_foundation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# OHLCV Ingestion Foundation

## Purpose

This adds the first real DB/ingestion foundation on top of the local SQLite MVP
store. The previous demo path rebuilt `data/demo/mvp_trading_agent.sqlite` from
saved Vietcap IQ gap-chart payloads. The new path records ingestion runs, raw
payload metadata, canonical refreshes, feature refreshes, signal refreshes, and
a compact data quality report.

This is still exploratory infrastructure. It is not production-grade ingestion,
not live trading, not broker execution, and not investment advice.

## Flow

```text
cached payload
-> source_runs
-> raw_source_payloads
-> parse/normalize
-> upsert securities + daily_prices
-> refresh feature_snapshots
-> refresh signals
-> quality report
```

## Tables

The canonical tables remain:

- `securities`
- `daily_prices`
- `feature_snapshots`
- `signals`

The ingestion foundation adds:

- `source_runs`: run id, source, mode, status, symbols, network flag, caveats.
- `raw_source_payloads`: source, symbol, run id, timestamp, content hash, raw
  path, metadata path, logical path, row count, and status.
- `ingestion_watermarks`: latest usable trade date and row count by source and
  symbol.

Canonical `daily_prices` rows retain `source_id` and `raw_path`. Failed OHLC
rows can remain visible in `daily_prices`, but feature and signal refreshes read
only rows where `quality_status != 'fail'`.

## CLI

Cached mode is offline and deterministic:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT,VNM,VCB --mode cached
python scripts/run_ohlcv_ingestion.py --symbols FPT,VNM,VCB --mode cached --refresh-features --refresh-signals
```

Live mode is gated and not implemented in this foundation PR:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT --mode live
python scripts/run_ohlcv_ingestion.py --symbols FPT --mode live --allow-network
```

Without `--allow-network`, live mode returns a clear error and makes no network
request. With `--allow-network`, it still returns a clear not-implemented error
until the mentor confirms the live source and production DB path.

## Boundaries

- No new source discovery or network crawl.
- No QuestDB implementation yet.
- No LLM-generated decisions.
- No broker execution, live trading, shorting, or portfolio optimization.
- Generated SQLite DB files and raw payload files stay under ignored `data/`.

## Next Decision

Mentor should confirm the live data source and production DB direction
(SQLite/DuckDB/QuestDB/Postgres) before full live ingestion, scheduler work, or
QuestDB migration.
