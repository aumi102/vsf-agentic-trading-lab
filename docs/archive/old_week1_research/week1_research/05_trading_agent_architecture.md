---
title: 05_trading_agent_architecture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Agent Shape

### Orchestrator and tools

<details open>
<summary>The Trading Agent is a tool-driven pipeline, not a free-form financial chatbot.</summary>

---

#### Description

- **Cast:** `week1_agent_mvp` = an agent that can answer strategy-analysis questions for `BTCUSDT` daily data.
- **Orchestrator:** the LLM component that understands the question, chooses tools, and composes the answer.
- **Tool:** a bounded function with defined input, output, and failure modes.
- **Trace:** the record of which tool ran, what it received, what it returned, and why it failed if it failed.
- **Reader trap:** the LLM should explain and route; it should not invent Sharpe, drawdown, news causality, or trade recommendations.

---

#### Representation: High-level flow

- **User question:** `Backtest a simple RSI strategy on BTC`.
- **Planner output:** intent `backtest`, asset `BTCUSDT`, timeframe `1d`, strategy `RSI_14`, needed tools `market_data`, `quality`, `feature`, `signal`, `backtest`, `validation`.
- **Tool execution:** each tool consumes the previous tool's structured output.
- **Gate execution:** validation decides `reject`, `revise`, `promote_to_backtest`, `promote_to_paper_test`, or `unanswered`.
- **Answer:** the composer summarizes result, evidence, failures, limitations, and next action.
- **Takeaway:** every final sentence should be traceable to a tool output or a documented limitation.

---

#### Representation: Tool contracts

| Tool | Input | Output | Failure mode |
|---|---|---|---|
| `market_data_tool` | `symbol`, `timeframe`, `start`, `end` | OHLCV rows | `data_not_found` |
| `data_quality_tool` | OHLCV rows | quality report | `invalid_timestamp` |
| `feature_tool` | OHLCV rows, feature config | feature table | `insufficient_lookback` |
| `signal_tool` | feature table, strategy rule | signal table | `undefined_rule` |
| `backtest_tool` | OHLCV, signals, cost config | trades, metrics, equity curve | `missing_cost_config` |
| `validation_gate_tool` | metrics, thresholds | decision and failed gates | `metrics_missing` |
| `evidence_retrieval_tool` | query, asset, time window | evidence table | `no_reliable_evidence` |
| `abstention_tool` | tool statuses and gaps | answerability decision | `insufficient_basis` |

---

</details>

---

## Mechanism

### How a question becomes a decision

<details open>
<summary>The pipeline should make causality explicit: data quality comes before features, features before signals, and signals before backtest.</summary>

---

#### Level 1: Intent

- **Input:** raw user question.
- **Example:** `Does this momentum strategy still work after transaction costs?`.
- **Output:** intent `cost_adjusted_strategy_validation`.
- **Meaning:** the agent needs a previous or new backtest plus cost assumptions.

---

#### Level 2: Data and tool plan

- **Input:** intent, asset, timeframe, strategy name, date range.
- **Example plan:** load `BTCUSDT` daily OHLCV -> check data -> compute momentum -> build signal -> run backtest -> apply costs -> validate.
- **Output:** ordered tool calls.
- **Meaning:** the agent knows what each block must produce before answer composition.

---

#### Level 3: Validation decision

- **Input:** tool results and gate thresholds.
- **Sample metrics:** net return `6.0%`, Sharpe `0.42`, max drawdown `-31.0%`, trades `42`, buy-and-hold return `22.0%`.
- **Failed gates:** `drawdown_gate`, `benchmark_gate`.
- **Output:** `revise`.
- **Meaning:** the system does not promote a strategy just because it is positive after costs.

---

#### Level 4: Answer composition

- **Answer shape:** result -> evidence -> failed gates -> uncertainty -> next action.
- **Example answer:** strategy is `revise`, not `promote`, because it remains positive after cost but fails drawdown and benchmark gates.
- **Safety:** if any required tool failed, the answer should switch from conclusion to `unanswered` with reason code.

---

</details>

---

## Product Boundary

### MVP and non-goals

<details open>
<summary>The week-1 architecture should protect the MVP from becoming a live-trading product too early.</summary>

---

#### MVP scope

- **Asset:** one liquid asset, such as `BTCUSDT` daily or one VN stock basket sample.
- **Strategies:** one or two rule-based strategies, such as RSI mean reversion and moving-average momentum.
- **Data:** historical OHLCV first; news and vector retrieval can be optional.
- **Validation:** data quality, execution timing, cost, drawdown, trade count, benchmark, and regime sanity.
- **Trace:** every tool call saves input, output, status, and failure reason.

---

#### Non-goals

- **No live order placement:** the agent does not execute real trades.
- **No personal investment advice:** the agent analyzes strategy evidence, not user-specific portfolio decisions.
- **No unlimited asset support:** the MVP should not promise every market and timeframe.
- **No hidden metrics:** the LLM cannot report a metric unless a tool produced it.

---

#### Worked example

- **Allowed question:** `Backtest RSI strategy on BTC from 2023 to 2025 with 0.10% fee and 0.05% slippage`.
- **Not allowed as direct answer:** `Should I buy BTC now?`.
- **Safe transformation:** analyze BTC trend, run a defined strategy backtest, and state uncertainty.
- **Reason:** the product should remain a research and validation assistant, not a discretionary financial advisor.

---

#### Cons

- **Big limitation:** a rule-based MVP may look less impressive than an autonomous multi-agent demo.
- **Tradeoff:** the smaller MVP is easier to audit and less likely to hallucinate.
- **Net:** correctness, traceability, and `unanswered` behavior are more valuable than broad claims in week 1.

---

</details>
