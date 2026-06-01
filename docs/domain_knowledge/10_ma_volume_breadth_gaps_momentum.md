---
title: 10_ma_volume_breadth_gaps_momentum
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Trend Tools

### Moving averages and bands

<details open>
<summary>Moving averages define direction; bands and channels add volatility context around that direction.</summary>

---

#### Description

- **Cast:** `BTC_trend_stack` = `BTCUSDT` daily chart with moving averages, volume confirmation, breadth proxy, gaps, and momentum.
- **Moving average:** smoothed price over a lookback window.
- **Purpose:** reduce noise and identify trend direction, support, resistance, or crossover signals.
- **Reader trap:** moving averages work better in trending markets and can whipsaw in sideways markets.

---

#### Moving average table

| Type | Meaning | Main behavior |
|---|---|---|
| `SMA` | Simple average of past prices | slower and easy to interpret |
| `EMA` | Exponential average with more weight on recent prices | reacts faster to recent changes |
| `Wilder` | Wilder-style smoothing used in indicators like RSI | smoother and more delayed |
| `Centered MA` | average shifted toward the middle of a window | useful for cycle study, not safe for live crossover signals |

---

#### Worked example

- **Close:** `70000`.
- **SMA_20:** `68000`.
- **SMA_50:** `65000`.
- **Read:** price is above both averages, so trend filter points up.
- **Crossover note:** a fast MA crossing above a slow MA can signal trend improvement.
- **Whipsaw note:** in a sideways market, repeated crossovers can create losses.

---

#### Bands and channels

- **Bollinger Bands:** volatility band around moving average, often using standard deviation.
- **Keltner Channels:** volatility channel often based on average true range.
- **STARC Bands:** bands around a moving average using volatility logic.
- **Breakout reading:** price closing outside an outer band can indicate trend expansion.
- **Careful:** outer-band breakouts can also reverse; volume and follow-through matter.

---

</details>

---

## Confirmation Tools

### Volume, breadth, and supply-demand

<details open>
<summary>Trend direction becomes more credible when participation confirms it.</summary>

---

#### Volume indicators

| Indicator | What it combines | Simple use |
|---|---|---|
| `OBV` | up/down price direction and volume | detects accumulation or distribution |
| `Accumulation/Distribution` | close location inside bar and volume | estimates buying or selling pressure |
| `Force Index` | price change and volume | measures strength of buyers or sellers |
| `VWAP` | price weighted by volume | execution benchmark and intraday fair price reference |

---

#### Breadth indicators

- **Breadth:** checks whether many assets confirm the index direction.
- **Advance-decline:** compares the number of rising and falling assets.
- **Extreme rule sample:** readings around `+400` or `-400` in a specific advance-decline system can mark overbought or oversold states, but the exact threshold is system-specific.
- **Three-day decline idea:** many declining stocks for several days may set up mean reversion, but only if tested.

---

#### Worked example

- **Index:** a VN stock basket rises `1.2%`.
- **Components:** `22` of `30` stocks rise.
- **Breadth ratio:** `22 / 30 ≈ 73.3%`.
- **Volume:** basket volume is `1.4×` its `20`-day average.
- **Read:** both breadth and volume confirm participation.
- **Agent output:** `trend_confirmation = strong`, but final strategy decision still depends on backtest and risk.

---

</details>

---

## Entry And Exit Timing

### Gaps, bar patterns, momentum, and cycles

<details open>
<summary>Short-term patterns help time entries and exits, but they should not replace validation.</summary>

---

#### Gap table

| Gap type | Where it appears | Simple read |
|---|---|---|
| `breakaway gap` | price exits a range | possible start of new trend |
| `runaway gap` | middle of an existing trend | trend continuation and possible measuring clue |
| `exhaustion gap` | late in an extended trend | possible final burst before reversal |

---

#### Bar pattern table

| Pattern | Simple read | Caution |
|---|---|---|
| `one-bar reversal` | new high or low but close reverses | needs context near support or resistance |
| `two-bar reversal` | two bars together reject prior direction | still needs follow-through |
| `inside bar` | pause or compression | breakout direction matters |
| `outside bar` | volatility expansion | direction of close matters |
| `dead cat bounce` | weak rebound after large fall | can trap early buyers |

---

#### Momentum and cycle example

- **Momentum formula:** `momentum_n = close_today - close_n_days_ago`.
- **Sample:** close today `70000`, close `20` days ago `64000` -> momentum `6000`.
- **Dominant cycle:** if peaks are about `40` days apart, test momentum windows near `20` days and `10` days.
- **Reason:** `20` is half-cycle and `10` is quarter-cycle.
- **Read:** momentum helps detect acceleration or slowdown so the agent can avoid entering after trend exhaustion.

---

#### Net strategy reading

- **Direction:** moving averages define bias.
- **Confirmation:** volume and breadth check participation.
- **Entry:** gaps and bar patterns refine timing.
- **Exit:** momentum slowdown or support break can trigger exit.
- **Validation:** only backtesting can tell whether this stack has historical edge.

---

</details>
