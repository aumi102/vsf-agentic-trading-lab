---
title: mentor_demo_runbook
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Demo Runbook

## Purpose

This runbook lets a mentor walk through the current agent demo in under five minutes. It demonstrates the DB/tool/agent flow built across PRs #16–#18:

- **PR #16:** MVP SQLite store, OHLCV ingestion, features, signals, tools.
- **PR #17:** Deterministic orchestrator — symbol resolution, fixed tool sequence, Vietnamese answer.
- **PR #18:** Scenario runner — `market_brief`, `risk_check`, `compare` with structured output and CLI.

This is not production trading. It is not financial advice. No LLM reasoning is present yet; all answers come from deterministic rule-based tools reading saved local data.

---

## Step 1 — One-Time Build

Build the local SQLite store from saved gap-chart payloads:

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

Expected output:
```
available_symbols=FPT,REE,SAM,VCB,VNM
symbols_loaded=FPT,VCB,VNM
storage=sqlite
db_path=data/demo/mvp_trading_agent.sqlite
row_counts={"daily_prices": 14079, "feature_snapshots": 14071, ...}
```

The SQLite file lives at `data/demo/mvp_trading_agent.sqlite` and is gitignored. Run this once per environment. No network call is made during build or demo.

---

## Step 2 — Demo Commands

### Market brief — direct symbol

```bash
python scripts/run_agent_demo.py --scenario market_brief --symbol FPT
```

Resolves FPT, calls the full tool sequence, returns a Vietnamese summary.

### Market brief — natural-language query

```bash
python scripts/run_agent_demo.py --scenario market_brief --query "FPT hôm nay thế nào?"
```

The orchestrator extracts FPT from the query without an LLM.

### Risk check

```bash
python scripts/run_agent_demo.py --scenario risk_check --symbol VCB
```

Returns risk flags, quality status, and caveats for VCB.

### Compare — three known symbols

```bash
python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB
```

Produces a Markdown comparison table with signal, risk flags, and quality for each symbol. Row order matches input order.

### Compare — one missing symbol

```bash
python scripts/run_agent_demo.py --scenario compare --symbols FPT,HPG
```

FPT is found; HPG is not in the demo store. HPG appears in the table with `status=not_found`. No traceback.

### Compare — all symbols missing

```bash
python scripts/run_agent_demo.py --scenario compare --symbols HPG,XYZ
```

Neither symbol is in the store. Overall `status=not_found`, exit code 1. No traceback.

---

## Step 3 — Expected Behavior

| Command | Exit | Status | Key result |
|---|---:|---|---|
| `market_brief --symbol FPT` | 0 | ok | HOLD, close 75000, 5-tool trace |
| `market_brief --query "FPT hôm nay thế nào?"` | 0 | ok | FPT resolved without LLM |
| `risk_check --symbol VCB` | 0 | ok | `normal_20d_volatility`, `thin_recent_volume` |
| `compare --symbols FPT,VNM,VCB` | 0 | ok | 3 rows in input order |
| `compare --symbols FPT,HPG` | 0 | ok | FPT ok, HPG not_found |
| `compare --symbols HPG,XYZ` | 1 | not_found | all rows missing, no traceback |
| missing DB | 1 | missing_store | build instruction printed, no traceback |

---

## Step 4 — Reading the Output

Each scenario prints a compact JSON summary followed by `## final_answer` and a Vietnamese Markdown answer.

**JSON summary fields:**

| Field | Meaning |
|---|---|
| `status` | `ok`, `not_found`, `missing_store`, `needs_symbol` |
| `scenario` | which demo scenario was run |
| `tool_call_trace` | list of `{tool_name, symbol, status, quality_status}` entries |
| `caveats` | warnings from tools (e.g. adjustment status unknown) |
| `not_financial_advice` | always `true` |

---

## Step 5 — Tool-Call Trace

The `tool_call_trace` makes the agent flow transparent. For `market_brief` and `risk_check`, the sequence is:

```
market_data → features → signal → risk → report
```

For `compare` (per symbol):

```
market_data → features → signal → risk
```

Each trace entry:

```json
{
  "tool_name": "market_data",
  "symbol": "FPT",
  "status": "ok",
  "quality_status": "warn"
}
```

`quality_status: warn` is expected on all market data rows because `adjustment_status` is unknown for all saved payloads.

---

## Limitations

- **Saved local data only.** Source is Vietcap IQ gap-chart payloads saved to `data/raw/`. No fresh official exchange feed.
- **No real-time data.** Latest date in demo store is 2026-06-05.
- **No corporate-action adjustment engine.** All rows have `adjustment_status=unknown`; this is flagged in every caveat.
- **No backtest.** Feature/signal logic is correct but not validated against a historical backtest.
- **No broker execution.** This is a read-only demo layer.
- **No LLM reasoning yet.** Symbol resolution and answers are deterministic. No prompt engineering or model calls.
- **Not financial advice.** All outputs carry `not_financial_advice=True` and an explicit Vietnamese disclaimer.
