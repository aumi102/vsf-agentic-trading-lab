---
title: mentor_review_checklist
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Review Checklist

Use this checklist during and after the demo session to confirm the current state and decide next engineering steps. No market knowledge is required — focus on tool flow, output quality, and product direction.

---

## What to Run

### One-time build

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

Expected: prints `symbols_loaded=FPT,VCB,VNM`, row counts, and DB path. No network calls.

### Demo scenarios

```bash
python scripts/run_agent_demo.py --scenario market_brief --symbol FPT
python scripts/run_agent_demo.py --scenario market_brief --query "FPT hôm nay thế nào?"
python scripts/run_agent_demo.py --scenario risk_check --symbol VCB
python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB
python scripts/run_agent_demo.py --scenario compare --symbols FPT,HPG
```

### Full suite at once

```bash
python scripts/run_mentor_demo_suite.py
```

Expected: prints a status table with OK for all scenarios. HPG,XYZ appears as expected-nonzero (labeled OK in the suite).

---

## What to Inspect

| Item | What to look for |
|---|---|
| FPT market brief | Latest date; signal (HOLD/BUY/SELL); risk flag; caveat about adjustment_status |
| VCB risk check | Risk flags; `thin_recent_volume` caveat; quality_status=warn |
| Compare table | 3 rows; FPT/VNM/VCB signals differ; table prints in input order |
| FPT vs HPG compare | FPT ok row; HPG `not_found` row with N/A values; no traceback |
| Tool-call trace | 5 entries per symbol: market_data → features → signal → risk → report |
| `not_financial_advice` | Always `true` in JSON output |
| Disclaimer | Vietnamese text ends with: _Đây là demo công cụ nội bộ, không phải khuyến nghị đầu tư_ |

---

## Expected Output Summary

| Command | Exit | Status | Signal (FPT) | Risk (VCB) |
|---|---:|---|---|---|
| `market_brief --symbol FPT` | 0 | ok | HOLD | — |
| `risk_check --symbol VCB` | 0 | ok | — | normal_20d_volatility, thin_recent_volume |
| `compare --symbols FPT,VNM,VCB` | 0 | ok | FPT HOLD, VNM SELL, VCB HOLD | — |
| `compare --symbols FPT,HPG` | 0 | ok | HPG not_found, no traceback | — |

---

## Questions for Mentor

Please answer these so we can plan the next sprint:

### 1. Demo readiness

> Is the current SQLite MVP demo sufficient to show at the next stakeholder meeting?
> Or does it need additional symbols, improved wording, or a different output format?

### 2. Production data store

> Which store should we move to next?
>
> - **Keep SQLite** temporarily — simple, no infra, good for < 10 symbols
> - **DuckDB** — columnar, fast analytics, no server, easy migration from SQLite
> - **QuestDB** — time-series native, websocket support, needs Docker
> - **Postgres / TimescaleDB** — familiar, production-grade, more ops overhead

### 3. Symbol universe

> Which symbols should be prioritized next?
> Current demo: FPT, VNM, VCB (+ REE, SAM available locally)
> HOSE/HNX universe: 2,080 symbols (full fetch not yet approved)

### 4. Signal/answer wording

> The current signal is rule-based: BUY / SELL / HOLD.
> Should the answer surface this wording to non-technical stakeholders?
> Or should it stay as an internal signal value with the Vietnamese caveat only?

### 5. Minimum backtest requirement

> When does a backtest need to exist?
> - Never (demo only)?
> - Before production DB is approved?
> - Before an LLM agent is added?
> What strategy should the first backtest cover (e.g., the existing MA20/MA50 momentum rule)?

### 6. LLM integration timeline

> The current agent is fully deterministic (no LLM).
> When should an LLM layer be added?
> - Immediately (to write better Vietnamese answers)?
> - After backtest is validated?
> - After production DB is stable?

### 7. Stakeholder visibility

> Which parts of the output should be private (not shown to non-technical stakeholders)?
> - Raw risk flags?
> - Quality_status: warn?
> - Caveats about adjustment_status?
> - The tool-call trace JSON?

---

## After the Demo Session

Record answers to the questions above and update `docs/plans/post_demo_technical_roadmap.md` with the agreed next phase.

The current blockers remain:

- Production DB write: blocked until store decision is made.
- Full-history FA fetch: blocked on mapping, PIT, and schema gates.
- Backtest: blocked on DB write.
- LLM reasoning: blocked until backtest is validated or explicitly deferred.
- Real-time feed: blocked until data contracts are stable.
