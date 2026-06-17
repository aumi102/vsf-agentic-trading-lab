---
title: live_ingestion_readiness_checklist
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Live Ingestion Readiness Checklist

## Current State

- Supported live source: Vietcap IQ gap-chart OHLCV.
- Default mode: cached/offline ingestion.
- Live command requires `--mode live --allow-network`.
- Current live cap: 3 explicit symbols per run.
- Default `countBack`: 5000.
- Raw payloads and metadata are saved before parsing under ignored data paths.
- The same parser, canonical upsert, feature refresh, signal refresh, watermark,
  and quality report flow is reused after live fetch.

## Required Decisions Before Expansion

| Decision | Needed Before |
|---|---|
| Approved live data source | relying on live data beyond smoke checks |
| Allowed symbol universe | any broad symbol ingestion |
| Scheduler cadence | daemon, cron, or recurring fetch work |
| Raw retention policy | keeping or pruning live payload evidence |
| Production DB path: SQLite/DuckDB/QuestDB/Postgres | production-scale storage design |
| Rate limit / politeness policy | repeated live ingestion |
| Next-bar execution convention | stronger backtest assumptions |
| Adjusted/unadjusted price handling | production-quality prices and returns |

## Guardrails

- Do not run a full-universe crawl from this adapter.
- Do not add a scheduler or daemon until cadence and source permission are
  agreed.
- Do not commit generated SQLite DBs or raw payloads.
- Do not treat the adapter as production-ready ingestion.
- Do not claim investment advice or production trading readiness.

## Next Step

Mentor should confirm the live source reliability, symbol universe, raw
retention policy, and production DB direction before expanding beyond controlled
small-symbol live smoke runs.
