---
title: adjusted_ohlc_backtest_requirement
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Backtest Requirement

## Why This Matters

Backtests must use a price series that is consistent across dividends, splits,
and other corporate actions. Using adjusted close while leaving open, high, and
low unadjusted can create false signals, impossible fills, and distorted risk
metrics. Adjusted OHLC is mandatory before hardening Backtrader results.

This is a technical requirement only. It is not production readiness and not
financial advice.

## Adjustment Factor

When a trusted adjusted close is available, derive one factor per row:

```text
adjust_factor = adjusted_close / close
adjusted_open = open * adjust_factor
adjusted_high = high * adjust_factor
adjusted_low = low * adjust_factor
adjusted_close = close * adjust_factor
```

If adjusted close is not available, the factor must be derived from dividend,
split, and corporate action events before the row can be used in hardened
backtests.

## Raw Vs Adjusted Columns

The database should keep raw observed OHLCV values as source evidence and store
adjusted values in clearly named fields. Backtest feeds must consume adjusted
OHLC. Raw prices may remain available for audit, parsing validation, and source
comparison, but they should not drive strategy signals or fills once adjusted
series are required.

Required policy:

- raw close/open/high/low: retained as ingested evidence;
- adjustment factor: recorded with source and method;
- adjusted open/high/low/close: used by Backtrader;
- missing factor: block hardened backtest use for that row or symbol.

## Current Implementation

The local SQLite `daily_prices` table now has nullable adjusted OHLC fields:
`adjustment_factor`, `adjusted_open`, `adjusted_high`, `adjusted_low`, and
`adjusted_close`. Current Vietcap IQ gap-chart ingestion keeps these fields
empty because the source path does not yet provide a trusted adjusted close or
corporate-action factor. This is intentional: the system records the schema
slot without claiming raw prices are adjusted.

Pure utility functions in `src/trading_agent/ingestion/adjusted_ohlc.py`
compute an adjustment factor, scale OHLC values, and validate adjusted OHLC
consistency without network access or database mutation.

## Corporate Action Data

The adjustment factor must come from approved source logic for dividends,
splits, and other relevant corporate actions. The source, event date, effective
date, and calculation method should be auditable. If events conflict across
sources, the row should be flagged rather than silently adjusted.

## Validation Checks

Before a row enters a hardened backtest feed:

- adjusted OHLC fields are present for every backtest row;
- no `adjust_factor <= 0`;
- no missing adjusted close;
- `adjusted_high >= max(adjusted_open, adjusted_close)`;
- `adjusted_low <= min(adjusted_open, adjusted_close)`;
- adjusted OHLC remains internally consistent after rounding;
- rows with unresolved corporate-action status are excluded or blocked.

## Caveats

Current demo data can still carry `adjustment_status=unknown`. That is acceptable
for the local demo only. VN100 Backtrader work should wait until adjusted OHLC
schema, factor provenance, and validation tests are in place.

Not implemented yet:

- full dividend/split/corporate-action event engine;
- approved source for adjustment factors;
- Backtrader strategy optimizer;
- ETL Docker scheduler.
