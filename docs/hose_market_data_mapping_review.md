---
title: hose_market_data_mapping_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Market Data Mapping Review

## 1. Executive Summary

<details open>
<summary>HOSE listed-stock universe is now parser-ready; quote-report targets still need usable row-level payloads in the saved raw samples.</summary>

---

#### Verified HOSE probe targets

The latest HOSE source-probe run is:

`run_id=20260603T042853Z`

The run contains three configured HOSE targets:

- `hose_listed_stock_universe_api_candidate`
- `hose_daily_quote_report_completed_day_candidate`
- `hose_daily_quote_report_current_day_candidate`

#### Row-level evidence

- The listed-stock universe target returned row-level JSON with `data.list` rows and `data.paging` pagination metadata.
- The completed-day quote-report target returned HTTP 200, but the saved payload body is an HTML `Request Rejected` page, not row-level JSON.
- The current-day quote-report target also returned HTTP 200 with an HTML `Request Rejected` page, not row-level JSON.

#### Parser planning readiness

- HOSE listed-stock universe is ready for parser dry-run planning.
- HOSE completed-day quote report is not ready for parser dry-run planning from the current saved artifact, because no row-level quote data was captured.
- HOSE current-day quote report is not ready for parser dry-run planning from the current saved artifact. When captured successfully, it should be treated as a provisional snapshot unless final EOD status is confirmed.

#### Still not confirmed

- Whether `tradingBy=VNINDEX` returns all HOSE stock rows or only VNINDEX/index-related rows.
- Whether quote-report has pagination or another request shape for full-market data.
- Whether quote-report can retrieve older trading days reliably.
- Exact numeric units for price, volume, and trading value fields in quote-report data.
- Trading calendar, corporate actions, index constituent data, and index price endpoints.

---

</details>

## 2. Probe Evidence

<details open>
<summary>The latest run captured one usable JSON stock-universe sample and two quote-report rejection bodies.</summary>

---

| Target name | Dataset | Raw sample path | Metadata path | HTTP status | Content type | Observed row count | Likely canonical tables |
|---|---|---|---|---:|---|---:|---|
| `hose_listed_stock_universe_api_candidate` | `hose_listed_stock_universe` | `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_listed_stock_universe/payload.json` | `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_listed_stock_universe/metadata.json` | 200 | `application/json; charset=utf-8` | 30 rows on page 1; 403 total via pagination | `securities_master`, `exchange_listings`, `symbol_universe` |
| `hose_daily_quote_report_completed_day_candidate` | `hose_daily_quote_report` | `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_daily_quote_report/payload.html` | `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_daily_quote_report/metadata.json` | 200 | `text/html; charset=utf-8` | 0 usable quote rows; saved body is request rejection HTML | Intended: `daily_price_bars`, `daily_quote_reports`, `market_ohlcv_snapshots` |
| `hose_daily_quote_report_current_day_candidate` | `hose_daily_quote_report_current_day` | `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_daily_quote_report_current_day/payload.html` | `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_daily_quote_report_current_day/metadata.json` | 200 | `text/html; charset=utf-8` | 0 usable quote rows; saved body is request rejection HTML | Intended: `daily_price_bars`, `daily_quote_reports`, `market_ohlcv_snapshots` |

Terms notes from metadata:

- Listed-stock universe: public HOSE listed-stock API discovered from browser Network tab. Use for listed stock universe and exchange listing metadata, not OHLCV.
- Completed-day quote report: public HOSE quote-report API discovered from browser Network tab. Needs validation for final EOD status, units, pagination, and whether `tradingBy=VNINDEX` covers all HOSE stocks.
- Current-day quote report: because the trading day may not be finished, treat this as provisional/intraday-like snapshot, not confirmed final EOD data.

---

</details>

## 3. Listed Stock Universe Review

<details open>
<summary>The listed-stock universe response is a paginated JSON API with row-level listing metadata.</summary>

---

#### Endpoint

`https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=30&alphabet=&sectorId=`

#### Top-level JSON fields

- `data`
- `success`
- `message`

#### Container fields

Inside `data`:

- `list`
- `object`
- `paging`

Inside `data.paging`:

- `pageIndex`
- `pageSize`
- `totalCount`
- `totalPages`

Observed pagination:

- `pageIndex=1`
- `pageSize=30`
- `totalCount=403`
- `totalPages=14`

#### Row fields observed

The first row includes these fields:

- `id`
- `name`
- `code`
- `brief`
- `address`
- `phone`
- `fax`
- `webUrl`
- `director`
- `spokesman`
- `capital`
- `securitiesType`
- `displayText`
- `reason`
- `isin`
- `bloomberg`
- `parValue`
- `regDate`
- `ftdate`
- `affectDate`
- `acceptDate`
- `listDate`
- `listingStatusId`
- `listingVolume`
- `listingValue`
- `outStanding`
- `adjOutStanding`
- `turnoverRatio`
- `foreignOwnedRatio`
- `stateOwnedRatio`
- `avgOutStanding`
- `changeOutStanding`
- `treasuryVol`
- `issueOwner`
- `intRate`
- `term`
- `invFirmName`
- `refIndex`
- `cwName`
- `cwType`
- `underlyingSymbol`
- `authOrg`
- `perIntPayment`
- `intPayMethod`
- `traddingDate`
- `lastTraddingDate`
- `maturityDate`

#### Observed examples

| Code | ISIN | Bloomberg / FIGI-like field | Securities type | Listing volume | Outstanding volume | List date raw | Notes |
|---|---|---|---:|---:|---:|---:|---|
| `AAA` | `VN000000AAA4` | `BBG000BB42R4` | 1 | `393,742,730` | `393,742,730` | `1466640000` | `displayText` combines symbol and company name. |
| `AAM` | `VN000000AAM9` | `BBG000PDD0V4` | 1 | `12,346,411` | `10,451,182` | `-62135596800` | Sentinel date appears and should become null. |
| `AAN` | `VN000000AAN7` | `BBG022JL54J2` | 1 | `65,000,000` | `65,000,000` | `1770854400` | Future-looking timestamp should be validated before use. |

#### Proposed mapping

| Raw field | Proposed canonical table | Proposed canonical field | Notes |
|---|---|---|---|
| `code` | `securities_master`, `exchange_listings`, `symbol_universe` | `symbol` | Required. Trim and uppercase. |
| Source identity | `exchange_listings`, `symbol_universe` | `exchange` | Normalize to `HOSE` because this endpoint is under HSX/HOSE. |
| `id` | `securities_master` | `source_security_id` | Preserve source id. |
| `name` | `securities_master` | `company_name` | UTF-8 text; parser must avoid mojibake. |
| `brief` | `securities_master` | `short_name` | Optional. |
| `isin` | `securities_master` | `isin` | Validate if present. |
| `bloomberg` | `securities_master` | `figi_or_bloomberg_id` | The field name is `bloomberg`; confirm whether value is OpenFIGI-like before naming final column. |
| `securitiesType` | `exchange_listings` | `security_type_code` | Need lookup table for numeric codes. |
| `capital` | `securities_master` | `charter_capital_vnd` | Numeric. |
| `parValue` | `securities_master` | `par_value_vnd` | Numeric. |
| `listingVolume` | `exchange_listings` | `listed_volume` | String with thousands separators; parse to integer. |
| `listingValue` | `exchange_listings` | `listed_value_vnd` | String with thousands separators; parse to integer. |
| `outStanding` | `securities_master` | `outstanding_volume` | String with thousands separators; parse to integer. |
| `adjOutStanding` | `securities_master` | `adjusted_outstanding_volume` | Optional numeric string. |
| `treasuryVol` | `securities_master` | `treasury_volume` | Optional numeric string. |
| `foreignOwnedRatio` | `securities_master` | `foreign_owned_ratio_pct` | Numeric percent. |
| `stateOwnedRatio` | `securities_master` | `state_owned_ratio_pct` | Numeric percent. |
| `regDate` | `exchange_listings` | `registration_date` | Epoch-like seconds; sentinel negative value should become null. |
| `ftdate` | `exchange_listings` | `first_trading_date` | Confirm semantics. |
| `acceptDate` | `exchange_listings` | `acceptance_date` | Confirm semantics. |
| `listDate` | `exchange_listings` | `listing_date` | Epoch-like seconds; sentinel negative value should become null. |
| `listingStatusId` | `exchange_listings` | `listing_status_id` | Need lookup table. |
| `displayText` | `symbol_universe` | `display_text` | Useful UI label and parse cross-check. |

#### Parser planning notes

- The parser should fetch all pages, not only page 1.
- Parser dry-run should write `securities_master.csv`, `exchange_listings.csv`, `symbol_universe.csv`, `validation_report.md`, and `validation_summary.json`.
- The first dry-run parser should use the saved page-1 raw sample only, then separately plan a full pagination probe/parser.

---

</details>

## 4. Daily Quote Report Review

<details open>
<summary>The quote-report endpoints are discovered but the saved raw bodies are not usable row-level quote data.</summary>

---

#### Completed-day endpoint

`https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=2026-06-02`

Saved payload:

`data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_daily_quote_report/payload.html`

Observed body:

- HTML page with title `Request Rejected`.
- Body text says the requested URL was rejected and includes a support id.
- No JSON top-level fields.
- No row/list container field.
- No symbol rows.
- No observed quote fields.

#### Current-day endpoint

`https://api.hsx.vn/mk/api/v1/market/quote-report?tradingBy=VNINDEX&date=2026-06-03`

Saved payload:

`data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_daily_quote_report_current_day/payload.html`

Observed body:

- HTML page with title `Request Rejected`.
- Body text says the requested URL was rejected and includes a support id.
- No JSON top-level fields.
- No row/list container field.
- No symbol rows.
- No observed quote fields.

#### Date handling

The date appears in the request URL. It is not present in the saved quote-report payloads because the payloads are rejection HTML. A future successful parser should treat URL date as request metadata and should still verify whether the response body contains its own trading date.

#### Pagination and coverage

Pagination is not confirmed for quote-report. Coverage is also not confirmed:

- `tradingBy=VNINDEX` may mean all HOSE market rows, VNINDEX-related rows, index constituents, or another report grouping.
- A successful row-level response is needed before deciding whether this endpoint can populate full-market daily bars.

#### Intended mapping if a future row-level JSON payload is captured

| Expected raw field | Proposed canonical table | Proposed canonical field | Notes |
|---|---|---|---|
| Symbol/code field | `daily_price_bars`, `daily_quote_reports`, `market_ohlcv_snapshots` | `symbol` | Required. Field name not observed yet. |
| Request `date` or response trading date | `daily_price_bars`, `daily_quote_reports` | `trading_date` | Required. Completed-day versus provisional status must be explicit. |
| Ceiling price | `daily_quote_reports` | `ceiling_price` | Expected but not observed. |
| Floor price | `daily_quote_reports` | `floor_price` | Expected but not observed. |
| Reference/prior close | `daily_quote_reports`, `daily_price_bars` | `prior_close` | Expected but not observed. |
| Open price | `daily_price_bars` | `open_price` | Expected but not observed. |
| Close/matched price | `daily_price_bars` | `close_price` | Expected but not observed. |
| Price change | `daily_quote_reports` | `price_change` | Expected but not observed. |
| Price change percent | `daily_quote_reports` | `price_change_pct` | Expected but not observed. |
| Low price | `daily_price_bars` | `low_price` | Expected but not observed. |
| High price | `daily_price_bars` | `high_price` | Expected but not observed. |
| Matched volume | `daily_price_bars`, `daily_quote_reports` | `matched_volume` | Expected but not observed. |
| Trading value | `daily_price_bars`, `daily_quote_reports` | `trading_value` | Expected but not observed. |

#### Parser planning decision

Do not implement quote-report parser dry run from these saved quote-report artifacts. The correct next step is to re-probe quote-report with the browser-observed request requirements until the local raw sample contains actual row-level JSON.

---

</details>

## 5. Completed-Day Versus Current-Day Semantics

<details open>
<summary>Completed-day and current-day quote data must be treated differently to avoid leakage.</summary>

---

When a row-level quote-report payload is successfully captured:

- Treat `2026-06-02` quote-report as a completed-day EOD candidate, but only after confirming the trading day was closed and the report is final.
- Treat `2026-06-03` quote-report as current-day or provisional snapshot unless final EOD status is confirmed.
- Store a `data_status` or equivalent field such as `completed_eod`, `provisional_current_day`, or `unknown`.

Why this matters:

- A backtest must not use a current-day provisional value as if it were finalized after market close.
- Current-day values can change during the session and can leak future intraday information if joined incorrectly.
- If a signal is generated at close, execution must be next-bar or later, not at the same close used to create the signal.

---

</details>

## 6. Parser Risks

<details open>
<summary>HOSE parser planning must account for pagination, source semantics, and anti-bot/rejection behavior.</summary>

---

#### Listed-stock universe risks

- Pagination must be complete: page 1 has 30 rows, while `totalCount=403` and `totalPages=14`.
- Numeric strings contain thousands separators.
- Epoch-like date fields include sentinel negative values such as `-62135596800`.
- Vietnamese names must remain UTF-8 and should not be stored as mojibake.
- `securitiesType` and `listingStatusId` need lookup semantics.
- Some date values may appear future-looking and need validation before use.

#### Quote-report risks

- The saved quote-report bodies are request rejection HTML, despite HTTP 200.
- Content type may not be enough to decide success; parser/probe must inspect body shape.
- `tradingBy` parameter semantics are not confirmed.
- Date parameter may not equal actual trading calendar date if the date is holiday/weekend/non-trading day.
- Current-day values may be provisional.
- Numeric price units and trading value units are not observed yet.
- Pagination, if any, is not observed yet.
- Symbol universe alignment against the listed-stock universe is required.

---

</details>

## 7. Data Quality Checks Needed

<details open>
<summary>The universe parser can be planned now; quote-report checks remain conditional on a successful JSON sample.</summary>

---

#### Stock universe checks

- Required `symbol` from raw `code`.
- Unique symbol per exchange in the parsed page or full crawl.
- Normalize exchange to `HOSE`.
- Validate `isin` format when present.
- Preserve `bloomberg` field and confirm final naming before treating it as FIGI.
- Parse `listingVolume`, `listingValue`, `outStanding`, `adjOutStanding`, and `treasuryVol` as numeric values.
- Parse `capital` and `parValue` as numeric values.
- Parse epoch-like date fields and convert sentinel negative dates to null with warnings.
- Validate pagination completeness: fetched page count must match `totalPages`, and parsed total rows should match `totalCount` for full crawl.

#### Daily quote-report checks

Only apply these after a successful row-level quote-report JSON payload is captured:

- Required `symbol`.
- Required `trading_date`, from response body or request metadata.
- OHLC numeric fields parseable.
- `high_price >= low_price`.
- `close_price` within high/low when all are present.
- `open_price` within high/low when all are present.
- `matched_volume >= 0`.
- `trading_value >= 0`.
- Explicit `data_status` for completed-day versus provisional current-day.
- Deduplicate by `symbol + trading_date + data_status + source_payload_id`.
- Cross-check quote-report symbols against the HOSE universe parser output.

---

</details>

## 8. Readiness Decision

<details open>
<summary>Only the listed-stock universe should move to parser dry-run planning from the current artifacts.</summary>

---

| Dataset | Ready for parser dry-run planning? | Decision |
|---|---|---|
| HOSE listed stock universe | Yes | The saved raw sample is row-level JSON with a clear `data.list` container and pagination metadata. |
| HOSE completed-day quote report | No | The saved raw sample is HTML request-rejection content, not quote rows. Re-probe is required before parser planning. |
| HOSE current-day quote report | No | The saved raw sample is HTML request-rejection content. When captured correctly, plan it as provisional snapshot data only. |

---

</details>

## 9. Remaining HOSE Discovery Tasks

<details open>
<summary>HOSE still needs market-data endpoint confirmation beyond the listed-stock universe.</summary>

---

- Capture all pages of the listed-stock universe endpoint or confirm the pagination pattern.
- Re-probe quote-report until the saved raw sample contains actual row-level JSON, not request-rejection HTML.
- Confirm whether `tradingBy=VNINDEX` covers all HOSE stock rows, index constituents, or a report grouping.
- Confirm whether quote-report can retrieve older trading days reliably.
- Discover the trading calendar endpoint.
- Discover corporate actions endpoint.
- Discover index constituent endpoint.
- Discover index data endpoint.
- Confirm whether price board/order book snapshots have a separate endpoint.
- Confirm required headers/cookies/referrer behavior without storing secrets.

---

</details>

## 10. Recommended Next Step

<details open>
<summary>The safest next implementation step is a HOSE listed-universe parser dry run.</summary>

---

Implement a HOSE listed-stock universe parser dry run first.

Suggested dry-run scope:

- Input: `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_listed_stock_universe/payload.json`
- Output:
  - `data/processed/dry_run/hose_listed_universe/<run_id>/securities_master.csv`
  - `data/processed/dry_run/hose_listed_universe/<run_id>/exchange_listings.csv`
  - `data/processed/dry_run/hose_listed_universe/<run_id>/symbol_universe.csv`
  - `data/processed/dry_run/hose_listed_universe/<run_id>/validation_report.md`
  - `data/processed/dry_run/hose_listed_universe/<run_id>/validation_summary.json`

Do not implement quote-report parser, database writes, or backtest until a usable row-level quote-report JSON sample is captured and reviewed.

---

</details>
