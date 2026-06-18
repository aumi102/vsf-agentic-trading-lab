---
title: mentor_feedback_capture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Feedback Capture

Use this document to record decisions and action items from the mentor demo session. Fill in after running `docs/demo/mentor_demo_runbook.md`.

---

## Session Details

| Field | Value |
|---|---|
| Date | 2026-06-18 |
| Reviewer / Mentor | Mentor |
| Demo environment | Local — `data/demo/mvp_trading_agent.sqlite` |
| Demo symbols | FPT, VNM, VCB |
| Session notes | Consolidate current work into one Markdown handoff and prioritize data correctness plus stable ETL automation before strategy expansion. |

---

## 2026-06-18 Mentor Feedback

- Consolidate the current DB, ingestion, and backtest plan into one `.md` file
  for upload to the shared Vin folder.
- Backtests should use Backtrader.
- Strategies should stay simple.
- Use FA scanning for stock filtering.
- Use TA rules-based strategies and optimize parameters by Sharpe Ratio.
- Run about 5-10 strategy templates over the current VN100 list for the MVP.
- Each ticker only needs one selected strategy.
- The selected strategy must have the highest Sharpe Ratio among candidates and
  must beat the ticker's buy-and-hold benchmark.
- Be careful in docs and implementation because backtest bugs are easy.
- Adjusted price is mandatory.
- Adjust OHLC using an adjustment factor from dividend, split, and corporate
  action logic, not adjusted close alone.
- Research and propose transaction cost assumptions before hardening backtests.
- Use reasonable slippage bounded by exchange daily price bands: HSX +/-7% and
  UPCOM +/-15%.
- Docker priority is DB/ETL flow first.
- ETL should run automatically and stably with a schedule.
- Only stable components should be Dockerized.

---

## Demo Commands Run

Mark each command that was actually run during the session:

- [ ] `python scripts/build_mvp_db.py --symbols FPT,VNM,VCB`
- [ ] `python scripts/run_agent_demo.py --scenario market_brief --symbol FPT`
- [ ] `python scripts/run_agent_demo.py --scenario market_brief --query "FPT hôm nay thế nào?"`
- [ ] `python scripts/run_agent_demo.py --scenario risk_check --symbol VCB`
- [ ] `python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB`
- [ ] `python scripts/run_agent_demo.py --scenario compare --symbols FPT,HPG`
- [ ] `python scripts/run_mentor_demo_suite.py`

---

## Mentor Answers

### Production data store

> **Question:** Which store should be used next — SQLite (keep), DuckDB, QuestDB, or Postgres/TimescaleDB?

**Answer:** _(fill in)_

**Rationale from mentor:** _(fill in)_

---

### Symbol universe

> **Question:** Which symbols should be prioritized next? (Current: FPT, VNM, VCB)

**Answer:** _(fill in)_

**Minimum universe for backtest:** _(fill in)_

---

### Backtest expectation

> **Question:** When does a backtest need to exist, and what is the minimum acceptable output?

**Answer:** _(fill in)_

**Acceptable metric set:** _(Sharpe only? Full set? Equity curve visualization?)_

---

### Signal/answer wording

> **Question:** Should BUY/SELL/HOLD be shown to non-technical stakeholders, or kept internal?

**Answer:** _(fill in)_

---

### Acceptable limitations for demo

> **Question:** Which current limitations are acceptable for the next milestone?
> (adjustment_status=unknown, no realtime, no LLM, local data only)

**Answer:** _(fill in)_

---

### Priority ranking

> **Question:** Please rank these from most to least urgent:
> 1. More demo symbols
> 2. Production DB migration
> 3. Backtest MVP
> 4. LLM reasoning layer
> 5. Realtime feed

**Ranking from mentor:** _(fill in)_

---

## Action Items

| Item | Owner | Priority | Due Date | Status |
|---|---|---|---|---|
| _(fill in)_ | _(fill in)_ | High / Med / Low | _(YYYY-MM-DD)_ | Open |
| _(fill in)_ | _(fill in)_ | | | |
| _(fill in)_ | _(fill in)_ | | | |

---

## Decision Log

| Decision | Rationale | Date | Impact |
|---|---|---|---|
| _(fill in)_ | _(fill in)_ | _(YYYY-MM-DD)_ | _(fill in)_ |

---

## Notes

_(Free text for additional mentor comments, questions raised, or items to revisit.)_
