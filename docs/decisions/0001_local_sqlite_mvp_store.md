---
title: "ADR-0001: Local SQLite MVP Store"
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# ADR-0001: Local SQLite MVP Store

**Status:** Accepted for MVP demo (2026-06-16)

---

## Context

The autonomous trading agent needs a local data store to serve deterministic tool calls (market data, features, signals, risk) without a live exchange connection. The immediate goal is a mentor-facing demo showing the agent/tool/DB flow, not production trading.

Key constraints at decision time:

- No QuestDB infrastructure is approved.
- No production DB write path exists.
- Data is limited to saved local Vietcap IQ gap-chart payloads for 3–5 symbols.
- The demo must run with zero external infrastructure dependencies.
- Generated DB files must not be committed to the repository.

---

## Decision

Use **SQLite** as the local MVP store, generated at runtime by `scripts/build_mvp_db.py`.

Tables: `securities`, `daily_prices`, `feature_snapshots`, `signals`.

The SQLite file lives at `data/demo/mvp_trading_agent.sqlite` and is covered by the `data/` entry in `.gitignore`.

All demo tools open the SQLite file read-only. No tool writes to the store during demo runs. The store is rebuilt from scratch on each call to `build_mvp_db.py`.

---

## Consequences

**Positive:**

- Zero infrastructure — Python stdlib `sqlite3`, no pip install required.
- Reproducible: rebuilding from the same raw payloads always produces the same store.
- File-level explainability: the store can be inspected with any SQLite viewer.
- Supports all current tool queries without modification.

**Negative / Accepted trade-offs:**

- Single-writer limitation: only one process can write at a time (acceptable for batch rebuild).
- No native time-series partitioning: suitable for < 10,000 rows/symbol but not for full-universe ingestion.
- No concurrent read/write for realtime: does not support streaming updates.
- `adjustment_status=unknown` on all rows: corporate-action adjustment is not implemented.

---

## Alternatives Considered

| Alternative | Reason not chosen now |
|---|---|
| DuckDB | No stdlib; requires pip install; migration is low-effort when needed |
| QuestDB | Requires Docker; not justified for 3-symbol demo |
| Postgres/Timescale | Requires server; too much ops overhead for demo phase |
| Parquet files | No SQL query layer; harder to integrate with existing tool interface |

---

## Expiry Condition

This decision should be revisited when **any** of the following occur:

1. The symbol universe exceeds 20 symbols and query latency becomes noticeable.
2. A realtime feed or concurrent ingest pipeline is required.
3. The mentor confirms a production DB target (QuestDB / DuckDB / Postgres).
4. The backtest MVP requires columnar time-range queries that exceed SQLite performance.

At expiry, migrate using the decision matrix in `docs/plans/data_store_decision_matrix.md`. The tool interface (`get_latest_market_data`, etc.) is DB-agnostic and should require only a connector swap.
