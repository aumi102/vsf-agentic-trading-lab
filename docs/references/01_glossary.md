---
title: 01_glossary
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Key Terms

### Market and strategy glossary

<details open>
<summary>Short definitions for the terms the agent and mentor discussion will reuse.</summary>

---

#### Market data terms

| Term | Meaning |
|---|---|
| `OHLCV` | Open, High, Low, Close, Volume for one bar. |
| `return` | Percentage gain or loss over a period. |
| `volatility` | Degree of return fluctuation. |
| `liquidity` | Ability to trade size without large price impact. |
| `volume` | Quantity traded during a period. |
| `spread` | Difference between best buy and sell prices. |
| `slippage` | Difference between expected and actual execution price. |

---

#### Strategy terms

| Term | Meaning |
|---|---|
| `alpha` | Return beyond benchmark or common risk explanation. |
| `factor` | Measurable property that may explain returns. |
| `feature` | Computed column used by a rule or model. |
| `signal` | Output such as `buy`, `sell`, `hold`, or a score. |
| `strategy` | Full trading rule with entry, exit, sizing, cost, and risk. |
| `backtest` | Historical simulation of a strategy. |
| `benchmark` | Baseline used for comparison. |

---

#### Risk terms

| Term | Meaning |
|---|---|
| `lookahead bias` | Using future information at a past decision point. |
| `survivorship bias` | Ignoring assets that disappeared or delisted. |
| `transaction cost` | Explicit trading cost such as fee or commission. |
| `drawdown` | Decline from equity peak to later trough. |
| `Sharpe ratio` | Risk-adjusted return measure. |
| `overfitting` | Strategy tuned too tightly to historical data. |
| `regime` | Market state such as trend, range, high volatility, or low volatility. |

---

#### Infrastructure and agent terms

| Term | Meaning |
|---|---|
| `QuestDB` | Time-series database candidate for OHLCV and ticks. |
| `MongoDB` | Document database candidate for trace, config, news, and raw responses. |
| `Qdrant` | Vector database candidate for semantic evidence retrieval. |
| `vector search` | Search by meaning using embeddings, not just exact keywords. |
| `tool trace` | Record of tool input, output, status, and failure reason. |
| `abstention` | Agent chooses not to conclude because basis is insufficient. |
| `unanswered` | Final answer state when data, evidence, or tool output is not enough. |

---

</details>

---

## Worked Mini Examples

### Applying the glossary

<details open>
<summary>Small examples make the terms concrete enough to use in later docs.</summary>

---

#### Return and drawdown

- **Price example:** `BTCUSDT` moves from `68000` to `70000`.
- **Return:** `70000 / 68000 - 1 ≈ 2.94%`.
- **Equity example:** account rises from `100000` to `115000`, then falls to `95000`.
- **Drawdown:** `95000 / 115000 - 1 ≈ -17.39%`.
- **Read:** the strategy made money first, but the later fall from peak was large.

---

#### Slippage and cost

- **Expected buy price:** `100.00`.
- **Actual fill:** `100.20`.
- **Slippage:** `0.20 / 100.00 = 0.20%`.
- **Fee:** `0.10%`.
- **Total one-side drag:** `0.20% + 0.10% = 0.30%`.
- **Read:** frequent trading can erase small edges.

---

#### Tool trace and unanswered

- **User asks:** does strategy still work after costs?
- **Tool trace:** `backtest_tool` failed with `missing_cost_config`.
- **Correct answer state:** `unanswered`.
- **Wrong behavior:** the LLM invents a cost-adjusted Sharpe.
- **Read:** `unanswered` is a safety feature, not a failure of communication.

---

</details>
