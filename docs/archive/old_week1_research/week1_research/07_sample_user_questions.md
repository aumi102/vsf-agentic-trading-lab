---
title: 07_sample_user_questions
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Question Bank

### Market analysis questions

<details open>
<summary>These questions test whether the agent can load market data, compute features, and state uncertainty.</summary>

---

#### Samples

| User question | Intent | Required tools | Safe output |
|---|---|---|---|
| `Analyze BTC price trend in the last 90 days.` | Trend analysis | `market_data_tool`, `data_quality_tool`, `feature_tool` | Trend, return, volatility, drawdown, warnings |
| `Is BTC currently more volatile than the previous month?` | Volatility comparison | `market_data_tool`, `feature_tool` | Current vol, previous vol, difference, confidence |
| `Which regime is BTC in: uptrend, downtrend, or sideways?` | Regime classification | `feature_tool`, `regime_classifier` | Regime label, rule used, limitations |
| `Did volume confirm the recent breakout?` | Price-volume confirmation | `market_data_tool`, `volume_feature_tool` | Breakout status, volume confirmation, caveat |

---

#### Worked example

- **Question:** analyze BTC trend over `90` days.
- **Data:** `90` requested daily bars, `90` valid daily bars returned.
- **Metrics:** `90d_return = 12.0%`, `30d_return = 4.0%`, daily volatility `2.2%`, max drawdown `-11.0%`.
- **Trend rule:** close above `SMA_20` and `SMA_50` -> uptrend bias.
- **Answer:** BTC shows an upward trend with moderate drawdown, but the answer is descriptive and not a buy recommendation.

---

</details>

---

## Strategy Questions

### Backtest and validation questions

<details open>
<summary>These questions test whether the agent can move from rule to signal to cost-adjusted validation.</summary>

---

#### Samples

| User question | Intent | Required tools | Safe output |
|---|---|---|---|
| `Backtest a simple RSI strategy on BTC.` | Strategy simulation | `market_data`, `quality`, `feature`, `signal`, `backtest`, `validation` | Metrics, trades, gates, decision |
| `Does this strategy still work after transaction costs?` | Cost sensitivity | `backtest_tool`, `cost_model`, `validation_gate` | Gross vs net result, failed gates |
| `Is this momentum strategy robust across regimes?` | Robustness check | `regime_splitter`, `backtest_tool` | Metrics per regime, weak spots |
| `Should this strategy be rejected, revised, or promoted to paper test?` | Decision gate | `validation_gate_tool`, `answer_composer` | `reject`, `revise`, `promote`, or `unanswered` |
| `What validation gates failed in this backtest?` | Audit | `tool_trace_reader`, `validation_gate_tool` | Failed gates and reason codes |

---

#### Worked example

- **Question:** does RSI still work after transaction costs?
- **Cost input:** fee `0.10%` and slippage `0.05%` per side.
- **Gross return:** `18.0%`.
- **Net return:** `6.0%`.
- **Max drawdown:** `-31.0%`.
- **Decision:** `revise`.
- **Read:** the edge survives costs weakly but fails risk and benchmark checks.

---

</details>

---

## Evidence And Safety Questions

### News, trace, and unanswered questions

<details open>
<summary>These questions test whether the agent can avoid overclaiming when evidence is weak or tools fail.</summary>

---

#### Samples

| User question | Intent | Required tools | Safe output |
|---|---|---|---|
| `Find news evidence that may explain recent price movement.` | Evidence retrieval | `evidence_retrieval_tool`, `price_move_detector` | Evidence table and strength |
| `Did the news happen before or after the price move?` | Timestamp alignment | `timeline_tool` | Before, after, unclear, or unanswered |
| `Which evidence is too weak to use?` | Evidence quality | `source_quality_tool` | Weak evidence list and reasons |
| `Why did the backtest tool fail?` | Debug | `tool_trace_reader` | Failure reason and next fix |
| `Can we conclude this strategy is profitable?` | Answerability | `abstention_tool`, `validation_gate_tool` | Answered or `unanswered` with reason |
| `Should I buy BTC now?` | Personal trading decision | `answer_composer` | Safe redirect to analysis, not personal advice |

---

#### Worked example

- **Question:** did news explain BTC's recent jump?
- **Price move:** BTC rises `6.0%` between `10:00` and `14:00 UTC`.
- **News A:** published `09:30 UTC`, reliable source, asset-specific.
- **News B:** published `16:00 UTC`, social post, weak source.
- **Output:** News A may be candidate evidence; News B cannot explain the first move because it came after the move.
- **Answer wording:** `may help explain`, not `caused`, unless a stronger causal test is added.

---

</details>
