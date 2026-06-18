---
title: mentor_feedback_capture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Feedback Capture

Use this document to record mentor feedback, confirmed requirements, and
remaining decisions for the next implementation phase.

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

## Confirmed Requirements

| Requirement | Date | Impact |
|---|---|---|
| Use Backtrader for backtests | 2026-06-18 | Future backtest work should use Backtrader, not a custom strategy engine. |
| Use current VN100 for MVP universe | 2026-06-18 | First broad universe is current VN100, with survivorship caveat documented. |
| Use adjusted OHLC | 2026-06-18 | Backtests must wait for adjusted open/high/low/close handling, not adjusted close alone. |
| Prioritize DB/ETL Dockerization | 2026-06-18 | Stable ingestion/status/control flow comes before experimental strategy Dockerization. |
| Add scheduling later with guardrails | 2026-06-18 | ETL should eventually ingest new data automatically, but no scheduler is enabled yet. |

---

## Proposed Next Steps

1. Add adjusted OHLC schema/spec and tests.
2. Design stable ETL Docker/scheduler foundation.
3. Add a Backtrader research scaffold only after adjusted OHLC is reliable.
4. Run current VN100 through FA scan plus 5-10 simple TA templates.
5. Select one strategy per ticker only when Sharpe is highest among candidates
   and above buy-and-hold on the same adjusted feed.

---

## Still Open For Research Or Review

- Transaction cost assumptions.
- Final slippage model, bounded by HSX +/-7% and UPCOM +/-15%.
- Corporate-action factor source and validation policy.
- Production DB path after the local SQLite MVP.
- Scheduler deployment details after stable ETL Docker review.
