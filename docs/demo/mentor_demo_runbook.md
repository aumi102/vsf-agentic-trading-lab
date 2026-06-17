---
title: mentor_demo_runbook
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Demo Runbook

## Purpose

This runbook lets a mentor walk through the current local demo. It covers the DB/tool/agent/backtest flow built across PRs #16-#22:

- PR #16: MVP SQLite store, OHLCV ingestion, features, signals, tools.
- PR #17: Deterministic orchestrator: symbol resolution, fixed tool sequence, Vietnamese answer.
- PR #18: Scenario runner: `market_brief`, `risk_check`, `compare`.
- PR #22: Exploratory Backtest MVP over cached SQLite data.

This is not production trading and not financial advice. No LLM reasoning is present; all outputs come from deterministic rule-based tools reading saved local data.

---

## Step 1 - One-Time Build

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

Expected: `symbols_loaded=FPT,VCB,VNM`, row counts, and `db_path=data/demo/mvp_trading_agent.sqlite`.

The SQLite file is gitignored. No network call is made during build or demo.

---

## Step 2 - DB/Ingestion Status

```bash
python scripts/run_ingestion_status.py --symbols FPT,VNM,VCB
```

Expected: `status=ok`, table counts, source lineage, freshness, and tool
readiness. A DB built by `build_mvp_db.py` may show no `source_runs`; a DB
updated by `run_ohlcv_ingestion.py` should show source runs and watermarks.

---

## Step 3 - Agent Demo Commands

```bash
python scripts/run_agent_demo.py --scenario market_brief --symbol FPT
python scripts/run_agent_demo.py --scenario market_brief --query "FPT hôm nay thế nào?"
python scripts/run_agent_demo.py --scenario risk_check --symbol VCB
python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB
python scripts/run_agent_demo.py --scenario compare --symbols FPT,HPG
python scripts/run_agent_demo.py --scenario compare --symbols HPG,XYZ
```

If the local shell has encoding issues, use the ASCII fallback: `FPT hom nay the nao?`.

Expected behavior:

| Command | Exit | Status | Key result |
|---|---:|---|---|
| `market_brief --symbol FPT` | 0 | ok | tool trace and Vietnamese answer |
| `market_brief --query "FPT hôm nay thế nào?"` | 0 | ok | FPT resolved without LLM |
| `risk_check --symbol VCB` | 0 | ok | risk flags and caveats |
| `compare --symbols FPT,VNM,VCB` | 0 | ok | 3 rows in input order |
| `compare --symbols FPT,HPG` | 0 | ok | FPT ok, HPG not_found |
| `compare --symbols HPG,XYZ` | 1 | not_found | all rows missing, no traceback |

---

## Step 4 - Backtest MVP Commands

```bash
python scripts/run_backtest_demo.py --symbols FPT,VNM,VCB --strategy-id mvp_ma20_ma50_momentum
python scripts/run_backtest_demo.py --symbols FPT,HPG --strategy-id mvp_ma20_ma50_momentum
python scripts/run_backtest_demo.py --symbols FPT --start-date 2030-01-01 --end-date 2030-12-31
```

Expected behavior:

| Command | Exit | Status | Key result |
|---|---:|---|---|
| `backtest --symbols FPT,VNM,VCB` | 0 | ok | metrics present; gates pass/warn |
| `backtest --symbols FPT,HPG` | 0 | ok | FPT runs; HPG in `symbols_missing` |
| `backtest --symbols FPT --start-date 2030-01-01 --end-date 2030-12-31` | 1 | not_found | no usable rows; no traceback |

---

## Step 5 - Full Suite

```bash
python scripts/run_mentor_demo_suite.py
```

Expected: status table with OK for all expected outcomes. The suite treats documented nonzero edge cases as pass when exit code and status match.

---

## Reading The Output

Agent commands print a JSON summary plus `## final_answer`. Backtest commands print a JSON summary, compact metrics table, and caveats.

Key fields:

| Field | Meaning |
|---|---|
| `status` | `ok`, `not_found`, `missing_store`, `invalid_assumptions` |
| `tool_call_trace` | deterministic agent tool sequence |
| `symbols_found`, `symbols_missing` | backtest symbol coverage |
| `validation_gates` | backtest data and assumption checks |
| `tool_readiness` | DB readiness for market data, features, signals, and backtest |
| `caveats` | adjustment, data, or execution-convention warnings |
| `not_financial_advice` | always `true` |

---

## Limitations

- Saved local data only; no fresh exchange feed.
- Latest observation in demo store is 2026-06-05.
- Corporate-action adjustment status is unknown.
- Backtest is exploratory only; same-day close is an MVP caveat.
- Flat cost/slippage assumptions are placeholders.
- No broker execution, live trading, shorting, QuestDB, network crawl, or LLM reasoning.
- Not financial advice.
