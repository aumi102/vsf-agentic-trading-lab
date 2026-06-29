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

Mentor policy is confirmed: adjusted price is mandatory, and the full OHLC
series must be adjusted, not only close. When adjusted price is available,
derive one factor per row:

```text
adjust_factor = adjusted_close / close
adjusted_open = open * adjust_factor
adjusted_high = high * adjust_factor
adjusted_low = low * adjust_factor
adjusted_close = close * adjust_factor
```

The factor must reflect dividend/split/corporate-action logic and be traceable
to source evidence. If adjusted price is not available, the factor must be
derived from dividend, split, and corporate action events before the row can be
used in hardened backtests.

## Raw Vs Adjusted Columns

The database should keep raw observed OHLCV values as source evidence and store
adjusted values in clearly named fields. Backtest feeds must consume adjusted
OHLC. Raw prices may remain available for audit, parsing validation, and source
comparison, but they should not drive strategy signals or fills once adjusted
series are required.

Required policy:

- raw close/open/high/low: retained as ingested evidence;
- adjustment factor: recorded with separate factor source, raw path, and method;
- adjusted open/high/low/close: used by Backtrader;
- missing factor: block hardened backtest use for that row or symbol.

## Trading Core Gate Scripts

A read-only adjusted OHLCV readiness check gates strategy signal generation
and backtest execution. Scripts are in `scripts/`:

| Script | Purpose |
|---|---|
| `adjusted_ohlc_readiness.py` | Per-symbol gate from `adjusted_daily_prices`. Reports `PASS`/`BLOCKED`/`PARTIAL`. `--source-policy approved_only|prototype_allowed`. Default `approved_only` (vnstock blocked). `--require-all` exits 1 if any symbol blocked. |
| `run_trading_signals.py` | Computes BUY/SELL/HOLD/BLOCKED per symbol. PASS symbols use `adjusted_daily_prices`. BLOCKED symbols return `signal=BLOCKED` with reason. `--require-all` exits 1. |
| `run_custom_backtest.py` | Custom no-lookahead backtest engine. PASS symbols run from `adjusted_daily_prices`. BLOCKED symbols skipped with reason. `--require-all` exits 1. Supports `baseline_buy_hold_v1` (engine validation only, not alpha). |
| `run_trading_core_demo.py` | End-to-end demo: readiness -> signals -> backtest. Shows all symbols with status. PARTIAL if mixed. |

Signal contract fields: `symbol`, `as_of`, `strategy`, `signal` (BUY/SELL/HOLD/BLOCKED),
`score`, `features_used`, `reason`, `risk_flags`, `data_source`, `gate` (pass/blocked), `caveats`.

Backtest contract v1 fields: `portfolio` ({cash, position, equity, bars_count}),
`trade_ledger` ({date, symbol, side, price, quantity, value}),
`metrics` ({total_return_pct, sharpe_ratio, sortino_ratio, profit_factor, max_drawdown_pct, win_rate, total_trades, cost_slippage_assumptions}),
`execution_rule` (no-lookahead: signal at bar t fires at bar t+1 open price).

All four scripts support `--json` for machine-parseable output.

### PARTIAL semantics

Requests with mixed PASS/BLOCKED symbols return `status=PARTIAL` (exit 0 without `--require-all`).
`--require-all` exits 1 if any requested symbol is blocked.

Never fallback to raw `daily_prices` for blocked symbols. Only `adjusted_daily_prices` is approved
for trading computation.

### Source policy

`--source-policy approved_only` (default): vnstock-derived rows do NOT count as PASS.
Symbols with `adjustment_source` containing "vnstock" are classified `BLOCKED_UNAPPROVED_SOURCE`.
`--source-policy prototype_allowed`: vnstock rows count as `PASS_PROTOTYPE` with caveat.
Per-symbol fields include: `adjustment_source`, `source_policy`, `source_approval_status`, `blocked_reason`.

Current status (approved_only):
- FPT, VNM: `BLOCKED_UNAPPROVED_SOURCE` (vnstock-derived, not approved)
- HPG, VCB, CTG, VHM: `BLOCKED_ADJUSTED_SOURCE_MISSING` (no corporate action source)
- No symbol has an approved adjusted OHLC source under the default policy.

QuestDB `event_news_items` and `event_news_raw_payloads` were audited (2026-06-29):
- Schema is disclosure/news oriented, not structured corporate action.
- FPT has 1 dividend candidate; VNM/HPG/VCB/CTG/VHM have no rows.
- Raw payload is HTML listing page; PDF dividend details not parseable without a PDF parser.
- All 4 required fields missing: ex_date, record_date, cash_dividend_per_share, currency.

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

`scripts/check_adjusted_ohlc_readiness.py` reports adjusted OHLC coverage for a
local SQLite store. The current demo DB is expected to return
`status=not_ready` and `backtest_gate=blocked` because adjusted fields are still
empty for gap-chart ingestion.

`docs/data_platform/adjusted_factor_source_review.md` records the current source
evidence. `src/trading_agent/ingestion/adjustment_factors.py` now defines pure
factor-record helpers, but ETL still does not populate adjusted OHLC until a
trusted adjusted-close or corporate-action source is integrated.
`scripts/probe_adjusted_factor_sources.py` can plan no-network source probes and
inspect local JSON payloads for adjusted-factor evidence. Probe evidence is
candidate-level only and does not make a source usable without provenance review.
`scripts/capture_adjusted_factor_evidence.py` can record local payload evidence
with a content hash for review, but it still does not populate adjusted OHLC or
unblock Backtrader by itself.
`scripts/apply_adjustment_factors.py` can apply reviewed local factor records to
explicit symbols in a local SQLite DB. It is dry-run by default, requires
`--execute` to mutate adjusted columns, and does not discover factors or fetch
network data. Readiness requires adjusted OHLC plus `adjustment_source_id`,
`adjustment_raw_path`, and `adjustment_method`; raw OHLC `source_id` and
`raw_path` are not reused as factor provenance.
`src/trading_agent/ingestion/sources/adjustment_factor_source.py` adds a
fixture-only adapter interface for converting adjusted-close or
corporate-action payloads into factor records with provenance. The current
fixtures are synthetic and are not a live source. A controlled,
no-network verification layer
(`docs/data_platform/controlled_factor_source_verification.md`) reuses that
adapter to confirm a local payload yields usable factor records on a small
explicit symbol set before any ETL adjusted-OHLC population. PR #37 created
that controlled local verification layer without wiring a live source or
populating adjusted OHLC.

The confirmed policy is documented in
`docs/data_platform/confirmed_adjusted_price_policy.md`. The next required step
is implementation verification of adjusted-price or factor evidence for
`FPT`, `VNM`, and `VCB`.
`docs/data_platform/adjusted_price_evidence_pipeline.md` adds the local-first
pipeline for that verification and optional explicit local adjusted-OHLC
population path. `docs/data_platform/adjusted_price_evidence_smoke_runbook.md`
proves the mechanics with synthetic local data only. Reviewed local evidence
intake still must require source, raw-path, reviewer, review timestamp, and
evidence-basis metadata plus payload SHA-256 integrity before real adjusted-price
evidence is used. After local execute readiness, the read-only
`docs/data_platform/adjusted_ohlc_execution_audit.md` workflow must inspect
adjusted rows, factor provenance, factor consistency, and readiness reports
before any Backtrader feed planning. Strict audit mode requires factor records,
validation report, and readiness report. Raw OHLC unchanged is independently
verified only if a raw baseline file is supplied.
`docs/backtest/adjusted_ohlc_backtest_feed_contract.md` then defines the
small-symbol feed preview contract that maps adjusted OHLC into feed
`open/high/low/close` fields without implementing Backtrader. That contract is
preview only: it requires a strict adjusted OHLC execution audit whose metadata
matches the DB and requested symbols, requires every requested symbol to have
eligible adjusted rows, validates date and `max_rows` inputs instead of
silently correcting them, keeps raw OHLC diagnostics-only, and emits
`feed_contract_version=adjusted_ohlc_feed_v1` with `source_price_basis=adjusted_ohlc`.
`docs/backtest/adjusted_ohlc_feed_to_backtest_dry_run.md` then consumes that feed
preview and prepares a backtest input contract for a research dry-run. It
validates the adjusted feed plus explicit transaction-cost and slippage
assumptions and encodes the slippage bands (HOSE/HSX +/-7%, UPCoM +/-15%). It is
preparation only: no Backtrader, no optimizer, no full VN100, and no investment
advice. `docs/backtest/adjusted_ohlc_fixture_signal_dry_run.md` then consumes
that preparation JSON and emits a tiny deterministic fixture signal preview
(default all-cash `NO_POSITION`, optional synthetic alternating flag). It is
fixture signal preview only: not a real strategy, not Backtrader, not an
optimizer, not full VN100, and it reports no performance metrics by default and
gives no investment advice. `docs/backtest/adjusted_ohlc_fixture_metrics_report.md`
then consumes that fixture signal output and produces deterministic, clearly
fixture-labeled diagnostic metrics (counts, dates, no-position ratio). It is
fixture diagnostics only: not strategy performance, not Backtrader, not an
optimizer, not full VN100, not investment advice, and it intentionally avoids
Sharpe/Sortino/Profit Factor/Max Drawdown/PnL/equity curve.
`docs/backtest/adjusted_ohlc_fixture_roundtrip_engine.md` then consumes the
preparation, fixture signal, and fixture metrics and runs a deterministic
adjusted-basis fixture round-trip engine that emits only state-transition
diagnostics (`fixture_enter_count`, `fixture_exit_count`, `duplicate_enter_count`,
`unmatched_exit_count`, `open_fixture_state_count`). It is fixture round-trip
diagnostics only: not strategy performance, not Backtrader, not an optimizer,
not full VN100, not investment advice, and it intentionally avoids all
profitability/performance metrics.
`docs/backtest/adjusted_ohlc_fixture_cost_diagnostics.md` then attaches validated
cost/slippage assumptions to fixture enter/exit counts as bps-units diagnostics
only. It is not PnL, returns, strategy performance, Backtrader, an optimizer,
full VN100, or investment advice, and intentionally avoids price multiplication
and trade lists. After PR #53, mentor review is required before any real
adjusted-basis engine integration.

## Corporate Action Data

The adjustment factor must come from verified source logic for dividends,
splits, and other relevant corporate actions. The source, event date, effective
date, and calculation method should be auditable. If events conflict across
sources, the row should be flagged rather than silently adjusted.

For later Backtrader assumptions, transaction cost is a research task. Slippage
must be reasonable and bounded by daily exchange price bands: HSX/HOSE +/-7% and
UPCoM +/-15%.

## Validation Checks

Before a row enters a hardened backtest feed:

- adjusted OHLC fields are present for every backtest row;
- adjustment factor provenance fields are present for every adjusted row;
- no `adjust_factor <= 0`;
- no missing adjusted close;
- `adjusted_high >= max(adjusted_open, adjusted_close)`;
- `adjusted_low <= min(adjusted_open, adjusted_close)`;
- adjusted OHLC remains internally consistent after rounding;
- rows with unresolved corporate-action status are excluded or blocked.
- local execute-readiness validation and adjusted OHLC execution audit both pass.
- adjusted OHLC execution audit reports `backtest_planning_gate=pass`.
- feed preview uses adjusted OHLC only and keeps raw OHLC diagnostics-only.

## Caveats

Current demo data can still carry `adjustment_status=unknown`. That is acceptable
for the local demo only. VN100 Backtrader work should wait until adjusted OHLC
schema, factor provenance, and validation tests are in place.

Not implemented yet:

- full dividend/split/corporate-action event engine;
- verified source evidence for adjustment factors;
- reviewed source-probe evidence for ETL integration;
- broader ETL population from a real verified source adapter;
- live/vendor source verification for factor records;
- Backtrader strategy optimizer;
- ETL Docker scheduler.
