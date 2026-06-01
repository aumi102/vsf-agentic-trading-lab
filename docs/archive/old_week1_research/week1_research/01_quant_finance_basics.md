---
title: 01_quant_finance_basics
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Market Data And Trading Objects

### Core objects

<details open>
<summary>The smallest objects are market bars, returns, features, signals, and strategy decisions.</summary>

---

#### Description

- **Cast:** `vn_momentum_bot` = a week-1 Trading Agent demo that analyzes `FPT` daily bars and can later be reused for `BTCUSDT` daily bars.
- **Purpose:** turn raw market records into a testable trading decision, not a confident story.
- **Reader trap:** `price went up` is not the same as `strategy works`; a strategy must survive data checks, cost assumptions, and validation gates.

---

#### Representation: Market bar

- **Context:** one daily bar records what happened to one asset during one trading day.
- **Fields:** `symbol` = asset code; `timestamp` = bar end time; `open` = first traded price; `high` = highest traded price; `low` = lowest traded price; `close` = last traded price; `volume` = traded quantity.
- **Sample:** `FPT`, `2026-05-28`, `open 118000`, `high 121000`, `low 117500`, `close 120000`, `volume 2,400,000` shares.
- **Tie-out:** `high` must be at least `max(open, close)` and `low` must be at most `min(open, close)`; otherwise the bar is not safe for backtesting.
- **Takeaway:** OHLCV is the base material; every indicator and backtest result inherits its quality.

---

#### Representation: Return

- **Context:** return converts price movement into a comparable unit.
- **Formula:** `simple_return = close_today / close_yesterday - 1`.
- **Sample:** `FPT` close moves from `118000` to `120000` -> `120000 / 118000 - 1 ≈ 0.01695` -> about `1.70%`.
- **Read:** the stock gained about `1.70%` for that day.
- **Takeaway:** agents compare returns, not just prices, because `+2000` VND has different meaning for a `20000` VND stock and a `200000` VND stock.

---

#### Representation: Feature -> signal -> strategy

- **Feature:** a computed column from data, such as `20d_return`, `20d_volatility`, `SMA_20`, or `RSI_14`.
- **Signal:** a compact trading hint, such as `buy`, `sell`, `hold`, or a score from `-1` to `1`.
- **Strategy:** the full rule that turns signals into positions, including entry, exit, sizing, cost, and failure handling.
- **Sample feature:** `close 120000`, `SMA_20 116000` -> price is above trend filter.
- **Sample signal:** `close > SMA_20` and `20d_return > 0` -> `long_signal = 1`.
- **Sample strategy:** enter at next day open, hold until `close < SMA_20`, charge `0.15%` cost per side, max position `20%` of capital.
- **Signal vs strategy:** signal is a traffic light; strategy is the whole driving plan.

---

</details>

---

## Key Terms

### Trading terms

<details open>
<summary>These terms should be defined once, then referenced by exact heading in later docs.</summary>

---

#### Market and return terms

| Term | Meaning |
|---|---|
| `OHLCV` | Open, High, Low, Close, Volume for one asset and one timeframe. |
| `return` | Percentage gain or loss over a period. |
| `volatility` | How much returns fluctuate; higher volatility means larger swings. |
| `liquidity` | How easily the agent can trade size without moving price too much. |
| `drawdown` | Fall from a previous equity peak to a later trough. |
| `benchmark` | The comparison baseline, such as buy-and-hold `VN30` or buy-and-hold `BTC`. |

---

#### Alpha and signal terms

| Term | Meaning |
|---|---|
| `alpha` | Return that remains after accounting for common risk or a benchmark. |
| `factor` | A measurable property that may explain future returns, such as momentum or liquidity. |
| `feature` | A computed input column used by a model or rule. |
| `signal` | The rule output that suggests `buy`, `sell`, `hold`, or a score. |
| `strategy` | The complete trading policy that includes signal, execution, sizing, and risk rules. |

---

#### Worked derivation

- **Given:** `FPT` close yesterday `118000`, close today `120000`, and the `VN30` benchmark return today `0.80%`.
- **Compute asset return:** `120000 / 118000 - 1 ≈ 1.70%`.
- **Compute simple excess return:** `1.70% - 0.80% = 0.90%`.
- **Read:** before risk adjustment, `FPT` outperformed the benchmark by about `0.90%` that day.
- **Careful:** one day of excess return is not alpha; alpha needs repeated evidence and validation.

---

</details>

---

## Agent Mapping

### From raw data to answer

<details open>
<summary>The agent should move through a causal pipeline before it writes any conclusion.</summary>

---

#### Flow

- **Raw record:** `market_data_tool` loads OHLCV rows for `FPT` or `BTCUSDT`.
- **Quality check:** `data_quality_tool` checks missing timestamps, duplicates, and OHLC consistency.
- **Feature build:** `feature_tool` computes returns, volatility, moving averages, RSI, or volume features.
- **Signal build:** `signal_tool` converts features into `buy`, `sell`, or `hold` decisions.
- **Strategy execution:** `backtest_tool` simulates entries, exits, costs, slippage, and equity curve.
- **Validation:** `validation_gate_tool` checks whether the result is robust enough.
- **Answer:** `answer_composer` explains what passed, what failed, and what is still unanswered.

---

#### Worked example

- **Question:** analyze `FPT` trend over the last `60` trading days.
- **Input:** `60` daily OHLCV bars with no missing trading dates.
- **Feature:** `60d_return = 8.0%`, `20d_volatility = 1.6%` daily, `close 120000`, `SMA_20 116000`, `SMA_50 112000`.
- **Interpretation:** price is above both moving averages, so the trend filter leans upward.
- **Risk note:** the trend statement is weaker if the last `5` bars contain low volume or missing rows.
- **Output:** `trend = uptrend`, `confidence = medium`, `limitations = data_quality_and_recent_volume`.

---

#### When to answer unanswered

- **Missing data:** if `60` bars are requested but only `37` valid bars exist, the agent should not report a confident `60d_return`.
- **Bad timestamp:** if news timestamps and market timestamps use different timezones, the agent should not claim one caused the other.
- **Undefined strategy:** if user says `test momentum` but does not define entry and exit rules, the agent should ask for rule detail or mark strategy backtest as `unanswered`.
- **No tool output:** if no tool produced a metric, the LLM must not invent that metric.

---

</details>
