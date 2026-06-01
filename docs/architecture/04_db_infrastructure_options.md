---
title: 04_db_infrastructure_options
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## DB Infrastructure Options

### Key Terms
<details open>
<summary>Database choices should follow data shape and query pattern.</summary>
---
#### Storage terms

| Term | Meaning |
|---|---|
| `time-series DB` | A database optimized for rows indexed by time, such as OHLCV, trades, and order book snapshots. |
| `OLAP` | Analytical database design for scanning many rows and aggregating quickly. |
| `object storage` | Cheap storage for files such as raw CSV, JSON, PDF, HTML, and Parquet. |
| `metadata DB` | A relational store for symbols, exchanges, sectors, reports, and run records. |
| `cache` | Fast temporary storage for latest data, sessions, and repeated queries. |
| `vector DB` | A database that stores embeddings for semantic search over reports, news, and notes. |
| `message queue` | A system that buffers crawl, parse, and compute jobs. |

---
#### Candidate technologies

| Family | Candidate | Main use |
|---|---|---|
| time-series | QuestDB | OHLCV, intraday bars, trades. |
| relational | PostgreSQL | metadata, schemas, runs, results. |
| object storage | S3-compatible storage | raw files and Parquet datasets. |
| document | MongoDB | flexible JSON reports, traces, raw parsed objects. |
| vector | Qdrant | semantic retrieval over reports and news. |
| cache | Redis | latest values, sessions, queues. |
| OLAP | DuckDB or ClickHouse | local analytics or large scans. |

---
</details>

### Mapping By Data Family
<details open>
<summary>Each data family should have one primary home and one audit path.</summary>
---
#### Market time-series

- **shape** = `symbol + timestamp + OHLCV + source_id`.
- **primary home** = time-series DB or partitioned Parquet.
- **query pattern** = load one symbol across years, load universe across one date, aggregate daily to weekly, compute rolling windows.
- **audit path** = raw file in object storage plus row-level `source_id`.
- **read** = this data feeds TA, features, backtest, and risk modules.

---
#### Reports and news

- **shape** = document metadata plus full text, PDF path, summary, tags, ticker links, and embedding ID.
- **primary home** = object storage for raw PDFs, metadata DB for fields, vector DB for semantic retrieval.
- **query pattern** = find reports about `FPT`, find industry reports, retrieve evidence related to price movement.
- **audit path** = raw PDF path, crawl time, source URL, parser version.
- **read** = this data feeds FA, macro, evidence, and answer-composer modules.

---
#### Tool traces

- **shape** = run ID, tool name, input JSON, output JSON, status, error code, latency, and timestamp.
- **primary home** = document DB or relational JSON column.
- **query pattern** = debug a run, reproduce a result, compare tool outputs across versions.
- **audit path** = immutable run record.
- **read** = this data feeds mentor review, QA, and future evaluation.

---
#### Macro and bond data

- **shape** = series ID, date, value, frequency, unit, vintage, and source.
- **primary home** = relational or time-series storage.
- **query pattern** = align monthly macro data to daily market data without leaking future values.
- **audit path** = source release date and vintage timestamp.
- **read** = this data feeds macro regime, risk, and strategy context.

---
</details>

### MVP Recommendation
<details open>
<summary>The first implementation should minimize moving parts while preserving future migration.</summary>
---
#### Recommended stack

- **PostgreSQL** = core metadata, symbols, runs, schemas, and final backtest summaries.
- **Parquet files** = raw and cleaned tabular market data for simple MVP scans.
- **DuckDB** = local analytics over Parquet before committing to a heavier OLAP stack.
- **Qdrant later** = semantic search once enough reports and news are collected.
- **Redis later** = cache and queue only when the system has repeated jobs or near-real-time flows.

---
#### Why not start with everything

- More databases create more connectors, migrations, failure modes, and deployment work.
- The mentor's current priority is architecture and schema clarity, not infra complexity.
- A narrow MVP can still document the target architecture while implementing only the minimum stack.

---
#### Worked example

- `daily_prices` for `10` stocks over `5` years = roughly `10 × 250 × 5 = 12,500` rows.
- `12,500` rows can be handled easily by Parquet plus DuckDB.
- If the universe grows to `1,000` stocks and intraday bars, a time-series or OLAP database becomes more useful.
- The architectural rule is: start simple, but keep `source_id`, `schema_version`, and `as_of_timestamp` so migration does not destroy lineage.

---
</details>

### Cons And Mentor Questions
<details open>
<summary>The biggest DB risk is choosing tools before defining schemas and query patterns.</summary>
---
#### Cons

- **PostgreSQL-only con** = simple to operate, but may become slow for heavy intraday scans.
- **QuestDB con** = strong for time-series, but it does not replace metadata, documents, or vector retrieval.
- **MongoDB con** = flexible, but flexibility can hide schema inconsistency if not controlled.
- **Qdrant con** = useful for semantic search, but embeddings are not a substitute for structured fields like ticker and date.
- **object storage con** = cheap and durable, but it needs a catalog or metadata DB to be queryable.
- **net** = define data contracts first; choose the database only after query patterns are clear.

---
#### Questions to ask mentor

- Should the MVP prioritize local reproducibility or cloud deployment?
- Should raw files be immutable from day one?
- Which DB family does mentor expect the team to evaluate first: time-series, OLAP, vector, or metadata?
- Should tool traces be stored in PostgreSQL JSON fields or a document DB?
- Is real-time crawling part of the first milestone or only a future extension?

---
</details>
