---
title: 06_backtest_metrics
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Backtest Metrics

### Key Terms
<details open>
<summary>Backtest metrics should measure return, risk, cost, and robustness together.</summary>
---
#### Metric terms

| Term | Meaning |
|---|---|
| `total return` | Overall gain or loss over the test window. |
| `annualized return` | Return converted to a yearly rate. |
| `volatility` | Variability of returns. |
| `Sharpe ratio` | Return per unit of volatility. |
| `max drawdown` | Largest fall from peak equity to later trough. |
| `win rate` | Percent of trades that make money. |
| `profit factor` | Gross profit divided by gross loss. |
| `turnover` | How much the strategy trades. |
| `transaction cost` | Fees, taxes, commissions, and similar costs. |
| `slippage` | Difference between expected and executed price. |
| `benchmark` | Reference strategy, such as buy-and-hold. |

---
#### Metric warning

- A high return with high drawdown may be unacceptable.
- A high Sharpe with too few trades may be unreliable.
- A profitable result before cost can become unprofitable after cost.
- A strategy that beats zero but loses to benchmark may not be useful.

---
</details>

### Representation
<details open>
<summary>A backtest result should include both metrics and validation gates.</summary>
---
#### Result fields

| Field | Meaning |
|---|---|
| `start_date` | First date of simulation. |
| `end_date` | Last date of simulation. |
| `initial_capital` | Starting capital. |
| `final_capital` | Ending capital after trades. |
| `total_return` | Final capital divided by initial capital minus one. |
| `max_drawdown` | Largest equity peak-to-trough fall. |
| `sharpe` | Risk-adjusted return metric. |
| `trade_count` | Number of completed trades. |
| `cost_bps` | Cost in basis points. |
| `slippage_bps` | Slippage in basis points. |
| `benchmark_return` | Return of reference baseline. |
| `decision` | reject, revise, promote, or unanswered. |

---
#### Validation gates

| Gate | Example threshold | Meaning |
|---|---|---|
| data quality | status is not `fail` | bad data blocks conclusion. |
| trade count | trades `>= 20` | tiny sample is weak. |
| cost sensitivity | after-cost return remains positive | avoids fake edge. |
| drawdown | max drawdown better than `-20%` | controls risk. |
| benchmark | strategy beats buy-and-hold or explains why not | avoids useless complexity. |
| leakage | no lookahead flags | protects validity. |

---
</details>

### Worked Example
<details open>
<summary>Show the values first, then read what they mean.</summary>
---
#### Example values

- `initial_capital` = `100m` VND.
- `final_capital_before_cost` = `128m` VND.
- `final_capital_after_cost` = `116m` VND.
- Before-cost return = `(128 / 100) - 1 = 28%`.
- After-cost return = `(116 / 100) - 1 = 16%`.
- Cost drag = `28% - 16% = 12%`.
- Max drawdown = `-22%`.
- Buy-and-hold return = `30%`.

---
#### Read

- The strategy makes money after cost.
- The strategy loses to buy-and-hold by `14` percentage points.
- The drawdown gate fails if the maximum allowed drawdown is `-20%`.
- The correct decision is `revise`, not `promote_to_paper_test`.

---
</details>

### Risks And Questions
<details open>
<summary>The main risk is reporting one attractive number while hiding failed gates.</summary>
---
#### Risks

- **single-metric risk** = total return hides drawdown and cost.
- **cost risk** = frequent strategies can look good before cost and fail after cost.
- **benchmark risk** = strategy can be profitable but worse than passive exposure.
- **sample risk** = too few trades can create false confidence.
- **overfitting risk** = many tried parameter sets can produce a lucky winner.

---
#### Questions to ask mentor

- Which metrics are mandatory in every backtest report?
- What thresholds should be used for drawdown, Sharpe, and trade count?
- Should benchmark be buy-and-hold, VN-Index, sector index, or cash?
- Should the agent show before-cost and after-cost metrics side by side?

---
</details>
