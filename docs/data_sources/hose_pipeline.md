---
title: hose_pipeline
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Pipeline

## 1. Executive Summary

HOSE listed-universe and quote-report dry runs work; DB/backtest remains blocked by source semantics.

#### What is working

- HOSE listed-stock universe all-pages dry run works.
- HOSE quote-report parser dry run works for saved verified JSON samples.
- HOSE quote-report stock-only filter works.
- Full quote-report rows are preserved; non-stock-like rows excluded in derived stock-only outputs.
- Mentor recommends Vietcap IQ as the main full-market universe provider. HOSE listed universe remains HOSE-specific.

#### What is still blocked

- Source units are not confirmed.
- Final EOD semantics are not confirmed.
- `tradingBy=VNINDEX` coverage is not fully confirmed.
- Historical date availability and non-trading-day behavior are not audited.
- Database ingestion and backtest use remain blocked.

#### Current stock-only result

| Dataset | Count |
|---|---:|
| Full quote-report symbols | 662 |
| Listed-universe stock symbols | 403 |
| Stock-only symbols | 403 |
| Excluded non-stock-like symbols | 259 |

---

## 2. Source Endpoints

#### Listed-stock universe

Endpoint pattern:

`https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=30&alphabet=&sectorId=`

- Method: `GET`
- Pagination: `pageIndex` and `pageSize`
- Observed page-1 metadata: `totalCount=403`, `totalPages=14`
- Role: listed-stock universe and exchange-listing metadata

#### Quote report

Endpoint pattern:

`https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=<YYYY-MM-DD>`

- Method: `POST`; body: `body_json={}`
- HTTP 200 with `Request Rejected` HTML must not be treated as usable data.
- A browser-derived local header may be required for local probing.
- Local header values must stay in local config only and must not be committed or printed.
- Role: completed-day OHLCV-like quote report and current-day provisional snapshot.

---

## 3. Listed Universe Pipeline

#### All-pages dry-run result

Current reviewed run: `data/processed/dry_run/hose_listed_universe_all_pages/20260603T080254Z/`

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

Quality warnings: `warning_sentinel_date_acceptDate` (220), `warning_sentinel_date_listDate` (220), `warning_listed_volume_less_than_outstanding_volume` (11).

---

## 4. Quote-Report Pipeline

#### Verified POST run

`run_id=20260603T091759Z`

| Dataset | Request date | Data status | Row count |
|---|---|---|---:|
| `hose_daily_quote_report` | `2026-06-02` | `final_candidate` | 662 |
| `hose_daily_quote_report_current_day` | `2026-06-03` | `provisional` | 662 |

Observed row container: top-level `data` list; 662 rows per saved sample.

#### Completed-day dry-run result

Current reviewed run: `data/processed/dry_run/hose_quote_report/20260603T094855Z/`

| Metric | Count |
|---|---:|
| `daily_price_bars.csv` rows | 662 |
| `daily_quote_reports.csv` rows | 662 |
| `market_ohlcv_snapshots.csv` rows | 662 |
| Quality pass rows | 0 |
| Quality warn rows | 662 |
| Quality fail rows | 0 |

Quality warnings: `warning_source_units_unconfirmed` (662), `warning_no_trade_zero_ohlc` (58).

#### Data-status behavior

- Completed-day samples are tagged `final_candidate`.
- Current-day samples are tagged `provisional`.
- Backtests must not treat `provisional` rows as final EOD bars.

---

## 5. Stock-Only Filter

The quote-report endpoint is broader than the listed-stock universe — includes ordinary stocks
plus non-stock-like instruments (covered warrants, ETFs). The first MVP strategy should use the
stock-only subset.

| Metric | Count |
|---|---:|
| Full quote-report symbols | 662 |
| Listed-universe symbols | 403 |
| Stock-only symbols | 403 |
| Excluded symbols | 259 |
| Duplicate quote-report symbol/date/status rows | 0 |
| Filter run status | `pass` |

Excluded symbols include covered warrant-like rows (`CACB2510`, `CFPT2517`) and ETF-like rows (`E1VFVN30`, `FUEVFVND`).

---

## 6. Unit And EOD Confirmation Checklist

Fields requiring mentor/source confirmation before DB/backtest use:

| Field | Current parser meaning | Suspected unit | Confirmation needed | Blocks DB/backtest |
|---|---|---|---|---|
| `priorClosePrice` | Previous close price. | Display price, likely thousand VND. | Confirm exact price unit and adjusted/unadjusted. | yes |
| `openPrice` | Session open price. | Display price, likely thousand VND. | Confirm exact unit and zero/no-trade behavior. | yes |
| `highPrice` | Session high price. | Display price, likely thousand VND. | Confirm unit and whether high is final after EOD. | yes |
| `lowPrice` | Session low price. | Display price, likely thousand VND. | Confirm unit and whether low is final after EOD. | yes |
| `closePrice` | Session close or latest matched price. | Display price, likely thousand VND. | Confirm when this becomes final EOD close. | yes |
| `averagePrice` | Average matched price. | Display price, likely thousand VND. | Confirm formula and unit. | yes |
| `ceiling` | Ceiling price. | Display price, likely thousand VND. | Confirm unit and daily reference basis. | yes |
| `floor` | Floor price. | Display price, likely thousand VND. | Confirm unit and daily reference basis. | yes |
| `mainVolume` | Matched trading volume. | Unknown: shares, lots, or display-scaled. | Confirm exact volume unit. | yes |
| `mainValue` | Matched trading value. | Unknown: VND, thousand VND, million VND. | Confirm exact value unit. | yes |
| `changePriceRatio` | Percent price change. | Percent value. | Confirm whether `1.23` means `1.23%` or ratio. | yes |

---

## 7. Data-Quality Gates Before DB/Backtest

Required gates:

- Source units confirmed.
- Final EOD timing understood.
- Historical and non-trading-day behavior audited.
- `tradingBy=VNINDEX` coverage understood.
- Stock-only coverage stable across dates.
- No duplicate `symbol + trading_date + data_status` rows.
- Current-day/provisional records remain separate from completed-day/final-candidate records.
- Unit conversion rule explicitly approved.

---

## 8. Current Scripts

| Script | Purpose |
|---|---|
| `parse_hose_listed_universe_dry_run.py` | Parse saved page-1 listed-stock universe JSON into local CSV outputs. |
| `parse_hose_listed_universe_all_pages_dry_run.py` | Fetch and parse all listed-stock universe pages into local CSV outputs. |
| `parse_hose_quote_report_dry_run.py` | Parse saved quote-report JSON into daily price, quote report, and OHLCV snapshot CSV outputs. |
| `audit_hose_quote_report_universe_coverage.py` | Compare quote-report symbols with listed-universe symbols and write coverage audit outputs. |
| `build_hose_quote_report_stock_only_dry_run.py` | Join quote-report outputs to listed-universe outputs and write stock-only derived CSVs. |
| `audit_hose_quote_report_saved_outputs.py` | Summarize saved quote-report dry-run folders without live fetching. |

---

## 9. Current Tests

| Test file | Purpose |
|---|---|
| `test_hose_listed_universe_parser.py` | Tests page-1 listed-universe parsing, normalization, validation, and deterministic IDs. |
| `test_hose_listed_universe_all_pages.py` | Tests all-pages fetch/merge behavior, missing pages, duplicate symbols, and summary counts. |
| `test_hose_quote_report_parser.py` | Tests quote-report shape parsing, date extraction, numeric parsing, validation, provisional warnings, and deterministic IDs. |
| `test_hose_quote_report_stock_only_filter.py` | Tests stock-only join/filter behavior, excluded rows, duplicate handling, and summary counts. |
| `test_hose_quote_report_saved_outputs_audit.py` | Tests saved-output audit summary behavior without live fetching. |

---

## 10. Recommended Next Step

Recommended order:

1. Manual unit confirmation from HOSE UI/source page evidence or mentor review.
2. Historical multi-date audit using safe configured quote-report probes.
3. Review stock-only coverage stability across dates.
4. Only then consider canonical storage design or backtest preparation.

Do not implement: database migrations, database writes, backtest, production crawling.

Historical audit run details archived at: `notes/archive/hose_pipeline_legacy_notes.md`
