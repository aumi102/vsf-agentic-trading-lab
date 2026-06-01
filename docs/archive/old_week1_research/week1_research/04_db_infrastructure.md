---
title: 04_db_infrastructure
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Storage Families

### Why one database is not enough conceptually

<details open>
<summary>Trading Agent data has different shapes, so the docs should separate time-series, documents, vectors, metadata, and cache.</summary>

---

#### Description

- **Cast:** `agent_run_2026_05_29` = one demo run where a user asks the agent to test a simple `BTCUSDT` momentum strategy.
- **Purpose:** make every input, output, and failure traceable after the answer is written.
- **Reader trap:** the database is not just storage; it is the audit trail that proves why the agent answered or abstained.

---

#### Representation: Time-series store

- **Role:** stores dense timestamped market data.
- **Candidate:** `QuestDB` for OHLCV, trades, ticks, order book snapshots, and computed features.
- **Key fields:** `symbol`, `timeframe`, `timestamp`, `open`, `high`, `low`, `close`, `volume`, `source`.
- **Sample row:** `BTCUSDT`, `1d`, `2026-05-28T00:00:00Z`, `open 68000`, `close 70000`, `volume 32000` BTC.
- **Query pattern:** load contiguous time windows quickly for indicators and backtests.
- **Takeaway:** this store feeds `market_data_tool`, `data_quality_tool`, `feature_tool`, and `backtest_tool`.

---

#### Representation: Document store

- **Role:** stores flexible JSON-like records.
- **Candidate:** `MongoDB` for news articles, raw API responses, tool traces, configs, and error logs.
- **Key fields:** `run_id`, `tool_name`, `input`, `output`, `status`, `failure_reason`, `created_at`.
- **Sample trace:** `backtest_tool`, status `failed`, reason `missing_cost_config`, run `agent_run_2026_05_29`.
- **Query pattern:** reconstruct what happened in a run.
- **Takeaway:** this store makes the agent debuggable and auditable.

---

#### Representation: Vector store

- **Role:** stores embeddings for semantic retrieval.
- **Candidate:** `Qdrant` for news evidence, research notes, strategy descriptions, and past failure cases.
- **Key fields:** `doc_id`, `embedding`, `text`, `source`, `timestamp`, `asset_tags`, `quality_score`.
- **Sample query:** `news that may explain BTC breakout` -> retrieve ETF inflow, exchange flow, and macro news snippets.
- **Query pattern:** find meaning-related evidence even when exact keywords differ.
- **Takeaway:** this store supports evidence retrieval, not numerical backtesting.

---

#### Representation: Relational metadata store

- **Role:** stores structured registry records.
- **Candidate:** `PostgreSQL` for production or `SQLite` for a week-1 MVP.
- **Key tables:** `strategies`, `runs`, `backtest_summaries`, `validation_results`, `data_versions`, `tool_contracts`.
- **Sample strategy record:** `rsi_demo_v1`, asset `BTCUSDT`, timeframe `1d`, status `draft`, owner `research_lab`.
- **Query pattern:** list, compare, and version strategies.
- **Takeaway:** this store gives the agent a stable map of what exists.

---

</details>

---

## Data Flow

### Tool input and output movement

<details open>
<summary>Each storage family supports a specific stage in the agent pipeline.</summary>

---

#### Flow

| Stage | Reads from | Writes to | Output for next block |
|---|---|---|---|
| `market_data_tool` | Time-series store | Document trace | OHLCV rows |
| `data_quality_tool` | OHLCV rows | Document trace | quality report |
| `feature_tool` | OHLCV rows | Time-series or document store | feature table |
| `signal_tool` | feature table | Document trace | signal table |
| `backtest_tool` | OHLCV, signals, config | metadata and trace stores | metrics and trades |
| `validation_gate_tool` | metrics and trades | metadata store | reject, revise, promote, or unanswered |
| `evidence_retrieval_tool` | vector and document stores | Document trace | evidence table |

---

#### Worked example

- **User asks:** does the `BTCUSDT` RSI strategy still work after transaction costs?
- **Market data:** read `750` daily bars from the time-series store.
- **Quality report:** `0` missing bars, `0` duplicates, OHLC valid.
- **Cost config:** `0.10%` fee and `0.05%` slippage per side.
- **Backtest summary:** gross return `18.0%`, net return `6.0%`, max drawdown `-31.0%`.
- **Validation output:** `revise` because drawdown and benchmark gates fail.
- **Trace:** every tool input and output is stored under `agent_run_2026_05_29`.

---

#### Unanswered rules

- **No OHLCV:** market analysis and backtest cannot run.
- **No cost config:** cost-adjusted performance must be `unanswered`.
- **No trace:** the final answer cannot be audited, so it should be treated as incomplete.
- **No source timestamp:** news evidence cannot be aligned to price movement.

---

</details>

---

## MVP Decision

### What to implement first

<details open>
<summary>Week 1 should document the target design while keeping the next implementation small.</summary>

---

#### Minimal stack

- **Time-series MVP:** a single table or file for daily OHLCV is enough before deploying `QuestDB`.
- **Metadata MVP:** `SQLite` or `PostgreSQL` can store run summaries and strategy configs.
- **Trace MVP:** JSON files or a simple document collection can store tool traces.
- **Vector MVP:** skip vector search until news or research-note retrieval becomes required.
- **Reason:** the first demo needs correctness and traceability more than infrastructure breadth.

---

#### Pros and cons

| Choice | Pros | Cons |
|---|---|---|
| Single relational DB first | Simple deployment and fewer moving parts | Weaker for high-frequency time-series and vector search |
| Full multi-DB stack | Closer to target architecture | More infra work before strategy demo exists |
| File-based MVP | Fastest for week-1 and week-2 experiments | Harder to audit and scale later |

---

#### Net

- **Recommendation:** document the multi-store target, but implement the next MVP with the smallest stack that still preserves tool I/O and trace logs.
- **Mentor question:** should week 2 prioritize backtest correctness or database architecture first?

---

</details>
