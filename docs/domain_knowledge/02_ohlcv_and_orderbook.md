---
title: 02_ohlcv_and_orderbook
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## OHLCV And Orderbook

### Key Terms
<details open>
<summary>OHLCV summarizes completed trading; order book shows current supply and demand.</summary>
---
#### Market data terms

| Term | Meaning |
|---|---|
| `open` | First traded price in a bar. |
| `high` | Highest traded price in a bar. |
| `low` | Lowest traded price in a bar. |
| `close` | Last traded price in a bar. |
| `volume` | Number of shares or contracts traded in a period. |
| `value` | Money value traded in a period. |
| `bid` | Price where buyers are willing to buy. |
| `ask` | Price where sellers are willing to sell. |
| `spread` | Difference between ask and bid. |
| `depth` | Available quantity at bid and ask levels. |
| `slippage` | Difference between expected execution price and actual execution price. |

---
#### OHLCV vs order book

- **OHLCV** is historical summary; it tells what already traded.
- **order book** is live or snapshot liquidity; it tells what is currently offered to buy and sell.
- **OHLCV** is enough for daily strategy research.
- **order book** matters more for execution, intraday trading, and liquidity-sensitive strategies.

---
</details>

### Data Representation
<details open>
<summary>The same stock can have daily bars and order-book snapshots with different schemas.</summary>
---
#### Representation: OHLCV bar

| Field | Meaning |
|---|---|
| `security_id` | Stable instrument ID. |
| `trade_date` | Trading day. |
| `open` | First traded price. |
| `high` | Highest traded price. |
| `low` | Lowest traded price. |
| `close` | Last traded price. |
| `volume` | Shares traded, after unit normalization. |
| `value` | Cash value traded. |
| `source_id` | Source batch. |

---
#### Representation: order-book snapshot

| Field | Meaning |
|---|---|
| `security_id` | Stable instrument ID. |
| `timestamp` | Exact snapshot time. |
| `bid_price_1` | Best buy price. |
| `bid_size_1` | Quantity available at best bid. |
| `ask_price_1` | Best sell price. |
| `ask_size_1` | Quantity available at best ask. |
| `spread` | `ask_price_1 - bid_price_1`. |
| `source_id` | Source batch. |

---
#### Worked example

- `FPT` best bid is `95.0` and best ask is `95.2`.
- Spread is `95.2 - 95.0 = 0.2`.
- If the expected execution is `95.0` but the actual buy fills at `95.2`, slippage is `0.2 / 95.0 = 0.21%`.
- Read: a profitable backtest can fail in real execution if spread and slippage are ignored.

---
</details>

### Usage In Agent
<details open>
<summary>OHLCV feeds research; order book feeds execution realism.</summary>
---
#### Tool mapping

| Data | Tool | Output |
|---|---|---|
| OHLCV | `market_data_tool` | historical bar table. |
| OHLCV | `feature_tool` | return, MA, RSI, volatility, volume ratio. |
| OHLCV | `backtest_tool` | simulated trades and metrics. |
| order book | `liquidity_tool` | spread, depth, estimated slippage. |
| order book | `execution_tool` | execution-cost estimate. |

---
#### MVP rule

- Use daily OHLCV for the first backtest MVP.
- Record that order book is future work unless the mentor requires execution realism early.
- Add simple slippage assumptions even without order book, such as `5` to `20` basis points.
- Do not claim a strategy is executable at scale without liquidity and depth checks.

---
</details>

### Risks And Questions
<details open>
<summary>The biggest risk is treating clean daily prices as proof of executable trades.</summary>
---
#### Risks

- **unit risk** = volume can be shares, lots, or contracts depending on source.
- **liquidity risk** = high close-to-close return may not be tradable at size.
- **stale book risk** = delayed order-book snapshots can misrepresent real depth.
- **lookahead risk** = using close price for same-day entry can leak future information.

---
#### Questions to ask mentor

- Should the first demo use daily OHLCV only?
- Is order book required for Vietnamese market MVP?
- What default slippage assumption should be used when order book is unavailable?
- Should volume be normalized to shares or kept in source units plus normalized units?

---
</details>
