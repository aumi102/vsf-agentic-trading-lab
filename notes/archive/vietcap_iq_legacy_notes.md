---
title: 01_vietcap_iq_legacy_notes
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ — Historical Probe Logs and Notes

> **Archival document.** Full historical probe logs, field semantics, URL inventory, and investigation records from source discovery. Compact entry point: `docs/data_sources/01_vietcap_iq.md`.

---

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

### OHLCV Price-Chart Candidate

<details open>
<summary>The price-chart endpoint is browser-observed and needs small-symbol probe verification before parser planning.</summary>

---

#### Candidate endpoint pattern

`https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{symbol}/price-chart?lengthReport=3&toCurrent=true`

Current status:

- Browser-observed candidate only.
- Not yet verified for stock OHLCV row shape.
- Do not run over the full 1598-symbol listed-market fetch universe.
- Probe only a few explicit symbols first, such as `FPT`, `VNM`, and `VCB`.
- The current source-probe target config does not support `{symbol}` URL templating; add explicit local-only targets for each test symbol.
- Do not promote this endpoint to parser or fetcher work until row-level OHLCV payload fields are verified.

Fields to inspect in the raw payload:

- Date or timestamp field.
- Open, high, low, close fields.
- Volume field.
- Adjusted and unadjusted values, if both are present.
- Corporate-action or adjustment-related fields.
- History coverage controlled by `lengthReport=3` and `toCurrent=true`.

Likely canonical mapping after verification:

| Candidate table | Notes |
|---|---|
| `daily_price_bars` | Use only if daily OHLCV rows are present. |
| `ohlcv_bars` | Candidate generic bar table if interval metadata is available. |
| `market_observations` | Use only if the payload is chart/market observation data rather than canonical bars. |

Manual local-target approach:

- Keep committed example config to one non-secret `FPT` target.
- In `config/source_probe_targets.local.json`, duplicate the target for `VNM` and `VCB` if local headers are required.
- Keep browser-derived headers, cookies, and tokens local-only.
- Run source probe with `--sources vietcap_iq --symbols FPT,VNM,VCB`, but understand that configured URLs are explicit targets, not symbol-templated requests.

---

</details>

### Gap-Chart OHLCV Candidate

<details open>
<summary>The Vietcap Trading gap-chart endpoint is the next small-symbol OHLCV candidate to probe.</summary>

---

#### Candidate endpoint

`https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart`

Observed request pattern:

| Field | Value |
|---|---|
| method | `POST` |
| body field | `symbols`, for example `["FPT"]` |
| body field | `timeFrame`, for example `ONE_DAY` |
| body field | `countBack`, for example `250` |
| body field | `to`, epoch-like request timestamp |

This endpoint is more promising than the IQ `price-chart` endpoint because the browser request is explicitly named `OHLCChart` and uses chart parameters that may return richer bar data. It is still only a browser-observed candidate until raw payload fields are verified.

Initial probe scope:

- Probe only explicit small symbols first: `FPT`, `VNM`, and `VCB`.
- Use unique dataset names so raw payloads are preserved separately:
  - `vietcap_iq_gap_chart_fpt`
  - `vietcap_iq_gap_chart_vnm`
  - `vietcap_iq_gap_chart_vcb`
- Start without cookies in committed/example config.
- If the endpoint returns `403` or a rejected response, use local-only browser-derived headers/cookies as needed, but never commit or print cookies, tokens, or local secrets.
- Do not fetch the full 1598-symbol listed-market fetch universe from this endpoint yet.

Fields to inspect before parser planning:

- Date or timestamp.
- Open, high, low, close.
- Volume.
- Trading value.
- Adjusted and unadjusted values.
- Dividend, split, corporate-action, or adjustment-related fields.
- History coverage and whether `countBack` can support full-history re-fetch.

Readiness rule:

- If the response has row-level OHLCV plus enough price-basis or adjustment context, proceed to a mapping review.
- If it only has OHLC or chart-only fields, continue DevTools discovery.
- No parser, fetcher, database migration, or backtest should be implemented from this endpoint until the small-symbol payload is reviewed.

---

</details>

### Gap-Chart Small-Symbol Probe Result

<details open>
<summary>The gap-chart probe returns aligned OHLCV/value arrays for FPT, VNM, and VCB.</summary>

---

#### Probe evidence

| Item | Value |
|---|---|
| run_id | `20260605T045715Z` |
| symbols probed | `FPT`, `VNM`, `VCB` |
| command scope | Small-symbol probe only; no full 1598-symbol fetch. |
| raw directory | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/` |
| report | `reports/source_probe_report.md` |

Per-symbol evidence:

| Symbol | Target | Status | Raw path | Metadata path | Top-level rows | Bar count | Coverage from `t` |
|---|---|---|---|---|---:|---:|---|
| `FPT` | `vietcap_iq_gap_chart_fpt_candidate` | verified | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_fpt/payload.json` | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_fpt/metadata.json` | 1 | 250 | `2025-06-05` to `2026-06-05` |
| `VNM` | `vietcap_iq_gap_chart_vnm_candidate` | verified | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_vnm/payload.json` | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_vnm/metadata.json` | 1 | 250 | `2025-06-05` to `2026-06-05` |
| `VCB` | `vietcap_iq_gap_chart_vcb_candidate` | verified | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_vcb/payload.json` | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_vcb/metadata.json` | 1 | 250 | `2025-06-05` to `2026-06-05` |

--- 

#### Observed payload shape

The payload is a top-level JSON array. For each probed symbol, the array contains one object with aligned arrays:

- `symbol`
- `o`
- `h`
- `l`
- `c`
- `v`
- `t`
- `accumulatedVolume`
- `accumulatedValue`
- `minBatchTruncTime`

Observed field interpretation:

| Requirement | Observed? | Notes |
|---|---|---|
| date/time | yes | `t` is an array of epoch-second strings; `minBatchTruncTime` is also present. |
| open/high/low/close | yes | `o`, `h`, `l`, `c` arrays. |
| volume | yes | `v` and `accumulatedVolume` arrays. |
| trading value | yes | `accumulatedValue` array. |
| adjusted and unadjusted values | no | No separate adjusted/unadjusted fields are visible. |
| corporate-action or adjustment fields | no | No dividend, split, adjustment factor, or corporate-action fields are visible. |
| consistent shape across FPT/VNM/VCB | yes | Same top-level array shape, same object fields, same 250-bar count, and same date coverage. |

Null/empty-value review:

- No null or empty values were observed in the important aligned arrays for `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, or `accumulatedValue`.
- Parser planning must still validate that all aligned arrays have equal length before exploding them into one row per bar.

--- 

#### Readiness decision

- The endpoint is sufficient for a dedicated OHLCV mapping review using small-symbol saved payloads.
- It is more useful than the previous IQ `price-chart` endpoint because it includes volume and trading value.
- It is not yet enough for full canonical ingestion or full-universe fetching because adjusted/unadjusted price bases and corporate-action/adjustment fields are not visible.
- Next mapping review should define how to explode aligned arrays into row-level bars and how to label the visible price basis, likely `source_reported` until adjustment semantics are confirmed.
- Do not fetch the full 1598-symbol universe yet.
- Do not implement a parser, fetcher, database migration, or backtest yet.

---

</details>

### Gap-Chart OHLCV Mapping Review

<details open>
<summary>The verified gap-chart payload can be mapped into row-level daily OHLCV bars by exploding aligned arrays.</summary>

---

#### Source payload shape

- The top-level JSON payload is an array.
- Each top-level object represents one requested symbol.
- The object contains aligned arrays: `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, and `accumulatedValue`.
- Each array index becomes one daily bar row.
- The verified FPT, VNM, and VCB samples each contain one symbol object and 250 aligned bars from `2025-06-05` to `2026-06-05`.

Row explosion rule:

```text
for each symbol object:
  for i in range(len(t)):
    create one daily bar from o[i], h[i], l[i], c[i], v[i], t[i], accumulatedVolume[i], accumulatedValue[i]
```

--- 

#### Canonical field mapping

| Source field | Canonical field | Notes |
|---|---|---|
| `symbol` | `symbol` | Strip and uppercase. |
| `t[i]` | `bar_ts` | Parse as epoch seconds. |
| `t[i]` converted to date | `trading_date` | Use a documented timezone conversion; current samples align to UTC dates. |
| `o[i]` | `open_price` | Source-reported price basis. |
| `h[i]` | `high_price` | Source-reported price basis. |
| `l[i]` | `low_price` | Source-reported price basis. |
| `c[i]` | `close_price` | Source-reported price basis. |
| `v[i]` | `volume_candidate` | Appears to match `accumulatedVolume[i]` in the small-symbol samples; confirm semantics before DB use. |
| `accumulatedVolume[i]` | `accumulated_volume_candidate` | Candidate daily volume field. |
| `accumulatedValue[i]` | `trading_value_candidate` | Candidate daily trading value field; unit still needs confirmation. |
| request `timeFrame` | `bar_interval` | `ONE_DAY` for the verified small-symbol probes. |
| inferred constant | `price_basis` | Use `source_reported` until adjusted/unadjusted semantics are confirmed. |
| inferred constant | `adjustment_type` | Use `unknown` or `source_reported` until source adjustment semantics are confirmed. |
| raw metadata | lineage fields | Include `source_name`, `source_payload_id`, `raw_content_hash`, `parser_version`, and `schema_version`. |

--- 

#### Validation gates

- All aligned arrays must have equal length before row explosion.
- Required arrays: `t`, `o`, `h`, `l`, and `c`.
- `v`, `accumulatedVolume`, and `accumulatedValue` are strongly preferred for OHLCV and should be present for this endpoint to remain useful.
- `t` must parse as epoch seconds.
- `high_price >= low_price` when both are present.
- `open_price` and `close_price` should be within `high_price` and `low_price` when values are present.
- Duplicate `symbol + bar_ts + price_basis + bar_interval` should fail.
- Zero, empty, and null handling must be explicit; do not silently convert missing values to zero.
- `countBack=250` gives recent history only, not full-history re-fetch.
- Full-history support still needs `countBack`, pagination, or window-parameter exploration.

--- 

#### Known limitations

- Adjusted and unadjusted price values are not separated in the observed payload.
- Dividend, split, corporate-action, and adjustment-factor fields are not visible.
- `accumulatedValue` unit is not confirmed.
- Timezone conversion from `t` to `trading_date` must be fixed before parser output is promoted.
- The verified payload is enough for a small-symbol OHLCV mapping review, but not enough for a full 1598-symbol fetch, database migration, or backtest.

Next decision:

- If this mapping is accepted, the next safe implementation step is a small-symbol parser dry run using only the saved FPT, VNM, and VCB payloads.
- Parser output should remain local dry-run CSV/report artifacts until adjustment semantics, full-history behavior, and value units are confirmed.

---

</details>

### Gap-Chart Parser Dry-Run Result

<details open>
<summary>The saved FPT, VNM, and VCB gap-chart payloads parse into local daily price bars with limited-history warnings only.</summary>

---

#### Inputs and outputs

| Item | Value |
|---|---|
| input run_id | `20260605T045715Z` |
| input raw paths | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_fpt/payload.json`; `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_vnm/payload.json`; `data/raw/source_probe/source=vietcap_iq/run_id=20260605T045715Z/vietcap_iq_gap_chart_vcb/payload.json` |
| output directory | `data/processed/dry_run/vietcap_iq_gap_chart/20260605T080850Z/` |
| output files | `daily_price_bars.csv`, `validation_report.md`, `validation_summary.json` |

---

#### Coverage and quality

| Symbol | Bars | Coverage | Quality pass | Quality warn | Quality fail |
|---|---:|---|---:|---:|---:|
| `FPT` | 250 | `2025-06-05` to `2026-06-05` | 0 | 250 | 0 |
| `VNM` | 250 | `2025-06-05` to `2026-06-05` | 0 | 250 | 0 |
| `VCB` | 250 | `2025-06-05` to `2026-06-05` | 0 | 250 | 0 |

Totals:

| Metric | Count |
|---|---:|
| Parsed symbols | 3 |
| Daily price bars | 750 |
| Quality pass rows | 0 |
| Quality warn rows | 750 |
| Quality fail rows | 0 |

Quality note:

- All rows are warnings because `countBack=250` is recorded as limited recent history, not full history.
- No duplicate bar keys or OHLC range failures were observed in the saved small-symbol payloads.

Known limitations:

- No adjusted/unadjusted price split is visible in the payload.
- No dividend, split, corporate-action, or adjustment-factor fields are visible.
- `countBack=250` covers only recent history.
- No full-universe fetch was performed.
- No database migration, database write, or backtest was performed.

Readiness decision:

- Ready for review as a small-symbol parser dry run over saved gap-chart payloads only.
- Not ready for full-universe fetch, canonical database ingestion, or backtesting.

---

</details>

### Gap-Chart Full-History Exploration Plan

<details open>
<summary>Next probe should test whether larger FPT gap-chart windows can return more than the current 250 recent bars.</summary>

---

Current parser status:

- The saved-payload gap-chart parser dry run currently uses the verified `countBack=250` FPT, VNM, and VCB payloads only.
- Each current small-symbol payload contains 250 daily bars covering `2025-06-05` to `2026-06-05`.
- All parsed rows warn because `countBack=250` is limited recent history, not full available OHLCV history.

Mentor direction:

- OHLCV ingestion should target full available history when practical.
- Full-history feasibility is still an endpoint capability question, not a parser, database, or backtest task.

Next safe probe sequence:

| Step | Symbol scope | countBack | Decision rule |
|---|---|---:|---|
| 1 | `FPT` only | 500 | Confirm access, row count above 250 if available, coverage, payload size, and stable shape. |
| 2 | `FPT` only | 1000 | Run only if 500 works without access or shape regression. |
| 3 | `FPT` only | 2000 | Run only if 1000 works and payload size remains manageable. |
| 4 | `FPT` only | 5000 | Run only if 2000 works and the endpoint appears stable. |

Inspect for each probe:

- Access status and HTTP/content-type stability.
- Top-level payload shape and aligned-array field consistency.
- Row count returned versus requested `countBack`.
- Coverage start/end dates from `t`.
- Raw payload byte size.
- Whether volume, accumulated volume, and accumulated value remain present.
- Whether any adjusted/unadjusted or corporate-action fields appear.

CountBack=500 result:

| Item | Value |
|---|---|
| run_id | `20260605T084151Z` |
| target | `vietcap_iq_gap_chart_fpt_countback_500_candidate` |
| dataset | `vietcap_iq_gap_chart_fpt_countback_500` |
| status | verified usable JSON, HTTP `200`, content type `application/json; charset=utf-8` |
| raw path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T084151Z/vietcap_iq_gap_chart_fpt_countback_500/payload.json` |
| metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T084151Z/vietcap_iq_gap_chart_fpt_countback_500/metadata.json` |
| raw payload size | 37,821 bytes |
| top-level shape | JSON array with 1 object for `FPT` |
| rows returned | 500 aligned daily bars |
| coverage from `t` | `2024-06-04` to `2026-06-05` |
| fields | `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, `minBatchTruncTime` |
| null or empty values in aligned arrays | 0 observed |
| length mismatches | none observed |
| adjusted/unadjusted fields | none observed |
| dividend/split/corporate-action fields | none observed |

Comparison with countBack=250:

- Row count increased from 250 to 500.
- Coverage expanded earlier than `2025-06-05`, back to `2024-06-04`.
- Payload shape remained stable with the same aligned arrays and no extra adjustment or corporate-action fields.
- Response size remains manageable for a small-symbol probe.
- This is enough evidence to proceed to an FPT-only `countBack=1000` probe.

CountBack=1000 result:

| Item | Value |
|---|---|
| run_id | `20260605T092311Z` |
| target | `vietcap_iq_gap_chart_fpt_countback_1000_candidate` |
| dataset | `vietcap_iq_gap_chart_fpt_countback_1000` |
| status | verified usable JSON, HTTP `200`, content type `application/json; charset=utf-8` |
| raw path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T092311Z/vietcap_iq_gap_chart_fpt_countback_1000/payload.json` |
| metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T092311Z/vietcap_iq_gap_chart_fpt_countback_1000/metadata.json` |
| raw payload size | 72,147 bytes |
| top-level shape | JSON array with 1 object for `FPT` |
| rows returned | 1,000 aligned daily bars |
| coverage from `t` | `2022-06-02` to `2026-06-05` |
| fields | `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, `minBatchTruncTime` |
| null or empty values in aligned arrays | `accumulatedValue` has 73 null values from `2022-06-02` to `2022-09-14`; `o`, `h`, `l`, `c`, `v`, `t`, and `accumulatedVolume` have 0 observed null or empty values |
| length mismatches | none observed |
| adjusted/unadjusted fields | none observed |
| dividend/split/corporate-action fields | none observed |

Comparison with countBack=250 and countBack=500:

- Row count increased again from 500 to 1,000.
- Coverage expanded earlier than `2024-06-04`, back to `2022-06-02`.
- Payload shape remained stable with the same aligned arrays and no extra adjustment or corporate-action fields.
- Response size remains manageable for a small-symbol probe.
- The 73 older null `accumulatedValue` entries are a data-quality caveat for trading-value completeness, but they are not a shape regression.
- This is enough evidence to proceed to an FPT-only `countBack=2000` probe.

CountBack=2000 result:

| Item | Value |
|---|---|
| run_id | `20260605T093633Z` |
| target | `vietcap_iq_gap_chart_fpt_countback_2000_candidate` |
| dataset | `vietcap_iq_gap_chart_fpt_countback_2000` |
| status | verified usable JSON, HTTP `200`, content type `application/json; charset=utf-8` |
| raw path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T093633Z/vietcap_iq_gap_chart_fpt_countback_2000/payload.json` |
| metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T093633Z/vietcap_iq_gap_chart_fpt_countback_2000/metadata.json` |
| raw payload size | 141,113 bytes |
| top-level shape | JSON array with 1 object for `FPT` |
| rows returned | 2,000 aligned daily bars |
| coverage from `t` | `2018-06-04` to `2026-06-05` |
| fields | `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, `minBatchTruncTime` |
| null or empty values in aligned arrays | `accumulatedValue` has 1,073 null values from `2018-06-04` to `2022-09-14`; `o`, `h`, `l`, `c`, `v`, `t`, and `accumulatedVolume` have 0 observed null or empty values |
| length mismatches | none observed |
| adjusted/unadjusted fields | none observed |
| dividend/split/corporate-action fields | none observed |

Comparison with countBack=250, 500, and 1000:

- Row count increased again from 1,000 to 2,000.
- Coverage expanded earlier than `2022-06-02`, back to `2018-06-04`.
- Payload shape remained stable with the same aligned arrays and no extra adjustment or corporate-action fields.
- Response size remains manageable for a single-symbol probe.
- `accumulatedValue` nulls increased from 73 to 1,073 and remain limited to older dates through `2022-09-14`; OHLC, volume, timestamps, and `accumulatedVolume` remain complete in this saved FPT sample.
- This is enough endpoint-capability evidence to proceed to one FPT-only `countBack=5000` probe before repeating large windows for `VNM` or `VCB`.

CountBack=5000 result:

| Item | Value |
|---|---|
| run_id | `20260605T094714Z` |
| target | `vietcap_iq_gap_chart_fpt_countback_5000_candidate` |
| dataset | `vietcap_iq_gap_chart_fpt_countback_5000` |
| status | verified usable JSON, HTTP `200`, content type `application/json; charset=utf-8`; result appears capped by available FPT history |
| raw path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T094714Z/vietcap_iq_gap_chart_fpt_countback_5000/payload.json` |
| metadata path | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T094714Z/vietcap_iq_gap_chart_fpt_countback_5000/metadata.json` |
| raw payload size | 323,966 bytes |
| top-level shape | JSON array with 1 object for `FPT` |
| rows returned | 4,852 aligned daily bars, below requested `countBack=5000` |
| coverage from `t` | `2006-12-13` to `2026-06-05` |
| fields | `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, `minBatchTruncTime` |
| null or empty values in aligned arrays | `accumulatedValue` has 3,925 null values from `2006-12-13` to `2022-09-14`; `o`, `h`, `l`, `c`, `v`, `t`, and `accumulatedVolume` have 0 observed null or empty values |
| length mismatches | none observed |
| adjusted/unadjusted fields | none observed |
| dividend/split/corporate-action fields | none observed |

Comparison with countBack=250, 500, 1000, and 2000:

- Row count increased again from 2,000 to 4,852, but did not reach the requested 5,000 rows.
- Coverage expanded earlier than `2018-06-04`, back to `2006-12-13`.
- The response appears capped by available FPT history rather than by the requested count.
- Payload shape remained stable with the same aligned arrays and no extra adjustment or corporate-action fields.
- Response size remains manageable for a single-symbol probe.
- `accumulatedValue` nulls increased from 1,073 to 3,925 and remain limited to older dates through `2022-09-14`; OHLC, volume, timestamps, and `accumulatedVolume` remain complete in this saved FPT sample.
- FPT full-history exploration can stop here. Next safe step is to repeat `countBack=5000` for `VNM` and `VCB` only, then compare coverage, caps, and value completeness across the three small symbols.

VNM and VCB countBack=5000 result:

| Symbol | Run ID | Status | Rows returned | Coverage from `t` | Raw payload size | Cap / available-history decision | `accumulatedValue` nulls |
|---|---|---|---:|---|---:|---|---|
| `FPT` | `20260605T094714Z` | verified usable JSON | 4,852 | `2006-12-13` to `2026-06-05` | 323,966 bytes | Below requested 5,000; appears capped by available FPT history. | 3,925 nulls from `2006-12-13` to `2022-09-14` |
| `VNM` | `20260605T095611Z` | verified usable JSON | 5,000 | `2006-05-18` to `2026-06-05` | 332,755 bytes | Returned requested 5,000 rows; no cap observed at this request size. | 4,073 nulls from `2006-05-18` to `2022-09-14` |
| `VCB` | `20260605T095611Z` | verified usable JSON | 4,227 | `2009-06-30` to `2026-06-05` | 282,980 bytes | Below requested 5,000; appears capped by available VCB history. | 3,300 nulls from `2009-06-30` to `2022-09-14` |

Cross-symbol conclusion:

- VNM and VCB preserved the same top-level JSON array shape and the same fields as FPT: `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, and `minBatchTruncTime`.
- No aligned-array length mismatches were observed for FPT, VNM, or VCB at `countBack=5000`.
- No adjusted/unadjusted price split, dividend, split, or corporate-action fields were observed for any of the three.
- OHLC, `v`, `t`, and `accumulatedVolume` are complete across all three saved `countBack=5000` payloads.
- `accumulatedValue` has substantial older null coverage for all three symbols, ending consistently on `2022-09-14`; treat trading-value completeness before `2022-09-15` as an open quality caveat.
- Response sizes remain manageable for small-symbol saved-payload work.
- Next safe implementation step is a limited full-history parser dry run over the saved FPT, VNM, and VCB `countBack=5000` payloads, with no full-universe fetch, database migration, database write, or backtest.

Escalation rule:

- FPT, VNM, and VCB are enough for this full-history exploration stage; do not probe additional symbols yet.
- Do not run this over the full 1598-symbol listed-market universe.
- Do not implement a production fetcher from this exploration.
- Do not perform database migrations, database writes, or backtests.

---

</details>

### Full-History Parser Dry-Run Failure Review

<details open>
<summary>The saved countBack=5000 parser dry run is usable, with eight OHLC data-quality failures kept quarantined.</summary>

---

#### Dry-run result

| Item | Value |
|---|---|
| output directory | `data/processed/dry_run/vietcap_iq_gap_chart/20260605T100326Z/` |
| daily price bars | `data/processed/dry_run/vietcap_iq_gap_chart/20260605T100326Z/daily_price_bars.csv` |
| validation report | `data/processed/dry_run/vietcap_iq_gap_chart/20260605T100326Z/validation_report.md` |
| validation summary | `data/processed/dry_run/vietcap_iq_gap_chart/20260605T100326Z/validation_summary.json` |
| total rows | 14,079 |
| quality pass rows | 2,781 |
| quality warn rows | 11,290 |
| quality fail rows | 8 |

Coverage and quality by symbol:

| Symbol | Rows | Coverage | Pass | Warn | Fail |
|---|---:|---|---:|---:|---:|
| `FPT` | 4,852 | `2006-12-13` to `2026-06-05` | 927 | 3,922 | 3 |
| `VNM` | 5,000 | `2006-05-18` to `2026-06-05` | 927 | 4,068 | 5 |
| `VCB` | 4,227 | `2009-06-30` to `2026-06-05` | 927 | 3,300 | 0 |

Failure reason counts:

| Reason | Count | Policy decision |
|---|---:|---|
| `close_price_outside_high_low` | 6 | Keep as fail. Raw source values have close outside the high/low range. |
| `open_price_outside_high_low` | 2 | Keep as fail. Raw source values have open outside the high/low range. |

Failed-row scope:

| Symbol | Failed rows | Failed date range |
|---|---:|---|
| `FPT` | 3 | `2007-08-17` to `2009-12-07` |
| `VNM` | 5 | `2006-06-14` to `2009-06-11` |
| `VCB` | 0 | none |

Review conclusion:

- The eight failed rows are source data-quality failures, not a parser bug.
- No failed rows are caused by `high_price < low_price`, invalid timestamps, duplicate bar keys, missing required OHLC/timestamp fields, or required numeric conversion errors.
- All eight failed rows also have missing `accumulatedValue`, but missing `trading_value` remains warning-only as intended for older history.
- Do not silently downgrade these OHLC inconsistencies without source evidence; keep them quarantined as `quality_status=fail`.
- The dry run is usable for review, but parser output is still pre-DB and pre-backtest.
- No full-universe fetch, database migration, database write, production fetcher, or backtest should proceed from this result yet.

---

</details>

### Gap-Chart OHLCV Ingestion Readiness Closeout

<details open>
<summary>The gap-chart endpoint is ready for safe fetcher planning, but not full-universe ingestion, DB writes, or backtesting.</summary>

---

#### Proven

- Small-symbol endpoint reachability is verified for FPT, VNM, and VCB.
- `countBack=5000` can approximate full available history for the tested symbols:
  - FPT: 4,852 bars, `2006-12-13` to `2026-06-05`.
  - VNM: 5,000 bars, `2006-05-18` to `2026-06-05`.
  - VCB: 4,227 bars, `2009-06-30` to `2026-06-05`.
- Payload shape is stable across FPT/VNM/VCB: `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, `minBatchTruncTime`.
- The saved-payload parser dry run works on full-history samples and writes local CSV/report/summary outputs.
- Quality gates separate pass, warn, and fail rows.
- Source OHLC inconsistencies are quarantined as fail rows, not treated as parser bugs.

#### Not Proven

- Full 1,598-symbol fetch safety.
- Rate-limit, retry, access, and response-stability behavior at scale.
- Adjusted versus unadjusted price semantics.
- Dividend, split, or other corporate-action fields.
- QuestDB table, migration, or upsert behavior.
- Backtest readiness.

#### Data-Quality Policy

- OHLC, timestamp, and volume are required for usable bars.
- Missing `accumulatedValue` / `trading_value` in older history is warning-only.
- OHLC range inconsistency remains fail.
- Failed rows must stay quarantined and visible in reports; do not silently drop or downgrade them.

#### Next Implementation Steps

1. Build a safe gap-chart fetcher in dry-run/controlled mode only.
2. Fetch only a very small controlled batch first, not the full universe.
3. Use sector-batched ordering from `scripts/build_ohlcv_fetch_plan_dry_run.py`.
4. Add checkpoint/resume state before broader runs.
5. Add random sleep and avoid aggressive async/high concurrency.
6. Save raw payloads and metadata before parsing.
7. Parse to local dry-run CSV/report/summary only.
8. Do not write DB, implement migrations, run backtests, or fetch the full universe yet.

Readiness decision:

- Ready for safe fetcher planning and a tiny controlled dry-run fetch design.
- Not ready for full-universe ingestion, canonical DB ingestion, or backtesting.

---

</details>

### Controlled Gap-Chart Fetcher Plan

<details open>
<summary>The controlled fetcher skeleton is intended for tiny, sequential raw-fetch dry runs only.</summary>

---

- Script: `scripts/fetch_vietcap_iq_gap_chart_controlled.py`.
- Default behavior is plan-only: it writes `fetch_plan.json` and `fetch_plan_report.md` and makes no network requests unless `--execute` is supplied.
- Default symbol scope is the verified tiny batch `FPT,VNM,VCB`; execute mode fails fast if the requested symbol count exceeds `--max-symbols`.
- Request body is one symbol at a time: `symbols`, `timeFrame`, `countBack`, and `to`.
- The script does not read `config/source_probe_targets.local.json` and does not require secrets/cookies for plan-only mode.
- Execute mode is sequential only, with concurrency fixed at one and random sleep between symbol requests.
- Checkpoint/resume uses `fetch_checkpoint.json`; completed symbols are skipped on rerun unless `--force` is supplied.
- Raw payloads are saved before parsing, with one folder per symbol containing `payload.json` and `metadata.json`.
- The fetcher does not parse, write DB tables, run migrations, run backtests, or fetch the full universe.

Safe next step:

1. Run plan-only mode for the tiny verified symbol set and inspect the planned requests.
2. If approved, run one tiny controlled execute pass for `FPT,VNM,VCB` with conservative sleep.
3. Parse only the saved raw payloads into local dry-run CSV/report outputs.
4. Keep full-universe, sector-batched fetching, DB writes, and backtests blocked until controlled-fetch and rate-limit behavior are reviewed.

---

</details>

### Controlled Gap-Chart Tiny Execute Smoke Result

<details open>
<summary>The tiny controlled execute pass succeeded for FPT, VNM, and VCB only.</summary>

---

#### Execute evidence

| Item | Value |
|---|---|
| command | `python scripts/fetch_vietcap_iq_gap_chart_controlled.py --symbols FPT,VNM,VCB --count-back 5000 --to 1780633564 --sleep-min-seconds 2 --sleep-max-seconds 5 --max-symbols 3 --execute` |
| run_id | `20260608T021035Z` |
| mode | `execute` |
| network_requests_made | `True` |
| planned_request_count | `3` |
| completed_symbols | `FPT`, `VCB`, `VNM` |
| failed_symbols | none |
| pending_symbols | none |
| output directory | `data/raw/controlled_fetch/source=vietcap_iq/20260608T021035Z/` |
| checkpoint | `data/raw/controlled_fetch/source=vietcap_iq/20260608T021035Z/fetch_checkpoint.json` |
| fetch plan | `data/raw/controlled_fetch/source=vietcap_iq/20260608T021035Z/fetch_plan.json` |
| fetch plan report | `data/raw/controlled_fetch/source=vietcap_iq/20260608T021035Z/fetch_plan_report.md` |

Per-symbol raw files:

| Symbol | Dataset | Access status | HTTP | Content type | Payload saved | Metadata saved | Metadata byte_size | Payload file size | Rows | Coverage from `t` | `accumulatedValue` nulls |
|---|---|---|---:|---|---|---|---:|---:|---:|---|---:|
| `FPT` | `vietcap_iq_gap_chart_fpt_countback_5000` | `verified` | 200 | `application/json; charset=utf-8` | yes | yes | 323,966 | 634,622 | 4,852 | `2006-12-13` to `2026-06-05` | 3,925 |
| `VNM` | `vietcap_iq_gap_chart_vnm_countback_5000` | `verified` | 200 | `application/json; charset=utf-8` | yes | yes | 332,755 | 652,883 | 5,000 | `2006-05-18` to `2026-06-05` | 4,073 |
| `VCB` | `vietcap_iq_gap_chart_vcb_countback_5000` | `verified` | 200 | `application/json; charset=utf-8` | yes | yes | 282,980 | 553,636 | 4,227 | `2009-06-30` to `2026-06-05` | 3,300 |

Payload shape:

- Top-level type is a JSON array with one object per requested symbol.
- Fields match the previous saved `countBack=5000` payloads: `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, and `minBatchTruncTime`.
- Aligned array lengths match the row counts above for each symbol.
- Row counts and coverage match the previous saved `countBack=5000` expectations exactly.
- `accumulatedValue` is null in older history and remains a warning-only trading-value completeness caveat; OHLC, `v`, `t`, and `accumulatedVolume` remain present.
- Metadata request bodies contain only `symbols`, `timeFrame`, `countBack`, and `to`; no cookie, token, secret, authorization, or password fields were observed in metadata.

Scope guardrails:

- This execute pass fetched only `FPT`, `VNM`, and `VCB`.
- No full-universe fetch was run.
- No database migration, database write, parser-to-DB step, production fetcher, async/concurrency expansion, or backtest was implemented.

Recommendation:

- The next safe step is to parse only these controlled raw payloads into local dry-run CSV/report artifacts, then review rate-limit/access behavior before any broader controlled batch.

---

</details>

### Controlled FPT/VNM/VCB Parser Dry-Run Result

<details open>
<summary>The controlled-fetch FPT, VNM, and VCB raw payloads parse identically to the previous source-probe saved-payload dry run.</summary>

---

#### Dry-run evidence

| Item | Value |
|---|---|
| controlled fetch run_id | `20260608T021035Z` |
| parser dry-run run_id | `20260608T031039Z` |
| parser command | `python scripts/parse_vietcap_iq_gap_chart_dry_run.py --raw-base-dir data/raw/controlled_fetch/source=vietcap_iq --datasets vietcap_iq_gap_chart_fpt_countback_5000,vietcap_iq_gap_chart_vnm_countback_5000,vietcap_iq_gap_chart_vcb_countback_5000` |
| output directory | `data/processed/dry_run/vietcap_iq_gap_chart/20260608T031039Z/` |
| output files | `daily_price_bars.csv`, `validation_report.md`, `validation_summary.json` |
| input datasets | `vietcap_iq_gap_chart_fpt_countback_5000`, `vietcap_iq_gap_chart_vnm_countback_5000`, `vietcap_iq_gap_chart_vcb_countback_5000` |
| total rows | 14,079 |
| quality pass | 2,781 |
| quality warn | 11,290 |
| quality fail | 8 |

Per-symbol parser result:

| Symbol | Rows | Coverage | Pass | Warn | Fail |
|---|---:|---|---:|---:|---:|
| `FPT` | 4,852 | `2006-12-13` to `2026-06-05` | 927 | 3,922 | 3 |
| `VNM` | 5,000 | `2006-05-18` to `2026-06-05` | 927 | 4,068 | 5 |
| `VCB` | 4,227 | `2009-06-30` to `2026-06-05` | 927 | 3,300 | 0 |

Quality reasons:

| Reason | Count | Classification |
|---|---:|---|
| `warning_missing_trading_value` | 11,298 | warning-only; older `accumulatedValue` / trading value missingness |
| `close_price_outside_high_low` | 6 | fail; source OHLC inconsistency, keep quarantined |
| `open_price_outside_high_low` | 2 | fail; source OHLC inconsistency, keep quarantined |

Comparison with previous source-probe saved-payload parse:

- The controlled-fetch parse matches the previous source-probe parser dry run exactly on total rows and quality split: 14,079 rows, 2,781 pass, 11,290 warn, and 8 fail.
- Coverage also matches the expected controlled execute payloads: FPT `2006-12-13` to `2026-06-05`, VNM `2006-05-18` to `2026-06-05`, and VCB `2009-06-30` to `2026-06-05`.
- The 8 fail rows are OHLC range inconsistencies in the saved source data and remain quarantined.
- Missing `accumulatedValue` / trading value remains warning-only and does not fail rows by itself.
- No full-universe fetch, database migration, database write, parser-to-DB step, or backtest was performed.

---

</details>

### Gap-Chart Time Horizon Exploration Plan

<details open>
<summary>Mentor wants daily OHLCV coverage by time horizon, while the current gap-chart fetcher is still countBack-based.</summary>

---

#### Current behavior

- Mentor requirement: daily OHLCV should target the practical Vietnamese market horizon, roughly `2000` to now where source coverage allows.
- Current controlled fetcher request body is countBack-based, not explicit from/to-date-based:
  - `symbols`
  - `timeFrame`
  - `countBack`
  - `to`
- `countBack` means a number of daily bars/trading sessions backward from `to`, not a number of calendar days.
- `countBack=5000` is useful for large-window exploration, but it is not guaranteed to reach `2000` for every symbol.
- Existing code/docs do not show confirmed `gap-chart` support for a true `from`, `fromDate`, `toDate`, `fromTime`, or equivalent time-horizon request body.

#### Why REE and SAM

- REE and SAM are useful early-history probes because they are early listed Vietnamese market symbols.
- If `countBack=10000` with `timeFrame=ONE_DAY` can reach early market history for these symbols, it gives evidence about the endpoint's practical historical horizon without fetching the full universe.
- This remains an empirical endpoint-capability test, not a parser, DB, or backtest step.

#### Proposed next empirical test

Use a tiny controlled plan first:

```text
python scripts/fetch_vietcap_iq_gap_chart_controlled.py --symbols REE,SAM --count-back 10000 --to 1780633564 --sleep-min-seconds 2 --sleep-max-seconds 5 --max-symbols 2
```

Only after review should a tiny controlled execute be considered for `REE,SAM` with the same fixed `to=1780633564`.

#### Plan-only result

| Item | Value |
|---|---|
| run_id | `20260608T024107Z` |
| mode | `plan_only` |
| network_requests_made | `False` |
| planned_request_count | `2` |
| symbols | `REE`, `SAM` |
| output directory | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024107Z/` |
| fetch plan | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024107Z/fetch_plan.json` |
| fetch plan report | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024107Z/fetch_plan_report.md` |

Planned datasets:

| Symbol | Dataset | countBack | to |
|---|---|---:|---:|
| `REE` | `vietcap_iq_gap_chart_ree_countback_10000` | 10000 | 1780633564 |
| `SAM` | `vietcap_iq_gap_chart_sam_countback_10000` | 10000 | 1780633564 |

Plan-only guardrails:

- No network request was made.
- No `payload.json` files were created.
- No symbol `metadata.json` files were created.
- No full-universe fetch, database migration, database write, parser-to-DB step, or backtest was performed.

#### Tiny execute result

| Item | Value |
|---|---|
| command | `python scripts/fetch_vietcap_iq_gap_chart_controlled.py --symbols REE,SAM --count-back 10000 --to 1780633564 --sleep-min-seconds 2 --sleep-max-seconds 5 --max-symbols 2 --execute` |
| run_id | `20260608T024652Z` |
| mode | `execute` |
| network_requests_made | `True` |
| planned_request_count | `2` |
| completed_symbols | `REE`, `SAM` |
| failed_symbols | none |
| pending_symbols | none |
| output directory | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024652Z/` |
| checkpoint | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024652Z/fetch_checkpoint.json` |
| fetch plan | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024652Z/fetch_plan.json` |
| fetch plan report | `data/raw/controlled_fetch/source=vietcap_iq/20260608T024652Z/fetch_plan_report.md` |

Per-symbol result:

| Symbol | Dataset | Access status | HTTP | Content type | Payload saved | Metadata saved | Metadata byte_size | Payload file size | Rows | Coverage from `t` | Reached around 2000? | `accumulatedValue` nulls |
|---|---|---|---:|---|---|---|---:|---:|---:|---|---|---:|
| `REE` | `vietcap_iq_gap_chart_ree_countback_10000` | `verified` | 200 | `application/json; charset=utf-8` | yes | yes | 405,689 | 808,377 | 6,290 | `2000-07-28` to `2026-06-05` | yes | 5,363 |
| `SAM` | `vietcap_iq_gap_chart_sam_countback_10000` | `verified` | 200 | `application/json; charset=utf-8` | yes | yes | 398,785 | 801,473 | 6,290 | `2000-07-28` to `2026-06-05` | yes | 5,363 |

Shape and request safety:

- Payload shape matches previous gap-chart payloads: top-level JSON array with one object and fields `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, `accumulatedValue`, and `minBatchTruncTime`.
- All aligned arrays have length 6,290 for both symbols.
- Metadata request bodies contain only `symbols`, `timeFrame`, `countBack`, and `to`; no cookie, token, secret, authorization, or password fields were observed in metadata.
- `accumulatedValue` has older null coverage and remains a warning-only trading-value completeness caveat.

Time-horizon decision:

- `countBack=10000` reached `2000-07-28` for both REE and SAM, which is close to the practical start of Vietnamese stock-market daily history.
- The endpoint did not return the requested 10,000 rows; both symbols returned 6,290 rows, which looks like an available-history cap rather than a countBack cap for these early listed symbols.
- Large countBack is a workable fallback for approximating `2000`-to-now daily OHLCV on early listed symbols, but it is still not a true from/to horizon contract.
- Continue searching for a true from/to request body before treating this endpoint as a final time-horizon fetch design.
- No full-universe fetch, database migration, database write, parser-to-DB step, production fetcher, async/concurrency expansion, or backtest was performed.

#### Parser dry-run result

| Item | Value |
|---|---|
| controlled fetch run_id | `20260608T024652Z` |
| parser dry-run run_id | `20260608T025853Z` |
| parser command | `python scripts/parse_vietcap_iq_gap_chart_dry_run.py --raw-base-dir data/raw/controlled_fetch/source=vietcap_iq --datasets vietcap_iq_gap_chart_ree_countback_10000,vietcap_iq_gap_chart_sam_countback_10000` |
| output directory | `data/processed/dry_run/vietcap_iq_gap_chart/20260608T025853Z/` |
| output files | `daily_price_bars.csv`, `validation_report.md`, `validation_summary.json` |
| input datasets | `vietcap_iq_gap_chart_ree_countback_10000`, `vietcap_iq_gap_chart_sam_countback_10000` |
| total rows | 12,580 |
| quality pass | 1,854 |
| quality warn | 10,721 |
| quality fail | 5 |

Per-symbol parser result:

| Symbol | Rows | Coverage | Pass | Warn | Fail |
|---|---:|---|---:|---:|---:|
| `REE` | 6,290 | `2000-07-28` to `2026-06-05` | 927 | 5,359 | 4 |
| `SAM` | 6,290 | `2000-07-28` to `2026-06-05` | 927 | 5,362 | 1 |

Quality reasons:

| Reason | Count | Classification |
|---|---:|---|
| `warning_missing_trading_value` | 10,726 | warning-only; older `accumulatedValue` / trading value missingness |
| `close_price_outside_high_low` | 3 | fail; source OHLC inconsistency, keep quarantined |
| `open_price_outside_high_low` | 2 | fail; source OHLC inconsistency, keep quarantined |

Fail-row review:

- `REE`: four OHLC range failures on `2006-06-15`, `2008-01-25`, `2009-06-10`, and `2009-06-11`.
- `SAM`: one OHLC range failure on `2007-08-02`.
- The failed rows are consistent with true source data-quality issues because the saved OHLC values violate high/low constraints; they should remain quarantined.
- Missing `accumulatedValue` is still warning-only and should not be downgraded to fail by itself.

Parser conclusion:

- The controlled REE/SAM raw outputs parse into local dry-run artifacts and preserve the `2000-07-28` to `2026-06-05` horizon.
- This supports `countBack=10000` as the current fallback for approximating the mentor-requested `2000`-to-now daily OHLCV horizon.
- True from/to request support remains preferable if it can be discovered.
- No full-universe fetch, database migration, database write, parser-to-DB step, or backtest was performed.

Recommendation:

- Review the `REE,SAM` execute evidence before any broader controlled batch.
- In parallel, keep DevTools/source discovery open for a true from/to request body; if confirmed, prefer explicit time horizon over countBack approximation.

---

</details>

### Price-Chart Small-Symbol Probe Result

<details open>
<summary>The rerun preserved separate FPT, VNM, and VCB raw payloads; all three are OHLC-only chart JSON, not full OHLCV.</summary>

---

#### Probe evidence

| Item | Value |
|---|---|
| run_id | `20260605T040654Z` |
| symbols probed | `FPT`, `VNM`, `VCB` |
| command scope | Small-symbol probe only; no full 1598-symbol fetch. |
| raw directory | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/` |
| report | `reports/source_probe_report.md` |

The rerun used separate dataset names, so each symbol has its own raw payload and metadata instead of overwriting the previous symbol.

Per-symbol evidence:

| Symbol | Target | Classification | Raw path | Metadata path | Rows | Coverage from `tradingTime` |
|---|---|---|---|---|---:|---|
| `FPT` | `vietcap_iq_company_price_chart_fpt_candidate` | verified OHLC-only chart JSON | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/vietcap_iq_company_price_chart_fpt/payload.json` | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/vietcap_iq_company_price_chart_fpt/metadata.json` | 749 | `2023-06-05` to `2026-06-05` |
| `VNM` | `vietcap_iq_company_price_chart_vnm_candidate` | verified OHLC-only chart JSON | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/vietcap_iq_company_price_chart_vnm/payload.json` | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/vietcap_iq_company_price_chart_vnm/metadata.json` | 749 | `2023-06-05` to `2026-06-05` |
| `VCB` | `vietcap_iq_company_price_chart_vcb_candidate` | verified OHLC-only chart JSON | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/vietcap_iq_company_price_chart_vcb/payload.json` | `data/raw/source_probe/source=vietcap_iq/run_id=20260605T040654Z/vietcap_iq_company_price_chart_vcb/metadata.json` | 749 | `2023-06-05` to `2026-06-05` |

--- 

#### Observed payload shape

All three symbol payloads have the same shape.

| Item | Value |
|---|---|
| content type | `application/json` |
| top-level fields | `serverDateTime`, `traceId`, `status`, `code`, `msg`, `exception`, `successful`, `data` |
| row/container field | `data` |
| observed row fields | `tradingTime`, `openPrice`, `highPrice`, `lowPrice`, `closingPrice` |
| null counts for observed fields | 0 nulls for all five observed row fields in FPT, VNM, and VCB |

Field interpretation across FPT, VNM, and VCB:

| Requirement | Observed? | Notes |
|---|---|---|
| date/time | yes | `tradingTime` appears to be epoch seconds. |
| open/high/low/close | yes | `openPrice`, `highPrice`, `lowPrice`, `closingPrice`. |
| volume | no | No volume or trading-value field observed. |
| adjusted and unadjusted values | no | Only one price basis is exposed; adjusted/unadjusted semantics are not separated. |
| corporate-action or adjustment fields | no | No dividend, split, adjustment factor, or corporate-action fields observed. |
| consistent shape across FPT/VNM/VCB | yes | Same top-level structure, same `data` container, same row fields, and same 749-row coverage. |

--- 

#### Readiness decision

- The endpoint is sufficient for OHLC-only chart mapping review.
- It is not sufficient for canonical OHLCV ingestion because volume and trading value are missing.
- It is not enough to satisfy the mentor direction to store all useful adjusted and unadjusted price bases, because only one price basis is visible.
- It does not provide dividend, split, corporate-action, or adjustment-related fields needed for the planned one-table OHLCV MVP design.
- Do not implement an OHLCV parser or fetcher from this payload yet.
- Do not fetch the full 1598-symbol universe yet.
- No DB/backtest work should proceed from this endpoint alone.

Next DevTools discovery should search for endpoints, request payloads, or response fields containing:

- `volume`
- `value`
- `ohlcv`
- `historical-price`
- `trading-history`
- `quote`
- `adjusted`
- `dividend`
- `split`
- `corporate-action`

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
- The canonical daily re-fetch, dedup, and dynamic-universe policy lives in `docs/ingestion_v2_schema_plan.md`.
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

### Financial Statement / FA Data Discovery Plan

<details open>
<summary>Vietcap IQ FA endpoints still need manual DevTools discovery before any parser or fetcher work.</summary>

---

#### Current status

- Mentor requirement: Vietcap IQ financial statement and FA data should be fetched with full available history where possible.
- Verified so far: Vietcap IQ broad universe/search-bar JSON, company/profile-like universe fields, research/report HTML surfaces, and gap-chart OHLCV.
- Not verified yet: row-level financial statement, ratio, dividend, corporate-action, or full-history FA JSON endpoints.
- No financial statement parser, financial statement fetcher, database migration, database write, or backtest is implemented.
- The committed source-probe example has only a placeholder `vietcap_iq_reports_candidate`; it is not a verified endpoint.
- `scripts/probe_sources.py` and the source-probe config model can support static browser-observed `GET`/`POST` targets, request bodies, expected content-type/body checks, auth env handling, and secret redaction. Use this only after manual endpoint review.

#### Target data groups

| Data group | Desired coverage | Notes |
|---|---|---|
| Income statement | full available history; yearly and quarterly where available | Revenue, gross profit, operating profit, net income, EPS, and source line-item labels. |
| Balance sheet | full available history; yearly and quarterly where available | Assets, liabilities, equity, cash, debt, inventory, receivables, and source line-item labels. |
| Cash flow | full available history; yearly and quarterly where available | Operating, investing, financing cash flow, capex, free-cash-flow candidates, and source line-item labels. |
| Financial ratios | full available history; yearly and quarterly where available | Margins, ROE/ROA, leverage, liquidity, valuation ratios, and source ratio names/units. |
| Company profile / sector metadata | current plus source-updated history if exposed | Company name, sector/industry, listing metadata, flags, and profile fields from search/profile payloads. |
| Dividends / corporate actions | full available history if exposed | Use only if a verified endpoint exposes dividend, split, issue, or adjustment event rows. |

#### Expected canonical tables

| Candidate table | Role |
|---|---|
| `financial_statement_facts` | Generic long-form financial statement facts with symbol, period, statement type, line item, value, unit, and lineage. |
| `income_statement_items` | Optional statement-specific output if a wide/typed dry run is useful. |
| `balance_sheet_items` | Optional statement-specific output if a wide/typed dry run is useful. |
| `cash_flow_items` | Optional statement-specific output if a wide/typed dry run is useful. |
| `financial_ratios` | Ratio facts with ratio name, value, unit, fiscal period, and source lineage. |
| `company_profiles` | Profile and sector metadata linked to `securities_master` / `instrument_universe`. |
| `corporate_actions` | Only if source exposes verified dividend, split, issue, or adjustment-event rows. |

#### Source discovery workflow

1. Open Vietcap IQ company pages for `FPT`, `VNM`, `VCB`, `REE`, and `SAM`.
2. Use browser DevTools Network and filter XHR/fetch.
3. Inspect company tabs for Financials, `Bao cao tai chinh`, ratios, profile, dividends, and corporate-action surfaces.
4. Capture endpoint URL, method, query params or request body, required headers, and whether the response is public or account-bound.
5. Inspect response shape for row-level JSON, statement type, fiscal year/quarter, period end date, publication or update timestamp, line-item names, values, units, and currency.
6. Add local-only source-probe targets after manual review; do not commit cookies, tokens, account-specific URLs, or local secrets.
7. Run tiny probes only, starting with `FPT`, then `VNM`, `VCB`, `REE`, and `SAM` if shape and access are stable.
8. Preserve raw `payload.json` and non-secret `metadata.json` before any normalization.
9. Write a parser dry run only after row-level JSON is verified; keep outputs local CSV/report/summary artifacts.

#### Guardrails and readiness gates

- No full-universe FA fetch until tiny endpoint behavior, terms/access, period coverage, and rate-limit behavior are reviewed.
- No database migration, database write, canonical ingestion, backtest, or production FA tool until parser dry-run evidence exists.
- Do not print or commit cookies, tokens, browser session identifiers, or local-only config.
- Preserve raw lineage: source name, endpoint label, request scope, content hash, raw path, metadata path, parser version, and schema version.
- Quality flags must separate missing optional values, unsupported statement rows, duplicate periods/items, invalid numeric values, and point-in-time availability gaps.
- Point-in-time fields are mandatory for later backtest safety: fiscal period, period end date, source updated timestamp, published/available timestamp if exposed, and raw capture time.

Next decision:

- Start manual DevTools discovery for Vietcap IQ financial statement and ratio endpoints; only after a concrete endpoint is captured should a local source-probe target be added and probed.

---

</details>

### FA Endpoint Tiny Probe Result

<details open>
<summary>Five FPT-only FA endpoint candidates were probed with non-secret headers, but direct access returned 403.</summary>

---

#### Probe scope

| Item | Value |
|---|---|
| command | `python scripts/probe_sources.py --sources vietcap_iq --symbols FPT --start 2026-06-01 --end 2026-06-03 --targets-config config/source_probe_targets.local.json` |
| run_id | `20260608T083412Z` |
| symbol scope | `FPT` only |
| endpoint scope | Five manually observed Vietcap IQ FA candidates only. |
| raw payloads saved | none |
| metadata files saved | none |
| report | `reports/source_probe_report.md` |

The first sandboxed attempt could not open sockets (`WinError 10013`), so the same command was rerun with network permission. The network-reaching run returned HTTP `403` for all five candidates. No endpoint was retried after the `403` result.

#### Target result

| Target | Dataset | Access status | Auth status | HTTP result | Raw path | Observed keys | Data shape | First classification |
|---|---|---|---|---|---|---|---|---|
| `vietcap_iq_fa_financial_statement_balance_sheet_fpt_candidate` | `vietcap_iq_fa_financial_statement_balance_sheet` | `auth_required` | `auth_or_access_failed` | `403 Forbidden` | none | none | unavailable | `financial_statement_facts` / `balance_sheet_items` candidate |
| `vietcap_iq_fa_financial_statement_metrics_fpt_candidate` | `vietcap_iq_fa_financial_statement_metrics` | `auth_required` | `auth_or_access_failed` | `403 Forbidden` | none | none | unavailable | `financial_statement_metrics` candidate |
| `vietcap_iq_fa_short_financial_fpt_candidate` | `vietcap_iq_fa_short_financial` | `auth_required` | `auth_or_access_failed` | `403 Forbidden` | none | none | unavailable | `short_financial_summary` candidate |
| `vietcap_iq_fa_last_quarter_financial_fpt_candidate` | `vietcap_iq_fa_last_quarter_financial` | `auth_required` | `auth_or_access_failed` | `403 Forbidden` | none | none | unavailable | `last_quarter_financial_snapshot` candidate |
| `vietcap_iq_fa_statistics_financial_fpt_candidate` | `vietcap_iq_fa_statistics_financial` | `auth_required` | `auth_or_access_failed` | `403 Forbidden` | none | none | unavailable | `financial_statistics` candidate |

Because no raw JSON was saved, the browser-observed wrapper keys (`serverDateTime`, `traceId`, `status`, `code`, `msg`, `exception`, `successful`, `data`) are not yet verified by source-probe output, and there is no row-level payload available for parser planning.

#### Remaining unknowns

- Full-history parameters.
- Quarter/year frequency controls.
- Point-in-time availability fields.
- Exact units and currency semantics.
- Whether `section` supports `INCOME_STATEMENT` and `CASH_FLOW`.
- Whether access requires account-bound browser session context, additional non-secret browser headers, or provider-approved credentials.

Guardrails confirmed:

- FPT only.
- No full universe.
- No database write.
- No parser or backtest.
- No cookies, tokens, authorization headers, or local secrets were added to docs.

Next decision:

- Review access/terms and required non-secret browser context before another tiny probe. Parser work remains blocked until at least one FA endpoint returns saved row-level JSON.

---

</details>

### FA Short-Financial Header Context Diagnostic

<details open>
<summary>Adding non-secret browser-like headers did not resolve the short-financial 403.</summary>

---

#### Diagnostic scope

| Item | Value |
|---|---|
| command | `python scripts/probe_sources.py --sources vietcap_iq --symbols FPT --start 2026-06-01 --end 2026-06-03 --targets-config config/source_probe_targets.local.json` |
| run_id | `20260608T090818Z` |
| endpoint tested | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/FPT/short-financial?lengthReport=10` |
| target | `vietcap_iq_fa_short_financial_fpt_header_context_candidate` |
| dataset | `vietcap_iq_fa_short_financial_header_context` |
| symbol scope | `FPT` only |
| endpoint scope | one endpoint only |

Header context was browser-like but non-secret: JSON accept headers, Vietnamese/English language preference, Vietcap Trading origin/referer context, browser-like user agent, and `Sec-Fetch-*` request context. No `Cookie`, `Authorization`, access token, session token, or local secret was used.

#### Result

| Field | Value |
|---|---|
| access status | `auth_required` |
| auth status | `auth_or_access_failed` |
| HTTP result | `403 Forbidden` |
| raw path | none |
| metadata path | none |
| top-level keys | unavailable |
| `data` shape | unavailable |
| parser readiness | blocked |

Conclusion:

- Non-secret browser-like headers alone are not enough for this FA endpoint from the source-probe runner.
- The browser `200` result may depend on account-bound browser session context, provider-approved access, or other access/terms conditions that should not be copied into committed config or docs.
- Parser planning remains blocked until a compliant tiny probe saves row-level FA JSON.

Guardrails confirmed:

- FPT only.
- One endpoint only.
- No `Cookie` or `Authorization`.
- No full universe.
- No database write.
- No parser.
- No backtest.

---

</details>

### FA HTTPX Session Diagnostic Result

<details open>
<summary>httpx page bootstrap reached the company page but the FA API still returned 403.</summary>

---

#### Diagnostic scope

Mentor suggested using `httpx` as a browser-like session. The diagnostic used one `httpx.Client`, first loading the company financial page, then calling one FA API endpoint with the same client/session.

| Item | Value |
|---|---|
| command | `python scripts/probe_vietcap_iq_fa_httpx_session.py` |
| run_id | `20260608T100523Z` |
| symbol | `VCI` |
| page URL | `https://trading.vietcap.com.vn/iq/company?ticker=VCI&tab=financial&isIndex=false&financialTab=financialStatement` |
| API URL | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement?section=BALANCE_SHEET` |
| dataset | `vietcap_iq_fa_financial_statement_balance_sheet_httpx_session` |
| metadata path | `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260608T100523Z/vietcap_iq_fa_financial_statement_balance_sheet_httpx_session/metadata.json` |
| raw payload path | none |

#### Result

| Field | Value |
|---|---|
| page HTTP status | `200` |
| API HTTP status | `403` |
| access status | `auth_required` |
| API content type | `text/html` |
| payload saved | no |
| response top-level type | unavailable |
| response top-level keys | unavailable |
| `data` shape | unavailable |
| parser readiness | blocked |

Conclusion:

- `httpx.Client` page bootstrap alone does not resolve FA API access.
- The page request itself is reachable, but the FA API remains blocked by an access/session/provider-terms gate.
- No row-level FA JSON was saved, so parser planning remains blocked.

Guardrails confirmed:

- No manual `Cookie` or `Authorization`.
- Cookies and authorization values were not saved to metadata.
- One symbol only.
- One endpoint only.
- No full universe.
- No parser.
- No database write.
- No backtest.

---

</details>

### FA HTTPX Browser-Session Warm-Up Diagnostic

<details open>
<summary>httpx warm-up: trading subdomain public endpoints returned 200; all iq subdomain endpoints (warm-up + FA API) returned 403.</summary>

---

#### Mentor direction

Mentor said the 403 is a request-context blocking issue that can be passed with httpx. The previous diagnostic only hit the financial page then called the FA API directly, used a fake User-Agent, and applied no warm-up sequence.

This run adds:
- Real Chrome/Edge User-Agent string.
- A 5-step warm-up sequence on the same `httpx.Client` before the FA API call.
- Correct `Sec-Fetch-*`, `Origin`, `Referer`, and `sec-ch-ua` hints on JSON requests.

#### Scope

| Item | Value |
|---|---|
| command | `python scripts/probe_vietcap_iq_fa_httpx_session.py --symbol VCI --section BALANCE_SHEET` |
| run_id | `20260609T024007Z` |
| symbol | `VCI` |
| page URL | `https://trading.vietcap.com.vn/iq/company?ticker=VCI&tab=financial&isIndex=false&financialTab=financialStatement` |
| warm-up endpoints | 5 public/browser-observed endpoints (3 on `trading.*`, 2 on `iq.*`) |
| API URL | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement?section=BALANCE_SHEET` |
| metadata path | `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260609T024007Z/vietcap_iq_fa_financial_statement_balance_sheet_httpx_session/metadata.json` |
| raw payload path | none |

#### Result

| Field | Value |
|---|---|
| page HTTP status | `200` |
| warm-up: `configuration-service/v1/non-authen/app-config` | `200 application/json` |
| warm-up: `price/marketStatus/getAll` | `200 application/json` |
| warm-up: `market-data-service/v1/data-version` | `200 application/json` |
| warm-up: `iq-insight-service/v2/company/search-bar` | `403 text/html` |
| warm-up: `iq-insight-service/v1/company/details?ticker=VCI` | `403 text/html` |
| FA API HTTP status | `403` |
| access status | `auth_required` |
| API content type | `text/html` |
| payload saved | no |
| parser readiness | blocked |

#### Conclusion

- All three `trading.vietcap.com.vn` public endpoints returned `200`.
- All two `iq.vietcap.com.vn` warm-up endpoints returned `403`, and the FA API also returned `403`.
- In this httpx warm-up flow, `trading.*` public endpoints returned `200` while all `iq.*` endpoints returned `403`.
- This suggests missing request context, session/access requirement, or header/profile mismatch on the `iq.*` subdomain in the current httpx flow.
- Note: the Vietcap IQ universe search-bar endpoint previously returned results in an earlier source-probe context; that request profile has not yet been directly compared against the current httpx warm-up flow.
- Next step: compare the current httpx request profile against the previously working search-bar/source-probe request profile before concluding whether provider-approved auth or a different session mechanism is required.
- No row-level FA JSON was saved; parser planning remains blocked.

#### Guardrails confirmed

- No manual `Cookie` or `Authorization`.
- Cookies and authorization values were not saved to metadata.
- One symbol only (`VCI`).
- One FA endpoint only.
- No full universe.
- No parser.
- No database write.
- No backtest.

---

</details>

### FA Search-Bar Parity Diagnostic

<details open>
<summary>Fresh httpx session with 8-header search-bar profile returned HTTP 200 — suggests the warm-up flow introduced state that made iq.* return 403; the iq subdomain is accessible with a clean request profile.</summary>

---

#### Run details (run `20260609T032924Z`)

| Field | Value |
|---|---|
| Diagnostic target | `search-bar` |
| Target URL | `https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1` |
| Referer style | `trading-company-page` |
| HTTP status | `200` |
| Access status | `verified` |
| Content type | `application/json` |
| Response top-level type | `dict` |
| Response top-level keys | `code, data, exception, msg, serverDateTime, status, successful, traceId` |
| `data` type | `list` |
| `data` length | `2083` |
| Manual cookie header set | `false` |
| Manual authorization header set | `false` |
| Cookies saved | `false` |
| Authorization saved | `false` |

---

#### Request profile used

| Header | Value |
|---|---|
| `Accept` | `application/json, text/plain, */*` |
| `Accept-Language` | `vi,en-US;q=0.9,en;q=0.8` |
| `User-Agent` | Chrome 148 / Edge 148 (real UA) |
| `Origin` | `https://trading.vietcap.com.vn` |
| `Referer` | `https://trading.vietcap.com.vn/iq/company?ticker=VCI&tab=overview&isIndex=false` |
| `Sec-Fetch-Dest` | `empty` |
| `Sec-Fetch-Mode` | `cors` |
| `Sec-Fetch-Site` | `same-site` |

No `sec-ch-ua*` headers. No `Cookie`. No `Authorization`.

---

#### Key finding

A fresh `httpx.Client` session (no prior page load, no prior trading subdomain warm-up) with the 8-header search-bar profile returns `200 JSON` from `iq.vietcap.com.vn`. This directly contradicts the previous warm-up diagnostic (run `20260609T024007Z`) where the same URL returned `403` inside a session that had already made requests to `trading.vietcap.com.vn`.

Candidate root causes (narrowed, not yet confirmed):

1. **Session cookies from trading subdomain reaching iq subdomain.** Cookies set by `trading.vietcap.com.vn` may be scoped to `.vietcap.com.vn` (parent domain) and thus sent automatically by `httpx.Client` to `iq.vietcap.com.vn`. The iq backend may check for a valid authenticated session; if the cookie carries a partially-initialised or unauthenticated session token, the server rejects it as `403`. A fresh session carries no cookies and the server falls back to unauthenticated-public behaviour — returning `200` for the public search-bar.
2. **`sec-ch-ua*` headers triggering a stricter server path.** The warm-up used 11 headers including `sec-ch-ua`, `sec-ch-ua-mobile`, and `sec-ch-ua-platform`. The parity probe uses 8 headers without them. The server may interpret the presence of client hints as an indication of a full browser session and require a corresponding authenticated context.

Both causes, or a combination, could explain the pattern. Note that this result applied to the public search-bar endpoint only. The FA endpoint was subsequently tested with the same clean profile — see the "FA Direct Clean-Profile Diagnostic" section below.

---

#### Guardrails and terms notes

- No manual `Cookie` or `Authorization` header.
- No parser run.
- No database write.
- No backtest.
- Payload captured for inspection only under `data/raw/httpx_diagnostic/`.

---

</details>

### FA Direct Clean-Profile Diagnostic

<details open>
<summary>FA endpoint returned HTTP 200 with a clean 8-header httpx profile — no warm-up, no Cookie, no Authorization, no sec-ch-ua* headers.</summary>

---

#### Why this test was run

The search-bar parity diagnostic (run `20260609T032924Z`) showed that a fresh `httpx.Client` with an 8-header clean profile can reach `iq.vietcap.com.vn`. This test applied the same approach directly to the FA financial-statement endpoint to check whether it behaves the same way or has stricter access requirements.

**Command used:**

```
python scripts/probe_vietcap_iq_fa_httpx_session.py \
  --diagnostic-target fa-direct \
  --symbol VCI \
  --section BALANCE_SHEET \
  --referer-style trading-company-page
```

---

#### Run details (run `20260609T035318Z`)

| Field | Value |
|---|---|
| Diagnostic target | `fa-direct` |
| Target URL | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement?section=BALANCE_SHEET` |
| Referer style | `trading-company-page` |
| HTTP status | `200` |
| Access status | `verified` |
| Content type | `application/json` |
| Byte size | `354,443` |
| Response top-level type | `dict` |
| Response top-level keys | `code, data, exception, msg, serverDateTime, status, successful, traceId` |
| `data` type | `dict` |
| `data` keys | `quarters, years` |
| `data` length | `null` (data is a dict, not a list) |
| Manual cookie header set | `false` |
| Manual authorization header set | `false` |
| Cookies saved | `false` |
| Authorization saved | `false` |

---

#### Request profile used

| Header | Value |
|---|---|
| `Accept` | `application/json, text/plain, */*` |
| `Accept-Language` | `vi,en-US;q=0.9,en;q=0.8` |
| `User-Agent` | Chrome 148 / Edge 148 (real UA) |
| `Origin` | `https://trading.vietcap.com.vn` |
| `Referer` | `https://trading.vietcap.com.vn/iq/company?ticker=VCI&tab=overview&isIndex=false` |
| `Sec-Fetch-Dest` | `empty` |
| `Sec-Fetch-Mode` | `cors` |
| `Sec-Fetch-Site` | `same-site` |

No `sec-ch-ua*` headers. No `Cookie`. No `Authorization`.

---

#### Payload shape (inspection only — no parser)

- Top-level response is a `dict` with keys `code, data, exception, msg, serverDateTime, status, successful, traceId`.
- `data` is a `dict` with keys `quarters` and `years`.
- Both `quarters` and `years` likely contain financial statement rows by period; exact structure and field names not yet inspected.
- No parser has been run. No schema has been promoted. No DB write has been made.

---

#### Conclusion

The FA endpoint is accessible with a clean 8-header httpx request profile — the same profile that reached the search-bar endpoint. This means the previous `403` results from the warm-up session diagnostic were likely caused by session state (cookies from `trading.vietcap.com.vn` or `sec-ch-ua*` headers) rather than an endpoint-level access requirement. Parser planning for this endpoint can now advance to payload-shape review.

Next steps:
- Review the `data.quarters` and `data.years` structure to understand the financial statement row format.
- Test at least one other section (e.g., `INCOME_STATEMENT`) and one other symbol before concluding the access pattern is general.
- No full-universe fetch, no parser implementation, no DB write until those reviews are done.

---

#### Guardrails and terms notes

- No manual `Cookie` or `Authorization` header.
- No warm-up sequence. Fresh `httpx.Client` only.
- One symbol (`VCI`), one section (`BALANCE_SHEET`), one request.
- No parser run.
- No database write.
- No backtest.
- Payload captured for shape inspection only under `data/raw/httpx_diagnostic/`.

---

#### Payload-shape review

A compact payload-shape review (field structure, period encoding, metric prefix groups, PIT warning, proposed canonical schema, and next steps) has been added at:

`docs/data_sources/vietcap_iq_fa_payload_shape_review.md`

#### Shape cross-check

A cross-check of the access profile and payload shape across VCI INCOME_STATEMENT and FPT BALANCE_SHEET has been added at:

`docs/data_sources/vietcap_iq_fa_shape_cross_check.md`

Both additional probes returned HTTP 200. Initial section/symbol cross-check passed for the clean 8-header profile. Parser dry-run design can start.

#### FA Parser Dry-Run

A local-only wide-to-long parser dry-run has been implemented at:

`docs/data_sources/vietcap_iq_fa_parser_dry_run.md`

Parser script: `scripts/parse_vietcap_iq_fa_payloads_dry_run.py`

Key results: `34,563` long-format fact rows from three saved payloads; null/zero distinction preserved; `line_item_name` empty (no mapping); no DB write, no backtest; `publicDate` PIT semantics unconfirmed.

#### Metric Mapping Discovery

A mapping discovery audit was run. An initial probe (run `20260609T091305Z`) failed at DNS level.
A re-probe (run `20260610T025420Z`) succeeded: HTTP 200, mapping payload confirmed with 1078
non-null metric codes across sections BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, NOTE. Coverage
against saved probe payloads: 62.8% BS / 43.6% IS / 65.8% CF — below the 95% gate threshold.
See `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` and
`docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` for full details.

#### FA Ingestion V2 Readiness Package

A readiness document, manifest planner, and tests were added for the FA ingestion V2 phase:

| Artifact | Path | Notes |
|---|---|---|
| Readiness document | `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` | Defines all confirmed facts, open gates, policies, and next steps |
| Manifest planner script | `scripts/plan_vietcap_iq_fa_full_history_manifest.py` | Dry-run only; generates a deterministic fetch-plan CSV with no network requests |
| Manifest tests | `tests/test_plan_vietcap_iq_fa_full_history_manifest.py` | 43 tests |

#### FA Mapping and CASH_FLOW Probe Package

Additional scripts and docs added for the mapping retrieval and CASH_FLOW coverage phase:

| Artifact | Path | Notes |
|---|---|---|
| Probe report | `docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` | Results for mapping re-probe and VCI/FPT CASH_FLOW probes |
| Mapping parser script | `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` | Offline only; no network, no DB; outputs deterministic mapping CSV and optional coverage report |
| Mapping parser tests | `tests/test_parse_vietcap_iq_fa_metric_mapping_dry_run.py` | 50 tests |

Key constraints still enforced:

- `line_item_name` remains empty in parser output — mapping coverage is below the 95% gate threshold.
- `publicDate` is a candidate field only — PIT semantics are unconfirmed.
- CASH_FLOW section is now confirmed (same envelope, HTTP 200 for VCI and FPT).
- Full-history FA fetch is planned but not implemented.
- DB write remains blocked (§17 of readiness doc).
- Backtest remains blocked (§18 of readiness doc).

Mapping parser CLI example:

```
python scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py \
  --output-mapping data/processed/vietcap_iq/fa_metric_mapping.csv \
  --probe-dir data/raw/httpx_diagnostic/source=vietcap_iq \
  --output-coverage data/processed/vietcap_iq/fa_metric_mapping_coverage.csv
```

#### FA Mapping Coverage Bank/Insurance Probe Package

Additional mapping payloads retrieved for VCB (bank), BVH (insurance), and SSI (securities)
to investigate the INCOME_STATEMENT coverage gap (VCI-only: 43.6%). Key finding: **the mapping
is firm-type-specific**. SSI returned the identical mapping to VCI. VCB returned bank-specific
codes (`isb*`, `bsb*`, `cfb*`). BVH returned insurance-specific codes (`isi*`, `bsi*`).

Union of 4 firm-type mappings: 1793 codes, 88 name conflicts (4.9%).

| Section | VCI-only % | Union % | Gate (95%) |
|---|---|---|---|
| BALANCE_SHEET | 62.8% | **89.4%** | **blocked** |
| INCOME_STATEMENT | 43.6% | **92.3%** | **blocked** |
| CASH_FLOW | 65.8% | **86.7%** | **blocked** |

No section reaches the 95% gate. `line_item_name` remains empty. DB write and backtest remain blocked.

| Artifact | Path | Notes |
|---|---|---|
| Probe report | `docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` | Bank/insurance probe results, union analysis, coverage table, integration strategy discussion |
| Union analysis script | `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` | Offline; reads saved payloads; outputs union mapping CSV and coverage CSV; no network, no DB |
| Union analysis tests | `tests/test_analyze_vietcap_iq_fa_metric_mapping_union.py` | 39 tests |

Union analysis CLI example:

```
python scripts/analyze_vietcap_iq_fa_metric_mapping_union.py \
  --probe-dir data/raw/httpx_diagnostic/source=vietcap_iq \
  --output-union data/processed/vietcap_iq/fa_metric_mapping_union.csv \
  --output-coverage data/processed/vietcap_iq/fa_metric_mapping_union_coverage.csv
```

#### FA Mapping Integration Strategy

Mapping integration strategy designed (not implemented). Recommended: Option C — Hybrid
gated mapping. Per-symbol mapping as primary, union consensus (conflict-free only) as
fallback, with provenance columns (`line_item_name_en`, `mapping_status`,
`mapping_source_symbol`, `mapping_source_run_id`, `mapping_conflict`). Existing
`line_item_name` remains empty until integration is implemented and tested.

See `docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md`.

`line_item_name` is not populated. DB write and backtest remain blocked.

#### FA Firm-Type Determination Design

Firm-type determination logic designed (not integrated into parser). Recommended:
Approach D — Hybrid metadata-primary. Uses `company_type_code` from the Vietcap IQ
universe CSV to select the correct firm-type-specific mapping payload:

| `company_type_code` | Mapping group | Source symbol |
|---|---|---|
| `NH` (bank) | bank | VCB |
| `BH` (insurance) | insurance | BVH |
| `CK` (securities) | securities | VCI |
| `CT`, `QU`, other | general | (none — consensus fallback only) |

Explicit overrides for the 4 directly-probed symbols (VCI, SSI, VCB, BVH) take precedence.
Planner script: `scripts/plan_vietcap_iq_fa_firm_type_mapping.py` (offline, 46 tests).
Parser code not changed. `line_item_name` remains empty.

See `docs/data_sources/vietcap_iq_fa_firm_type_determination.md`.

#### FA Option C Mapping Resolver

Pure offline Option C mapping resolver implemented. Script:
`scripts/resolve_vietcap_iq_fa_metric_mapping.py` (74 tests, 487 total passing).

Resolves `(section, line_item_code)` → `MappingResult` with six statuses:

| Status | Meaning |
|--------|---------|
| `primary` | Code found in firm-type-specific primary mapping, section matches |
| `consensus_fallback` | Primary miss; code in union with `conflict=false`, section matches |
| `conflict_skipped` | Code in union with `conflict=true` — name withheld |
| `not_covered` | Code absent from primary and union |
| `no_mapping_available` | Primary expected (`has_primary=True`) but no rows loaded |
| `section_mismatch` | Code found but stored section does not match queried section |

See `docs/data_sources/vietcap_iq_fa_mapping_resolver_tests.md`.

---

#### FA Parser Mapping Integration

Resolver wired into `scripts/parse_vietcap_iq_fa_payloads_dry_run.py`. 7 new output columns
added after `line_item_name` (legacy — always empty): `line_item_name_en`, `line_item_name_vi`,
`mapping_status`, `mapping_source_symbol`, `mapping_source_run_id`, `mapping_conflict`,
`mapping_group`. All columns default to `""` when no mapping flags are supplied (backward
compatible). Existing tests unchanged (552 total passing, +65 new tests).

Dry-run validated on 5 saved payloads (VCI BS / IS / CF, FPT BS / CF): 53,013 fact rows,
0 errors. VCI BALANCE_SHEET: 87% rows named (11,849/13,571). No DB write. No backtest.
`publicDate` PIT semantics still unconfirmed. Mapping coverage still below 95% DB-write gate.

See `docs/data_sources/vietcap_iq_fa_parser_mapping_integration.md`.

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