---
title: 01_deepagents_concepts
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## DeepAgents Concept

### Key Terms
<details open>
<summary>The minimum vocabulary needed before designing a trading agent.</summary>
---
#### Agent terms

| Term | Meaning |
|---|---|
| `agent` | A system that receives a goal, chooses steps, calls tools, and writes an answer. |
| `planner` | The part that breaks one user request into smaller tasks. |
| `tool` | A deterministic function or service that does work the LLM should not fake, such as querying prices or running a backtest. |
| `sub-agent` | A specialized worker agent used for one domain, such as data validation, FA, TA, macro, risk, or backtest. |
| `context` | The information currently visible to the agent while it is reasoning. |
| `memory` | Information saved across steps or runs, such as tool outputs, assumptions, files, and prior decisions. |
| `file system` | A workspace where the agent can store intermediate notes, plans, schemas, and reports. |
| `tool trace` | The audit log of tool calls: input, output, status, error, and timestamp. |
| `abstention` | The policy that lets the agent say `unanswered` instead of forcing a weak conclusion. |

---
#### References

- `REF_LANGCHAIN_DEEP_AGENTS_OVERVIEW`: LangChain describes Deep Agents as agents that can plan, use subagents, and use file systems for complex tasks.
- `REF_LANGCHAIN_SUBAGENTS`: LangChain describes subagents as a way to delegate specialized work and keep the main context clean.
- `REF_LANGCHAIN_BACKENDS`: LangChain documents filesystem backends for agent workspaces.
---
</details>

### Core Mechanism
<details open>
<summary>A DeepAgent is a coordinator-worker system, not a single chatbot answer.</summary>
---
#### Description

- `vn_trading_agent` = the project agent for Vietnamese market research; the user asks it to analyze `FPT` and decide whether a strategy should be rejected, revised, or paper-tested.
- The coordinator does not directly invent a trading answer; it creates a plan and delegates work to tools or sub-agents.
- The sub-agents do not own the final answer; they return structured outputs that the coordinator can compare.
- The final answer is only allowed after the coordinator checks data quality, evidence quality, risk, and unanswered rules.

---
#### Level: coordinator

- **input** = the user request, such as `Backtest a moving-average strategy on FPT from 2021 to 2025`.
- **job** = identify the asset, timeframe, required data, strategy rule, and required validation gates.
- **output** = a task plan: market data -> data quality -> feature engineering -> signal -> backtest -> validation -> final answer.
- **meaning** = the coordinator protects the system from jumping straight from a question to a conclusion.

---
#### Level: tool

- **input** = a narrow contract, such as `symbol=FPT`, `timeframe=1d`, `start=2021-01-01`, `end=2025-12-31`.
- **job** = perform one concrete operation that can be tested.
- **output** = structured data, such as rows, metrics, validation flags, or a failure code.
- **meaning** = tools are where prices, indicators, and backtest numbers come from; the LLM only explains them.

---
#### Level: sub-agent

- **Data Agent** checks source freshness, missing dates, duplicates, and schema validity.
- **TA Agent** converts OHLCV into indicators, signals, and rule-based strategy candidates.
- **FA Agent** reads financial reports, company reports, and analyst notes.
- **Macro Agent** aligns interest rates, bond yields, CPI, FX, and global risk indicators.
- **Risk Agent** checks volatility, drawdown, exposure, liquidity, and cost assumptions.
- **Backtest Agent** runs historical simulation and returns metrics plus validation gates.
- **Strategy Agent** combines evidence and recommends `reject`, `revise`, `promote_to_backtest`, or `promote_to_paper_test`.

---
#### Worked example

- **request** = `Should this FPT momentum strategy be promoted to paper test?`.
- **coordinator** creates `6` tasks: load data, validate data, compute momentum, run backtest, check risk, compose answer.
- **backtest result** = total return `24%`, max drawdown `-18%`, Sharpe `0.72`, trades `18`, after-cost return `15%`.
- **risk result** = max drawdown gate fails because the gate is `>-15%`.
- **final read** = the strategy is not ready for paper test; the right state is `revise`, not `promote_to_paper_test`.

---
</details>

### Trading-Agent Interpretation
<details open>
<summary>DeepAgents matter because trading tasks are long, stateful, and easy to fake.</summary>
---
#### Why a normal chatbot is not enough

- A normal chatbot can summarize terms, but it can hallucinate price data, metrics, and causal explanations.
- A trading agent must keep a full chain from data source -> cleaned data -> features -> signal -> backtest -> validation -> answer.
- A trading agent needs memory because one answer often depends on previous tool outputs and assumptions.
- A trading agent needs sub-agents because FA, TA, macro, and backtest use different data and failure modes.

---
#### What should be stored

| Stored item | Why it matters |
|---|---|
| user request | Lets the team reproduce what was asked. |
| plan | Shows why the agent called each tool. |
| tool input | Proves the exact symbol, time range, and assumptions. |
| tool output | Provides the numbers used in the final answer. |
| failure reason | Explains why the answer became `unanswered`. |
| final decision | Records whether the strategy was rejected, revised, or promoted. |

---
#### Predictable confusion

- **not every task needs a sub-agent**: if one deterministic tool is enough, the coordinator should call the tool directly.
- **not every memory is useful**: raw logs are for audit; distilled assumptions are for future planning.
- **not every DeepAgent is safe**: the architecture still needs tool contracts and abstention gates.

---
</details>

### Risks And Mentor Questions
<details open>
<summary>The main design risk is building a fancy agent before defining tool contracts.</summary>
---
#### Cons

- **tool contract risk** = if tool input/output is vague, sub-agents will return unmergeable outputs.
- **context bloat risk** = if every raw report is placed in context, the coordinator may miss the important fields.
- **over-orchestration risk** = if every tiny step becomes a sub-agent, the MVP becomes slow and hard to debug.
- **false confidence risk** = if the final answer does not expose uncertainty, users may treat analysis as trading advice.
- **net** = DeepAgents are useful only after data contracts and failure contracts are explicit.

---
#### Questions to ask mentor

- Which sub-agent boundaries should exist in MVP: `Data`, `TA`, `Backtest`, `Risk`, and `Answer`, or more?
- Should FA and macro be part of the first demo, or should they stay as reference docs first?
- Should every tool call be stored in a trace database from day one?
- What decision states should the system support: `reject`, `revise`, `promote_to_backtest`, `promote_to_paper_test`, `unanswered`?
- What is the minimum acceptable abstention policy for week-two planning?

---
</details>
