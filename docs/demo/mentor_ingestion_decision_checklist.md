---
title: mentor_ingestion_decision_checklist
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Ingestion Decision Checklist

A concise, mentor-facing checklist to unblock the next ingestion phase. No
production readiness is claimed; this is not financial advice.

## Current State

- Cached OHLCV ingestion foundation (`source_runs`, `raw_source_payloads`,
  `ingestion_watermarks`; canonical prices/features/signals).
- Controlled one-symbol live OHLCV smoke succeeded (FPT/VNM/VCB tiny execute).
- Ingestion observability/status tool (read-only runs, payloads, watermarks,
  lineage, freshness, tool readiness).
- Dry-run production ingestion control planner (validates allowlist, batch cap,
  countBack, retention, and rate-limit policy with no network and no DB write).

## Decisions Needed

| Decision | Options / Notes |
|---|---|
| Approved live source | confirm the endpoint allowed for repeated use |
| Initial symbol universe | which symbols may be fetched (start small) |
| Max symbols per batch | current dry-run cap is 3 |
| Default and max countBack | current default 100 / max 5000 |
| Min seconds between requests | politeness cadence (current 2s) |
| Max batches per manual run | current 1 |
| Raw retention days | how long raw payload evidence is kept (current 30) |
| Production DB path | SQLite / DuckDB / QuestDB / Postgres |
| When scheduler is allowed | gates required before any daemon/cron |
| Backtest execution convention | same-day vs next-bar fills |

## Commands To Show Mentor

```bash
python scripts/plan_live_ingestion_run.py --symbols FPT,VNM,VCB
python scripts/plan_live_ingestion_run.py --symbols FPT,VNM,VCB,MSN
python scripts/run_ingestion_status.py --symbols FPT,VNM,VCB
```

Expected: first returns `ok`; second returns `blocked` (over batch cap); every
plan reports `network_request_made=false` and `db_mutation_made=false`.

## Boundaries

- No scheduler yet.
- No full-universe ingestion yet.
- No QuestDB yet.
- No broker execution or live trading.
- Not financial advice.
