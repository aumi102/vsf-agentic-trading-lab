---
title: hose_quote_report_stock_only_filter_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Quote Report Stock-Only Filter Review

## 1. Purpose

<details open>
<summary>This dry run derives a stock-only HOSE quote-report subset without mutating the full quote-report outputs.</summary>

---

The stock-only filter joins HOSE quote-report dry-run outputs with the HOSE listed-universe all-pages output. It keeps only symbols present in the listed-stock universe and writes excluded non-stock symbols separately for audit.

This is a derived local dry run only. It does not write to a database, implement a backtest, fetch live data, or change the original quote-report CSV files.

---

</details>

## 2. Input Dry-Run Folders

<details open>
<summary>The filter uses the verified quote-report dry run and all-pages listed-universe dry run.</summary>

---

- Quote-report directory: `data\processed\dry_run\hose_quote_report\20260603T094855Z`
- Listed-universe directory: `data\processed\dry_run\hose_listed_universe_all_pages\20260603T080254Z`

Input quote-report files:

- `daily_price_bars.csv`
- `daily_quote_reports.csv`
- `market_ohlcv_snapshots.csv`
- `validation_summary.json`

Input listed-universe files:

- `symbol_universe.csv`
- `securities_master.csv`
- `exchange_listings.csv`

---

</details>

## 3. Output Files

<details open>
<summary>Filtered outputs are written under the quote-report dry-run folder in `stock_only/`.</summary>

---

Output directory:

`data\processed\dry_run\hose_quote_report\20260603T094855Z/stock_only/`

Output files:

- `daily_price_bars_stock_only.csv`
- `daily_quote_reports_stock_only.csv`
- `market_ohlcv_snapshots_stock_only.csv`
- `excluded_non_stock_symbols.csv`
- `stock_only_filter_summary.json`
- `stock_only_filter_report.md`

---

</details>

## 4. Join And Filter Logic

<details open>
<summary>The filter normalizes symbols and keeps only quote-report rows found in the listed-stock universe.</summary>

---

Rules:

- Normalize symbols by stripping whitespace and uppercasing.
- Keep only quote-report rows whose symbol exists in `symbol_universe.csv`.
- Preserve original quote-report outputs unchanged.
- Write excluded rows separately with `exclusion_reason = not_in_hose_listed_stock_universe`.
- Enrich stock-only rows when listed-universe fields are available:
  - `security_id`
  - `company_name`
  - `display_text`
  - `security_type_code`
  - `listing_status_id`
  - `listed_volume`
  - `outstanding_volume`
  - `listed_universe_run_id`

Validation:

- Duplicate quote-report `symbol + trading_date + data_status` rows fail the filter run.
- Duplicate listed-universe symbols warn and keep the first row.

---

</details>

## 5. Filter Result Summary

<details open>
<summary>The stock-only subset contains 403 rows and excludes 259 non-stock-like rows.</summary>

---

| Metric | Count |
|---|---:|
| Quote-report rows | 662 |
| Quote-report unique symbols | 662 |
| Listed-universe rows | 403 |
| Listed-universe unique symbols | 403 |
| Stock-only rows | 403 |
| Stock-only unique symbols | 403 |
| Excluded rows | 259 |
| Excluded unique symbols | 259 |

Quality after filter:

- `warn`: 403

---

</details>

## 6. Excluded Symbol Patterns

<details open>
<summary>Excluded rows are mostly covered warrant-like and ETF/fund-like symbols.</summary>

---

Top excluded symbol prefixes:

- `CACB`: 14
- `CFPT`: 24
- `CHDB`: 7
- `CHPG`: 26
- `CLPB`: 3
- `CMBB`: 16
- `CMSN`: 12
- `CMWG`: 18
- `CSHB`: 7
- `CSSB`: 3
- `CSTB`: 19
- `CTCB`: 13
- `CTPB`: 7
- `CVHM`: 14
- `CVIB`: 7
- `CVIC`: 4
- `CVNM`: 12
- `CVPB`: 19
- `CVRE`: 9
- `FUCT`: 3

Excluded examples:

`CACB2510`, `CACB2511`, `CACB2514`, `CACB2515`, `CACB2516`, `CACB2517`, `CACB2601`, `CACB2602`, `CACB2603`, `CACB2604`, `CACB2605`, `CACB2606`, `CACB2607`, `CACB2608`, `CDGC2601`, `CFPT2517`, `CFPT2518`, `CFPT2520`, `CFPT2521`, `CFPT2524`, `CFPT2526`, `CFPT2528`, `CFPT2529`, `CFPT2532`, `CFPT2533`, `CFPT2601`, `CFPT2602`, `CFPT2603`, `CFPT2604`, `CFPT2605`, `CFPT2606`, `CFPT2607`, `CFPT2608`, `CFPT2609`, `CFPT2610`, `CFPT2611`, `CFPT2612`, `CFPT2613`, `CFPT2614`, `CHDB2508`

These rows should remain available for audit and future instrument-specific support, but they should not feed the first ordinary-stock MVP strategy.

---

</details>

## 7. MVP Implication

<details open>
<summary>The first MVP ordinary-stock strategy should use the stock-only subset.</summary>

---

Use the stock-only outputs for first MVP ordinary-stock strategy work because:

- All 403 listed-stock symbols are retained.
- 259 quote-report rows outside the listed-stock universe are excluded.
- Covered warrant-like and ETF/fund-like symbols have different behavior from ordinary stocks.
- The full quote-report dataset remains preserved for audit.

---

</details>

## 8. Limitations

<details open>
<summary>The filtered dataset is still not ready for database or backtest promotion.</summary>

---

Limitations:

- No database migration or database write was performed.
- No backtest was implemented.
- HOSE quote-report source units are still unconfirmed.
- Final EOD semantics are still unconfirmed.
- `tradingBy=VNINDEX` coverage is still not fully confirmed.
- ETF/fund and covered warrant-like instruments are excluded for MVP, not deleted.

---

</details>
