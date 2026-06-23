# Adjusted OHLC Quality Audit

QuestDB: `http://localhost:9000`
Scope: `FPT,VNM,HPG`

## Column availability

Required adjusted OHLC columns: `adjusted_open`, `adjusted_high`, `adjusted_low`, `adjusted_close`.

Available adjusted columns: `adjusted_open, adjusted_high, adjusted_low, adjusted_close`
Missing adjusted columns: `none`

## Interpretation

`source_adjustment_unverified` is a caveat, not a hard failure: current source rows carry `adjusted_price_missing_warn` and/or adjusted close equals close for nearly all rows.

## Per-symbol audit

| Symbol | Rows | Status | corr(high, adj_high) | corr(close, adj_close) | corr(high/close, adj_high/adj_close) | max factor diff | adjustment_status |
|---|---:|---|---:|---:|---:|---:|---|
| `FPT` | 4,860 | `source_adjustment_unverified` | 1.000000 | 1.000000 | 1.000000 | 0 | `adjusted_price_missing_warn` |
| `HPG` | 4,631 | `source_adjustment_unverified` | 1.000000 | 1.000000 | 1.000000 | 0 | `adjusted_price_missing_warn` |
| `VNM` | 5,084 | `source_adjustment_unverified` | 1.000000 | 1.000000 | 1.000000 | 0 | `adjusted_price_missing_warn` |

## Caveats

- Audit is read-only; it does not alter QuestDB tables.
- Median factor differences use QuestDB `approx_percentile(..., 0.5)`.
- If source adjusted OHLC remains identical to raw OHLC, downstream backtests should keep the adjusted-price caveat visible.
