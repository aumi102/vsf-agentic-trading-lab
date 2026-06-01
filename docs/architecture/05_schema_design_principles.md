---
title: 05_schema_design_principles
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Schema Design Principles

### Key Terms
<details open>
<summary>Schemas are the contract that stops crawled data from becoming messy.</summary>
---
#### Schema terms

| Term | Meaning |
|---|---|
| `entity` | A real object such as company, security, report, macro series, or backtest run. |
| `primary key` | The field or fields that uniquely identify one row. |
| `foreign key` | A reference from one entity to another. |
| `security_id` | A stable ID for a traded instrument, safer than relying only on ticker. |
| `as_of_date` | The date at which a fact was known or valid. |
| `effective_date` | The date an event changes the market object, such as ex-dividend date. |
| `source_id` | A reference to the source file, API response, or document. |
| `schema_version` | A version number that records the field layout used when data was written. |

---
#### Why ticker alone is not enough

- A ticker can change after listing changes, mergers, or exchange events.
- A ticker can be reused or interpreted differently across exchanges and vendors.
- A stable `security_id` lets the system keep the same instrument identity even if the display ticker changes.

---
</details>

### Core Entities
<details open>
<summary>The schema should separate identity, observations, documents, events, and runs.</summary>
---
#### Identity tables

| Table | Primary key | Purpose |
|---|---|---|
| `exchanges` | `exchange_id` | Stores HOSE, HNX, UPCOM, and other venues. |
| `companies` | `company_id` | Stores issuer-level facts such as legal name and industry. |
| `securities` | `security_id` | Stores listed instruments such as common shares, ETFs, or bonds. |
| `symbol_history` | `security_id + start_date` | Maps tickers to securities through time. |

---
#### Observation tables

| Table | Primary key | Purpose |
|---|---|---|
| `daily_prices` | `security_id + trade_date + source_id` | Stores OHLCV and value by day. |
| `intraday_bars` | `security_id + timestamp + interval + source_id` | Stores minute or tick-derived bars. |
| `macro_observations` | `series_id + observation_date + vintage_date` | Stores macro values with revision safety. |
| `bond_auctions` | `auction_id` | Stores government bond auction results. |

---
#### Document and event tables

| Table | Primary key | Purpose |
|---|---|---|
| `reports` | `report_id` | Stores metadata for Vietcap, company, industry, and macro reports. |
| `report_chunks` | `chunk_id` | Stores text chunks for retrieval and embeddings. |
| `corporate_actions` | `action_id` | Stores dividends, splits, rights issues, and listing events. |
| `events_calendar` | `event_id` | Stores earnings dates, shareholder meetings, and macro release dates. |

---
#### Run tables

| Table | Primary key | Purpose |
|---|---|---|
| `agent_runs` | `run_id` | Stores one user request and final state. |
| `tool_traces` | `trace_id` | Stores tool input, output, status, and error. |
| `backtest_runs` | `backtest_id` | Stores strategy config, data version, cost config, and metrics. |
| `validation_results` | `validation_id` | Stores gate status and failure reasons. |

---
</details>

### Design Rules
<details open>
<summary>Every schema decision should protect reproducibility and point-in-time correctness.</summary>
---
#### Required fields

- Every crawled row should include `source_id`.
- Every derived row should include `created_at` and `pipeline_version`.
- Every feature row should include `feature_timestamp` and `lookback_window`.
- Every document row should include `published_at`, `crawled_at`, and `source_url` when available.
- Every final metric should include `data_version`, `strategy_version`, and `cost_config_id`.

---
#### Point-in-time rules

- A strategy running on `2024-06-01` must not use a report published on `2024-06-10`.
- A macro value must use the release date or vintage date, not only the observation month.
- A financial statement should be joined by announcement date, not fiscal quarter alone.
- A corporate action should separate declaration date, ex-date, record date, and payment date.

---
#### Worked example

- `FPT` has a report with `published_at=2024-08-15`.
- A backtest trade on `2024-08-10` cannot use that report.
- A trade on `2024-08-20` can use that report only if the report was already crawled or known by that date.
- The schema therefore needs both `published_at` and `crawled_at`.
- The read is simple: date fields are not admin detail; they prevent data leakage.

---
</details>

### Quality Gates And Questions
<details open>
<summary>A schema is incomplete until its validation gates are defined.</summary>
---
#### Validation gates

| Gate | Failure example | Consequence |
|---|---|---|
| unique key | duplicate `security_id + trade_date` | reject data load. |
| unit check | volume stored as lots in one source and shares in another | normalize or warn. |
| timestamp check | report has no publish date | cannot use for point-in-time backtest. |
| corporate action check | price not adjusted around split | block return calculation. |
| source check | row has no `source_id` | block production use. |
| schema version check | parser writes unknown column set | quarantine batch. |

---
#### Questions to ask mentor

- Should the MVP implement `security_id` from the start or use ticker first and migrate later?
- Which corporate actions must be supported before backtesting VN stocks?
- Should report retrieval require document chunks and embeddings in the first version?
- Should macro series store vintage dates from the beginning?
- What schema artifacts should be reviewed by mentor: ERD, table list, JSON schema, or sample rows?

---
</details>
