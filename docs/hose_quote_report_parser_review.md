---
title: hose_quote_report_parser_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Quote Report Parser Review

## 1. Purpose

<details open>
<summary>This document records the first dry-run parser for saved HOSE quote-report JSON samples.</summary>

---

The HOSE quote-report parser dry run converts saved source-probe JSON payloads into local canonical CSV candidates. It does not fetch live data, write to a database, implement OHLCV ingestion, or support backtesting.

The parser is intended to prove the source-to-canonical mapping for quote-report payloads before any migration or production ingestion work.

---

</details>

## 2. Input Raw Samples

<details open>
<summary>The first dry run used the completed-day quote-report sample from the verified POST probe.</summary>

---

Latest verified HOSE quote-report probe:

`run_id=20260603T091759Z`

Completed-day input:

- Raw payload: `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report/payload.json`
- Metadata: `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report/metadata.json`
- Request date: `2026-06-02`
- Parser data status: `final_candidate`

Current-day supported input:

- Raw payload: `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report_current_day/payload.json`
- Metadata: `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report_current_day/metadata.json`
- Request date: `2026-06-03`
- Parser data status: `provisional`

The script defaults to the completed-day sample. Current-day parsing is available only when explicitly requested with `--include-current-day`, and those rows are tagged `provisional`.

---

</details>

## 3. Output Files

<details open>
<summary>The parser writes local dry-run CSV outputs and validation files only.</summary>

---

Dry-run output directory:

`data/processed/dry_run/hose_quote_report/20260603T094855Z/`

Output files:

- `daily_price_bars.csv`
- `daily_quote_reports.csv`
- `market_ohlcv_snapshots.csv`
- `validation_report.md`
- `validation_summary.json`

No database write, migration, or backtest was performed.

---

</details>

## 4. Field Mapping

<details open>
<summary>Source fields are mapped into daily price, quote-report, and OHLCV snapshot candidates.</summary>

---

| Raw field | Canonical field | Notes |
|---|---|---|
| `securitySymbol` | `symbol` | Trimmed and uppercased. |
| Request URL `date` | `trading_date` | Extracted from metadata endpoint query. |
| Parser input/inference | `data_status` | `final_candidate` or `provisional`. |
| `id` | `source_row_id` | Preserved for lineage. |
| `securityName` | `security_name` | Optional. |
| `isin` | `isin` | Optional. |
| `bloomberg` | `bloomberg_id` | Optional; not assumed to be FIGI. |
| `priorClosePrice` | `prior_close_price` | Numeric string. |
| `openPrice` | `open_price` | Numeric string. |
| `highPrice` | `high_price` | Numeric string. |
| `lowPrice` | `low_price` | Numeric string. |
| `closePrice` | `close_price` | Numeric string. |
| `changePrice` | `price_change` | Numeric string. |
| `changePriceRatio` | `price_change_pct` | Numeric percent-like string. |
| `mainVolume` | `matched_volume` | Comma thousands separators are removed. |
| `mainValue` | `trading_value` | Comma thousands separators are removed. |
| `averagePrice` | `average_price` | Numeric string. |
| `ceiling` | `ceiling_price` | Numeric string. |
| `floor` | `floor_price` | Numeric string. |

The parser also adds:

- `exchange = HOSE`
- `source_name = hose`
- `source_payload_id`
- `raw_content_hash`
- `raw_row_index`
- `parser_version`
- `schema_version`
- `quality_status`
- `quality_reasons`

---

</details>

## 5. Validation Rules

<details open>
<summary>The parser validates required identifiers, numeric fields, OHLC relationships, duplicates, and data status.</summary>

---

Required fields:

- `symbol`
- `trading_date`
- `data_status`

Quality checks:

- Numeric strings must parse after removing comma thousands separators.
- Empty strings, `-`, and null numeric values become null.
- `0.00` parses as zero, not null.
- `high_price >= low_price` when both are present and non-zero.
- `close_price` and `open_price` must be within high/low when the row traded and high/low are non-zero.
- `matched_volume >= 0`.
- `trading_value >= 0`.
- `ceiling_price >= floor_price`.
- Duplicate `symbol + trading_date + data_status` fails affected rows.
- Provisional rows get `warning_provisional_current_day`.
- No-trade rows with open/high/low/average equal to zero and close equal to prior close get `warning_no_trade_zero_ohlc`, not fail.
- Source unit uncertainty is recorded as `warning_source_units_unconfirmed`.

---

</details>

## 6. Dry-Run Result Summary

<details open>
<summary>The completed-day dry run parsed all 662 quote rows with warnings and no failures.</summary>

---

Command:

```bash
python scripts/parse_hose_quote_report_dry_run.py
```

Result:

| Metric | Count |
|---|---:|
| JSON input rows | 662 |
| `daily_price_bars` rows | 662 |
| `daily_quote_reports` rows | 662 |
| `market_ohlcv_snapshots` rows | 662 |
| Quality pass rows | 0 |
| Quality warn rows | 662 |
| Quality fail rows | 0 |

Quality reasons:

| Reason | Count |
|---|---:|
| `warning_source_units_unconfirmed` | 662 |
| `warning_no_trade_zero_ohlc` | 58 |

The warning-only result is expected because source units and final EOD semantics are not yet fully confirmed.

---

</details>

## 7. Completed-Day Versus Current-Day Behavior

<details open>
<summary>The parser keeps final-candidate and provisional quote data separate.</summary>

---

Completed-day sample behavior:

- Dataset: `hose_daily_quote_report`
- Inferred `data_status`: `final_candidate`
- Meaning: candidate completed-day EOD quote report, pending final source-semantics confirmation.

Current-day sample behavior:

- Dataset: `hose_daily_quote_report_current_day`
- Inferred `data_status`: `provisional`
- Meaning: current-day quote snapshot that may change during the session.

Backtest implication:

- Backtests must not treat `provisional` rows as final EOD bars.
- `final_candidate` rows still need source-semantics confirmation before database/backtest use.

---

</details>

## 8. Limitations

<details open>
<summary>The parser is ready for review, but not for database or backtest promotion.</summary>

---

Known limitations:

- Price units are not fully confirmed.
- Volume and trading value units are not fully confirmed.
- Final EOD semantics are not fully confirmed.
- `tradingBy=VNINDEX` coverage is not fully confirmed.
- Instrument classification still needs a join against HOSE listed-universe output.
- This is a local dry run only.
- No database migration or write was performed.
- No backtest was implemented.

---

</details>
