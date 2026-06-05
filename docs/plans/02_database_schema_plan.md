---
title: 02_database_schema_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Database Schema Plan

### Goal And Scope
<details open>
<summary>The schema plan should make future crawling and backtesting reproducible.</summary>
---
#### Goal

- Define the first set of entities before writing crawlers.
- Separate raw source metadata from normalized analytics tables.
- Support point-in-time joins for reports, macro, and financial data.
- Support tool trace and validation results from the first agent demo.

---
#### MVP schema families

- **identity** = exchanges, companies, securities, symbol history.
- **market data** = daily prices, trading calendar, market summary.
- **events** = corporate actions and event calendar.
- **documents** = reports, report chunks, report ticker links.
- **macro** = macro series and observations.
- **agent runs** = tool traces, backtest runs, validation results.

---
</details>

### Entity Plan
<details open>
<summary>Each entity should have a stable key, source linkage, and clear owner module.</summary>
---
#### Entity table

| Entity | Key | Owner module |
|---|---|---|
| `exchanges` | `exchange_id` | Data Agent. |
| `companies` | `company_id` | Schema Agent. |
| `securities` | `security_id` | Schema Agent. |
| `daily_prices` | `security_id + trade_date + source_id` | Market Data Tool. |
| `corporate_actions` | `action_id` | Data Agent. |
| `reports` | `report_id` | Evidence Tool. |
| `report_chunks` | `chunk_id` | Retrieval Tool. |
| `macro_series` | `series_id` | Macro Agent. |
| `macro_observations` | `series_id + observation_date + realtime_start` | Macro Agent. |
| `agent_runs` | `run_id` | Orchestrator. |
| `tool_traces` | `trace_id` | Trace Store. |
| `backtest_runs` | `backtest_id` | Backtest Tool. |

---
#### Required invariants

- No analytics row should exist without `source_id` or upstream `dataset_id`.
- No backtest result should exist without `strategy_config_id`, `data_version`, and `cost_config_id`.
- No report should be used for point-in-time analysis without `published_at`.
- No macro observation should be used in a historical strategy without release or vintage handling.
- QuestDB OHLCV dedup/upsert design is not finalized here; use `docs/ingestion_v2_schema_plan.md` for the current daily re-fetch and `DEDUP UPSERT KEYS` policy note.
- Per mentor clarification, MVP OHLCV storage should start as one OHLCV table/dataset with adjustment-related columns; do not split corporate actions into separate tables before the ingestion path is stable.

---
</details>

### Implementation Order
<details open>
<summary>Build the schema in the same order as the agent pipeline consumes it.</summary>
---
#### Steps

- **define identity tables** = exchanges, companies, securities, and symbol history.
- **define source tables** = source files, crawl batches, parser versions, and schema versions.
- **define market tables** = trading calendar and daily prices.
- **define feature tables** = derived indicators and feature metadata.
- **define backtest tables** = strategy config, cost config, backtest run, trades, metrics, and validation results.
- **define document tables** = reports and report chunks.
- **define trace tables** = agent runs and tool traces.

---
#### Worked example

- A user asks for `FPT` MA crossover backtest.
- `securities` maps ticker `FPT` to `security_id=sec_fpt_hose`.
- `daily_prices` loads rows for `sec_fpt_hose`.
- `backtest_runs` stores strategy version and data version.
- `tool_traces` stores every tool call.
- Read: the final answer can be reproduced because every output points back to inputs.

---
</details>

### Questions To Mentor
<details open>
<summary>The schema needs review before implementation to avoid later migration pain.</summary>
---
#### Questions

- Should schema be documented as ERD, SQL DDL, JSON schema, or all three?
- Which database should host MVP metadata: PostgreSQL, SQLite, or another option?
- Should tool traces be immutable append-only records?
- Should features be stored or recomputed for each backtest run?
- What naming convention should be used for tables and fields?

---
</details>
