---
title: ingestion_v2_schema_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Ingestion V2 Schema Plan

### 1. Executive Summary

<details open>
<summary>VBMA and FRED are ready for parser planning; HOSE and Vietcap IQ still need row-level endpoint discovery.</summary>

---

#### What is ready now

- **VBMA** is ready for ingestion v2 planning for government bond auction results. The verified raw sample is row-level and parses as an XLSX spreadsheet even though the endpoint path ends in `.csv`.
- **FRED** is ready for macro-context ingestion planning. The verified raw sample is structured JSON with top-level series metadata and nested observations.

#### What is not ready yet

- **HOSE** is not ready for ingestion. The current verified sample is an HTML/JavaScript app shell, not row-level listing or market data.
- **Vietcap IQ** is not ready for ingestion. The current verified sample is an HTML/report surface that points toward IQ/report pages, but it does not contain report-list rows or document metadata.

#### Why VBMA plus FRED first

- They are the only sources with verified row-level or observation-level payloads.
- They are context sources, so they can be implemented without blocking the still-open stock-market source discovery work.
- They exercise the ingestion architecture needed later: raw payload preservation, parser versioning, canonical schema mapping, point-in-time fields, and quality reports.

---

</details>

### 2. Ingestion V2 Scope

<details open>
<summary>The first v2 scope is macro and bond context, not stock OHLCV or backtesting.</summary>

---

#### In scope

- VBMA government bond auction results.
- FRED macro series and observations.
- Raw payload provenance, parser outputs, canonical table proposals, and validation gates.

#### Out of scope for now

- HOSE ingestion until actual row-level JSON/XHR endpoints are captured.
- Vietcap IQ ingestion until report-list and document APIs are captured.
- Stock OHLCV ingestion.
- Price board/order book ingestion.
- Backtest engine.
- Database migrations or production storage changes.

---

</details>

### 3. Proposed Canonical Schema

<details open>
<summary>The schema keeps source runs and raw payloads separate from normalized macro and bond tables.</summary>

---

#### `source_runs`

| Column | Type | Required | Notes |
|---|---:|---|---|
| `run_id` | string | yes | Primary key. Timestamp-style run ID from probe/ingestion. |
| `source_name` | string | yes | `vbma` or `fred` for this scope. |
| `adapter_name` | string | yes | Adapter/parser owner. |
| `target_name` | string | yes | Configured probe/ingestion target name. |
| `dataset` | string | yes | Source dataset such as `vbma_primary_market_auction_results`. |
| `started_at` | timestamp | yes | UTC ingestion start. |
| `completed_at` | timestamp | no | UTC ingestion completion. |
| `status` | string | yes | `success`, `partial`, or `fail`. |
| `config_hash` | string | no | Hash of non-secret config fields. |
| `parser_version` | string | yes | Parser contract version. |
| `schema_version` | string | yes | Canonical schema version. |
| `warnings` | array/string | no | Machine-readable warning codes. |
| `errors` | array/string | no | Machine-readable error codes. |

Primary key:

- `run_id`

Unique key:

- `source_name + target_name + started_at`

#### `raw_source_payloads`

| Column | Type | Required | Notes |
|---|---:|---|---|
| `raw_payload_id` | string | yes | Primary key. Use deterministic hash or `run_id + dataset + sequence`. |
| `run_id` | string | yes | Foreign key to `source_runs`. |
| `source_name` | string | yes | Source owner. |
| `dataset` | string | yes | Dataset or endpoint label. |
| `endpoint_or_surface` | string | yes | Redacted URL or surface label. |
| `request_params_json` | json/string | yes | Must exclude secrets. |
| `http_status` | integer | no | HTTP response code when applicable. |
| `content_type` | string | no | Raw response content type. |
| `raw_path` | string | yes | Local raw payload path. |
| `metadata_path` | string | yes | Local metadata JSON path. |
| `content_hash` | string | yes | SHA-256 of raw bytes. |
| `byte_size` | integer | no | Raw payload size. |
| `row_count_observed` | integer | no | Parser-observed row count, if known. |
| `crawled_at` | timestamp | yes | UTC raw capture time. |
| `terms_notes` | string | no | Terms/legal notes copied from metadata. |

Primary key:

- `raw_payload_id`

Unique key:

- `content_hash`

#### `macro_series`

| Column | Type | Required | Notes |
|---|---:|---|---|
| `series_id` | string | yes | Primary key. Example: `DGS10`. |
| `source_name` | string | yes | `fred`. |
| `title` | string | no | Requires series metadata endpoint; not in observations sample. |
| `unit` | string | no | From FRED `units` or series metadata. |
| `frequency` | string | no | Requires series metadata endpoint or configured series catalog. |
| `seasonal_adjustment` | string | no | Requires series metadata endpoint. |
| `observation_start` | date | no | From observations response. |
| `observation_end` | date | no | From observations response. |
| `source_payload_id` | string | yes | Raw lineage. |
| `created_at` | timestamp | yes | Canonical write time. |
| `schema_version` | string | yes | Macro schema version. |

Primary key:

- `series_id`

Unique key:

- `source_name + series_id`

#### `macro_observations`

| Column | Type | Required | Notes |
|---|---:|---|---|
| `series_id` | string | yes | Foreign key to `macro_series`. |
| `observation_date` | date | yes | FRED `observations[].date`. |
| `observation_value` | decimal | no | FRED `observations[].value`; `.` becomes null. |
| `realtime_start` | date | yes | FRED vintage start. |
| `realtime_end` | date | yes | FRED vintage end. |
| `source_payload_id` | string | yes | Raw lineage. |
| `quality_status` | string | yes | `pass`, `warn`, or `fail`. |
| `quality_reasons` | array/string | no | Machine-readable quality reasons. |
| `created_at` | timestamp | yes | Canonical write time. |
| `schema_version` | string | yes | Macro schema version. |

Primary key:

- `series_id + observation_date + realtime_start`

Unique key:

- `series_id + observation_date + realtime_start + source_payload_id`

#### `bond_instruments`

| Column | Type | Required | Notes |
|---|---:|---|---|
| `bond_id` | string | yes | Primary key. Candidate rule: `vbma:<bond_code>`. |
| `bond_code` | string | yes | VBMA `Ma trai phieu` / `Mã trái phiếu`. |
| `issuer` | string | yes | VBMA `To chuc phat hanh` / `Tổ chức phát hành`. |
| `tenor_years` | decimal | no | VBMA `Ky han (nam)` / `Kỳ hạn (năm)`. |
| `issue_date` | date | no | Use only after confirming `Ngay TCPH` semantics. |
| `maturity_date` | date | no | Missing in current sample. |
| `coupon_rate_pct` | decimal | no | Missing in current sample. |
| `currency` | string | yes | Default `VND` unless later evidence says otherwise. |
| `source_payload_id` | string | yes | Raw lineage. |
| `created_at` | timestamp | yes | Canonical write time. |
| `schema_version` | string | yes | Bond schema version. |

Primary key:

- `bond_id`

Unique key:

- `source_name + bond_code`

#### `bond_auction_results`

| Column | Type | Required | Notes |
|---|---:|---|---|
| `auction_result_id` | string | yes | Primary key. Candidate hash of `bond_code + auction_date + source_payload_id`. |
| `bond_id` | string | yes | Foreign key to `bond_instruments`. |
| `bond_code` | string | yes | Raw bond code. |
| `issuer` | string | yes | Raw issuer. |
| `tenor_years` | decimal | yes | Parsed tenor. |
| `auction_or_issue_date` | date | yes | From `Ngay TCPH`; final name depends on mentor confirmation. |
| `offered_amount_billion_vnd` | decimal | no | VBMA offered amount. |
| `bid_amount_billion_vnd` | decimal | no | VBMA bid amount. |
| `winning_amount_billion_vnd` | decimal | no | VBMA winning amount. |
| `winning_yield_pct` | decimal | no | VBMA winning yield. |
| `bid_yield_max_pct` | decimal | no | VBMA max bid yield. |
| `bid_yield_min_pct` | decimal | no | VBMA min bid yield. |
| `bid_to_cover_ratio` | decimal | no | Derived as bid amount / offered amount when valid. |
| `amount_unit` | string | yes | Default `billion_vnd`. |
| `source_payload_id` | string | yes | Raw lineage. |
| `quality_status` | string | yes | `pass`, `warn`, or `fail`. |
| `quality_reasons` | array/string | no | Machine-readable quality reasons. |
| `created_at` | timestamp | yes | Canonical write time. |
| `schema_version` | string | yes | Bond schema version. |

Primary key:

- `auction_result_id`

Unique key:

- `bond_code + auction_or_issue_date + source_payload_id`

---

</details>

### 4. Field Mapping Details

<details open>
<summary>FRED maps cleanly to macro tables; VBMA needs file-signature and Vietnamese header normalization.</summary>

---

#### FRED mapping

| Raw field | Canonical table | Canonical field | Normalization rule |
|---|---|---|---|
| Request `series_id` | `macro_series`, `macro_observations` | `series_id` | Preserve from config/request, because it is not repeated per observation body. |
| `units` | `macro_series` | `unit` | Store source value; later map to display unit if needed. |
| `observation_start` | `macro_series` | `observation_start` | Parse as date. |
| `observation_end` | `macro_series` | `observation_end` | Parse as date. |
| `observations[].date` | `macro_observations` | `observation_date` | Parse as date. |
| `observations[].value` | `macro_observations` | `observation_value` | Convert string to numeric; `.` becomes null with warning. |
| `observations[].realtime_start` | `macro_observations` | `realtime_start` | Preserve for vintage handling. |
| `observations[].realtime_end` | `macro_observations` | `realtime_end` | Preserve for vintage handling. |

#### VBMA mapping

| Raw field | Canonical table | Canonical field | Normalization rule |
|---|---|---|---|
| `Mã trái phiếu` | `bond_instruments`, `bond_auction_results` | `bond_code` | Trim string. |
| `Tổ chức phát hành` | `bond_instruments`, `bond_auction_results` | `issuer` | Trim string and preserve source abbreviation. |
| `Kỳ hạn\n(năm)` | `bond_instruments`, `bond_auction_results` | `tenor_years` | Strip newline, parse numeric. |
| `Ngày TCPH` | `bond_auction_results` | `auction_or_issue_date` | Parse as date; confirm exact business meaning with mentor. |
| `Giá trị gọi thầu\n(tỷ đồng)` | `bond_auction_results` | `offered_amount_billion_vnd` | Strip whitespace/newlines; parse numeric. |
| `Giá trị đặt thầu\n(tỷ đồng)` | `bond_auction_results` | `bid_amount_billion_vnd` | Parse numeric; `-` becomes null. |
| `Giá trị trúng thầu\n(tỷ đồng)` | `bond_auction_results` | `winning_amount_billion_vnd` | Parse numeric; `-` becomes null. |
| `Lãi suất trúng thầu (%/y)` | `bond_auction_results` | `winning_yield_pct` | Parse numeric percent; `-` becomes null. |
| `Lãi suất đấu thầu max` | `bond_auction_results` | `bid_yield_max_pct` | Parse numeric percent; `-` becomes null. |
| `Lãi suất đấu thầu min` | `bond_auction_results` | `bid_yield_min_pct` | Parse numeric percent; `-` becomes null. |

#### Parser normalization rules

- FRED `value == "."` becomes null, not zero.
- FRED numeric values arrive as strings and must be parsed to decimal/float.
- VBMA endpoint says `.csv`, but payload may be XLSX.
- Parser selection must inspect file signature and content type, not extension.
- Strip whitespace and newline characters in Vietnamese headers before mapping.
- VBMA `-` in numeric fields becomes null.
- VBMA amounts are treated as billion VND unless later evidence says otherwise.

---

</details>

### 5. Data Quality Checks

<details open>
<summary>Quality gates should fail bad schemas, warn on missing optional context, and preserve raw lineage.</summary>

---

#### Required field checks

- `source_runs`: `run_id`, `source_name`, `target_name`, `dataset`, `started_at`, `status`, `parser_version`, `schema_version`.
- `raw_source_payloads`: `raw_payload_id`, `run_id`, `source_name`, `dataset`, `raw_path`, `metadata_path`, `content_hash`, `crawled_at`.
- `macro_series`: `series_id`, `source_name`, `source_payload_id`.
- `macro_observations`: `series_id`, `observation_date`, `realtime_start`, `realtime_end`, `source_payload_id`.
- `bond_instruments`: `bond_id`, `bond_code`, `issuer`, `currency`, `source_payload_id`.
- `bond_auction_results`: `auction_result_id`, `bond_id`, `bond_code`, `issuer`, `tenor_years`, `auction_or_issue_date`, `source_payload_id`.

#### Type conversion checks

- Parse all dates using a strict date parser.
- Convert FRED observation strings to numeric or null.
- Convert VBMA amount/yield cells to numeric or null.
- Fail rows where required dates or required identifiers cannot be parsed.

#### Duplicate checks

- `macro_observations`: no duplicate `series_id + observation_date + realtime_start`.
- `bond_instruments`: no duplicate `source_name + bond_code`.
- `bond_auction_results`: no duplicate `bond_code + auction_or_issue_date + source_payload_id`.
- `raw_source_payloads`: no duplicate `content_hash` unless intentionally reprocessing the same raw file.

#### Plausibility checks

- FRED values may be negative for some macro series, so plausibility rules must be series-specific.
- VBMA amount fields must be greater than or equal to zero when present.
- VBMA `winning_amount_billion_vnd <= bid_amount_billion_vnd` when both are present.
- VBMA `winning_yield_pct`, `bid_yield_min_pct`, and `bid_yield_max_pct` should be non-negative and within a mentor-approved plausible range.
- VBMA `bid_yield_min_pct <= bid_yield_max_pct` when both are present.

#### Row-count and hash checks

- Record raw row count and parsed row count.
- Warn if a verified source produces zero parsed rows.
- Store raw SHA-256 content hash before parsing.
- Store parser version and schema version with every canonical write.
- Include raw path and metadata path in every canonical row through `source_payload_id`.

---

</details>

### 6. Point-In-Time And Leakage Considerations

<details open>
<summary>Macro and bond data cannot be joined to future trading dates without availability rules.</summary>

---

#### FRED vintage handling

- Preserve `realtime_start` and `realtime_end`.
- Use `realtime_start` or a future release-calendar table to decide when an observation was knowable.
- Do not join a revised macro value into a historical backtest unless the revision was available as of that simulated date.
- Treat observation date and availability date as different concepts.

#### VBMA date ambiguity

- The current VBMA field `Ngày TCPH` needs business-definition confirmation.
- It may represent auction, issue, or issuance-related date depending on VBMA terminology.
- Until confirmed, use `auction_or_issue_date` in planning and avoid overclaiming exact semantics.
- If a separate publication timestamp is later available, store it and use it for point-in-time joins.

#### Backtest leakage rule

- Do not use future FRED macro values in equity or bond-market backtests.
- Do not use VBMA rows dated after a simulated decision date.
- If publication time is unknown, use a conservative availability rule and mark the limitation in validation reports.

---

</details>

### 7. Parser And Ingestion Design

<details open>
<summary>The design should be staged and idempotent; no database migration is required before parser proof.</summary>

---

#### Proposed parser components

- `FredObservationParser`: parse FRED observations JSON into `macro_series` and `macro_observations` rows.
- `VbmaAuctionResultParser`: parse VBMA auction spreadsheet bytes into `bond_instruments` and `bond_auction_results` rows.
- `RawPayloadClassifier`: detect JSON, HTML, CSV, XLSX, or text from file signature and content type.
- `CanonicalQualityValidator`: run table-specific required-field, type, duplicate, and plausibility checks.
- `IngestionReportWriter`: write dry-run inventory and quality summaries before any database write.

#### Proposed stages

```text
raw fetch -> raw store -> parse -> normalize -> validate -> canonical write
```

| Stage | Responsibility | Output |
|---|---|---|
| raw fetch | Call configured source target or consume existing raw payload. | raw bytes plus response metadata. |
| raw store | Persist exact payload and metadata. | `raw_source_payloads` candidate row. |
| parse | Convert raw bytes into source-shaped rows. | parser dataframe/list and parser warnings. |
| normalize | Map source-shaped rows to canonical schema. | canonical row candidates. |
| validate | Run quality gates. | `pass`, `warn`, or `fail` with reasons. |
| canonical write | Write only rows that pass policy. | local files first; database later. |

#### Idempotency strategy

- Raw payload identity is based on `content_hash`.
- Canonical row identity is based on source business keys plus `source_payload_id`.
- Re-running the same raw payload should produce the same canonical row keys.
- Parser version changes should be visible in reports and may create a new canonical dataset version.

#### Error handling strategy

- Missing config or auth remains `not_configured`, not data failure.
- Unsupported payload type returns `parser_unsupported_payload_type`.
- Unknown schema returns `schema_unknown` and does not write canonical rows.
- Partial row failures should quarantine failed rows and report counts.
- No parser should silently coerce `-`, `.`, empty string, or invalid dates without a quality reason.

---

</details>

### 8. Remaining Manual Investigation Tasks

<details open>
<summary>HOSE and Vietcap IQ need real row-level endpoints before ingestion planning.</summary>

---

#### HOSE

- Find actual row-level listing/universe endpoint.
- Then find OHLCV, price board/order book, corporate actions, trading calendar, and index endpoints.
- Capture small raw samples and metadata for each endpoint.
- Confirm terms/robots/access expectations before crawling.
- Verify whether pagination, cookies, or language parameters are required.

#### Vietcap IQ

- Find report-list API endpoint.
- Find document metadata and document download endpoints.
- Confirm access/auth/terms for public and logged-in IQ report surfaces.
- Capture sample report rows with report id, title, published date, category, company symbol, analyst, and document URL.
- Do not ingest reports until timestamp and document availability are clear.

#### Questions to ask mentor

- For VBMA, does `Ngày TCPH` mean auction date, issuance date, or another official date?
- Should VBMA amount fields be stored in billion VND or converted to raw VND?
- Which FRED series should be in the first macro whitelist beyond `DGS10`?
- Should FRED vintage handling use `realtime_start` immediately, or is latest-only acceptable for early context demos?
- Should parser output be local Parquet/CSV first, or should schema migration come before canonical writes?

---

</details>

### 9. Implementation Roadmap

<details open>
<summary>Implement parsers before migrations, and keep HOSE/Vietcap work in manual discovery.</summary>

---

1. Implement VBMA parser only.
   - Input: existing/raw VBMA payload bytes.
   - Output: dry-run `bond_instruments` and `bond_auction_results` rows plus validation report.

2. Implement FRED parser only.
   - Input: existing/raw FRED observations JSON.
   - Output: dry-run `macro_series` and `macro_observations` rows plus validation report.

3. Add dry-run validation.
   - Required fields, type conversion, duplicates, plausibility, row counts, hash checks.
   - No database write yet.

4. Only then consider migrations/storage.
   - Use the parser outputs and quality results to finalize schema types and keys.

5. Continue HOSE/Vietcap manual endpoint discovery.
   - Do not plan their ingestion until row-level raw samples are captured.

---

</details>

### 10. Acceptance Criteria

<details open>
<summary>The plan is ready for coding only when parser inputs, outputs, and quality gates are explicit.</summary>

---

#### Before moving from planning to code

- VBMA raw payload and metadata path are available locally.
- FRED raw payload and metadata path are available locally.
- Canonical table columns and keys are accepted for parser proof.
- Parser behavior for XLSX-via-`.csv`, `-`, `.`, and missing values is defined.
- Dry-run output paths and report names are agreed before writing code.
- No HOSE, Vietcap IQ, stock OHLCV, database, or backtest scope is mixed into the parser task.

#### Tests needed later

- FRED parser converts observation strings to numeric values.
- FRED parser converts `.` to null with a warning.
- FRED parser preserves `realtime_start` and `realtime_end`.
- VBMA parser detects XLSX payload by signature/content, not extension.
- VBMA parser normalizes Vietnamese headers with whitespace/newlines.
- VBMA parser converts `-` numeric fields to null with a warning.
- VBMA parser computes `bid_to_cover_ratio` only when denominator is valid.
- Quality validator detects duplicate macro and bond auction keys.
- Quality validator fails missing required identifiers and dates.
- Reports include raw path, metadata path, content hash, parser version, and schema version.

---

</details>
