---
title: hose_quote_report_universe_coverage_audit
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Quote Report Universe Coverage Audit

## A. Executive Summary

<details open>
<summary>The quote-report dataset is broader than the listed-stock universe and should be filtered for the first stock MVP.</summary>

---

Input dry-run folders:

- Quote report: `data\processed\dry_run\hose_quote_report\20260603T094855Z`
- Listed universe: `data\processed\dry_run\hose_listed_universe_all_pages\20260603T080254Z`

Key counts:

- Quote-report rows: 662
- Unique quote-report symbols: 662
- Listed-universe rows: 403
- Unique listed-universe symbols: 403
- Matched symbols: 403
- Unmatched quote-report symbols: 259

Likely mismatch reason:

The listed-universe all-pages dry run uses the HOSE stock universe endpoint and contains 403 stock symbols. The quote-report sample contains 662 symbols and appears to include stocks plus non-stock instruments such as covered warrant-like symbols and ETF/fund-like symbols. The unmatched quote-report symbols should not be dropped, but they should not be used in the first ordinary-stock MVP strategy unless instrument support is explicit.

---

</details>

## B. Coverage Table

<details open>
<summary>All listed stock symbols matched the quote-report, while 259 quote-report symbols were outside the listed-stock universe.</summary>

---

| Metric | Count |
|---|---:|
| Total quote-report rows | 662 |
| Total quote-report symbols | 662 |
| Listed-universe rows | 403 |
| Listed-universe symbols | 403 |
| Matched listed-universe symbols | 403 |
| Unmatched quote-report symbols | 259 |
| Duplicate quote-report symbol rows | 0 |
| Duplicate listed-universe symbol rows | 0 |

Coverage ratio:

- Matched symbols as share of quote-report symbols: 60.88%
- Matched symbols as share of listed-universe symbols: 100.00%

---

</details>

## C. Instrument-Type Analysis

<details open>
<summary>Matched rows are stock-universe rows; unmatched rows show warrant-like and ETF/fund-like naming patterns.</summary>

---

Matched listed-universe security type codes:

| security_type_code | Count |
|---|---:|
| `1` | 403 |

Matched listed-universe listing status ids:

| listing_status_id | Count |
|---|---:|
| `11` | 403 |

Unmatched quote-report symbol patterns:

| Pattern | Count |
|---|---:|
| Symbols starting with `C` | 237 |
| Symbols starting with `F` | 21 |
| Symbols with length 8 | 259 |

Top unmatched four-character prefixes:

`CHPG`: 26, `CFPT`: 24, `CSTB`: 19, `CVPB`: 19, `CMWG`: 18, `CMBB`: 16, `CACB`: 14, `CVHM`: 14, `CTCB`: 13, `CMSN`: 12, `CVNM`: 12, `CVRE`: 9, `CHDB`: 7, `CSHB`: 7, `CTPB`: 7, `CVIB`: 7, `CVIC`: 4, `CLPB`: 3, `CSSB`: 3, `FUCT`: 3

Unmatched examples:

`CACB2510`, `CACB2511`, `CACB2514`, `CACB2515`, `CACB2516`, `CACB2517`, `CACB2601`, `CACB2602`, `CACB2603`, `CACB2604`, `CACB2605`, `CACB2606`, `CACB2607`, `CACB2608`, `CDGC2601`, `CFPT2517`, `CFPT2518`, `CFPT2520`, `CFPT2521`, `CFPT2524`, `CFPT2526`, `CFPT2528`, `CFPT2529`, `CFPT2532`, `CFPT2533`, `CFPT2601`, `CFPT2602`, `CFPT2603`, `CFPT2604`, `CFPT2605`, `CFPT2606`, `CFPT2607`, `CFPT2608`, `CFPT2609`, `CFPT2610`, `CFPT2611`, `CFPT2612`, `CFPT2613`, `CFPT2614`, `CHDB2508`

Interpretation:

- `C...` symbols such as `CACB2510`, `CFPT2517`, and `CHPG2523` look like covered warrant-like instruments.
- `F...` symbols such as `E1VFVN30`, `FUEVFVND`, and `FUCVREIT` look like ETF/fund-like instruments.
- The first MVP stock strategy should use the matched ordinary stock universe only.
- The full quote-report dataset should still be preserved for audit and future instrument support.

---

</details>

## D. Quote-Report Quality Analysis

<details open>
<summary>The quote-report dry run has warnings only and no failed rows.</summary>

---

Validation summary:

| Metric | Count |
|---|---:|
| Quality pass rows | 0 |
| Quality warn rows | 662 |
| Quality fail rows | 0 |
| `warning_source_units_unconfirmed` | 662 |
| `warning_no_trade_zero_ohlc` | 58 |

Additional quality counts:

| Metric | Count |
|---|---:|
| Rows with matched volume = 0 | 52 |
| Rows with trading value = 0 | 52 |
| Rows with open/high/low/average = 0 | 58 |
| Rows where close equals prior close | 135 |

Interpretation:

- `warning_source_units_unconfirmed` should remain until source page text or documentation confirms price, volume, and value units.
- `warning_no_trade_zero_ohlc` should remain a warning, not a failure, because zero OHLC rows can represent no-trade records.
- `quality_fail_count = 0`, so the completed-day quote-report parser dry run is structurally healthy enough for review.

---

</details>

## E. Strategy And MVP Implication

<details open>
<summary>The first MVP stock strategy should use a matched stock-only subset, not the full quote-report dataset.</summary>

---

Recommendation for first MVP:

- Use only quote-report rows whose symbols match the HOSE listed-stock universe.
- Exclude covered warrant-like and ETF/fund-like rows from the first ordinary-stock backtest unless those instruments are explicitly supported.
- Preserve the full quote-report dataset for audit, diagnostics, and future instrument-specific work.
- Derive a stock-only subset later rather than mutating the raw quote-report parser output.

Reason:

The quote-report endpoint appears to be a market quote-report surface, not a stock-only endpoint. The first MVP stock strategy should avoid mixing ordinary stocks with instruments that have different payoff structures, liquidity behavior, price rules, and risk profiles.

---

</details>

## F. Parser Improvement Recommendations

<details open>
<summary>The parser can stay broad, but a later filtered output should join against listed-universe metadata.</summary>

---

Recommended parser or dry-run improvements:

- Add an optional universe cross-check warning later: `warning_unmatched_listed_universe_symbol`.
- Add `instrument_type` or `security_type_code` after joining quote-report symbols with listed-universe metadata.
- Keep source-unit uncertainty as a run-level limitation and row-level warning until confirmed.
- Keep no-trade zero-OHLC as a warning, not a failure.
- Do not silently drop unmatched symbols in the parser.
- Add a stock-only derived output in a separate dry-run step if needed for MVP strategy inputs.

---

</details>

## G. Next Safe Implementation Step

<details open>
<summary>Add a stock-only filtered dry-run output before any database or backtest work.</summary>

---

Do not implement database migrations or backtest yet.

Next safest implementation step:

1. Add an optional stock-only filtered dry-run output that joins `daily_quote_reports.csv` to the HOSE listed-universe all-pages output and writes only matched ordinary stock symbols.

Alternative next step:

2. Run a source-unit confirmation and historical-date availability audit for HOSE quote-report before deriving strategy inputs.

Preferred order:

1. Stock-only filtered dry run.
2. Source unit and historical availability audit.
3. Only then consider canonical storage or backtest preparation.

---

</details>
