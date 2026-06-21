---
title: adjusted_ohlc_backtest_feed_contract
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Backtest Feed Contract

## Purpose

This contract defines what a small-symbol adjusted OHLC backtest feed may read
after reviewed evidence, local execute readiness, and strict adjusted OHLC audit
all pass. It does not implement Backtrader, strategy templates, or full VN100.

## Preconditions

- Reviewed evidence dry-run report passed.
- Local execute readiness passed on an explicit local DB.
- Adjusted OHLC execution audit passed in strict mode.
- Audit report has `backtest_planning_gate=pass`.

## Required Columns

- `symbol`
- `trade_date`
- `adjusted_open`
- `adjusted_high`
- `adjusted_low`
- `adjusted_close`
- `volume`
- `adjustment_factor`
- `adjustment_source_id`
- `adjustment_raw_path`
- `adjustment_method`

## Forbidden Price Inputs

Raw `open`, `high`, `low`, and `close` must not be used as trading price fields
once adjusted OHLC is required. Raw OHLC is diagnostics only.

## Required Filters

- explicit symbol whitelist;
- date range;
- adjusted rows only;
- `quality_status=ok`;
- audit `status=ok`;
- audit `backtest_planning_gate=pass`.

## Preview Output Schema

- `symbol`
- `datetime`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `source_price_basis=adjusted_ohlc`
- `caveats`

## Blocking Cases

- any adjusted price is null;
- missing adjustment provenance;
- readiness or audit is not `ok`;
- audit lacks `backtest_planning_gate=pass`;
- no strict evidence;
- full VN100 requested;
- Backtrader implementation requested before this contract is accepted.

## Preview Command

```bash
python scripts/preview_adjusted_ohlc_backtest_feed.py --db-path path/to/local.sqlite --symbols FPT,VNM,VCB --start-date 2026-01-01 --end-date 2026-12-31 --audit-report reports/reviewed_evidence/adjusted_ohlc_audit.json --output-json reports/reviewed_evidence/feed_preview.json
```

This preview is read-only and maps adjusted OHLC into the `open/high/low/close`
fields expected by a later feed. It does not run Backtrader or a strategy.
