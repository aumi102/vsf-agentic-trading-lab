---
title: 09_candles_multi_timeframe
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Candlestick Patterns

### Reversal and continuation clues

<details open>
<summary>Candles are short-term behavior clues; they need trend context and confirmation before becoming signals.</summary>

---

#### Description

- **Cast:** `FPT_weekly_daily_setup` = weekly trend up, daily pullback to support, and a bullish candle pattern near that support.
- **Candlestick pattern:** a shape made from one or more OHLC bars.
- **Purpose:** detect hesitation, rejection, continuation, or possible reversal.
- **Reader trap:** a candle pattern is not a full strategy until entry, exit, timeframe, and risk are defined.

---

#### Pattern table

| Pattern family | Example | Context | Simple read |
|---|---|---|---|
| Engulfing | bullish or bearish engulfing | after a prior trend | opposite side overwhelms previous candle body |
| Dark cloud and piercing | dark cloud cover, piercing line | near trend extremes | second candle rejects prior direction |
| Star patterns | evening star, morning star | after extended trend | small middle candle shows hesitation |
| Harami | inside body pattern | after momentum move | momentum slows and indecision appears |
| Tweezers | equal highs or lows | near support or resistance | repeated rejection of a level |
| Three-candle patterns | three black crows, three white soldiers | trend change or continuation | persistent selling or buying pressure |
| Continuation patterns | rising three methods, tasuki gap | within existing trend | pause before old trend resumes |

---

#### Worked example

- **Prior trend:** `FPT` falls from `125000` to `115000`.
- **Day 1 candle:** red body from `118000` open to `115500` close.
- **Day 2 candle:** green body from `115000` open to `119000` close.
- **Pattern:** bullish engulfing because day 2 body covers day 1 body.
- **Read:** buyers rejected lower prices, but confirmation needs higher timeframe trend or next-bar follow-through.

---

</details>

---

## Multi-Timeframe Analysis

### Higher timeframe controls lower timeframe

<details open>
<summary>Multi-timeframe analysis uses the big chart for direction and the smaller chart for execution.</summary>

---

#### Three-step filter

- **Step A — higher timeframe:** use weekly chart to define main trend.
- **Step B — trading timeframe:** use daily chart to find pullback or setup.
- **Step C — lower timeframe:** use `60`-minute chart to find breakout or entry trigger.
- **Mechanism:** the larger timeframe sets the tide; the smaller timeframe chooses the wave to ride.
- **Careful:** lower-timeframe signals against the higher-timeframe trend need stricter risk control.

---

#### Worked example

- **Weekly chart:** `FPT` above rising `SMA_20`; main trend up.
- **Daily chart:** price pulls back from `122000` to support near `116000`.
- **Hourly chart:** price breaks above short-term resistance at `117500`.
- **Candle confirmation:** bullish engulfing appears near daily support.
- **Signal:** long setup is allowed because higher timeframe and candle confirmation align.
- **Invalidation:** close below `115000` breaks the support thesis.

---

#### Gann and higher timeframe rule

- **Krausz and Gann-style principle:** every timeframe has its own structure, but the higher timeframe has more authority.
- **Support and resistance:** weekly levels are usually more important than intraday levels.
- **Gann swings:** can be used to label trend direction from the highest chosen timeframe.
- **Agent output:** include the timeframe hierarchy used, not only the final signal.

---

</details>

---

## Momentum Confirmation

### KST and ROC across cycles

<details open>
<summary>Momentum indicators help check whether several cycles point in the same direction.</summary>

---

#### Key terms

| Term | Meaning |
|---|---|
| `ROC` | Rate of change; current price compared with price `n` periods ago. |
| `KST` | Know Sure Thing; weighted blend of multiple ROC measures. |
| `cycle` | Repeating market rhythm measured from peaks or troughs. |
| `confirmation` | Multiple tools or timeframes support the same directional view. |

---

#### Worked example

- **Short ROC:** `10`-day ROC = `3.0%`.
- **Medium ROC:** `20`-day ROC = `5.0%`.
- **Long ROC:** `40`-day ROC = `8.0%`.
- **Read:** all three momentum windows point upward.
- **Agent decision:** signal confidence increases, but the trade still needs exit and risk rules.

---

#### Takeaway

- **Candles:** useful for local trigger.
- **Higher timeframe:** useful for direction.
- **Momentum:** useful for confirming acceleration or slowdown.
- **Trading Agent use:** combine them into structured evidence, then backtest before promotion.

---

</details>
