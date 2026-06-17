---
title: data_store_decision_matrix
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Data Store Decision Matrix

## Current State

The local SQLite MVP store (`data/demo/mvp_trading_agent.sqlite`) exists for demo purposes only. It is generated at runtime by `scripts/build_mvp_db.py`, gitignored, and not a production DB. It holds 14,079 price rows across 3 symbols (FPT, VNM, VCB) from saved Vietcap IQ gap-chart payloads. All demo tools and scenarios read from this store without writing to it.

The current data flow is:

```
saved raw OHLCV (data/raw/) → build_mvp_db.py → SQLite → tools → demo runner
```

No production DB write is implemented. No realtime ingestion is wired.

---

## Store Comparison

| Criterion | SQLite | DuckDB | QuestDB | Postgres + Timescale | Parquet only |
|---|---|---|---|---|---|
| Local dev speed | Excellent | Excellent | Needs Docker | Needs server | No query layer |
| Time-series query | Adequate (&lt;10 symbols) | Fast (columnar) | Excellent (native) | Good (extension) | Slow ad hoc |
| Append/upsert | Simple | Simple | Native TSZ | Standard | Full rewrite |
| Deployment complexity | Zero | Zero | Docker / process | Server + config | Zero |
| Python integration | stdlib | `duckdb` pip | REST / influxdb client | `psycopg2` / SQLAlchemy | `pandas` / `polars` |
| Explainability | File-level | File-level | Server logs | Server logs | File-level |
| Realtime fit | Poor (no concurrency) | Moderate | Excellent | Good | Not applicable |
| Backtest fit | Good (small scale) | Very good (columnar) | Good | Good | Moderate |
| Migration from SQLite | N/A | Easy (DuckDB reads SQLite) | Medium | Medium | Easy |

---

## Recommendation

### Short term (now → backtest MVP)

**Keep SQLite or migrate to DuckDB.**

- SQLite already works for the local demo. If the mentor confirms that 3–10 symbols and local-only is sufficient for the next review, stay with SQLite.
- DuckDB is the natural upgrade: zero server, columnar analytics, Python-native, and can read existing SQLite or Parquet files directly. It is the lowest-friction path to backtest-ready queries.
- Do not deploy QuestDB before the backtest and ingestion schemas are finalized. Premature infrastructure adds ops risk with no immediate benefit.

### Medium term (after backtest MVP is validated)

**Evaluate QuestDB only after:**

1. Ingestion schema is stable (symbol, trade_date, source_id, adjustment_status).
2. Backtest requirements are confirmed (time-range queries, append-only updates).
3. Mentor explicitly requires realtime websocket capability.

### Not recommended without further evidence

- **Postgres/TimescaleDB:** Adds server ops overhead that is not justified until the universe exceeds 50+ symbols and concurrent access is needed.
- **Parquet-only:** Useful as a cold-storage export layer but not as the primary query target without DuckDB or a query engine on top.

---

## Decision Questions for Mentor

1. Is the current SQLite 3-symbol demo sufficient for the next stakeholder review, or do more symbols need to be available?
2. Is realtime (websocket/streaming) required before the next milestone, or is end-of-day batch sufficient?
3. Should the first backtest run on the existing SQLite data, or must a new store be deployed first?
4. What is the minimum required universe for the first backtest (3 symbols? 20? 100?)?
5. Does the mentor prefer QuestDB specifically, or is DuckDB acceptable as a simpler transition?
