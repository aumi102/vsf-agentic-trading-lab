---
title: post_demo_technical_roadmap
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Post-Demo Technical Roadmap

**Status as of 2026-06-16:** mentor demo complete (PRs #16–#19 merged). This roadmap describes the next engineering phases. Phases are sequential by default but can be reordered based on mentor feedback.

---

## Phase 1 — Demo Hardening

**Scope:** Keep SQLite MVP. Improve demo quality without adding infrastructure.

Tasks:

- Add more symbols from existing saved payloads (REE, SAM already available locally).
- Improve Vietnamese answer wording — clearer caveats, better phrasing.
- Improve `quality_status` explanation in output (currently `warn` on all rows due to unknown adjustment).
- Add signal reason text to compare table output.
- Stabilize `run_mentor_demo_suite.py` as the single entry point for mentor session.
- Confirm Docusaurus renders all demo docs correctly.

**Gate:** Mentor accepts demo as sufficient for next stakeholder meeting.

---

## Phase 2 — Production Data Store Decision

**Scope:** Choose and migrate to a production-grade store. No backtest yet.

Candidates:

| Option | Pros | Cons |
|---|---|---|
| SQLite (keep) | Zero infra, already working | Single-writer; poor concurrent access; limited time-series queries |
| DuckDB | Columnar, fast analytics, no server | No realtime ingest; less ecosystem |
| QuestDB | Time-series native, websocket, high throughput | Docker required; more ops overhead |
| Postgres + Timescale | Production-grade, familiar | Needs server; heavier setup |

**Selection criteria:**

1. Time-series query speed at 5,000+ rows/symbol.
2. Append/upsert without full rewrite.
3. Local dev simplicity (no Docker required ideally for dev).
4. Deployment complexity for production.
5. Integration with Python tools (pandas, sqlalchemy, async).

**Gate:** Mentor selects one option; schema migration plan drafted.

---

## Phase 3 — Backtest MVP

**Scope:** Simple rule-based backtest on existing signals. No LLM decision.

Tasks:

- Implement vectorized backtest over `signals` table using existing rule (MA20/MA50 momentum).
- Cost/slippage assumptions: flat bps or zero (document choice).
- Metrics: Sharpe ratio, Sortino ratio, Profit Factor, Max Drawdown.
- Backtest scope: FPT, VNM, VCB on saved historical data.
- Output: JSON or CSV results; no broker execution.

**Gate:** Backtest produces deterministic results; mentor reviews metric definitions.

---

## Phase 4 — Agent Integration (LLM Layer)

**Scope:** Add a minimal LLM layer that selects tools and explains results. Tool outputs remain the source of truth.

Constraints:

- LLM must not invent metric values.
- LLM selects which tool to call; tool returns the actual number.
- LLM composes the final Vietnamese explanation from tool outputs only.
- All tool outputs remain in `tool_call_trace` for auditability.
- `not_financial_advice=True` must remain in every response.

**Gate:** LLM integration passes determinism tests: same tool outputs produce same explanation structure. Mentor approves wording.

---

## Phase 5 — Realtime / Websocket Feed

**Scope:** Live price updates. Only after data contracts and backtest are stable.

Tasks:

- Define realtime ingestion contract (symbol, price, timestamp, source).
- Connect to one exchange feed (e.g., VPS, SSI, or public market data).
- Update `daily_prices` or a separate `realtime_prices` table.
- Trigger feature/signal recompute on new close.

**Gate:** After Phase 2 (store decision) and Phase 3 (backtest) are complete. Realtime adds complexity that is not needed before those foundations exist.

---

## Blockers Summary

| Item | Blocked By |
|---|---|
| Production DB write | Phase 2 store decision |
| Full-universe OHLCV ingestion | Phase 2 schema; fetch approval |
| Full-history FA fetch | Mapping coverage gate (currently 94.5% peak, need 95%); PIT gate; schema gate |
| Backtest | Production DB write (Phase 2) |
| LLM reasoning | Backtest validated (Phase 3) or explicitly deferred by mentor |
| Realtime feed | Phase 2 + Phase 3 complete |

---

## Items Not on This Roadmap

- Broker execution / live trading: out of scope for this project.
- Corporate-action adjustment engine: requires full adjustment data from exchange or vendor.
- Portfolio optimization: requires backtest results and risk model.
