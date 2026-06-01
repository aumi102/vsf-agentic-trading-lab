---
title: 07_volume_and_open_interest
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Volume As Confirmation

### What volume measures

<details open>
<summary>Volume is the traded quantity behind a price move, so it helps judge whether the move has participation.</summary>

---

#### Description

- **Cast:** `FPT_breakout_day` = `FPT` closes above resistance at `120000` with `2.4m` shares traded.
- **Volume:** total quantity traded during a period, usually a day for daily charts.
- **Purpose:** check whether a price move has broad participation or is only a thin move.
- **Reader trap:** high volume confirms participation; it does not guarantee the next price direction.

---

#### Key terms

| Term | Meaning |
|---|---|
| `market volume` | Actual traded quantity in a market during a period. |
| `tick volume` | Count of ticks or trade events; in some markets it proxies activity when true volume is unavailable. |
| `average volume` | Moving average of volume that smooths noisy daily spikes. |
| `float` | Shares held by the public and available to trade. |
| `restricted shares` | Shares held by insiders, founders, state owners, or locked holders that are not freely traded. |
| `open interest` | Number of outstanding futures or options contracts that remain open. |

---

#### Float vs company-held shares

- **Float:** shares that public investors can actually buy and sell.
- **Company or insider-held shares:** shares held by founders, treasury, strategic owners, or restricted holders.
- **Analogy:** float is the water moving in the river; locked shares are water frozen on the bank.
- **Trading meaning:** the same volume is more meaningful when float is small because a larger share of tradable supply changed hands.

---

</details>

---

## Price And Volume

### Four common readings

<details open>
<summary>Price-volume combinations are useful because they connect direction with participation.</summary>

---

#### Matrix

| Price | Volume | Simple read | Trading caution |
|---|---|---|---|
| Up | Up | demand confirms the up move | still needs resistance and risk check |
| Up | Down | uptrend may be weakening | possible exhaustion or thin rally |
| Down | Up | selling pressure increases | possible distribution or panic selling |
| Down | Down | selling pressure may be fading | possible base formation, not automatic buy |

---

#### Worked example

- **Resistance:** `FPT` struggles near `120000` for `20` sessions.
- **Breakout day:** close `122000`, volume `2.4m` shares.
- **Average volume:** `1.5m` shares.
- **Volume ratio:** `2.4m / 1.5m = 1.6`.
- **Read:** breakout has volume confirmation because activity is `1.6×` normal.
- **Next step:** pass the signal to a backtest; do not promote from one chart event.

---

#### Agent output

- **Input:** OHLCV rows, average volume lookback, breakout level.
- **Output:** `volume_confirmation = true`, `volume_ratio = 1.6`, `warning = single_event_not_validated`.
- **Next block:** `signal_tool` or `backtest_tool`.
- **Unanswered case:** if volume data is missing or from a weak source, the agent cannot confirm the breakout.

---

</details>

---

## Volume Tools

### VWAP, equivolume, volume at price, and open interest

<details open>
<summary>Each volume tool answers a different question about participation, execution, or derivatives positioning.</summary>

---

#### Tool table

| Tool | What it shows | Sample reading | Agent use |
|---|---|---|---|
| `VWAP` | Average price weighted by volume | buy execution below VWAP is better than market average | execution benchmark |
| `equivolume` | bar width shows volume and bar height shows range | wide and tall bar shows high activity and big range | visual confirmation |
| `volume at price` | volume traded at each price level | point of control at `118000` | support and resistance map |
| `open interest` | open futures or options contracts | OI rises with price | derivatives participation |

---

#### VWAP worked example

- **Trade slices:** `100` shares at `100`, `200` shares at `101`, `300` shares at `102`.
- **Total value:** `100×100 + 200×101 + 300×102 = 60800`.
- **Total volume:** `600` shares.
- **VWAP:** `60800 / 600 ≈ 101.33`.
- **Read:** an institutional desk buying below `101.33` executed better than the day's volume-weighted average.

---

#### Open interest vs volume

- **Volume:** how many contracts traded today.
- **Open interest:** how many contracts remain open after trading.
- **Example:** `1000` futures contracts trade today, but open interest rises by only `200`; many trades may have closed existing positions.
- **Price up plus OI up:** new participation supports the trend.
- **Price up plus OI down:** short covering may be driving the move, so continuation evidence is weaker.

---

</details>
