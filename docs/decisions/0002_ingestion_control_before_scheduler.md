---
title: 0002_ingestion_control_before_scheduler
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# ADR-0002: Ingestion Control Before Scheduler

## Status

Accepted for MVP planning.

## Context

The project now has cached OHLCV ingestion, a controlled live adapter, and
read-only ingestion observability. The next risk is accidentally expanding from
small explicit live runs into scheduler or full-universe behavior before source,
rate-limit, retention, and database decisions are agreed.

## Decision

Add a dry-run control layer before scheduler/full live ingestion:

- maintain an explicit MVP symbol allowlist;
- validate max symbols per batch;
- validate `countBack`;
- validate rate-limit/politeness settings;
- print planned batches and estimated raw paths;
- state clearly that no network request or DB mutation was made.

## Consequences

This keeps the next step reviewable by mentor before any recurring live
ingestion. It also gives a concrete contract for approving source reliability,
symbol universe, raw retention, and production DB path.

This ADR does not approve scheduler work, full-universe ingestion, QuestDB,
broker execution, live trading, LLM reasoning, or production readiness.
