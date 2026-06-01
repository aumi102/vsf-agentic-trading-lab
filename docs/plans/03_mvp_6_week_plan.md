---
title: 03_mvp_6_week_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## MVP 6 Week Plan

### Goal And Boundary
<details open>
<summary>The MVP should demonstrate an auditable trading-agent pipeline, not live trading.</summary>
---
#### Goal

- Build a demo where the agent answers strategy research questions using real data, tool outputs, validation gates, and trace.
- Show that the system can reject weak strategies and say `unanswered` when inputs are insufficient.
- Keep scope small enough to finish and defend.

---
#### Boundary

- **in scope** = daily OHLCV, simple strategies, backtest, validation, tool trace, cautious answer.
- **optional** = document evidence from reports, macro context, and vector search.
- **out of scope** = broker execution, real-money trading, high-frequency order book strategy, and RL-based strategy search.

---
</details>

### Week Plan
<details open>
<summary>Each week should produce one reviewable artifact.</summary>
---
#### Plan table

| Week | Output | Acceptance check |
|---|---|---|
| Week `1` | architecture, data source, domain, and plan docs | mentor can review module map and schema direction. |
| Week `2` | schema draft and local data pipeline prototype | one source produces raw plus clean daily data. |
| Week `3` | feature and signal tools | one strategy creates auditable signals. |
| Week `4` | backtest and validation gates | metrics and reject/revise/promote states work. |
| Week `5` | agent orchestrator and tool trace | user request flows through tools with saved trace. |
| Week `6` | demo polish and report | demo shows success case, failure case, and unanswered case. |

---
#### Worked example demo

- User asks: `Backtest MA20/MA50 on FPT from 2021 to 2025`.
- Agent loads `FPT` daily OHLCV.
- Data quality passes.
- Feature tool computes MA20 and MA50.
- Signal tool creates entry and exit rules.
- Backtest tool returns metrics.
- Validation gate returns `revise` because drawdown is too high.
- Final answer explains the result and links to trace.

---
</details>

### Demo Scenarios
<details open>
<summary>The demo should include one good path, one rejected path, and one unanswered path.</summary>
---
#### Scenario table

| Scenario | Purpose | Expected state |
|---|---|---|
| clean backtest | show normal pipeline works | `reject` or `revise` based on metrics. |
| strategy with high cost sensitivity | show cost gate works | `reject` or `revise`. |
| missing data | show safety behavior | `unanswered`. |
| vague user strategy | show clarification or abstention | `unanswered`. |
| report evidence question | show cautious evidence retrieval | answered with limitations. |

---
#### Required final-answer fields

- `decision` = reject, revise, promote, or unanswered.
- `main_reason` = one plain reason.
- `metrics` = only metrics returned by tools.
- `failed_gates` = machine-readable and human-readable.
- `limitations` = missing data, assumptions, and confidence.
- `next_step` = what to test or fix next.

---
</details>

### Risks And Questions
<details open>
<summary>The main MVP risk is trying to prove strategy profitability instead of system correctness.</summary>
---
#### Risks

- **scope risk** = too many assets, data sources, and agent roles.
- **data risk** = missing corporate actions makes VN equity backtest unreliable.
- **demo risk** = only showing a successful answer hides failure handling.
- **metric risk** = mentor may expect specific validation metrics not yet included.
- **net** = the MVP should prove auditable workflow and safety first; profitability is secondary.

---
#### Questions to ask mentor

- Is the success criterion a profitable strategy or a correct research system?
- Which asset should be used for final demo?
- Should Week `6` include a paper-trading simulation or only a backtest decision?
- Which cases does mentor want to see in the demo: success, reject, revise, unanswered?

---
</details>
