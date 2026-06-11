---
title: ingestion_v2_schema_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Ingestion V2 Schema Plan

### Status

| Source | Parser status | DB status |
|---|---|---|
| VBMA (government bond auctions) | Dry-run parser available | Not implemented |
| FRED (macro series/observations) | Dry-run parser available | Not implemented |
| HOSE (listed universe, quote-report) | Dry-run available — see `docs/data_sources/hose_pipeline.md` | Not implemented |
| Vietcap IQ OHLCV | Tiny controlled fetch passed (FPT/VNM/VCB) | Not implemented |
| Vietcap IQ FA | Parser + Option C mapping integration done — 552 tests pass; 53,013 rows; 0 errors | **Blocked** — coverage below 95%; PIT unconfirmed; schema not designed |

No DB writes. No backtests. Current phase: source discovery, parser dry-run, safe fetch planning.

---

### 1. Executive Summary

#### What is ready

- **VBMA**: verified XLSX-behind-`.csv` endpoint; row-level auction results parsed; dry-run parser done.
- **FRED**: structured JSON; series metadata + observations; dry-run parser done.
- **HOSE**: listed-universe, quote-report, stock-only filter; details in `docs/data_sources/hose_pipeline.md`.
- **Vietcap IQ universe**: 2080 rows; 1598 listed-market candidates; fetch planning done.
- **Vietcap IQ FA**: HTTP 200 for BS/IS/CF on VCI + FPT; Option C mapping resolver wired; 7 output columns; 552 tests pass. Remaining blockers: mapping coverage below 95% gate (union: BS 89.4% / IS 92.3% / CF 86.7%); `publicDate` PIT unconfirmed; QuestDB schema not designed.

#### What is not ready

- Stock OHLCV DB/backtest: units, adjustment policy, EOD semantics, and dynamic universe filters unconfirmed.
- Vietcap IQ FA DB write: blocked on mapping, PIT, and schema gates.
- Final tradable assets: not defined — must be selected from broad fetch outputs by liquidity and strategy filters.

#### Why VBMA + FRED first

They are context sources with verified row-level payloads. Implementing them exercises the ingestion architecture (raw payload preservation, parser versioning, canonical schema, PIT fields, quality reports) without blocking open stock-market discovery work.

---

### 2. Ingestion V2 Scope

**In scope:** VBMA government bond auction results; FRED macro series and observations; Vietcap IQ universe dry-run as source discovery artifact; raw payload provenance, parser outputs, canonical table proposals, validation gates.

**Out of scope:** HOSE DB ingestion; Vietcap IQ FA DB write; stock OHLCV ingestion; price board/order book; backtest engine; database migrations.

#### Data layers

| Layer | Purpose | Example |
|---|---|---|
| Raw payload | Preserve exact source response and request metadata | `payload.json`, `metadata.json`, `content_hash` |
| Parsed canonical | Normalize source rows with lineage and quality status | `macro_observations.csv`, `bond_auction_results.csv` |
| Fetch universe | Broad set used by fetchers to collect enough data | Vietcap IQ listed-market candidates |
| Dynamic tradable universe | Select assets later by liquidity, data completeness, strategy | Date-specific tradable candidates |

---

### 3. Proposed Canonical Schema

#### `source_runs`

| Column | Type | Notes |
|---|---:|---|
| `run_id` | string | Primary key |
| `source_name` | string | `vbma` or `fred` |
| `adapter_name` | string | Adapter/parser owner |
| `target_name` | string | Configured probe/ingestion target |
| `dataset` | string | e.g., `vbma_primary_market_auction_results` |
| `started_at` | timestamp | UTC ingestion start |
| `completed_at` | timestamp | UTC ingestion completion |
| `status` | string | `success`, `partial`, or `fail` |
| `parser_version` | string | Parser contract version |
| `schema_version` | string | Canonical schema version |
| `warnings` | array/string | Machine-readable warning codes |
| `errors` | array/string | Machine-readable error codes |

#### `raw_source_payloads`

| Column | Type | Notes |
|---|---:|---|
| `raw_payload_id` | string | Primary key |
| `run_id` | string | FK to `source_runs` |
| `source_name` | string | Source owner |
| `dataset` | string | Endpoint label |
| `endpoint_or_surface` | string | Redacted URL or surface label |
| `request_params_json` | json/string | Must exclude secrets |
| `http_status` | integer | HTTP response code |
| `raw_path` | string | Local raw payload path |
| `metadata_path` | string | Local metadata JSON path |
| `content_hash` | string | SHA-256 of raw bytes |
| `byte_size` | integer | Raw payload size |
| `row_count_observed` | integer | Parser-observed row count |
| `crawled_at` | timestamp | UTC raw capture time |
| `terms_notes` | string | Terms/legal notes from metadata |

#### `macro_series`

| Column | Type | Notes |
|---|---:|---|
| `series_id` | string | Primary key — e.g., `DGS10` |
| `source_name` | string | `fred` |
| `unit` | string | From FRED `units` |
| `frequency` | string | From series metadata or config |
| `observation_start` | date | From observations response |
| `observation_end` | date | From observations response |
| `source_payload_id` | string | Raw lineage |
| `created_at` | timestamp | Canonical write time |
| `schema_version` | string | Macro schema version |

#### `macro_observations`

| Column | Type | Notes |
|---|---:|---|
| `series_id` | string | FK to `macro_series` |
| `observation_date` | date | FRED `observations[].date` |
| `observation_value` | decimal | FRED `observations[].value`; `.` → null |
| `realtime_start` | date | FRED vintage start |
| `realtime_end` | date | FRED vintage end |
| `source_payload_id` | string | Raw lineage |
| `quality_status` | string | `pass`, `warn`, or `fail` |
| `created_at` | timestamp | Canonical write time |
| `schema_version` | string | Macro schema version |

Natural key: `series_id + observation_date + realtime_start`

#### `bond_instruments`

| Column | Type | Notes |
|---|---:|---|
| `bond_id` | string | Primary key — candidate: `vbma:<bond_code>` |
| `bond_code` | string | VBMA `Mã trái phiếu` |
| `issuer` | string | VBMA `Tổ chức phát hành` |
| `tenor_years` | decimal | VBMA `Kỳ hạn (năm)` |
| `issue_date` | date | Confirm `Ngày TCPH` semantics with mentor |
| `currency` | string | Default `VND` |
| `source_payload_id` | string | Raw lineage |
| `created_at` | timestamp | Canonical write time |
| `schema_version` | string | Bond schema version |

#### `bond_auction_results`

| Column | Type | Notes |
|---|---:|---|
| `auction_result_id` | string | Primary key — hash of `bond_code + auction_date + source_payload_id` |
| `bond_id` | string | FK to `bond_instruments` |
| `bond_code` | string | Raw bond code |
| `issuer` | string | Raw issuer |
| `tenor_years` | decimal | Parsed tenor |
| `auction_or_issue_date` | date | From `Ngày TCPH`; confirm exact meaning |
| `offered_amount_billion_vnd` | decimal | VBMA offered amount |
| `bid_amount_billion_vnd` | decimal | VBMA bid amount |
| `winning_amount_billion_vnd` | decimal | VBMA winning amount |
| `winning_yield_pct` | decimal | VBMA winning yield |
| `bid_yield_max_pct` | decimal | VBMA max bid yield |
| `bid_yield_min_pct` | decimal | VBMA min bid yield |
| `bid_to_cover_ratio` | decimal | Derived: bid / offered when valid |
| `amount_unit` | string | Default `billion_vnd` |
| `source_payload_id` | string | Raw lineage |
| `quality_status` | string | `pass`, `warn`, or `fail` |
| `created_at` | timestamp | Canonical write time |
| `schema_version` | string | Bond schema version |

Natural key: `bond_code + auction_or_issue_date + source_payload_id`

**HOSE dry-run:** Details consolidated in `docs/data_sources/hose_pipeline.md`.

---

### 4. Key Normalization Rules

- FRED `value == "."` → null (not zero); string values must be parsed to decimal.
- VBMA endpoint says `.csv` but payload is XLSX — detect by file signature, not extension.
- VBMA `-` in numeric fields → null. Amounts are in billion VND.
- Strip whitespace and newline characters from Vietnamese headers before mapping.
- VBMA `Ngày TCPH` business meaning (auction vs. issue date) needs mentor confirmation.
- FRED `realtime_start` / `realtime_end` must be preserved for vintage/PIT handling.
- Do not join FRED macro values into a backtest without checking revision availability.

---

### 5. Remaining Investigation Tasks

| Task | Source |
|---|---|
| Confirm `Ngày TCPH` exact meaning | VBMA mentor |
| Confirm VBMA amount fields: billion VND or raw VND | VBMA mentor |
| Confirm FRED macro whitelist beyond `DGS10` | FRED mentor |
| Confirm whether FRED latest-only is acceptable for early demos | FRED mentor |
| Find HOSE row-level listing endpoint | HOSE manual |
| Confirm HOSE pagination, cookies, language parameters | HOSE manual |
| Find Vietcap IQ report-list and document metadata endpoints | Vietcap manual |

---

### 6. Implementation Roadmap

1. Implement VBMA parser — input: saved raw bytes; output: `bond_instruments` + `bond_auction_results` dry-run CSVs + validation report.
2. Implement FRED parser — input: saved JSON; output: `macro_series` + `macro_observations` dry-run CSVs + validation report.
3. Add dry-run validation (required fields, type conversion, duplicates, plausibility, hash checks).
4. Only then consider DB migrations — use parser outputs to finalize schema types and keys.
5. Continue HOSE/Vietcap manual endpoint discovery in parallel.
