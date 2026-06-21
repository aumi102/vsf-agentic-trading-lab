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

PR #48 is feed contract and preview only. The feed preview is allowed only after
a strict adjusted OHLC execution audit, the audit report must match the DB and
requested symbols, and every requested symbol must have eligible adjusted rows.
Date and `max_rows` inputs are validated, not silently corrected. There is no
Backtrader implementation, no strategy execution, no full VN100, and no
production readiness claim.

## Preconditions

- Reviewed evidence dry-run report passed.
- Local execute readiness passed on an explicit local DB.
- Adjusted OHLC execution audit passed in strict mode.
- Audit report has `backtest_planning_gate=pass`.

## Audit Report Gate

The audit report is not accepted just because it says `status=ok`. The feed
gate requires the strict audit metadata that PR #47 emits and cross-checks it
against the current request:

- audit report is a JSON object;
- audit `status=ok` and `backtest_planning_gate=pass`;
- audit `evidence_mode=strict`;
- audit `required_evidence_present=true`;
- audit `symbols` includes every requested symbol;
- audit `db_path`, when present, matches the current `db_path`;
- audit `unadjusted_rows=0`;
- audit `readiness_status=ok`;
- audit `backtest_gate=pass`;
- audit `validation_status=ok`;
- audit `db_mutation_made=true`.

Missing strict audit metadata blocks the preview rather than weakening the gate.
Representative block reasons: `audit_evidence_mode_not_strict:<value>`,
`audit_required_evidence_not_present`, `audit_missing_symbol:<SYMBOL>`,
`audit_db_path_mismatch`, `audit_unadjusted_rows_present:<N>`,
`audit_readiness_status_not_ok:<value>`, `audit_backtest_gate_not_pass:<value>`,
`audit_validation_status_not_ok:<value>`, `audit_db_mutation_not_made`, and
`audit_missing_required_field:<field>`.

## Symbol Coverage Gate

Every requested symbol must have at least one eligible adjusted row in the date
range. A symbol is missing when it has no rows, or has rows but none are
eligible because adjusted OHLC is null, provenance is missing, or
`quality_status != ok`. Any missing symbol sets `status=not_ready`, adds
`missing_requested_symbol:<SYMBOL>`, and lists it under `missing_symbols`.

## Date And max_rows Validation

- `start_date` and `end_date`, when provided, must be ISO `YYYY-MM-DD`;
- `start_date > end_date` fails with `invalid_date_range:start_after_end`;
- `max_rows <= 0` fails with `max_rows_must_be_positive` and is never silently
  coerced to `1`.

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

Top-level fields:

- `status`
- `feed_contract_version=adjusted_ohlc_feed_v1`
- `source_price_basis=adjusted_ohlc`
- `symbols`
- `missing_symbols`
- `symbols_with_eligible_rows`
- `row_count`
- `total_eligible_rows`
- `audit_status`
- `audit_backtest_planning_gate`
- `reasons`
- `caveats`

Each row:

- `symbol`
- `datetime`
- `open` / `high` / `low` / `close` (adjusted OHLC)
- `volume`
- `source_price_basis=adjusted_ohlc`
- `adjustment_factor`
- `adjustment_source_id`
- `adjustment_raw_path`
- `adjustment_method`

Rows never include `raw_open/raw_high/raw_low/raw_close`, signal fields, trade
fields, PnL/equity fields, or strategy fields. Raw OHLC is diagnostics only and
is not exposed as a trading price.

## Blocking Cases

- any adjusted price is null;
- missing adjustment provenance;
- a requested symbol has no eligible adjusted rows;
- readiness or audit is not `ok`;
- audit lacks `backtest_planning_gate=pass`;
- audit metadata is stale, mismatched, or missing;
- invalid date format, `start_date > end_date`, or `max_rows <= 0`;
- no strict evidence;
- full VN100 requested;
- Backtrader implementation requested before this contract is accepted.

## Preview Command

```bash
python scripts/preview_adjusted_ohlc_backtest_feed.py --db-path path/to/local.sqlite --symbols FPT,VNM,VCB --start-date 2026-01-01 --end-date 2026-12-31 --audit-report reports/reviewed_evidence/adjusted_ohlc_audit.json --output-json reports/reviewed_evidence/feed_preview.json
```

This preview is read-only and maps adjusted OHLC into the `open/high/low/close`
fields expected by a later feed. It does not run Backtrader or a strategy.

## Next Step

`docs/backtest/adjusted_ohlc_feed_to_backtest_dry_run.md` consumes this feed
preview JSON and prepares a backtest input contract for a research dry-run. That
layer validates the adjusted feed plus explicit transaction-cost and slippage
assumptions (slippage bounded by HOSE/HSX +/-7% and UPCoM +/-15%). It is
preparation only: it does not implement Backtrader, optimize a strategy, run
full VN100, or produce investment advice.
