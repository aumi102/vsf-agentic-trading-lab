---
title: production_ingestion_control_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Production Ingestion Control Plan

## Purpose

This adds a control layer before any scheduler, full-universe ingestion, or
QuestDB work. It is a dry-run planning step that validates a small allowlist,
batch limits, countBack, and rate-limit policy without fetching network data or
mutating a database.

## Files

- `configs/ingestion/live_symbols_mvp.json`: MVP live allowlist and default
  symbols.
- `configs/ingestion/rate_limit_policy.json`: manual-run politeness policy.
- `scripts/plan_live_ingestion_run.py`: dry-run planner.

## Commands

```bash
python scripts/plan_live_ingestion_run.py --symbols FPT,VNM,VCB
python scripts/plan_live_ingestion_run.py --symbols FPT,VNM,VCB,MSN
python scripts/plan_live_ingestion_run.py --config configs/ingestion/live_symbols_mvp.json
```

Expected behavior:

- valid allowlisted symbols at or below the batch cap return `status=ok`;
- more than three symbols return `status=blocked`;
- unknown symbols return `status=blocked`;
- every result includes `network_request_made=false` and `db_mutation_made=false`.

## Decisions Required Before Expansion

See the mentor-facing checklist at
`docs/demo/mentor_ingestion_decision_checklist.md` for the full decision list and
commands to run during the mentor session.

| Decision | Why it matters |
|---|---|
| verified live source | confirms which endpoint is allowed for repeated use |
| symbol universe | prevents accidental full-universe crawl |
| rate-limit/politeness policy | controls request cadence before scheduler work |
| raw retention policy | defines how long payload evidence is kept |
| production DB path | chooses SQLite/DuckDB/QuestDB/Postgres before scaling |
| scheduler readiness gates | prevents daemon work before controls are approved |
| backtest execution convention | same-day vs next-bar fills before hardening |

## Boundaries

- No network request.
- No DB mutation.
- No scheduler or daemon.
- No full-universe ingestion.
- No QuestDB implementation.
- No broker execution, live trading, LLM reasoning, or backtest expansion.
- Not production-ready and not financial advice.
