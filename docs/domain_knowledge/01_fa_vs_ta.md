---
title: 01_fa_vs_ta
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## FA Vs TA

### Key Terms
<details open>
<summary>FA explains business quality; TA explains market behavior and timing.</summary>
---
#### Analysis terms

| Term | Meaning |
|---|---|
| `FA` | Fundamental Analysis: analysis of business, financial statements, industry, macro, valuation, and news. |
| `TA` | Technical Analysis: analysis of price, volume, trend, indicators, patterns, and order flow. |
| `thesis` | A reasoned claim about why an asset might be attractive or risky. |
| `signal` | A rule-based output such as buy, sell, hold, or score. |
| `strategy` | A complete rule set with entry, exit, sizing, cost, and risk controls. |
| `evidence` | Data or document support for a claim. |

---
#### FA vs TA

- **FA** asks whether the asset deserves attention based on business and macro fundamentals.
- **TA** asks when the market behavior gives a tradable entry or exit.
- **FA without TA** can identify a good company at a bad entry price.
- **TA without FA** can find a tradable pattern without understanding business risk.
- **agent rule** = a thesis is not a signal, and a signal is not yet a full strategy.

---
</details>

### Mechanism
<details open>
<summary>The agent should convert FA and TA into separate evidence objects before combining them.</summary>
---
#### Cast

- `FPT` = example stock.
- `fa_view` = strong revenue growth, healthy margins, and positive industry outlook.
- `ta_view` = price above MA200 but RSI is `78`, which may indicate short-term overbought pressure.
- `strategy_question` = should the system buy now, wait, or test a pullback strategy?

---
#### FA path

- **input** = financial reports, company reports, industry reports, macro context, and valuation fields.
- **processing** = extract revenue growth, profit growth, debt, cash flow, margin, analyst recommendation, and risk comments.
- **output** = a thesis with confidence and evidence links.
- **meaning** = FA can justify why `FPT` belongs in a watchlist.

---
#### TA path

- **input** = OHLCV, indicators, trend state, volume, support and resistance, and volatility.
- **processing** = compute MA, RSI, return, drawdown, volume ratio, breakout, and regime.
- **output** = an entry/exit signal or a warning.
- **meaning** = TA can decide whether current market behavior supports action now.

---
#### Combined read

- Strong FA plus weak TA -> `watchlist` or `wait_for_pullback`.
- Weak FA plus strong TA -> `short_term_trade_candidate`, not long-term conviction.
- Strong FA plus strong TA -> `promote_to_backtest`, not automatic buy.
- Weak FA plus weak TA -> `reject` or `unanswered` depending on missing data.

---
</details>

### Worked Example
<details open>
<summary>A good company can still be a poor immediate trade if the timing signal is weak.</summary>
---
#### Example values

- `FPT` report suggests revenue growth of `18%` year-over-year.
- The stock is above MA200, which supports a long-term uptrend read.
- RSI is `78`, above the common overbought threshold of `70`.
- Volume is `60%` above its `20`-day average on the breakout day.
- The agent has not yet run a backtest for the proposed entry rule.

---
#### Interpretation

- FA thesis is positive because business growth is strong.
- TA trend is positive because price is above long-term moving average.
- TA timing is risky because RSI is high.
- Volume supports participation, but it does not prove future return.
- Final state should be `promote_to_backtest`, not `buy now`, because the rule has not been validated.

---
</details>

### Risks And Questions
<details open>
<summary>The main risk is mixing narrative confidence with validated strategy confidence.</summary>
---
#### Risks

- **narrative risk** = a persuasive company story can hide weak entry timing.
- **indicator risk** = an indicator can look precise while being overfit.
- **causality risk** = news and reports can explain a move after it already happened.
- **advice risk** = the agent may sound like it is giving personal buy/sell advice.
- **net** = FA and TA should feed structured hypotheses, then backtest and risk gates decide the next state.

---
#### Questions to ask mentor

- Should MVP combine FA and TA, or start with TA-only backtest first?
- Which FA fields are mandatory for a Vietnamese equity thesis?
- Should analyst target price be treated as a feature, evidence, or only reference text?
- Should the final answer use states such as `watchlist`, `wait`, and `promote_to_backtest`?

---
</details>
