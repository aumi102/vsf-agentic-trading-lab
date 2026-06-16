---
title: current_demo_architecture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Current Demo Architecture

**State as of 2026-06-16** — merged PRs #16, #17, #18, #19.

This document describes what is implemented and running, plus the blocked future layers. No production trading, realtime, or LLM is active.

---

## Data Flow (Current)

```text
┌─────────────────────────────────────────────────────────┐
│  Saved raw OHLCV payloads (data/raw/)                   │
│  Source: Vietcap IQ gap-chart API (previously fetched)  │
│  Symbols: FPT, VNM, VCB (+ REE, SAM available locally)  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
           build_mvp_db.py
           (scripts/build_mvp_db.py)
           │  -- OHLCV parse + quality checks
           │  -- feature computation (MA20, MA50, returns, volatility)
           │  -- momentum signal evaluation (BUY/SELL/HOLD)
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  SQLite MVP store (data/demo/mvp_trading_agent.sqlite)  │
│  Tables: securities, daily_prices,                      │
│          feature_snapshots, signals                     │
│  14,079 price rows; 14,071 features/signals; 3 symbols  │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┼───────────────────┐
         ▼           ▼                   ▼
   market_data   features/signal      risk_tool
   _tool           _tool             (assess_symbol_risk)
         │           │                   │
         └───────────┴───────────────────┘
                     │
                     ▼
              report_tool
         (compose_market_answer)
         Vietnamese Markdown answer
                     │
                     ▼
              orchestrator
         (answer_market_query)
         │  -- symbol resolution
         │  -- fixed tool sequence
         │  -- returns structured result dict
                     │
                     ▼
             demo_runner
         (run_demo: market_brief /
                    risk_check /
                    compare)
                     │
                     ▼
          run_agent_demo.py (CLI)
          run_mentor_demo_suite.py (suite)
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Output: JSON summary + Vietnamese Markdown answer      │
│  Fields: status, scenario, tool_call_trace,             │
│          outputs, answer_markdown, caveats,             │
│          not_financial_advice=true                      │
└─────────────────────────────────────────────────────────┘
```

---

## Tool-Call Sequence

For `market_brief` and `risk_check`:

```text
market_data → features → signal → risk → report
```

For `compare` (per symbol):

```text
market_data → features → signal → risk
```

Each tool returns a dict with `status`, `quality_status`, and `caveats`. The orchestrator and demo runner aggregate these without inventing values.

---

## What Is NOT Implemented (Blocked Layers)

```text
┌──────────────────────────────────────────────────────────┐
│  BLOCKED — Not implemented                               │
│                                                          │
│  ┌─────────────────────┐   ┌────────────────────────┐   │
│  │  Production DB      │   │  Full-universe OHLCV   │   │
│  │  (QuestDB / DuckDB  │   │  ingestion             │   │
│  │  / Postgres)        │   │  (2,080 symbols)       │   │
│  └─────────────────────┘   └────────────────────────┘   │
│                                                          │
│  ┌─────────────────────┐   ┌────────────────────────┐   │
│  │  Realtime feed      │   │  Backtest engine       │   │
│  │  (websocket / API)  │   │  (Sharpe, Drawdown)    │   │
│  └─────────────────────┘   └────────────────────────┘   │
│                                                          │
│  ┌─────────────────────┐   ┌────────────────────────┐   │
│  │  LLM agent layer    │   │  Corporate-action      │   │
│  │  (tool selection,   │   │  adjustment engine     │   │
│  │  explanation)       │   │                        │   │
│  └─────────────────────┘   └────────────────────────┘   │
│                                                          │
│  ┌─────────────────────┐                                 │
│  │  Broker execution   │  ← out of scope permanently    │
│  └─────────────────────┘                                 │
└──────────────────────────────────────────────────────────┘
```

---

## Source Modules

| Module | Path | Role |
|---|---|---|
| DB builder | `src/trading_agent/db/build_mvp_store.py` | Parses raw payloads, writes SQLite |
| Market data tool | `src/trading_agent/tools/market_data_tool.py` | Latest OHLCV read |
| Feature tool | `src/trading_agent/tools/feature_tool.py` | Latest features read |
| Signal tool | `src/trading_agent/tools/signal_tool.py` | Latest signal read |
| Risk tool | `src/trading_agent/tools/risk_tool.py` | Risk flag derivation |
| Report tool | `src/trading_agent/tools/report_tool.py` | Vietnamese answer composition |
| Orchestrator | `src/trading_agent/agent/orchestrator.py` | `answer_market_query()` |
| Demo runner | `src/trading_agent/agent/demo_runner.py` | Scenario dispatch |
| Demo CLI | `scripts/run_agent_demo.py` | User-facing CLI |
| Suite runner | `scripts/run_mentor_demo_suite.py` | Full-suite status table |

---

## Current Limitations

- **Adjustment status:** Unknown on all rows — every row carries `quality_status: warn`.
- **Latest data date:** 2026-06-05 (no realtime update).
- **No LLM:** All answers are deterministic rule-based outputs.
- **Not financial advice:** All outputs carry `not_financial_advice=True`.
