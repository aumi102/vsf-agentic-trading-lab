---
title: 08_risk_list
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Risk Families

### Data risks

<details open>
<summary>Bad data makes every downstream tool look smarter than it really is.</summary>

---

#### Risk table

| Risk | Example | Mitigation | Agent state |
|---|---|---|---|
| Missing data | `90` bars requested, `74` valid bars returned | report missing rate and block backtest if above threshold | `unanswered` if material |
| Wrong timestamp | news in local time merged with price in UTC | normalize timezone and store source timezone | `unanswered` if alignment unclear |
| Duplicate data | two OHLCV rows for the same symbol and timestamp | unique key and dedup rule | warning or fail |
| Bad source quality | price from unknown API or news from low-quality blog | source metadata and confidence score | weak evidence |
| OHLC inconsistency | `high < close` or `low > open` | row-level validation | fail data gate |
| Data leakage | feature uses future close | feature timestamp audit | fail execution gate |

---

#### Worked example

- **Requested:** `BTCUSDT` daily bars for `365` days.
- **Returned:** `361` bars.
- **Missing rate:** `4 / 365 ≈ 1.10%`.
- **Threshold:** maximum allowed missing rate `1.00%`.
- **Gate result:** fail.
- **Answer:** the agent should not run a high-confidence backtest until missing dates are repaired or explicitly accepted.

---

</details>

---

## Backtest Risks

### Validation risks

<details open>
<summary>Most impressive strategy demos fail because the backtest is too optimistic.</summary>

---

#### Risk table

| Risk | Example | Mitigation | Decision impact |
|---|---|---|---|
| Lookahead bias | trade at same close used to create signal | signal at close, execute next open | fail immediately |
| Survivorship bias | only test stocks still listed today | include delisted assets or state limitation | confidence down |
| Ignoring cost | profit `3.0%` before fee, loss after fee | always report gross and net | revise or reject |
| Ignoring slippage | fill assumed at perfect price | stress test slippage levels | revise if edge disappears |
| Overfitting | try `500` parameter sets and keep best | holdout, walk-forward, parameter log | reject or revise |
| Regime dependence | all profit comes from bull market | metrics per regime | revise |
| Low sample size | only `6` trades | minimum trade-count gate | unanswered or revise |
| Benchmark missing | strategy earns `10%`, buy-and-hold earns `30%` | compare against baseline | reject or revise |

---

#### Worked example

- **Gross return:** `12.0%`.
- **After-cost return:** `-2.0%`.
- **Trade count:** `160`.
- **Reason:** high turnover creates too much cost drag.
- **Decision:** `reject` because the strategy does not survive execution assumptions.
- **Read:** high activity is not automatically good; it can convert a weak edge into a net loss.

---

</details>

---

## LLM And Product Risks

### Agent behavior risks

<details open>
<summary>The LLM must not turn missing tool output into confident financial claims.</summary>

---

#### LLM risk table

| Risk | Example | Mitigation | Safe response |
|---|---|---|---|
| Hallucinated metrics | LLM says Sharpe is `1.4` without backtest output | metrics must come from tools | `metric_not_available` |
| Weak news overclaim | blog post treated as strong evidence | evidence strength score | cautious wording |
| No abstention | tool failed but agent still concludes | abstention policy | `unanswered` |
| Missing uncertainty | answer sounds certain despite weak sample | limitations block | confidence label |
| Prompt injection | retrieved article gives instructions to agent | treat retrieved text as data only | ignore embedded instructions |

---

#### Product risk table

| Risk | Example | Mitigation | Week-1 priority |
|---|---|---|---|
| Scope too broad | live trading, all assets, news, multi-agent, portfolio optimization | narrow MVP to one asset and two strategies | highest |
| Demo not convincing | chart without validation gates | show gates and failed reasons | high |
| Tool output unclear | tool returns free text only | structured JSON-like contract | high |
| Advice confusion | user asks `Should I buy BTC now?` | redirect to analysis and disclaim personal advice | high |
| No reproducibility | cannot rerun same result | save data version, config, and trace | high |

---

#### Worked example

- **User asks:** should this strategy be promoted to paper test?
- **Tool status:** `backtest_tool = success`, `validation_gate_tool = success`, `cost_config = missing`.
- **Wrong answer:** promote because gross return is positive.
- **Safe answer:** `unanswered` for paper-test decision because cost-adjusted validation is missing.
- **Next action:** define fee and slippage assumptions, then rerun validation.

---

#### Top week-1 risks

- **Scope creep:** the project becomes too wide before a correct backtest exists.
- **No tool contracts:** mentor cannot review input, output, or failure modes.
- **Lookahead bias:** the demo shows fake profitability.
- **Cost blindness:** the strategy works only before fees and slippage.
- **LLM hallucination:** the final answer invents metrics or causes.
- **No unanswered behavior:** the agent forces a conclusion when it should abstain.

---

</details>
