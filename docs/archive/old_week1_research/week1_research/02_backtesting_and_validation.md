---
title: 02_backtesting_and_validation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Backtest Purpose

### What a backtest can and cannot prove

<details open>
<summary>A backtest is a historical simulation; it filters bad ideas but does not guarantee future profit.</summary>

---

#### Description

- **Cast:** `rsi_demo_v1` = a simple strategy tested on `BTCUSDT` daily data from `2023-01-01` to `2025-12-31`.
- **Strategy rule:** buy when `RSI_14 < 30`, exit when `RSI_14 > 50`, execute at next day open.
- **Purpose:** check whether the rule survives costs, slippage, drawdown, and out-of-sample validation.
- **Reader trap:** profitable backtest does not mean tradable strategy; it may be leakage, overfitting, or cost illusion.

---

#### Representation: Trade simulation

- **Input:** OHLCV rows, features, signals, execution rule, cost rule, slippage rule, starting capital.
- **Signal timestamp:** the signal is known only after the bar closes.
- **Execution timestamp:** the trade must happen on the next bar, not on the same close that created the signal.
- **Sample:** signal appears at `2024-04-01` close; entry happens at `2024-04-02` open.
- **Tie-out:** signal time `<` execution time must hold for every trade.
- **Takeaway:** this one timestamp rule prevents lookahead bias in the simplest MVP.

---

#### Representation: Performance metrics

| Field | Meaning |
|---|---|
| `total_return` | Full-period strategy return after all trades. |
| `annualized_return` | Return scaled to a yearly rate. |
| `volatility` | Standard deviation of strategy returns. |
| `Sharpe` | Risk-adjusted return; higher is better only if sample is credible. |
| `max_drawdown` | Worst peak-to-trough equity loss. |
| `trade_count` | Number of completed trades; too few trades reduce confidence. |
| `turnover` | How much capital is traded; high turnover makes costs matter more. |

---

#### Worked example

- **Starting capital:** `100000` USDT.
- **Gross final equity:** `118000` USDT -> gross return `18.0%`.
- **Cost per side:** `0.10%`; slippage per side `0.05%`; total per side `0.15%`.
- **Trades:** `40` round trips -> `80` sides.
- **Approx cost drag:** `80 × 0.15% = 12.0%` of one full notional turnover assumption.
- **Net final equity:** `106000` USDT -> net return `6.0%`.
- **Read:** the strategy looked strong before costs but becomes marginal after realistic execution assumptions.

---

</details>

---

## Key Terms

### Validation terms

<details open>
<summary>These terms describe how the agent avoids fake confidence from historical data.</summary>

---

#### Backtest and split terms

| Term | Meaning |
|---|---|
| `backtest` | Historical simulation of a strategy. |
| `train split` | Period used to design or tune a rule. |
| `validation split` | Period used to choose among variants. |
| `test split` | Final holdout period used to estimate out-of-sample behavior. |
| `walk-forward` | Repeated train-then-test windows that move forward through time. |
| `purged CV` | Cross-validation that removes overlapping samples to reduce leakage. |
| `embargo` | A gap after a test fold to reduce information spillover. |
| `CPCV` | Combinatorial Purged Cross-Validation; many purged out-of-sample paths. |

---

#### Risk and bias terms

| Term | Meaning |
|---|---|
| `lookahead bias` | Using information that was not available at decision time. |
| `survivorship bias` | Testing only assets that survived until today. |
| `transaction cost` | Explicit cost such as fee or commission. |
| `slippage` | Price difference between expected fill and actual fill. |
| `overfitting` | Tuning a rule until it matches the past too closely. |
| `regime` | Market state such as uptrend, downtrend, sideways, high volatility, or low volatility. |

---

</details>

---

## Validation Gates

### Gate design

<details open>
<summary>Each gate should return pass, fail, or unanswered with a reason code.</summary>

---

#### Gate table

| Gate | Checks | Example threshold | Failure meaning |
|---|---|---:|---|
| `data_quality_gate` | Missing, duplicate, timestamp, OHLC consistency | missing bars `<= 1%` | Backtest cannot be trusted. |
| `execution_gate` | Signal time precedes trade time | every trade passes | Lookahead risk exists. |
| `cost_gate` | Net result after fees and slippage | net return `> 0%` | Gross profit disappears after costs. |
| `drawdown_gate` | Worst equity decline | max drawdown `>-25%` | Risk may be too large for MVP. |
| `trade_count_gate` | Enough observations | trades `>= 30` | Sample is too small. |
| `benchmark_gate` | Strategy beats baseline | excess return `> 0%` | Buy-and-hold may be better. |
| `regime_gate` | Performance across market states | no single regime explains all profit | Strategy may be regime-specific. |

---

#### Worked example

- **Gross return:** `18.0%`.
- **Net return:** `6.0%` after cost and slippage.
- **Max drawdown:** `-31.0%`.
- **Trade count:** `42`.
- **Buy-and-hold return:** `22.0%`.
- **Gate read:** cost gate passes, trade count passes, drawdown gate fails, benchmark gate fails.
- **Decision:** `revise`, not `promote_to_paper_test`.
- **Reason:** the strategy is not worthless, but it underperforms buy-and-hold and takes too much drawdown.

---

#### Failure vs negative result

- **Failure:** the tool cannot run safely, such as missing OHLCV or invalid timestamps.
- **Negative result:** the tool runs correctly and shows weak performance.
- **Failure output:** `unanswered` because no reliable performance conclusion exists.
- **Negative output:** `reject` or `revise` because the strategy was actually tested.

---

</details>
