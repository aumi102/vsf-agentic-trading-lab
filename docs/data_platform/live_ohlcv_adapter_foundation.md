---
title: live_ohlcv_adapter_foundation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Live OHLCV Adapter Foundation

## Purpose

This adds a controlled live adapter for Vietcap IQ gap-chart OHLCV payloads. It
is a small, explicit bridge into the existing ingestion pipeline:

```text
explicit live fetch
-> save raw payload + metadata under ignored data/raw/
-> record source_runs + raw_source_payloads
-> parse/normalize
-> upsert daily_prices
-> refresh feature_snapshots/signals
-> update ingestion_watermarks
-> quality report
```

Default ingestion remains cached/offline. Live mode requires
`--mode live --allow-network`.

## Commands

Cached mode remains the normal offline path:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT,VNM,VCB --mode cached
```

Live mode is explicit and limited:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT --mode live --allow-network --count-back 100
```

The live adapter rejects more than three symbols per run. There is no override
in this PR.

## Adapter Contract

Module:

```text
src/trading_agent/ingestion/sources/vietcap_iq_gap_chart.py
```

The adapter writes `payload.json` and `metadata.json` before parsing. Metadata
includes source name, symbol, request parameters, `crawled_at`/`fetched_at`,
content hash, row count, status, and caveats. It does not store secrets, cookies,
or auth tokens.

The adapter reuses the same endpoint/request/header shape as the existing
controlled fetch script. It stays sequential and small-batch only.

## Boundaries

- No full-universe crawl.
- No scheduler or daemon.
- No QuestDB implementation.
- No broker execution, live trading, shorting, or portfolio optimization.
- No LLM-generated decisions.
- Raw payloads and generated SQLite DBs stay under ignored paths.
- Exploratory data infrastructure only; not production-ready and not financial advice.

## Next Decision

Mentor should confirm live source reliability, acceptable symbol universe, and
production DB path before scheduler work, full-universe ingestion, or QuestDB.
