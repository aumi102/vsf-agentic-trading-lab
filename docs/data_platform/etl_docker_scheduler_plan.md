---
title: etl_docker_scheduler_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# ETL Docker Scheduler Plan

## Purpose

This plan captures the mentor direction to prioritize stable DB/ETL automation
before experimental strategy work. The first Docker target should be ingestion,
status, and control tooling that already exists and has deterministic behavior.

This is a plan only. No scheduler is enabled by this document.

## Stable Components Eligible For Docker

- DB build: `scripts/build_mvp_db.py`
- Cached/live ingestion: `scripts/run_ohlcv_ingestion.py`
- Ingestion status: `scripts/run_ingestion_status.py`
- Production ingestion planner: `scripts/plan_live_ingestion_run.py`

Live ingestion must remain gated by explicit configuration and the existing
allowlist/rate-limit controls.

## Components Not Eligible Yet

- Experimental Backtrader optimizer.
- LLM or UI wiring.
- QuestDB or realtime ingestion.
- Broker execution or live trading.

Only stable components should be Dockerized.

## Proposed Docker Artifacts

A future implementation PR can add:

- `Dockerfile.etl`
- `docker-compose.etl.yml`
- `.env.example`
- scheduled entrypoint script

The image should run with mounted data/config directories so generated SQLite
files, raw payloads, logs, and temp outputs are not committed.

## Scheduler Modes

The scheduled entrypoint should support:

- `--once`
- `--schedule-interval-minutes`
- `--max-cycles`

Scheduled mode must be disabled by default. A dry-run plan should be available
before starting any loop.

## Guardrails

The scheduler must enforce:

- configured symbol allowlist;
- max batch size;
- max `countBack`;
- rate-limit/politeness policy;
- raw retention policy;
- status reporting after each cycle;
- no full-universe crawl by default;
- no network in cached mode;
- explicit opt-in for live mode.

Failures should produce clear logs and non-traceback statuses where possible.
Status output should remain compatible with `run_ingestion_status.py`.

## Next Step

Implement a minimal ETL container and disabled-by-default scheduler wrapper only
after adjusted OHLC requirements and ingestion guardrails are reviewed.
