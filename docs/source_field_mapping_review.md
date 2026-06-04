# Source Field Mapping Review

## Summary

This review inspects the latest verified raw source-probe samples under `data/raw/source_probe` for the focused source scope: `fred`, `hose`, `vbma`, and `vietcap_iq`.

No ingestion decision below promotes a source to production use. The purpose is to decide whether each verified sample is sufficient for ingestion v2 planning.

| Source | Target | Dataset | Raw sample | Dataset type | Likely canonical tables | Ready for ingestion v2 planning? | Decision |
|---|---|---|---|---|---|---|---|
| `fred` | `fred_dgs10_observations_candidate` | `fred_observations` | `data/raw/source_probe/source=fred/run_id=20260602T072716Z/fred_observations/payload.json` | Global macro time-series observations | `macro_series`, `macro_observations`, `macro_features` | Yes | Ready for macro-context ingestion planning only |
| `hose` | `hose_listed_symbols_candidate` | `hose_listed_symbols` | `data/raw/source_probe/source=hose/run_id=20260602T074355Z/hose_listed_symbols/payload.html` | HOSE website/app shell for listing metadata surface | `securities` first; maybe `daily_prices`, `realtime_quote_snapshots`, `corporate_events` after more endpoints | No | Needs manual Network-tab endpoint discovery |
| `vbma` | `vbma_primary_market_auction_csv` | `vbma_primary_market_auction_results` | `data/raw/source_probe/source=vbma/run_id=20260602T085214Z/vbma_primary_market_auction_results/payload.txt` | Bond auction result spreadsheet served from CSV-like endpoint | `bond_auctions`, `bond_instruments`, `yield_curve_points`, `macro_context_events` | Yes | Ready for VBMA auction ingestion planning |
| `vietcap_iq` | `vietcap_iq_research_center_candidate` | `vietcap_iq_research_reports` | `data/raw/source_probe/source=vietcap_iq/run_id=20260602T090035Z/vietcap_iq_research_reports/payload.html` | Public research center / Vietcap IQ report surface HTML | `research_reports`, `company_research_signals`, `macro_research_notes`, `market_commentary` | No | Needs report-list API endpoint discovery |

## FRED

### Probe Evidence

| Item | Value |
|---|---|
| Target name | `fred_dgs10_observations_candidate` |
| Dataset | `fred_observations` |
| Raw sample path | `data/raw/source_probe/source=fred/run_id=20260602T072716Z/fred_observations/payload.json` |
| Metadata path | `data/raw/source_probe/source=fred/run_id=20260602T072716Z/fred_observations/metadata.json` |
| HTTP status | `200` |
| Content type | `application/json; charset=UTF-8` |
| Terms notes | Use FRED/fredapi for global macro context only, not stock OHLCV. |

### Observed Structure

Top-level response fields:

- `realtime_start`
- `realtime_end`
- `observation_start`
- `observation_end`
- `units`
- `output_type`
- `file_type`
- `order_by`
- `sort_order`
- `count`
- `offset`
- `limit`
- `observations`

Observation fields:

- `realtime_start`
- `realtime_end`
- `date`
- `value`

The sample is for `DGS10`, with `count=16804` and `limit=5`.

### Field Mapping

| Raw field | Proposed canonical table | Proposed canonical field | Notes |
|---|---|---|---|
| configured `series_id` | `macro_series` | `series_id` | Must be preserved from request params or source URL. |
| `units` | `macro_series` | `unit` | Example value from sample: `lin`. |
| `observation_start` | `macro_series` | `observation_start` | Series-level metadata. |
| `observation_end` | `macro_series` | `observation_end` | Series-level metadata. |
| `count` | probe/report metadata | `source_observation_count` | Useful for inventory, not a normalized observation field. |
| `observations[].date` | `macro_observations` | `observation_date` | Parse as date. |
| `observations[].value` | `macro_observations` | `observation_value` | Parse numeric; FRED may use `.` for missing values. |
| `observations[].realtime_start` | `macro_observations` | `realtime_start` | Needed for point-in-time handling. |
| `observations[].realtime_end` | `macro_observations` | `realtime_end` | Needed for revision windows. |

### Missing Fields

- Human-readable series title is not present in this observations response.
- Frequency and seasonal-adjustment labels are not present unless fetched from a series metadata endpoint.
- Source request series id is not a body field, so ingestion must persist it from config/request context.

### Parser Risks

- `value` is a string and can be `.` for missing observations.
- FRED realtime revision fields must not be discarded if later point-in-time analysis matters.
- API key must stay outside raw metadata and reports.
- This is macro context only; it must not be treated as equity OHLCV.

### Data Quality Checks Needed

- Required fields: `series_id`, `date`, `value`, `realtime_start`, `realtime_end`.
- Parse `date`, `realtime_start`, and `realtime_end` as dates.
- Convert numeric values, preserving missing `.` as null with a warning.
- Deduplicate by `series_id + observation_date + realtime_start`.
- Confirm requested series id, row count, and returned limit.

### Readiness Decision

FRED is ready for ingestion v2 planning for macro context tables only. It should not block stock-market ingestion and must not be represented as a stock OHLCV source.

## HSX/HOSE

### Probe Evidence

| Item | Value |
|---|---|
| Target name | `hose_listed_symbols_candidate` |
| Dataset | `hose_listed_symbols` |
| Raw sample path | `data/raw/source_probe/source=hose/run_id=20260602T074355Z/hose_listed_symbols/payload.html` |
| Metadata path | `data/raw/source_probe/source=hose/run_id=20260602T074355Z/hose_listed_symbols/metadata.json` |
| HTTP status | `200` |
| Content type | `text/html` |
| Terms notes | Official HSX/HOSE listed-symbol candidate. Use for symbol universe/listing metadata, not OHLCV. |

### Observed Structure

The sample is an HTML shell for a JavaScript app, not a listing data payload. Visible structure includes:

- HOSE page metadata and Vietnamese title/description.
- React-style app root: `id="HOSE"`.
- Static JavaScript bundle reference: `/static/js/main.d430e296.js`.
- No parsed listing rows in the raw HTML sample.
- Metadata reports `original_columns=[]` and `row_count=1`.

### Field Mapping

| Raw field / visible structure | Proposed canonical table | Proposed canonical field | Notes |
|---|---|---|---|
| Page/app shell URL | source inventory | `endpoint_or_surface` | Verifies official surface reachability only. |
| Intended listing endpoint parameters | `securities` | `symbol`, `exchange`, `company_name`, `security_type` | Not observed in the returned HTML. Needs actual JSON/XHR endpoint. |
| HOSE source identity | `securities` | `exchange` | Can be inferred as `HOSE` only after row-level symbols are captured. |
| Potential app bundle | manual investigation | endpoint discovery input | Inspect JS bundle or Network tab for API endpoint paths. |

### Missing Fields

- Symbol/code rows.
- Company name.
- Security type.
- Listing status.
- Sector/industry.
- Exchange/floor row field.
- Pagination metadata from an actual data response.
- Any OHLCV fields.

### Parser Risks

- Current sample is only an app shell; parsing it would create false confidence.
- Useful data may be loaded by JavaScript through separate XHR/fetch calls.
- Endpoint parameters may require exact headers, cookies, language, pagination, or anti-cache fields.
- Encoding and Vietnamese text should be handled as UTF-8.

### Data Quality Checks Needed

For a future listing-data endpoint:

- Required fields: `symbol`, `exchange`, `company_name`, `security_type` where available.
- Normalize exchange to `HOSE`.
- Deduplicate symbol rows.
- Track pagination completeness.
- Preserve raw endpoint parameters and response hash.
- Confirm symbols such as `FPT` and `VNM` appear in captured listing data.

### Readiness Decision

HOSE is not ready for ingestion v2 planning yet. It is ready for targeted manual source investigation. The next step is to capture the actual listing/universe XHR endpoint and then separately probe market-data, corporate-action, index, and calendar endpoints.

## VBMA

### Probe Evidence

| Item | Value |
|---|---|
| Target name | `vbma_primary_market_auction_csv` |
| Dataset | `vbma_primary_market_auction_results` |
| Raw sample path | `data/raw/source_probe/source=vbma/run_id=20260602T085214Z/vbma_primary_market_auction_results/payload.txt` |
| Metadata path | `data/raw/source_probe/source=vbma/run_id=20260602T085214Z/vbma_primary_market_auction_results/metadata.json` |
| HTTP status | `200` |
| Content type | `application/octet-stream` |
| Terms notes | Public VBMA primary-market CSV discovered from browser Network tab. SSL verification disabled only for this local probe target because Python cannot verify the site's certificate chain in this environment. Not related to stock OHLCV. |

### Observed Structure

Despite the `.csv` endpoint name, the payload begins with an XLSX ZIP signature and parses as a spreadsheet. The observed sheet name is:

- `Kết quả đấu thầu theo đợt Eng`

Parsed sample size:

- 3,268 rows.

Observed columns:

- `Mã trái phiếu`
- `Tổ chức phát hành`
- `Kỳ hạn\n(năm)`
- `Ngày TCPH`
- ` Giá trị gọi thầu\n(tỷ đồng) `
- ` Giá trị đặt thầu\n(tỷ đồng) `
- ` Giá trị trúng thầu\n(tỷ đồng) `
- `Lãi suất trúng thầu (%/y)`
- `Lãi suất đấu thầu max`
- `Lãi suất đấu thầu min`

### Field Mapping

| Raw field | Proposed canonical table | Proposed canonical field | Notes |
|---|---|---|---|
| `Mã trái phiếu` | `bond_auctions`, `bond_instruments` | `bond_code` | Also a candidate instrument key. |
| `Tổ chức phát hành` | `bond_auctions`, `bond_instruments` | `issuer` | Example observed issuer: `KBNN`. |
| `Kỳ hạn\n(năm)` | `bond_auctions`, `bond_instruments` | `tenor_years` | Numeric tenor. |
| `Ngày TCPH` | `bond_auctions` | `auction_or_issue_date` | Need confirm Vietnamese label meaning before final naming. |
| `Giá trị gọi thầu\n(tỷ đồng)` | `bond_auctions` | `offered_amount_billion_vnd` | Strip whitespace/newlines from header. |
| `Giá trị đặt thầu\n(tỷ đồng)` | `bond_auctions` | `bid_amount_billion_vnd` | Numeric amount. |
| `Giá trị trúng thầu\n(tỷ đồng)` | `bond_auctions` | `winning_amount_billion_vnd` | Numeric amount. |
| `Lãi suất trúng thầu (%/y)` | `bond_auctions`, `yield_curve_points` | `winning_yield_pct` | Convert dash values to null. |
| `Lãi suất đấu thầu max` | `bond_auctions` | `bid_yield_max_pct` | Numeric or null. |
| `Lãi suất đấu thầu min` | `bond_auctions` | `bid_yield_min_pct` | Numeric or null. |

### Missing Fields

- Separate maturity date.
- Coupon.
- Bid-to-cover ratio, though it can be derived as bid amount / offered amount when both are valid.
- Auction session id.
- Currency.
- Whether amounts are always VND billions.
- Report/publication timestamp.

### Parser Risks

- Endpoint is named `.csv` but returns XLSX content.
- Metadata currently records `application/octet-stream`, so parser selection should inspect file signature, not extension.
- Vietnamese headers include spaces and newline characters.
- Some numeric fields contain `-` when no bid or no winning result exists.
- `verify_ssl=false` is target-local and should remain a documented exception, not a global default.

### Data Quality Checks Needed

- Required fields: `bond_code`, `issuer`, `tenor_years`, `auction_or_issue_date`.
- Parse dates.
- Convert amount and yield fields to numeric with `-` as null.
- Check `winning_amount <= bid_amount` when both are present.
- Check `bid_amount >= 0`, `offered_amount >= 0`, `winning_amount >= 0`.
- Check yield values are non-negative and within a plausible range.
- Deduplicate by `bond_code + auction_or_issue_date`.
- Flag rows with zero bids or zero winning amount.

### Readiness Decision

VBMA is ready for ingestion v2 planning for bond auction results. It is not a stock OHLCV source. The immediate ingestion design should support XLSX payload parsing even when the endpoint path uses `.csv`.

## Vietcap IQ

### Probe Evidence

| Item | Value |
|---|---|
| Target name | `vietcap_iq_research_center_candidate` |
| Dataset | `vietcap_iq_research_reports` |
| Raw sample path | `data/raw/source_probe/source=vietcap_iq/run_id=20260602T090035Z/vietcap_iq_research_reports/payload.html` |
| Metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260602T090035Z/vietcap_iq_research_reports/metadata.json` |
| HTTP status | `200` |
| Content type | `text/html` |
| Terms notes | Public Vietcap Research Center / Vietcap IQ-related research report surface. Use for company reports, market commentary, macro/strategy notes, and analyst views. Do not use as stock OHLCV source. |

### Observed Structure

The sample is a public research center HTML page. Visible structures include:

- Redirect script from Vietcap research center to `https://trading.vietcap.com.vn/iq/report?...`.
- Research category mappings: company research, market commentary, technical analysis, sector reports, macroeconomics, strategy, fixed income.
- HTML metadata with `apiUrl` pointing to `https://www.vietcap.com.vn/api/cms-service`.
- UI text for report filtering and report listing, including company filter and tag filter placeholders.
- No directly extracted report list rows in the current raw sample.

### Field Mapping

| Raw field / visible structure | Proposed canonical table | Proposed canonical field | Notes |
|---|---|---|---|
| `researchIQLinkMapping` categories | `research_reports` | `report_category` | Needs actual report-list API response for row-level mapping. |
| `vietcapIQLink` report URL | source inventory | `report_surface_url` | Useful for next manual endpoint discovery. |
| `apiUrl` meta value | source inventory | `api_base_url` | Candidate CMS API base, not yet verified for report rows. |
| UI company filter placeholder | `research_reports` | `company_symbol` / `company_name` | Indicates company-filtered reports likely exist, not yet captured. |
| UI tag filter placeholder | `research_reports` | `tags` | Indicates tag metadata likely exists. |
| Page title / report labels | `research_reports` | `source_page_context` | Not enough for report ingestion. |

### Missing Fields

- Report id.
- Report title.
- Published date.
- Analyst/author.
- Company ticker.
- Sector.
- Category.
- Language.
- Report summary.
- Download/document URL.
- Full report document bytes or stable document id.
- Pagination metadata.

### Parser Risks

- Current sample is a page shell plus client-side components, not the report API payload.
- Some content is hydrated by JavaScript/Astro islands.
- It may redirect to `trading.vietcap.com.vn/iq/report`, so the useful endpoint may be outside the public company website host.
- Access/auth/terms for Vietcap IQ report APIs must be reviewed before crawling.
- Search/filter UI can mislead if parser only scrapes visible placeholder text.

### Data Quality Checks Needed

For a future report-list/document endpoint:

- Required fields: `report_id`, `title`, `published_at`, `url` or document id, `source`.
- Parse and timezone-normalize `published_at`.
- Deduplicate by stable report id or content hash.
- Verify document URL availability.
- Track category, language, company symbol, and analyst fields when present.
- Preserve raw HTML/API response and document content hash.
- Enforce timestamp alignment before using reports as evidence.

### Readiness Decision

This older Vietcap IQ report-surface sample was not ready for report/document ingestion planning by itself. Later work verified the Vietcap IQ search-bar JSON as the broad full-market fetch universe candidate; report-list, document, financial-statement, and OHLCV ingestion still need separate source discovery before DB/backtest use.

## Final Recommendation

| Source | Recommendation |
|---|---|
| `vbma` | Plan ingestion v2 for `bond_auctions` first. The sample is structured enough, has row-level data, and has clear canonical mapping. |
| `fred` | Plan ingestion v2 for `macro_observations` and `macro_series` after defining macro-series config. It is structured and verified, but context-only. |
| `hose` | Continue manual Network-tab investigation. Capture actual JSON/XHR endpoints for listed symbols first, then OHLCV/price board/corporate actions. |
| `vietcap_iq` | Continue manual Network-tab investigation. Capture report-list and document endpoints before ingestion planning. |

The best next implementation planning target is VBMA auction ingestion, followed by FRED macro observations. HOSE and Vietcap IQ should not move into ingestion until raw row-level data endpoints are captured and reviewed.
