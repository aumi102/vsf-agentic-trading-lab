---
title: adjusted_factor_source_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted Factor Source Review

## Current Evidence

This review is based on tracked repo code, parser tests, and docs only. No live
network fetch or full-universe crawl was run.

The current Vietcap IQ gap-chart parser reads daily arrays for timestamp,
open, high, low, close, volume, accumulated volume, and accumulated value. It
marks `price_basis=source_reported` and `adjustment_type=unknown`. The parser
summary explicitly says adjusted and unadjusted price values are not separated,
and dividend, split, corporate-action, and adjustment-factor fields are not
visible.

Current ingestion therefore leaves `adjustment_factor`, `adjusted_open`,
`adjusted_high`, `adjusted_low`, and `adjusted_close` empty. That is correct:
the repo must not pretend raw close is adjusted close.

## What Cannot Be Concluded Yet

- Gap-chart OHLC cannot be treated as adjusted without source proof.
- No tracked fixture currently proves that gap-chart contains adjusted close.
- No tracked gap-chart field carries dividend, split, rights, or bonus event
  terms.
- Current demo DB is not adjusted-backtest-ready.

## Possible Source Paths

1. Use adjusted close from a trusted OHLCV endpoint, then derive
   `adjustment_factor = adjusted_close / close` for each row.
2. Use corporate-action events: cash dividends, stock dividends, splits,
   rights, bonus issues, and other exchange/vendor action records.
3. Use an official or paid source if public payloads do not provide enough
   auditable adjustment evidence.

## Risks

- Dividend timing can depend on ex-date, record date, payment date, and source
  convention.
- Split and stock-dividend ratios must be normalized consistently.
- Rights issues and bonus shares can require source-specific handling.
- Current VN100 membership introduces a survivorship caveat for later research.
- Adjusted high/low/open/close must remain internally consistent after factor
  application and rounding.

## Recommendation

The controlled dry-run probe is documented in
`docs/data_platform/adjusted_factor_source_probe_plan.md` and implemented by
`scripts/probe_adjusted_factor_sources.py`. The probe reports candidate evidence
levels only; it does not verify source usability or populate adjusted OHLC.
Follow-up evidence capture records local payload hashes and candidate field
summaries, but still does not make a source usable. After captured evidence is
reviewed, integrate one verified factor source into ETL. The readiness gate
should remain blocked until adjusted OHLC rows are populated, validated, and
traceable to `source_id` and `raw_path`. Backtrader/VN100 strategy work should
wait for that gate to pass.
