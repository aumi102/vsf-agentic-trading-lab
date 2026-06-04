---
title: 01_vietcap_iq
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Review

### Snapshot

<details open>
<summary>Vietcap IQ is now the preferred full-market universe candidate, while reports remain evidence inputs.</summary>

---

#### Mentor direction

- Vietcap IQ should be treated as the main candidate provider for the full Vietnamese market universe.
- Mentor guidance says Vietcap IQ can provide around 1600 symbols.
- HOSE listed universe currently has 403 symbols, so it is HOSE-specific and should not be treated as the full-market universe.
- Vietcap IQ universe discovery should support `securities_master`, `exchange_listings`, `symbol_universe`, and `instrument_universe`.
- This remains discovery/probe stage until a row-level payload is verified and source terms are reviewed.

---

#### Source role

- **source** = Vietcap IQ / Vietcap Trading browser-observed data surfaces.
- **primary candidate use** = full-market symbol and instrument universe.
- **secondary use** = company profiles, financial statements, financial ratios, company reports, and document/evidence metadata.
- **agent usage later** = FA Agent, Evidence Agent, Strategy Agent, and Answer Composer.
- **MVP stance** = probe Vietcap IQ universe first; do not promote it to canonical storage until raw fields, coverage, access, and terms are verified.

---

</details>

### Candidate URL Assessment

<details open>
<summary>Browser-observed Vietcap endpoints should be probed safely before parser planning.</summary>

---

| Priority | URL | Classification | Why it matters | Next action |
|---|---|---|---|---|
| P0 | `https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1` | likely universe candidate | Strongest full-market symbol search/universe candidate; may expose around 1600 instruments if mentor guidance matches payload. | Add to local probe config first and verify row-level JSON fields. |
| P1 | `https://trading.vietcap.com.vn/order/locales/vi/stock-asset.json?v=1780043897253` | secondary universe candidate | May contain stock asset localization or symbol list. | Probe only if the P0 search-bar payload is incomplete. |
| P1 | `https://trading.vietcap.com.vn/order/locales/vi/stock-asset-bond.json?v=1780043897253` | secondary universe candidate | May contain bond or mixed instrument asset labels. | Probe after P0 if bond/instrument classification is needed. |
| P2 | `https://trading.vietcap.com.vn/vietcap-iq/language/vi/company.json?v=1778834931080` | metadata/localization | Likely label/localization data for company UI fields, not the universe itself. | Use only to decode labels if needed. |
| P2 | `https://trading.vietcap.com.vn/vietcap-iq/language/vi/market.json?v=1778834931080` | metadata/localization | Likely label/localization data for market UI fields. | Use only to decode labels if needed. |
| P2 | `https://trading.vietcap.com.vn/api/market-data-service/v1/data-version` | metadata/localization | May expose data version metadata, not row-level universe. | Probe later to understand cache/version behavior. |
| P3 | `https://trading.vietcap.com.vn/api/price/marketStatus/getAll` | market status | Market/session state, not full universe. | Context-only; does not replace universe source. |
| P3 | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VNINDEX/price-chart?lengthReport=3&toCurrent=true` | chart-specific | Index-specific chart data for `VNINDEX`, not full universe. | Not a universe target. |
| P3 | `https://trading.vietcap.com.vn/vietcap-iq/data/stock-with-highest.json` | ranking/top list | Ranking/list endpoint, likely partial by design. | Not a full-universe target. |
| P3 | `https://trading.vietcap.com.vn/api/market-data-service/v1/tickers/price/top-stock` | ranking/top list | Top-stock endpoint, partial by design. | Not a full-universe target. |

---

</details>

### Verified Search-Bar Probe Result

<details open>
<summary>The Vietcap IQ search-bar probe returned row-level symbol and instrument data.</summary>

---

#### Probe classification

| Target | Dataset | Classification | Notes |
|---|---|---|---|
| `vietcap_iq_research_center_candidate` | `vietcap_iq_research_reports` | verified HTML/non-universe | Useful research/report surface, but not a row-level universe payload. |
| `vietcap_iq_company_search_bar_universe_candidate` | `vietcap_iq_company_search_bar` | verified usable JSON | Strong full-market universe candidate with row-level symbol and instrument fields. |

---

#### Search-bar evidence

| Item | Value |
|---|---|
| run_id | `20260604T081901Z` |
| target name | `vietcap_iq_company_search_bar_universe_candidate` |
| dataset | `vietcap_iq_company_search_bar` |
| raw path | `data/raw/source_probe/source=vietcap_iq/run_id=20260604T081901Z/vietcap_iq_company_search_bar/payload.json` |
| metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260604T081901Z/vietcap_iq_company_search_bar/metadata.json` |
| content type | `application/json` |
| top-level JSON fields | `serverDateTime`, `traceId`, `status`, `code`, `msg`, `exception`, `successful`, `data` |
| list/container field | `data` |
| observed data rows | 2080 |
| source-probe metadata row count | 1 top-level envelope row |

---

#### Observed row fields

Observed row fields include:

- `id`
- `name`
- `floor`
- `phone`
- `fax`
- `code`
- `shortName`
- `logoUrl`
- `tax`
- `organCode`
- `icbLv1`
- `icbLv2`
- `icbLv3`
- `icbLv4`
- `isBank`
- `isIndex`
- `comTypeCode`
- `inCu`
- `upsideToTpPercentage`
- `projectedTsrPercentage`
- `currentPrice`
- `dividendPerShareTsr`
- `targetPrice`
- `bank`
- `index`

Example row shape, shortened:

| Field | Example |
|---|---|
| `code` | `STK` |
| `name` | `Công ty Cổ phần Sợi Thế Kỷ` |
| `shortName` | `Sợi Thế Kỷ` |
| `floor` | `HOSE` |
| `organCode` | `CENTURY` |
| `comTypeCode` | `CT` |
| `isIndex` | `false` |
| `isBank` | `false` |

Observed `floor` values include `HOSE`, `HNX`, `UPCOM`, `OTC`, `OTHER`, and `STOP`. This is broader than the HOSE-specific 403-symbol listed universe and is consistent with mentor guidance that Vietcap IQ can expose a much larger full-market universe. The observed 2080 rows are above the rough 1600-symbol expectation, likely because the search-bar universe includes non-common-stock instruments, indexes, OTC/other entries, or inactive/status-specific rows.

---

#### Likely canonical mapping

| Canonical table | Mapping notes |
|---|---|
| `securities_master` | Use `code` as symbol candidate, `name` as company/security name, `shortName`, `organCode`, `tax`, sector fields, and flags. |
| `exchange_listings` | Use `floor` as exchange/listing venue candidate; verify whether `STOP` is a venue, status, or special category before canonical mapping. |
| `symbol_universe` | Use row-level `code`, `floor`, `name`, `shortName`, `comTypeCode`, `isIndex`, and `isBank` for normalized universe membership. |
| `instrument_universe` | Use `comTypeCode`, `isIndex`, `index`, `bank`, and sector objects to classify stocks, banks, indexes, and other instrument classes where possible. |

---

#### Readiness decision

- Ready for a dedicated mapping review and parser dry-run planning.
- Not yet DB/backtest-ready.
- Before parser implementation, confirm exact meanings for `floor`, `comTypeCode`, `inCu`, `isIndex`, `bank`, `index`, and nested `icbLv*` sector objects.
- Compare the parsed Vietcap IQ universe against HOSE's 403-symbol exchange universe after a parser dry run.
- Preserve raw payloads and terms/access notes; do not use local browser headers, cookies, or tokens in committed config or docs.

---

</details>

### Universe Parser Dry-Run Result

<details open>
<summary>The saved search-bar payload parses into four local dry-run universe tables.</summary>

---

#### Dry-run inputs and outputs

| Item | Value |
|---|---|
| input raw path | `data/raw/source_probe/source=vietcap_iq/run_id=20260604T081901Z/vietcap_iq_company_search_bar/payload.json` |
| input metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260604T081901Z/vietcap_iq_company_search_bar/metadata.json` |
| output directory | `data/processed/dry_run/vietcap_iq_universe/20260604T101513Z/` |
| output files | `securities_master.csv`, `exchange_listings.csv`, `symbol_universe.csv`, `instrument_universe.csv`, `index_universe.csv`, `validation_report.md`, `validation_summary.json` |

---

#### Counts

| Metric | Count |
|---|---:|
| JSON rows | 2080 |
| Unique symbols | 2078 |
| Securities master rows | 2080 |
| Exchange listing rows | 2080 |
| Symbol universe rows | 2080 |
| Instrument universe rows | 2080 |
| Index universe rows | 34 |
| Quality pass rows | 1598 |
| Quality warn rows | 480 |
| Quality fail rows | 2 |

Floor counts:

| Floor | Count |
|---|---:|
| `HNX` | 310 |
| `HOSE` | 454 |
| `OTC` | 294 |
| `OTHER` | 152 |
| `STOP` | 2 |
| `UPCOM` | 868 |

Quality notes:

- The two fail rows are duplicate `VVDIF + OTHER` rows.
- Warning rows mainly preserve `OTC`, `OTHER`, `STOP`, and index candidates instead of dropping them.
- `STOP` is treated as a status/special-category candidate until source semantics are confirmed.

---

#### HOSE overlap

| Metric | Count |
|---|---:|
| Vietcap unique symbols | 2078 |
| HOSE listed-universe symbols | 403 |
| Overlap count | 403 |
| HOSE symbols missing from Vietcap | 0 |
| Vietcap symbols not in HOSE | 1675 |

This confirms that the verified Vietcap IQ search-bar payload covers all current HOSE listed-stock symbols from the local HOSE dry run, while also containing a much broader universe. It is consistent with the mentor direction to use Vietcap IQ as the main full-market universe candidate and keep HOSE as HOSE-specific market data.

---

#### Readiness decision

- Ready for review as a broad full-market universe parser dry run.
- Ready for a mapping review of `floor`, `comTypeCode`, `isIndex`, `bank`, `index`, and nested `icbLv*` sector fields.
- Not DB/backtest-ready.
- Do not treat the broad universe as final tradable assets; fetch broadly first, then apply dynamic liquidity and data-completeness filters later.

---

</details>

### Mentor Feedback: Fetch Universe Versus Tradable Assets

<details open>
<summary>The Vietcap IQ universe should drive broad fetching, not define the final tradable asset list.</summary>

---

#### Updated interpretation

- Vietcap IQ's broad universe is for fetchers to collect enough market, fundamental, and instrument data.
- The 1598 listed-market candidate rows are not final tradable assets.
- Final tradable assets should be selected later by dynamic filters, especially liquidity, data completeness, exchange eligibility, and strategy-specific constraints.
- Index rows must be separated into their own output/table. The parser now writes `index_universe.csv` with 34 index candidates.
- OHLCV tradable universe selection should be dynamic and can change over time.
- Fundamental data should be fetched as broadly and completely as possible before filtering.
- Ingestion should re-fetch/re-ingest daily where practical, because historical market data can be restated after dividends, splits, or adjustments.
- QuestDB dedup can tolerate repeated ingestion if primary/dedup keys are designed correctly.
- This remains pre-DB and pre-backtest work.

---

</details>

### Field Semantics Review

<details open>
<summary>The current listed-market fetch rule looks reasonable, but key field meanings still need mentor/source confirmation.</summary>

---

#### Field distribution summary

| Field | Observed distribution |
|---|---|
| `exchange_or_floor` / `floor` | `HOSE=454`, `HNX=310`, `UPCOM=868`, `OTC=294`, `OTHER=152`, `STOP=2` |
| `company_type_code` / `comTypeCode` | `CT=1778`, `QU=181`, `CK=43`, `UNKNOWN=34`, `NH=30`, `BH=14` |
| `is_index` / `isIndex` | `false=2046`, `true=34` |
| `is_bank` / `isBank` | `false=2052`, `true=28` |
| `bank_raw` | Boolean-like: `false=2052`, `true=28` |
| `index_raw` | Boolean-like: `false=2046`, `true=34` |
| `icb_lv1_raw` / `icb_lv2_raw` | Available on 1931 rows; missing on 149 rows |
| `icb_lv3_raw` / `icb_lv4_raw` | Available on 1931 rows; missing on 149 rows |
| `quality_status` | `pass=1598`, `warn=480`, `fail=2` |

Quality reasons:

| Reason | Count | Interpretation |
|---|---:|---|
| `warning_non_listed_or_special_floor_candidate` | 448 | `OTC`, `OTHER`, and `STOP` rows are preserved but excluded from the first listed-market fetch candidate set. |
| `warning_stop_floor_status_candidate` | 2 | `STOP` looks like a special status/category, not a normal exchange. |
| `warning_non_stock_index_candidate` | 34 | Index rows are preserved but excluded from the stock universe. |
| `duplicate_symbol_exchange_or_floor` | 2 | Duplicate `VVDIF + OTHER` rows fail parser quality and are excluded. |

---

#### Excluded listed-floor rows

The filter excludes 34 rows from otherwise listed floors because they are index candidates:

| Floor | Excluded rows | Reason |
|---|---:|---|
| `HOSE` | 26 | `excluded_index_candidate` |
| `HNX` | 7 | `excluded_index_candidate` |
| `UPCOM` | 1 | `excluded_index_candidate` |

The two quality-fail rows are duplicate `VVDIF + OTHER`, not HOSE/HNX/UPCOM listed-market fetch candidates.

---

#### Current recommended MVP fetch-universe rule

For the first MVP listed-market fetch universe dry run:

- Include rows where `floor` is `HOSE`, `HNX`, or `UPCOM`.
- Exclude rows where `floor` is `OTC`, `OTHER`, or `STOP`.
- Exclude rows where `isIndex` or `index` indicates an index candidate.
- Exclude rows with `quality_status=fail`.
- Preserve every excluded row in audit output; do not silently drop anything.

This rule is still a dry-run fetch-universe rule, not a final database/backtest rule. It remains valid for review because it produces 1598 listed-market fetch candidates, while preserving special floors, index rows, and quality-fail rows for audit. A later liquidity/data-completeness layer may reduce the final tradable asset list substantially.

---

#### Mentor questions

- `floor` có phải sàn giao dịch/listing venue không?
- `comTypeCode` có ý nghĩa cụ thể như thế nào?
- `isIndex`/`index` có đủ để loại index khỏi universe cổ phiếu không?
- `OTC`/`OTHER`/`STOP` có nên loại khỏi MVP không?
- Có cần giữ `bank` flag để phân nhóm sector/risk không?

---

</details>

### Listed-Market Fetch Universe Filter Dry-Run Result

<details open>
<summary>The first MVP fetch-universe candidate keeps listed floors and quarantines special/index/fail rows.</summary>

---

#### Inputs and outputs

| Item | Value |
|---|---|
| input dry-run directory | `data/processed/dry_run/vietcap_iq_universe/20260604T085258Z/` |
| output directory | `data/processed/dry_run/vietcap_iq_universe/20260604T101513Z/tradable_universe/` |
| output files | `securities_master_tradable.csv`, `exchange_listings_tradable.csv`, `symbol_universe_tradable.csv`, `instrument_universe_tradable.csv`, `excluded_universe_rows.csv`, `tradable_universe_summary.json`, `tradable_universe_report.md` |

---

#### Filter result

| Metric | Count |
|---|---:|
| Full rows | 2080 |
| Full unique symbols | 2078 |
| Listed-market fetch candidate rows | 1598 |
| Listed-market fetch candidate unique symbols | 1598 |
| Excluded rows | 482 |
| Excluded unique symbols | 481 |
| Duplicate symbol + floor after filter | 0 |
| Run status | `warn` |

Included floors:

| Floor | Count |
|---|---:|
| `HNX` | 303 |
| `HOSE` | 428 |
| `UPCOM` | 867 |

Excluded floors:

| Floor | Count |
|---|---:|
| `HNX` | 7 |
| `HOSE` | 26 |
| `OTC` | 294 |
| `OTHER` | 152 |
| `STOP` | 2 |
| `UPCOM` | 1 |

Exclusion reasons:

| Reason | Count |
|---|---:|
| `excluded_non_tradable_floor` | 448 |
| `excluded_index_candidate` | 34 |
| `excluded_quality_fail` | 2 |

The raw `HOSE + HNX + UPCOM` floor count is 1632, which matches the mentor expectation of around 1600 listed-market symbols. The listed-market fetch candidate subset is 1598 because 34 index candidates are separated into `index_universe.csv` and quarantined from stock fetching. `OTC`, `OTHER`, `STOP`, and duplicate/fail rows are preserved in `excluded_universe_rows.csv` for audit instead of being silently dropped.

---

#### Readiness decision

- Ready for review as an MVP listed-market fetch-universe candidate.
- Not DB/backtest-ready until `floor`, `comTypeCode`, `isIndex`, and trading eligibility semantics are confirmed.
- The filter should remain a dry-run fetch layer until mentor/source review approves which floors and instrument classes can proceed into dynamic tradable-asset selection.

---

</details>

### Canonical Mapping Target

<details open>
<summary>The first Vietcap IQ probe should establish full-market instrument coverage and field shape.</summary>

---

#### Candidate canonical tables

| Canonical table | Vietcap IQ role | Fields to discover |
|---|---|---|
| `securities_master` | one row per security/instrument | symbol, exchange, company name, short name, ISIN, instrument type, industry, status |
| `exchange_listings` | listing-level metadata | symbol, exchange, listed status, listed date, security type |
| `symbol_universe` | normalized broad/fetch universe | symbol, exchange, display name, active flag, instrument category |
| `instrument_universe` | broader instrument set | stocks, bonds, ETFs, funds, covered warrants, indexes if present |

---

#### Discovery rules

- Do not assume all returned rows are ordinary stocks.
- Preserve the raw payload and metadata before any normalization.
- Record row count, observed fields, and instrument categories if present.
- Compare Vietcap IQ universe size against mentor guidance of around 1600 symbols.
- Compare overlap with HOSE's 403 listed-stock symbols after a verified payload exists.
- Do not use browser cookies, tokens, or local-only headers in committed config or docs.

---

</details>

### Reports And Evidence

<details open>
<summary>Vietcap IQ reports remain useful, but they are secondary to universe discovery for the next step.</summary>

---

#### Supporting data categories

| Category | Example | Later agent use |
|---|---|---|
| company report | ticker update report | FA thesis and valuation context. |
| industry report | banking, real estate, technology | sector regime and peer comparison. |
| market report | VN-Index daily or monthly wrap | market context and breadth narrative. |
| macro report | rates, FX, liquidity, policy | macro regime input. |
| recommendation fields | rating, target price, upside | evidence input, not automatic trade decision. |

---

#### Evidence safeguards

- Backtests must not use report content before `published_at`.
- Analyst text should be cited as opinion, not observed market fact.
- Report/document retrieval needs access and terms review before parser planning.

---

</details>
