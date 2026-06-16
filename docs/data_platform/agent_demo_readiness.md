---
title: agent_demo_readiness
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Agent Demo Readiness

## Context

Three PRs built the current demo-ready foundation:

- **PR #16** — MVP SQLite store with `daily_prices`, `feature_snapshots`, `signals`, and `securities` tables. Tools: `market_data_tool`, `feature_tool`, `signal_tool`, `risk_tool`, `report_tool`.
- **PR #17** — Deterministic orchestrator (`answer_market_query`). Resolves a symbol from a query or `--symbol`, calls tools in a fixed sequence, returns a Vietnamese answer with tool outputs, caveats, and `not_financial_advice=True`.
- **This branch** — Scenario runner (`demo_runner.py` + `scripts/run_agent_demo.py`). Adds `market_brief`, `risk_check`, and `compare` scenarios with structured result dicts, tool-call traces, and a CLI.

## Build the Store

Before running demos, build the local SQLite store from saved gap-chart payloads:

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

The store is written to `data/demo/mvp_trading_agent.sqlite`. It is not committed to the repo.

## Demo Commands

### Market brief — one symbol

```bash
python scripts/run_agent_demo.py --scenario market_brief --symbol FPT
python scripts/run_agent_demo.py --scenario market_brief --query "FPT hôm nay thế nào?"
```

Resolves a symbol, calls the full tool sequence, and returns a Vietnamese summary.

### Risk check — one symbol

```bash
python scripts/run_agent_demo.py --scenario risk_check --symbol VCB
```

Emphasises risk flags and caveats; includes not-financial-advice wording.

### Compare — multiple symbols

```bash
python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB
python scripts/run_agent_demo.py --scenario compare --symbols FPT,HPG
```

Calls market\_data, features, signal, risk tools for each symbol and produces a Markdown comparison table in input order. Symbols absent from the store appear with `status=not_found`; no traceback is raised.

## Tool-Call Trace

Every result dict includes a `tool_call_trace` list. Each entry has:

```json
{
  "tool_name": "market_data",
  "symbol": "FPT",
  "status": "ok",
  "quality_status": "warn"
}
```

Sequence for `market_brief` and `risk_check`:
`market_data → features → signal → risk → report`

Sequence for `compare` (per symbol):
`market_data → features → signal → risk`

## Result Dict Structure

```json
{
  "status": "ok",
  "scenario": "market_brief",
  "input": {"symbol": "FPT", "query": null},
  "tool_call_trace": [...],
  "outputs": {...},
  "answer_markdown": "## FPT - tóm tắt MVP\n...",
  "caveats": ["Adjustment/corporate-action basis is unknown."],
  "not_financial_advice": true
}
```

## Exit Codes

| Condition | Exit code |
|---|---|
| At least one valid symbol | 0 |
| Missing MVP store | 1 |
| All symbols missing | 1 |
| Invalid scenario | 2 (argparse) |

## Current Demo Symbols

Primary: `FPT`, `VNM`, `VCB` (always included in build command).
Also locally available if payloads exist: `REE`, `SAM`.

## Limitations

- **Local data only.** No realtime feed. No official exchange API.
- **No corporate-action adjustment engine.** `adjustment_status=unknown` on all rows; all quality\_status for market data returns `warn`.
- **No backtest.** DB write and backtesting remain blocked.
- **No broker execution.** This is a read-only demo layer.
- **No LLM reasoning.** Answers are deterministic rule-based outputs from the tool layer.
- **Not financial advice.** All outputs carry `not_financial_advice=True` and explicit disclaimer text.
