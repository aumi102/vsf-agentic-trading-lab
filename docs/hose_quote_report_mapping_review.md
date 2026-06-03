---
title: hose_quote_report_mapping_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Quote Report Mapping Review

## 1. Executive Summary

<details open>
<summary>HOSE quote-report is now verified as usable JSON for completed-day and current-day samples.</summary>

---

The latest focused HOSE source probe is:

`run_id=20260603T091759Z`

The run verified two quote-report targets as usable JSON:

- `hose_daily_quote_report_completed_day_candidate`
- `hose_daily_quote_report_current_day_candidate`

Both targets returned HTTP 200 with `application/json; charset=utf-8` content and row-level quote records under the top-level `data` list. This is OHLCV-like daily quote data, but it has not yet been parsed into canonical tables.

Parser implementation is out of scope for this review. The safe next step is a parser dry run for the completed-day quote-report sample first.

Still not confirmed:

- Whether `tradingBy=VNINDEX` covers all HOSE-traded instruments or a report-specific subset.
- Whether the completed-day sample is final EOD data by source definition.
- Exact source units for price, volume, and trading value fields.
- Whether older dates are consistently available.
- Whether current-day data can be treated as final after market close or must always remain provisional.

---

</details>

## 2. Probe Evidence

<details open>
<summary>The completed-day and current-day quote-report targets both captured row-level JSON samples.</summary>

---

| Target name | Dataset | Raw sample path | Metadata path | Access status | Content type | Observed row count | Likely canonical tables | Data status |
|---|---|---|---|---|---|---:|---|---|
| `hose_daily_quote_report_completed_day_candidate` | `hose_daily_quote_report` | `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report/payload.json` | `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report/metadata.json` | `verified` | `application/json; charset=utf-8` | 662 rows in `data` | `daily_price_bars`, `daily_quote_reports`, `market_ohlcv_snapshots` | `final_candidate` |
| `hose_daily_quote_report_current_day_candidate` | `hose_daily_quote_report_current_day` | `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report_current_day/payload.json` | `data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report_current_day/metadata.json` | `verified` | `application/json; charset=utf-8` | 662 rows in `data` | `daily_price_bars`, `daily_quote_reports`, `market_ohlcv_snapshots` | `provisional` |

Metadata row count is `1` because the raw-store layer counted the top-level JSON object. The parser planning row count should use the length of the top-level `data` list, which is 662 rows for each sample.

The probe metadata records `POST` with a small JSON body and records header names only. Local browser-derived header values must remain in local config and must not be committed or printed.

---

</details>

## 3. Observed JSON Structure

<details open>
<summary>The response shape is simple JSON with a top-level row list.</summary>

---

#### Top-level fields

- `data`
- `success`
- `message`

#### Row container

The row container is:

`data`

`data` is a list of quote-report rows.

#### Observed row fields

Each inspected row contains:

- `id`
- `securitySymbol`
- `securityName`
- `isin`
- `bloomberg`
- `changePrice`
- `priorClosePrice`
- `openPrice`
- `highPrice`
- `lowPrice`
- `closePrice`
- `changePriceRatio`
- `mainVolume`
- `mainValue`
- `averagePrice`
- `ceiling`
- `floor`

#### Sample row shape

The first completed-day row has this shape:

| Field | Example value |
|---|---|
| `id` | UUID-like source row id |
| `securitySymbol` | `AAA` |
| `securityName` | null |
| `isin` | null |
| `bloomberg` | null |
| `changePrice` | `-0.05` |
| `priorClosePrice` | `7.03` |
| `openPrice` | `7.03` |
| `highPrice` | `7.08` |
| `lowPrice` | `6.96` |
| `closePrice` | `6.98` |
| `changePriceRatio` | `-0.71` |
| `mainVolume` | `6,756.00` |
| `mainValue` | `4,734.69` |
| `averagePrice` | `7.01` |
| `ceiling` | `7.52` |
| `floor` | `6.54` |

The current-day sample has the same row fields and row count. Its values should be treated as provisional until source finalization semantics are confirmed.

---

</details>

## 4. Field Mapping Proposal

<details open>
<summary>The quote-report payload can support daily price bars, quote reports, and market OHLCV snapshots.</summary>

---

#### Target canonical tables

- `daily_price_bars`
- `daily_quote_reports`
- `market_ohlcv_snapshots`

#### Raw-to-canonical mapping

| Raw field | Canonical field | Proposed table | Notes |
|---|---|---|---|
| `securitySymbol` | `symbol` | all three | Required. Trim and uppercase. |
| Request URL `date` | `trading_date` | all three | Required. The row body did not expose a separate date in the inspected shape. |
| `priorClosePrice` | `prior_close_price` | `daily_quote_reports`, `daily_price_bars` | Numeric string. |
| `openPrice` | `open_price` | `daily_price_bars`, `market_ohlcv_snapshots` | Numeric string; zero may indicate no trade for some rows. |
| `highPrice` | `high_price` | `daily_price_bars`, `market_ohlcv_snapshots` | Numeric string. |
| `lowPrice` | `low_price` | `daily_price_bars`, `market_ohlcv_snapshots` | Numeric string. |
| `closePrice` | `close_price` | `daily_price_bars`, `market_ohlcv_snapshots` | Numeric string. |
| `changePrice` | `price_change` | `daily_quote_reports` | Numeric string. |
| `changePriceRatio` | `price_change_pct` | `daily_quote_reports` | Numeric percent-like string. |
| `mainVolume` | `matched_volume` | `daily_price_bars`, `daily_quote_reports` | Numeric string with comma separators. Unit must be confirmed. |
| `mainValue` | `trading_value` | `daily_price_bars`, `daily_quote_reports` | Numeric string with comma separators. Unit must be confirmed. |
| `averagePrice` | `average_price` | `daily_quote_reports`, `market_ohlcv_snapshots` | Numeric string. |
| `ceiling` | `ceiling_price` | `daily_quote_reports` | Numeric string. |
| `floor` | `floor_price` | `daily_quote_reports` | Numeric string. |
| `id` | `source_row_id` | all three | Preserve source row identity for lineage. |
| `securityName` | `security_name` | `daily_quote_reports` | Observed null in inspected rows. Do not require. |
| `isin` | `isin` | `daily_quote_reports` | Observed null in inspected rows. Prefer joining from HOSE listed universe. |
| `bloomberg` | `bloomberg_id` | `daily_quote_reports` | Observed null in inspected rows. Do not treat as FIGI without confirmation. |

#### Additional canonical metadata

A later parser dry run should add:

- `exchange = HOSE`
- `source_name = hose`
- `source_payload_id`
- `raw_content_hash`
- `raw_row_index`
- `parser_version`
- `schema_version`
- `data_status`
- `quality_status`
- `quality_reasons`

---

</details>

## 5. Numeric Normalization Risks

<details open>
<summary>Quote-report numeric fields are strings and need conservative parsing.</summary>

---

Observed examples include comma thousands separators:

- `mainVolume = "6,756.00"`
- `mainValue = "4,734.69"`

Parser risks:

- Empty strings should become null, not zero.
- `0.00` may mean no trade for some rows, especially when open/high/low/average are zero.
- Price units appear to be display price units, likely thousand VND-style market display units, but this must be confirmed before canonical database design.
- `mainVolume` and `mainValue` units must be documented from the HOSE source page text or source documentation.
- Commas in numeric strings should be treated as thousands separators for this payload shape.
- Preserve raw string values in debug output when the parser is later implemented so unit mistakes can be traced.

---

</details>

## 6. Completed-Day Versus Current-Day Semantics

<details open>
<summary>The completed-day sample can be planned as an EOD candidate; current-day must remain provisional.</summary>

---

Recommended `data_status` values:

- `final_candidate`
- `provisional`

Use `final_candidate` for the `2026-06-02` completed-day quote-report sample until the project confirms HOSE final EOD semantics.

Use `provisional` for the `2026-06-03` current-day quote-report sample unless the source proves the trading day is complete and final.

This distinction matters for backtesting:

- Current-day values can change during the trading session.
- Treating current-day provisional rows as final EOD bars can make historical tests non-reproducible.
- Joining provisional quote data into a simulated past decision can leak information that was not final at that simulated time.
- Completed-day and current-day outputs should never be mixed without an explicit `data_status`.

---

</details>

## 7. Instrument Universe Issue

<details open>
<summary>The quote-report appears broader than ordinary common-stock rows and should be joined against the listed universe.</summary>

---

The sample includes ordinary ticker-like symbols and warrant-like symbols. Examples of longer symbols observed in the completed-day sample include:

- `CACB2510`
- `CACB2511`
- `CDGC2601`
- `CFPT2517`

Parser planning should:

- Join quote-report symbols against the HOSE listed-universe output when possible.
- Classify stocks, ETFs, covered warrants, and other instrument types using listed-universe metadata.
- Keep unknown or unmatched symbols with warning reasons instead of silently dropping them.
- Avoid assuming every row maps to a common stock.
- Preserve `securitySymbol` exactly enough to trace source rows, while also storing a normalized uppercase `symbol`.

---

</details>

## 8. Data Quality Checks Needed

<details open>
<summary>The quote-report parser should validate identifiers, numeric fields, OHLC relationships, and data status.</summary>

---

Required checks:

- `symbol` is required.
- `trading_date` is required from request URL metadata.
- Price, volume, and value fields must parse numerically when present.
- `high_price >= low_price` when both are present and non-zero.
- `close_price` should be within high/low when the instrument traded.
- `open_price` should be within high/low when the instrument traded.
- `matched_volume >= 0`.
- `trading_value >= 0`.
- `ceiling_price >= floor_price`.
- Duplicate `symbol + trading_date + data_status` should fail.
- `data_status` is required and should distinguish completed-day from current-day/provisional records.
- No-trade rows with open/high/low/average equal to zero but close equal to prior close should be allowed with a warning or explicit note, not failed automatically.
- Quote-report symbols should be cross-checked against HOSE listed-universe symbols and instrument type metadata.

Recommended warning reasons:

- `warning_unmatched_listed_universe_symbol`
- `warning_provisional_current_day`
- `warning_no_trade_zero_ohlc`
- `warning_source_units_unconfirmed`
- `warning_security_name_missing`
- `warning_isin_missing`

---

</details>

## 9. Parser Risks

<details open>
<summary>The endpoint is usable but depends on request shape and local browser-derived headers.</summary>

---

Known risks:

- `POST` with `body_json={}` is required for the verified local probe.
- A browser-derived local header may be required; its value must stay local-only and must not be committed or printed.
- Response validation must continue to reject HTTP 200 HTML bodies containing `Request Rejected` or `The requested URL was rejected`.
- `trading_date` comes from the request URL, not from the observed row body.
- `tradingBy=VNINDEX` semantics are not fully confirmed.
- Historical date availability should be tested across multiple older trading days before database planning.
- Current-day row values may change during the trading session.
- Quote-report coverage may include stocks, ETFs, covered warrants, and other listed instruments.
- Numeric source units are not yet confirmed.

---

</details>

## 10. Readiness Decision

<details open>
<summary>The completed-day quote-report is ready for parser dry-run planning; current-day should be planned only as provisional.</summary>

---

| Dataset | Ready for parser dry-run planning? | Decision |
|---|---|---|
| HOSE completed-day quote report | Yes | The saved raw sample is row-level JSON with 662 rows and expected OHLCV-like quote fields. Plan it as `final_candidate`, not fully confirmed EOD. |
| HOSE current-day quote report | Yes, provisional only | The saved raw sample is row-level JSON with the same shape and row count, but current-day values should be tagged `provisional`. |

Remaining unknowns before database or backtest work:

- Final EOD status semantics.
- Price, volume, and trading value units.
- `tradingBy=VNINDEX` coverage semantics.
- Historical date availability.
- Instrument-type classification and join behavior against the listed universe.
- Trading-calendar alignment.

---

</details>

## 11. Recommended Next Step

<details open>
<summary>Implement a completed-day quote-report parser dry run before any database or backtest work.</summary>

---

Next safest implementation target:

Implement `HOSE quote-report completed-day parser dry-run`.

Suggested first input:

`data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report/payload.json`

Suggested outputs:

- `data/processed/dry_run/hose_quote_report/<run_id>/daily_price_bars.csv`
- `data/processed/dry_run/hose_quote_report/<run_id>/daily_quote_reports.csv`
- `data/processed/dry_run/hose_quote_report/<run_id>/market_ohlcv_snapshots.csv`
- `data/processed/dry_run/hose_quote_report/<run_id>/validation_report.md`
- `data/processed/dry_run/hose_quote_report/<run_id>/validation_summary.json`

Optional second input:

`data/raw/source_probe/source=hose/run_id=20260603T091759Z/hose_daily_quote_report_current_day/payload.json`

Only include current-day behavior if the parser assigns `data_status=provisional`.

Do not implement database migration or backtest in the quote-report parser dry run.

---

</details>
