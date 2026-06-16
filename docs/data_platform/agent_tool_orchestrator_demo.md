---
title: agent_tool_orchestrator_demo
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Agent Tool Orchestrator Demo

## Purpose

This demo adds a thin agent-facing orchestration layer on top of the merged MVP
DB/tool foundation. It does not add LLM reasoning, network fetching, broker
execution, QuestDB, or a backtest. The purpose is to prove that a user-facing
entry point can resolve a symbol, call deterministic tools, and return a
Vietnamese answer from tool outputs.

## Flow

`answer_market_query(query=None, symbol=None, db_path=..., language="vi")`
performs:

1. Resolve a symbol from `--symbol` or a simple deterministic query scan.
2. Check that the local SQLite MVP store exists.
3. Call tools in this exact sequence:
   `market_data`, `features`, `signal`, `risk`, `report`.
4. Return status, resolved symbol, tool outputs, final Markdown answer,
   caveats, and `not_financial_advice=True`.

No values are invented by the orchestrator; the report text comes from the
existing report tool.

## Commands

Build the local store first:

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

Run the agent-facing demo:

```bash
python scripts/agent_answer_demo.py --symbol FPT
python scripts/agent_answer_demo.py --query "FPT hôm nay thế nào?"
```

If the DB is missing, the orchestrator tells the user to run the build command.
If no symbol can be resolved, it returns `needs_symbol`; if a parsed symbol is
not in the store, it returns `not_found` without a traceback.

## Limitations

- No LLM reasoning or planning.
- No network fetches or source probes.
- No real-time feed.
- No corporate-action adjustment logic beyond existing caveats.
- No backtest.
- No broker execution.
- Not financial advice.
