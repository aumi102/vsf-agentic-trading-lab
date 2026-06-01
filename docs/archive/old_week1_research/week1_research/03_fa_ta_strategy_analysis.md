---
title: 03_fa_ta_strategy_analysis
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Strategy Evidence Layers

### Thesis, signal, and strategy

<details open>
<summary>Market stories must be converted into testable rules before the agent can validate them.</summary>

---

#### Description

- **Cast:** `vn_breakout_note` = an analyst idea that `FPT` may continue upward because price breaks above a range with rising volume.
- **Thesis:** the story explaining why a move may happen.
- **Signal:** the measurable condition that fires, such as `close > 20d_high`.
- **Strategy:** the complete trading rule, including entry, exit, size, costs, and validation.
- **Reader trap:** a thesis is not a strategy; a convincing story can still fail when converted into rules.

---

#### Representation: Technical analysis

- **Input:** OHLCV, derived indicators, volume, volatility, support and resistance levels.
- **Examples:** moving average, RSI, MACD, Bollinger Bands, breakout, mean reversion, volume spike.
- **Sample:** `FPT` close `120000` is above `20d_high 119000` and volume `2.4m` is above `20d_avg_volume 1.5m`.
- **Signal:** `breakout_signal = 1` because price and volume both confirm.
- **Meaning:** the move has stronger evidence than a price-only breakout.
- **Careful:** TA signal still needs backtest; confirmation is not proof of future return.

---

#### Representation: Fundamental analysis

- **Input for equities:** revenue, profit, margin, debt, cash flow, valuation, sector, macro conditions.
- **Input for crypto:** on-chain activity, token supply, exchange flows, funding rate, open interest, regulation, news.
- **Sample equity thesis:** `FPT` earnings growth improves from `15%` to `22%`, while valuation stays near its sector average.
- **Signal candidate:** upgrade score from `0.2` to `0.7` if earnings growth beats threshold and price trend confirms.
- **Meaning:** FA gives a reason for the move, but does not automatically provide timing.
- **Careful:** FA and TA answer different questions; FA asks why value may change, TA asks how price is behaving now.

---

#### Representation: News evidence

- **Input:** article text, source, publication timestamp, asset mapping, relevance score, evidence strength.
- **Sample:** news published at `2026-05-28 09:00 UTC`; price breakout begins at `2026-05-28 14:00 UTC`.
- **Possible reading:** news happened before the price move, so it can be considered candidate evidence.
- **Weak reading:** if the news appears after the price move, it may explain narrative attention but not the cause of the first move.
- **Answer wording:** use `may help explain` for weak evidence; avoid `caused` unless the evidence standard is high.

---

</details>

---

## Key Terms

### Analysis terms

<details open>
<summary>These terms separate market interpretation from executable trading logic.</summary>

---

#### Table

| Term | Meaning |
|---|---|
| `TA` | Technical analysis; studies price, volume, and indicators. |
| `FA` | Fundamental analysis; studies business, macro, valuation, or token economics. |
| `thesis` | A reasoned market story that may or may not be testable yet. |
| `evidence` | Data, news, or metric that supports or weakens a thesis. |
| `signal` | A measurable trigger that can feed a trading rule. |
| `strategy` | A complete executable rule with entry, exit, sizing, and costs. |
| `regime` | Market environment that can change strategy behavior. |
| `abstention` | The agent's choice to avoid a conclusion when evidence is insufficient. |

---

#### X vs Y

- **Thesis vs signal:** thesis is the story; signal is the measurable trigger.
- **Signal vs strategy:** signal says `consider buying`; strategy says when, how much, when to exit, and what cost to assume.
- **Evidence vs proof:** evidence supports a claim; proof requires a much stronger causal design than a normal news lookup.

---

</details>

---

## Agent Workflow

### Turning analysis into a testable object

<details open>
<summary>The agent should lower a broad market idea into a structured hypothesis before backtesting.</summary>

---

#### Flow

- **Extract intent:** identify whether user asks for trend analysis, strategy test, news explanation, or decision gate.
- **Name the asset:** map `BTC`, `FPT`, or `VN30` to a concrete data source and timeframe.
- **Build hypothesis:** describe the thesis in one line.
- **Build signal:** define the exact data condition.
- **Build strategy:** define entry, exit, holding period, position sizing, transaction cost, and slippage.
- **Run validation:** pass the strategy to `backtest_tool` and `validation_gate_tool`.
- **Compose answer:** state result, caveats, failed gates, and whether the agent must answer `unanswered`.

---

#### Worked example

- **User idea:** `FPT breakout looks strong because volume increased`.
- **Hypothesis:** breakouts with volume confirmation may have better continuation than breakouts without volume.
- **Signal rule:** `close > 20d_high` and `volume > 1.5 × avg_volume_20d`.
- **Entry:** next day open.
- **Exit:** close below `SMA_10` or after `10` trading days.
- **Cost:** `0.15%` per side.
- **Backtest output:** net return `7.0%`, max drawdown `-12.0%`, trades `18`.
- **Decision:** `revise` because trade count is too small for a strong conclusion.

---

#### Unanswered rules

- **No timestamp:** news evidence without publication time cannot support a price-move explanation.
- **No rule:** a thesis without entry and exit cannot be backtested.
- **No cost:** a strategy result without transaction cost should not be promoted.
- **No source quality:** a blog or social post should not be treated as strong evidence unless mentor explicitly allows it.

---

</details>
