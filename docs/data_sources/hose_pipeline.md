---
title: hose_pipeline
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Pipeline

## 1. Executive Summary

<details open>
<summary>HOSE listed-universe and quote-report dry runs work; DB/backtest remains blocked by source semantics.</summary>

---

#### What is working

- HOSE listed-stock universe page-1 parser dry run works.
- HOSE listed-stock universe all-pages dry run works.
- HOSE quote-report parser dry run works for saved verified JSON samples.
- HOSE quote-report stock-only filter works.
- Full quote-report rows are preserved, and non-stock-like rows are excluded only in derived stock-only outputs.

#### What is still blocked

- Source units are not confirmed.
- Final EOD semantics are not confirmed.
- `tradingBy=VNINDEX` coverage is not fully confirmed.
- Historical date availability and non-trading-day behavior are not audited.
- Database ingestion and backtest use remain blocked.

#### First MVP recommendation

Use the stock-only quote-report subset for the first ordinary-stock MVP, not the full quote-report dataset.

The current stock-only result is:

| Dataset | Count |
|---|---:|
| Full quote-report symbols | 662 |
| Listed-universe stock symbols | 403 |
| Stock-only symbols | 403 |
| Excluded non-stock-like symbols | 259 |

---

</details>

## 2. Source Endpoints

<details open>
<summary>The current HOSE flow uses a listed-stock endpoint and a quote-report endpoint.</summary>

---

#### Listed-stock universe

Endpoint pattern:

`https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=30&alphabet=&sectorId=`

Request notes:

- Method: `GET`
- Pagination: `pageIndex` and `pageSize`
- Observed page-1 metadata: `totalCount=403`, `totalPages=14`
- Role: listed-stock universe and exchange-listing metadata

#### Quote report

Endpoint pattern:

`https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=<YYYY-MM-DD>`

Request notes:

- Method: `POST`
- Body: `body_json={}`
- Response must validate as JSON.
- HTTP 200 with `Request Rejected` HTML must not be treated as usable data.
- A browser-derived local header may be required for local probing.
- Local header values must stay in local config only and must not be committed or printed.

Role:

- Completed-day OHLCV-like quote report candidate.
- Current-day provisional quote snapshot candidate.

---

</details>

## 3. Listed Universe Pipeline

<details open>
<summary>The listed-universe all-pages workflow captures 403 listed-stock rows with no failures.</summary>

---

#### Raw source shape

Top-level JSON fields:

- `data`
- `success`
- `message`

Container fields:

- `data.list`
- `data.paging`

Important row fields:

- `id`
- `code`
- `name`
- `brief`
- `isin`
- `bloomberg`
- `securitiesType`
- `displayText`
- `listingStatusId`
- `listingVolume`
- `listingValue`
- `outStanding`
- `adjOutStanding`
- `treasuryVol`
- `regDate`
- `ftdate`
- `acceptDate`
- `listDate`

#### All-pages dry-run result

Current reviewed run:

`data/processed/dry_run/hose_listed_universe_all_pages/20260603T080254Z/`

| Metric | Count |
|---|---:|
| Requested pages | 14 |
| Fetched pages | 14 |
| Expected total rows | 403 |
| Parsed rows | 403 |
| Duplicate symbols | 0 |
| Quality pass rows | 178 |
| Quality warn rows | 225 |
| Quality fail rows | 0 |

Validation warnings:

- `warning_sentinel_date_acceptDate`: 220
- `warning_sentinel_date_listDate`: 220
- `warning_listed_volume_less_than_outstanding_volume`: 11

#### Output files

- `securities_master.csv`
- `exchange_listings.csv`
- `symbol_universe.csv`
- `validation_report.md`
- `validation_summary.json`
- `raw_pages/page_001.json ... page_014.json`
- `raw_pages/page_manifest.json`

---

</details>

## 4. Quote-Report Pipeline

<details open>
<summary>The quote-report parser converts saved verified JSON into local dry-run OHLCV-like outputs.</summary>

---

#### Verified POST JSON run

Source-probe run:

`run_id=20260603T091759Z`

Verified quote-report samples:

| Dataset | Request date | Data status | Row count |
|---|---|---|---:|
| `hose_daily_quote_report` | `2026-06-02` | `final_candidate` | 662 |
| `hose_daily_quote_report_current_day` | `2026-06-03` | `provisional` | 662 |

Observed JSON shape:

- Top-level fields: `data`, `success`, `message`
- Row container: top-level `data` list
- Observed row count: 662 rows per saved sample

Important row fields:

- `id`
- `securitySymbol`
- `securityName`
- `isin`
- `bloomberg`
- `priorClosePrice`
- `openPrice`
- `highPrice`
- `lowPrice`
- `closePrice`
- `changePrice`
- `changePriceRatio`
- `mainVolume`
- `mainValue`
- `averagePrice`
- `ceiling`
- `floor`

#### Completed-day parser dry-run result

Current reviewed run:

`data/processed/dry_run/hose_quote_report/20260603T094855Z/`

| Metric | Count |
|---|---:|
| `daily_price_bars.csv` rows | 662 |
| `daily_quote_reports.csv` rows | 662 |
| `market_ohlcv_snapshots.csv` rows | 662 |
| Quality pass rows | 0 |
| Quality warn rows | 662 |
| Quality fail rows | 0 |

Quality warnings:

- `warning_source_units_unconfirmed`: 662
- `warning_no_trade_zero_ohlc`: 58

#### Output files

- `daily_price_bars.csv`
- `daily_quote_reports.csv`
- `market_ohlcv_snapshots.csv`
- `validation_report.md`
- `validation_summary.json`

#### Data-status behavior

- Completed-day samples are tagged `final_candidate`.
- Current-day samples are tagged `provisional`.
- Backtests must not treat `provisional` rows as final EOD bars.

---

</details>

## 5. Stock-Only Filter

<details open>
<summary>The stock-only filter keeps ordinary stock symbols for MVP and preserves excluded rows for audit.</summary>

---

#### Why it is needed

The quote-report endpoint is broader than the listed-stock universe. It includes ordinary stock symbols plus non-stock-like instruments. The first MVP ordinary-stock strategy should not mix stocks with ETF/fund-like or covered warrant-like rows unless those instruments are explicitly supported.

#### Current stock-only result

Input folders:

- Quote report: `data/processed/dry_run/hose_quote_report/20260603T094855Z/`
- Listed universe: `data/processed/dry_run/hose_listed_universe_all_pages/20260603T080254Z/`

Output folder:

`data/processed/dry_run/hose_quote_report/20260603T094855Z/stock_only/`

| Metric | Count |
|---|---:|
| Full quote-report symbols | 662 |
| Listed-universe symbols | 403 |
| Stock-only symbols | 403 |
| Excluded symbols | 259 |
| Duplicate quote-report symbol/date/status rows | 0 |
| Duplicate listed-universe symbols | 0 |
| Filter run status | `pass` |

Excluded symbols are likely covered warrant-like and ETF/fund-like rows. Examples include:

- `CACB2510`
- `CFPT2517`
- `CHPG2523`
- `E1VFVN30`
- `FUEVFVND`
- `FUCVREIT`

#### Output files

- `daily_price_bars_stock_only.csv`
- `daily_quote_reports_stock_only.csv`
- `market_ohlcv_snapshots_stock_only.csv`
- `excluded_non_stock_symbols.csv`
- `stock_only_filter_summary.json`
- `stock_only_filter_report.md`

---

</details>

## 6. Saved-Output Units And History Audit

<details open>
<summary>Saved outputs confirm parser health, but not units, EOD finality, or historical availability.</summary>

---

Saved-output audit:

`data/processed/dry_run/hose_quote_report_saved_outputs_audit.json`

Saved quote-report dry-run folders found:

| Run ID | Dates | Data statuses | Rows | Stock-only output |
|---|---|---|---:|---|
| `20260603T094855Z` | `2026-06-02` | `final_candidate` | 662 | yes, 403 rows |
| `20260603T101327Z` | `2026-06-02` | `final_candidate` | 662 | no |
| `20260603T101349Z` | `2026-06-02`, `2026-06-03` | `final_candidate`, `provisional` | 1324 | no |

Audit conclusions:

- Units remain unconfirmed in all saved quote-report runs.
- Final EOD semantics remain unconfirmed.
- Historical availability remains unconfirmed.
- No saved-output audit fetched live data.
- DB/backtest remains blocked.

Unit hypotheses:

- Price fields may be displayed price units, likely thousand VND-style for Vietnam equities.
- `mainVolume` may be shares or lot-scaled volume.
- `mainValue` may be million VND or another display unit.
- Do not hard-code DB unit conversions until source evidence or mentor review confirms them.

Historical availability audit design:

- Test several completed trading days.
- Test at least one weekend or non-trading day.
- Test older historical dates.
- Record statuses as `verified_json`, `empty_data`, `rejected_response`, or `error`.
- Compare full row count, stock-only coverage, duplicate counts, and quality counts across dates.

---

</details>

## 7. Data-Quality Gates Before DB/Backtest

<details open>
<summary>Database and backtest work should wait until source semantics are resolved.</summary>

---

Required gates:

- Source units confirmed.
- Final EOD timing understood.
- Historical and non-trading-day behavior audited.
- `tradingBy=VNINDEX` coverage understood.
- Stock-only coverage stable across dates.
- No duplicate `symbol + trading_date + data_status` rows.
- Current-day/provisional records remain separate from completed-day/final-candidate records.
- Unit conversion rule explicitly approved.

Until these gates are satisfied, HOSE quote-report outputs should remain dry-run artifacts only.

---

</details>

## 8. Current Scripts

<details open>
<summary>These scripts support the current HOSE dry-run pipeline.</summary>

---

| Script | Purpose |
|---|---|
| `parse_hose_listed_universe_dry_run.py` | Parse saved page-1 listed-stock universe JSON into local CSV outputs. |
| `parse_hose_listed_universe_all_pages_dry_run.py` | Fetch and parse all listed-stock universe pages into local CSV outputs. |
| `parse_hose_quote_report_dry_run.py` | Parse saved quote-report JSON into daily price, quote report, and OHLCV snapshot CSV outputs. |
| `audit_hose_quote_report_universe_coverage.py` | Compare quote-report symbols with listed-universe symbols and write coverage audit outputs. |
| `build_hose_quote_report_stock_only_dry_run.py` | Join quote-report outputs to listed-universe outputs and write stock-only derived CSVs. |
| `audit_hose_quote_report_saved_outputs.py` | Summarize saved quote-report dry-run folders without live fetching. |

---

</details>

## 9. Current Tests

<details open>
<summary>These tests cover the current HOSE parser and audit utilities.</summary>

---

| Test file | Purpose |
|---|---|
| `test_hose_listed_universe_parser.py` | Tests page-1 listed-universe parsing, normalization, validation, and deterministic IDs. |
| `test_hose_listed_universe_all_pages.py` | Tests all-pages fetch/merge behavior, missing pages, duplicate symbols, and summary counts. |
| `test_hose_quote_report_parser.py` | Tests quote-report shape parsing, date extraction, numeric parsing, validation, provisional warnings, and deterministic IDs. |
| `test_hose_quote_report_stock_only_filter.py` | Tests stock-only join/filter behavior, excluded rows, duplicate handling, and summary counts. |
| `test_hose_quote_report_saved_outputs_audit.py` | Tests saved-output audit summary behavior without live fetching. |

---

</details>

## 10. Recommended Next Step

<details open>
<summary>The next step is unit or historical availability confirmation, still without DB/backtest work.</summary>

---

Recommended order:

1. Manual unit confirmation from HOSE UI/source page evidence or mentor review.
2. Historical multi-date audit using safe configured quote-report probes.
3. Review stock-only coverage stability across dates.
4. Only then consider canonical storage design or backtest preparation.

Still do not implement:

- Database migrations.
- Database writes.
- Backtest.
- Production crawling.

---

</details>

## 11. Appendix: Old Docs Merged

<details open>
<summary>The following old HOSE docs were merged into this canonical document.</summary>

---

| Old doc path | Merged into section | Action |
|---|---|---|
| `docs/hose_market_data_mapping_review.md` | Source endpoints, listed universe pipeline, quote-report pipeline | removed after merge |
| `docs/hose_listed_universe_parser_review.md` | Listed universe pipeline | removed after merge |
| `docs/hose_listed_universe_all_pages_review.md` | Listed universe pipeline | removed after merge |
| `docs/hose_quote_report_mapping_review.md` | Quote-report pipeline, data-quality gates | removed after merge |
| `docs/hose_quote_report_parser_review.md` | Quote-report pipeline | removed after merge |
| `docs/hose_quote_report_universe_coverage_audit.md` | Stock-only filter | removed after merge |
| `docs/hose_quote_report_stock_only_filter_review.md` | Stock-only filter | removed after merge |
| `docs/hose_quote_report_units_and_history_audit_plan.md` | Saved-output units and history audit, data-quality gates | removed after merge |

---

</details>
