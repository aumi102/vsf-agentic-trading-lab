---
title: 02_trading_agent_architecture_overview
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Trading Agent Architecture Overview

### Key Terms
<details open>
<summary>The architecture terms used across all later plans.</summary>
---
#### System terms

| Term | Meaning |
|---|---|
| `orchestrator` | The main agent that chooses the next module or tool. |
| `module` | A system block with a clear responsibility, such as data, features, backtest, or risk. |
| `contract` | The required input, output, and failure shape for a module. |
| `gate` | A validation rule that must pass before moving forward. |
| `state` | The current run record: request, assumptions, tool outputs, and decision. |
| `evidence` | Data or document content used to support an answer. |
| `unanswered` | The final state when the system cannot safely conclude. |

---
#### Decision states

| State | Meaning |
|---|---|
| `reject` | The strategy was tested and failed core gates. |
| `revise` | The strategy has a useful idea but fails one or more fixable gates. |
| `promote_to_backtest` | The idea is structured enough to test, but not yet tested. |
| `promote_to_paper_test` | The strategy passed MVP gates and can be tried without real capital. |
| `unanswered` | The system lacks data, evidence, assumptions, or tool success. |

---
</details>

### Module Map
<details open>
<summary>The trading agent is a pipeline of tools around a cautious orchestrator.</summary>
---
#### Cast

- `vn_trading_agent` = the orchestrator that handles user requests.
- `FPT` = the example Vietnamese stock used through this document.
- `ma20_ma50_strategy` = the example strategy: buy when `MA20 > MA50`, exit when `MA20 < MA50`.
- `backtest_window` = `2021-01-01` to `2025-12-31` on daily bars.

---
#### Core modules

| Module | Job | Output |
|---|---|---|
| `intent_parser` | Understand the user request and extract asset, time range, and task type. | intent object. |
| `market_data_tool` | Load OHLCV and trading calendar data. | market data table. |
| `data_quality_tool` | Check missing dates, duplicates, timestamp, and OHLC rules. | quality report. |
| `feature_tool` | Compute MA, RSI, volatility, return, and other features. | feature table. |
| `signal_tool` | Convert features into buy/sell/hold signals. | signal table. |
| `backtest_tool` | Simulate trades with cost and slippage assumptions. | metrics and trade list. |
| `validation_gate_tool` | Check gates such as drawdown, sample size, cost sensitivity, and leakage. | decision proposal. |
| `evidence_tool` | Retrieve reports, news, or macro context when the request requires explanation. | evidence table. |
| `answer_composer` | Convert structured outputs into a cautious user answer. | final response. |
| `trace_store` | Save plan, tool calls, outputs, and decision. | reproducible run record. |

---
#### What each module must not do

- `intent_parser` must not invent missing strategy rules.
- `market_data_tool` must not silently fill large data gaps.
- `feature_tool` must not use future values when computing today signals.
- `backtest_tool` must not ignore transaction cost or slippage by default.
- `answer_composer` must not invent metrics that are absent from tool output.

---
</details>

### End-To-End Flow
<details open>
<summary>The output of one block must become the input of the next block.</summary>
---
#### Flow

- **user request** -> `intent_parser` extracts `symbol=FPT`, `strategy=ma20_ma50_strategy`, and `period=2021-2025`.
- **intent object** -> `market_data_tool` loads daily OHLCV for `FPT`.
- **OHLCV table** -> `data_quality_tool` checks if the data can be trusted.
- **quality report** -> `feature_tool` only runs if quality status is `pass` or `warn`.
- **feature table** -> `signal_tool` creates position signals.
- **signal table** -> `backtest_tool` simulates trades.
- **backtest result** -> `validation_gate_tool` checks gates.
- **gate result** -> `answer_composer` writes the final answer.
- **all objects** -> `trace_store` saves the run.

---
#### Worked example

- **raw input** = `Backtest MA20/MA50 on FPT from 2021 to 2025 with 15 bps total cost`.
- **data rows** = `1,250` daily rows.
- **quality report** = `missing_days=0`, `duplicate_rows=0`, `ohlc_errors=0`, `status=pass`.
- **signal output** = `13` entry signals and `13` exit signals.
- **backtest output** = total return `18%`, after-cost return `11%`, max drawdown `-16%`, Sharpe `0.64`.
- **gate output** = return gate passes, drawdown gate fails, Sharpe gate fails.
- **final read** = `revise`; the strategy is testable but not strong enough for paper test.

---
#### Unanswered path

- If OHLCV has missing rows above the threshold, the flow stops at `data_quality_tool`.
- If the strategy rule is not specified, the flow stops after `intent_parser` and asks for the missing rule.
- If cost assumptions are missing, the backtest can run as a diagnostic, but the final investment conclusion must be `unanswered`.

---
</details>

### MVP Boundary
<details open>
<summary>The MVP should be narrow enough to prove the pipeline, not the whole market.</summary>
---
#### Recommended MVP

- **asset universe** = `5` to `10` VN stocks or `1` crypto asset if the data source is easier.
- **bar frequency** = daily OHLCV first; intraday can wait.
- **strategy family** = simple rule-based TA strategies such as moving average crossover and RSI mean reversion.
- **validation** = data quality, no lookahead, cost, slippage, drawdown, Sharpe, trade count, and regime split.
- **output** = structured decision with reason codes.

---
#### Out of scope for first demo

- live trading and order execution.
- portfolio optimization across many assets.
- high-frequency order book strategy.
- complex reinforcement learning.
- fully automated buy/sell advice for real money.

---
#### Questions to ask mentor

- Which asset universe should be used for MVP: VN stocks, crypto, or both?
- Should the first demo focus on architecture trace or strategy profitability?
- Which metrics should become hard gates and which should be warnings?
- Should the user see raw tool outputs or only summarized decisions?

---
</details>
