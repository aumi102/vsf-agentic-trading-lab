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

Escalation rule:

- Only after FPT works at a larger countBack should the same small-symbol probe be repeated for `VNM` and `VCB`.
- Do not run this over the full 1598-symbol listed-market universe.
- Do not implement a production fetcher from this exploration.
- Do not perform database migrations, database writes, or backtests.

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
